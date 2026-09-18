"""Extractor de la tabla de Identificacion del paciente.

Split de crear_notas_clinicas (Fase 3c). Incluye los helpers de espera
_wait_visible/_safe_text compartidos por los demas extractores.

"""

from __future__ import annotations

import logging
import re

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import (
    expected_conditions as EC,  # noqa: N812 (alias estandar de Selenium)
)
from selenium.webdriver.support.ui import WebDriverWait

# ---- Paso 4.2: extraer informacion de la ficha abierta ----


def _wait_visible(driver: WebDriver, selector: str, timeout: int = 10) -> WebElement | None:
    """Espera a que un elemento sea visible. Devuelve None si no aparece.

    Acepta selectores CSS o xpath. Se detecta por el prefijo: si
    empieza con '//' o '(' se trata como xpath; en otro caso CSS.
    """
    if selector.startswith("//") or selector.startswith("("):
        by, val = By.XPATH, selector
    else:
        by, val = By.CSS_SELECTOR, selector
    try:
        wait = WebDriverWait(driver, timeout)
        return wait.until(EC.visibility_of_element_located((by, val)))
    except Exception:
        return None


def _safe_text(el: WebElement | None) -> str:
    """Devuelve el texto de un WebElement, o string vacio si es None."""
    if el is None:
        return ""
    return el.text.strip()


def extraer_identificacion(driver: WebDriver, logger: logging.Logger) -> dict[str, str]:
    """Extrae la tabla de identificacion del paciente.

    La tabla tiene pares <th>:<td> con campos como RUN, Fecha de nacimiento,
    Direccion, etc. Devuelve un dict {campo: valor}.

    Estrategia de busqueda (orden de fallback):
    1) Cualquier <table> que tenga <th> en <tbody> (estructura del paciente).
    2) Si no, cualquier <table> con <tbody> adentro de un div.side-nav-margin.
    3) Si no, la primera <table.table> de la pagina.

    Cuando un <td> contiene una sub-tabla (caso de Telefono), se
    concatenan los valores en un solo string con " | " como separador.

    Desduplicacion: cuando Rayen lista el mismo telefono bajo varios
    labels ("Telefono", "Tipo otro telefono de contacto", "Telefono
    movil"), el script conserva solo el primero para no triplicar el
    numero.
    """
    logger.info("[crear_notas] Extrayendo tabla de identificacion...")
    out: dict[str, str] = {}
    try:
        table = None

        # Paso 1: tabla con <th> en <tbody> (la del paciente).
        tables_con_th = driver.find_elements(
            By.XPATH,
            "//table[.//tbody/th]",
        )
        if tables_con_th:
            table = tables_con_th[0]
            logger.info(
                f"[crear_notas] Tabla encontrada por <tbody><th> ({len(tables_con_th)} match)"
            )

        # Paso 2: tabla dentro de div.side-nav-margin.
        if table is None:
            tables_side = driver.find_elements(
                By.XPATH,
                "//div[contains(@class,'side-nav-margin')]//table[.//tbody]",
            )
            if tables_side:
                table = tables_side[0]
                logger.info(
                    f"[crear_notas] Tabla encontrada por side-nav-margin ({len(tables_side)} match)"
                )

        # Paso 3: primera tabla.table de la pagina.
        if table is None:
            tables_any = driver.find_elements(By.CSS_SELECTOR, "table.table")
            if tables_any:
                table = tables_any[0]
                logger.info(
                    f"[crear_notas] Tabla encontrada por fallback table.table "
                    f"({len(tables_any)} match)"
                )

        if table is None:
            total_t = len(driver.find_elements(By.CSS_SELECTOR, "table"))
            total_tbody = len(driver.find_elements(By.CSS_SELECTOR, "table tbody"))
            total_th = len(driver.find_elements(By.CSS_SELECTOR, "table th"))
            logger.warning(
                f"[crear_notas] No se encontro tabla. DOM tiene: "
                f"tables={total_t}, tbodies={total_tbody}, ths={total_th}"
            )
            return out

        rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
        pares: list[tuple[str, str]] = []
        for r in rows:
            th_elements = r.find_elements(By.CSS_SELECTOR, "th")
            if not th_elements:
                continue
            th_text = _safe_text(th_elements[0])
            tds = r.find_elements(By.CSS_SELECTOR, "td")
            if not th_text or not tds:
                continue
            # Si el td es una sub-tabla (caso de Telefono), concatenar
            # los valores de la sub-tabla en un solo string.
            subtable = tds[0].find_elements(By.CSS_SELECTOR, "table")
            if subtable:
                celdas_sub = subtable[0].find_elements(By.CSS_SELECTOR, "td")
                valores = []
                for celda in celdas_sub:
                    txt = _safe_text(celda)
                    if txt:
                        valores.append(txt)
                td_text = " | ".join(valores) if valores else _safe_text(tds[0])
            else:
                td_text = _safe_text(tds[0])
            if td_text:
                pares.append((th_text, td_text))

        # Desduplicar telefonos consecutivos con el mismo valor.
        patron_telefono = re.compile(
            r"tel[eé]fono|tel[eé]fonos|movil|m[oó]vil|contacto",
            re.IGNORECASE,
        )
        filtrados: list[tuple[str, str]] = []
        prev_telefono_value: str | None = None
        for label, valor in pares:
            es_tel = bool(patron_telefono.search(label))
            if es_tel and prev_telefono_value is not None and valor.strip() == prev_telefono_value:
                continue
            filtrados.append((label, valor))
            prev_telefono_value = valor.strip() if es_tel else None

        for label, valor in filtrados:
            out[label] = valor
    except Exception as e:
        logger.warning(f"[crear_notas] Error extrayendo identificacion: {e}")
    logger.info(f"[crear_notas] Identificacion: {len(out)} campos")
    return out
