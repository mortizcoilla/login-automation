from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests

from src import api_client


@pytest.fixture
def fake_config(tmp_path) -> str:
    config = {
        "url": "https://api.test/Lista/4229/FechaHoraInicio=20260529%20000000;FechaHoraTermino=20260530%20000000;IdsDeRecursos=391966",
        "method": "GET",
        "headers": {"Accept": "application/json"},
    }
    p = tmp_path / "api_config.json"
    p.write_text(__import__("json").dumps(config), encoding="utf-8")
    return str(p)


def test_load_api_config_ok(fake_config) -> None:
    cfg = api_client.load_api_config(fake_config)
    assert cfg["method"] == "GET"
    assert "Lista" in cfg["url"]


def test_load_api_config_inexistente(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        api_client.load_api_config(str(tmp_path / "no.json"))


def test_build_url_reemplaza_fechas() -> None:
    template = (
        "https://api.test/Lista/4229/"
        "FechaHoraInicio=20260529%20000000;"
        "FechaHoraTermino=20260530%20000000;"
        "IdsDeRecursos=391966"
    )
    url = api_client.build_url_for_date(template, "15-03-2026")
    assert "FechaHoraInicio=20260315%20000000" in url
    assert "FechaHoraTermino=20260315%20235959" in url
    assert "IdsDeRecursos=391966" in url


def test_build_url_invalida() -> None:
    with pytest.raises(ValueError):
        api_client.build_url_for_date("https://x", "no-es-fecha")


def test_extract_cookies() -> None:
    driver = MagicMock()
    driver.get_cookies.return_value = [
        {"name": "a", "value": "1"},
        {"name": "b", "value": "2"},
    ]
    driver.execute_script.return_value = "ua-test"
    driver.current_url = "https://x/main"
    session = api_client.build_session_from_driver(driver)
    assert session.headers["User-Agent"] == "ua-test"
    assert session.cookies.get("a") == "1"
    assert session.cookies.get("b") == "2"


def test_fetch_pacientes_exitoso(monkeypatch) -> None:
    fake_session = MagicMock()
    fake_response = MagicMock()
    fake_response.json.return_value = [{"Id": 1, "NombreUsuarioAps": "Test"}]
    fake_response.raise_for_status = MagicMock()
    fake_session.get.return_value = fake_response

    data = api_client.fetch_pacientes_for_date(
        fake_session, "https://x/FechaHoraInicio=X;FechaHoraTermino=Y", "01-01-2026"
    )
    assert data == [{"Id": 1, "NombreUsuarioAps": "Test"}]
    fake_session.get.assert_called_once()


def test_fetch_pacientes_reintenta_y_falla(monkeypatch) -> None:
    fake_session = MagicMock()
    fake_session.get.side_effect = requests.RequestException("boom")
    with pytest.raises(requests.RequestException):
        api_client.fetch_pacientes_for_date(
            fake_session,
            "https://x/FechaHoraInicio=X;FechaHoraTermino=Y",
            "01-01-2026",
            timeout=1,
        )
    assert fake_session.get.call_count == api_client.MAX_RETRIES


def test_fetch_pacientes_respuesta_no_lista(monkeypatch) -> None:
    fake_session = MagicMock()
    fake_response = MagicMock()
    fake_response.json.return_value = {"error": "no"}
    fake_response.raise_for_status = MagicMock()
    fake_session.get.return_value = fake_response
    with pytest.raises(ValueError, match="no es lista"):
        api_client.fetch_pacientes_for_date(
            fake_session, "https://x/FechaHoraInicio=X;FechaHoraTermino=Y", "01-01-2026"
        )
