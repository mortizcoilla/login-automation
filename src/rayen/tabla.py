"""La tabla de 'Pacientes citados': filas, datos y match de paciente.

Split de src/browser_automation.py + logica de match de
crear_notas_clinicas (refactorizacion 2026-09-18, Fase 3a).

REQ-019: match exacto -> parcial unico -> ambiguo NO matchea.
REQ-031: doble-click tolerante a stale element (re-find por nombre).
"""

from __future__ import annotations

import logging
import time

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import (
    expected_conditions as EC,  # noqa: N812 (alias estandar de Selenium)
)

from src.constants import CAMPOS_POR_FILA, ESTADO_INICIADO
from src.rayen.navegador import _SELECTORS, _make_wait, _select


def get_pacientes_iniciados(driver: WebDriver, logger: logging.Logger) -> list[WebElement]:
    wait = _make_wait(driver)
    by, val = _select("table.iniciado_cell")
    cells = wait.until(EC.presence_of_all_elements_located((by, val)))
    row_xpath = _SELECTORS["table"]["row_group"]["value"]
    rows: list[WebElement] = []
    for cell in cells:
        try:
            row = cell.find_element(By.XPATH, row_xpath)
            rows.append(row)
        except StaleElementReferenceException:
            continue
    logger.info(f"Pacientes con estado '{ESTADO_INICIADO}': {len(rows)}")
    return rows


def get_pacientes_del_dia(driver: WebDriver, logger: logging.Logger) -> list[WebElement]:
    """Devuelve TODAS las filas de la tabla de Pacientes citados, sin filtrar
    por estado. Complemento de get_pacientes_iniciados (que solo trae
    las 'Iniciado').

    Usa el selector 'div.rt-tr-group' (clase de react-table) para
    agarrar cada fila de la tabla.
    """
    wait = _make_wait(driver, 15)
    rows = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.rt-tr-group")))
    logger.info(f"Pacientes del día (todos los estados): {len(rows)}")
    return rows


def extraer_datos_fila(row: WebElement) -> dict[str, str]:
    by, val = _select("table.cell")
    celdas = row.find_elements(by, val)
    if len(celdas) < CAMPOS_POR_FILA:
        raise ValueError(
            f"Fila con {len(celdas)} celdas (esperaba >= {CAMPOS_POR_FILA}). "
            "La estructura de la tabla puede haber cambiado."
        )
    return {
        "hora": celdas[0].text,
        "estado": celdas[1].text,
        "nombre": celdas[2].text,
        "tipo_cupo": celdas[3].text,
        "llegada": celdas[4].text,
        "llamada": celdas[5].text,
        "razon": celdas[6].text,
        "tipo_atencion": celdas[7].text,
        "adjunto": celdas[8].text,
    }


# ---------------------------------------------------------------------------
# Match de paciente contra la tabla del dia
# ---------------------------------------------------------------------------


def _buscar_paciente_en_tabla(
    driver: WebDriver,
    logger: logging.Logger,
    nombre_objetivo: str,
) -> tuple[WebElement, str | None] | None:
    """Busca la fila del paciente por nombre en la tabla del dia.

    Devuelve una tupla (WebElement de la fila, nombre_real_rayen) si
    la encuentra, None si no.

    Si hubo match exacto, nombre_real_rayen es None (porque coincide
    con el nombre del informe). Si hubo match parcial, nombre_real_rayen
    tiene el nombre completo de Rayen (para guardarlo como metadato).

    Estrategia de match (REQ-019, en orden):
    1) Exacto: el nombre de Rayen es identico al del informe.
    2) Parcial unico: el nombre del informe esta contenido en el de
       Rayen (caso de informe truncado) o viceversa. Si hay UN solo
       candidato, matchea.
    3) Si hay multiples candidatos parciales, NO matchea para evitar
       falsos positivos.
    """
    rows = get_pacientes_del_dia(driver, logger)
    nombre_norm = nombre_objetivo.strip().lower()

    # 1) Match exacto.
    for row in rows:
        try:
            datos = extraer_datos_fila(row)
        except (ValueError, StaleElementReferenceException):
            # StaleElement: la fila se re-renderizo mientras iterabamos.
            # Saltamos y seguimos con las siguientes.
            continue
        if datos.get("nombre", "").strip().lower() == nombre_norm:
            return (row, None)

    # 2) Match parcial.
    candidatos: list[tuple[WebElement, str]] = []
    for row in rows:
        try:
            datos = extraer_datos_fila(row)
        except (ValueError, StaleElementReferenceException):
            continue
        nombre_row = datos.get("nombre", "").strip()
        if not nombre_row:
            continue
        if nombre_norm in nombre_row.lower() or nombre_row.lower() in nombre_norm:
            candidatos.append((row, nombre_row))

    if len(candidatos) == 1:
        logger.info(f"[crear_notas] Match parcial: '{nombre_objetivo}' ~ '{candidatos[0][1]}'")
        return (candidatos[0][0], candidatos[0][1])
    if len(candidatos) > 1:
        nombres = [c[1] for c in candidatos]
        logger.warning(
            f"[crear_notas] Match parcial ambiguo para '{nombre_objetivo}': "
            f"{nombres}. No se hace match."
        )
        return None

    return None


def _doble_click_en_paciente(
    driver: WebDriver,
    logger: logging.Logger,
    row: WebElement,
    nombre_objetivo: str | None = None,
) -> None:
    """Hace doble click en la fila del paciente para abrir la ficha.

    REQ-031: si la fila quedo stale (Rayen re-renderizo la tabla mientras
    esperabamos), re-busca por nombre y re-intenta una vez. Bug que
    afectaba ECICEP-g3 porque el panel tarda 15-30s en cargar y durante esa
    espera la fila original quedaba stale.
    """
    try:
        ActionChains(driver).double_click(row).perform()
        logger.info("[crear_notas] Doble click sobre la fila del paciente")
        return
    except StaleElementReferenceException:
        if not nombre_objetivo:
            # Sin nombre no podemos re-find. Propagamos el error original.
            logger.warning("[crear_notas] Fila stale pero no se paso nombre para re-find")
            raise
    except Exception as e:
        logger.warning(f"[crear_notas] No se pudo doble-click en fila: {e}")
        raise

    # Stale + tenemos nombre: re-buscar y re-intentar una sola vez.
    logger.warning(
        "[crear_notas] Fila stale tras esperar panel (15-30s). Re-buscando por nombre..."
    )
    time.sleep(1)
    resultado = _buscar_paciente_en_tabla(driver, logger, nombre_objetivo)
    if resultado is None:
        raise RuntimeError(f"No se encontro '{nombre_objetivo}' tras stale element")
    row_fresh, _ = resultado
    ActionChains(driver).double_click(row_fresh).perform()
    logger.info("[crear_notas] Doble click (re-find) OK")
