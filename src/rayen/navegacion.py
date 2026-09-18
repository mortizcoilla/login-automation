"""Navegacion entre paginas de Rayen: fecha, orden y vuelta a la lista.

Split de src/browser_automation.py + volver_a_pacientes_citados de
crear_notas_clinicas (refactorizacion 2026-09-18, Fase 3a).
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import (
    expected_conditions as EC,  # noqa: N812 (alias estandar de Selenium)
)

from src.constants import DATE_FORMAT
from src.rayen.navegador import (
    _SELECTORS,
    NAVIGATION_TIMEOUT,
    _capture_error,
    _cerrar_alertas,
    _make_wait,
    _select,
    _wait_loading_modal_gone,
)


def select_date(driver: WebDriver, logger: logging.Logger, fecha_str: str | None = None) -> str:
    if fecha_str is None:
        fecha_str = input("Ingrese fecha (dd-mm-yyyy): ").strip()
    if not re.match(r"^\d{2}-\d{2}-\d{4}$", fecha_str):
        raise ValueError(
            f"Formato invalido. Use dd-mm-yyyy (ej: 29-05-2026). Recibido: {fecha_str!r}"
        )
    datetime.strptime(fecha_str, DATE_FORMAT)
    by, val = _select("table.date_input")
    _ = by
    css = val
    # Antes de buscar el input, esperar a que el modal "Cargando" de
    # Rayen desaparezca. Sin esto, el input no existe en el DOM durante
    # la carga y el wait falla aunque la página SÍ esté cargando.
    _wait_loading_modal_gone(driver, logger, timeout=30)
    logger.info(f"Esperando input de fecha ({css})...")
    try:
        _make_wait(driver, 60).until(  # antes era NAVIGATION_TIMEOUT (20s)
            EC.presence_of_element_located((by, val))
        )
    except TimeoutException as e:
        _capture_error(driver, logger, "date_input_missing")
        raise TimeoutException(
            f"No aparecio {css} en {NAVIGATION_TIMEOUT}s. "
            f"URL actual: {driver.current_url}. "
            f"Revise que la pagina 'Pacientes citados' haya cargado."
        ) from e
    driver.execute_script(
        f"""
        var input = document.querySelector({json.dumps(css)});
        if (!input) throw new Error('No se encontro {css}');
        var nativeSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        nativeSetter.call(input, arguments[0]);
        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
        """,
        fecha_str,
    )
    logger.info(f"Fecha {fecha_str} ingresada")
    return fecha_str


def sort_by_estado(driver: WebDriver, logger: logging.Logger) -> None:
    wait = _make_wait(driver)
    _cerrar_alertas(driver, logger)
    by, val = _select("table.estado_header")
    estado_header = wait.until(EC.presence_of_element_located((by, val)))
    from src.rayen.navegador import _safe_js_click

    _safe_js_click(driver, estado_header)
    # Después del click, la tabla se reordena. Esperamos a que el primer
    # cambio de estado aparezca. Si el día no tiene fichas o no tiene
    # 'Iniciado', el wait falla con TimeoutException — lo capturamos
    # y seguimos (la tabla ya está ordenada, solo no hay datos para
    # esperar).
    try:
        wait.until(
            EC.presence_of_all_elements_located(
                (By.XPATH, _SELECTORS["table"]["iniciado_cell"]["value"])
            )
        )
    except TimeoutException:
        logger.info(
            "No se encontraron celdas 'Iniciado' tras el sort "
            "(día sin 'Iniciado' o sin fichas). Continuando."
        )
    _safe_js_click(driver, estado_header)
    logger.info("Tabla ordenada por Estado (descendente)")


def volver_a_pacientes_citados(driver: WebDriver, logger: logging.Logger) -> bool:
    """Hace click en el link 'Pacientes citados' del sidebar para volver
    a la lista. Sin esto, el script se queda pegado en la ficha del paciente.
    """
    try:
        link = driver.find_element(
            By.XPATH,
            "//a[contains(@href, '/main') and normalize-space(text())='Pacientes citados']",
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
        time.sleep(0.3)
        try:
            link.click()
        except Exception:
            driver.execute_script("arguments[0].click();", link)
        time.sleep(1.5)
        logger.info("[crear_notas] Vuelta a 'Pacientes citados' OK")
        return True
    except Exception as e:
        logger.warning(f"[crear_notas] No se pudo volver a 'Pacientes citados': {e}")
        return False
