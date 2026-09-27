"""Handler de diagnostico: loggea TODO mensaje que llega (grupo -1).

Corre en el grupo -1, ANTES de los handlers de negocio (grupo 0), y no
consume el update: los handlers de negocio se evaluan normal despues.
Responde la pregunta P0 de STATUS.md: que esta llegando exactamente por
el cable cuando Yadira manda una foto, y de quien (user_id), sin depender
de que el filtro de /archivar matchee.

El caption se loggea con ascii() para hacer visibles caracteres
invisibles (zero-width, BOM) que rompen el regex del filtro.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)


async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Loguea una linea por mensaje recibido. Nunca responde ni consume."""
    msg = update.effective_message
    if msg is None:
        logger.info("[debug] update sin message: update_id=%s", update.update_id)
        return
    user = update.effective_user
    logger.info(
        "[debug] msg_id=%s user_id=%s username=%r chat_id=%s "
        "photo=%s doc=%s(mime=%s) text=%s caption=%s",
        msg.message_id,
        user.id if user else None,
        user.username if user else None,
        update.effective_chat.id if update.effective_chat else None,
        bool(msg.photo),
        bool(msg.document),
        (msg.document.mime_type or "?") if msg.document else "-",
        ascii(msg.text) if msg.text else None,
        ascii(msg.caption) if msg.caption else None,
    )


def register(application) -> None:
    """Registra el logger en el grupo -1 (corre antes que el grupo 0)."""
    application.add_handler(MessageHandler(filters.ALL, log_update), group=-1)
