"""Motor OCR via CLI opencode: modelos con vision del tier free (REQ-061).

Motor DEFAULT de la mision 2 del bot (decision 2026-09-21: la API de
Gemini requiere prepago y z.ai no tenia key en el PC; opencode-go tiene
modelos con vision gratuitos — probado en vivo con mimo-v2.6-flash-free).

Config (en .env):
    OCR_ENGINE          opencode (default) | gemini | zai
    OCR_OPENCODE_MODEL  default opencode/mimo-v2.6-flash-free
    OCR_TIMEOUT         segundos por imagen (default 180)
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from src.core.rutas import ROOT

DEFAULT_MODEL = "opencode/mimo-v2.6-flash-free"
_TIMEOUT_SEGUNDOS = 180

# Codigos ANSI que el CLI deja en la salida.
logger = logging.getLogger(__name__)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

PROMPT_TRANSCRIPCION = (
    "Transcribe fielmente TODO el texto visible de esta imagen de examen "
    "medico (encabezados, tablas con sus columnas y valores, unidades, "
    "rangos de referencia, pie de pagina). NO interpretes resultados, NO "
    "agregues datos que no esten escritos, NO diagnostiques. Si algo es "
    "ilegible, escribe [ilegible]. Devuelve unicamente la transcripcion."
)


class OpencodeOCRError(RuntimeError):
    """Error transcribiendo via CLI opencode (CLI ausente, HTTP, etc.)."""


def _limpiar_salida(texto: str) -> str:
    """Quita ANSI y el encabezado del CLI ('> agente - modelo')."""
    texto = _ANSI_RE.sub("", texto)
    lineas = texto.splitlines()
    i = 0
    while i < len(lineas) and not lineas[i].strip():
        i += 1
    if i < len(lineas) and re.match(r"^>\s*\S.*\s·\s\S", lineas[i]):
        i += 1
        while i < len(lineas) and not lineas[i].strip():
            i += 1
    return "\n".join(lineas[i:]).strip()


def transcribir_imagen(
    image_path: Path,
    prompt: str = PROMPT_TRANSCRIPCION,
    modelo: str | None = None,
    timeout: int | None = None,
) -> str:
    """Transcribe una imagen invocando `opencode run --file`.

    Raises:
        OpencodeOCRError: CLI ausente, codigo distinto de 0, timeout o
            salida vacia.
    """
    modelo_efectivo = modelo or os.environ.get("OCR_OPENCODE_MODEL", DEFAULT_MODEL)
    timeout_efectivo = timeout or int(os.environ.get("OCR_TIMEOUT", "180"))
    exe = shutil.which("opencode")
    if not exe:
        raise OpencodeOCRError("CLI de opencode no encontrada en PATH")
    try:
        resultado = subprocess.run(
            [exe, "run", "--model", modelo_efectivo, "--file", str(image_path), prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            timeout=timeout_efectivo,
        )
    except subprocess.TimeoutExpired as e:
        raise OpencodeOCRError(
            f"timeout de {timeout_efectivo}s transcribiendo {image_path.name}"
        ) from e
    if resultado.returncode != 0:
        detalle = (resultado.stderr or resultado.stdout or "")[:200]
        raise OpencodeOCRError(
            f"opencode run ({modelo_efectivo}) termino con codigo {resultado.returncode}: {detalle}"
        )
    limpio = _limpiar_salida(resultado.stdout or "")
    if not limpio:
        raise OpencodeOCRError(f"opencode run ({modelo_efectivo}) devolvio salida vacia")
    return limpio
