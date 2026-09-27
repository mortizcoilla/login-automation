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
from src.rayen import pestanas
from src.rayen.navegacion import (
    select_date,
    sort_by_estado,
    volver_a_pacientes_citados,
)
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
    "//*[contains(@class, 'stratification-card')] | "
    # UI nueva G3 (23-09-2026): la vista de atencion tiene los paneles
    # 'Evaluacion' y 'Plan' y la seccion 'Anamnesis' (caso Natalie).
    "//h5[normalize-space()='Evaluación'] | "
    "//h4[normalize-space()='Evaluación'] | "
    "//h3[normalize-space()='Evaluación'] | "
    "//div[normalize-space()='Evaluación'] | "
    "//h5[normalize-space()='Anamnesis'] | "
    "//div[normalize-space()='Anamnesis']"
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


def _cerrar_tutorial_onboarding(driver: WebDriver, logger: logging.Logger) -> bool:
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
                # No hay tutorial (o ya cerro): salir limpio. El volcado
                # HTML queda como evidencia de diagnostico.
                logger.info("Tutorial onboarding: no quedan botones (cerrado o ausente).")
                try:
                    from selenium.webdriver.common.by import By

                    from src.core.rutas import LOGS_DIR as _LD

                    _LD.mkdir(parents=True, exist_ok=True)
                    driver.switch_to.default_content()
                    (_LD / "tutorial_main.html").write_text(
                        driver.page_source, encoding="utf-8"
                    )
                    for j, frame in enumerate(
                        driver.find_elements(By.XPATH, "//iframe")
                    ):
                        try:
                            driver.switch_to.frame(frame)
                            (_LD / f"tutorial_frame_{j}.html").write_text(
                                driver.page_source, encoding="utf-8"
                            )
                        except Exception:
                            continue
                        finally:
                            driver.switch_to.default_content()
                except Exception:
                    driver.switch_to.default_content()
                return False
            driver.execute_script(
                "if (arguments[0]) arguments[0].click();", btn
            )
            logger.info(f"Cerrando tutorial onboarding via shadow DOM (click {paso})...")
            time.sleep(0.5)
            return True
        logger.info(f"Cerrando tutorial onboarding (click {paso})...")
        try:
            btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)
        time.sleep(0.5)
    driver.switch_to.default_content()
    return True


def _wait_present(driver, xpath: str, timeout: int):
    """Espera PRESENCIA en el DOM (a diferencia de _wait_visible)."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC  # noqa: N812
    from selenium.webdriver.support.ui import WebDriverWait

    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.XPATH, xpath))
    )


def _entrar_atencion_y_esperar_editor(
    driver: WebDriver, logger: logging.Logger, budget_s: int, poll_s: float = 2.0
):
    """Entra a la atencion y espera la senal editable.

    DOS estados posibles (Yadira 26-09-2026):
      - ("lapiz", el)   -> hay anamnesis: se puede editar/descartar
      - ("agregar", el) -> SIN anamnesis (placeholder 'Agregar!'): se
        creara una nueva directamente
    Flujo real: el doble click aterriza en la vista 'Historia clinica' —
    hay que CLICK en la pestaña 'Atencion actual' del nav vertical. En
    el camino puede aparecer el tutorial onboarding (se cierra).
    Devuelve None si ninguna senal aparece en el presupuesto.
    """
    import time as _time

    from selenium.webdriver.common.by import By

    tab_atencion = (
        By.XPATH,
        "//li[contains(@class, 'verticalnav-tab')]"
        "[.//div[normalize-space(text())='Atención actual']]",
    )
    agregar_btn = (
        By.XPATH,
        "//button[contains(@class,'btn-info')]"
        "[normalize-space()='Agregar!']",
    )
    fin = _time.monotonic() + budget_s
    tab_hecho = False
    while _time.monotonic() < fin:
        # REQ-090: modal de limite de pestañas -> senal especial; el
        # caller libera pestañas y reintenta la apertura.
        if pestanas.modal_pestanas_presente(driver):
            return "pestanas", None
        # Senal 1: hay anamnesis -> lapiz (seccion editable).
        try:
            lapiz = driver.find_element(
                By.CSS_SELECTOR, "li#anamnesis button[id^='anamnesis-edit-']"
            )
            return "lapiz", lapiz
        except Exception:
            pass
        # Senal 2: SIN anamnesis -> placeholder 'Agregar!'.
        try:
            agregar = driver.find_element(*agregar_btn)
            return "agregar", agregar
        except Exception:
            pass
        if not tab_hecho:
            try:
                tab = driver.find_element(*tab_atencion)
                _ = tab.location_once_scrolled_into_view
                tab.click()  # click nativo: mismo metodo del paso 3
                tab_hecho = True
                logger.info(
                    "[crear_notas] Click en pestaña 'Atención actual' del nav."
                )
            except Exception as e:
                logger.debug(f"[apertura] pestaña no disponible aun: {e}")
        _cerrar_tutorial_onboarding(driver, logger)
        _time.sleep(poll_s)
    return None


def _esperar_panel_historia_clinica(
    driver: WebDriver, logger: logging.Logger, budget_s: int, poll_s: float = 2.0
):
    """REQ-093: espera el panel de la vista 'Historia clinica'.

    El doble click aterriza en esa vista; sus senales son la tabla de
    identificacion (<th> en <tbody>), el arbol del historial (.rct-tree)
    o el card de estratificacion ECICEP (g3 sin tabla visible).
    NO entrar a 'Atencion actual': identificacion e historial se extraen
    desde AQUI (regresion 26/27-09: el waiter del editor cambiaba de
    vista antes de extraer y las notas salian sin tabla ni historial).

    Devuelve el elemento del panel, o None si no aparecio en el
    presupuesto (timeout o modal de pestañas — el caller decide).
    """
    import time as _time

    from selenium.webdriver.common.by import By

    senales = (
        "//table[.//tbody/th]",
        "//div[contains(@class,'side-card')]//*[contains(@class,'rct-tree')]",
        "//*[contains(@class, 'stratification-card')]",
    )
    fin = _time.monotonic() + budget_s
    while _time.monotonic() < fin:
        # REQ-090: bloqueo por pestañas -> salir ya para que el caller
        # libere el tablero en vez de quemar el presupuesto completo.
        if pestanas.modal_pestanas_presente(driver):
            logger.warning(
                "[apertura] Modal de pestañas durante la espera del panel."
            )
            return None
        for xp in senales:
            try:
                el = driver.find_element(By.XPATH, xp)
                if el.is_displayed():
                    return el
            except Exception:
                continue
        _time.sleep(poll_s)
    return None


def abrir_ficha_por_nombre(
    driver: WebDriver,
    logger: logging.Logger,
    paciente: PacienteObjetivo,
    entrar_atencion: bool = True,
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
        entrar_atencion: True (default, paso 8) entra a la pestaña
            'Atencion actual' y espera la senal del editor (lapiz /
            Agregar!). False (paso 3, REQ-093) se queda en la vista
            'Historia clinica' — identificacion e historial se extraen
            desde ahi y el click a 'Atencion actual' lo hace el caller
            despues de extraerlos.

    Returns:
        True si la ficha esta abierta (panel haya cargado o no);
        False si el paciente no aparecio en la tabla.
    """
    logger.info(
        f"Paciente: {paciente.nombre} | fecha={paciente.fecha} "
        f"| tipo={paciente.tipo_atencion}"
    )

    # REQ-090: si Rayen bloquea la apertura por limite de pestañas
    # (modal "Supero maximo de pestañas", conteo server-side), se
    # libera el tablero y se reintenta UNA vez. Un segundo bloqueo
    # seguido se degrada igual que un timeout de panel.
    for intento in (1, 2):
        # 1) Filtrar por fecha
        select_date(driver, logger, fecha_str=paciente.fecha)
        sort_by_estado(driver, logger)

        # 2) Buscar al paciente por nombre completo
        resultado_busqueda = _buscar_paciente_en_tabla(
            driver, logger, paciente.nombre
        )
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

        if not entrar_atencion:
            # REQ-093 (paso 3): quedarse en 'Historia clinica' — la
            # identificacion y el historial se extraen desde esta vista
            # y el click a 'Atencion actual' lo hace crear_notas AFTER.
            panel = _esperar_panel_historia_clinica(
                driver, logger, PANEL_TIMEOUT_S
            )
            if (
                panel is None
                and intento == 1
                and pestanas.modal_pestanas_presente(driver)
            ):
                logger.warning(
                    "Rayen bloqueo la apertura por limite de pestañas (REQ-090). "
                    "Liberando tablero y reintentando una vez..."
                )
                pestanas.liberar_pestanas(driver, logger)
                volver_a_pacientes_citados(driver, logger)
                continue
            if panel is None:
                logger.warning(
                    f"Panel de Historia clinica no aparecio en {PANEL_TIMEOUT_S}s. "
                    f"Extraccion procedera sobre lo que haya (flag REVISION)."
                )
                try:
                    from src.core.rutas import SCREENSHOTS_DIR

                    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
                    ruta = SCREENSHOTS_DIR / (
                        f"panel_timeout_{paciente.nombre.replace(' ', '_')}"
                        f"_{PANEL_TIMEOUT_S}s.png"
                    )
                    driver.save_screenshot(str(ruta))
                    logger.warning(f"Screenshot del timeout: {ruta.name}")
                except Exception:
                    pass
                paciente.panel_cargo = False
            else:
                logger.info(
                    f"Panel de Historia clinica cargado ({panel.tag_name})"
                )
                _cerrar_tutorial_onboarding(driver, logger)
                paciente.panel_cargo = True
            break

        # 4) Entrar a la atencion (pestaña 'Atencion actual' del nav
        #    vertical) y esperar la señal editable: lapiz (hay anamnesis) o
        #    Agregar! (sin anamnesis — se creara una nueva). Maneja el
        #    tutorial onboarding asincrono (REQ-030: sin re-click).
        senal = _entrar_atencion_y_esperar_editor(
            driver, logger, PANEL_TIMEOUT_S + 60
        )
        tipo_editor = senal[0] if senal else None

        if tipo_editor == "pestanas":
            if intento == 1:
                logger.warning(
                    "Rayen bloqueo la apertura por limite de pestañas (REQ-090). "
                    "Liberando tablero y reintentando una vez..."
                )
                pestanas.liberar_pestanas(driver, logger)
                volver_a_pacientes_citados(driver, logger)
                continue
            logger.error(
                "Rayen SIGUE bloqueado por pestañas tras liberar. "
                "Correr: python -m src.tools.cerrar_pestanas_rayen"
            )
            try:
                from src.core.rutas import SCREENSHOTS_DIR

                SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
                ruta = SCREENSHOTS_DIR / (
                    "pestanas_bloqueo_"
                    f"{paciente.nombre.replace(' ', '_')}.png"
                )
                driver.save_screenshot(str(ruta))
                logger.warning(f"Screenshot del bloqueo: {ruta.name}")
            except Exception:
                pass
            paciente.panel_cargo = False
            break

        if tipo_editor is None:
            # REQ-030: no re-clickear. Marcar flag y seguir.
            logger.warning(
                f"Senal editable (lapiz/Agregar) no aparecio en {PANEL_TIMEOUT_S + 30}s. "
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
            logger.info("Seccion anamnesis de la atencion disponible (lapiz presente)")
            paciente.panel_cargo = True
        break

    logger.info(
        f"Ficha abierta para {paciente.nombre} (URL actual: {driver.current_url})"
    )
    return True
