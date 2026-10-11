"""Consolidacion de examenes: fotos crudas -> exam_<pac>_<fecha>.md (REQ-047).

Paso 2b (opt-in por paciente). Lee las fotos y PDFs de
data/examenes_crudos/ (paso 2a), los transcribe con la API de vision
(los PDF se renderizan a paginas primero, REQ-101) y consolida UN
archivo exam_<pac>_<fecha>.md en data/examenes/. NUNCA sobrescribe
(_v2, _v3...). Si la API falla, el archivado del 2a NO se ve afectado.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path

from src.core.fechas import fecha_hoy_str
from src.core.nombres import nombre_a_filename, safe_filename
from src.core.rutas import EXAMENES_CRUDOS_DIR, EXAMENES_DIR
from src.examenes.pdf import renderizar_paginas
from src.examenes.vision_api import DEFAULT_MODEL, transcribir_imagen

# Extensiones que la API de vision procesa como imagen.
EXTENSIONES_IMAGEN = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

# Lo que el paso 2b sabe procesar: imagenes + PDF (render previo a
# paginas, REQ-101). Regla 11-10-2026: TODO examen archivado debe
# terminar consolidado como insumo del LLM.
EXTENSIONES_PROCESABLES = EXTENSIONES_IMAGEN | {".pdf"}


def buscar_fotos_crudas(paciente: str, fecha: str | None, crudos_dir: Path) -> list[Path]:
    """Fotos/PDF archivados del paciente (y fecha si se dio), ordenados por nombre."""
    prefijo = nombre_a_filename(paciente) + "_"
    fotos = [
        p
        for p in sorted(crudos_dir.glob(prefijo + "*"))
        if p.suffix.lower() in EXTENSIONES_PROCESABLES
    ]
    if fecha:
        fotos = [p for p in fotos if f"_{fecha}" in p.stem]
    return fotos


def transcribir_archivo(ruta: Path, transcriptor: Callable[[Path], str]) -> str:
    """OCR de un archivo procesable (REQ-101).

    Imagen: pasa directo al transcriptor. PDF: renderiza cada pagina a
    PNG y transcribe pagina a pagina, uniendo con marcadores '[pagina N]'
    para que el LLM conserve el orden del documento. Las imagenes del
    render son temporales y se borran al salir.
    """
    if ruta.suffix.lower() != ".pdf":
        return transcriptor(ruta)
    paginas = renderizar_paginas(ruta)
    try:
        partes = []
        for i, pag in enumerate(paginas, start=1):
            texto = (transcriptor(pag) or "").strip()
            partes.append(f"[pagina {i}]\n{texto}" if texto else f"[pagina {i}] (sin texto)")
        return "\n\n".join(partes)
    finally:
        for pag in paginas:
            pag.unlink(missing_ok=True)
        if paginas:
            with contextlib.suppress(OSError):
                paginas[0].parent.rmdir()


def _resolver_destino(destino_dir: Path, nombre: str) -> Path:
    destino_dir.mkdir(parents=True, exist_ok=True)
    candidato = destino_dir / nombre
    if not candidato.exists():
        return candidato
    stem, suffix, n = candidato.stem, candidato.suffix, 2
    while True:
        nuevo = destino_dir / f"{stem}_v{n}{suffix}"
        if not nuevo.exists():
            return nuevo
        n += 1


def consolidar_examenes(
    paciente: str,
    fecha: str | None = None,
    crudos_dir: Path = EXAMENES_CRUDOS_DIR,
    destino_dir: Path = EXAMENES_DIR,
    transcriptor: Callable[[Path], str] = transcribir_imagen,
    modelo: str | None = None,
) -> dict:
    """Transcribe las fotos crudas de un paciente y consolida exam_<pac>_<fecha>.md.

    Returns:
        dict {ok, path, fotos, transcripciones: list[(nombre, texto|None, error)],
              fecha_resuelta, error}
    """
    resultado: dict = {
        "ok": False,
        "path": "",
        "fotos": 0,
        "transcripciones": [],
        "fecha_resuelta": "",
        "error": "",
    }
    fotos = buscar_fotos_crudas(paciente, fecha, crudos_dir)
    if not fotos:
        resultado["error"] = (
            f"No hay fotos crudas de '{paciente}'"
            + (f" con fecha {fecha}" if fecha else "")
            + f" en {crudos_dir}"
        )
        return resultado
    resultado["fotos"] = len(fotos)

    # Fecha: la dada, o la del primer archivo crudo (convencion paso 2a).
    if not fecha:
        partes = fotos[0].stem.split("_")
        fecha = partes[-1] if len(partes[-1].split("-")) == 3 else fecha_hoy_str()
    resultado["fecha_resuelta"] = fecha

    transcripciones: list[tuple[str, str | None, str]] = []
    textos: list[str] = []
    for foto in fotos:
        try:
            texto = transcribir_archivo(foto, transcriptor)
            transcripciones.append((foto.name, texto, ""))
        except Exception as e:
            transcripciones.append((foto.name, None, str(e)))
    resultado["transcripciones"] = [
        {"archivo": n, "texto": tx, "error": e} for n, tx, e in transcripciones
    ]
    textos = [tx for (_, tx, _) in transcripciones if tx]
    # SIN fotos transcritas -> error general (no se escribe nada).
    if not textos:
        resultado["error"] = "Todas las transcripciones fallaron (ver transcripciones)"
        return resultado

    nombre = f"exam_{safe_filename(paciente)}_{fecha}.md"
    destino = _resolver_destino(destino_dir, nombre)

    md = ["---"]
    md.append(f'paciente: "{paciente}"')
    md.append(f'fecha_atencion: "{fecha}"')
    md.append("archivos_origen:")
    for foto in fotos:
        md.append(f'  - "{foto.name}"')
    md.append(f'modelo_ocr: "{modelo or DEFAULT_MODEL} (vision API)"')
    md.append(f'fecha_digitalizacion: "{fecha_hoy_str()}"')
    md.append("---")
    md.append("")
    md.append(f"# Examenes de {paciente} ({fecha})")
    md.append("")
    for (nombre_foto, texto_t, error), foto in zip(transcripciones, fotos, strict=False):
        md.append(f"## {foto.stem}")
        md.append("")
        md.append(f"Fuente: {nombre_foto}")
        md.append("")
        if texto_t:
            for ln in texto_t.splitlines():
                md.append(ln.rstrip())
        else:
            md.append(f"(transcripcion fallo: {error})")
        md.append("")
    destino.write_text("\n".join(md) + "\n", encoding="utf-8")

    resultado.update({"ok": True, "path": str(destino)})
    return resultado
