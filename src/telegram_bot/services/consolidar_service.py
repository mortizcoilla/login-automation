"""Fachada de consolidacion OCR del bot (mision 2, REQ-061).

Tras archivar una foto (mision 1), el bot invoca el paso 2b existente
(src.examenes.consolidar) para transcribir con la API de vision z.ai
TODAS las imagenes crudas del paciente y dejar UN unico
exam_<pac>_<fecha>.md en EXAMENES_DIR.

Politica del archivo unico: el markdown es un DERIVADO de las fotos
crudas (la fuente inmutable en examenes_respaldos). Al consolidar:
  - si la transcripcion falla, el md anterior NO se toca, y
  - si tiene exito, los md previos del mismo paciente+fecha se
    reemplazan por uno nuevo con el nombre canonico, asi la segunda foto
    del mismo examen NO acumula _v2/_v3: siempre queda UN solo archivo
    con TODAS las imagenes encontradas.

Los PDF se archivan (mision 1) pero NO se transcriben: la API de vision
procesa imagenes; el aviso se le informa a Yadira en el reply.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from src.core.fechas import fecha_hoy_str
from src.core.nombres import safe_filename
from src.core.rutas import EXAMENES_CRUDOS_DIR, EXAMENES_DIR
from src.examenes.consolidar import buscar_fotos_crudas, consolidar_examenes
from src.examenes.gemini_api import transcribir_imagen as _gemini
from src.examenes.ocr_opencode import transcribir_imagen as _opencode
from src.examenes.vision_api import transcribir_imagen as _zai

_MOTORES: dict[str, Callable[[Path], str]] = {
    "opencode": _opencode,
    "gemini": _gemini,
    "zai": _zai,
}


def _transcriptor_default() -> Callable[[Path], str]:
    """Motor OCR segun OCR_ENGINE: opencode (default), gemini o zai."""
    motor = os.getenv("OCR_ENGINE", "opencode").strip().lower()
    return _MOTORES.get(motor, _opencode)


def _inferir_fecha(fotos: list[Path], fecha: str | None) -> str:
    """La fecha dada, o la del primer archivo crudo (convencion paso 2a)."""
    if fecha:
        return fecha
    partes = fotos[0].stem.split("_")
    return partes[-1] if len(partes[-1].split("-")) == 3 else fecha_hoy_str()


def consolidar_desde_telegram(
    nombre_paciente: str,
    fecha_atencion: str | None = None,
    crudos_dir: Path | None = None,
    destino_dir: Path | None = None,
    transcriptor: Callable[[Path], str] | None = None,
) -> dict:
    """Transcribe y consolida los examenes archivados de un paciente.

    Args:
        nombre_paciente: el nombre que Yadira escribio en el caption.
        fecha_atencion: dd-mm-yyyy opcional; si falta, se infiere de los
            archivos crudos.
        crudos_dir: override del dir de fotos crudas (default:
            EXAMENES_CRUDOS_DIR; el handler pasa el destino del bot).
        destino_dir: override del dir del md (default: EXAMENES_DIR).
        transcriptor: inyectable para tests (nunca API real en la suite);
            default = motor segun OCR_ENGINE (gemini, REQ-061).

    Returns:
        El dict de consolidar_examenes() ({ok, path, fotos, ...}); si no
        hay imagenes que procesar, {ok: False, motivo: "sin_fotos_imagen"}.
    """
    crudos = crudos_dir if crudos_dir is not None else EXAMENES_CRUDOS_DIR
    destino = destino_dir if destino_dir is not None else EXAMENES_DIR
    transcriptor = transcriptor or _transcriptor_default()

    fotos = buscar_fotos_crudas(nombre_paciente, fecha_atencion, crudos)
    if not fotos:
        return {
            "ok": False,
            "path": "",
            "fotos": 0,
            "motivo": "sin_fotos_imagen",
            "error": (
                "No hay imagenes archivadas de ese paciente "
                "(los PDF se archivan sin OCR)"
            ),
        }

    fecha = _inferir_fecha(fotos, fecha_atencion)
    resultado = consolidar_examenes(
        paciente=nombre_paciente,
        fecha=fecha,
        crudos_dir=crudos,
        destino_dir=destino,
        transcriptor=transcriptor,
    )

    # Archivo unico: con exito, dejar SOLO el md canonico de esta fecha.
    if resultado.get("ok"):
        safe = safe_filename(nombre_paciente)
        canonico = destino / f"exam_{safe}_{fecha}.md"
        nuevo = Path(str(resultado["path"]))
        for previo in destino.glob(f"exam_{safe}_{fecha}*.md"):
            if previo != nuevo:
                previo.unlink(missing_ok=True)
        if nuevo != canonico:
            nuevo.replace(canonico)
            resultado["path"] = str(canonico)
    return resultado
