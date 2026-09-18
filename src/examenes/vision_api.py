"""Cliente de vision z.ai para transcribir examenes (paso 2b, REQ-047).

Sin OCR local (decision del usuario 18-09-2026): las fotos de examenes
se transcriben con la API de z.ai (GLM vision) via requests. Cero
dependencias nuevas.

Config (en .env, nunca en el repo):
    ZAI_API_KEY       API key de z.ai
    ZAI_BASE_URL      default https://api.z.ai/api/paas/v4
    ZAI_VISION_MODEL  default glm-4.5v
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import requests

DEFAULT_BASE_URL = "https://api.z.ai/api/paas/v4"
DEFAULT_MODEL = "glm-4.5v"
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


class VisionAPIError(RuntimeError):
    """Error llamando a la API de vision (clave faltante, HTTP, etc.)."""


def _config() -> tuple[str, str, str]:
    api_key = os.getenv("ZAI_API_KEY", "").strip()
    if not api_key:
        raise VisionAPIError(
            "ZAI_API_KEY no esta configurada (ver .env.example). "
            "El paso 2b no puede correr sin ella."
        )
    base_url = os.getenv("ZAI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    modelo = os.getenv("ZAI_VISION_MODEL", DEFAULT_MODEL)
    return api_key, base_url, modelo


def _imagen_a_data_url(image_path: Path) -> str:
    ext = image_path.suffix.lower().lstrip(".")
    ext = "jpeg" if ext in ("jpg", "jpeg") else ext
    payload = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/{ext};base64,{payload}"


def transcribir_imagen(
    image_path: Path,
    prompt: str = PROMPT_TRANSCRIPCION,
    api_key: str | None = None,
    base_url: str | None = None,
    modelo: str | None = None,
    timeout: int = _TIMEOUT_SEGUNDOS,
) -> str:
    """Envia una imagen a la API de vision y devuelve la transcripcion.

    Args:
        image_path: ruta local a la foto (.jpg/.png/.webp/...).
        prompt: instruccion para el modelo (default: transcripcion fiel).
        api_key/base_url/modelo: inyectables para tests; default = env.

    Raises:
        VisionAPIError: clave faltante, error HTTP o respuesta malformada.
    """
    key_env, url_env, modelo_env = _config()
    api_key = api_key or key_env
    base_url = (base_url or url_env).rstrip("/")
    modelo = modelo or modelo_env

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": modelo,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": _imagen_a_data_url(image_path)},
                            },
                        ],
                    }
                ],
            },
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise VisionAPIError(f"Error de red llamando a z.ai: {e}") from e

    if resp.status_code != 200:
        raise VisionAPIError(f"z.ai respondio HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        contenido = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        raise VisionAPIError(f"Respuesta malformada de z.ai: {resp.text[:300]}") from e
    if not contenido or not str(contenido).strip():
        raise VisionAPIError("z.ai devolvio una transcripcion vacia")
    return str(contenido).strip()
