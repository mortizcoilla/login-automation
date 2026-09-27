"""Gestion del limite de pestañas de ficha abiertas en Rayen (REQ-090).

Rayen APS permite como maximo 8 pestañas de ficha abiertas
simultaneamente y el conteo vive EN EL SERVIDOR: re-loguearse no las
cierra y se acumulan entre corridas. Al llegar a 8, Rayen bloquea toda
apertura nueva con el modal "Supero maximo de pestañas abiertas" y el
flujo ve "panel ausente": notas sin identificacion ni historial y
pacientes con (-) en el informe enriquecido (incidente 25/26-09-2026,
pacientes 14-20 del informe).

Este modulo: detecta el modal, lo descarta (boton Descartar), deja un
volcado HTML del tablero de pestañas como evidencia de diagnostico y
hace un mejor-esfuerzo de cierre de las pestañas acumuladas.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path

# El modal dice "Supero maximo de pestañas abiertas". Tolerante a
# tildes: m[aá]ximo / pesta[nñ]as.
MODAL_RE = re.compile(r"m[aá]ximo de pesta[nñ]as", re.IGNORECASE)

# Pestañas de ficha del tablero inferior: su texto arranca con "FC:"
# (ficha clinica). Se usa text() (nodo propio) y no "." para no
# matchear contenedores padres.
XPATH_PESTANA_FICHA = "//*[starts-with(normalize-space(text()), 'FC:')]"

# Candidatos de control de cierre de pestaña. El DOM exacto del
# tablero es desconocido (por eso el volcado de evidencia): cada
# candidato es inofensivo si no matchea nada y cada click queda
# logueado. El primer candidato cubre el patron Ant Design (React),
# familia de componentes que Rayen G3 ya usa en el nav vertical.
XPATH_CANDIDATOS_CIERRE = (
    "//button[contains(@class,'ant-tabs-tab-remove')]"
    " | //*[contains(@class,'ant-tabs-tab-remove')]",
    "//*[@title='Cerrar' or @aria-label='Cerrar'"
    " or @title='Close' or @aria-label='Close']",
    "//*[contains(@class,'tab')]//*[self::button or self::i or self::span]"
    "[contains(translate(@class,'CLOSE','close'),'close')]",
)

# Tope de clicks por pasada: evitar tormentas de clicks si un
# candidato matchea un contenedor grande.
MAX_CLICKS_POR_PASADA = 12


def modal_pestanas_presente(driver) -> bool:
    """True si el modal 'Supero maximo de pestañas' esta en el DOM."""
    try:
        return bool(MODAL_RE.search(driver.page_source or ""))
    except Exception:
        return False


def contar_pestanas_ficha(driver) -> int:
    """Cuantas pestañas de ficha ('FC: ...') hay en el tablero.

    Devuelve -1 si no se puede saber (driver muerto, DOM no cargado).
    """
    try:
        from selenium.webdriver.common.by import By

        return len(driver.find_elements(By.XPATH, XPATH_PESTANA_FICHA))
    except Exception:
        return -1


def _click_nativo(driver, el) -> None:
    """Click nativo con scroll previo; fallback JS (patron Rayen)."""
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", el
        )
        time.sleep(0.2)
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", el)


def descartar_modal_pestanas(driver, logger: logging.Logger) -> bool:
    """Click en 'Descartar' (naranja) del modal; fallback 'Volver'."""
    from selenium.webdriver.common.by import By

    for texto in ("Descartar", "Volver"):
        try:
            btn = driver.find_element(
                By.XPATH, f"//button[normalize-space()='{texto}']"
            )
        except Exception:
            continue
        try:
            _click_nativo(driver, btn)
            logger.info(f"[pestanas] Modal descartado via boton '{texto}'.")
            time.sleep(1.0)
            return True
        except Exception as e:
            logger.warning(
                f"[pestanas] Boton '{texto}' presente pero no clickeable: {e}"
            )
    return False


def volcar_tablero_pestanas(driver, logger: logging.Logger) -> Path | None:
    """Deja el page_source en logs/ como evidencia del estado del tablero."""
    try:
        from src.core.rutas import LOGS_DIR

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = LOGS_DIR / f"pestanas_dump_{ts}.html"
        ruta.write_text(driver.page_source or "", encoding="utf-8")
        logger.warning(f"[pestanas] Evidencia HTML del tablero: {ruta}")
        return ruta
    except Exception as e:
        logger.warning(f"[pestanas] No se pudo volcar el HTML: {e}")
        return None


def cerrar_pestanas_ficha(driver, logger: logging.Logger) -> int:
    """Mejor-esfuerzo: acciona controles de cierre de pestañas de ficha.

    Devuelve cuantos controles se accionaron. Si el DOM real no usa
    ningun candidato, devuelve 0 — el volcado de evidencia es la via
    para descubrir el control exacto y ajustar XPATH_CANDIDATOS_CIERRE.
    """
    from selenium.webdriver.common.by import By

    accionados = 0
    for xp in XPATH_CANDIDATOS_CIERRE:
        try:
            elementos = driver.find_elements(By.XPATH, xp)
        except Exception:
            continue
        for el in elementos:
            if accionados >= MAX_CLICKS_POR_PASADA:
                return accionados
            try:
                _click_nativo(driver, el)
                accionados += 1
                logger.debug(f"[pestanas] Cierre accionado: {xp}")
                time.sleep(0.4)
            except Exception:
                continue
    if accionados:
        # Cerrar una pestaña con cambios puede abrir un confirm;
        # descartarlo para no dejar el flujo tapado.
        time.sleep(1.0)
        if modal_pestanas_presente(driver):
            descartar_modal_pestanas(driver, logger)
    return accionados


def liberar_pestanas(driver, logger: logging.Logger) -> bool:
    """Orquestador al detectar el modal: descartar + evidencia + cerrar.

    Devuelve True si tras el intento el modal ya no esta en el DOM.
    """
    logger.warning("[pestanas] Modal 'Supero maximo de pestañas' detectado.")
    descartar_modal_pestanas(driver, logger)
    volcar_tablero_pestanas(driver, logger)
    n = contar_pestanas_ficha(driver)
    logger.warning(f"[pestanas] Pestañas de ficha en el tablero: {n}")
    accionados = cerrar_pestanas_ficha(driver, logger)
    logger.warning(f"[pestanas] Controles de cierre accionados: {accionados}")
    return not modal_pestanas_presente(driver)
