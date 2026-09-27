"""Generacion de TEXTO para los papers de Yadira (REQ-096).

Motores (env PAPERS_LLM_ENGINE):
    opencode (default) -> opencode/mimo-v2.6-flash-free (tier FREE,
        grande en tokens, distinto de la cascada z.ai/minimax de
        mortadelo — decision del usuario 27-09).
    gemini -> API de Google (GEMINI_API_KEY). OJO: el prepago puede
        estar agotado (402); con PAPERS_LLM_ENGINE=auto se intenta
        gemini y se cae a opencode si falla.

Variables (en .env):
    PAPERS_LLM_ENGINE        opencode | gemini | auto (default auto:
                             gemini primero, opencode de respaldo)
    PAPERS_OPENCODE_MODEL    default opencode/mimo-v2.6-flash-free
    PAPERS_OPENCODE_TIMEOUT  default 600 (papers largos tardan)
    GEMINI_API_KEY           para el motor gemini
    GEMINI_PAPERS_MODEL      default gemini-3.6-flash
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Callable

import requests
from dotenv import load_dotenv

from src.core.rutas import ROOT
from src.examenes.ocr_opencode import _limpiar_salida

logger = logging.getLogger(__name__)

DEFAULT_MODEL_GEMINI = "gemini-3.6-flash"
DEFAULT_MODEL_OPENCODE = "opencode/mimo-v2.6-flash-free"
_TIMEOUT_GEMINI = 240  # papers largos tardan; generacion no es ping
# El bot corre desde el Programador de Tareas (sin PATH de usuario):
# respaldo absoluto al shim de npm.
_OPENCODE_FALLBACK = os.path.join(
    os.environ.get("APPDATA", ""), "npm", "opencode.cmd"
)


class GeminiTextoError(RuntimeError):
    """Error generando texto (cualquier motor)."""


# ---- Motor Gemini (API de Google) ----


def _generar_gemini(
    prompt: str,
    modelo: str | None,
    post: Callable[..., requests.Response] = requests.post,
) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise GeminiTextoError("GEMINI_API_KEY no esta configurada (ver .env).")
    base = os.getenv("GEMINI_BASE_URL", "").rstrip("/") or (
        "https://generativelanguage.googleapis.com/v1beta"
    )
    modelo = modelo or os.getenv("GEMINI_PAPERS_MODEL", "").strip() or DEFAULT_MODEL_GEMINI
    url = f"{base}/models/{modelo}:generateContent"
    try:
        resp = post(
            url,
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=_TIMEOUT_GEMINI,
        )
        resp.raise_for_status()
        candidatos = resp.json().get("candidates", [])
        if not candidatos:
            raise GeminiTextoError("respuesta sin candidatos (posible filtro)")
        partes = candidatos[0].get("content", {}).get("parts", [])
        texto = "".join(p.get("text", "") for p in partes).strip()
        if not texto:
            raise GeminiTextoError("candidato sin texto")
        return texto
    except requests.RequestException as e:
        raise GeminiTextoError(f"request fallo: {e}") from e
    except (KeyError, ValueError) as e:
        raise GeminiTextoError(f"respuesta malformada: {e}") from e


# ---- Motor opencode (mimo, tier free) ----


def _exe_opencode() -> str:
    exe = shutil.which("opencode")
    if exe:
        return exe
    if os.path.isfile(_OPENCODE_FALLBACK):
        return _OPENCODE_FALLBACK
    raise GeminiTextoError("CLI de opencode no encontrada (PATH ni npm).")


def _generar_opencode(prompt: str, modelo: str | None) -> str:
    modelo = modelo or os.getenv("PAPERS_OPENCODE_MODEL", "").strip() or DEFAULT_MODEL_OPENCODE
    timeout = int(os.getenv("PAPERS_OPENCODE_TIMEOUT", "600"))
    # El CLI de opencode TRUNCA el mensaje en los saltos de linea reales
    # del argv (el modelo recibe solo la primera linea y responde que
    # "no llego el texto"). Prompt a UNA linea; el modelo sigue pudiendo
    # responder con formato multilinea.
    prompt_plano = " ".join(prompt.split())
    # cwd NEUTRAL: con cwd=repo el agente carga el contexto del proyecto
    # (AGENTS.md, codigo) y responde como asistente de programacion en
    # vez de procesar el prompt tal cual.
    import tempfile

    try:
        resultado = subprocess.run(
            # --standalone: servidor privado por corrida. Sin el flag, el
            # servicio en background comparte el contexto del proyecto y
            # el modelo lee el codigo fuente del repo en vez del prompt
            # (mimo citaba oferta_papers.py dentro de sus respuestas).
            [_exe_opencode(), "run", "--standalone", "--model", modelo, prompt_plano],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=tempfile.gettempdir(),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise GeminiTextoError(f"opencode timeout de {timeout}s") from e
    if resultado.returncode != 0:
        detalle = (resultado.stderr or resultado.stdout or "")[:200]
        raise GeminiTextoError(
            f"opencode run ({modelo}) termino con codigo {resultado.returncode}: {detalle}"
        )
    limpio = _limpiar_salida(resultado.stdout or "")
    if not limpio:
        raise GeminiTextoError(f"opencode run ({modelo}) devolvio salida vacia")
    return limpio


# ---- API publica ----


def generar_texto(
    prompt: str,
    modelo: str | None = None,
    post: Callable[..., requests.Response] = requests.post,
) -> str:
    """Genera texto con el motor configurado (ver docstring del modulo).

    auto (default): gemini primero; si falla (prepago agotado, 402/404,
    red), cae a opencode/mimo sin perder la solicitud.
    """
    load_dotenv()
    engine = os.getenv("PAPERS_LLM_ENGINE", "auto").strip().lower()
    if engine in ("gemini", "auto"):
        try:
            return _generar_gemini(prompt, modelo, post)
        except GeminiTextoError as e:
            if engine == "gemini":
                raise
            logger.warning("[papers-llm] gemini fallo (%s); caigo a opencode", e)
    return _generar_opencode(prompt, modelo)
