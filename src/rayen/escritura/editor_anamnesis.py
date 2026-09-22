"""Pegado de la ficha generada (paso 7) en el editor de anamnesis de Rayen.

Selectores REALES, entregados por Yadira (sesion 2026-09-22, ejemplo
Rosa Davila Luengo 22-09-2026):

1. En la ficha abierta (limite: <div>Atencion actual</div> activo), el
   item de anamnesis es <li id="anamnesis" ...> y su boton de edicion
   es el lapiz: <button id="anamnesis-edit-<id>" aria-label="Modificar">.
2. El click abre el editor lateral con DOS textareas:
   - #motivoConsulta (maxlength 500): NO lo tocamos, Yadira lo escribe.
   - #historiaEnfermedad: LA ANAMNESIS. Ahi se pega la ficha generada
     (reemplaza todo el texto previo).
3. Guardar es el boton .add-header-button ("Guardar"). REGLA DURA
   (REQ-073): este modulo NUNCA lo toca. Yadira revisa y guarda ella.

Regla dura del proyecto (REQ-001): el texto pegado es la ficha que
construimos; no se interpreta ni se completa nada aqui.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC  # noqa: N812
from selenium.webdriver.support.ui import WebDriverWait


class TipoEditor(Enum):
    """Tipo de editor detectado. Hoy Rayen usa el editor de textareas."""

    DESCONOCIDO = "desconocido"
    TEXTAREA = "textarea"  # #historiaEnfermedad / #motivoConsulta
    NINGUNO = "ninguno"


@dataclass
class ResultadoPegado:
    """Resultado de un intento de pegado."""

    ok: bool
    tipo_editor: TipoEditor
    motivo: str = ""
    caracteres_pegados: int = 0


# El lapiz de la anamnesis: el id lleva sufijo numerico variable
# (anamnesis-edit-13094892), por eso el prefijo.
_LAPIZ_SELECTOR = (
    By.CSS_SELECTOR,
    "li#anamnesis button[id^='anamnesis-edit-']",
)
# Fallback por aria-label (el tooltip "Modificar"), por si el prefijo
# del id cambia en alguna version de Rayen.
_LAPIZ_ARIA = (
    By.XPATH,
    "//li[@id='anamnesis']//button[@aria-label='Modificar']",
)
_HISTORIA_SELECTOR = (By.CSS_SELECTOR, "textarea#historiaEnfermedad")
_EDITOR_TIMEOUT_S = 15

# Set + eventos: reemplaza TODO el texto (corrar y pegar) y dispara
# input/change para que el UI de Rayen reaccione (auto-height, contador).
_JS_PEGAR = """
const el = arguments[0], texto = arguments[1];
el.focus();
el.value = texto;
el.dispatchEvent(new Event('input', {bubbles: true}));
el.dispatchEvent(new Event('change', {bubbles: true}));
return el.value.length;
"""


def abrir_editor_anamnesis(
    driver: WebDriver, logger: logging.Logger, timeout: int = _EDITOR_TIMEOUT_S
) -> WebElement | None:
    """Abre el editor de anamnesis (click en el lapiz) y devuelve el
    textarea de historia. None si el lapiz o el editor no aparecen.

    NO modifica nada: solo abre el editor.
    """
    wait = WebDriverWait(driver, timeout)
    try:
        lapiz = wait.until(
            EC.element_to_be_clickable(_LAPIZ_SELECTOR)
        )
    except TimeoutException:
        try:
            lapiz = wait.until(EC.element_to_be_clickable(_LAPIZ_ARIA))
        except TimeoutException:
            logger.warning("[editor_anamnesis] lapiz de anamnesis no aparecio")
            return None
    try:
        lapiz.click()
    except Exception:
        driver.execute_script("arguments[0].click();", lapiz)

    try:
        return WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located(_HISTORIA_SELECTOR)
        )
    except TimeoutException:
        logger.warning("[editor_anamnesis] el editor (#historiaEnfermedad) no aparecio")
        return None


def pegar_en_editor(
    driver: WebDriver,
    texto: str,
    logger: logging.Logger,
    *,
    wait_timeout: int = _EDITOR_TIMEOUT_S,
) -> ResultadoPegado:
    """Abre el editor de anamnesis y reemplaza su contenido por `texto`.

    Pega SOLO en #historiaEnfermedad (la anamnesis). #motivoConsulta no
    se toca. NUNCA presiona Guardar (REQ-073): Yadira revisa y guarda.

    Returns:
        ResultadoPegado con ok=True y caracteres_pegados=len(texto) si
        el textarea quedo con el texto; ok=False y motivo detallado si
        no (lapiz/editor no aparecieron, verificacion fallida).
    """
    logger.info(f"[editor_anamnesis] pegando {len(texto)} caracteres en la anamnesis")

    textarea = abrir_editor_anamnesis(driver, logger, timeout=wait_timeout)
    if textarea is None:
        return ResultadoPegado(
            ok=False,
            tipo_editor=TipoEditor.NINGUNO,
            motivo="lapiz o editor de anamnesis no aparecieron",
            caracteres_pegados=0,
        )

    try:
        largo_final = driver.execute_script(_JS_PEGAR, textarea, texto)
    except Exception as e:
        logger.exception(f"[editor_anamnesis] fallo el pegado: {e}")
        return ResultadoPegado(
            ok=False,
            tipo_editor=TipoEditor.TEXTAREA,
            motivo=f"error pegando: {type(e).__name__}: {e}",
            caracteres_pegados=0,
        )

    if largo_final != len(texto):
        return ResultadoPegado(
            ok=False,
            tipo_editor=TipoEditor.TEXTAREA,
            motivo=f"verificacion fallo: el campo quedo con {largo_final} de {len(texto)} chars",
            caracteres_pegados=largo_final or 0,
        )

    logger.info(f"[editor_anamnesis] pegado verificado: {largo_final} chars en la anamnesis")
    return ResultadoPegado(
        ok=True,
        tipo_editor=TipoEditor.TEXTAREA,
        caracteres_pegados=largo_final,
    )
