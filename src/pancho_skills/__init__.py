"""Pancho skills — capa de wrappers sobre browser_automation con API limpia.

Estas skills son las únicas que Pilita y Teodoro pueden invocar para interactuar
con Rayen APS. Cada skill:

- Recibe un WebDriver ya autenticado (excepto `login_rayen`)
- Retorna tipos estructurados (dataclasses) en vez de dicts
- Valida el principio de aprobación humana (cuando aplica)
- Loguea cada acción con el prefijo `[pancho]`
- NO toma decisiones clínicas — solo ejecuta

Skills implementadas:
    - login_rayen: autentica en Rayen
    - listar_iniciados: devuelve fichas en estado "Iniciado"
    - leer_ficha: lee el contenido de una ficha específica

Skills pendientes (stubs con TODOs):
    - obtener_historial: trae historial clínico y farma del paciente
    - enviar_ficha: envía una ficha a Rayen (requiere token de aprobación)
"""

from src.pancho_skills.enviar import (
    ResultadoEnvio,
    enviar_ficha,
)
from src.pancho_skills.historial import (
    HistorialCompleto,
    obtener_historial,
)
from src.pancho_skills.leer_ficha import (
    FichaDetalle,
    leer_ficha,
)
from src.pancho_skills.listar_iniciados import (
    PacienteIniciado,
    listar_iniciados,
)
from src.pancho_skills.login import login_rayen

__all__ = [
    "FichaDetalle",
    "HistorialCompleto",
    "PacienteIniciado",
    "ResultadoEnvio",
    "enviar_ficha",
    "leer_ficha",
    "listar_iniciados",
    "login_rayen",
    "obtener_historial",
]
