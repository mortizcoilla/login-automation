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
        # REQ-030: no re-clickear. Marcar flag y seguir.
        logger.warning(
            f"Panel no aparecio en {PANEL_TIMEOUT_S}s. "
            f"El flujo procedera sobre lo que haya. "
            f"El caller debera decidir si esto es aceptable."
        )
        paciente.panel_cargo = False
    else:
        logger.info(f"Panel del paciente cargado ({panel.tag_name})")
        paciente.panel_cargo = True

    logger.info(
        f"Ficha abierta para {paciente.nombre} (URL actual: {driver.current_url})"
    )
    return True
