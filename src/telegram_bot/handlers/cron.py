"""Comandos Go/Kill/Status: Yadira controla el cron desde Telegram (REQ-105).

 - Go    -> arranca el flujo diario completo ya (runner --forzar yadira,
            desprendido: sobrevive a esta conversacion). Si ya corre, no
            lanza una segunda cadena.
 - Kill  -> si corre, mata el arbol del runner (paso en curso incluido)
            y limpia el candado.
 - Status-> reporte chito: corre o no, PID, ultimo paso y ultima
            actividad del cron.

Son texto plano (sin barra), registrados ANTES del catch-all de texto
para ganarle al WELCOME generico. Aceptan "go", "Go", "/go" y punto
final ("go."). La auth (whitelist de user IDs) se aplica en app.py.
"""

from __future__ import annotations

import asyncio
import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from src.telegram_bot.services import cron_service

logger = logging.getLogger(__name__)

_RX_GO = re.compile(r"(?i)^\s*/?\s*go\s*\.?\s*$")
_RX_KILL = re.compile(r"(?i)^\s*/?\s*kill\s*\.?\s*$")
_RX_STATUS = re.compile(r"(?i)^\s*/?\s*status\s*\.?\s*$")


def calza_go(texto: str | None) -> bool:
    return bool(texto and _RX_GO.match(texto))


def calza_kill(texto: str | None) -> bool:
    return bool(texto and _RX_KILL.match(texto))


def calza_status(texto: str | None) -> bool:
    return bool(texto and _RX_STATUS.match(texto))


async def cmd_go(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    logger.info("Go de user_id=%s", update.effective_user.id if update.effective_user else "?")
    ok, detalle = await asyncio.to_thread(cron_service.arrancar_cron)
    if ok:
        await message.reply_text(
            f"Dale, arranco el flujo diario completo ya ({detalle}).\n"
            "Tarda un par de horas; escribime Status para ver como va."
        )
    elif detalle.startswith("ya corre"):
        await message.reply_text(
            f"El flujo ya esta corriendo ({detalle}).\n"
            "Escribeme Status para ver como va."
        )
    else:
        await message.reply_text(
            f"No pude arrancarlo: {detalle}.\nEscribeme Status para ver el estado."
        )


async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    logger.info("Kill de user_id=%s", update.effective_user.id if update.effective_user else "?")
    await message.reply_text("Un segundito, reviso el flujo...")
    ok, detalle = await asyncio.to_thread(cron_service.matar_cron)
    if ok:
        await message.reply_text(f"Listo: {detalle}.")
    else:
        await message.reply_text(
            f"No pude detenerlo ({detalle}).\nEscribeme Status para ver el estado."
        )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    logger.info(
        "Status de user_id=%s", update.effective_user.id if update.effective_user else "?"
    )
    await message.reply_text(await asyncio.to_thread(cron_service.texto_status))
