"""Tests para el fallback de texto (handlers/text.py).

Cubre tres casos:
- Texto libre ("hola") -> responde con WELCOME.
- Comando desconocido ("/foo bar") -> responde con WELCOME + menciona el comando.
- /archivar sin foto -> responde con hint pidiendo la foto.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.telegram_bot.handlers.start import WELCOME
from src.telegram_bot.handlers.text import cmd_text_fallback


def _make_update(text: str) -> MagicMock:
    message = MagicMock()
    message.text = text
    message.caption = None
    message.photo = None
    message.document = None
    message.reply_text = AsyncMock()
    user = MagicMock()
    user.id = 123456
    user.username = "tester"
    update = MagicMock()
    update.effective_message = message
    update.effective_user = user
    return update


def _reply_text_of(update: MagicMock) -> str:
    """Devuelve el texto del unico reply_text.await_args."""
    return update.effective_message.reply_text.await_args.args[0]


def test_texto_libre_responde_con_welcome():
    update = _make_update("hola")
    asyncio.run(cmd_text_fallback(update, MagicMock()))
    reply = _reply_text_of(update)
    assert WELCOME in reply
    assert WELCOME[:50] in reply


def test_comando_desconocido_responde_con_welcome_y_nombre_del_comando():
    update = _make_update("/foo bar baz")
    asyncio.run(cmd_text_fallback(update, MagicMock()))
    reply = _reply_text_of(update)
    assert "/foo" in reply  # menciona el comando no reconocido
    assert WELCOME in reply  # y la bienvenida


def test_archivar_sin_foto_responde_con_hint_de_foto():
    update = _make_update("/archivar Marta 01-09-2026")
    asyncio.run(cmd_text_fallback(update, MagicMock()))
    reply = _reply_text_of(update)
    assert "foto" in reply.lower()
    assert "/archivar" in reply  # repite el comando en la sugerencia


def test_archivar_con_minusculas_tambien_cae_en_hint_de_foto():
    update = _make_update("/ARCHIVAR Benedicto")  # mayusculas
    asyncio.run(cmd_text_fallback(update, MagicMock()))
    reply = _reply_text_of(update)
    assert "foto" in reply.lower()


def test_sin_message_no_falla():
    """Sin effective_message (canal raro), no debe explotar."""
    update = MagicMock()
    update.effective_message = None
    update.effective_user = MagicMock(id=1)
    # No debe lanzar excepcion.
    asyncio.run(cmd_text_fallback(update, MagicMock()))


def test_text_vacio_cae_en_welcome():
    """Texto vacio se considera texto libre y devuelve bienvenida."""
    update = _make_update("")
    asyncio.run(cmd_text_fallback(update, MagicMock()))
    reply = _reply_text_of(update)
    assert WELCOME in reply
