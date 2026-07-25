from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC  # noqa: N812
from selenium.webdriver.support.ui import WebDriverWait

from src.constants import (
    CAMPOS_POR_FILA,
    DATE_FORMAT,
    ESTADO_INICIADO,
    LOGIN_URL,
    SEPARADOR_ANCHO,
)

ByType = str


def _selector(by_str: str, value: str) -> tuple[ByType, str]:
    mapping = {
        "id": By.ID,
        "css": By.CSS_SELECTOR,
        "xpath": By.XPATH,
        "name": By.NAME,
        "class": By.CLASS_NAME,
    }
    if by_str not in mapping:
        raise ValueError(f"Tipo de selector no soportado: {by_str}")
    return mapping[by_str], value


def _selectors_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config",
        "selectors.json",
    )


def _load_selectors() -> dict[str, Any]:
    with open(_selectors_path(), encoding="utf-8") as f:
        selectors: dict[str, Any] = json.load(f)
    return selectors


_SELECTORS: dict[str, Any] = _load_selectors()
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", _SELECTORS["timeouts"]["default"]))
NAVIGATION_TIMEOUT = _SELECTORS["timeouts"]["navigation"]


def _build_chrome_options(headless: bool = False) -> Options:
    opts = Options()
    opts.add_argument("--incognito")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-extensions")
    opts.page_load_strategy = "normal"
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    if headless:
        opts.add_argument("--headless=new")
    return opts


def _make_wait(driver: WebDriver, timeout: int | None = None) -> WebDriverWait:
    return WebDriverWait(driver, timeout or TIMEOUT_SECONDS)


def _es_url_login(url: str) -> bool:
    return url.rstrip("/") == LOGIN_URL.rstrip("/")


def _select(key: str) -> tuple[ByType, str]:
    node: Any = _SELECTORS
    for part in key.split("."):
        node = node[part]
    by_str = node["by"]
    value = node["value"]
    return _selector(by_str, value)


def _wait_url_change(driver: WebDriver, logger: logging.Logger) -> None:
    logger.info("Esperando redireccion fuera de login...")
    _make_wait(driver, NAVIGATION_TIMEOUT).until(lambda d: not _es_url_login(d.current_url))


def _safe_js_click(driver: WebDriver, element: WebElement) -> None:
    driver.execute_script("arguments[0].click();", element)


def _hide_modal(driver: WebDriver, logger: logging.Logger) -> None:
    try:
        driver.execute_script(
            """
            var m = document.querySelector(arguments[0]);
            if (m) m.style.display = 'none';
            """,
            _SELECTORS["login"]["modal"]["value"],
        )
        logger.info("Modal ocultado por JS")
    except WebDriverException:
        logger.info("No habia modal visible")


def _cerrar_alertas(driver: WebDriver, logger: logging.Logger) -> int:
    cerradas = 0
    for selector in _SELECTORS["alerts"]["close_selectors"]:
        try:
            alertas = driver.find_elements(By.CSS_SELECTOR, selector)
        except WebDriverException:
            continue
        for alerta in alertas:
            try:
                alerta.click()
                cerradas += 1
            except (StaleElementReferenceException, WebDriverException):
                continue
    if cerradas:
        logger.info(f"Alertas cerradas: {cerradas}")
    return cerradas


def run_login(
    credentials: dict[str, str],
    logger: logging.Logger,
    headless: bool = False,
) -> WebDriver:
    logger.info("Iniciando instancia de Google Chrome en modo incognito...")
    options = _build_chrome_options(headless)
    driver = webdriver.Chrome(options=options)
    wait = _make_wait(driver)

    try:
        logger.info(f"Navegando a {LOGIN_URL}...")
        driver.get(LOGIN_URL)

        for campo in ("location", "username", "password"):
            by, val = _select(f"login.{campo}")
            el = wait.until(EC.presence_of_element_located((by, val)))
            el.clear()
            el.send_keys(credentials[campo])
            logger.info(f"{campo.capitalize()} insertado")

        logger.info("Esperando habilitacion del boton de ingreso...")
        submit_disabled = _select("login.submit_disabled")
        submit = _select("login.submit")
        from contextlib import suppress

        with suppress(TimeoutException):
            wait.until_not(EC.element_to_be_clickable(submit_disabled))
        wait.until(EC.element_to_be_clickable(submit))

        logger.info("Enviando Enter al boton de inicio de sesion...")
        submit_btn = driver.find_element(*submit)
        submit_btn.send_keys("\n")

        _wait_url_change(driver, logger)
        logger.info("Login completado. Maximizando ventana...")
        driver.maximize_window()

        _hide_modal(driver, logger)

        by, val = _select("menu.bars_icon")
        menu_icon = wait.until(EC.presence_of_element_located((by, val)))
        _safe_js_click(driver, menu_icon)
        logger.info("Menu lateral abierto")
        _capture_after_click(driver, logger, "1_menu")
        _wait_loading_modal_gone(driver, logger, timeout=20)

        by, val = _select("menu.box_item")
        box_menu = wait.until(EC.element_to_be_clickable((by, val)))
        _safe_js_click(driver, box_menu)
        logger.info("Box seleccionado")
        _capture_after_click(driver, logger, "2_box")
        _wait_loading_modal_gone(driver, logger, timeout=30)

        by, val = _select("menu.pacientes_citados")
        try:
            pacientes = _make_wait(driver, 8).until(EC.element_to_be_clickable((by, val)))
        except TimeoutException as e:
            _capture_error(driver, logger, "pacientes_citados_not_found")
            raise TimeoutException(
                f"No se encontro 'Pacientes citados' tras click en Box. "
                f"URL: {driver.current_url}. "
                f"Probable cambio de UI. Revise error_pacientes_citados_not_found_*.png"
            ) from e
        _safe_js_click(driver, pacientes)
        logger.info("Pacientes citados clickeado")
        _capture_after_click(driver, logger, "3_pacientes_citados")

        # Esperar a que termine la carga de la página de Pacientes citados.
        # Sin esto, las operaciones siguientes (select_date, etc.) fallan
        # porque el modal "Cargando" tapa el DOM.
        _wait_loading_modal_gone(driver, logger, timeout=30)

        logger.info(
            f"run_login OK — URL final: {driver.current_url}"
        )
        return driver

    except TimeoutException as e:
        _capture_error(driver, logger, "timeout_login")
        logger.error(f"Tiempo de espera agotado durante login: {e}")
        raise
    except NoSuchElementException as e:
        _capture_error(driver, logger, "missing_element_login")
        logger.error(f"Elemento no encontrado durante login: {e}")
        raise
    except WebDriverException as e:
        _capture_error(driver, logger, "webdriver_login")
        logger.error(f"Error de WebDriver durante login: {e}")
        raise


def _capture_after_click(
    driver: WebDriver, logger: logging.Logger, tag: str
) -> None:
    """Captura screenshot + HTML después de un click, como diagnóstico.

    No es un error: es un snapshot del estado de la UI tras un click,
    útil para entender en qué quedó la página después de la navegación.
    """
    if not driver:
        return
    try:
        path = f"step_{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        driver.save_screenshot(path)
        logger.info(f"Screenshot: {path}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No se pudo capturar screenshot: {e}")


def _capture_error(driver: WebDriver | None, logger: logging.Logger, tag: str) -> None:
    if not driver:
        return
    try:
        path = f"error_{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        driver.save_screenshot(path)
        logger.error(f"Screenshot guardado: {path}")
        with open(
            f"error_{tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html", "w", encoding="utf-8"
        ) as f:
            f.write(driver.page_source[:200000])
    except Exception as e:
        logger.warning(f"No se pudo capturar screenshot: {e}")


# Selector XPath del modal de carga de Rayen. Es un overlay que dice
# "Cargando - Espere un momento por favor" con un spinner. Aparece cada
# vez que la página está trayendo datos del servidor y, si no lo
# esperamos, las operaciones siguientes fallan con TimeoutException
# porque el DOM no está listo.
_LOADING_MODAL_XPATH = "//*[contains(text(), 'Espere un momento')]"


def _wait_loading_modal_gone(
    driver: WebDriver, logger: logging.Logger, timeout: int = 30
) -> None:
    """Espera a que el modal 'Cargando' de Rayen desaparezca.

    Estrategia en dos pasos:
    1. Verificar si el modal está visible (hasta 5s).
       Si no se encuentra, la página probablemente ya cargó — salimos.
    2. Si está visible, esperar hasta `timeout` a que desaparezca.

    Ante cualquier error, logueamos y seguimos. Es un wait defensivo,
    no debe bloquear el flujo si falla.
    """
    try:
        wait_short = _make_wait(driver, 5)
        try:
            wait_short.until(
                EC.presence_of_element_located((By.XPATH, _LOADING_MODAL_XPATH))
            )
        except TimeoutException:
            logger.info("No se detectó modal 'Cargando' — página probablemente ya cargada")
            return
        logger.info("Modal 'Cargando' detectado, esperando a que se vaya...")
        _make_wait(driver, timeout).until_not(
            EC.presence_of_element_located((By.XPATH, _LOADING_MODAL_XPATH))
        )
        logger.info("Modal 'Cargando' desapareció")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Wait defensivo de modal 'Cargando' falló: {e}. Continuando...")


def ensure_session_alive(driver: WebDriver, logger: logging.Logger) -> bool:
    if _es_url_login(driver.current_url):
        logger.warning("Sesion expirada (URL de login detectada)")
        return False
    return True


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
    rows = wait.until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "div.rt-tr-group")
        )
    )
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


def safe_quit(driver: WebDriver | None, logger: logging.Logger) -> None:
    if not driver:
        return
    try:
        driver.quit()
        logger.info("Navegador cerrado")
    except WebDriverException as e:
        logger.warning(f"Error cerrando navegador: {e}")


def login_url() -> str:
    return LOGIN_URL


def separador(caracter: str = "-", ancho: int = SEPARADOR_ANCHO) -> str:
    return caracter * ancho
