"""Render de paginas PDF a imagenes para el OCR (REQ-101).

Los examenes tambien llegan como PDF (informes de laboratorio). La API
de vision procesa imagenes: este modulo renderiza cada pagina a PNG
(PyMuPDF, rueda unica sin dependencias de sistema) para pasarla por el
mismo motor OCR que las fotos.
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def renderizar_paginas(
    pdf: Path,
    dpi: int = 150,
    destino_dir: Path | None = None,
) -> list[Path]:
    """Renderiza cada pagina del PDF a PNG y devuelve las rutas en orden.

    dpi 150: legible para OCR de informes de laboratorio sin generar
    imagenes gigantes. Sin destino_dir se crea un directorio temporal
    nuevo; el llamador es dueno de limpiarlo (transcribir_archivo lo
    hace). Inyectable destino_dir para tests.
    """
    import pymupdf

    doc = pymupdf.open(str(pdf))
    try:
        destino = (
            Path(tempfile.mkdtemp(prefix="ocr_pdf_"))
            if destino_dir is None
            else destino_dir
        )
        destino.mkdir(parents=True, exist_ok=True)
        zoom = dpi / 72
        matriz = pymupdf.Matrix(zoom, zoom)
        paginas: list[Path] = []
        for i, pagina in enumerate(doc, start=1):
            pix = pagina.get_pixmap(matrix=matriz)
            ruta = destino / f"{pdf.stem}_pag{i:03d}.png"
            pix.save(str(ruta))
            paginas.append(ruta)
        return paginas
    finally:
        doc.close()
