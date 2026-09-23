"""Tests del editor de anamnesis REAL (selectores de Yadira 2026-09-22).

Flujo: lapiz (button[id^='anamnesis-edit-']) -> click -> textarea
#historiaEnfermedad -> set por JS con eventos -> verificacion de largo.
REGLA DURA: jamas se toca el boton Guardar (REQ-073).
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from selenium.common.exceptions import TimeoutException

from src.rayen.escritura import editor_anamnesis
from src.rayen.escritura.editor_anamnesis import TipoEditor, pegar_en_editor

FICHA = "paciente femenina de 74 años, control integral g3" + chr(10) * 2 + "PLAN: ..."


class _FakeWait:
    """WebDriverWait falso con una cola de resultados compartida."""

    def __init__(self, cola: list) -> None:
        self._cola = cola

    def until(self, method):
        r = self._cola.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _con_waits(cola: list):
    """Context manager: WebDriverWait del modulo consume la cola dada."""
    return patch.object(
        editor_anamnesis, "WebDriverWait", lambda drv, t: _FakeWait(cola)
    )


def _driver() -> MagicMock:
    d = MagicMock()
    d.execute_script.return_value = len(FICHA)
    return d


# --- flujo feliz --------------------------------------------------------------


def test_pega_la_ficha_completa_en_la_historia() -> None:
    d = _driver()
    lapiz, textarea = MagicMock(), MagicMock()
    with _con_waits([lapiz, textarea]):
        r = pegar_en_editor(d, FICHA, logging.getLogger("test"))

    assert r.ok is True
    assert r.tipo_editor is TipoEditor.TEXTAREA
    assert r.caracteres_pegados == len(FICHA)
    lapiz.click.assert_called_once()
    script_args = d.execute_script.call_args.args
    assert script_args[1] is textarea
    assert script_args[2] == FICHA


def test_nunca_toca_guardar() -> None:
    """REQ-073: el flujo no busca ni clickea ningun Guardar."""
    d = _driver()
    lapiz, textarea = MagicMock(), MagicMock()
    with _con_waits([lapiz, textarea]):
        pegar_en_editor(d, FICHA, logging.getLogger("test"))
    lapiz.click.assert_called_once()
    textarea.click.assert_not_called()
    # execute_script: 1 expansion 'ver mas' + 1 pegado. Ningun Guardar:
    # guardar_editor_anamnesis NO forma parte de pegar_en_editor.
    assert d.execute_script.call_count == 2
    for llamada in d.execute_script.call_args_list:
        script = llamada.args[0]
        assert "add-header-button" not in script


# --- fallos -------------------------------------------------------------------


def test_lapiz_no_aparece() -> None:
    d = _driver()
    lapiz = MagicMock()
    with _con_waits([TimeoutException(), TimeoutException()]):
        r = pegar_en_editor(d, FICHA, logging.getLogger("test"))
    assert r.ok is False
    assert "no aparecieron" in r.motivo
    lapiz.click.assert_not_called()


def test_editor_no_aparece_tras_click() -> None:
    d = _driver()
    lapiz = MagicMock()
    with _con_waits([lapiz, TimeoutException()]):
        r = pegar_en_editor(d, FICHA, logging.getLogger("test"))
    assert r.ok is False
    assert "editor" in r.motivo.lower()
    lapiz.click.assert_called_once()


def test_verificacion_de_largo_fallida() -> None:
    d = _driver()
    lapiz, textarea = MagicMock(), MagicMock()
    d.execute_script.return_value = 10  # el campo quedo truncado
    with _con_waits([lapiz, textarea]):
        r = pegar_en_editor(d, FICHA, logging.getLogger("test"))
    assert r.ok is False
    assert "quedo con 10" in r.motivo


def test_excepcion_en_el_pegado() -> None:
    d = _driver()
    lapiz, textarea = MagicMock(), MagicMock()
    d.execute_script.side_effect = RuntimeError("JS muerto")
    with _con_waits([lapiz, textarea]):
        r = pegar_en_editor(d, FICHA, logging.getLogger("test"))
    assert r.ok is False
    assert "RuntimeError" in r.motivo


def test_expande_ver_mas_antes_de_buscar_el_lapiz() -> None:
    """Flujo real (Yadira 23-09-2026): la anamnesis viene colapsada;
    primero '...ver mas', despues el lapiz."""
    d = _driver()
    lapiz, textarea = MagicMock(), MagicMock()
    ver_mas = MagicMock()
    d.find_element.return_value = ver_mas  # el buscador de ver-mas
    with _con_waits([lapiz, textarea]):
        pegar_en_editor(d, FICHA, logging.getLogger("test"))
    # El click de expansion SI se ejecuto (por JS, al boton ver-mas).
    d.execute_script.assert_any_call("arguments[0].click();", ver_mas)
    # Y despues el lapiz abrio el editor normalmente.
    lapiz.click.assert_called_once()
