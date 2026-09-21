"""/start y /help: bienvenida e instrucciones para Yadira."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


WELCOME = (
    "Hola! Soy Rubicita, la que recibe tus examenes.\n\n"
    "Envia una foto o PDF con un caption asi:\n\n"
    "  /archivar <paciente> [dd-mm-yyyy]\n\n"
    "Ejemplos:\n"
    "  /archivar Benedicto Alfonso Martin Colimil 16-09-2026\n"
    "  /archivar Benedicto Martin\n"
    "    (busca el nombre completo y la fecha en notas_clinicas/)\n\n"
    "v1: una foto por mensaje. Para varias, envialas una a una.\n"
    "Si me mandas video o audio, no los proceso; avisame con foto o PDF."
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler de /start y /help (alias)."""
    message = update.effective_message
    user = update.effective_user
    if message is None:
        return
    await message.reply_text(WELCOME)
    if user is not None:
        logger.info(
            "/start de user_id=%s username=%r first_name=%r",
            user.id,
            user.username,
            user.first_name,
        )
