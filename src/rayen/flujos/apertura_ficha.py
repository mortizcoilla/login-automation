"""Flujo: abrir la ficha de un paciente en Rayen a partir del informe.

Origen: antes vivia como `paso_4_1_abrir_ficha` dentro de
`src/tools/crear_notas_clinicas.py`. Se extrae aqui (sesion 2026-09-21)
para que paso 3 (Pancho) y paso 8 (cargar_ficha) compartan la misma
logica de apertura sin duplicarla.

Reglas duras preservadas:
- REQ-019: match exacto -> parcial unico -> ambiguo NO matchea.
- REQ-030: timeout del panel 60s; sin carga -> `paciente.panel_cargo=False`,
  NO se re-clickea (un segundo click no ayuda; la fila queda stale).
- REQ-031: doble-click tolerante a stale element (delegado a
  `src.rayen.tabla._doble_click_en_paciente`).

Contrato:
    abrir_ficha_por_nombre(driver, logger, paciente) -> bool
        True  -> la ficha esta abierta y el panel cargo (o intento
                 cargar, puede que no haya cargado).
        False -> no se encontro al paciente en la tabla del dia.

El llamador es responsable de verificar `paciente.panel_cargo` si le
importa que la extraccion proceda sobre datos reales (paso 3 si; paso
8 solo necesita la ficha abierta para pegar texto).
"""

from __future__ import annotations

import logging

from selenium.webdriver.remote.webdriver import WebDriver

from src.notas.modelos import PacienteObjetivo
from src.rayen.extraccion.identificacion import _wait_visible
from src.rayen.navegacion import select_date, sort_by_estado
from src.rayen.tabla import _buscar_paciente_en_tabla, _doble_click_en_paciente

# Senal inequivoca de que la ficha del paciente esta abierta: aparece
# el <div>Atencion actual</div> dentro de un <li> de la navegacion
# vertical (clases `verticalnav-tab verticalnav-tab-active`), segun
# sesion 2026-09-21 con Yadira.
#
# HTML observado:
#   <li role="presentation"
#       class="verticalnav-tab verticalnav-tab-active">
#     <div>Atencion actual</div>
#   </li>
#
# Este es el LIMITE del flujo compartido entre paso 3 y paso 8:
#   - Paso 3 (Pancho) sigue: hace click en Atencion actual y entra al
#     panel de evaluacion para extraer motivo/anamnesis/etc.
#   - Paso 8 (cargar_ficha) NO hace click: se queda aqui y pega la
#     ficha generada en el editor asociado a Atencion actual.
#
# Mantenemos los selectores antiguos como fallback (compatibilidad con
# versiones previas de Rayen):
# - <li id='anamnesis'>: versiones viejas del UI.
# - <table[.//tbody/th]>: tabla de identificacion del paciente.
# - <div.side-card> con rct-tree: arbol ECICEP.
# - <*.stratification-card>: ECICEP-g3 (la estratificacion carga primero).
#
# Sesion 2026-09-16: 30s -> 60s para ECICEP-g3 (caso real, el panel
# tarda >30s). NO hacer retry del doble-click aqui (REQ-030): el primer
# click ya nos llevo a la ficha; si el panel no cargo, un segundo click
# no ayuda y la fila queda stale -> TimeoutException.
_PANEL_XPATH = (
    # Limite del flujo compartido (sesion 2026-09-21 con Yadira).
    "//li[contains(@class,'verticalnav-tab-active')]"
    "//div[normalize-space()='Atencion actual'] | "
    "//li[contains(@class,'verticalnav-tab-active')]"
    "//div[normalize-space()='Atención actual'] | "
    "//div[normalize-space()='Atencion actual'] | "
    "//div[normalize-space()='Atención actual'] | "
    # Fallbacks por si la UI cambia o hay versiones viejas.
    "//table[.//tbody/th] | "
    "//li[@id='anamnesis'] | "
    "//div[contains(@class,'side-card')]//*[contains(@class,'rct-tree')] | "
    "//*[contains(@class, 'stratification-card')]"
)
PANEL_TIMEOUT_S = 60


_JS_BUSCAR_SHADOW = """
function buscar(root, palabra, out) {
  const elems = root.querySelectorAll('*');
  for (const el of elems) {
    if (el.shadowRoot) buscar(el.shadowRoot, palabra, out);
  }
  for (const el of elems) {
    const t = (el.textContent || '').trim().toLowerCase();
    if (t === palabra) { out.push(el); return; }
  }
}
const out = [];
buscar(document, arguments[0], out);
return out.length ? out[0] : null;
"""


def _buscar_en_cualquier_frame(driver: WebDriver, xpath: str):
    """Busca un elemento en el doc principal y en todos los iframes.

    Si lo encuentra dentro de un iframe, el driver QUEDA cambiado a ese
    frame (el caller decide volver a default_content).
    """
    from selenium.common.exceptions import NoSuchElementException
    from selenium.webdriver.common.by import By

    driver.switch_to.default_content()
    try:
        return driver.find_element(By.XPATH, xpath)
    except Exception:
        pass
    for frame in driver.find_elements(By.XPATH, "//iframe"):
        try:
            driver.switch_to.frame(frame)
        except Exception:
            continue
        try:
            return driver.find_element(By.XPATH, xpath)
        except Exception:
            driver.switch_to.default_content()
    driver.switch_to.default_content()
    raise NoSuchElementException(f"no encontrado en ningun frame: {xpath}")


def _cerrar_tutorial_onboarding(driver: WebDriver, logger: logging.Logger) -> None:
    """Cierra el tutorial de Rayen si esta presente (hasta 7 clicks).

    Caso real 22-09-2026: al entrar por primera vez a Atencion actual,
    Rayen muestra un onboarding modal (boton 'siguiente', paginacion
    1-2-3) que bloquea el nav vertical. Sin cerrarlo, el panel nunca
    'aparece'. El overlay puede vivir en un iframe: se busca en todos
    los frames y al final se vuelve al documento principal.
    """

    xpath_tutorial = (
        "//*[contains(translate(normalize-space(text()),"
        "'SIGUIENTEETERMINARLISTOFINALIZAR','siguienteeterminarlistofinalizar'),"
        " 'siguiente') or contains(translate(normalize-space(text()),"
        " 'TERMINAR','terminar'), 'terminar') or contains("
        "translate(normalize-space(text()), 'LISTO','listo'), 'listo') "
        "or contains(translate(normalize-space(text()), "
        "'FINALIZAR','finalizar'), 'finalizar')]"
    )
    import time

    driver.switch_to.default_content()
    for paso in range(1, 8):
        # El overlay carga asincrono tras entrar a Atencion actual: hasta
        # 10s esperando a que el boton aparezca en algun frame.
        btn = None
        for _ in range(10):
            try:
                btn = _buscar_en_cualquier_frame(driver, xpath_tutorial)
                break
            except Exception:
                time.sleep(1)
        if btn is None:
            # Ultimo recurso: el overlay puede vivir en un SHADOW DOM
            # (invisible para find_element). Busqueda JS recursiva.
            btn = driver.execute_script(_JS_BUSCAR_SHADOW, "siguiente")
            if btn is None:
                btn = driver.execute_script(_JS_BUSCAR_SHADOW, "terminar")
            if btn is None:
                btn = driver.execute_script(_JS_BUSCAR_SHADOW, "listo")
            if btn is None:
                logger.info("Tutorial onboarding: no quedan botones (cerrado o ausente).")
                driver.switch_to.default_content()
                return
            driver.execute_script("arguments[0].click();", btn)
            logger.info(f"Cerrando tutorial onboarding via shadow DOM (click {paso})...")
            time.sleep(0.5)
            continue
        logger.info(f"Cerrando tutorial onboarding (click {paso})...")
        try:
            btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)
        time.sleep(0.5)
    driver.switch_to.default_content()


def abrir_ficha_por_nombre(
    driver: WebDriver,
    logger: logging.Logger,
    paciente: PacienteObjetivo,
) -> bool:
    """Abre la ficha del paciente en Rayen.

    Pasos:
        1. Filtrar la tabla de Pacientes citados por la fecha del
           paciente.
        2. Buscar la fila por nombre (match exacto -> parcial unico).
           Si no hay match: log warning y retorna False.
        3. Doble click en la fila para abrir la ficha.
        4. Esperar a que cargue el panel del paciente (60s). Si no
           carga: marca `paciente.panel_cargo=False` y sigue. NO
           re-clickea.

    Args:
        driver: WebDriver de Selenium posicionado en Pacientes citados
            (post-login, post-box).
        logger: logger del modulo que invoca (segun convencion del
            proyecto, cada flujo loguea con prefijo del caller).
        paciente: el paciente a abrir. Se muta in-place: si hay match
            parcial, `paciente.nombre_rayen` queda seteado; si el
            panel no cargo, `paciente.panel_cargo` queda en False.

    Returns:
        True si la ficha esta abierta (panel haya cargado o no);
        False si el paciente no aparecio en la tabla.
    """
    logger.info(
        f"Paciente: {paciente.nombre} | fecha={paciente.fecha} "
        f"| tipo={paciente.tipo_atencion}"
    )

    # 1) Filtrar por fecha
    select_date(driver, logger, fecha_str=paciente.fecha)
    sort_by_estado(driver, logger)

    # 2) Buscar al paciente por nombre completo
    resultado_busqueda = _buscar_paciente_en_tabla(driver, logger, paciente.nombre)
    if resultado_busqueda is None:
        logger.warning(
            f"No se encontro a '{paciente.nombre}' en la tabla del {paciente.fecha}"
        )
        return False
    row, nombre_rayen = resultado_busqueda
    if nombre_rayen is not None:
        # Match parcial: guardar el nombre real de Rayen como metadato
        # para que pipelines posteriores (Mortadelo, enriquecer, etc.)
        # puedan matchear.
        paciente.nombre_rayen = nombre_rayen

    # 3) Doble click en la fila para abrir la ficha
    _doble_click_en_paciente(driver, logger, row, nombre_objetivo=paciente.nombre)

    # 4) Esperar a que el panel del paciente se cargue
    panel = _wait_visible(driver, _PANEL_XPATH, timeout=PANEL_TIMEOUT_S)

    if panel is None:
        # Caso real 22-09-2026 (Rosa Davila): el doble click aterriza en
        # la vista "Historia clinica" (Identificacion/Historial), con un
        # badge "NN Atencion actual" en la cabecera. Entrar ahi: click
        # al badge y re-esperar el panel (30s mas).
        logger.info("Panel ausente; intentando click en el badge 'Atencion actual'...")
        try:
            from selenium.webdriver.common.by import By

            badge = driver.find_element(
                By.XPATH,
                "//*[contains(normalize-space(text()), 'Atención actual')]",
            )
            driver.execute_script("arguments[0].click();", badge)
            _cerrar_tutorial_onboarding(driver, logger)
            panel = _wait_visible(driver, _PANEL_XPATH, timeout=30)
        except Exception as e:  # el badge no estaba o fallo el click
            logger.warning(f"Badge 'Atencion actual' no encontrado: {e}")

    if panel is None:
        # REQ-030: no re-clickear. Marcar flag y seguir.
        logger.warning(
            f"Panel no aparecio en {PANEL_TIMEOUT_S}s. "
            f"El flujo procedera sobre lo que haya. "
            f"El caller debera decidir si esto es aceptable."
        )
        # Evidencia para diagnostico: que habia en pantalla.
        try:
            from src.core.rutas import SCREENSHOTS_DIR

            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            ruta = SCREENSHOTS_DIR / f"panel_timeout_{paciente.nombre.replace(' ', '_')}_{PANEL_TIMEOUT_S}s.png"
            driver.save_screenshot(str(ruta))
            logger.warning(f"Screenshot del timeout: {ruta.name}")
        except Exception:
            pass
        paciente.panel_cargo = False
    else:
        logger.info(f"Panel del paciente cargado ({panel.tag_name})")
        paciente.panel_cargo = True

    logger.info(
        f"Ficha abierta para {paciente.nombre} (URL actual: {driver.current_url})"
    )
    return True
