"""Tests de la mision 2 del bot: consolidacion OCR (REQ-061).

Servicio puro con transcriptor inyectado (NUNCA API real en la suite,
REQ-047) + integracion del handler con ambos servicios mockeados.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.telegram_bot.handlers.photo import cmd_archivar
from src.telegram_bot.services.consolidar_service import consolidar_desde_telegram

PAC = "Paciente Prueba"
FECHA = "21-09-2026"


def _foto_cruda(crudos: Path, nombre: str) -> Path:
    ruta = crudos / nombre
    ruta.write_bytes(b"\xff\xd8 fake-jpeg")
    return ruta


def _transcriptor_ok(texto: str = "GLUCOSA 100 mg/dL"):
    llamadas: list[Path] = []

    def _fake(image_path: Path) -> str:
        llamadas.append(image_path)
        return texto

    return _fake, llamadas


# --- servicio ---------------------------------------------------------------


def _crudos(tmp_path: Path) -> Path:
    crudos = tmp_path / "crudos"
    crudos.mkdir()
    return crudos


def test_consolidar_dos_fotos_genera_un_md(tmp_path: Path) -> None:
    crudos = tmp_path / "crudos"
    destino = tmp_path / "examenes"
    crudos.mkdir()
    _foto_cruda(crudos, "Paciente_Prueba_1_21-09-2026.jpg")
    _foto_cruda(crudos, "Paciente_Prueba_2_21-09-2026.jpg")
    fake, llamadas = _transcriptor_ok()

    r = consolidar_desde_telegram(PAC, crudos_dir=crudos, destino_dir=destino, transcriptor=fake)

    assert r["ok"] is True
    assert r["fotos"] == 2
    assert len(llamadas) == 2
    mds = list(destino.glob("*.md"))
    assert len(mds) == 1
    contenido = mds[0].read_text(encoding="utf-8")
    assert contenido.count("## ") == 2
    assert "GLUCOSA" in contenido
    assert mds[0].name == f"exam_Paciente_Prueba_{FECHA}.md"


def test_segunda_foto_reemplaza_y_mantiene_archivo_unico(tmp_path: Path) -> None:
    crudos = tmp_path / "crudos"
    destino = tmp_path / "examenes"
    crudos.mkdir()
    _foto_cruda(crudos, "Paciente_Prueba_1_21-09-2026.jpg")
    fake, _ = _transcriptor_ok()
    consolidar_desde_telegram(PAC, crudos_dir=crudos, destino_dir=destino, transcriptor=fake)

    # Llega la segunda foto del mismo examen: re-consolidar.
    _foto_cruda(crudos, "Paciente_Prueba_2_21-09-2026.jpg")
    r2 = consolidar_desde_telegram(PAC, crudos_dir=crudos, destino_dir=destino, transcriptor=fake)

    assert r2["ok"] is True
    mds = list(destino.glob("*.md"))
    assert len(mds) == 1, "debe quedar UN unico md, sin _v2"
    assert mds[0].name == f"exam_Paciente_Prueba_{FECHA}.md", "nombre canonico"
    assert mds[0].read_text(encoding="utf-8").count("## ") == 2


def test_fallo_total_de_transcripcion_conserva_md_previo(tmp_path: Path) -> None:
    crudos = tmp_path / "crudos"
    destino = tmp_path / "examenes"
    crudos.mkdir()
    _foto_cruda(crudos, "Paciente_Prueba_1_21-09-2026.jpg")
    fake_ok, _ = _transcriptor_ok()
    consolidar_desde_telegram(PAC, crudos_dir=crudos, destino_dir=destino, transcriptor=fake_ok)
    antes = (destino / f"exam_Paciente_Prueba_{FECHA}.md").read_text(encoding="utf-8")

    def _fake_roto(image_path: Path) -> str:
        raise RuntimeError("API caida")

    r = consolidar_desde_telegram(PAC, crudos_dir=crudos, destino_dir=destino, transcriptor=_fake_roto)

    assert r["ok"] is False
    despues = (destino / f"exam_Paciente_Prueba_{FECHA}.md").read_text(encoding="utf-8")
    assert despues == antes, "el md previo no se toca si la transcripcion falla"


def test_solo_pdf_sin_fotos_imagen(tmp_path: Path) -> None:
    crudos = tmp_path / "crudos"
    destino = tmp_path / "examenes"
    crudos.mkdir()
    (crudos / f"Paciente_Prueba_1_{FECHA}.pdf").write_bytes(b"%PDF fake")

    fake, llamadas = _transcriptor_ok()
    r = consolidar_desde_telegram(PAC, crudos_dir=crudos, destino_dir=destino, transcriptor=fake)

    assert r["ok"] is False
    assert r["motivo"] == "sin_fotos_imagen"
    assert llamadas == []  # nunca llamo a la API


def test_fecha_inferida_de_los_crudos(tmp_path: Path) -> None:
    crudos = tmp_path / "crudos"
    destino = tmp_path / "examenes"
    crudos.mkdir()
    _foto_cruda(crudos, "Paciente_Prueba_1_15-09-2026.jpg")
    fake, _ = _transcriptor_ok()

    r = consolidar_desde_telegram(PAC, fecha_atencion=None, crudos_dir=crudos, destino_dir=destino, transcriptor=fake)

    assert r["ok"] is True
    assert r["fecha_resuelta"] == "15-09-2026"


# --- handler (integracion) ---------------------------------------------------


def _make_message(caption=None, photo=None, document=None):
    msg = MagicMock()
    msg.caption = caption
    msg.photo = photo
    msg.document = document
    msg.reply_text = AsyncMock()
    return msg


def _make_update(message):
    update = MagicMock()
    update.effective_message = message
    update.effective_user = MagicMock(id=1389428233, username="yadira", first_name="Y")
    return update


def _make_context():
    context = MagicMock()
    context.bot = AsyncMock()
    tg_file = MagicMock()
    tg_file.file_id = "fid"
    tg_file.download_to_drive = AsyncMock()
    context.bot.get_file.return_value = tg_file
    context.application.bot_data = {}
    return context


def _resultado_archivado() -> dict:
    return {
        "ok": True,
        "nombre": "pac_1_21-09-2026.jpg",
        "paciente_resuelto": PAC,
        "paciente_input": PAC,
        "paciente_matcheado": PAC,
        "fecha_resuelta": FECHA,
    }


def test_handler_responde_con_la_transcripcion(tmp_path: Path) -> None:
    msg = _make_message(caption=f"/archivar {PAC}", photo=[MagicMock(file_id="f1")])
    with (
        patch(
            "src.telegram_bot.handlers.photo.archivar_foto_desde_telegram",
            return_value=_resultado_archivado(),
        ),
        patch(
            "src.telegram_bot.handlers.photo.consolidar_desde_telegram",
            return_value={
                "ok": True,
                "path": str(tmp_path / f"exam_Paciente_Prueba_{FECHA}.md"),
                "fotos": 2,
            },
        ) as mock_consol,
    ):
        asyncio.run(cmd_archivar(_make_update(msg), _make_context()))

    texto = msg.reply_text.call_args[0][0]
    assert "Listo, archivado:" in texto
    assert "Examenes transcritos a:" in texto
    assert "(2 imagen/es)" in texto
    assert mock_consol.call_args.kwargs["nombre_paciente"] == PAC


def test_handler_avisa_cuando_la_consolidacion_falla(tmp_path: Path) -> None:
    msg = _make_message(caption=f"/archivar {PAC}", photo=[MagicMock(file_id="f1")])
    with (
        patch(
            "src.telegram_bot.handlers.photo.archivar_foto_desde_telegram",
            return_value=_resultado_archivado(),
        ),
        patch(
            "src.telegram_bot.handlers.photo.consolidar_desde_telegram",
            return_value={"ok": False, "error": "ZAI_API_KEY no esta configurada"},
        ),
    ):
        asyncio.run(cmd_archivar(_make_update(msg), _make_context()))

    texto = msg.reply_text.call_args[0][0]
    assert "Listo, archivado:" in texto, "el archivado NO se ve afectado"
    assert "Aviso: la transcripcion automatica no corrio" in texto
    assert "ZAI_API_KEY" in texto
