"""Cliente de vision Google Gemini para transcribir examenes (REQ-061).

Motor DEFAULT del bot (decision del usuario 21-09-2026: usar Gemini).
REST puro via requests, mismo patron que vision_api.py (z.ai, que queda
como respaldo seleccionable via OCR_ENGINE=zai). Cero dependencias nuevas.

Config (en .env, nunca en el repo):
    GEMINI_API_KEY    API key de Google AI Studio
    GEMINI_BASE_URL   default https://generativelanguage.googleapis.com/v1beta
    GEMINI_OCR_MODEL  default gemini-2.5-flash
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import requests

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.5-flash"
_TIMEOUT_SEGUNDOS = 120

# Prompt de transcripcion fiel: el modelo SOLO transcribe, no interpreta
# ni diagnostica (REQ-001: los agentes no deciden diagnosticos).
PROMPT_TRANSCRIPCION = (
    "Transcribe fielmente TODO el texto visible de esta imagen de examen "
    "medico (encabezados, tablas con sus columnas y valores, unidades, "
    "rangos de referencia, pie de pagina). NO interpretes resultados, NO "
    "agregues datos que no esten escritos, NO diagnostiques. Si algo es "
    "ilegible, escribe [ilegible]. Devuelve unicamente la transcripcion."
)


class GeminiAPIError(RuntimeError):
    """Error llamando a la API de Gemini (clave faltante, HTTP, etc.)."""


_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def _config() -> tuple[str, str, str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GeminiAPIError(
            "GEMINI_API_KEY no esta configurada (ver .env.example). "
            "La transcripcion no puede correr sin ella."
        )
    base_url = os.getenv("GEMINI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    modelo = os.getenv("GEMINI_OCR_MODEL", DEFAULT_MODEL)
    return api_key, base_url, modelo


def transcribir_imagen(
    image_path: Path,
    prompt: str = PROMPT_TRANSCRIPCION,
    api_key: str | None = None,
    base_url: str | None = None,
    modelo: str | None = None,
    timeout: int = _TIMEOUT_SEGUNDOS,
) -> str:
    """Envia una imagen a Gemini y devuelve la transcripcion.

    Args:
        image_path: ruta local a la foto (.jpg/.png/.webp/...).
        prompt: instruccion para el modelo (default: transcripcion fiel).
        api_key/base_url/modelo: inyectables para tests; default = env.

    Raises:
        GeminiAPIError: clave faltante, error HTTP o respuesta malformada.
    """
    key_env, url_env, modelo_env = _config()
    api_key = api_key or key_env
    base_url = (base_url or url_env).rstrip("/")
    modelo = modelo or modelo_env
    mime = _MIME_TYPES.get(image_path.suffix.lower(), "image/jpeg")
    payload_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

    try:
        resp = requests.post(
            f"{base_url}/models/{modelo}:generateContent",
            headers={"x-goog-api-key": api_key},
            json={
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": mime, "data": payload_b64}},
                        ]
                    }
                ],
                "generationConfig": {"temperature": 0},
            },
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise GeminiAPIError(f"Error de red llamando a Gemini: {e}") from e

    if resp.status_code != 200:
        raise GeminiAPIError(f"Gemini respondio HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        partes = resp.json()["candidates"][0]["content"]["parts"]
        texto = "".join(str(p.get("text", "")) for p in partes)
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise GeminiAPIError(f"Respuesta malformada de Gemini: {resp.text[:300]}") from e
    if not texto.strip():
        raise GeminiAPIError("Gemini devolvio una transcripcion vacia")
    return texto.strip()
