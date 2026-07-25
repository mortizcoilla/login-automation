"""Rescata el anio 2025. Para comparacion interanual y estudios de
estacionalidad.

Recorre todos los dias habiles del 2025 (01-01-2025 → 31-12-2025)
y trae TODAS las citas de la tabla de Pacientes citados. Las
inserta en data/analysis/fichas_completo.db (la misma DB que el
script fichas_completo_db.py, con UPSERT por (fecha, hora, nombre)
para no duplicar).

Uso:
    python -m src.analysis.rescatar_anio_2025

Tiempo: ~20-40 minutos (252 dias habiles del 2025).

Resultado: en la DB, los registros con fecha 01-01-2025 a 31-12-2025
estan. Para comparar con 2026, las queries usan WHERE fecha LIKE
'%-2025' vs WHERE fecha LIKE '%-2026'.

Privacidad: la DB tiene PII (nombre) y vive en data/analysis/ que
esta en .gitignore. NO se commitea.
"""
from __future__ import annotations

import calendar
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
ANIO_OBJETIVO = 2025

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


def _dias_habiles(inicio: date, fin: date) -> list[date]:
    dias: list[date] = []
    current = inicio
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
    print(f"RESCATAR ANIO {ANIO_OBJETIVO} (todos los dias habiles)")
    print("=" * 60)

    user_id = _resolver_usuario()
    if user_id is None:
        return 1

    conn = _init_db()
    inicio = date(ANIO_OBJETIVO, 1, 1)
    fin = date(ANIO_OBJETIVO, 12, 31)
    dias = _dias_habiles(inicio, fin)
    print(f"DB: {DB_PATH.relative_to(BASE_DIR)}")
    print(f"Recorrido: {inicio.strftime(DATE_FORMAT)} → {fin.strftime(DATE_FORMAT)} "
          f"({len(dias)} dias habiles)")
    print()

    # Conteo de registros previos del 2025
    pre_count = conn.execute(
        "SELECT COUNT(*) FROM fichas WHERE fecha LIKE ?",
        (f"%-{ANIO_OBJETIVO}",),
    ).fetchone()[0]
    print(f"Registros previos del {ANIO_OBJETIVO}: {pre_count} (se actualizaran con UPSERT)")
    print()

    try:
        credentials = load_credentials(user_id)
    except (KeyError, ValueError) as e:
        print(f"ERROR cargando credenciales: {e}", file=sys.stderr)
        return 1

    driver = None
    total_insertadas = 0
    total_actualizadas = 0
    errores_consecutivos = 0
    MAX_ERRORES = 3

    try:
        driver = login_rayen(credentials, logger, headless=False)
        print("[OK] Login realizado. Recorriendo el anio...\n")

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
                # INSERT OR REPLACE: si ya existe (por PK), actualiza
                conn.execute(
                    f"INSERT OR REPLACE INTO fichas ({cols}) VALUES ({placeholders})",
                    [ficha[c] for c in COLUMNAS],
                )
                n_dia += 1

            total_insertadas += n_dia
            conn.commit()

            if idx % 10 == 0 or idx == len(dias):
                print(f"  [{idx}/{len(dias)}] {fecha_str}: {n_dia} fichas")

        # Reporte final
        total_2025 = conn.execute(
            "SELECT COUNT(*) FROM fichas WHERE fecha LIKE ?",
            (f"%-{ANIO_OBJETIVO}",),
        ).fetchone()[0]
        estados_2025 = conn.execute(
            "SELECT estado, COUNT(*) FROM fichas WHERE fecha LIKE ? GROUP BY estado ORDER BY 2 DESC",
            (f"%-{ANIO_OBJETIVO}",),
        ).fetchall()

        print()
        print("=" * 60)
        print(f"REPORTE FINAL — Anio {ANIO_OBJETIVO}")
        print("=" * 60)
        print(f"Dias habiles:        {len(dias)}")
        print(f"Fichas del {ANIO_OBJETIVO}:       {total_2025}")
        print(f"Estados:")
        for estado, cant in estados_2025:
            print(f"  {estado:<25s} {cant}")
        print()
        print("Para comparar con 2026 (queries en DB Browser):")
        print(f"  WHERE fecha LIKE '%-2025'  -- anio {ANIO_OBJETIVO}")
        print(f"  WHERE fecha LIKE '%-2026'  -- anio 2026")
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
