"""Tracking completo del año: TODAS las fichas, TODOS los estados.

A diferencia de tracking_diario.py (que solo trackea 'Iniciado' con
upsert por cita), este script recorre día por día y trae TODAS las
citas de la tabla de Pacientes citados (Completado, Iniciado,
Pendiente, Agendado, No se Presentó, etc.) y guarda los AGREGADOS
por día en una DB nueva.

No se persisten datos PII (nombre, RUT) en la DB — solo agregados.
Los nombres se imprimen en el output del run (consola + archivo).

Privacidad: la DB no tiene nombres. El archivo de output sí los tiene
(en .gitignore, no se commitea).

Output:
- DB: data/analysis/tracking_completo.db (agregados por día)
- Consola: tabla con todas las fichas del día, agrupadas por estado
- Archivo: data/analysis/tracking_completo_run_<timestamp>.txt
"""
from __future__ import annotations

import io
import logging
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from src.browser_automation import (
    ensure_session_alive,
    extraer_datos_fila,
    get_pacientes_del_dia,
    select_date,
    sort_by_estado,
)
from src.constants import DATE_FORMAT
from src.credentials import list_known_users, load_credentials
from src.logger_config import setup_logger
from src.pancho_skills import login_rayen
from src.plantillas import sanitizar_tipo

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "analysis" / "tracking_completo.db"
FECHA_INICIO_ABSOLUTA = date(2026, 1, 1)


def _init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agregados_diarios (
            fecha TEXT PRIMARY KEY,
            total_citadas INTEGER NOT NULL,
            iniciado INTEGER NOT NULL,
            completado INTEGER NOT NULL,
            pendiente INTEGER NOT NULL,
            agendado INTEGER NOT NULL,
            no_se_presento INTEGER NOT NULL,
            otros INTEGER NOT NULL,
            tipos_iniciado_json TEXT,
            tipos_total_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_run TEXT NOT NULL,
            fecha_inicio_recorrido TEXT NOT NULL,
            fecha_fin_recorrido TEXT NOT NULL,
            dias_recorridos INTEGER,
            total_fichas INTEGER
        )
        """
    )
    conn.commit()
    return conn


def _dias_habiles(inicio: date, fin: date) -> list[date]:
    dias: list[date] = []
    current = inicio
    while current <= fin:
        if current.weekday() < 5:
            dias.append(current)
        current += timedelta(days=1)
    return dias


def _parse_args() -> tuple[date | None, date | None, bool]:
    desde: date | None = None
    hasta: date | None = None
    historico = False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--desde" and i + 1 < len(args):
            desde = datetime.strptime(args[i + 1], DATE_FORMAT).date()
            i += 2
        elif args[i] == "--hasta" and i + 1 < len(args):
            hasta = datetime.strptime(args[i + 1], DATE_FORMAT).date()
            i += 2
        elif args[i] == "--historico":
            historico = True
            i += 1
        else:
            i += 1
    return desde, hasta, historico


def _resolver_usuario() -> str | None:
    KNOWN_FLAGS = {"--desde", "--hasta", "--historico"}
    cli_user = None
    skip_next = False
    for arg in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if arg in KNOWN_FLAGS:
            skip_next = True
            continue
        if arg.startswith("--"):
            continue
        cli_user = arg
        break
    users = list_known_users()
    if not users:
        print("ERROR: no hay usuarios configurados", file=sys.stderr)
        return None
    if cli_user:
        if cli_user not in users:
            print(f"ERROR: '{cli_user}' no está configurado", file=sys.stderr)
            return None
        return cli_user
    return users[0]


def _safe_quit(driver, logger) -> None:
    try:
        from src.browser_automation import safe_quit
        safe_quit(driver, logger)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No se pudo cerrar el browser: {e}")


def _ensure_session_alive(driver, credentials, logger):
    from src.browser_automation import _es_url_login
    if not _es_url_login(driver.current_url):
        return driver
    logger.warning("Sesión expiró, re-logueando...")
    _safe_quit(driver, logger)
    return login_rayen(credentials, logger, headless=False)


class _TeeStdout:
    def __init__(self, original):
        self._original = original
        self._buffer = io.StringIO()

    def write(self, s: str) -> int:
        self._original.write(s)
        return self._buffer.write(s)

    def flush(self) -> None:
        self._original.flush()

    def get_output(self) -> str:
        return self._buffer.getvalue()


def _guardar_output(capturado: str, sufijo: str) -> Path | None:
    if not capturado.strip():
        return None
    try:
        OUT_DIR = BASE_DIR / "data" / "analysis"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUT_DIR / f"tracking_completo_run_{sufijo}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(capturado)
        return path
    except OSError as e:  # noqa: BLE001
        print(f"WARN: no se pudo guardar output: {e}", file=sys.stderr)
        return None


def _import_json():
    import json
    return json


def _run(logger: logging.Logger) -> int:
    print("=" * 60)
    print("TRACKING COMPLETO — TODAS LAS FICHAS, TODOS LOS ESTADOS")
    print("=" * 60)

    user_id = _resolver_usuario()
    if user_id is None:
        return 1

    conn = _init_db()
    desde_arg, hasta_arg, historico = _parse_args()
    if historico:
        inicio = FECHA_INICIO_ABSOLUTA
        print(f"[--historico] Forzando desde {FECHA_INICIO_ABSOLUTA.strftime(DATE_FORMAT)}")
    elif desde_arg:
        inicio = desde_arg
    else:
        # Auto-deteccion: fecha minima registrada en la DB
        cur = conn.execute("SELECT MIN(fecha) FROM agregados_diarios")
        row = cur.fetchone()
        if row and row[0]:
            try:
                fecha_min = datetime.strptime(row[0], DATE_FORMAT).date()
                inicio = max(FECHA_INICIO_ABSOLUTA, fecha_min)
            except ValueError:
                inicio = FECHA_INICIO_ABSOLUTA
        else:
            inicio = FECHA_INICIO_ABSOLUTA
    fin = hasta_arg or date.today()

    if inicio > fin:
        print(f"ERROR: {inicio} es posterior a {fin}", file=sys.stderr)
        return 1

    dias = _dias_habiles(inicio, fin)
    print(
        f"Recorrido planificado: {inicio.strftime(DATE_FORMAT)} → "
        f"{fin.strftime(DATE_FORMAT)} ({len(dias)} días hábiles)"
    )
    print(f"DB: {DB_PATH.relative_to(BASE_DIR)}")
    print()

    if not dias:
        print("No hay días para recorrer.")
        return 0

    try:
        credentials = load_credentials(user_id)
    except (KeyError, ValueError) as e:
        print(f"ERROR cargando credenciales: {e}", file=sys.stderr)
        return 1

    driver = None
    total_fichas_global = 0
    json = _import_json()

    try:
        driver = login_rayen(credentials, logger, headless=False)
        print("[OK] Login realizado. Iniciando recorrido día por día...\n")

        for idx, dia in enumerate(dias, 1):
            fecha_str = dia.strftime(DATE_FORMAT)

            try:
                driver = _ensure_session_alive(driver, credentials, logger)
            except Exception as e:  # noqa: BLE001
                logger.error(f"{fecha_str}: re-login falló -> {e}")
                continue

            try:
                if not ensure_session_alive(driver, logger):
                    raise RuntimeError("sesión inválida")
                select_date(driver, logger, fecha_str=fecha_str)
                sort_by_estado(driver, logger)
                rows = get_pacientes_del_dia(driver, logger)
            except Exception as e:  # noqa: BLE001
                logger.error(f"{fecha_str}: error -> {e}")
                continue

            # Calcular agregados
            counter_estados: Counter = Counter()
            counter_tipos_iniciado: Counter = Counter()
            counter_tipos_total: Counter = Counter()
            total_dia = 0
            for row in rows:
                try:
                    datos = extraer_datos_fila(row)
                except ValueError:
                    continue
                estado = datos.get("estado", "DESCONOCIDO")
                tipo = sanitizar_tipo(datos.get("tipo_atencion", ""))
                counter_estados[estado] += 1
                counter_tipos_total[tipo] += 1
                total_dia += 1
                if estado == "Iniciado":
                    counter_tipos_iniciado[tipo] += 1

            # Persistir agregados (UPSERT por fecha)
            conn.execute(
                """INSERT OR REPLACE INTO agregados_diarios
                   (fecha, total_citadas, iniciado, completado, pendiente,
                    agendado, no_se_presento, otros, tipos_iniciado_json, tipos_total_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fecha_str,
                    total_dia,
                    counter_estados.get("Iniciado", 0),
                    counter_estados.get("Completado", 0),
                    counter_estados.get("Pendiente", 0),
                    counter_estados.get("Agendado", 0),
                    counter_estados.get("No se Presentó", 0),
                    sum(
                        v for k, v in counter_estados.items()
                        if k not in {
                            "Iniciado", "Completado", "Pendiente",
                            "Agendado", "No se Presentó",
                        }
                    ),
                    json.dumps(dict(counter_tipos_iniciado), ensure_ascii=False),
                    json.dumps(dict(counter_tipos_total), ensure_ascii=False),
                ),
            )
            conn.commit()
            total_fichas_global += total_dia

            # Mostrar progreso cada 5 días o al final
            if idx % 5 == 0 or idx == len(dias):
                inci = counter_estados.get("Iniciado", 0)
                comp = counter_estados.get("Completado", 0)
                print(
                    f"  [{idx}/{len(dias)}] {fecha_str}: "
                    f"{total_dia} citadas "
                    f"(Inic:{inci} Comp:{comp} Pend:{counter_estados.get('Pendiente', 0)} "
                    f"Agend:{counter_estados.get('Agendado', 0)} "
                    f"NSP:{counter_estados.get('No se Presentó', 0)})"
                )

        # Registrar el run
        conn.execute(
            """INSERT INTO runs (fecha_run, fecha_inicio_recorrido,
               fecha_fin_recorrido, dias_recorridos, total_fichas)
               VALUES (?, ?, ?, ?, ?)""",
            (
                datetime.now().strftime(DATE_FORMAT),
                inicio.strftime(DATE_FORMAT),
                fin.strftime(DATE_FORMAT),
                len(dias),
                total_fichas_global,
            ),
        )
        conn.commit()

        # Reporte final — query SQL al estado real
        cur = conn.execute(
            """SELECT
                SUM(total_citadas), SUM(iniciado), SUM(completado),
                SUM(pendiente), SUM(agendado), SUM(no_se_presento), SUM(otros)
               FROM agregados_diarios
               WHERE fecha BETWEEN ? AND ?""",
            (
                inicio.strftime(DATE_FORMAT),
                fin.strftime(DATE_FORMAT),
            ),
        )
        row = cur.fetchone()
        tot_cit, tot_inci, tot_comp, tot_pend, tot_agend, tot_nsp, tot_otros = row

        # Top 10 días con más "Iniciado"
        cur = conn.execute(
            """SELECT fecha, iniciado, total_citadas FROM agregados_diarios
               WHERE fecha BETWEEN ? AND ?
               ORDER BY iniciado DESC, total_citadas DESC LIMIT 10""",
            (inicio.strftime(DATE_FORMAT), fin.strftime(DATE_FORMAT)),
        )
        top_dias = cur.fetchall()

        # Distribución anual por tipo (sumando tipos_iniciado_json)
        cur = conn.execute(
            """SELECT tipos_iniciado_json FROM agregados_diarios
               WHERE fecha BETWEEN ? AND ? AND iniciado > 0""",
            (inicio.strftime(DATE_FORMAT), fin.strftime(DATE_FORMAT)),
        )
        tipos_global: Counter = Counter()
        for (tipos_json_str,) in cur.fetchall():
            if tipos_json_str:
                try:
                    d = json.loads(tipos_json_str)
                    for t, c in d.items():
                        tipos_global[t] += c
                except (json.JSONDecodeError, TypeError):
                    pass

        print()
        print("=" * 60)
        print("REPORTE FINAL")
        print("=" * 60)
        print(f"Recorrido:           {inicio.strftime(DATE_FORMAT)} → "
              f"{fin.strftime(DATE_FORMAT)}")
        print(f"Días hábiles:        {len(dias)}")
        print()
        print("=== TOTAL ANUAL (todos los estados) ===")
        print(f"  Citas totales:     {tot_cit or 0}")
        print(f"  Iniciado:          {tot_inci or 0}  ({100*(tot_inci or 0)/(tot_cit or 1):.1f}%)")
        print(f"  Completado:        {tot_comp or 0}  ({100*(tot_comp or 0)/(tot_cit or 1):.1f}%)")
        print(f"  Pendiente:         {tot_pend or 0}  ({100*(tot_pend or 0)/(tot_cit or 1):.1f}%)")
        print(f"  Agendado:          {tot_agend or 0}  ({100*(tot_agend or 0)/(tot_cit or 1):.1f}%)")
        print(f"  No se Presentó:    {tot_nsp or 0}  ({100*(tot_nsp or 0)/(tot_cit or 1):.1f}%)")
        if tot_otros:
            print(f"  Otros:             {tot_otros or 0}")
        if tipos_global:
            print()
            print("=== 'INICIADO' ANUAL POR TIPO DE ATENCIÓN ===")
            for tipo, cant in tipos_global.most_common(10):
                pct = 100 * cant / (tot_inci or 1)
                print(f"  {tipo:<40s} {cant:4d}  ({pct:5.1f}%)")
        if top_dias:
            print()
            print("=== TOP 10 DÍAS CON MÁS 'INICIADO' ===")
            print(f"  {'Fecha':<12} {'Iniciado':>8} {'Total':>8}")
            for fecha, inci, tot in top_dias:
                print(f"  {fecha:<12} {inci:>8} {tot:>8}")
        print("=" * 60)
        return 0
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error fatal: {e}")
        return 1
    finally:
        try:
            input("\nPresione Enter para cerrar el browser...")
        except EOFError:
            pass
        _safe_quit(driver, logger)
        conn.close()


def main() -> int:
    logger = setup_logger()
    tee = _TeeStdout(sys.stdout)
    sys.stdout = tee
    rc = 0
    sufijo = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        rc = _run(logger)
    finally:
        sys.stdout = tee._original
        out_path = _guardar_output(tee.get_output(), sufijo)
        if out_path is not None:
            print(
                f"\n[output completo guardado en: "
                f"{out_path.relative_to(BASE_DIR)}]"
            )
    return rc


if __name__ == "__main__":
    sys.exit(main())
