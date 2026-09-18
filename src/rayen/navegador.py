"""Nucleo del navegador: Chrome, login en Rayen y vida de sesion.

Split de src/browser_automation.py (refactorizacion 2026-09-18, Fase 3a).
Aca vive TODO lo relativo a: construccion de Chrome, carga de
config/selectors, login + navegacion post-login hasta 'Pacientes
citados', capturas de diagnostico y cierre defensivo.

La manipulacion de la tabla vive en rayen.tabla; la navegacion entre
paginas (fecha, sort, volver) en rayen.navegacion.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
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
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import (
    expected_conditions as EC,  # noqa: N812 (alias estandar de Selenium)
)
from selenium.webdriver.support.ui import WebDriverWait

from src.constants import LOGIN_URL, SEPARADOR_ANCHO
from src.core.rutas import SCREENSHOTS_DIR

ByType = str


# ---------------------------------------------------------------------------
# Config: selectors.json
# ---------------------------------------------------------------------------


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
    from src.core.rutas import ROOT

    return os.path.join(str(ROOT), "config", "selectors.json")


def _load_selectors() -> dict[str, Any]:
    with open(_selectors_path(), encoding="utf-8") as f:
        selectors: dict[str, Any] = json.load(f)
    return selectors


_SELECTORS: dict[str, Any] = _load_selectors()
TIMEOUT_SECONDS = int(os.getenv("TIMEOUT_SECONDS", _SELECTORS["timeouts"]["default"]))
NAVIGATION_TIMEOUT = _SELECTORS["timeouts"]["navigation"]


# ---------------------------------------------------------------------------
# Env / Chrome options
# ---------------------------------------------------------------------------


def _env_bool(key: str, default: bool = False) -> bool:
    """Lee una env var como bool. True si el valor (case-insensitive, stripped)
    esta en {"1", "true", "yes", "on"}. Cualquier otro valor (incluido vacio)
    devuelve `default`. Ausencia de la variable tambien devuelve `default`.
    """
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# Default leido al importar modulo. run_login()/login_rayen() usan este valor
# cuando el caller NO pasa `headless` explicitamente. Para CI / produccion
# setear HEADLESS=true; para desarrollo local dejar sin definir (False = visible).
HEADLESS_DEFAULT: bool = _env_bool("HEADLESS", False)


def _resolve_headless(headless: bool | None) -> bool:
    """Resuelve el flag `headless` final: si el caller pasa None, usa
    `HEADLESS_DEFAULT` (env var). Si pasa bool explicito, gana el caller.

    Funcion pura para facilitar testing.
    """
    return HEADLESS_DEFAULT if headless is None else headless


def _build_chrome_options(
    headless: bool = False,
    download_dir: str | None = None,
) -> Options:
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
    if download_dir:
        # Configurar carpeta de descargas para que Chrome NO muestre
        # el dialogo "Guardar como" y guarde directo a download_dir.
        opts.add_experimental_option(
            "prefs",
            {
                "download.default_directory": download_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
            },
        )
    return opts


# ---------------------------------------------------------------------------
# Helpers de espera / clicks
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Login (incluye navegacion post-login hasta 'Pacientes citados')
# ---------------------------------------------------------------------------


def run_login(
    credentials: dict[str, str],
    logger: logging.Logger,
    headless: bool | None = None,
    download_dir: str | None = None,
) -> WebDriver:
    """Inicia Chrome, autentica en Rayen y retorna el WebDriver.

    Args:
        credentials: dict con `location`, `username`, `password`.
        logger: logger compartido.
        headless: si True, Chrome corre sin ventana visible. Si None (default),
            se usa el valor de la env var `HEADLESS` (cargado al importar el
            modulo). Pase un bool explicito para forzar el modo independientemente
            del environment.
        download_dir: carpeta de descargas para Chrome (None = dialogo nativo).
    """
    if headless is None:
        headless = _resolve_headless(headless)
    logger.info("Iniciando instancia de Google Chrome en modo incognito...")
    options = _build_chrome_options(headless, download_dir=download_dir)
    from src.core.rutas import LOGS_DIR

    os.makedirs(LOGS_DIR, exist_ok=True)
    service = Service(service_log_path=os.path.join(str(LOGS_DIR), "chromedriver.log"))
    driver = webdriver.Chrome(options=options, service=service)
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
        with contextlib.suppress(TimeoutException):
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
        logger.info(f"run_login OK — URL final: {driver.current_url}")
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


# ---------------------------------------------------------------------------
# Capturas de diagnostico
# ---------------------------------------------------------------------------


def _capture_after_click(driver: WebDriver, logger: logging.Logger, tag: str) -> None:
    """Captura screenshot + HTML después de un click, como diagnóstico.

    No es un error: es un snapshot del estado de la UI tras un click,
    útil para entender en qué quedó la página después de la navegación.
    """
    if not driver:
        return
    try:
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = SCREENSHOTS_DIR / f"step_{tag}_{ts}.png"
        driver.save_screenshot(str(path))
        logger.info(f"Screenshot: {path}")
    except Exception as e:
        logger.warning(f"No se pudo capturar screenshot: {e}")


def _capture_error(driver: WebDriver | None, logger: logging.Logger, tag: str) -> None:
    if not driver:
        return
    try:
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        png_path = SCREENSHOTS_DIR / f"error_{tag}_{ts}.png"
        html_path = SCREENSHOTS_DIR / f"error_{tag}_{ts}.html"
        driver.save_screenshot(str(png_path))
        logger.error(f"Screenshot guardado: {png_path}")
        html_path.write_text(driver.page_source[:200000], encoding="utf-8")
    except Exception as e:
        logger.warning(f"No se pudo capturar screenshot: {e}")


# ---------------------------------------------------------------------------
# Modal de carga de Rayen
# ---------------------------------------------------------------------------

# Selector XPath del modal de carga de Rayen. Es un overlay que dice
# "Cargando - Espere un momento por favor" con un spinner. Aparece cada
# vez que la página está trayendo datos del servidor y, si no lo
# esperamos, las operaciones siguientes fallan con TimeoutException
# porque el DOM no está listo.
_LOADING_MODAL_XPATH = "//*[contains(text(), 'Espere un momento')]"


def _wait_loading_modal_gone(driver: WebDriver, logger: logging.Logger, timeout: int = 30) -> None:
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
            wait_short.until(EC.presence_of_element_located((By.XPATH, _LOADING_MODAL_XPATH)))
        except TimeoutException:
            logger.info("No se detectó modal 'Cargando' — página probablemente ya cargada")
            return
        logger.info("Modal 'Cargando' detectado, esperando a que se vaya...")
        _make_wait(driver, timeout).until_not(
            EC.presence_of_element_located((By.XPATH, _LOADING_MODAL_XPATH))
        )
        logger.info("Modal 'Cargando' desapareció")
    except Exception as e:
        logger.warning(f"Wait defensivo de modal 'Cargando' falló: {e}. Continuando...")


# ---------------------------------------------------------------------------
# Vida de sesion
# ---------------------------------------------------------------------------


def ensure_session_alive(driver: WebDriver, logger: logging.Logger) -> bool:
    if _es_url_login(driver.current_url):
        logger.warning("Sesion expirada (URL de login detectada)")
        return False
    return True


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
