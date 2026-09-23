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
_GUARDAR_SELECTOR = (By.CSS_SELECTOR, "button.add-header-button")
# Flujo real entregado por Yadira (23-09-2026): la anamnesis aparece
# COLAPSADA; primero se expande con "...ver mas" y recien entonces el
# lapiz abre el editor. Sin este paso el lapiz no esta disponible.
_VER_MAS_ANAMNESIS = (
    By.XPATH,
    "//li[@id='anamnesis']//div[contains(@class,'textoverflow-button')]",
)
_VER_MAS_GENERICO = (
    By.XPATH,
    "//div[contains(@class,'textoverflow-button')]"
    "[contains(normalize-space(.), 'ver más') or contains(normalize-space(.), 'ver mas')]",
)
_EDITOR_TIMEOUT_S = 30

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


def _expandir_ver_mas(driver: WebDriver, logger: logging.Logger, timeout: int) -> None:
    """Paso 1 del flujo real: expandir la anamnesis colapsada.

    Click en '...ver mas' (el de la anamnesis; si no esta, el primero
    de la pagina). Tolerante: si no hay boton colapsado, no pasa nada —
    la seccion ya puede estar expandida.
    """
    import time as _time


    intentos = max(3, timeout // 10)
    for _ in range(intentos):
        for selector in (_VER_MAS_ANAMNESIS, _VER_MAS_GENERICO):
            try:
                boton = driver.find_element(*selector)
            except Exception:
                continue
            try:
                driver.execute_script("arguments[0].click();", boton)
                logger.info("[editor_anamnesis] '...ver más' expandido")
            except Exception:
                pass
            return
        _time.sleep(1)
    logger.info("[editor_anamnesis] sin '...ver más' (seccion ya expandida)")


def abrir_editor_anamnesis(
    driver: WebDriver, logger: logging.Logger, timeout: int = _EDITOR_TIMEOUT_S
) -> WebElement | None:
    """Abre el editor de anamnesis y devuelve el textarea de historia.

    Flujo real (Yadira 23-09-2026): expandir '...ver mas' -> click en
    el lapiz -> el editor despliega #historiaEnfermedad.
    None si el lapiz o el editor no aparecen. NO pega nada.
    """
    _expandir_ver_mas(driver, logger, timeout)
    wait = WebDriverWait(driver, timeout)
    try:
        # PRESENCIA (no clickeable): el lapiz vive dentro de la seccion
        # colapsada y Selenium no lo ve como clicable; el click por JS
        # funciona igual (caso Natalie 23-09).
        lapiz = wait.until(
            EC.presence_of_element_located(_LAPIZ_SELECTOR)
        )
    except TimeoutException:
        try:
            lapiz = wait.until(EC.presence_of_element_located(_LAPIZ_ARIA))
        except TimeoutException:
            logger.warning("[editor_anamnesis] lapiz de anamnesis no aparecio")
            try:
                from selenium.webdriver.common.by import By

                from src.core.rutas import LOGS_DIR as _LD

                _LD.mkdir(parents=True, exist_ok=True)
                driver.switch_to.default_content()
                (_LD / "editor_sin_lapiz.html").write_text(
                    driver.page_source, encoding="utf-8"
                )
                for j, frame in enumerate(driver.find_elements(By.XPATH, "//iframe")):
                    try:
                        driver.switch_to.frame(frame)
                        (_LD / f"editor_sin_lapiz_frame_{j}.html").write_text(
                            driver.page_source, encoding="utf-8"
                        )
                    except Exception:
                        continue
                    finally:
                        driver.switch_to.default_content()
            except Exception:
                pass
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


def guardar_editor_anamnesis(
    driver: WebDriver, logger: logging.Logger, timeout: int = 10
) -> bool:
    """Presiona Guardar en el editor y espera su cierre.

    REQ-073 revisada (decision de la usuaria 23-09-2026): el guardado es
    automatico dentro del flujo del paso 8. Si el editor no cierra tras
    el click, devuelve False (el paciente queda como error).
    """
    wait = WebDriverWait(driver, timeout)
    try:
        boton = wait.until(EC.element_to_be_clickable(_GUARDAR_SELECTOR))
    except TimeoutException:
        logger.warning("[editor_anamnesis] boton Guardar no aparecio")
        return False
    try:
        boton.click()
    except Exception:
        driver.execute_script("arguments[0].click();", boton)
    try:
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located(_HISTORIA_SELECTOR)
        )
    except TimeoutException:
        logger.warning("[editor_anamnesis] el editor no cerro tras Guardar")
        return False
    logger.info("[editor_anamnesis] Guardar OK (editor cerrado)")
    return True


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
