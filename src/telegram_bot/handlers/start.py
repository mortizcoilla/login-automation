"""/start y /help: bienvenida e instrucciones para Yadira."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


WELCOME = (
    "Hola mama yadira, mandame los examenes en el formato\n"
    " /archivar <paciente> [dd-mm-yyyy]\n"
    "una foto por mensaje. Para varias, envialas una a una."
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
