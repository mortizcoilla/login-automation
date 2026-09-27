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
DEFAULT_MODEL_OPENCODE = "opencode/mimo-v2.6-flash-free"  # rapido: mini-resumenes
# Calidad para traducciones largas (nvidia = free en opencode; GO es
# el plan pago del usuario y NO se usa aqui). Lento pero mejor texto.
DEFAULT_MODEL_TRADUCCION = "nvidia/z-ai/glm-5.3-flash"
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


def _generar_opencode(prompt: str, modelos: str | None) -> str:
    """Corre opencode con una CADENA de modelos (separados por coma).

    El primer modelo que devuelva texto gana; los muertos (HTTP 410 de
    endpoints retirados) o vacios se saltan. El usuario paga GO; los
    modelos por defecto aqui son los FREE (opencode/mimo y nvidia).
    """
    if not modelos:
        modelos = os.getenv(
            "PAPERS_OPENCODE_MODELS", ""
        ).strip() or f"{DEFAULT_MODEL_OPENCODE},{DEFAULT_MODEL_TRADUCCION}"
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

    ultimo_error: Exception | None = None
    for modelo in [m.strip() for m in modelos.split(",") if m.strip()]:
        try:
            resultado = subprocess.run(
                # --standalone: servidor privado por corrida. Sin el flag,
                # el servicio en background comparte el contexto del
                # proyecto y el modelo lee el codigo fuente del repo.
                [_exe_opencode(), "run", "--standalone", "--model", modelo, prompt_plano],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=tempfile.gettempdir(),
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            ultimo_error = e
            logger.warning("[papers-llm] %s timeout (%ss); siguiente", modelo, timeout)
            continue
        if resultado.returncode != 0:
            detalle = (resultado.stderr or resultado.stdout or "")[:160]
            ultimo_error = GeminiTextoError(
                f"opencode run ({modelo}) codigo {resultado.returncode}: {detalle}"
            )
            logger.warning("[papers-llm] %s fallo; siguiente", modelo)
            continue
        limpio = _limpiar_salida(resultado.stdout or "")
        if not limpio:
            ultimo_error = GeminiTextoError(f"opencode run ({modelo}) salida vacia")
            logger.warning("[papers-llm] %s salida vacia; siguiente", modelo)
            continue
        return limpio
    raise GeminiTextoError(f"todos los modelos fallaron: {ultimo_error}")


# ---- API publica ----


def generar_texto(
    prompt: str,
    modelo: str | None = None,
    post: Callable[..., requests.Response] = requests.post,
) -> str:
    """Genera texto con el motor configurado (ver docstring del modulo).

    auto (default): gemini primero; si falla (prepago agotado, 402/404,
    red), cae a opencode/mimo sin perder la solicitud. `modelo` admite
    una cadena "modelo1,modelo2" (solo opencode: prueba en orden).
    """
    load_dotenv()
    engine = os.getenv("PAPERS_LLM_ENGINE", "auto").strip().lower()
    es_cadena = modelo is not None and "," in modelo
    if engine in ("gemini", "auto") and not es_cadena:
        try:
            return _generar_gemini(prompt, modelo, post)
        except GeminiTextoError as e:
            if engine == "gemini":
                raise
            logger.warning("[papers-llm] gemini fallo (%s); caigo a opencode", e)
    return _generar_opencode(prompt, modelo)
