"""/archivar: handler de recepcion de fotos/documentos con caption.

Flujo por mensaje:
    1. Parsea el caption: /archivar <paciente> [dd-mm-yyyy]
    2. Descarga la foto o el documento a un tmp.
    3. Llama al service archivar_foto_desde_telegram (que envuelve
       recibir_y_archivar()).
    4. Responde a Yadira con el resultado o el error.
    5. Borra el tmp.

Limites v1:
    - Solo mensaje unitario (1 foto o 1 PDF). Albums NO soportados.
    - El indice es siempre 1 (cada envio es 1 foto).
    - La fecha del filename la decide recibir_y_archivar() (fecha del
      informe, no fecha del caption de Yadira).

Cadenas de error que respondemos in-line:
    - caption vacio: "Falta el comando /archivar..."
    - caption mal parseado: ayuda con formato esperado
    - fecha invalida (no dd-mm-yyyy): aviso
    - sin foto/documento: aviso (deberia no llegar por el filtro)
    - error de recibir_y_archivar(): mensaje "Error: <motivo>"
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from src.telegram_bot.services.consolidar_service import consolidar_desde_telegram
from src.telegram_bot.services.recibir_foto_service import (
    archivar_foto_desde_telegram,
)

logger = logging.getLogger(__name__)


# /archivar <paciente> [dd-mm-yyyy] — tolerante a "/ archivar" (gap entre
# la barra y el verbo, caso real de Yadira 2026-09-22) y a mayusculas.
# - paciente: cualquier texto, no vacio
# - fecha: opcional, formato dd-mm-yyyy al final
ARCHIVAR_RE = re.compile(
    r"^\s*/\s*archivar\s+(?P<paciente>.+?)(?:\s+(?P<fecha>\d{2}-\d{2}-\d{4}))?\s*$",
    re.IGNORECASE | re.DOTALL,
)

# Muletilla descriptiva que Yadira usa al nombrar el examen:
# "examenes de Paulina Tapia" -> paciente "Paulina Tapia".
_PREFIJO_DESCRIPTIVO_RE = re.compile(
    r"^(?:ex[aá]menes|examen|an[aá]lisis|analisis)\s+(?:de|del|para)\s+",
    re.IGNORECASE,
)


def _limpiar_paciente(paciente: str) -> str:
    """Quita la muletilla 'examenes de' del nombre dado por Yadira."""
    return _PREFIJO_DESCRIPTIVO_RE.sub("", paciente).strip()


def _tmp_dir(context: ContextTypes.DEFAULT_TYPE) -> Path:
    """Devuelve el tmp dir del bot, creandolo si hace falta.

    Cachea la ruta en bot_data para no crearla en cada mensaje.
    """
    cached = context.application.bot_data.get("telegram_tmp_dir")
    if isinstance(cached, Path):
        return cached
    tmp = Path(tempfile.gettempdir()) / "telegram_bot_rubicita"
    tmp.mkdir(parents=True, exist_ok=True)
    context.application.bot_data["telegram_tmp_dir"] = tmp
    logger.info("tmp_dir del bot: %s", tmp)
    return tmp


async def cmd_archivar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler de /archivar (foto o documento con caption)."""
    message = update.effective_message
    # Log de diagnostico: si esta linea no aparece en consola, el filtro
    # de app.py esta rechazando el mensaje y hay que ajustar el filter.
    logger.info(
        "cmd_archivar invocado: has_msg=%s has_caption=%s caption=%r has_photo=%s has_doc=%s",
        message is not None,
        bool(message.caption) if message else False,
        (message.caption or "")[:60] if message else None,
        bool(message.photo) if message else False,
        bool(message.document) if message else False,
    )
    if message is None:
        return

    caption = (message.caption or "").strip()
    if not caption:
        await message.reply_text(
            "Falta el comando /archivar. Ejemplo:\n  /archivar <paciente> [dd-mm-yyyy]"
        )
        return

    match = ARCHIVAR_RE.match(caption)
    if match is None:
        await message.reply_text(
            f"No pude parsear el caption: {caption!r}\n\n"
            "Formato esperado: /archivar <paciente> [dd-mm-yyyy]"
        )
        return

    paciente = _limpiar_paciente(match.group("paciente").strip())
    if not paciente:
        await message.reply_text(
            "No me quedo un nombre de paciente despues de limpiar el caption. "
            "Ejemplo: /archivar Paulina Tapia 22-09-2026"
        )
        return
    fecha = match.group("fecha")  # puede ser None

    # Si Yadira dio una fecha, validar formato dd-mm-yyyy estrictamente.
    # (La regex solo valida estructura, no valores reales del calendario.)
    if fecha:
        try:
            datetime.strptime(fecha, "%d-%m-%Y")
        except ValueError:
            await message.reply_text(f"Fecha invalida {fecha!r}. Formato dd-mm-yyyy.")
            return

    # Descargar el archivo desde Telegram.
    if message.photo:
        tg_file = await context.bot.get_file(message.photo[-1].file_id)
        suggested_ext = ".jpg"
    elif message.document:
        tg_file = await context.bot.get_file(message.document.file_id)
        suggested_ext = Path(message.document.file_name or "").suffix.lower() or ".bin"
    else:
        # No deberia llegar aqui por el filtro, pero por las dudas.
        await message.reply_text("Solo proceso fotos o documentos. Videos/audios no.")
        return

    tmp_dir = _tmp_dir(context)
    # file_id es estable por archivo; usarlo como nombre unico.
    tmp_path = tmp_dir / f"{tg_file.file_id}{suggested_ext}"
    try:
        await tg_file.download_to_drive(str(tmp_path))
    except Exception as exc:  # network/Telegram error
        logger.exception("Error descargando archivo desde Telegram")
        await message.reply_text(f"Error descargando: {exc}")
        return

    # Invocar el service en hilo (recibir_y_archivar hace I/O sync de archivos).
    bot_config = context.application.bot_data.get("config")
    notas_dir_override = (
        Path(bot_config.notas_dir_path)
        if bot_config is not None and bot_config.notas_dir_path
        else None
    )
    destino_dir_override = (
        Path(bot_config.destino_dir_path)
        if bot_config is not None and bot_config.destino_dir_path
        else None
    )
    try:
        resultado = await asyncio.to_thread(
            archivar_foto_desde_telegram,
            input_path=tmp_path,
            indice_n=1,
            nombre_paciente=paciente,
            fecha_atencion=fecha,
            destino_dir_override=destino_dir_override,
            notas_dir_override=notas_dir_override,
        )
    except Exception as exc:
        logger.exception("Error inesperado en service")
        await message.reply_text(f"Error inesperado: {exc}")
        _cleanup(tmp_path)
        return
    finally:
        _cleanup(tmp_path)

    # Responder segun el resultado.
    if resultado.get("ok"):
        lineas = [
            "Listo, archivado:",
            f"  archivo: {resultado.get('nombre', '')}",
            f"  paciente: {resultado.get('paciente_resuelto', '')}",
            f"  fecha: {resultado.get('fecha_resuelta', '')}",
        ]
        if resultado.get("paciente_matcheado") and resultado.get(
            "paciente_matcheado"
        ) != resultado.get("paciente_input"):
            lineas.append(
                f"  (match: tu '{resultado.get('paciente_input', '')}' "
                f"-> completo '{resultado.get('paciente_matcheado', '')}')"
            )
        if resultado.get("fecha_input_descartada"):
            lineas.append("")
            lineas.append(f"Aviso: {resultado.get('motivo_descarte', '')}")

        # Mision 2 (REQ-061): transcribir con vision y consolidar TODAS las
        # imagenes archivadas del paciente en un unico exam_<pac>_<fecha>.md.
        # El archivado ya esta hecho: un fallo aqui es un aviso, no un error.
        try:
            consolidado = await asyncio.to_thread(
                consolidar_desde_telegram,
                nombre_paciente=paciente,
                fecha_atencion=fecha,
                crudos_dir=destino_dir_override,
            )
        except Exception as exc:
            logger.exception("Error inesperado en consolidacion OCR")
            consolidado = {"ok": False, "error": f"error inesperado: {exc}"}
        lineas.append("")
        if consolidado.get("ok"):
            lineas.append(
                f"Examenes transcritos a: {Path(str(consolidado.get('path', ''))).name} "
                f"({consolidado.get('fotos', 0)} imagen/es)"
            )
        else:
            lineas.append(
                f"Aviso: la transcripcion automatica no corrio "
                f"({consolidado.get('error', 'motivo desconocido')})"
            )
        await message.reply_text("\n".join(lineas))
    else:
        await message.reply_text(f"Error: {resultado.get('error', 'sin detalle')}")


def _cleanup(tmp_path: Path) -> None:
    """Borra el archivo temporal. Silenciosamente, no es critico."""
    with contextlib.suppress(OSError):
        tmp_path.unlink(missing_ok=True)


async def cmd_foto_sin_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Red de seguridad: foto/doc cuyo caption NO calzo con /archivar.

    Sin este handler, un caption mal escrito se traga en silencio y
    Yadira siente que "el bot no funciona" (caso real 2026-09-22:
    "/ archivar examenes de X"). SIEMPRE responde con el formato.
    """
    message = update.effective_message
    if message is None:
        return
    caption = (message.caption or "").strip()
    if not caption:
        await message.reply_text(
            "📸 Recibi tu foto, mama! Pero le faltó el caption:\n\n"
            "/archivar <paciente> [dd-mm-yyyy]\n\n"
            "Reenviamela con ese caption y la archivo ✨"
        )
        return
    await message.reply_text(
        f"📸 Recibi tu foto con el caption:\n{caption}\n\n"
        "Pero no pude leerlo. El formato es:\n"
        "/archivar <paciente> [dd-mm-yyyy]\n\n"
        "Ejemplo: /archivar Paulina Tapia 22-09-2026"
    )
