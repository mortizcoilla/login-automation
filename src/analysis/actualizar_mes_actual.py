"""Actualiza el mes en curso. Pensado para correr todos los días.

Hace un recorrido completo del mes actual (ej. julio 2026), borra
los registros existentes de ese mes y los reinserta con datos
frescos. Asi, cada dia que corre el script, el mes queda al dia.

Uso:
    python -m src.analysis.actualizar_mes_actual

Tiempo: ~2-3 minutos (un mes de dias habiles = 20-22 dias).

Privacidad: la DB tiene PII (nombre) y vive en data/analysis/ que
esta en .gitignore. NO se commitea.
"""
from __future__ import annotations

import calendar
import logging
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from src.browser_automation import (
    _es_url_login,
    ensure_session_alive,
    extraer_datos_fila,
    get_pacientes_del_dia,
    safe_quit,
    select_date,
    sort_by_estado,
)
from src.constants import DATE_FORMAT
from src.credentials import list_known_users, load_credentials
from src.logger_config import setup_logger
from src.pancho_skills import login_rayen
from src.plantillas import sanitizar_tipo

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "analysis" / "fichas_completo.db"

COLUMNAS = [
    "fecha", "hora", "estado", "nombre", "tipo_cupo",
    "llegada", "llamada", "razon", "tipo_atencion", "adjunto",
]


def _init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cols_sql = ", ".join(f"{c} TEXT" for c in COLUMNAS)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS fichas (
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            nombre TEXT NOT NULL,
            {cols_sql.replace('fecha TEXT,', '').replace('hora TEXT,', '').replace('nombre TEXT,', '')},
            PRIMARY KEY (fecha, hora, nombre)
        )
        """
    )
    cur = conn.execute("PRAGMA table_info(fichas)")
    cols_existentes = {row[1] for row in cur.fetchall()}
    for c in COLUMNAS:
        if c not in cols_existentes:
            conn.execute(f"ALTER TABLE fichas ADD COLUMN {c} TEXT")
    conn.commit()
    return conn


def _dias_habiles_del_mes(year: int, month: int) -> list[date]:
    """Devuelve los días hábiles del mes (lun-vie) hasta hoy inclusive."""
    _, last_day = calendar.monthrange(year, month)
    fin_mes = date(year, month, last_day)
    hoy = date.today()
    fin = min(fin_mes, hoy)
    dias: list[date] = []
    current = date(year, month, 1)
    while current <= fin:
        if current.weekday() < 5:
            dias.append(current)
        current = date.fromordinal(current.toordinal() + 1)
    return dias


def _resolver_usuario() -> str | None:
    cli_user = None
    for arg in sys.argv[1:]:
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


def main() -> int:
    logger = setup_logger()
    print("=" * 60)
    print("ACTUALIZAR MES EN CURSO (uso diario)")
    print("=" * 60)

    user_id = _resolver_usuario()
    if user_id is None:
        return 1

    conn = _init_db()
    hoy = date.today()
    dias = _dias_habiles_del_mes(hoy.year, hoy.month)
    print(f"Mes actual: {hoy.strftime('%m-%Y')}")
    print(f"DB: {DB_PATH.relative_to(BASE_DIR)}")
    print(f"Recorrido: {dias[0].strftime(DATE_FORMAT)} → {dias[-1].strftime(DATE_FORMAT)} "
          f"({len(dias)} dias habiles)")
    print()

    if not dias:
        print("No hay dias habiles este mes todavia.")
        conn.close()
        return 0

    # Borrar todo el mes en curso (formato dd-mm-yyyy, asi que usamos LIKE)
    # El mes en formato dd-mm-yyyy: el mes es el segundo grupo, ej "07-2026"
    mes_prefix = f"%-{hoy.strftime('%m-%Y')}"
    cur = conn.execute("SELECT COUNT(*) FROM fichas WHERE fecha LIKE ?", (mes_prefix,))
    pre_count = cur.fetchone()[0]
    conn.execute("DELETE FROM fichas WHERE fecha LIKE ?", (mes_prefix,))
    conn.commit()
    print(f"Borrados {pre_count} registros del mes {hoy.strftime('%m-%Y')} (seran regenerados).")
    print()

    try:
        credentials = load_credentials(user_id)
    except (KeyError, ValueError) as e:
        print(f"ERROR cargando credenciales: {e}", file=sys.stderr)
        return 1

    driver = None
    total_insertadas = 0
    errores_consecutivos = 0
    MAX_ERRORES = 3

    try:
        driver = login_rayen(credentials, logger, headless=False)
        print("[OK] Login realizado. Recorriendo el mes...\n")

        for idx, dia in enumerate(dias, 1):
            fecha_str = dia.strftime(DATE_FORMAT)

            try:
                if not _es_url_login(driver.current_url):
                    pass
                else:
                    raise RuntimeError("sesion expirada")
            except Exception:
                driver = login_rayen(credentials, logger, headless=False)

            try:
                select_date(driver, logger, fecha_str=fecha_str)
                sort_by_estado(driver, logger)
                rows = get_pacientes_del_dia(driver, logger)
                errores_consecutivos = 0
            except Exception as e:  # noqa: BLE001
                logger.error(f"{fecha_str}: error -> {e}")
                errores_consecutivos += 1
                if errores_consecutivos >= MAX_ERRORES:
                    print(
                        f"\n[ABORT] {MAX_ERRORES} errores consecutivos. "
                        f"Abortando. Ultimo error: {e}"
                    )
                    break
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
                placeholders = ", ".join(["?"] * len(COLUMNAS))
                cols = ", ".join(COLUMNAS)
                conn.execute(
                    f"INSERT OR REPLACE INTO fichas ({cols}) VALUES ({placeholders})",
                    [ficha[c] for c in COLUMNAS],
                )
                n_dia += 1

            total_insertadas += n_dia
            conn.commit()

            if idx % 5 == 0 or idx == len(dias):
                print(f"  [{idx}/{len(dias)}] {fecha_str}: {n_dia} fichas")

        # Reporte final
        cur = conn.execute(
            "SELECT COUNT(*) FROM fichas WHERE fecha LIKE ?",
            (mes_prefix,),
        )
        total_mes = cur.fetchone()[0]
        cur = conn.execute(
            "SELECT estado, COUNT(*) FROM fichas WHERE fecha LIKE ? GROUP BY estado ORDER BY 2 DESC",
            (mes_prefix,),
        )
        estados_mes = cur.fetchall()

        print()
        print("=" * 60)
        print(f"REPORTE FINAL — Mes {hoy.strftime('%m-%Y')}")
        print("=" * 60)
        print(f"Dias habiles:        {len(dias)}")
        print(f"Fichas del mes:      {total_mes}")
        print(f"Estados:")
        for estado, cant in estados_mes:
            print(f"  {estado:<25s} {cant}")
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
        safe_quit(driver, logger)
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
