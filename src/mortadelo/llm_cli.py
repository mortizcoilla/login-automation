"""Llamada al LLM via CLI de opencode, con seleccion de modelos por cascada.

REQ-055: motor exclusivo = opencode CLI (agente .opencode/agent/mortadelo.md
con el rol v2 aprobado). La cascada intenta cada modelo en orden y usa el
primero que responda; el modelo usado lo reporta el CODIGO (el LLM no se
autoreporta).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

from src.core.rutas import ROOT

# Cascada por defecto. Override: env MORTADELO_MODELOS="modelo1,modelo2".
MODELOS_DEFAULT = ["opencode/nemotron-3-ultra-free"]
TIMEOUT_DEFAULT = 300  # segundos por llamada

# Codigos ANSI que opencode deja en la salida.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class LLMError(RuntimeError):
    """Todos los modelos de la cascada fallaron."""


def modelos_cascada() -> list[str]:
    crudo = os.getenv("MORTADELO_MODELOS", "").strip()
    if not crudo:
        return list(MODELOS_DEFAULT)
    return [m.strip() for m in crudo.split(",") if m.strip()]


def _limpiar_salida(texto: str) -> str:
    """Quita ANSI y el encabezado del CLI ('\n> agente - modelo\n\n').

    El encabezado de opencode es UNA linea '> algo · modelo' al inicio;
    el contenido puede empezar con blockquotes legitimos ('> **Motivo
    de atencion:**...'), que NO se tocan.
    """
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


def _invocar(modelo: str, prompt: str, timeout: int) -> str:
    exe = shutil.which("opencode")
    if not exe:
        raise LLMError("CLI de opencode no encontrado en PATH")
    resultado = subprocess.run(
        [exe, "run", "--agent", "mortadelo", "--model", modelo],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        timeout=timeout,
    )
    if resultado.returncode != 0:
        raise LLMError(
            f"opencode run ({modelo}) termino con codigo "
            f"{resultado.returncode}: {resultado.stderr[:200]}"
        )
    limpio = _limpiar_salida(resultado.stdout or "")
    if not limpio:
        raise LLMError(f"opencode run ({modelo}) devolvio salida vacia")
    return limpio


def llm_run(
    prompt: str,
    modelos: list[str] | None = None,
    timeout: int | None = None,
) -> tuple[str, str]:
    """Ejecuta el prompt con la cascada de modelos.

    Returns:
        (texto_respuesta, modelo_usado).

    Raises:
        LLMError: si ningun modelo de la cascada responde.
    """
    candidatos = modelos or modelos_cascada()
    timeout = timeout or int(os.getenv("MORTADELO_TIMEOUT", str(TIMEOUT_DEFAULT)))
    errores: list[str] = []
    for modelo in candidatos:
        try:
            return _invocar(modelo, prompt, timeout), modelo
        except subprocess.TimeoutExpired:
            errores.append(f"{modelo}: timeout {timeout}s")
        except LLMError as e:
            errores.append(f"{modelo}: {e}")
    raise LLMError("Cascada agotada. " + " | ".join(errores))


if __name__ == "__main__":  # smoke manual: python -m src.mortadelo.llm_cli
    texto, modelo = llm_run("Responde exclusivamente con la palabra: OK")
    print(f"[{modelo}] {texto[:80]}")
    sys.exit(0 if texto.startswith("OK") else 1)
