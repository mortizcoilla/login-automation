"""Tests para las skills de Pancho.

Estas tests mockean el WebDriver de Selenium para no necesitar un browser
real. Cubren:
- Wrapper de login
- Listar iniciados y convertir filas a dataclasses
- Leer ficha
- Generación y validación del token de aprobación (CRÍTICO para seguridad)
- Rechazo del envío sin token
- Aceptación del token válido (luego NotImplementedError porque es stub)
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import WebDriverException

from src import pancho_skills
from src.pancho_skills.enviar import TokenInvalidoError, enviar_ficha
from src.pancho_skills.leer_ficha import FichaDetalle, leer_ficha
from src.pancho_skills.listar_iniciados import PacienteIniciado, listar_iniciados
from src.queue_store import (
    crear_ficha,
    generar_token,
    inicializar_db,
    validar_y_consumir_token,
)


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("test_pancho")


@pytest.fixture
def fake_creds() -> dict[str, str]:
    return {"location": "cesfam", "username": "user", "password": "pass"}


@pytest.fixture
def db_path_token(tmp_path):
    path = tmp_path / "tokens.db"
    inicializar_db(path)
    return path


def test_login_rayen_delega_a_browser_automation(fake_creds, logger) -> None:
    fake_driver = MagicMock()
    with patch("src.pancho_skills.login.run_login", return_value=fake_driver) as mock_login:
        result = pancho_skills.login_rayen(fake_creds, logger, headless=True)
    assert result is fake_driver
    mock_login.assert_called_once_with(fake_creds, logger, headless=True)


def test_login_rayen_propaga_errores(fake_creds, logger) -> None:
    with patch(
        "src.pancho_skills.login.run_login",
        side_effect=WebDriverException("chrome died"),
    ):
        with pytest.raises(WebDriverException, match="chrome died"):
            pancho_skills.login_rayen(fake_creds, logger)


def test_listar_iniciados_retorna_dataclasses(logger) -> None:
    fake_driver = MagicMock()
    fake_row = MagicMock()
    with (
        patch("src.pancho_skills.listar_iniciados.ensure_session_alive", return_value=True),
        patch("src.pancho_skills.listar_iniciados.select_date"),
        patch("src.pancho_skills.listar_iniciados.sort_by_estado"),
        patch(
            "src.pancho_skills.listar_iniciados.get_pacientes_iniciados",
            return_value=[fake_row],
        ),
        patch(
            "src.pancho_skills.listar_iniciados.extraer_datos_fila",
            return_value={
                "hora": "10:30",
                "estado": "Iniciado",
                "nombre": "Juan Pérez",
                "tipo_cupo": "Normal",
                "llegada": "10:00",
                "llamada": "10:25",
                "razon": "Control",
                "tipo_atencion": "ME, Control Crónico",
                "adjunto": "Dr. Smith",
            },
        ),
    ):
        result = listar_iniciados(fake_driver, logger, fecha="23-07-2026")

    assert len(result) == 1
    p = result[0]
    assert isinstance(p, PacienteIniciado)
    assert p.nombre == "Juan Pérez"
    assert p.tipo_atencion == "Control Crónico"  # sanitizado
    assert p.tipo_atencion_raw == "ME, Control Crónico"  # original
    assert p.razon == "Control"


def test_listar_iniciados_sin_fichas_retorna_lista_vacia(logger) -> None:
    fake_driver = MagicMock()
    with (
        patch("src.pancho_skills.listar_iniciados.ensure_session_alive", return_value=True),
        patch("src.pancho_skills.listar_iniciados.select_date"),
        patch("src.pancho_skills.listar_iniciados.sort_by_estado"),
        patch(
            "src.pancho_skills.listar_iniciados.get_pacientes_iniciados",
            return_value=[],
        ),
    ):
        result = listar_iniciados(fake_driver, logger, fecha="23-07-2026")
    assert result == []


def test_listar_iniciados_rechaza_si_sesion_invalida(logger) -> None:
    fake_driver = MagicMock()
    with (
        patch("src.pancho_skills.listar_iniciados.ensure_session_alive", return_value=False),
        pytest.raises(RuntimeError, match="sesión de Rayen es inválida"),
    ):
        listar_iniciados(fake_driver, logger)


def test_listar_iniciados_salta_fila_mala(logger) -> None:
    """Si una fila tiene menos celdas de las esperadas, no debe romper todo."""
    fake_driver = MagicMock()
    bad_row = MagicMock()
    good_row = MagicMock()
    with (
        patch("src.pancho_skills.listar_iniciados.ensure_session_alive", return_value=True),
        patch("src.pancho_skills.listar_iniciados.select_date"),
        patch("src.pancho_skills.listar_iniciados.sort_by_estado"),
        patch(
            "src.pancho_skills.listar_iniciados.get_pacientes_iniciados",
            return_value=[bad_row, good_row],
        ),
        patch(
            "src.pancho_skills.listar_iniciados.extraer_datos_fila",
            side_effect=[ValueError("fila con 3 celdas"), {
                "hora": "11:00", "estado": "Iniciado", "nombre": "OK",
                "tipo_cupo": "Normal", "llegada": "", "llamada": "",
                "razon": "Consulta", "tipo_atencion": "Morbilidad",
                "adjunto": "",
            }],
        ),
    ):
        result = listar_iniciados(fake_driver, logger, fecha="23-07-2026")
    assert len(result) == 1
    assert result[0].nombre == "OK"


def test_leer_ficha_devuelve_ficha_detalle(logger) -> None:
    paciente = PacienteIniciado(
        hora="10:00", estado="Iniciado", nombre="Test",
        tipo_cupo="Normal", llegada="", llamada="",
        razon="Control", tipo_atencion_raw="ME, Control", tipo_atencion="Control",
        adjunto="",
    )
    ficha = leer_ficha(paciente, logger)
    assert isinstance(ficha, FichaDetalle)
    assert ficha.paciente is paciente
    assert ficha.notas_clinicas == ""  # todavía no implementado


# === Tests de seguridad del token (CRÍTICOS) ===
# Migrados al sistema de DB de queue_store (más robusto: con audit + TTL)


def test_generar_y_validar_token_round_trip(db_path_token) -> None:
    f = crear_ficha(db_path_token, "Test", "Control", "23-07-2026")
    contenido = "PACIENTE: test\nNOTA: HTA descompensada"
    token = generar_token(db_path_token, f.id, contenido)
    assert token.id > 0
    assert token.ficha_id == f.id
    # El token se puede consumir inmediatamente con el contenido correcto
    validar_y_consumir_token(db_path_token, token.id, f.id, contenido)


def test_token_rechazado_para_otra_ficha(db_path_token) -> None:
    f1 = crear_ficha(db_path_token, "Juan", "Control", "23-07-2026")
    f2 = crear_ficha(db_path_token, "Maria", "Control", "23-07-2026")
    contenido = "x"
    token = generar_token(db_path_token, f1.id, contenido)
    with pytest.raises(TokenInvalidoError, match="no corresponde a esta ficha"):
        validar_y_consumir_token(db_path_token, token.id, f2.id, contenido)


def test_token_rechazado_para_otro_contenido(db_path_token) -> None:
    f = crear_ficha(db_path_token, "Juan", "Control", "23-07-2026")
    contenido_v1 = "primera version"
    contenido_v2 = "version modificada por la médica"
    token = generar_token(db_path_token, f.id, contenido_v1)
    with pytest.raises(TokenInvalidoError, match="no corresponde a este contenido"):
        validar_y_consumir_token(db_path_token, token.id, f.id, contenido_v2)


def test_enviar_sin_token_rechaza(db_path_token, monkeypatch) -> None:
    """El caso más crítico: alguien llama enviar con token que no existe."""
    f = crear_ficha(db_path_token, "Juan", "Control", "23-07-2026")
    # Apuntar la skill a la DB de este test (no a data/queue.db real)
    monkeypatch.setenv("LOGIN_AUTOMATION_DB", str(db_path_token))
    with pytest.raises(TokenInvalidoError):
        enviar_ficha(
            driver=MagicMock(),
            ficha_id=f.id,
            paciente_id="pac-1",
            contenido="x",
            token=99999,  # no existe
            logger=logging.getLogger("t"),
        )


def test_token_no_reutilizable(db_path_token) -> None:
    f = crear_ficha(db_path_token, "Juan", "Control", "23-07-2026")
    contenido = "x"
    token = generar_token(db_path_token, f.id, contenido)
    validar_y_consumir_token(db_path_token, token.id, f.id, contenido)
    # Segundo intento debe fallar
    with pytest.raises(TokenInvalidoError, match="ya fue utilizado"):
        validar_y_consumir_token(db_path_token, token.id, f.id, contenido)


def test_enviar_con_token_valido_pasa_validacion_pero_es_stub(db_path_token, monkeypatch) -> None:
    """Si el token es válido, la validación pasa, pero el submit real
    lanza NotImplementedError (porque el envío a Rayen es stub)."""
    f = crear_ficha(db_path_token, "Juan", "Control", "23-07-2026")
    contenido = "draft aprobado por la médica"
    token = generar_token(db_path_token, f.id, contenido)
    monkeypatch.setenv("LOGIN_AUTOMATION_DB", str(db_path_token))
    with pytest.raises(NotImplementedError, match="submit real a Rayen no está implementado"):
        enviar_ficha(
            driver=MagicMock(),
            ficha_id=f.id,
            paciente_id="pac-1",
            contenido=contenido,
            token=token.id,
            logger=logging.getLogger("t"),
        )
