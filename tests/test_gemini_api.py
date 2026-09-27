"""Tests del cliente Gemini para OCR de examenes (REQ-061).

Sin red real: requests.post mockeado en el namespace del modulo.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.examenes import gemini_api
from src.examenes.gemini_api import GeminiAPIError, transcribir_imagen


def _imagen(tmp_path: Path) -> Path:
    ruta = tmp_path / "foto.jpg"
    ruta.write_bytes(b"\xff\xd8 fake")
    return ruta


def test_api_key_faltante_levanta_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(GeminiAPIError, match="GEMINI_API_KEY"):
        transcribir_imagen(_imagen(tmp_path))


def _respuesta_ok(texto: str = "Hemograma: leucocitos 7.000") -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": texto}]}}]
    }
    return resp


def test_transcripcion_exitosa(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key-falsa")
    monkeypatch.delenv("GEMINI_OCR_MODEL", raising=False)
    with patch.object(gemini_api.requests, "post", return_value=_respuesta_ok()) as mock_post:
        texto = transcribir_imagen(_imagen(tmp_path))

    assert "Hemograma" in texto
    url = mock_post.call_args.args[0]
    assert ":generateContent" in url
    assert gemini_api.DEFAULT_MODEL in url
    cuerpo = mock_post.call_args.kwargs["json"]
    partes = cuerpo["contents"][0]["parts"]
    assert "Transcribe fielmente" in partes[0]["text"], "prompt de transcripcion fiel"
    assert partes[1]["inline_data"]["mime_type"] == "image/jpeg"
    assert mock_post.call_args.kwargs["headers"]["x-goog-api-key"] == "key-falsa"


def test_error_http_levanta_excepcion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key-falsa")
    resp = MagicMock()
    resp.status_code = 429
    resp.text = "quota exceeded"
    with (
        patch.object(gemini_api.requests, "post", return_value=resp),
        pytest.raises(GeminiAPIError, match="429"),
    ):
        transcribir_imagen(_imagen(tmp_path))


def test_respuesta_malformada_levanta_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key-falsa")
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"candidates": []}
    with (
        patch.object(gemini_api.requests, "post", return_value=resp),
        pytest.raises(GeminiAPIError, match="malformada"),
    ):
        transcribir_imagen(_imagen(tmp_path))


def test_transcripcion_vacia_levanta_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "key-falsa")
    with (
        patch.object(gemini_api.requests, "post", return_value=_respuesta_ok("   ")),
        pytest.raises(GeminiAPIError, match="vacia"),
    ):
        transcribir_imagen(_imagen(tmp_path))


def test_selector_de_motor_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.telegram_bot.services import consolidar_service

    monkeypatch.delenv("OCR_ENGINE", raising=False)
    assert consolidar_service._transcriptor_default() is consolidar_service._opencode
    monkeypatch.setenv("OCR_ENGINE", "gemini")
    assert consolidar_service._transcriptor_default() is consolidar_service._gemini
    monkeypatch.setenv("OCR_ENGINE", "zai")
    assert consolidar_service._transcriptor_default() is consolidar_service._zai
    monkeypatch.setenv("OCR_ENGINE", "motor-extrano")
    assert consolidar_service._transcriptor_default() is consolidar_service._opencode
