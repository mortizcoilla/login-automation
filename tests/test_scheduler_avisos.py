"""Tests del paso 9: avisos Telegram del scheduler (REQ-076).

Sin red: requests.post mockeado. Los mensajes nunca rompen la cadena.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.scheduler import avisos

_LUNES = date(2026, 9, 21)  # lunes
_MARTES = _LUNES + timedelta(days=1)


# --- eleccion y armado de mensajes -------------------------------------------


def test_inicio_rota_entre_dias() -> None:
    m_lunes = avisos.armar_mensaje_inicio(_LUNES, 3)
    m_martes = avisos.armar_mensaje_inicio(_MARTES, 3)
    assert m_lunes != m_martes, "dias distintos, mensajes distintos"


def test_inicio_mismo_dia_mismo_mensaje_y_sin_aleatorio() -> None:
    assert avisos.armar_mensaje_inicio(_LUNES, 2) == avisos.armar_mensaje_inicio(_LUNES, 2)


def test_inicio_incluye_conteo_de_pacientes() -> None:
    mensaje = avisos.armar_mensaje_inicio(_LUNES, 7)
    assert "7 pacientes" in mensaje
    assert "paciente en" not in mensaje  # plural correcto


def test_inicio_sin_conteo_no_menciona_lista() -> None:
    assert "lista" not in avisos.armar_mensaje_inicio(_LUNES, None)


def test_fin_ok_menciona_fichas_guardadas() -> None:
    mensaje = avisos.armar_mensaje_fin(ok=True, fichas_ok=4, paso_fallido=0)
    # El pool rota por fecha: todas las variantes mencionan el conteo.
    assert "4 fichas" in mensaje


def test_fin_ok_sin_dato_es_sobrio() -> None:
    mensaje = avisos.armar_mensaje_fin(ok=True, fichas_ok=None, paso_fallido=0)
    assert "terminó bien" in mensaje


def test_fin_fallo_menciona_el_paso() -> None:
    mensaje = avisos.armar_mensaje_fin(ok=False, fichas_ok=None, paso_fallido=3)
    assert "paso 3/5" in mensaje


def test_conteo_del_log_toma_el_ultimo_resumen(tmp_path: Path) -> None:
    log = tmp_path / "scheduler.log"
    log.write_text(
        "[mortadelo] === Resumen: 1/2 pacientes completos ===\n"
        "[mortadelo] === Resumen: 2/2 pacientes completos ===\n"
        "[crear_notas] Modo --todos: 5 pacientes del informe x.txt\n",
        encoding="utf-8",
    )
    assert avisos.contar_fichas_del_log(log) == (2, 2, 5)


def test_conteo_log_ausente_devuelve_none(tmp_path: Path) -> None:
    assert avisos.contar_fichas_del_log(tmp_path / "no_existe.log") is None


# --- envio -------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _env_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_RUBICITA", "token-falso")
    monkeypatch.setenv("TELEGRAM_CHAT_AVISOS", "123")


def test_envio_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"ok": True}
    with patch.object(avisos.requests, "post", return_value=resp) as mock_post:
        assert avisos.enviar("hola") is True
    cuerpo = mock_post.call_args.kwargs["json"]
    assert cuerpo["chat_id"] == "123"
    assert cuerpo["text"] == "hola"


def test_envio_error_http_devuelve_false(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = MagicMock()
    resp.status_code = 400
    resp.json.return_value = {"ok": False, "description": "chat not found"}
    with patch.object(avisos.requests, "post", return_value=resp):
        assert avisos.enviar("hola") is False


def test_envio_excepcion_devuelve_false_sin_romper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with patch.object(
        avisos.requests, "post", side_effect=avisos.requests.RequestException("red")
    ):
        assert avisos.enviar("hola") is False


def test_envio_sin_config_devuelve_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_CHAT_AVISOS")
    with patch.object(avisos.requests, "post") as mock_post:
        assert avisos.enviar("hola") is False
    mock_post.assert_not_called()


# --- REQ-080: saludo matutino y aviso de fichas abiertas ---------------------


def test_saludo_matutino_rotativo_y_determinista() -> None:
    a = avisos.armar_saludo_matutino(_LUNES)
    b = avisos.armar_saludo_matutino(_LUNES)
    assert a == b  # mismo dia, mismo saludo
    c = avisos.armar_saludo_matutino(_MARTES)
    assert c != a  # otro dia, otro saludo


def test_aviso_fichas_abiertas_formato_pedido() -> None:
    distribucion = [
        ("Morbilidad telefonica", 5),
        ("Control integral ecicep-g3", 4),
        ("Control cronico descompensado", 2),
        ("Ingreso integral ecicep-g3", 1),
    ]
    mensaje = avisos.armar_aviso_fichas_abiertas(12, distribucion)
    assert "TOTAL FICHAS ABIERTAS:12" in mensaje
    assert "Distribucion por tipo de atencion:" in mensaje
    for tipo, _ in distribucion:
        assert tipo in mensaje


def test_aviso_fichas_abiertas_ordenado_por_conteo() -> None:
    distribucion = [("Tipo B", 2), ("Tipo A", 9)]
    mensaje = avisos.armar_aviso_fichas_abiertas(11, distribucion)
    pos_b = mensaje.index("Tipo B")
    pos_a = mensaje.index("Tipo A")
    assert pos_a < pos_b  # el mayor conteo primero
