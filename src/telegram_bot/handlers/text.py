"""/text fallback: handler para cualquier mensaje de texto sin comando /archivar.

Casos que caen aca:
- Texto plano ("hola", "buenos dias", "que pasa").
- Comando desconocido ("/foo bar").
- /archivar SIN foto/documento (porque el handler especializado requiere media).

En todos los casos, respondemos con WELCOME para que el usuario entienda
que hacer. Si el texto arranca con "/archivar" pero no trae foto, agregamos
un hint explicito pidiendo la foto.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.telegram_bot.handlers.start import WELCOME

logger = logging.getLogger(__name__)


_HINT_FALTA_FOTO = (
    "Recibí el comando /archivar pero no detecte foto ni documento adjunto.\n"
    "Reenvia el comando /archivar como CAPTION de la foto. Ejemplo:\n"
    "  [foto.jpg con caption:] /archivar Marta 18-09-2026"
)


async def cmd_text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde a cualquier texto no /archivar-con-foto.

    Si arranca con /archivar, agregamos un hint especifico de "falta foto".
    Si es otro texto, devolvemos el WELCOME directo.
    """
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    text = (message.text or "").strip()

    if text.lower().startswith("/archivar"):
        # Usuario intento usar el comando pero se olvido de adjuntar la foto.
        await message.reply_text(_HINT_FALTA_FOTO)
    elif text.startswith("/"):
        # Comando desconocido (pero NO /archivar sin foto).
        primer_token = text.split(maxsplit=1)[0]
        await message.reply_text(f"Comando {primer_token!r} no reconocido.\n\n{WELCOME}")
    else:
        # Texto libre. Repito el WELCOME.
        await message.reply_text(WELCOME)

    if user is not None:
        logger.info(
            "text_fallback de user_id=%s username=%r texto=%r",
            user.id,
            user.username,
            text[:80],
        )
