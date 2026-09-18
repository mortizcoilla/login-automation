"""Shim de compatibilidad: el nucleo de Selenium vive en src.rayen.*.

Historico: este modulo fue el nucleo Selenium (login, navegacion,
tabla). Desde la refactorizacion 2026-09-18 (Fase 3a) esta dividido en:

- src/rayen/navegador.py  (Chrome, login, sesion, capturas)
- src/rayen/navegacion.py (select_date, sort_by_estado, volver_a_pacientes)
- src/rayen/tabla.py      (filas, datos, match de paciente)

Este archivo solo re-exporta para no romper imports existentes
(pancho_skills, tests de headless/env). El codigo nuevo debe importar
desde src.rayen.* directamente.
"""

from __future__ import annotations

from src.rayen.navegacion import select_date, sort_by_estado
from src.rayen.navegador import (
    _SELECTORS,
    HEADLESS_DEFAULT,
    NAVIGATION_TIMEOUT,
    SCREENSHOTS_DIR,
    TIMEOUT_SECONDS,
    _build_chrome_options,
    _capture_after_click,
    _capture_error,
    _cerrar_alertas,
    _env_bool,
    _es_url_login,
    _hide_modal,
    _load_selectors,
    _make_wait,
    _resolve_headless,
    _select,
    _wait_loading_modal_gone,
    ensure_session_alive,
    login_url,
    run_login,
    safe_quit,
    separador,
)
from src.rayen.tabla import (
    extraer_datos_fila,
    get_pacientes_del_dia,
    get_pacientes_iniciados,
)

__all__ = [
    "HEADLESS_DEFAULT",
    "NAVIGATION_TIMEOUT",
    "SCREENSHOTS_DIR",
    "TIMEOUT_SECONDS",
    "_SELECTORS",
    "_build_chrome_options",
    "_capture_after_click",
    "_capture_error",
    "_cerrar_alertas",
    "_env_bool",
    "_es_url_login",
    "_hide_modal",
    "_load_selectors",
    "_make_wait",
    "_resolve_headless",
    "_select",
    "_wait_loading_modal_gone",
    "ensure_session_alive",
    "extraer_datos_fila",
    "get_pacientes_del_dia",
    "get_pacientes_iniciados",
    "login_url",
    "run_login",
    "safe_quit",
    "select_date",
    "separador",
    "sort_by_estado",
]
