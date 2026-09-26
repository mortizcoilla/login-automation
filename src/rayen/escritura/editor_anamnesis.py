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
import re
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

# Flujo de REEMPLAZO (Yadira 24-09-2026): para cargar la ficha completa,
# la anamnesis vieja (incompleta) se DESCARTA y se escribe la nueva.
# Basura (trash): button anamnesis-delete-* con aria-label "Descartar";
# el dialogo de confirmacion pide confirmar con el boton naranja.
_BASURA_SELECTOR = (
    By.CSS_SELECTOR,
    "li#anamnesis button[id^='anamnesis-delete-']",
)
_BASURA_ARIA = (
    By.XPATH,
    "//li[@id='anamnesis']//button[@aria-label='Descartar']",
)
_DIALOGO_CONFIRMAR = (
    By.XPATH,
    "//button[contains(@class,'orange-btn')]"
    "[normalize-space()='Descartar']",
)
# Tras descartar, la seccion muestra el placeholder con el boton
# 'Agregar!' que abre el editor vacio (Yadira 24-09-2026).
_AGREGAR_SELECTOR = (
    By.XPATH,
    "//button[contains(@class,'btn-info')][normalize-space()='Agregar!']",
)

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


def verificar_anamnesis_guardada(
    driver: WebDriver,
    logger: logging.Logger,
    esperado: str,
    timeout: int = 30,
) -> bool:
    """Verifica lo que Rayen REALLY guardo: expande ver-mas, abre el
    lapiz y compara el textarea contra `esperado` (solo lectura)."""
    import time as _time

    fin = _time.monotonic() + timeout
    while _time.monotonic() < fin:
        textarea = abrir_editor_anamnesis(driver, logger, timeout=5)
        if textarea is not None:
            contenido = str(textarea.get_attribute("value") or "")
            if contenido.strip() == esperado.strip():
                logger.info(
                    "[editor_anamnesis] verificacion post-guardado OK "
                    f"({len(contenido)} chars en Rayen)"
                )
                return True
            logger.error(
                "[editor_anamnesis] MISMATCH post-guardado: Rayen tiene "
                f"{len(contenido)} chars, esperado {len(esperado)}. "
                f"Primeros 120: {contenido[:120]!r}"
            )
            return False
        _time.sleep(2)
    logger.warning("[editor_anamnesis] no se pudo reabrir para verificar")
    return False


def descartar_anamnesis(
    driver: WebDriver,
    logger: logging.Logger,
    respaldo_existe: bool,
    timeout: int = 15,
) -> bool:
    """Descarta la anamnesis vieja (trash -> confirmar en el dialogo).

    ACCION IRREVERSIBLE en Rayen. Guardia obligatorio: `respaldo_existe`
    debe ser True (la anamnesis original respaldada en OneDrive, en
    `anam_<pac>_<fecha>.md`); si no, NO descarta y devuelve False.

    Args:
        driver: en la vista Atencion actual, con el item de anamnesis visible.
        logger: logger del caller.
        respaldo_existe: True si el respaldo de la anamnesis esta en OneDrive.
        timeout: espera del dialogo de confirmacion.

    Returns:
        True si el descarte se confirmo (dialogo atendido); False si el
        guardia freno la operacion o el dialogo no aparecio.
    """
    if not respaldo_existe:
        logger.error(
            "[editor_anamnesis] DESCARTAR bloqueado: no hay respaldo de la "
            "anamnesis en OneDrive (anam_<pac>_<fecha>.md). No se toca Rayen."
        )
        return False

    wait = WebDriverWait(driver, timeout)
    try:
        basura = wait.until(EC.presence_of_element_located(_BASURA_SELECTOR))
    except TimeoutException:
        try:
            basura = wait.until(EC.presence_of_element_located(_BASURA_ARIA))
        except TimeoutException:
            logger.warning("[editor_anamnesis] boton Descartar (basura) no aparecio")
            return False
    try:
        basura.click()
    except Exception:
        driver.execute_script("arguments[0].click();", basura)

    # Dialogo: '¿Quiere descartar permanentemente esta anamnesis?' ->
    # confirmar con el boton naranja 'Descartar'.
    try:
        confirmar = wait.until(EC.element_to_be_clickable(_DIALOGO_CONFIRMAR))
    except TimeoutException:
        logger.warning("[editor_anamnesis] el dialogo de confirmacion no aparecio")
        return False
    try:
        confirmar.click()
    except Exception:
        driver.execute_script("arguments[0].click();", confirmar)
    logger.info("[editor_anamnesis] anamnesis vieja descartada (confirmado)")
    return True


def agregar_anamnesis_nueva(
    driver: WebDriver, logger: logging.Logger, timeout: int = 20
) -> WebElement | None:
    """Click en 'Agregar!' (tras el descarte) y espera el editor vacio.

    Patron que funciona con Rayen: click NATIVO (el click por JS no
    dispara los manejadores — caso de la pestaña 'Atencion actual') +
    sondeo hasta el presupuesto. Devuelve el textarea #historiaEnfermedad
    (vacio, listo para la ficha del LLM) o None. NO pega.
    """
    import time as _time


    fin = _time.monotonic() + timeout
    clickeado = False
    while _time.monotonic() < fin:
        if not clickeado:
            try:
                boton = driver.find_element(*_AGREGAR_SELECTOR)
                _ = boton.location_once_scrolled_into_view
                boton.click()  # nativo
                clickeado = True
                logger.info("[editor_anamnesis] 'Agregar!' clickeado (nativo)")
            except Exception as e:
                logger.debug(f"[editor_anamnesis] 'Agregar!' no disponible: {e}")
        else:
            try:
                ta = driver.find_element(*_HISTORIA_SELECTOR)
                logger.info("[editor_anamnesis] editor abierto tras 'Agregar!'")
                return ta
            except Exception:
                pass
        _time.sleep(1)
    logger.warning("[editor_anamnesis] 'Agregar!' o el editor no aparecieron")
    try:
        from src.core.rutas import LOGS_DIR as _LD

        _LD.mkdir(parents=True, exist_ok=True)
        driver.switch_to.default_content()
        (_LD / "agregar_sin_editor.html").write_text(
            driver.page_source, encoding="utf-8"
        )
    except Exception:
        pass
    return None


_MOTIVO_SELECTOR = (By.CSS_SELECTOR, "textarea#motivoConsulta")
_ETAPA_SELECTOR = (By.CSS_SELECTOR, "select#etapa")

_JS_SET = """
const el = arguments[0], valor = arguments[1];
el.focus();
const proto = el.tagName === 'TEXTAREA'
  ? window.HTMLTextAreaElement.prototype
  : (el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype);
const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
setter.call(el, valor);
el.dispatchEvent(new Event('input', {bubbles: true}));
el.dispatchEvent(new Event('change', {bubbles: true}));
return String(el.value).length;
"""


def _motivo_de_ficha(ficha: str) -> str:
    """'> **Motivo de atencion:** X' (primera linea de la ficha) -> X."""
    lineas = ficha.splitlines() if ficha else []
    if not lineas or not lineas[0].strip().startswith(">"):
        return ""
    m = re.match(
        r"^>\s*\*\*Motivo de atenci[oó]n:\*\*\s*(.+)$",
        lineas[0].strip(),
        re.IGNORECASE,
    )
    texto = m.group(1).strip() if m else lineas[0].lstrip("> ").strip()
    return texto[:500]  # maxlength del campo


def _historia_de_ficha(ficha: str) -> str:
    """La ficha SIN la primera linea del motivo (va en su campo propio)."""
    lineas = ficha.splitlines() if ficha else []
    if lineas and lineas[0].strip().startswith(">"):
        return "\n".join(lineas[1:]).strip()
    return ficha.strip()


def _etapa_de_ficha(ficha: str) -> str:
    """Ciclo vital femenino segun palabras de la ficha; default No Aplica."""
    norm = re.sub(r"\s+", " ", ficha.lower())
    norm = "".join(
        c for c in norm if c not in "áéíóú"
    )  # quitar tildes para matchear
    pares = [
        ("embarazada primigesta", "2"),
        ("embarazada", "3"),
        ("puerpera", "4"),
        ("climaterica", "5"),
        ("no gestante", "1"),
    ]
    for palabra, valor in pares:
        if palabra in norm:
            return valor
    return "0"  # No Aplica


def llenar_editor_nuevo(
    driver: WebDriver, logger: logging.Logger, ficha: str, timeout: int = 45
) -> bool:
    """Llena el editor nuevo: motivo + ciclo vital + historia (ficha).

    - #motivoConsulta <- el motivo de la primera linea de la ficha.
    - #etapa <- Ciclo vital femenino detectado en la ficha (default:
      No Aplica; Yadira lo revisa en el informe de trazabilidad).
    - #historiaEnfermedad <- la ficha completa (sin la linea del motivo).

    Returns:
        True si los tres campos quedaron seteados con verificacion.
    """
    motivo = _motivo_de_ficha(ficha)
    historia = _historia_de_ficha(ficha)
    etapa = _etapa_de_ficha(ficha)
    logger.info(
        f"[editor_anamnesis] llenando editor nuevo: motivo={motivo!r} "
        f"({len(motivo)} chars) | etapa={etapa} | historia={len(historia)} chars"
    )

    # Patron que funciona con Rayen (mismo de lapiz/Agregar!/pestaña):
    # SONDEO con find_element directo — el WebDriverWait+presence falla
    # intermitentemente con campos visibles (caso Juan Carlos 26-09:
    # la usuaria los vio en pantalla mientras el wait agotaba).
    driver.switch_to.default_content()  # por si un paso anterior quedo en un frame
    import time as _time

    fin = _time.monotonic() + timeout
    campos = None
    while _time.monotonic() < fin:
        try:
            campos = (
                driver.find_element(*_MOTIVO_SELECTOR),
                driver.find_element(*_ETAPA_SELECTOR),
                driver.find_element(*_HISTORIA_SELECTOR),
            )
            break
        except Exception:
            _time.sleep(1)
    if campos is None:
        logger.warning("[editor_anamnesis] campos del editor no aparecieron")
        try:
            from src.core.rutas import SCREENSHOTS_DIR as _SS

            _SS.mkdir(parents=True, exist_ok=True)
            driver.save_screenshot(str(_SS / "editor_sin_campos.png"))
        except Exception:
            pass
        try:
            from src.core.rutas import LOGS_DIR as _LD

            _LD.mkdir(parents=True, exist_ok=True)
            driver.switch_to.default_content()
            (_LD / "editor_sin_campos.html").write_text(
                driver.page_source, encoding="utf-8"
            )
        except Exception:
            pass
        return False
    campo_motivo, campo_etapa, campo_historia = campos

    import time as _time

    def _set_y_verificar(campo, valor, nombre):
        """Setea y re-lee; si el framework pisa el valor, reintenta."""
        for intento in range(1, 4):
            try:
                driver.execute_script(_JS_SET, campo, valor)
            except Exception as e:
                logger.exception(f"[editor_anamnesis] fallo seteando {nombre}: {e}")
                return False
            _time.sleep(0.5)
            actual = str(campo.get_attribute("value") or "")
            if actual == valor:
                logger.info(
                    f"[editor_anamnesis] {nombre} verificado "
                    f"({len(valor)} chars, intento {intento})"
                )
                return True
            logger.warning(
                f"[editor_anamnesis] {nombre} quedo con {len(actual)} de "
                f"{len(valor)} chars (intento {intento}); re-seteando"
            )
        return False

    try:
        if not _set_y_verificar(campo_motivo, motivo, "motivo"):
            return False
        if not _set_y_verificar(campo_etapa, etapa, "etapa"):
            return False
        if not _set_y_verificar(campo_historia, historia, "historia"):
            return False
    except Exception as e:
        logger.exception(f"[editor_anamnesis] fallo llenando el editor: {e}")
        return False
    logger.info("[editor_anamnesis] editor nuevo llenado y verificado")
    return True


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
