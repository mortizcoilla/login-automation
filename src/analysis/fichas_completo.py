"""Exporta TODAS las fichas con TODOS los campos a un CSV maestro.

Recorre dia por dia (con --historico para el anio completo) y para
cada dia trae TODAS las citas de Pacientes citados (todos los
estados). Cada ficha es una fila del CSV con TODOS los campos.

Output:
- data/analysis/fichas_completo_<anio>.csv — CSV maestro, una fila
  por ficha, todos los campos
- data/analysis/fichas_completo_run_<timestamp>.txt — output completo

El CSV se regenera en cada run (sobrescribe). Clave unica para
dedup: (fecha, hora, nombre) — si Yadira no reagenda/modifica
(como confirmaste), esta clave es estable.

Privacidad: el CSV tiene PII (nombre) y vive en data/analysis/ que
esta en .gitignore. NO se commitea.
"""
from __future__ import annotations

import csv
import io
import logging
import sys
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
OUT_DIR = BASE_DIR / "data" / "analysis"
FECHA_INICIO_ABSOLUTA = date(2026, 1, 1)

# Todos los campos que vamos a exportar
COLUMNAS = [
    "fecha",
    "hora",
    "estado",
    "nombre",
    "tipo_cupo",
    "llegada",
    "llamada",
    "razon",
    "tipo_atencion",
    "adjunto",
]


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


def _run(logger: logging.Logger) -> int:
    print("=" * 60)
    print("EXPORTAR TODAS LAS FICHAS A CSV (todos los campos)")
    print("=" * 60)

    user_id = _resolver_usuario()
    if user_id is None:
        return 1

    desde_arg, hasta_arg, historico = _parse_args()
    if historico:
        inicio = FECHA_INICIO_ABSOLUTA
    elif desde_arg:
        inicio = desde_arg
    else:
        # Auto-deteccion: por defecto, primer dia del anio
        inicio = FECHA_INICIO_ABSOLUTA
    fin = hasta_arg or date.today()

    if inicio > fin:
        print(f"ERROR: {inicio} es posterior a {fin}", file=sys.stderr)
        return 1

    dias = _dias_habiles(inicio, fin)
    print(
        f"Recorrido: {inicio.strftime(DATE_FORMAT)} → "
        f"{fin.strftime(DATE_FORMAT)} ({len(dias)} días hábiles)"
    )

    if not dias:
        print("No hay días para recorrer.")
        return 0

    try:
        credentials = load_credentials(user_id)
    except (KeyError, ValueError) as e:
        print(f"ERROR cargando credenciales: {e}", file=sys.stderr)
        return 1

    # CSV maestro del anio en curso
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / f"fichas_completo_{fin.year}.csv"

    # Cargar CSV existente si lo hay (para dedup)
    seen: set[tuple[str, str, str]] = set()
    if csv_path.exists():
        try:
            with open(csv_path, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    seen.add((row.get("fecha", ""), row.get("hora", ""), row.get("nombre", "")))
            print(f"CSV existente: {len(seen)} fichas ya registradas")
        except OSError as e:
            print(f"WARN: no se pudo leer CSV existente: {e}", file=sys.stderr)

    driver = None
    fichas_nuevas: list[dict[str, str]] = []
    total_procesadas = 0

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

            n_dia = 0
            for row in rows:
                try:
                    datos = extraer_datos_fila(row)
                except ValueError:
                    continue
                ficha = {
                    "fecha": fecha_str,
                    "hora": datos.get("hora", ""),
                    "estado": datos.get("estado", ""),
                    "nombre": datos.get("nombre", ""),
                    "tipo_cupo": datos.get("tipo_cupo", ""),
                    "llegada": datos.get("llegada", ""),
                    "llamada": datos.get("llamada", ""),
                    "razon": datos.get("razon", ""),
                    "tipo_atencion": sanitizar_tipo(datos.get("tipo_atencion", "")),
                    "adjunto": datos.get("adjunto", ""),
                }
                key = (ficha["fecha"], ficha["hora"], ficha["nombre"])
                if key not in seen:
                    seen.add(key)
                    fichas_nuevas.append(ficha)
                    n_dia += 1

            total_procesadas += len(rows)
            if idx % 5 == 0 or idx == len(dias):
                print(
                    f"  [{idx}/{len(dias)}] {fecha_str}: "
                    f"{len(rows)} fichas vistas, {n_dia} nuevas"
                )

        # Escribir CSV maestro (sobrescribe, incluyendo las viejas + nuevas)
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNAS, extrasaction="ignore")
            writer.writeheader()
            # Re-leer todas las fichas del CSV viejo (si existe) + las nuevas
            # PERO como ya tenemos `seen` con todo, podemos escribir las nuevas
            # y las viejas se mantienen. Estrategia: append al CSV existente.
            if csv_path.exists():
                # Reescribir desde cero: leer viejo + append nuevas
                with open(csv_path, encoding="utf-8-sig", newline="") as rf:
                    reader = csv.DictReader(rf)
                    for row in reader:
                        # Filtrar las que no estén en seen (defensivo)
                        key = (row.get("fecha", ""), row.get("hora", ""), row.get("nombre", ""))
                        if key in seen:
                            writer.writerow(row)
            # Agregar las nuevas
            for f_nueva in fichas_nuevas:
                writer.writerow(f_nueva)

        print()
        print("=" * 60)
        print("EXPORT COMPLETO")
        print("=" * 60)
        print(f"Recorrido:           {inicio.strftime(DATE_FORMAT)} → "
              f"{fin.strftime(DATE_FORMAT)}")
        print(f"Días hábiles:        {len(dias)}")
        print(f"Fichas vistas:       {total_procesadas}")
        print(f"Fichas nuevas:       {len(fichas_nuevas)}")
        print(f"Total en CSV:        {len(seen)}")
        print(f"CSV maestro:         {csv_path.relative_to(BASE_DIR)}")
        print()
        print("Columnas del CSV (todos los campos):")
        for c in COLUMNAS:
            print(f"  - {c}")
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
        try:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out_path = OUT_DIR / f"fichas_completo_run_{sufijo}.txt"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(tee.get_output())
            print(
                f"\n[output completo guardado en: "
                f"{out_path.relative_to(BASE_DIR)}]"
            )
        except OSError as e:  # noqa: BLE001
            print(f"WARN: no se pudo guardar output: {e}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
