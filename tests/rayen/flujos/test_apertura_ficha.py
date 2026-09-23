"""Tests para el flujo `abrir_ficha_por_nombre` (paso 3 y paso 8).

Mockeamos el WebDriver y los helpers de Rayen (tabla, navegacion,
identificacion) para no depender de un browser real. Cubren:
- Apertura exitosa (panel cargado).
- Apertura exitosa con match parcial (setea `paciente.nombre_rayen`).
- Paciente no encontrado en la tabla -> False.
- Panel no carga en 60s -> True pero `paciente.panel_cargo=False`.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from src.notas.modelos import PacienteObjetivo
from src.rayen.flujos.apertura_ficha import (
    PANEL_TIMEOUT_S,
    abrir_ficha_por_nombre,
)


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("test_apertura_ficha")


@pytest.fixture
def paciente_exacto() -> PacienteObjetivo:
    return PacienteObjetivo(
        fecha="15-09-2026",
        nombre="Amalia Andrea Jara Irarrazabal",
        tipo_atencion="Control",
    )


def test_panel_timeout_es_60_segundos() -> None:
    """REQ-030: timeout del panel del paciente = 60s."""
    assert PANEL_TIMEOUT_S == 60


def test_apertura_exitosa_panel_carga(
    paciente_exacto: PacienteObjetivo, logger: logging.Logger
) -> None:
    fake_driver = MagicMock()
    fake_row = MagicMock()
    fake_panel = MagicMock()
    fake_panel.tag_name = "table"

    with (
        patch("src.rayen.flujos.apertura_ficha.select_date"),
        patch("src.rayen.flujos.apertura_ficha.sort_by_estado"),
        patch(
            "src.rayen.flujos.apertura_ficha._buscar_paciente_en_tabla",
            return_value=(fake_row, None),  # match exacto -> nombre_rayen=None
        ),
        patch("src.rayen.flujos.apertura_ficha._doble_click_en_paciente"),
        patch(
            "src.rayen.flujos.apertura_ficha._wait_visible",
            return_value=fake_panel,
        ),
    ):
        ok = abrir_ficha_por_nombre(fake_driver, logger, paciente_exacto)

    assert ok is True
    assert paciente_exacto.panel_cargo is True
    assert paciente_exacto.nombre_rayen is None  # match exacto


def test_apertura_con_match_parcial_guarda_nombre_rayen(
    paciente_exacto: PacienteObjetivo, logger: logging.Logger
) -> None:
    fake_driver = MagicMock()
    fake_row = MagicMock()
    fake_panel = MagicMock()
    fake_panel.tag_name = "div"

    nombre_rayen_real = "Amalia Andrea Jara Irarrázabal"  # tilde distinta

    with (
        patch("src.rayen.flujos.apertura_ficha.select_date"),
        patch("src.rayen.flujos.apertura_ficha.sort_by_estado"),
        patch(
            "src.rayen.flujos.apertura_ficha._buscar_paciente_en_tabla",
            return_value=(fake_row, nombre_rayen_real),  # match parcial
        ),
        patch("src.rayen.flujos.apertura_ficha._doble_click_en_paciente"),
        patch(
            "src.rayen.flujos.apertura_ficha._wait_visible",
            return_value=fake_panel,
        ),
    ):
        ok = abrir_ficha_por_nombre(fake_driver, logger, paciente_exacto)

    assert ok is True
    assert paciente_exacto.nombre_rayen == nombre_rayen_real


def test_paciente_no_encontrado_retorna_false(
    paciente_exacto: PacienteObjetivo, logger: logging.Logger
) -> None:
    fake_driver = MagicMock()

    with (
        patch("src.rayen.flujos.apertura_ficha.select_date"),
        patch("src.rayen.flujos.apertura_ficha.sort_by_estado"),
        patch(
            "src.rayen.flujos.apertura_ficha._buscar_paciente_en_tabla",
            return_value=None,  # sin match
        ),
        patch("src.rayen.flujos.apertura_ficha._doble_click_en_paciente") as mock_dclick,
        patch("src.rayen.flujos.apertura_ficha._wait_visible") as mock_wait,
    ):
        ok = abrir_ficha_por_nombre(fake_driver, logger, paciente_exacto)

    assert ok is False
    # No debe haber doble-click ni espera del panel si no hubo match.
    mock_dclick.assert_not_called()
    mock_wait.assert_not_called()


def test_panel_no_carga_marca_panel_cargo_false(
    paciente_exacto: PacienteObjetivo, logger: logging.Logger
) -> None:
    """REQ-030: panel no cargo en 60s -> sigue pero panel_cargo=False."""
    fake_driver = MagicMock()
    fake_row = MagicMock()

    with (
        patch("src.rayen.flujos.apertura_ficha.select_date"),
        patch("src.rayen.flujos.apertura_ficha.sort_by_estado"),
        patch(
            "src.rayen.flujos.apertura_ficha._buscar_paciente_en_tabla",
            return_value=(fake_row, None),
        ),
        patch("src.rayen.flujos.apertura_ficha._doble_click_en_paciente"),
        patch(
            "src.rayen.flujos.apertura_ficha._wait_visible",
            return_value=None,  # panel no cargo
        ) as mock_wait,
    ):
        ok = abrir_ficha_por_nombre(fake_driver, logger, paciente_exacto)

    # Apertura "completa" en el sentido de que se intento, pero el flag
    # queda en False para que el caller sepa que debe proceder con
    # precaucion (paso 3 sigue con extraccion; paso 8 aborta el pegado).
    assert ok is True
    assert paciente_exacto.panel_cargo is False
    # El esperador combinado (REQ-081) pollea con esperas cortas dentro
    # de un presupuesto total de 60s + 30s del reintento del badge.
    timeouts = [c.kwargs.get("timeout") for c in mock_wait.call_args_list]
    assert timeouts
    assert set(timeouts) <= {8, PANEL_TIMEOUT_S}
    assert len(timeouts) >= 2  # hubo al menos un reintento tras el badge


def test_apertura_delega_a_select_date_con_fecha_paciente(
    paciente_exacto: PacienteObjetivo, logger: logging.Logger
) -> None:
    fake_driver = MagicMock()
    fake_row = MagicMock()
    fake_panel = MagicMock()
    fake_panel.tag_name = "table"

    with (
        patch("src.rayen.flujos.apertura_ficha.select_date") as mock_select,
        patch("src.rayen.flujos.apertura_ficha.sort_by_estado"),
        patch(
            "src.rayen.flujos.apertura_ficha._buscar_paciente_en_tabla",
            return_value=(fake_row, None),
        ),
        patch("src.rayen.flujos.apertura_ficha._doble_click_en_paciente"),
        patch(
            "src.rayen.flujos.apertura_ficha._wait_visible",
            return_value=fake_panel,
        ),
    ):
        abrir_ficha_por_nombre(fake_driver, logger, paciente_exacto)

    # select_date debe recibir la fecha del paciente como kwarg.
    mock_select.assert_called_once_with(
        fake_driver, logger, fecha_str=paciente_exacto.fecha
    )
