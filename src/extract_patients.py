from __future__ import annotations

import csv
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Any

from selenium.webdriver.remote.webdriver import WebDriver

from src.api_client import (
    build_session_from_driver,
    fetch_pacientes_for_date,
    load_api_config,
)
from src.constants import DATE_FORMAT
from src.credentials import load_credentials
from src.logger_config import setup_logger

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw_responses")
CSV_PATH = os.path.join(DATA_DIR, "pacientes_2026.csv")
CHECKPOINT_PATH = os.path.join(DATA_DIR, ".checkpoint.json")
FIELDNAMES = [
    "fecha",
    "hora_cita",
    "hora_llegada",
    "estado",
    "nombre_paciente",
    "rut",
    "numero_ficha",
    "genero",
    "sector",
    "prevision",
    "tipo_cupo",
    "razon",
    "tipo_atencion",
    "instrumento",
    "observacion",
    "citado_por",
    "nodo",
    "es_teleconsulta",
]


def working_days(start: datetime, end: datetime) -> list[datetime]:
    current = start
    days: list[datetime] = []
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def load_checkpoint() -> set[str]:
    if not os.path.exists(CHECKPOINT_PATH):
        return set()
    try:
        with open(CHECKPOINT_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("processed", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_checkpoint(processed: set[str]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = CHECKPOINT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"processed": sorted(processed)}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CHECKPOINT_PATH)


def extract_flat_record(item: dict[str, Any], date_str: str) -> dict[str, Any]:
    obs = (item.get("Observacion") or "").strip()

    cupos = item.get("Cupos") or []
    citado_por_nombre = ""
    if cupos:
        desc = cupos[0].get("Descripcion", "")
        m = re.search(r"Citado por:\s*(.+)", desc)
        if m:
            citado_por_nombre = m.group(1).strip()

    estado = item.get("EstadoCita") or {}
    tipo_atencion = item.get("TipoDeAtencion") or {}
    instrumento = item.get("Instrumento") or {}
    usuario = item.get("UsuarioAps") or {}
    genero = usuario.get("Genero") or {}
    prevision = usuario.get("InstitucionPrevisional") or {}
    sector = usuario.get("Sector") or {}

    return {
        "fecha": date_str,
        "hora_cita": item.get("FechaHora", ""),
        "hora_llegada": item.get("HoraDeLlegada", ""),
        "estado": estado.get("Nombre", ""),
        "nombre_paciente": item.get("NombreUsuarioAps", ""),
        "rut": usuario.get("Rut", ""),
        "numero_ficha": usuario.get("NumeroDeFicha", ""),
        "genero": genero.get("Nombre", ""),
        "sector": sector.get("Nombre", ""),
        "prevision": prevision.get("Nombre", ""),
        "tipo_cupo": item.get("TipoDeCupo", ""),
        "razon": item.get("Razon", ""),
        "tipo_atencion": tipo_atencion.get("Nombre", ""),
        "instrumento": instrumento.get("Codigo", ""),
        "observacion": obs,
        "citado_por": citado_por_nombre,
        "nodo": item.get("Nodo", ""),
        "es_teleconsulta": str(item.get("EsTeleconsulta", False)),
    }


def load_existing_ids() -> set[tuple[str, int]]:
    if not os.path.exists(CSV_PATH):
        return set()
    seen: set[tuple[str, int]] = set()
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fecha = row.get("fecha", "")
            try:
                hora = int(
                    (row.get("hora_cita") or "").split(" ")[-1].split("-")[0].replace(":", "")
                )
            except (ValueError, IndexError):
                hora = 0
            seen.add((fecha, hora))
    return seen


def write_csv(records: list[dict[str, Any]], path: str = CSV_PATH) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def run_extraction(
    driver: WebDriver,
    logger: logging.Logger,
    resume: bool = True,
) -> dict[str, int]:
    config = load_api_config()
    logger.info(f"API: {config['method']} {config['url'][:80]}...")

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)

    session = build_session_from_driver(driver)
    processed = load_checkpoint() if resume else set()
    logger.info(f"Checkpoint: {len(processed)} dias ya procesados")

    start = datetime(2026, 1, 1)
    end = min(
        datetime.now().replace(hour=0, minute=0, second=0, microsecond=0), datetime(2026, 12, 31)
    )
    days = working_days(start, end)
    todo = [d for d in days if d.strftime(DATE_FORMAT) not in processed]
    logger.info(f"Dias habiles {start.date()}..{end.date()}: {len(days)} | Pendientes: {len(todo)}")

    all_records: list[dict[str, Any]] = []
    stats = {"dias": 0, "con_datos": 0, "vacias": 0, "errores": 0, "registros": 0}

    for idx, day in enumerate(todo, 1):
        date_str = day.strftime(DATE_FORMAT)
        stats["dias"] += 1

        try:
            data = fetch_pacientes_for_date(session, config["url"], date_str)
        except Exception as e:
            stats["errores"] += 1
            logger.warning(f"{date_str}: error -> {e}")
            continue

        raw_path = os.path.join(RAW_DIR, f"{date_str}.json")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        if not data:
            stats["vacias"] += 1
        else:
            stats["con_datos"] += 1
            for item in data:
                all_records.append(extract_flat_record(item, date_str))
            stats["registros"] += len(data)

        processed.add(date_str)
        save_checkpoint(processed)

        if idx % 25 == 0 or idx == len(todo):
            logger.info(
                f"Progreso {idx}/{len(todo)}: {date_str} "
                f"(reg:{stats['registros']} err:{stats['errores']} vacias:{stats['vacias']})"
            )

    if all_records:
        existing_csv = os.path.exists(CSV_PATH)
        with open(CSV_PATH, "a" if existing_csv else "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
            if not existing_csv:
                writer.writeheader()
            writer.writerows(all_records)
        logger.info(f"CSV actualizado con {len(all_records)} registros nuevos")
    else:
        logger.info("Sin registros nuevos para agregar al CSV")

    return stats


def main() -> int:
    logger = setup_logger()
    logger.info("=" * 60)
    logger.info("Extraccion masiva de pacientes")
    logger.info("=" * 60)

    from src.browser_automation import ensure_session_alive, run_login, safe_quit
    from src.credentials import prompt_user_id

    user_id = prompt_user_id()

    credentials = load_credentials(user_id)
    driver: WebDriver | None = None
    try:
        driver = run_login(credentials, logger, headless=False)
        if not ensure_session_alive(driver, logger):
            logger.error("Sesion invalida tras login. Abortando.")
            return 1
        stats = run_extraction(driver, logger, resume=True)
        logger.info("=" * 60)
        logger.info("EXTRACCION COMPLETADA")
        logger.info(f"  Dias procesados:    {stats['dias']}")
        logger.info(f"  Dias con datos:     {stats['con_datos']}")
        logger.info(f"  Dias vacios:        {stats['vacias']}")
        logger.info(f"  Errores:            {stats['errores']}")
        logger.info(f"  Registros nuevos:   {stats['registros']}")
        logger.info(f"  CSV: {CSV_PATH}")
        logger.info("=" * 60)
        return 0
    except KeyboardInterrupt:
        logger.info("Extraccion interrumpida por el usuario. Checkpoint guardado.")
        return 130
    except Exception as e:
        logger.error(f"Error critico: {e}")
        return 1
    finally:
        safe_quit(driver, logger)


if __name__ == "__main__":
    sys.exit(main())
