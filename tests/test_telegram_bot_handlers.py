"""Tests para los handlers del bot (start, photo).

Mockeamos PTB (Update, Context, Bot) y el service `archivar_foto_desde_telegram`
para no tocar archivos reales ni Telegram.

No requieren pytest-asyncio: usamos asyncio.run() directamente.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.telegram_bot.handlers.photo import cmd_archivar
from src.telegram_bot.handlers.start import WELCOME, cmd_start

# --- helpers -------------------------------------------------------------


def _make_message(caption=None, photo=None, document=None):
    msg = MagicMock()
    msg.caption = caption
    msg.photo = photo  # list-like (Telegram envia varias resoluciones; usamos [-1])
    msg.document = document
    msg.reply_text = AsyncMock()
    return msg


def _make_update_with_message(message) -> MagicMock:
    update = MagicMock()
    update.effective_message = message
    user = MagicMock()
    user.id = 123456
    user.username = "yadira"
    user.first_name = "Yadira"
    update.effective_user = user
    return update


def _make_context_with_bot():
    """Context con bot.get_file mockeado y bot_data fresh."""
    context = MagicMock()
    context.bot = AsyncMock()
    # get_file devuelve un objeto con file_id y download_to_drive async.
    tg_file = MagicMock()
    tg_file.file_id = "fake_file_id"
    tg_file.download_to_drive = AsyncMock()
    context.bot.get_file.return_value = tg_file
    context.application.bot_data = {}
    return context


def _photo_mock(file_id="photo_fid_1"):
    p = MagicMock()
    p.file_id = file_id
    return p


# --- /start -----------------------------------------------------------


def test_cmd_start_envia_bienvenida_con_instrucciones():
    update = _make_update_with_message(_make_message())
    context = MagicMock()

    asyncio.run(cmd_start(update, context))

    reply = update.effective_message.reply_text.await_args.args[0]
    assert "Rubicita" in reply
    assert "/archivar" in reply
    assert "dd-mm-yyyy" in reply


def test_cmd_start_bienvenida_constante_no_vacia():
    """El WELCOME no debe estar vacio ni ser solo titulo."""
    assert isinstance(WELCOME, str)
    assert len(WELCOME) > 50
    assert "/archivar" in WELCOME


def test_cmd_start_sin_message_no_falla():
    """Si no hay message (edge case de canal), no debe petar."""
    update = MagicMock()
    update.effective_message = None
    update.effective_user = MagicMock(id=1, username="x", first_name="x")
    context = MagicMock()

    # No debe lanzar excepcion.
    asyncio.run(cmd_start(update, context))


# --- /archivar: parsing de caption -------------------------------------


def test_archivar_sin_caption_pide_formato():
    update = _make_update_with_message(_make_message(caption="", photo=[_photo_mock()]))
    context = _make_context_with_bot()

    asyncio.run(cmd_archivar(update, context))

    reply = update.effective_message.reply_text.await_args.args[0]
    assert "Falta el comando /archivar" in reply
    assert "/archivar" in reply


def test_archivar_sin_caption_y_sin_foto_no_intenta_descargar():
    """Sin caption ni photo: falla al parsing, NO llama a context.bot.get_file."""
    update = _make_update_with_message(_make_message(caption=None, photo=None, document=None))
    context = _make_context_with_bot()

    asyncio.run(cmd_archivar(update, context))

    # No es un caso de "solo fotos" porque ya fallo antes por caption.
    # Aceptamos uno u otro mensaje, pero NO debe haber llamado al bot.
    context.bot.get_file.assert_not_awaited()


def test_archivar_caption_mal_formado():
    update = _make_update_with_message(
        _make_message(
            caption="hola que tal",
            photo=[_photo_mock()],
        )
    )
    context = _make_context_with_bot()

    asyncio.run(cmd_archivar(update, context))

    reply = update.effective_message.reply_text.await_args.args[0]
    assert "No pude parsear" in reply


def test_archivar_fecha_invalida():
    """Fecha con dia/mes fuera de rango es capturada por la regex y luego
    rechazada por datetime.strptime. 32-13-2026 es invalido y la regex
    SI lo captura como grupo 'fecha'."""
    update = _make_update_with_message(
        _make_message(
            caption="/archivar Benedicto 32-13-2026",
            photo=[_photo_mock()],
        )
    )
    context = _make_context_with_bot()

    asyncio.run(cmd_archivar(update, context))

    reply = update.effective_message.reply_text.await_args.args[0]
    assert "Fecha invalida" in reply


def test_archivar_fecha_valida_pasa_a_service():
    update = _make_update_with_message(
        _make_message(
            caption="/archivar Benedicto Martin 16-09-2026",
            photo=[_photo_mock()],
        )
    )
    context = _make_context_with_bot()

    resultado = {
        "ok": True,
        "nombre": "benedicto_alfonso_martin_colimil_1_16-09-2026.jpg",
        "paciente_input": "Benedicto Martin",
        "paciente_matcheado": "Benedicto Alfonso Martin Colimil",
        "paciente_resuelto": "Benedicto Alfonso Martin Colimil",
        "fecha_input": "16-09-2026",
        "fecha_matcheada": "16-09-2026",
        "fecha_resuelta": "16-09-2026",
        "fecha_input_descartada": False,
        "motivo_descarte": "",
    }

    with patch(
        "src.telegram_bot.handlers.photo.archivar_foto_desde_telegram",
        return_value=resultado,
    ) as svc:
        asyncio.run(cmd_archivar(update, context))

    # Verifica kwargs enviados al service.
    call_kwargs = svc.call_args.kwargs
    assert call_kwargs["nombre_paciente"] == "Benedicto Martin"
    assert call_kwargs["fecha_atencion"] == "16-09-2026"
    assert call_kwargs["indice_n"] == 1


# --- /archivar: descarga desde Telegram --------------------------------


def test_archivar_descarga_la_resolucion_mas_alta_de_la_foto():
    """Telegram envia fotos en varias resoluciones en message.photo.
    El handler debe tomar la ULTIMA (la mas grande)."""
    photo_small = _photo_mock(file_id="small")
    photo_big = _photo_mock(file_id="big")
    update = _make_update_with_message(
        _make_message(
            caption="/archivar Marta 01-09-2026",
            photo=[photo_small, photo_small, photo_big],
        )
    )
    context = _make_context_with_bot()

    with patch(
        "src.telegram_bot.handlers.photo.archivar_foto_desde_telegram",
        return_value={
            "ok": True,
            "nombre": "x",
            "paciente_resuelto": "M",
            "fecha_resuelta": "01-09-2026",
            "paciente_input": "M",
            "paciente_matcheado": "M",
            "fecha_input_descartada": False,
            "motivo_descarte": "",
        },
    ):
        asyncio.run(cmd_archivar(update, context))

    context.bot.get_file.assert_awaited_once_with("big")


def test_archivar_descarga_document_como_archivo():
    """Si el mensaje trae document (PDF), descarga el file_id del doc."""
    doc = MagicMock()
    doc.file_id = "doc_file_id_42"
    doc.file_name = "examen.pdf"
    update = _make_update_with_message(
        _make_message(
            caption="/archivar Marta 01-09-2026",
            photo=None,
            document=doc,
        )
    )
    context = _make_context_with_bot()

    with patch(
        "src.telegram_bot.handlers.photo.archivar_foto_desde_telegram",
        return_value={
            "ok": True,
            "nombre": "x.pdf",
            "paciente_resuelto": "M",
            "fecha_resuelta": "01-09-2026",
            "paciente_input": "M",
            "paciente_matcheado": "M",
            "fecha_input_descartada": False,
            "motivo_descarte": "",
        },
    ):
        asyncio.run(cmd_archivar(update, context))

    context.bot.get_file.assert_awaited_once_with("doc_file_id_42")


# --- /archivar: respuestas segun resultado del service -----------------


def test_archivar_ok_reporta_paciente_y_fecha_resueltos():
    update = _make_update_with_message(
        _make_message(
            caption="/archivar Benedicto Martin 16-09-2026",
            photo=[_photo_mock()],
        )
    )
    context = _make_context_with_bot()
    resultado = {
        "ok": True,
        "nombre": "x.jpg",
        "paciente_input": "Benedicto Martin",
        "paciente_matcheado": "Benedicto Alfonso Martin Colimil",
        "paciente_resuelto": "Benedicto Alfonso Martin Colimil",
        "fecha_input": "16-09-2026",
        "fecha_resuelta": "16-09-2026",
        "fecha_input_descartada": False,
        "motivo_descarte": "",
    }

    with patch(
        "src.telegram_bot.handlers.photo.archivar_foto_desde_telegram",
        return_value=resultado,
    ):
        asyncio.run(cmd_archivar(update, context))

    reply = update.effective_message.reply_text.await_args.args[0]
    assert "Listo, archivado" in reply
    assert "Benedicto Alfonso Martin Colimil" in reply
    assert "16-09-2026" in reply


def test_archivar_ok_reporta_match_de_paciente():
    """Si hubo match parcial -> nombre completo, lineas separadas."""
    update = _make_update_with_message(
        _make_message(caption="/archivar Marta", photo=[_photo_mock()])
    )
    context = _make_context_with_bot()
    resultado = {
        "ok": True,
        "nombre": "x.jpg",
        "paciente_input": "Marta",
        "paciente_matcheado": "Marta Perez Diaz",
        "paciente_resuelto": "Marta Perez Diaz",
        "fecha_input": "",
        "fecha_resuelta": "01-09-2026",
        "fecha_input_descartada": True,
        "motivo_descarte": "Sin fecha, usando la del informe.",
    }

    with patch(
        "src.telegram_bot.handlers.photo.archivar_foto_desde_telegram",
        return_value=resultado,
    ):
        asyncio.run(cmd_archivar(update, context))

    reply = update.effective_message.reply_text.await_args.args[0]
    assert "Marta Perez Diaz" in reply  # paciente resuelto
    assert "match:" in reply  # se reporta el match
    assert "Aviso:" in reply  # se reporta la fecha descartada


def test_archivar_error_reporta_mensaje_del_service():
    update = _make_update_with_message(
        _make_message(
            caption="/archivar Desconocido 17-09-2026",
            photo=[_photo_mock()],
        )
    )
    context = _make_context_with_bot()

    with patch(
        "src.telegram_bot.handlers.photo.archivar_foto_desde_telegram",
        return_value={"ok": False, "error": "Extension .exe no aceptada."},
    ):
        asyncio.run(cmd_archivar(update, context))

    reply = update.effective_message.reply_text.await_args.args[0]
    assert "Error:" in reply
    assert ".exe" in reply


# --- /archivar: errores inesperados -------------------------------------


def test_archivar_sin_photo_ni_document_avisa():
    """Edge case: el filtro no atrapa este caso (no deberia llegar)."""
    update = _make_update_with_message(
        _make_message(
            caption="/archivar Marta 01-09-2026",
            photo=None,
            document=None,
        )
    )
    context = _make_context_with_bot()

    asyncio.run(cmd_archivar(update, context))

    reply = update.effective_message.reply_text.await_args.args[0]
    assert "Solo proceso fotos o documentos" in reply
