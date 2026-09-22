"""Pegado de la ficha generada (paso 7) en el editor interno de Rayen.

Sesion 2026-09-21 (paso 8 / cargar_ficha): esta capa es la primera del
proyecto que ESCRIBE en Rayen (todos los `src.rayen.extraccion.*` solo
leen). Por lo tanto, los selectores y la mecanica del pegado son
NUEVOS y dependen del UI concreto de Rayen que Yadira nos indique.

Estado actual: stub. La funcion publica `pegar_en_editor()` detecta el
tipo de editor y delega a un pegador especifico. Los pegadores
especificos estan todos en `NotImplementedError` con un mensaje claro
de que Yadira debe entregar el selector.

Regla dura del proyecto (mantener en cualquier implementacion futura):
- NUNCA auto-enviar. La aprobacion humana es de Yadira: el script
  pega el texto y se detiene; Yadira revisa visualmente y aprieta
  Guardar ella misma.

Convencion de retorno:
- `ResultadoPegado.ok = True`  -> el texto quedo en el campo del editor.
- `ResultadoPegado.ok = False` -> fallo (selector no encontrado, etc.).
  `motivo` tiene detalle para que `cargar_ficha.main()` lo registre en
  la trazabilidad.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait


class TipoEditor(Enum):
    """Tipo de editor que Rayen esta mostrando para el campo de anamnesis."""

    DESCONOCIDO = "desconocido"
    TEXTAREA = "textarea"  # <textarea name=...>
    CONTENTEDITABLE = "contenteditable"  # <div contenteditable="true">
    CKEDITOR = "ckeditor"  # iframe + CKEditor (versiones viejas)
    TINYMCE = "tinymce"  # iframe + TinyMCE
    NINGUNO = "ninguno"  # no se encontro campo de anamnesis


@dataclass
class ResultadoPegado:
    """Resultado de un intento de pegado."""

    ok: bool
    tipo_editor: TipoEditor
    motivo: str = ""
    caracteres_pegados: int = 0


# Selectores candidatos para el campo donde se escribe la anamnesis /
# atencion. Sesion 2026-09-21 con Yadira: el limite del flujo
# compartido es el <div>Atencion actual</div>; el editor donde se pega
# la ficha generada esta ASOCIADO a ese div (es el campo de evolucion
# / atencion actual que Yadira usa para escribir la nota del dia).
#
# El orden refleja la probabilidad:
# 1. Textarea hermano del <div>Atencion actual</div> (caso normal).
# 2. ContentEditable hermano del div.
# 3. Textarea plano (caso fallback, versiones viejas).
# 4. CKEditor / TinyMCE (versiones legacy con iframe).
#
# Cuando Yadira entregue el selector exacto, este listado se reduce al
# caso real y los demas quedan como fallback comentado.
_SELECTORES_CANDIDATOS: list[tuple[TipoEditor, tuple[str, str]]] = [
    # Caso normal (sesion 2026-09-21): el campo es hermano/adyacente al
    # <div>Atencion actual</div>. Probamos varias relaciones DOM.
    (
        TipoEditor.TEXTAREA,
        (
            "xpath",
            # textarea inmediatamente siguiente al div "Atencion actual".
            "//div[normalize-space()='Atencion actual']/following::textarea[1]",
        ),
    ),
    (
        TipoEditor.CONTENTEDITABLE,
        (
            "xpath",
            # contenteditable inmediatamente siguiente al div "Atencion actual".
            "//div[normalize-space()='Atencion actual']/following::*[@contenteditable='true'][1]",
        ),
    ),
    (
        TipoEditor.TEXTAREA,
        (
            "xpath",
            # textarea hijo del contenedor padre del div.
            "//div[normalize-space()='Atencion actual']/ancestor::*[1]//textarea[1]",
        ),
    ),
    # Fallbacks por si la UI cambia o hay versiones viejas.
    (TipoEditor.TEXTAREA, ("css", "textarea#anamnesis")),
    (TipoEditor.TEXTAREA, ("css", "textarea[name='anamnesis']")),
    (TipoEditor.TEXTAREA, ("css", "textarea[name*='anamnesis' i]")),
    (TipoEditor.CONTENTEDITABLE, ("css", "div[contenteditable='true']")),
    (TipoEditor.CKEDITOR, ("css", "iframe.cke_wysiwyg_frame")),
    (TipoEditor.TINYMCE, ("css", "iframe#mce_0_ifr")),
]


def _by_string(by_str: str):
    """Resuelve el By de Selenium a partir de su nombre."""
    from selenium.webdriver.common.by import By

    return {
        "id": By.ID,
        "css": By.CSS_SELECTOR,
        "xpath": By.XPATH,
        "name": By.NAME,
        "class": By.CLASS_NAME,
    }[by_str]


def detectar_tipo_editor(driver: WebDriver, logger: logging.Logger) -> TipoEditor:
    """Inspecciona el DOM y devuelve el primer tipo de editor que matchee.

    No levanta excepciones: si ninguno matchea devuelve `NINGUNO`.
    """
    for tipo, (by_str, value) in _SELECTORES_CANDIDATOS:
        by = _by_string(by_str)
        try:
            elements = driver.find_elements(by, value)
        except Exception as e:
            logger.debug(f"[editor_anamnesis] detectar_tipo_editor: error con {by_str}={value}: {e}")
            continue
        if elements:
            logger.info(f"[editor_anamnesis] editor detectado: {tipo.value} ({by_str}={value})")
            return tipo
    logger.warning("[editor_anamnesis] no se detecto ningun editor candidato")
    return TipoEditor.NINGUNO


def pegar_en_textarea(driver: WebDriver, texto: str, logger: logging.Logger) -> ResultadoPegado:
    """Stub: pega en un <textarea> plano.

    PENDIENTE de selector concreto. Yadira debe entregar el selector
    exacto del campo de anamnesis en Rayen (id, name o css path).
    Mientras tanto, este stub lanza NotImplementedError explicito para
    que `cargar_ficha.main()` lo registre en trazabilidad.
    """
    raise NotImplementedError(
        "pegar_en_textarea: pendiente selector del campo de anamnesis en Rayen. "
        "Yadira debe confirmar el id/name/css del <textarea> donde escribe la evolucion."
    )


def pegar_en_contenteditable(driver: WebDriver, texto: str, logger: logging.Logger) -> ResultadoPegado:
    """Stub: pega en un <div contenteditable>.

    PENDIENTE de selector concreto.
    """
    raise NotImplementedError(
        "pegar_en_contenteditable: pendiente selector del campo de anamnesis en Rayen. "
        "Yadira debe confirmar el css path del <div contenteditable>."
    )


def pegar_en_ckeditor(driver: WebDriver, texto: str, logger: logging.Logger) -> ResultadoPegado:
    """Stub: pega en el iframe de CKEditor.

    PENDIENTE de selector concreto.
    """
    raise NotImplementedError(
        "pegar_en_ckeditor: pendiente selector del iframe + cuerpo del CKEditor."
    )


def pegar_en_tinymce(driver: WebDriver, texto: str, logger: logging.Logger) -> ResultadoPegado:
    """Stub: pega en el iframe de TinyMCE.

    PENDIENTE de selector concreto.
    """
    raise NotImplementedError(
        "pegar_en_tinymce: pendiente selector del iframe + cuerpo de TinyMCE."
    )


# Mapeo tipo -> nombre del pegador. Resolucion por `globals()` para
# que los tests puedan parchear `pegar_en_textarea` y otros (si
# guardasemos la referencia en el dict, el patch no surtiria efecto
# porque la referencia se captura al importar el modulo).
_PEGADORES_POR_NOMBRE: dict[TipoEditor, str] = {
    TipoEditor.TEXTAREA: "pegar_en_textarea",
    TipoEditor.CONTENTEDITABLE: "pegar_en_contenteditable",
    TipoEditor.CKEDITOR: "pegar_en_ckeditor",
    TipoEditor.TINYMCE: "pegar_en_tinymce",
}


def pegar_en_editor(
    driver: WebDriver,
    texto: str,
    logger: logging.Logger,
    *,
    wait_timeout: int = 30,
) -> ResultadoPegado:
    """Punto de entrada unico: detecta el tipo y delega al pegador especifico.

    Args:
        driver: WebDriver posicionado en la ficha del paciente, con el
            panel ya cargado.
        texto: contenido completo del archivo
            `data/fichas_generadas/ficha_<pac>_<fecha>.md` a pegar.
        logger: logger del caller.
        wait_timeout: segundos a esperar a que el editor sea visible.

    Returns:
        ResultadoPegado con `ok=True` y `caracteres_pegados=len(texto)`
        si el pegado tuvo exito; `ok=False` y `motivo` detallado si
        fallo (incluyendo el caso "selector pendiente").
    """
    logger.info(
        f"[editor_anamnesis] pegar_en_editor: {len(texto)} caracteres"
    )

    # Esperar a que el editor sea visible antes de detectarlo (Rayen a
    # veces renderiza la ficha en dos cargas).
    try:
        WebDriverWait(driver, wait_timeout).until(
            lambda d: detectar_tipo_editor(d, logger) != TipoEditor.NINGUNO
        )
    except TimeoutException:
        logger.error(
            f"[editor_anamnesis] tras {wait_timeout}s no aparecio ningun editor candidato"
        )
        return ResultadoPegado(
            ok=False,
            tipo_editor=TipoEditor.NINGUNO,
            motivo=f"timeout {wait_timeout}s sin editor visible",
            caracteres_pegados=0,
        )

    tipo = detectar_tipo_editor(driver, logger)
    if tipo == TipoEditor.NINGUNO:
        return ResultadoPegado(
            ok=False,
            tipo_editor=tipo,
            motivo="ningun editor candidato matchea",
            caracteres_pegados=0,
        )

    nombre_pegador = _PEGADORES_POR_NOMBRE[tipo]
    # globals() devuelve Any: anotamos el tipo para que mypy valide el
    # retorno de pegar_en_editor.
    pegador: Callable[[WebDriver, str, logging.Logger], ResultadoPegado] = globals()[
        nombre_pegador
    ]
    try:
        resultado = pegador(driver, texto, logger)
    except NotImplementedError as e:
        logger.error(f"[editor_anamnesis] {e}")
        return ResultadoPegado(
            ok=False,
            tipo_editor=tipo,
            motivo=str(e),
            caracteres_pegados=0,
        )
    except Exception as e:
        logger.exception(f"[editor_anamnesis] fallo inesperado en pegador {tipo.value}: {e}")
        return ResultadoPegado(
            ok=False,
            tipo_editor=tipo,
            motivo=f"excepcion {type(e).__name__}: {e}",
            caracteres_pegados=0,
        )

    return resultado
