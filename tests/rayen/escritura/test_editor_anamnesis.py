"""Tests para la capa de escritura en Rayen (paso 8 / cargar_ficha).

Estado actual: stub. Los pegadores especificos lanzan
NotImplementedError hasta que Yadira entregue el selector concreto
del campo de anamnesis en Rayen. Cubrimos:

- Deteccion de tipo de editor (heuristica sobre selectores candidatos).
- `pegar_en_editor` cuando NO hay editor visible -> ResultadoPegado.ok=False.
- `pegar_en_editor` cuando el pegador especifico es un NotImplementedError
  -> ResultadoPegado.ok=False con motivo "pendiente selector".
- `pegar_en_editor` cuando el pegador tiene exito -> ResultadoPegado.ok=True
  con caracteres_pegados correcto.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from src.rayen.escritura.editor_anamnesis import (
    ResultadoPegado,
    TipoEditor,
    detectar_tipo_editor,
    pegar_en_editor,
)


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("test_editor_anamnesis")


# ---------------------------------------------------------------------------
# detectar_tipo_editor
# ---------------------------------------------------------------------------


def test_detectar_textarea_por_id(logger: logging.Logger) -> None:
    fake_driver = MagicMock()
    fake_driver.find_elements.return_value = [MagicMock()]
    with patch(
        "src.rayen.escritura.editor_anamnesis._by_string",
        return_value="css",  # cualquier by funciona para find_elements
    ):
        tipo = detectar_tipo_editor(fake_driver, logger)
    assert tipo == TipoEditor.TEXTAREA


def test_detectar_contenteditable_si_no_hay_textarea(logger: logging.Logger) -> None:
    fake_driver = MagicMock()
    # 9 selectores candidatos. Los 3 nuevos del <div>Atencion actual
    # no matchean (Rayen simulado sin div), los 3 textarea fallback
    # tampoco, y el primer contenteditable (selector 7) matchea.
    fake_driver.find_elements.side_effect = [
        [],  # 1. textarea xpath (siguiendo Atencion actual)
        [],  # 2. contenteditable xpath (siguiendo Atencion actual)
        [],  # 3. textarea xpath (ancestro de Atencion actual)
        [],  # 4. textarea#anamnesis
        [],  # 5. textarea[name='anamnesis']
        [],  # 6. textarea[name*='anamnesis' i]
        [MagicMock()],  # 7. div[contenteditable='true']
        [],  # 8. iframe.cke_wysiwyg_frame
        [],  # 9. iframe#mce_0_ifr
    ]
    tipo = detectar_tipo_editor(fake_driver, logger)
    assert tipo == TipoEditor.CONTENTEDITABLE


def test_detectar_ninguno_si_no_matchea_nada(logger: logging.Logger) -> None:
    fake_driver = MagicMock()
    fake_driver.find_elements.return_value = []
    tipo = detectar_tipo_editor(fake_driver, logger)
    assert tipo == TipoEditor.NINGUNO


def test_detectar_no_falla_si_find_elements_explota(logger: logging.Logger) -> None:
    """Robustez: un find_elements que rompe no debe tumbar el detector."""
    fake_driver = MagicMock()
    fake_driver.find_elements.side_effect = [
        Exception("driver died"),
    ] * 9  # 9 selectores candidatos
    tipo = detectar_tipo_editor(fake_driver, logger)
    assert tipo == TipoEditor.NINGUNO


# ---------------------------------------------------------------------------
# pegar_en_editor
# ---------------------------------------------------------------------------


def test_pegar_en_editor_timeout_sin_editor_visible(
    logger: logging.Logger,
) -> None:
    """Si no aparece editor en `wait_timeout` -> ResultadoPegado.ok=False."""
    fake_driver = MagicMock()

    # detectar_tipo_editor devuelve NINGUNO en cada llamada que hace
    # el wait.until(...). El wait nunca se cumple -> TimeoutException.
    with patch(
        "src.rayen.escritura.editor_anamnesis.detectar_tipo_editor",
        return_value=TipoEditor.NINGUNO,
    ):
        resultado = pegar_en_editor(
            fake_driver,
            "contenido de prueba",
            logger,
            wait_timeout=1,
        )

    assert isinstance(resultado, ResultadoPegado)
    assert resultado.ok is False
    assert resultado.tipo_editor == TipoEditor.NINGUNO
    assert "timeout" in resultado.motivo


def test_pegar_en_editor_devuelve_pendiente_selector_si_pegador_no_implementado(
    logger: logging.Logger,
) -> None:
    """Si el pegador especifico lanza NotImplementedError -> ok=False
    con motivo 'pendiente selector'."""
    fake_driver = MagicMock()

    with patch(
        "src.rayen.escritura.editor_anamnesis.detectar_tipo_editor",
        return_value=TipoEditor.TEXTAREA,
    ), patch(
        "src.rayen.escritura.editor_anamnesis.pegar_en_textarea",
        side_effect=NotImplementedError("pegar_en_textarea: pendiente selector"),
    ):
        resultado = pegar_en_editor(
            fake_driver, "contenido", logger, wait_timeout=1
        )

    assert resultado.ok is False
    assert resultado.tipo_editor == TipoEditor.TEXTAREA
    assert "pendiente selector" in resultado.motivo
    assert resultado.caracteres_pegados == 0


def test_pegar_en_editor_exitoso_devuelve_ok_con_caracteres(
    logger: logging.Logger,
) -> None:
    fake_driver = MagicMock()
    texto = "x" * 1234

    with patch(
        "src.rayen.escritura.editor_anamnesis.detectar_tipo_editor",
        return_value=TipoEditor.TEXTAREA,
    ), patch(
        "src.rayen.escritura.editor_anamnesis.pegar_en_textarea",
        return_value=ResultadoPegado(
            ok=True,
            tipo_editor=TipoEditor.TEXTAREA,
            caracteres_pegados=1234,
        ),
    ):
        resultado = pegar_en_editor(
            fake_driver, texto, logger, wait_timeout=1
        )

    assert resultado.ok is True
    assert resultado.tipo_editor == TipoEditor.TEXTAREA
    assert resultado.caracteres_pegados == 1234


def test_pegar_en_editor_con_pegador_que_falla_inesperadamente(
    logger: logging.Logger,
) -> None:
    """Si el pegador lanza una excepcion NO controlada -> ok=False
    con la excepcion en motivo."""
    fake_driver = MagicMock()

    with patch(
        "src.rayen.escritura.editor_anamnesis.detectar_tipo_editor",
        return_value=TipoEditor.TEXTAREA,
    ), patch(
        "src.rayen.escritura.editor_anamnesis.pegar_en_textarea",
        side_effect=RuntimeError("chrome died"),
    ):
        resultado = pegar_en_editor(
            fake_driver, "texto", logger, wait_timeout=1
        )

    assert resultado.ok is False
    assert resultado.tipo_editor == TipoEditor.TEXTAREA
    assert "RuntimeError" in resultado.motivo
    assert "chrome died" in resultado.motivo


def test_pegar_en_editor_con_tipo_contenteditable_delega_al_pegador_esperado(
    logger: logging.Logger,
) -> None:
    fake_driver = MagicMock()

    with patch(
        "src.rayen.escritura.editor_anamnesis.detectar_tipo_editor",
        return_value=TipoEditor.CONTENTEDITABLE,
    ), patch(
        "src.rayen.escritura.editor_anamnesis.pegar_en_contenteditable",
        return_value=ResultadoPegado(
            ok=True,
            tipo_editor=TipoEditor.CONTENTEDITABLE,
            caracteres_pegados=10,
        ),
    ) as mock_peg:
        resultado = pegar_en_editor(
            fake_driver, "0123456789", logger, wait_timeout=1
        )

    assert resultado.ok is True
    assert resultado.tipo_editor == TipoEditor.CONTENTEDITABLE
    mock_peg.assert_called_once_with(fake_driver, "0123456789", logger)
