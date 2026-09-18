"""Capa Rayen: todo lo que toca el sistema Rayen via Selenium.

Modulos (Fase 3a):
- navegador: Chrome, login, vida de sesion, capturas de diagnostico.
- navegacion: fecha, orden por estado, volver a 'Pacientes citados'.
- tabla: filas de la tabla del dia, datos por fila, match de paciente.
- extraccion: (Fase 3c) extractores por seccion de la ficha abierta.
"""

from src.rayen.navegacion import (
    select_date,
    sort_by_estado,
    volver_a_pacientes_citados,
)
from src.rayen.navegador import (
    HEADLESS_DEFAULT,
    ensure_session_alive,
    login_url,
    run_login,
    safe_quit,
    separador,
)
from src.rayen.tabla import (
    _buscar_paciente_en_tabla,
    _doble_click_en_paciente,
    extraer_datos_fila,
    get_pacientes_del_dia,
    get_pacientes_iniciados,
)

__all__ = [
    "HEADLESS_DEFAULT",
    "_buscar_paciente_en_tabla",
    "_doble_click_en_paciente",
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
    "volver_a_pacientes_citados",
]
