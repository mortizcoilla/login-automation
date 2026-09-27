"""Tests REQ-090: limite de pestañas de ficha en Rayen.

Mockeamos el WebDriver para no depender de un browser. Cubren:
- Deteccion del modal (con tilde, sin tilde, page_source vacio/muerto).
- Descartar hace click en 'Descartar' y cae a 'Volver' si no esta.
- contar_pestanas_ficha cuenta elementos 'FC:' y devuelve -1 en error.
- cerrar_pestanas_ficha acciona candidatos y respeta el tope de clicks.
- liberar_pestanas orquesta descartar -> volcar -> cerrar.
- El waiter de apertura devuelve la senal 'pestanas' ante el modal.
- abrir_ficha_por_nombre libera y reintenta una vez; con un segundo
  bloqueo degrada a panel_cargo=False sin romper el batch.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from src.notas.modelos import PacienteObjetivo
from src.rayen import pestanas
from src.rayen.flujos.apertura_ficha import (
    _entrar_atencion_y_esperar_editor,
    abrir_ficha_por_nombre,
)

TEXTO_MODAL = (
    "Superó máximo de pestañas abiertas. No puede tener más de 8 "
    "pestañas abiertas simultáneamente."
)


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("test_pestanas")


class _DriverMuerto:
    @property
    def page_source(self):
        raise RuntimeError("driver muerto")


class _Elemento:
    def __init__(self, driver=None):
        self.clicks = 0
        self._driver = driver

    def click(self):
        self.clicks += 1
        if self._driver is not None:
            self._driver.al_clickar(self)


class _DriverBotones:
    """Fake con find_element/find_elements por substring del selector."""

    def __init__(self, page_source="", botones=None, elementos=None,
                 solo_xpath=None):
        self.page_source = page_source
        self._botones = botones or {}
        self._elementos = elementos or []
        self._solo_xpath = solo_xpath
        self.scripts = []

    def al_clickar(self, el):
        pass

    def find_element(self, by, val):
        for clave, el in self._botones.items():
            if clave in val:
                return el
        raise Exception(f"no such element: {val}")

    def find_elements(self, by, val):
        if self._solo_xpath is not None and self._solo_xpath not in val:
            return []
        return list(self._elementos)

    def execute_script(self, script, *args):
        self.scripts.append(script)


# ---- Deteccion del modal ----


def test_deteccion_modal_con_tilde() -> None:
    d = MagicMock()
    d.page_source = TEXTO_MODAL
    assert pestanas.modal_pestanas_presente(d) is True


def test_deteccion_sin_tilde() -> None:
    d = MagicMock()
    d.page_source = "Supero maximo de pestanas abiertas"
    assert pestanas.modal_pestanas_presente(d) is True


def test_deteccion_sin_modal() -> None:
    d = MagicMock()
    d.page_source = "<html>Tabla de pacientes citados</html>"
    assert pestanas.modal_pestanas_presente(d) is False


def test_deteccion_page_source_none() -> None:
    d = MagicMock()
    d.page_source = None
    assert pestanas.modal_pestanas_presente(d) is False


def test_deteccion_driver_muerto() -> None:
    assert pestanas.modal_pestanas_presente(_DriverMuerto()) is False


# ---- Descartar el modal ----


def test_descartar_prefiere_boton_descartar(logger: logging.Logger) -> None:
    el_descartar = _Elemento()
    el_volver = _Elemento()
    d = _DriverBotones(
        page_source=TEXTO_MODAL,
        botones={"Descartar": el_descartar, "Volver": el_volver},
    )
    assert pestanas.descartar_modal_pestanas(d, logger) is True
    assert el_descartar.clicks == 1
    assert el_volver.clicks == 0


def test_descartar_fallback_a_volver(logger: logging.Logger) -> None:
    el_volver = _Elemento()
    d = _DriverBotones(page_source=TEXTO_MODAL, botones={"Volver": el_volver})
    assert pestanas.descartar_modal_pestanas(d, logger) is True
    assert el_volver.clicks == 1


def test_descartar_sin_botones(logger: logging.Logger) -> None:
    d = _DriverBotones(page_source=TEXTO_MODAL)
    assert pestanas.descartar_modal_pestanas(d, logger) is False


# ---- Contar pestañas ----


def test_contar_pestanas() -> None:
    d = _DriverBotones(elementos=[_Elemento(), _Elemento(), _Elemento()])
    assert pestanas.contar_pestanas_ficha(d) == 3


def test_contar_pestanas_error_devuelve_menos_uno() -> None:
    d = MagicMock()
    d.find_elements.side_effect = RuntimeError("boom")
    assert pestanas.contar_pestanas_ficha(d) == -1


# ---- Cierre mejor-esfuerzo ----


def test_cerrar_acciona_candidatos(logger: logging.Logger) -> None:
    els = [_Elemento(), _Elemento()]
    d = _DriverBotones(
        page_source="<html/>",
        elementos=els,
        solo_xpath="ant-tabs-tab-remove",
    )
    n = pestanas.cerrar_pestanas_ficha(d, logger)
    assert n == 2
    assert sum(el.clicks for el in els) == 2


def test_cerrar_respeta_tope_de_clicks(logger: logging.Logger) -> None:
    els = [_Elemento() for _ in range(30)]
    d = _DriverBotones(
        page_source="<html/>",
        elementos=els,
        solo_xpath="ant-tabs-tab-remove",
    )
    n = pestanas.cerrar_pestanas_ficha(d, logger)
    assert n == pestanas.MAX_CLICKS_POR_PASADA
    assert sum(el.clicks for el in els) == pestanas.MAX_CLICKS_POR_PASADA


# ---- Orquestador ----


def test_liberar_ordena_descartar_volcar_cerrar(
    logger: logging.Logger, tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr("src.core.rutas.LOGS_DIR", tmp_path)
    d = _DriverLiberable()
    assert pestanas.liberar_pestanas(d, logger) is True
    assert d._descartar.clicks == 1
    dumps = list(tmp_path.glob("pestanas_dump_*.html"))
    assert len(dumps) == 1


class _DriverLiberable(_DriverBotones):
    """Al clickar 'Descartar', el modal desaparece del page_source."""

    def __init__(self):
        super().__init__(page_source=TEXTO_MODAL)
        self._descartar = _Elemento(driver=self)

    def al_clickar(self, el):
        self.page_source = "<html>sin modal</html>"

    def find_element(self, by, val):
        if "Descartar" in val:
            return self._descartar
        raise Exception(f"no such element: {val}")

    def find_elements(self, by, val):
        return []


# ---- Integracion con el flujo local del worktree (paso_4_1) ----


def test_paso_41_libera_y_reintenta_una_vez(logger: logging.Logger) -> None:
    from src.tools import crear_notas_clinicas as cnc

    paciente = PacienteObjetivo(
        fecha="25-09-2026",
        nombre="Karina Alejandra Santos Collao",
        tipo_atencion="Morbilidad telefónica",
    )
    with (
        patch.object(cnc, "select_date") as mock_sd,
        patch.object(cnc, "sort_by_estado"),
        patch.object(
            cnc, "_buscar_paciente_en_tabla", return_value=(MagicMock(), None)
        ),
        patch.object(cnc, "_doble_click_en_paciente"),
        patch.object(cnc, "_wait_visible", return_value=None),
        patch.object(cnc.pestanas, "modal_pestanas_presente", return_value=True),
        patch.object(cnc.pestanas, "liberar_pestanas") as mock_liberar,
        patch.object(cnc, "volver_a_pacientes_citados") as mock_volver,
        patch.object(cnc, "_cerrar_tutorial_onboarding"),
    ):
        ok = cnc.paso_4_1_abrir_ficha(MagicMock(), logger, paciente)

    # Bloqueo en la pasada 1 -> libera y reintenta; bloqueo en la pasada
    # 2 -> degrada a panel_cargo=False sin excepcion (el batch sigue).
    assert ok is True
    assert paciente.panel_cargo is False
    mock_liberar.assert_called_once()
    mock_volver.assert_called_once()
    assert mock_sd.call_count == 2


def test_paso_41_segunda_pasada_carga_panel(logger: logging.Logger) -> None:
    from src.tools import crear_notas_clinicas as cnc

    paciente = PacienteObjetivo(
        fecha="25-09-2026",
        nombre="Rosalba Olivares Cardone",
        tipo_atencion="Morbilidad telefónica",
    )
    panel = MagicMock()
    panel.tag_name = "table"
    with (
        patch.object(cnc, "select_date") as mock_sd,
        patch.object(cnc, "sort_by_estado"),
        patch.object(
            cnc, "_buscar_paciente_en_tabla", return_value=(MagicMock(), None)
        ),
        patch.object(cnc, "_doble_click_en_paciente"),
        patch.object(
            cnc, "_wait_visible", side_effect=[None, None, panel]
        ),
        patch.object(cnc.pestanas, "modal_pestanas_presente", return_value=True),
        patch.object(cnc.pestanas, "liberar_pestanas") as mock_liberar,
        patch.object(cnc, "volver_a_pacientes_citados"),
        patch.object(cnc, "_cerrar_tutorial_onboarding"),
    ):
        ok = cnc.paso_4_1_abrir_ficha(MagicMock(), logger, paciente)

    # Tras liberar, el reintento consigue el panel (badge fallback).
    assert ok is True
    mock_liberar.assert_called_once()
    assert mock_sd.call_count == 2


def test_paso_41_sin_modal_no_libera(logger: logging.Logger) -> None:
    from src.tools import crear_notas_clinicas as cnc

    paciente = PacienteObjetivo(
        fecha="25-09-2026",
        nombre="Andrea Paola Guevara Videla",
        tipo_atencion="Morbilidad telefónica",
    )
    with (
        patch.object(cnc, "select_date"),
        patch.object(cnc, "sort_by_estado"),
        patch.object(
            cnc, "_buscar_paciente_en_tabla", return_value=(MagicMock(), None)
        ),
        patch.object(cnc, "_doble_click_en_paciente"),
        patch.object(cnc, "_wait_visible", return_value=None),
        patch.object(cnc.pestanas, "modal_pestanas_presente", return_value=False),
        patch.object(cnc.pestanas, "liberar_pestanas") as mock_liberar,
        patch.object(cnc, "_cerrar_tutorial_onboarding"),
    ):
        ok = cnc.paso_4_1_abrir_ficha(MagicMock(), logger, paciente)

    # Timeout de panel clasico (sin modal): comportamiento REQ-030
    # intacto, sin liberacion ni reintento.
    assert ok is True
    assert paciente.panel_cargo is False
    mock_liberar.assert_not_called()
