"""Tests del motor OCR via CLI opencode (REQ-061). Sin red: subprocess mockeado."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.examenes import ocr_opencode
from src.examenes.ocr_opencode import OpencodeOCRError, transcribir_imagen


def _imagen(tmp_path: Path) -> Path:
    ruta = tmp_path / "foto.jpg"
    ruta.write_bytes(b"\xff\xd8 fake")
    return ruta


def _salida_opencode(texto: str) -> MagicMock:
    r = MagicMock()
    r.returncode = 0
    r.stdout = f"\x1b[0m\n> build · mimo-v2.6-flash-free\n\n{texto}\n"
    r.stderr = ""
    return r


def test_transcripcion_ok_limpia_encabezado(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ocr_opencode.shutil, "which", lambda _: "opencode")
    with patch.object(
        ocr_opencode.subprocess, "run", return_value=_salida_opencode("GLUCOSA 100 mg/dL")
    ) as mock_run:
        texto = transcribir_imagen(_imagen(tmp_path), timeout=10)

    assert texto == "GLUCOSA 100 mg/dL"
    cmd = mock_run.call_args.args[0]
    assert cmd[0:4] == ["opencode", "run", "--model", "opencode/mimo-v2.6-flash-free"]
    assert "--file" in cmd and cmd[cmd.index("--file") + 1].endswith("foto.jpg")


def test_cli_ausente_levanta_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ocr_opencode.shutil, "which", lambda _: None)
    with pytest.raises(OpencodeOCRError, match="PATH"):
        transcribir_imagen(_imagen(tmp_path))


def test_codigo_no_cero_levanta_error(tmp_path: Path) -> None:
    r = MagicMock()
    r.returncode = 1
    r.stderr = "Go usage limit exceeded"
    r.stdout = ""
    with (
        patch.object(ocr_opencode.subprocess, "run", return_value=r),
        pytest.raises(OpencodeOCRError, match="codigo 1"),
    ):
        transcribir_imagen(_imagen(tmp_path), timeout=10)


def test_timeout_levanta_error(tmp_path: Path) -> None:
    with patch.object(
        ocr_opencode.subprocess,
        "run",
        side_effect=ocr_opencode.subprocess.TimeoutExpired(cmd="opencode", timeout=5),
    ), pytest.raises(OpencodeOCRError, match="timeout"):
        transcribir_imagen(_imagen(tmp_path), timeout=5)


def test_salida_vacia_levanta_error(tmp_path: Path) -> None:
    with (
        patch.object(ocr_opencode.subprocess, "run", return_value=_salida_opencode("")),
        pytest.raises(OpencodeOCRError, match="vacia"),
    ):
        transcribir_imagen(_imagen(tmp_path), timeout=10)
