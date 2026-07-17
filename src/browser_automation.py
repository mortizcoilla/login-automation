import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)

LOGIN_URL = "https://clinico.rayenaps.cl/"
SELECTOR_LOCATION = (By.ID, "location")
SELECTOR_USERNAME = (By.ID, "username")
SELECTOR_PASSWORD = (By.ID, "password")
SELECTOR_SUBMIT = (By.CSS_SELECTOR, "button.orange-btn[type='submit']")
SELECTOR_MENU_ICON = (By.CSS_SELECTOR, "i.fal.fa-bars.navbar-left-icon")
SELECTOR_BOX_MENU = (By.CSS_SELECTOR, "li.navbar-dropdown.d-flex.justify-content-between")
SELECTOR_PACIENTES_CITADOS = (By.CSS_SELECTOR, "span.text-wrap")
TIMEOUT_SECONDS = 15


def _build_chrome_options(headless=False):
    chrome_options = Options()

    chrome_options.add_argument("--incognito")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    if headless:
        chrome_options.add_argument("--headless=new")

    return chrome_options


def run_login(credentials, logger, headless=False):
    try:
        logger.info("Iniciando instancia de Google Chrome en modo incognito...")
        chrome_options = _build_chrome_options(headless)
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, TIMEOUT_SECONDS)

        logger.info(f"Navegando a {LOGIN_URL}...")
        driver.get(LOGIN_URL)

        logger.info("Buscando campo de ubicacion...")
        location_el = wait.until(EC.presence_of_element_located(SELECTOR_LOCATION))
        location_el.clear()
        location_el.send_keys(credentials["location"])
        logger.info(f"Ubicacion insertada: {credentials['location']}")

        logger.info("Buscando campo de usuario...")
        username_el = wait.until(EC.presence_of_element_located(SELECTOR_USERNAME))
        username_el.clear()
        username_el.send_keys(credentials["username"])
        logger.info(f"Usuario insertado: {credentials['username']}")

        logger.info("Buscando campo de clave...")
        password_el = wait.until(EC.presence_of_element_located(SELECTOR_PASSWORD))
        password_el.clear()
        password_el.send_keys(credentials["password"])
        logger.info("Clave insertada exitosamente")

        logger.info("Esperando a que el boton de ingreso se habilite...")
        wait.until_not(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.orange-btn.disabled")))
        wait.until(EC.element_to_be_clickable(SELECTOR_SUBMIT))
        logger.info("Boton de ingreso habilitado")

        logger.info("Enviando Enter al boton de inicio de sesion...")
        submit_btn = driver.find_element(*SELECTOR_SUBMIT)
        submit_btn.send_keys("\n")
        logger.info("Enter enviado al boton de inicio de sesion")

        logger.info("Esperando carga de la pagina principal...")
        wait.until(lambda d: d.current_url != LOGIN_URL or d.current_url != LOGIN_URL.rstrip("/"))

        logger.info("Maximizando ventana...")
        driver.maximize_window()

        logger.info("Cerrando modal si está presente...")
        try:
            driver.execute_script("""
                var m = document.querySelector('.rescheck-modal');
                if (m) m.style.display = 'none';
            """)
            logger.info("Modal ocultado por JS")
            time.sleep(0.5)
        except Exception:
            logger.info("No habia modal visible")

        logger.info("Buscando icono de menu (bars)...")
        menu_icon = wait.until(EC.presence_of_element_located(SELECTOR_MENU_ICON))
        driver.execute_script("arguments[0].click();", menu_icon)
        logger.info("Clic en icono de menu ejecutado")

        logger.info("Buscando elemento 'Box' en el menu...")
        box_menu = wait.until(EC.element_to_be_clickable(SELECTOR_BOX_MENU))
        box_menu.click()
        logger.info("Clic en 'Box' ejecutado")

        logger.info("Buscando 'Pacientes citados'...")
        pacientes_citados = wait.until(EC.element_to_be_clickable(SELECTOR_PACIENTES_CITADOS))
        pacientes_citados.click()
        logger.info("Clic en 'Pacientes citados' ejecutado")

        logger.info("Login completado. El navegador permanece abierto.")
        return driver

    except TimeoutException as e:
        logger.error(f"Tiempo de espera agotado al interactuar con el DOM: {e}")
        raise
    except NoSuchElementException as e:
        logger.error(f"Elemento no encontrado en el DOM: {e}")
        raise
    except WebDriverException as e:
        logger.error(f"Error de WebDriver o problema de conexion: {e}")
        raise
    except Exception as e:
        logger.error(f"Error inesperado durante la automatizacion: {e}")
        raise


def _cerrar_alertas(driver, logger):
    try:
        alertas = driver.find_elements(By.CSS_SELECTOR, ".alert-info .close, .alert-info button.close, .alert-dismissible .close")
        for a in alertas:
            try:
                a.click()
                logger.info("Alerta cerrada")
            except Exception:
                pass
        time.sleep(0.3)
    except Exception:
        pass


def sort_by_estado(driver, logger):
    wait = WebDriverWait(driver, TIMEOUT_SECONDS)

    _cerrar_alertas(driver, logger)

    logger.info("Buscando encabezado de columna 'Estado'...")
    estado_header = wait.until(
        EC.presence_of_element_located(
            (By.XPATH, "//div[contains(@class, 'rt-th') and contains(., 'Estado')]")
        )
    )

    logger.info("Ordenando por Estado (1er click)...")
    driver.execute_script("arguments[0].click();", estado_header)
    time.sleep(1)

    logger.info("Ordenando por Estado (2do click - descendente)...")
    driver.execute_script("arguments[0].click();", estado_header)
    time.sleep(1)

    logger.info("Tabla ordenada por Estado (descendente).")


def get_pacientes_iniciados(driver, logger):
    wait = WebDriverWait(driver, TIMEOUT_SECONDS)

    logger.info("Buscando pacientes con estado 'Iniciado'...")
    iniciado_cells = wait.until(
        EC.presence_of_all_elements_located(
            (By.XPATH, "//div[contains(@class, 'rt-td') and text()='Iniciado']")
        )
    )

    rows = []
    for cell in iniciado_cells:
        row = cell.find_element(By.XPATH, "./ancestor::div[contains(@class, 'rt-tr-group')]")
        rows.append(row)

    logger.info(f"Pacientes con estado 'Iniciado': {len(rows)}")
    return rows


def extraer_datos_fila(row):
    celdas = row.find_elements(By.CSS_SELECTOR, "div.rt-td")
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


def select_date(driver, logger):
    import re
    from datetime import datetime

    fecha_str = input("Ingrese fecha (dd-mm-yyyy): ").strip()

    if not re.match(r"^\d{2}-\d{2}-\d{4}$", fecha_str):
        raise ValueError("Formato inválido. Use dd-mm-yyyy (ej: 29-05-2026)")

    datetime.strptime(fecha_str, "%d-%m-%Y")

    logger.info(f"Insertando fecha {fecha_str} por JS...")
    driver.execute_script(
        """
        var input = document.querySelector('input.date-input');
        if (!input) throw new Error('No se encontró input.date-input');

        var nativeSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        nativeSetter.call(input, arguments[0]);

        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
    """,
        fecha_str,
    )

    logger.info(f"Fecha {fecha_str} ingresada correctamente")
    return fecha_str
