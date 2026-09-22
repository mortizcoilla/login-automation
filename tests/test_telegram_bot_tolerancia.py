"""Tolerancia del caption /archivar (caso real Yadira 2026-09-22).

"/ archivar examenes de Paulina Tapia" debe llegar al handler y el
paciente debe quedar limpio ("Paulina Tapia"). Y toda foto sin calzar
recibe respuesta (cmd_foto_sin_match): jamas silencio.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.telegram_bot.handlers.photo import (
    ARCHIVAR_RE,
    _limpiar_paciente,
    cmd_foto_sin_match,
)


def _match(caption: str) -> tuple[str, str | None]:
    m = ARCHIVAR_RE.match(caption)
    assert m is not None, f"el caption {caption!r} debe matchear"
    paciente = _limpiar_paciente(m.group("paciente").strip())
    return paciente, m.group("fecha")


def test_gap_entre_barra_y_verbo() -> None:
    paciente, fecha = _match("/ archivar examenes de Paulina Tapia")
    assert paciente == "Paulina Tapia"
    assert fecha is None


def test_formato_canonico_sigue_funcionando() -> None:
    paciente, fecha = _match("/archivar Paulina Tapia 22-09-2026")
    assert paciente == "Paulina Tapia"
    assert fecha == "22-09-2026"


def test_mayusculas_y_espacios_iniciales() -> None:
    paciente, _ = _match("  /Archivar   examenes de  Ana ")
    assert paciente == "Ana"


def test_muletillas_descriptivas_se_limpian() -> None:
    assert _limpiar_paciente("exámenes de Maria Paz") == "Maria Paz"
    assert _limpiar_paciente("análisis para Juan") == "Juan"
    assert _limpiar_paciente("Pedro Soto") == "Pedro Soto"  # sin muletilla


# --- red de seguridad --------------------------------------------------------


def _make_message(caption: str | None):
    msg = MagicMock()
    msg.caption = caption
    msg.reply_text = AsyncMock()
    return msg


def test_foto_sin_caption_recibe_instrucciones() -> None:
    msg = _make_message(None)
    asyncio.run(cmd_foto_sin_match(_update(msg), MagicMock()))
    texto = msg.reply_text.call_args[0][0]
    assert "faltó el caption" in texto
    assert "/archivar <paciente>" in texto


def test_foto_con_caption_raro_recibe_formato() -> None:
    msg = _make_message("/ archivar examenes de Paulina Tapia")
    asyncio.run(cmd_foto_sin_match(_update(msg), MagicMock()))
    texto = msg.reply_text.call_args[0][0]
    assert "/ archivar examenes de Paulina Tapia" in texto
    assert "/archivar <paciente>" in texto
    assert "Ejemplo:" in texto


def _update(message):
    update = MagicMock()
    update.effective_message = message
    return update
