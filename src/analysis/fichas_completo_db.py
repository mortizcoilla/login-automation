"""Llena una DB SQLite con TODAS las fichas del anio, todos los campos.

Recorre dia por dia y para cada dia trae TODAS las citas de la tabla
de Pacientes citados. Cada ficha es una fila en la tabla 'fichas' de
data/analysis/fichas_completo.db, con TODOS los campos de Rayen.

UPSERT por (fecha, hora, nombre) para que se pueda re-correr sin
duplicar. Soporta --historico para el anio completo.

Privacidad: la DB tiene PII (nombre) y vive en data/analysis/ que
esta en .gitignore. NO se commitea.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from datetime import date, datetime, timedelta
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
FECHA_INICIO_ABSOLUTA = date(2026, 1, 1)

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
    # Migracion: si la tabla existe sin alguna columna, agregarla
    cur = conn.execute("PRAGMA table_info(fichas)")
    cols_existentes = {row[1] for row in cur.fetchall()}
    for c in COLUMNAS:
        if c not in cols_existentes:
            conn.execute(f"ALTER TABLE fichas ADD COLUMN {c} TEXT")
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


def _ensure_session_alive(driver, credentials, logger):
    if not _es_url_login(driver.current_url):
        return driver
    logger.warning("Sesión expiró, re-logueando...")
    safe_quit(driver, logger)
    return login_rayen(credentials, logger, headless=False)


def main() -> int:
    logger = setup_logger()
    print("=" * 60)
    print("DB COMPLETA — TODAS las fichas, TODOS los campos, todo el anio")
    print("=" * 60)

    user_id = _resolver_usuario()
    if user_id is None:
        return 1

    conn = _init_db()
    # Conteos previos
    cur = conn.execute("SELECT COUNT(*) FROM fichas")
    prev_count = cur.fetchone()[0]
    print(f"DB: {DB_PATH.relative_to(BASE_DIR)}")
    print(f"Registros previos: {prev_count}")

    desde_arg, hasta_arg, historico = _parse_args()
    if historico:
        inicio = FECHA_INICIO_ABSOLUTA
    elif desde_arg:
        inicio = desde_arg
    else:
        cur = conn.execute("SELECT MIN(fecha) FROM fichas")
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
        print(f"ERROR: {inicio} > {fin}", file=sys.stderr)
        return 1

    dias = _dias_habiles(inicio, fin)
    print(
        f"Recorrido: {inicio.strftime(DATE_FORMAT)} → "
        f"{fin.strftime(DATE_FORMAT)} ({len(dias)} dias habiles)"
    )
    print()

    if not dias:
        print("No hay dias para recorrer.")
        conn.close()
        return 0

    try:
        credentials = load_credentials(user_id)
    except (KeyError, ValueError) as e:
        print(f"ERROR cargando credenciales: {e}", file=sys.stderr)
        return 1

    driver = None
    total_insertadas = 0
    total_actualizadas = 0
    errores_consecutivos = 0
    MAX_ERRORES_CONSECUTIVOS = 3

    try:
        driver = login_rayen(credentials, logger, headless=False)
        print("[OK] Login realizado. Recorriendo dia por dia...\n")

        for idx, dia in enumerate(dias, 1):
            fecha_str = dia.strftime(DATE_FORMAT)

            try:
                driver = _ensure_session_alive(driver, credentials, logger)
            except Exception as e:  # noqa: BLE001
                logger.error(f"{fecha_str}: re-login fallo -> {e}")
                errores_consecutivos += 1
                if errores_consecutivos >= MAX_ERRORES_CONSECUTIVOS:
                    print(
                        f"\n[ABORT] {MAX_ERRORES_CONSECUTIVOS} errores consecutivos. "
                        f"Abortando para no perder tiempo. Ultimo error: {e}"
                    )
                    break
                continue

            try:
                if not ensure_session_alive(driver, logger):
                    raise RuntimeError("sesion invalida")
                select_date(driver, logger, fecha_str=fecha_str)
                sort_by_estado(driver, logger)
                rows = get_pacientes_del_dia(driver, logger)
                errores_consecutivos = 0  # reset si el dia fue OK
            except Exception as e:  # noqa: BLE001
                logger.error(f"{fecha_str}: error -> {e}")
                errores_consecutivos += 1
                if errores_consecutivos >= MAX_ERRORES_CONSECUTIVOS:
                    print(
                        f"\n[ABORT] {MAX_ERRORES_CONSECUTIVOS} errores consecutivos. "
                        f"Abortando. Ultimo error: {e}"
                    )
                    break
                continue

            n_dia_nuevas = 0
            n_dia_act = 0
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
                # UPSERT manual: SELECT primero
                cur = conn.execute(
                    "SELECT 1 FROM fichas WHERE fecha=? AND hora=? AND nombre=?",
                    (ficha["fecha"], ficha["hora"], ficha["nombre"]),
                )
                if cur.fetchone() is None:
                    placeholders = ", ".join(["?"] * len(COLUMNAS))
                    cols = ", ".join(COLUMNAS)
                    conn.execute(
                        f"INSERT INTO fichas ({cols}) VALUES ({placeholders})",
                        [ficha[c] for c in COLUMNAS],
                    )
                    n_dia_nuevas += 1
                else:
                    sets = ", ".join(f"{c}=?" for c in COLUMNAS if c not in ("fecha", "hora", "nombre"))
                    conn.execute(
                        f"UPDATE fichas SET {sets} WHERE fecha=? AND hora=? AND nombre=?",
                        [ficha[c] for c in COLUMNAS if c not in ("fecha", "hora", "nombre")]
                        + [ficha["fecha"], ficha["hora"], ficha["nombre"]],
                    )
                    n_dia_act += 1

            total_insertadas += n_dia_nuevas
            total_actualizadas += n_dia_act
            conn.commit()

            if idx % 5 == 0 or idx == len(dias):
                print(
                    f"  [{idx}/{len(dias)}] {fecha_str}: "
                    f"{len(rows)} fichas (nuevas:{n_dia_nuevas} "
                    f"actualizadas:{n_dia_act})"
                )

        # Reporte final
        cur = conn.execute("SELECT COUNT(*) FROM fichas")
        total_db = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(DISTINCT fecha) FROM fichas")
        dias_cubiertos = cur.fetchone()[0]

        print()
        print("=" * 60)
        print("REPORTE FINAL")
        print("=" * 60)
        print(f"Recorrido:           {inicio.strftime(DATE_FORMAT)} → "
              f"{fin.strftime(DATE_FORMAT)}")
        print(f"Dias habiles:        {len(dias)}")
        print(f"Dias cubiertos:      {dias_cubiertos}")
        print(f"Fichas nuevas:       {total_insertadas}")
        print(f"Fichas actualizadas: {total_actualizadas}")
        print(f"Total en DB:         {total_db}")
        print()
        print("Columnas de la tabla 'fichas':")
        for c in COLUMNAS:
            print(f"  - {c}")
        print()
        print("Estados en la DB:")
        for estado, cant in conn.execute(
            "SELECT estado, COUNT(*) FROM fichas GROUP BY estado ORDER BY 2 DESC"
        ).fetchall():
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
