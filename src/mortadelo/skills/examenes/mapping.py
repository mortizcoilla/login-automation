"""Skill: lectura de examenes adjuntos (foto / PDF) usando easyocr.

Cuando Yadira adjunta una foto o PDF de un examen (audiometria, ECG,
laboratorio, etc.) en una ficha, Mortadelo puede:
1. Detectar el tipo de examen (por nombre)
2. Leer su contenido via OCR (easyocr para imagenes, pdfplumber para PDFs)
3. Devolver el texto crudo + tamano del archivo

Reglas duras:
- Local only (sin cloud, sin LLM externos).
- No interpreta clinicamente: eso lo hace Yadira.

Privacidad: el examen contiene PII del paciente. La lectura se hace
en local. El texto OCR queda en el .txt de la nota clinica, que
tambien es local.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional


# ---- Tipo de examen ----

def detectar_tipo_examen(nombre_archivo: str) -> Optional[str]:
    """Detecta el tipo de examen segun el nombre del archivo."""
    nombre = nombre_archivo.lower()
    if "audiometr" in nombre or "audio" in nombre:
        return "audiometria"
    if "ecg" in nombre or "electrocardio" in nombre:
        return "ecg"
    if "laborat" in nombre or "lab" in nombre or "sangre" in nombre:
        return "laboratorio"
    if "rx" in nombre or "radio" in nombre or "imagen" in nombre:
        return "imagen"
    if nombre.endswith(".pdf"):
        return "pdf_generico"
    return "imagen_generica"


# ---- Lectura del examen ----

def _leer_con_easyocr(ruta: Path, logger: logging.Logger) -> str:
    """Lee una imagen con easyocr. Retorna el texto extraido.

    Importacion lazy: easyocr se carga solo si se llama esta funcion.
    Si easyocr no esta instalado, retorna un mensaje de error.

    Workaround para easyocr 1.7.2 + OpenCV 5.0.0: easyocr hace un
    resize interno que rompe con `!ssize.empty()` en cv::resize cuando
    la imagen es grande (>2000px). Pre-redimensionamos con PIL a un
    tamano por debajo del canvas default de easyocr (2560) y pasamos
    el archivo temporal a easyocr. Asi evitamos el resize problematico.
    """
    try:
        import easyocr  # type: ignore
    except ImportError:
        logger.warning(
            f"[examenes] easyocr no esta instalado. "
            f"Para instalar: pip install easyocr "
            f"(tambien requiere torch y descarga modelos ~200MB la primera vez)"
        )
        return "[easyocr no instalado - no se pudo hacer OCR]"

    # Pre-resize con PIL si la imagen es muy grande.
    import tempfile
    from PIL import Image  # type: ignore

    MAX_LADO = 1800
    tmp_path: Optional[Path] = None
    try:
        img = Image.open(ruta)
        if max(img.size) > MAX_LADO:
            # Mantener aspect ratio.
            img.thumbnail((MAX_LADO, MAX_LADO), Image.Resampling.LANCZOS)
            # Guardar en un tempfile con la misma extension.
            suf = ruta.suffix.lower() or ".jpg"
            fd, tmp_name = tempfile.mkstemp(suffix=suf, prefix="examen_")
            import os
            os.close(fd)
            tmp_path = Path(tmp_name)
            # JPG no soporta alpha; convertir si viene con RGBA.
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(tmp_path, quality=92)
            ruta_ocr = tmp_path
        else:
            ruta_ocr = ruta
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[examenes] No se pudo pre-redimensionar {ruta}: {e}. Uso ruta original.")
        ruta_ocr = ruta

    try:
        # Lectura en espanol + ingles (por si el examen tiene texto en 2 idiomas)
        reader = easyocr.Reader(["es", "en"], gpu=False, verbose=False)
        result = reader.readtext(str(ruta_ocr), detail=0, paragraph=True)
        return "\n".join(result)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[examenes] Error en easyocr: {e}")
        return f"[Error en OCR: {e}]"
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _leer_pdf(ruta: Path, logger: logging.Logger) -> str:
    """Lee un PDF con pdfplumber. Retorna el texto extraido."""
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        logger.warning(
            "[examenes] pdfplumber no esta instalado. "
            "Para instalar: pip install pdfplumber"
        )
        return "[pdfplumber no instalado - no se pudo extraer texto]"

    try:
        texto_total: list[str] = []
        with pdfplumber.open(ruta) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                t = page.extract_text() or ""
                if t.strip():
                    texto_total.append(f"--- Pagina {i} ---\n{t}")
        return "\n".join(texto_total) if texto_total else "[PDF sin texto extraible]"
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[examenes] Error en pdfplumber: {e}")
        return f"[Error extrayendo PDF: {e}]"


def leer_examen(ruta_o_nombre: str) -> dict[str, str]:
    """Lee un examen y retorna sus datos estructurados.

    Args:
        ruta_o_nombre: ruta absoluta al archivo, o solo el nombre.

    Returns:
        dict con los datos del examen:
          - tipo: tipo detectado (audiometria, ecg, etc.)
          - texto_ocr: texto extraido (OCR para imagen, extraccion para PDF)
          - tamano_kb: tamano del archivo en KB
          - error: mensaje de error si algo fallo
    """
    logger = logging.getLogger("examenes")
    ruta = Path(ruta_o_nombre)
    if not ruta.exists():
        logger.warning(f"[examenes] Archivo no existe: {ruta}")
        return {"tipo": None, "texto_ocr": "", "tamano_kb": "0", "error": "archivo no existe"}

    tipo = detectar_tipo_examen(ruta.name)
    tamano_kb = ruta.stat().st_size // 1024
    ext = ruta.suffix.lower()

    if ext in (".pdf",):
        texto = _leer_pdf(ruta, logger)
    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"):
        texto = _leer_con_easyocr(ruta, logger)
    else:
        texto = f"[Extension {ext} no soportada aun]"

    return {
        "tipo": tipo or "desconocido",
        "texto_ocr": texto,
        "tamano_kb": str(tamano_kb),
        "error": "",
    }


# ---- Interpretacion (solo la parte que no es decision clinica) ----
# IMPORTANTE: Mortadelo NO interpreta clinicamente. Esto solo extrae
# valores tabulares que Yadira puede revisar.

def interpretar_audiometria(datos: dict[str, str]) -> str:
    """Extrae los valores de la audiometria (frecuencias, decibeles) del OCR.

    NO hace interpretacion clinica. Solo extrae los numeros que el OCR
    reconocio, para que Yadira los verifique y los use en su analisis.

    Formato comun de audiometria:
      Frecuencia (Hz): 250  500  1000  2000  4000  8000
      OD (dB):        20   25   30    35    40    45
      OI (dB):        20   25   30    35    40    45
    """
    if not datos.get("texto_ocr"):
        return "[Sin texto OCR para parsear]"
    texto = datos["texto_ocr"]
    lineas: list[str] = []
    lineas.append("Valores extraidos del OCR (verificar con el original):")
    # Buscar numeros asociados a OD y OI
    patron_od = re.compile(r"(\bOD\b|od\b|der|der\w*|derecho)[\s:]+([\d\s\.]+)", re.IGNORECASE)
    patron_oi = re.compile(r"(\bOI\b|oi\b|izq|izq\w*|izquierdo)[\s:]+([\d\s\.]+)", re.IGNORECASE)
    for m in patron_od.finditer(texto):
        lineas.append(f"  OD: {m.group(2).strip()}")
    for m in patron_oi.finditer(texto):
        lineas.append(f"  OI: {m.group(2).strip()}")
    # Si no encontro nada, devolver el texto crudo
    if len(lineas) == 1:
        lineas.append("  (no se detectaron valores OD/OI automaticos)")
        lineas.append("  Texto crudo OCR:")
        for ln in texto.split("\n"):
            lineas.append(f"    {ln}")
    return "\n".join(lineas)


__all__ = [
    "detectar_tipo_examen",
    "leer_examen",
    "interpretar_audiometria",
]
