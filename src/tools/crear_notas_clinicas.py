"""Abre la ficha de UN paciente en Rayen.

Hace exactamente:
  1. Login en Rayen
  2. Navega hasta la pagina de Pacientes citados
  3. Selecciona la fecha indicada
  4. Busca al paciente por nombre completo
  5. Doble click sobre su nombre para abrir la ficha
  6. Se queda en la pantalla con la informacion del paciente

Ejemplo de uso (Monserrat):
    python -m src.tools.crear_notas_clinicas --paciente "Monserrat Sofia Delgado Ramirez" --fecha 05-08-2026

Reglas:
- Procesa UN SOLO paciente por ejecucion.
- Login con ventana visible para que el operador valide.
- No modifica nada fuera de este script.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from selenium.webdriver.remote.webdriver import WebDriver

# Forzar UTF-8 en consola Windows
with contextlib.suppress(AttributeError, OSError):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from src.core.rutas import ROOT

sys.path.insert(0, str(ROOT))

from src.core.nombres import safe_filename as _core_safe_filename
from src.rayen.extraccion.atencion_actual import (
    click_atencion_actual,
    extraer_anamnesis,
    extraer_motivo_consulta,
)
from src.rayen.extraccion.diagnosticos import (
    extraer_actividades,
    extraer_diagnosticos,
    extraer_profesionales,
)
from src.rayen.extraccion.estratificacion import (
    extraer_estratificacion_ecicep,
    formatear_estratificacion,
)
from src.rayen.extraccion.historial import (
    extraer_historial,
    filtrar_historial_ultimos_6_meses,
)
from src.rayen.extraccion.identificacion import _wait_visible, extraer_identificacion
from src.rayen.extraccion.plan import (
    _filtrar_receta_mas_reciente,
    _tipo_atencion_es_recetas,
    extraer_laboratorio,
    extraer_recetas,
)
from src.rayen.navegacion import (
    select_date,
    sort_by_estado,
    volver_a_pacientes_citados,
)
from src.rayen.navegador import ensure_session_alive, run_login, safe_quit
from src.rayen.tabla import (
    _buscar_paciente_en_tabla,
    _doble_click_en_paciente,
)
from src.tools.informe_tecnico import (
    PacienteInforme,
    WarningsCollector,
    generar_informe_tecnico,
)


def _informe_mes_actual_path() -> Path:
    """Wrapper local para mantener el contrato con el resto del modulo.

    La implementacion real vive en `src.analysis.informe_paths` (single
    source of truth, sesion 2026-09-09).
    """
    from src.analysis.informe_paths import informe_mes_actual_path

    return informe_mes_actual_path()


INFORME_DEFAULT = _informe_mes_actual_path()
USERS_CONFIG = ROOT / "config" / "users.json"


# ---- Estructura del paciente objetivo ----


@dataclass
class PacienteObjetivo:
    """Un paciente del informe de fichas abiertas a procesar."""

    fecha: str
    nombre: str
    tipo_atencion: str
    razon: str = ""
    # Nombre real en Rayen. Se llena solo si difiere del nombre del
    # informe (caso de match parcial por truncamiento). El nombre del
    # informe sigue siendo el canonico para el filename; este campo
    # es solo metadato para que Mortadelo pueda matchear.
    nombre_rayen: str | None = None
    # Sesion 2026-09-16: flag que paso_4_1_abrir_ficha setea segun si
    # el panel del paciente cargo o no. Si False, guardar_nota_clinica()
    # escribe una nota con placeholder + "REVISION MANUAL" para que
    # Yadira sepa que tiene que completar la ficha a mano.
    panel_cargo: bool = True


# ---- Carga de credenciales (reutiliza patron de main.py) ----


def load_credentials(user_id: str) -> dict[str, str]:
    """Carga credenciales desde config/users.json."""
    if not USERS_CONFIG.exists():
        raise FileNotFoundError(f"No existe {USERS_CONFIG}")
    data = json.loads(USERS_CONFIG.read_text(encoding="utf-8"))
    users = data.get("users", {})
    if user_id not in users:
        raise ValueError(f"Usuario '{user_id}' no esta en {USERS_CONFIG}")
    credenciales: dict[str, str] = users[user_id]
    return credenciales


def list_known_users() -> list[str]:
    if not USERS_CONFIG.exists():
        return []
    data = json.loads(USERS_CONFIG.read_text(encoding="utf-8"))
    return list(data.get("users", {}).keys())


# ---- Parser del informe de fichas abiertas ----


def parsear_informe(ruta: Path) -> list[PacienteObjetivo]:
    """Lee el informe y devuelve la lista de pacientes objetivo.

    Mismo formato que usa mortadelo_batch._parsear_informe:
        dd-mm-yyyy  NOMBRE  TIPO_ATENCION  RAZON
    """
    if not ruta.exists():
        return []
    contenido = ruta.read_text(encoding="utf-8")
    # Prefijos que Rayen pone en el informe pero NO son parte del nombre
    # real del paciente. Hay que quitarlos para que el match contra
    # la tabla de Rayen funcione (alli aparece solo el nombre limpio).
    prefijo_patron = re.compile(
        r"^\s*\(?\s*(atenci[oó]n preferente|prioritario|urgente)\s*\)?\s*",
        re.IGNORECASE,
    )
    # Sesion 2026-09-09: el informe ahora puede traer la columna Edad
    # entre Nombre y Tipo. El regex anterior (`[A-Za-z]` para el 3er
    # campo) hacia backtracking e INCLUIA el "(-)" de Edad dentro del
    # nombre, produciendo nombres corruptos como
    # "Lisette Jara Gajardo              (-)" que Rayen no encuentra.
    # Migramos a re.split() y asignamos segun el conteo de columnas.
    #   6 cols: Fecha | Nombre | Edad | Tipo | Motivo | Plantilla
    #   5 cols: Fecha | Nombre | Tipo | Motivo | Plantilla (legacy)
    #   4 cols: Fecha | Nombre | Tipo | Plantilla (mas legacy)
    out: list[PacienteObjetivo] = []
    for line in contenido.splitlines():
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 4:
            continue
        if not re.match(r"^\d{2}-\d{2}-\d{4}$", parts[0]):
            continue
        fecha = parts[0]
        if len(parts) >= 6:
            nombre = parts[1]
            tipo_atencion = parts[3]
            motivo = parts[4]
        elif len(parts) == 5:
            nombre = parts[1]
            tipo_atencion = parts[2]
            motivo = parts[3]
        else:  # 4 cols (legacy, sin motivo)
            nombre = parts[1]
            tipo_atencion = parts[2]
            motivo = ""
        nombre_limpio = prefijo_patron.sub("", nombre).strip()
        out.append(
            PacienteObjetivo(
                fecha=fecha.strip(),
                nombre=nombre_limpio,
                tipo_atencion=tipo_atencion.strip(),
                razon=motivo.strip(),  # compat: 'razon' es el nombre del campo
            )
        )
    return out


# ---- Paso 4.1: filtrar por fecha, buscar nombre, doble click ----


# ---- REQ-017: limite de Rayen - solo 8 fichas por sesion (reset al llegar) ----
MAX_FICHAS_POR_SESION = 8

# Directorio que Chrome usa para bajar archivos (prefs de Chrome en
# run_login). El cache de descargas queda como subdirectorio _chrome_dl/
# (gitignored). Los adjuntos ya no se procesan (REQ-033), pero el
# download_dir sigue configurado para que Chrome nunca muestre dialogos.
from src.core.rutas import ADJUNTOS_DIR

ADJUNTOS_DOWNLOAD_DIR = ADJUNTOS_DIR / "_chrome_dl"


# ---- Paso 4.3: guardar nota clinica en archivo .txt ----


def _safe_filename(s: str) -> str:
    """Convierte un nombre a filename seguro (delega en core.nombres)."""
    return _core_safe_filename(s)


from src.core.rutas import ANAMNESIS_DIR as ANAMNESIS_BACKUP_DIR

# Documento complementario a la nota clinica: contiene TODA la info del
# paciente EXCEPTO la anamnesis cruda de Yadira. Es para "mirar al
# paciente de un vistazo" sin ver el texto libre de la consulta.
# Sesion 2026-09-16 17:45 (pedido Yadira):
#   data/notas_clinicas/<paciente>_<fecha>.md   <- nota completa (incluye anamnesis)
#   data/anamnesis/<paciente>_<fecha>.md        <- solo anamnesis cruda (respaldo)
#   data/info_paciente/<paciente>_<fecha>.md    <- todo MENOS la anamnesis (NUEVO)
from src.core.rutas import INFO_PACIENTE_DIR


# REQ-026/027: motivo nunca vacio; respaldo anam_<pac>_<fecha>.md.
def guardar_respaldo_anamnesis(
    paciente: PacienteObjetivo,
    anamnesis: str,
    motivo_consulta: str = "",
    backup_dir: Path = ANAMNESIS_BACKUP_DIR,
) -> Path | None:
    """Escribe un respaldo de la anamnesis cruda de Yadira en un .md
    liviano en `anamnesis/<safe_nombre>_<fecha>.md`.

    Sesion 2026-09-16 15:14 (regla Yadira): Yadira quiere un respaldo
    de las anamnesis que escribe en Rayen, separado de las notas
    clinicas completas.

    Sesion 2026-09-16 15:27 (segundo feedback Yadira): el respaldo
    tambien debe incluir el motivo de atencion. Yadira escribe primero
    el motivo y despues la anamnesis.

    Sesion 2026-09-16 15:35 (tercer feedback Yadira): el motivo de
    atencion JAMAS estara vacio. Mismo principio que la anamnesis
    (regla dura Yadira: la anamnesis SIEMPRE existe). Cuando Yadira
    abre una ficha en Rayen, el sistema la obliga a llenar primero el
    motivo de atencion y despues la anamnesis. Por lo tanto, si el
    extractor retorna motivo vacio es un bug, NO un caso normal.
    Esta funcion SIEMPRE escribe el blockquote del motivo (aunque sea
    vacio, como senal visible de bug del extractor).

    Solo respalda si la anamnesis NO esta vacia (no respalda
    extracciones fallidas). El sobreescribir es OK: la ultima
    extraccion es la que vale.

    Returns:
        Path al .md escrito, o None si la anamnesis estaba vacia.
    """
    if not (anamnesis or "").strip():
        return None
    # Sesion 2026-09-16 18:45: prefijo "anam_" para distinguir el
    # respaldo de anamnesis de la nota clinica y del info_paciente.
    nombre_archivo = f"anam_{_safe_filename(paciente.nombre)}_{paciente.fecha}.md"
    out_path = backup_dir / nombre_archivo

    md = ["---"]
    md.append(f'paciente: "{paciente.nombre}"')
    md.append(f'fecha_atencion: "{paciente.fecha}"')
    if paciente.nombre_rayen and paciente.nombre_rayen != paciente.nombre:
        md.append(f'paciente_rayen: "{paciente.nombre_rayen}"')
    md.append('fuente: "Rayen APS - CESFAM Raul Cuevas, San Bernardo"')
    md.append('source_url: "https://clinico.rayenaps.cl/"')
    md.append(f'fecha_extraccion: "{_now_iso()}"')
    md.append("---")
    md.append("")
    # Regla Yadira 2026-09-16 15:35: el motivo SIEMPRE existe. Lo
    # escribimos siempre, aunque venga vacio (eso es senal de bug del
    # extractor, no un caso normal).
    md.append(f"> **Motivo de atencion:** {motivo_consulta.strip()}")
    md.append("")
    md.append(anamnesis.strip())
    md.append("")

    backup_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md), encoding="utf-8")
    return out_path


# REQ-020/021/022: anamnesis vacia=ValueError; nota SIEMPRE se sobrescribe;
# validacion post-write con re-fetch de bloques vacios. Ver docs/REQUISITOS.md.
def guardar_nota_clinica(
    paciente: PacienteObjetivo,
    identificacion: dict[str, str],
    historial: str,
    anamnesis: str,
    diagnosticos: list[str],
    actividades: list[str],
    profesionales: list[str],
    pautas: list[str],
    examenes: str = "",
    otros_items: dict[str, str] | None = None,
    estratificacion: dict[str, Any] | None = None,
    motivo_consulta: str = "",
    recetas: list[str] | None = None,
    laboratorio: list[str] | None = None,
    notas_dir: Path | None = None,
    panel_cargo: bool = True,
) -> Path | None:
    """Guarda la nota clinica extraida en un .md en armonia con manuales_md.

    Sesion 2026-09-16: cambio de .txt con marcadores '=== INICIO/FIN ==='
    a markdown con frontmatter YAML + headers (##). Mismo formato que
    `manuales_md/<basename>/<basename>.md`. Esto permite que Yadira, el
    LLM y los scripts que parsean manuales trabajen sobre una sola
    estructura.

    Sesion 2026-09-16 14:14 (regla Yadira): el script SIEMPRE escribe
    el archivo (sobrescribe si existe). El script NO depende de la
    existencia de un archivo previo para arrancar ni para decidir que
    hacer; cada corrida arranca fresca desde Rayen. Si la extraccion
    falla (anamnesis vacia, panel no cargo), ValueError y el archivo
    NO se escribe en absoluto (eso lo cubre el try/except del pipeline
    y el test de rechazo correspondiente).

    Estructura del .md generado:
        ---
        <frontmatter YAML>
        ---
        # Nota clinica - <paciente>
        (flag si panel no cargo)
        ## Identificacion
        ## Historial de atenciones (ultimos 6 meses)
        ## Nota clinica de Yadira
        ## Diagnosticos
        ## Estratificacion ECICEP (solo si hay grupo)
        ## Actividades
        ## Profesionales
        ## Plan - Recetas
        ## Plan - Laboratorio

    La seccion ESTRATIFICACION ECICEP solo aparece si el paciente esta
    estratificado (la extraccion devolvio un grupo). Va entre
    DIAGNOSTICOS y ACTIVIDADES, porque es informacion del sistema
    (no de la atencion actual) que sirve para el ECICEP.

    El motivo de consulta (si lo hay) va DENTRO de la seccion
    "Nota clinica de Yadira" como blockquote en la primera linea.

    El historial de atenciones se filtra a las entradas de los ultimos
    6 meses respecto a paciente.fecha.

    Raises:
        ValueError: si `anamnesis` esta vacia. Regla dura de Yadira
            (sesion 2026-09-16): Rayen SIEMPRE tiene la anamnesis
            escrita por la doctora al abrir la ficha. Si la extraccion
            no la encontro, es un bug del extractor y el archivo NO se
            debe escribir (nota sin anamnesis no sirve). El pipeline
            caller atrapa la excepcion y marca al paciente como error.
    """
    if otros_items is None:
        otros_items = {}
    if recetas is None:
        recetas = []
    if laboratorio is None:
        laboratorio = []
    _log = logging.getLogger("crear_notas_clinicas")
    if not (anamnesis or "").strip():
        _log.error(
            f"[crear_notas] {paciente.nombre}: anamnesis vacia. "
            f"Rayen SIEMPRE tiene la anamnesis escrita por Yadira al "
            f"abrir la ficha (regla dura). Extraccion fallo: NO se "
            f"escribe la nota. panel_cargo={panel_cargo}."
        )
        raise ValueError(
            f"anamnesis vacia para {paciente.nombre}: la extraccion "
            f"fallo (panel_cargo={panel_cargo}). Ver logs de "
            f"`extraer_anamnesis()` y reintentar."
        )
    historial = filtrar_historial_ultimos_6_meses(historial, paciente.fecha, logger=_log)
    if notas_dir is None:
        raise ValueError("guardar_nota_clinica: notas_dir es requerido")
    nombre_archivo = f"{_safe_filename(paciente.nombre)}_{paciente.fecha}.md"
    out_path = notas_dir / nombre_archivo
    # Sesion 2026-09-16 14:14 (regla Yadira): el script NO depende de
    # la existencia de un archivo anterior. Si el archivo ya existe
    # (corrida previa que escribio la misma paciente/fecha), SE
    # SOBREESCRIBE con la extraccion nueva. La diferencia con versiones
    # anteriores: esto es overwrite NATURAL de una nueva corrida, NO
    # una estrategia "leer archivo viejo para mejorar". Si la extraccion
    # falla, NO se reescribe (eso lo maneja el try/except del pipeline).
    notas_dir.mkdir(parents=True, exist_ok=True)

    # ---- Frontmatter YAML ----
    md = ["---"]
    md.append(f'paciente: "{paciente.nombre}"')
    md.append(f'title: "Nota clinica - {paciente.nombre}"')
    md.append(f'fecha_atencion: "{paciente.fecha}"')
    md.append(f'tipo_atencion: "{paciente.tipo_atencion}"')
    if paciente.nombre_rayen and paciente.nombre_rayen != paciente.nombre:
        md.append(f'paciente_rayen: "{paciente.nombre_rayen}"')
    md.append('fuente: "Rayen APS - CESFAM Raul Cuevas, San Bernardo"')
    md.append('source_url: "https://clinico.rayenaps.cl/"')
    md.append(f'fecha_extraccion: "{_now_iso()}"')
    md.append(f'panel_cargo: "{str(panel_cargo).lower()}"')
    md.append("---")
    md.append("")

    # ---- Titulo ----
    md.append(f"# Nota clinica - {paciente.nombre}")
    md.append("")

    # ---- Flag de revision si aplica ----
    if not panel_cargo:
        md.append("> ⚠️ **ATENCION: panel del paciente NO CARGO en Rayen.**")
        md.append("> La nota tiene placeholders. Revisar manualmente en Rayen.")
        md.append("")

    # ---- Secciones ----
    md.append("## Identificacion")
    md.append("")
    if identificacion:
        for k, v in identificacion.items():
            md.append(f"- **{k}:** {v}")
    else:
        md.append("_(no se pudo extraer la tabla de identificacion)_")
    md.append("")

    md.append("## Historial de atenciones (ultimos 6 meses)")
    md.append("")
    md.append(historial or "_(no se pudo extraer el historial)_")
    md.append("")

    md.append("## Nota clinica de Yadira")
    md.append("")
    # Sesion 2026-09-16 (corregido 13:42 tras feedback de Yadira): el
    # bloque Yadira contiene la ANAMNESIS CRUDA que Yadira lleno en
    # Rayen al abrir la ficha. Es el INSUMO PRINCIPAL del flujo:
    # `completar_yadira.py` lee este bloque, lo pasa al LLM junto con
    # los demas bloques estructurados + manuales + conocimiento medico,
    # y el LLM lo enriquece en una version final que Yadira revisa.
    # El resultado del enriquecimiento se guarda en
    # `notas_clinicas_completadas/<paciente>_<fecha>.md`.
    if motivo_consulta:
        md.append(f"> **Motivo de atencion:** {motivo_consulta}")
        md.append("")
    if anamnesis and anamnesis.strip():
        md.append(anamnesis.strip())
    else:
        # Si llegamos aca, el ValueError de arriba deberia haber
        # detenido la escritura. Esto es solo defensa en profundidad.
        md.append("_(sin anamnesis — error de extraccion)_")
    md.append("")

    md.append("## Diagnosticos")
    md.append("")
    if diagnosticos:
        for d in diagnosticos:
            md.append(f"- {d.lstrip('- ')}")  # evitar "- - ..."
    else:
        md.append("_(sin diagnosticos)_")
    md.append("")

    estrat_texto = formatear_estratificacion(estratificacion)
    if estrat_texto:
        md.append("## Estratificacion ECICEP")
        md.append("")
        md.append(estrat_texto)
        md.append("")

    md.append("## Actividades")
    md.append("")
    if actividades:
        for a in actividades:
            md.append(f"- {a}")
    else:
        md.append("_(sin actividades)_")
    md.append("")

    md.append("## Profesionales")
    md.append("")
    if profesionales:
        for p in profesionales:
            md.append(f"- {p}")
    else:
        md.append("_(sin profesionales)_")
    md.append("")

    md.append("## Plan - Recetas")
    md.append("")
    if recetas:
        for r in recetas:
            for i, sub in enumerate(r.split("\n")):
                if i == 0:
                    md.append(f"- {sub}")
                else:
                    md.append(f"  - {sub}")
    else:
        md.append("_(sin recetas)_")
    md.append("")

    md.append("## Plan - Laboratorio")
    md.append("")
    if laboratorio:
        for lab in laboratorio:
            for i, sub in enumerate(lab.split("\n")):
                if i == 0:
                    md.append(f"- {sub}")
                else:
                    md.append(f"  - {sub}")
    else:
        md.append("_(sin ordenes de laboratorio)_")
    md.append("")

    # SCOPE 2026-08-26: bloques quitados (fuera de scope):
    # - PAUTAS
    # - EXAMENES ADJUNTOS
    # - OTROS ITEMS DE LA ATENCION
    # - Plan -> Imagenologia
    # - Plan -> Interconsulta
    out_path.write_text("\n".join(md), encoding="utf-8")
    logger = logging.getLogger("crear_notas_clinicas")
    logger.info(f"[crear_notas] Nota clinica guardada en: {out_path}")
    return out_path


# REQ-028: info_<pac>_<fecha>.md = todo menos anamnesis/motivo.
def guardar_info_paciente(
    paciente,
    identificacion: dict[str, str],
    historial: str,
    diagnosticos: list[str],
    actividades: list[str],
    profesionales: list[str],
    recetas: list[str],
    laboratorio: list[str],
    estratificacion: dict[str, Any] | None = None,
    info_paciente_dir: Path = INFO_PACIENTE_DIR,
    panel_cargo: bool = True,
) -> Path | None:
    """Guarda un md con TODA la info del paciente EXCEPTO la anamnesis.

    Sesion 2026-09-16 17:45 (pedido Yadira): ademas de la nota clinica
    completa (en notas_clinicas/) y del respaldo de anamnesis (en
    anamnesis/), Yadira quiere un documento complementario que tenga
    todo lo del paciente MENOS la anamnesis cruda. Es para "mirar al
    paciente de un vistazo" sin leer el texto libre de la consulta.

    Diferencia con guardar_nota_clinica():
    - NO incluye '## Nota clinica de Yadira' (la anamnesis)
    - NO incluye el motivo de atencion (porque va pegado a la anamnesis)
    - NO incluye `## Examenes adjuntos` (la transcripcion va con la anamnesis)
    - SI incluye todo lo demas: identificacion, historial, diagnosticos,
      actividades, profesionales, recetas, laboratorio, estratificacion

    Naming: <safe_paciente>_<fecha>.md en info_paciente_dir/.
    Misma convencion que notas_clinicas/ y anamnesis/ para que Yadira
    pueda cruzar los 3 archivos por nombre.

    Args:
        paciente: PacienteObjetivo del pipeline.
        identificacion: dict del bloque Identificacion.
        historial: texto crudo del historial de atenciones (6 meses).
        diagnosticos: lista de strings (cada uno es un dx).
        actividades: lista de strings.
        profesionales: lista de strings.
        recetas: lista de strings (puede tener prescripciones compuestas).
        laboratorio: lista de ordenes.
        estratificacion: dict ECICEP opcional (None si no aplica).
        info_paciente_dir: directorio destino (default: data/info_paciente/).
        panel_cargo: si False, marca el frontmatter con flag REVISION.

    Returns:
        Path al .md generado, o None si no se pudo escribir.
    """
    md: list[str] = []

    # ---- Frontmatter YAML (mismo formato canonico del proyecto) ----
    md.append("---")
    md.append(f'paciente: "{paciente.nombre}"')
    md.append(f'title: "Info paciente - {paciente.nombre}"')
    md.append(f'fecha_atencion: "{paciente.fecha}"')
    md.append(f'tipo_atencion: "{paciente.tipo_atencion}"')
    if paciente.nombre_rayen and paciente.nombre_rayen != paciente.nombre:
        md.append(f'paciente_rayen: "{paciente.nombre_rayen}"')
    md.append('fuente: "Rayen APS - CESFAM Raul Cuevas, San Bernardo"')
    md.append('source_url: "https://clinico.rayenaps.cl/"')
    md.append(f'fecha_extraccion: "{_now_iso()}"')
    md.append(f'panel_cargo: "{str(panel_cargo).lower()}"')
    md.append('tipo_documento: "info_paciente (sin anamnesis)"')
    md.append("---")
    md.append("")

    # ---- Header ----
    md.append(f"# Info paciente - {paciente.nombre}")
    md.append("")

    # Si panel no cargo, flag visible (mismo patron que notas_clinicas)
    if not panel_cargo:
        md.append("> ⚠️ **ATENCION: panel del paciente NO CARGO en Rayen.**")
        md.append("> La info tiene placeholders. Revisar manualmente en Rayen.")
        md.append("")

    # ---- Bloques (todos EXCEPTO anamnesis) ----
    md.append("## Identificacion")
    md.append("")
    if identificacion:
        for k, v in identificacion.items():
            md.append(f"- **{k}:** {v}")
    else:
        md.append("_(no se pudo extraer la tabla de identificacion)_")
    md.append("")

    md.append("## Historial de atenciones (ultimos 6 meses)")
    md.append("")
    md.append(historial or "_(no se pudo extraer el historial)_")
    md.append("")

    md.append("## Diagnosticos")
    md.append("")
    if diagnosticos:
        for d in diagnosticos:
            md.append(f"- {d.lstrip('- ')}")  # evitar "- - ..."
    else:
        md.append("_(sin diagnosticos)_")
    md.append("")

    if estratificacion:
        md.append("## Estratificacion ECICEP")
        md.append("")
        # Reutilizamos el helper de notas_clinicas si existe
        estrat_texto = _formatear_estrat_para_info(estratificacion)
        md.append(estrat_texto)
        md.append("")

    md.append("## Actividades")
    md.append("")
    if actividades:
        for a in actividades:
            md.append(f"- {a}")
    else:
        md.append("_(sin actividades)_")
    md.append("")

    md.append("## Profesionales")
    md.append("")
    if profesionales:
        for p in profesionales:
            md.append(f"- {p}")
    else:
        md.append("_(sin profesionales)_")
    md.append("")

    md.append("## Plan - Recetas")
    md.append("")
    if recetas:
        for r in recetas:
            # Las recetas pueden tener sub-items (receta con varias lineas)
            for sub in r.split("\n"):
                if sub.strip():
                    md.append(f"- {sub.strip()}")
    else:
        md.append("_(sin recetas)_")
    md.append("")

    md.append("## Plan - Laboratorio")
    md.append("")
    if laboratorio:
        for lab in laboratorio:
            for sub in lab.split("\n"):
                if sub.strip():
                    md.append(f"- {sub.strip()}")
    else:
        md.append("_(sin ordenes de laboratorio)_")
    md.append("")

    # ---- Escritura ----
    # Sesion 2026-09-16 18:45: prefijo "info_" para distinguir el
    # doc complementario de la nota clinica completa y del respaldo
    # de anamnesis. Asi Yadira puede cruzar los 3 archivos por nombre.
    nombre_archivo = f"info_{_safe_filename(paciente.nombre)}_{paciente.fecha}.md"
    out_path = info_paciente_dir / nombre_archivo

    info_paciente_dir.mkdir(parents=True, exist_ok=True)
    try:
        out_path.write_text("\n".join(md), encoding="utf-8")
    except OSError as e:
        logger = logging.getLogger("crear_notas_clinicas")
        logger.error(f"[crear_notas] No se pudo escribir info_paciente en {out_path}: {e}")
        return None

    logger = logging.getLogger("crear_notas_clinicas")
    logger.info(f"[crear_notas] Info paciente guardada en: {out_path}")
    return out_path


def _formatear_estrat_para_info(estratificacion: dict[str, Any]) -> str:
    """Formatea la estratificacion ECICEP como texto markdown para el doc.

    Sesion 2026-09-16 17:45: helper local para info_paciente.
    Si en el futuro guardar_nota_clinica() cambia el formato, hay que
    actualizar esta funcion tambien para mantener consistencia.
    """
    if not estratificacion:
        return "_(sin estratificacion)_"
    out: list[str] = []
    for k, v in estratificacion.items():
        if isinstance(v, dict):
            out.append(f"**{k}:**")
            for sk, sv in v.items():
                out.append(f"  - {sk}: {sv}")
        elif isinstance(v, list):
            out.append(f"**{k}:**")
            for item in v:
                out.append(f"  - {item}")
        else:
            out.append(f"- **{k}:** {v}")
    return "\n".join(out) if out else "_(sin estratificacion)_"


def _now_iso() -> str:
    """Helper: timestamp ISO 8601 al segundo. Usado para el frontmatter."""
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def _rellenar_bloque_en_nota(nota_path: Path, bloque: str, contenido_nuevo) -> None:
    """Sobrescribe el contenido del bloque dado en el archivo de la nota.

    Sesion 2026-09-16 14:14 (regla Yadira): si validar_nota_clinica
    detecta un bloque faltante y re_extraer_bloque() trajo contenido,
    esta funcion actualiza SOLO ese bloque, manteniendo el resto del
    archivo intacto. Es el "fix" parcial post-write.

    Args:
        nota_path: path al .md a actualizar.
        bloque: nombre del bloque (header `## <nombre>`).
        contenido_nuevo: contenido nuevo del bloque. Puede ser:
            - str (para bloques de texto como anamnesis, historial,
              motivo consulta)
            - list[str] (para bloques de bullets como diagnosticos,
              actividades, recetas)
            - dict[str, str] (para bloques clave-valor como
              identificacion)
        Se serializa al formato markdown apropiado.
    """
    contenido = nota_path.read_text(encoding="utf-8")
    lineas = contenido.splitlines()
    out: list[str] = []
    en_bloque = False
    bloque_reemplazado = False

    # Serializar contenido_nuevo al formato markdown apropiado.
    lineas_nuevas: list[str] = []
    if isinstance(contenido_nuevo, str):
        if contenido_nuevo.strip():
            lineas_nuevas.append(contenido_nuevo.strip())
            lineas_nuevas.append("")
    elif isinstance(contenido_nuevo, list):
        for item in contenido_nuevo:
            lineas_nuevas.append(f"- {item}")
        if lineas_nuevas:
            lineas_nuevas.append("")
    elif isinstance(contenido_nuevo, dict):
        for k, v in contenido_nuevo.items():
            lineas_nuevas.append(f"- **{k}:** {v}")
        if lineas_nuevas:
            lineas_nuevas.append("")

    for i, line in enumerate(lineas):
        if line.startswith(f"## {bloque}"):
            en_bloque = True
            out.append(line)
            out.append("")
            out.extend(lineas_nuevas)
            bloque_reemplazado = True
            # Saltar hasta el siguiente header.
            j = i + 1
            while j < len(lineas) and not lineas[j].startswith("## "):
                j += 1
            continue
        if en_bloque:
            if line.startswith("## "):
                en_bloque = False
                out.append(line)
            # Si estamos en el bloque siendo reemplazado, saltamos.
            continue
        out.append(line)

    if not bloque_reemplazado:
        return  # bloque no encontrado, no hacer nada

    nota_path.write_text("\n".join(out), encoding="utf-8")


# REQ-023: sin markers de fallo; hasta 3 reintentos de anamnesis.
def _reintentar_extraccion_anamnesis(
    driver: WebDriver,
    logger: logging.Logger,
    paciente: PacienteObjetivo,
    click_ok: bool,
    identificacion: dict[str, str],
    historial: str,
    diagnosticos: list[str],
    actividades: list[str],
    profesionales: list[str],
    recetas: list[str],
    laboratorio: list[str],
    examenes: str,
    otros_items: dict[str, str],
    estratificacion: dict[str, Any] | None,
    motivo_consulta: str,
    pautas: list[str],
    notas_dir: Path,
    max_intentos: int = 3,
) -> Path | None:
    """Sesion 2026-09-16 14:50 (regla Yadira): si la extraccion de
    anamnesis falla, NO escribir marker. El script debe REINTENTAR
    la extraccion (re-click en 'Atencion actual' + re-extraer
    anamnesis) hasta N veces. Solo si agota todos los reintentos
    retorna None (Yadira re-corre cuando Rayen este estable).

    Args:
        click_ok: si el click en 'Atencion actual' fue exitoso
            originalmente. Si False, no se puede re-clickear; retorna
            None inmediatamente.
        max_intentos: numero maximo de reintentos (default 3).

    Returns:
        Path al .md escrito si algun reintento tuvo exito, o None si
        agoto todos los reintentos sin exito.
    """
    if not click_ok:
        logger.warning(
            f"[crear_notas] {paciente.nombre}: panel NO cargo "
            f"(click_ok=False). No se puede reintentar la extraccion "
            f"desde aqui. Yadira debera re-correr con Rayen estable."
        )
        return None

    for intento in range(1, max_intentos + 1):
        logger.info(
            f"[crear_notas] {paciente.nombre}: reintento "
            f"{intento}/{max_intentos} de extraccion de anamnesis "
            f"(re-click 'Atencion actual')..."
        )
        try:
            # Re-click en "Atencion actual" para forzar recargar el
            # panel de Evaluacion. Si ya esta clickeado, no-op.
            click_atencion_actual(driver, logger)
            # Re-extraer anamnesis con el panel ya (re)cargado.
            anamnesis_nueva = extraer_anamnesis(driver, logger)
            if anamnesis_nueva and anamnesis_nueva.strip():
                # Reintento exitoso. Escribir nota con la nueva
                # anamnesis.
                logger.info(
                    f"[crear_notas] {paciente.nombre}: reintento "
                    f"{intento} exitoso ({len(anamnesis_nueva)} chars)."
                )
                return guardar_nota_clinica(
                    paciente,
                    identificacion,
                    historial,
                    anamnesis_nueva,
                    diagnosticos,
                    actividades,
                    profesionales,
                    pautas,
                    examenes,
                    otros_items,
                    estratificacion,
                    motivo_consulta,
                    recetas,
                    laboratorio,
                    notas_dir,
                    panel_cargo=paciente.panel_cargo,
                )
        except Exception as re_err:
            logger.warning(
                f"[crear_notas] {paciente.nombre}: reintento "
                f"{intento} lanzo excepcion: {type(re_err).__name__}: "
                f"{re_err!r}"
            )

    logger.error(
        f"[crear_notas] {paciente.nombre}: extraccion fallo despues "
        f"de {max_intentos} reintentos. No se escribe archivo. "
        f"Yadira debera re-correr `crear_notas_clinicas` cuando "
        f"Rayen este estable."
    )
    return None


def validar_nota_clinica(nota_path: Path) -> list[str]:
    """Lee un .md de nota clinica y retorna la lista de bloques que estan
    vacios (es decir, bloques que requieren re-fetch).

    Sesion 2026-09-16 14:14 (regla Yadira): despues de escribir la nota,
    el script valida que todos los bloques tengan contenido. Si falta
    alguno, va a buscarlo a Rayen y sobrescribe el archivo con el bloque
    completado.

    Bloques requeridos (si el extractor fallo, son huecos a re-fetch):
    - Identificacion
    - Historial de atenciones
    - Nota clinica de Yadira (anamnesis cruda)
    - Diagnosticos
    - Actividades
    - Profesionales

    Bloques opcionales (pueden estar vacios legitimamente):
    - Plan - Recetas (consultas sin prescripcion)
    - Plan - Laboratorio (consultas sin ordenes)
    - Estratificacion ECICEP (solo si paciente estratificado)

    Returns:
        Lista de nombres de bloques vacios (sin contenido).
        Lista vacia = OK.
    """
    contenido = nota_path.read_text(encoding="utf-8")
    faltantes: list[str] = []

    # Cada bloque: delimitar por "## " header y chequear contenido hasta
    # el siguiente "## " (o fin de archivo).
    bloques = {}
    nombre_actual = None
    contenido_actual: list[str] = []
    en_frontmatter = True

    for line in contenido.splitlines():
        if en_frontmatter:
            if line.strip() == "---":
                en_frontmatter = False
            continue
        if line.startswith("## "):
            if nombre_actual is not None:
                bloques[nombre_actual] = "\n".join(contenido_actual).strip()
            nombre_actual = line[3:].strip()
            contenido_actual = []
        else:
            contenido_actual.append(line)
    if nombre_actual is not None:
        bloques[nombre_actual] = "\n".join(contenido_actual).strip()

    # Chequear bloques requeridos (los que DEBEN tener contenido si se
    # pudo extraer; recetas/laboratorio son opcionales porque una
    # consulta puede no tener prescripcion ni ordenes de lab).
    bloques_requeridos = [
        "Identificacion",
        "Historial de atenciones (ultimos 6 meses)",
        "Nota clinica de Yadira",
        "Diagnosticos",
        "Actividades",
        "Profesionales",
    ]

    for bloque in bloques_requeridos:
        contenido_bloque = bloques.get(bloque, "")
        if not contenido_bloque:
            faltantes.append(bloque)

    return faltantes


def re_extraer_bloque(
    driver: WebDriver,
    logger: logging.Logger,
    bloque: str,
    click_ok: bool,
    identificacion: dict[str, str] | None = None,
    historial: str | None = None,
    anamnesis: str | None = None,
    motivo_consulta: str | None = None,
    diagnosticos: list[str] | None = None,
    actividades: list[str] | None = None,
    profesionales: list[str] | None = None,
    recetas: list[str] | None = None,
    laboratorio: list[str] | None = None,
) -> str | list[str] | dict[str, str] | None:
    """Re-extrae especificamente el bloque faltante desde Rayen.

    Sesion 2026-09-16 14:14 (regla Yadira): si validar_nota_clinica
    detecta un bloque vacio, el pipeline llama a esta funcion con el
    `driver` que sigue en la ficha del paciente (estamos dentro del
    mismo loop, no hemos navegado a otra ficha).

    NOTA: el `driver` aqui deberia estar todavia en la ficha del
    paciente, pero NO se asume. Si `click_ok` fue False originalmente,
    no se puede extraer el bloque (no hay panel cargado). En ese caso
    retorna None.

    Returns:
        Contenido del bloque re-extraido, o None si no se pudo.
    """
    if not click_ok:
        # Sin click en "Atencion actual", no se puede extraer nada del panel.
        logger.warning(
            f"[crear_notas] re-extraer {bloque}: click_ok=False, no se "
            f"puede re-extraer (panel no cargo)."
        )
        return None

    if bloque == "Identificacion":
        return extraer_identificacion(driver, logger)
    if bloque == "Historial de atenciones (ultimos 6 meses)":
        return extraer_historial(driver, logger)
    if bloque == "Nota clinica de Yadira":
        # Anamnesis: si tenemos la original, intentar re-fetch.
        return extraer_anamnesis(driver, logger)
    if bloque == "Diagnosticos":
        return extraer_diagnosticos(driver, logger)
    if bloque == "Actividades":
        return extraer_actividades(driver, logger)
    if bloque == "Profesionales":
        return extraer_profesionales(driver, logger)
    if bloque == "Plan - Recetas":
        return extraer_recetas(driver, logger)
    if bloque == "Plan - Laboratorio":
        return extraer_laboratorio(driver, logger)

    logger.warning(f"[crear_notas] re-extraer: bloque desconocido '{bloque}'")
    return None


# REQ-030: timeout panel 60s; sin carga -> placeholders + panel_cargo=false.
def paso_4_1_abrir_ficha(
    driver: WebDriver,
    logger: logging.Logger,
    paciente: PacienteObjetivo,
) -> bool:
    """Paso 4.1: filtra por fecha, busca al paciente por nombre, doble click.

    Devuelve True si abrio la ficha, False si no encontro al paciente.
    """
    logger.info(
        f"[crear_notas] 4.1 Paciente: {paciente.nombre} "
        f"| fecha={paciente.fecha} | tipo={paciente.tipo_atencion}"
    )

    # 4.1.a: filtrar por fecha
    select_date(driver, logger, fecha_str=paciente.fecha)
    sort_by_estado(driver, logger)

    # 4.1.b: buscar al paciente por nombre completo
    resultado_busqueda = _buscar_paciente_en_tabla(driver, logger, paciente.nombre)
    if resultado_busqueda is None:
        logger.warning(
            f"[crear_notas] No se encontro a '{paciente.nombre}' en la tabla del {paciente.fecha}"
        )
        return False
    row, nombre_rayen = resultado_busqueda
    # Si hubo match parcial, guardar el nombre real de Rayen como
    # metadato para que Mortadelo pueda matchear despues.
    if nombre_rayen is not None:
        paciente.nombre_rayen = nombre_rayen

    # 4.1.c: doble click en la fila para abrir la ficha
    _doble_click_en_paciente(driver, logger, row, nombre_objetivo=paciente.nombre)

    # Esperar a que el panel del paciente se cargue. Senal inequivoca:
    # la tabla de identificacion del paciente tiene <th> en <tbody>
    # (par label:valor). La tabla de Pacientes citados tiene <th> solo
    # en <thead>, asi que el xpath con [.//tbody/th] filtra
    # especificamente la del paciente.
    #
    # Sesion 2026-09-09: timeout subido de 15s a 30s. Caso Ana Patricia
    # Vivanco Munoz: el panel tarda >15s en cargar y el script
    # seguia con extraccion sobre un panel vacio, generando una nota
    # con placeholders "(no se pudo extraer...)". Con 30s cubrimos el
    # percentil alto de paginas lentas de Rayen sin penalizar el caso
    # normal (las paginas rapidas cargan en <5s).
    panel_xpath = (
        "//table[.//tbody/th] | "
        "//li[@id='anamnesis'] | "
        "//div[contains(@class,'side-card')]//*[contains(@class,'rct-tree')] | "
        # ECICEP-g3 a veces no tiene tabla de identificacion visible
        # (la estratificacion carga primero). Esperar el card tambien.
        "//*[contains(@class, 'stratification-card')]"
    )
    # Sesion 2026-09-16: 30s -> 60s para ECICEP-g3.
    # IMPORTANTE: NO hacer retry del doble-click aqui. El primer click
    # ya nos llevo a la ficha del paciente. Si el panel no cargo,
    # un segundo click no ayuda (la fila ya esta stale y ademas
    # get_pacientes_del_dia espera 15s por div.rt-tr-group que ya
    # no existe -> TimeoutException). Mejor: 1 sola espera de 60s,
    # si falla -> placeholder, navegar manualmente al siguiente.
    panel_timeout = 60
    panel = _wait_visible(driver, panel_xpath, timeout=panel_timeout)

    if panel is None:
        # Panel no cargo en 60s. NO re-clickamos. Marcamos el flag y
        # dejamos que la extraccion proceda (devuelve vacios). La nota
        # se guarda con placeholders + flag REVISION.
        logger.warning(
            f"[crear_notas] Panel no aparecio en {panel_timeout}s. "
            f"Extraccion procedera sobre lo que haya; "
            f"guardar_nota_clinica() escribira placeholder con flag REVISION."
        )
        paciente.panel_cargo = False
    else:
        logger.info(f"[crear_notas] Panel del paciente cargado ({panel.tag_name})")

    logger.info(
        f"[crear_notas] Ficha abierta para {paciente.nombre} (URL actual: {driver.current_url})"
    )
    return True


# ---- Iterador principal (paso 4.6: sigue con el siguiente) ----


def iterar_pacientes(
    driver: WebDriver,
    logger: logging.Logger,
    pacientes: list[PacienteObjetivo],
) -> dict[str, int]:
    """Por cada paciente: ejecutar paso 4.1. Si falla, sigue con el siguiente."""
    stats = {"procesados": 0, "abiertos": 0, "no_encontrados": 0, "errores": 0}
    for i, p in enumerate(pacientes, 1):
        logger.info(f"[crear_notas] ({i}/{len(pacientes)}) Procesando: {p.nombre} ({p.fecha})")
        try:
            stats["procesados"] += 1
            ok = paso_4_1_abrir_ficha(driver, logger, p)
            if ok:
                stats["abiertos"] += 1
            else:
                stats["no_encontrados"] += 1
        except Exception as e:
            stats["errores"] += 1
            logger.error(f"[crear_notas] Error con {p.nombre}: {e}. Sigue con el siguiente.")
            continue
    return stats


# ---- Main ----


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Crear notas clinicas desde Rayen. "
            "Por defecto procesa UN paciente (--paciente + --fecha). "
            "Con --todos procesa los pacientes del informe del mes en curso."
        )
    )
    parser.add_argument(
        "--paciente",
        type=str,
        default=None,
        help="Nombre completo del paciente a procesar (modo 1 paciente).",
    )
    parser.add_argument(
        "--fecha",
        type=str,
        default=None,
        help="Fecha del paciente en formato dd-mm-yyyy (modo 1 paciente).",
    )
    parser.add_argument(
        "--todos",
        action="store_true",
        help="Procesa los pacientes del informe del mes en curso (modo batch).",
    )
    parser.add_argument(
        "--informe",
        type=Path,
        default=None,
        help=(
            "Path al informe MENSUAL de fichas abiertas "
            f"(default: {_informe_mes_actual_path().name}). "
            "NO usar el informe anual (_completo.txt) — esta prohibido."
        ),
    )
    parser.add_argument(
        "--user",
        type=str,
        default="yadira",
        help="Usuario de config/users.json (default: yadira)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    # Default de --informe: el informe del mes en curso.
    if args.informe is None:
        args.informe = _informe_mes_actual_path()

    # Guard: el informe anual (_completo) NO se puede usar con --todos.
    # Es una operacion distinta, para otros propositos, y no debe
    # mezclarse con el batch mensual. Si llega por error, abortar claro.
    if args.todos and "_completo" in args.informe.name:
        parser.error(
            f"REFUSADO: {args.informe.name} es el informe ANUAL, "
            f"no se puede usar con --todos. "
            f"Usa el informe del mes en curso ({_informe_mes_actual_path().name}) "
            f"o pasa --informe con un path mensual explicito."
        )

    # Validar modo
    if not args.todos and (not args.paciente or not args.fecha):
        parser.error("Modo 1 paciente requiere --paciente y --fecha. O usa --todos.")

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("crear_notas_clinicas")

    # 1. Cargar credenciales
    try:
        credentials = load_credentials(args.user)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Error cargando credenciales: {e}")
        return 2
    logger.info(f"[crear_notas] Credenciales cargadas para usuario: {args.user}")

    # 2. Construir la lista de pacientes
    if args.todos:
        pacientes = parsear_informe(args.informe)
        logger.info(
            f"[crear_notas] Modo --todos: {len(pacientes)} pacientes del informe {args.informe.name}"
        )
    else:
        pacientes = [
            PacienteObjetivo(
                fecha=args.fecha,
                nombre=args.paciente,
                tipo_atencion="(no se valida contra informe)",
                razon="",
            )
        ]
        logger.info(f"[crear_notas] Modo 1 paciente: {pacientes[0].nombre} | {pacientes[0].fecha}")

    # 3. Pasos 1-3: login + box + Pacientes citados (via run_login)
    driver: WebDriver | None = None
    stats = {"procesados": 0, "abiertos": 0, "guardados": 0, "saltados": 0, "errores": 0}
    fichas_en_sesion = 0
    # Carpeta donde Chrome dejara los adjuntos descargados. Se crea
    # aca para que exista cuando _build_chrome_options la reciba.
    ADJUNTOS_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Capturador de warnings para el informe tecnico (separado de la ficha).
    warnings_collector = WarningsCollector()
    warnings_collector.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger("crear_notas").addHandler(warnings_collector)
    # Lista de informes por paciente.
    pacientes_informe: list[PacienteInforme] = []
    import time as _time

    logger.info(f"[crear_notas] Download dir Chrome: {ADJUNTOS_DOWNLOAD_DIR.resolve()}")
    try:
        driver = run_login(
            credentials,
            logger,
            download_dir=str(ADJUNTOS_DOWNLOAD_DIR.resolve()),
        )
        if not ensure_session_alive(driver, logger):
            logger.error("Sesion invalida tras login.")
            return 1
        logger.info("[crear_notas] Login + navegacion OK.")

        # 4. Por cada paciente: 4.1 (abrir ficha) + 4.2 (extraer) + 4.3 (guardar)
        notas_dir = ROOT / "data" / "notas_clinicas"
        for i, paciente in enumerate(pacientes, 1):
            t_inicio = _time.time()
            warnings_collector.reset()  # snapshot limpio por paciente
            logger.info(
                f"[crear_notas] ({i}/{len(pacientes)}) "
                f"Procesando: {paciente.nombre} ({paciente.fecha})"
            )
            stats["procesados"] += 1
            ficha_ok = False
            pinfo = PacienteInforme(
                nombre=paciente.nombre,
                fecha=paciente.fecha,
            )
            try:
                # Paso 4.1
                ok = paso_4_1_abrir_ficha(driver, logger, paciente)
                if not ok:
                    logger.warning(
                        f"[crear_notas] No se encontro a {paciente.nombre} en la tabla. Saltando."
                    )
                    stats["saltados"] += 1
                    pinfo.estado = "skipped"
                    pinfo.match_tipo = "ninguno"
                    pinfo.warnings = warnings_collector.snapshot()
                    pacientes_informe.append(pinfo)
                    continue
                stats["abiertos"] += 1
                ficha_ok = True
                # Si hubo match parcial, paso_4_1 setea paciente.nombre_rayen.
                if paciente.nombre_rayen:
                    pinfo.match_tipo = "parcial"
                    pinfo.match_nombre_rayen = paciente.nombre_rayen
                else:
                    pinfo.match_tipo = "exacto"

                # Paso 4.2
                # REQ-024: estratificacion ECICEP PRIMERO (su modal debe cerrarse antes).
                # Razon: la estratificacion abre un modal; hay que cerrarlo
                # con el boton "Salir" antes de cualquier otra extraccion, para
                # que el overlay/modal no intercepte clicks posteriores.
                # 1) Estratificacion (incluye apertura popover+modal, parseo
                #    y cierre via boton "Salir" + cierre de popover).
                # 2) Identificacion, 3) Historial.
                # 4) Click en Atencion actual.
                # 5) Motivo, 6) Anamnesis, 7) Diagnostico, 8) Actividad,
                #    9) Profesionales, 10) Plan -> Recetas, 11) Plan -> Laboratorio.
                # Fuera de scope: examenes adjuntos, pautas, otros items,
                # plan -> imagenologia, plan -> interconsulta.
                estratificacion = extraer_estratificacion_ecicep(driver, logger)
                identificacion = extraer_identificacion(driver, logger)
                # Historial ANTES del click en "Atencion actual" porque ese
                # click puede colapsar el panel del historial.
                historial = extraer_historial(driver, logger)
                # REQ-033: fuera de scope: examenes, pautas, otros items, imagenologia, interconsulta.
                # Secciones fuera de scope (no se extraen, se pasan vacias):
                examenes = ""
                # Ahora si hacemos click en Atencion actual
                click_ok = click_atencion_actual(driver, logger)
                motivo_consulta = extraer_motivo_consulta(driver, logger) if click_ok else ""
                anamnesis = extraer_anamnesis(driver, logger) if click_ok else ""
                # Paso 4.2.5 (sesion 2026-09-16 15:14): respaldo de la
                # anamnesis cruda de Yadira en anamnesis/<paciente>_<fecha>.md.
                # Es un .md liviano, separado de la nota clinica completa,
                # para que Yadira tenga una copia de seguridad local facil
                # de buscar por nombre y fecha. Solo si la anamnesis no
                # esta vacia. Sesion 15:27: tambien incluye motivo de
                # atencion como blockquote antes de la anamnesis (es la
                # primera linea que Yadira escribe en Rayen).
                if anamnesis:
                    guardar_respaldo_anamnesis(paciente, anamnesis, motivo_consulta=motivo_consulta)
                diagnosticos = extraer_diagnosticos(driver, logger) if click_ok else []
                actividades = extraer_actividades(driver, logger) if click_ok else []
                profesionales = extraer_profesionales(driver, logger) if click_ok else []
                # Plan (panel derecho). Recetas y Laboratorio se extraen
                # del mismo panel #right-side-attention que ya esta visible
                # tras click_atencion_actual. Si click_ok fallo, no se
                # intenta (no hay panel que leer).
                recetas = extraer_recetas(driver, logger) if click_ok else []
                # Regla Yadira 2026-08-26: si el tipo de atencion es
                # "Recetas", dejamos SOLO la prescripcion con la Vigencia
                # mas reciente en el bloque PLAN RECETAS del .txt. Para
                # cualquier otro tipo, se conservan todas las recetas.
                if _tipo_atencion_es_recetas(paciente.tipo_atencion) and len(recetas) > 1:
                    recetas_filtradas = _filtrar_receta_mas_reciente(recetas)
                    logger.info(
                        f"[crear_notas] tipo=Recetas: filtradas "
                        f"{len(recetas)} -> {len(recetas_filtradas)} "
                        f"prescripcion(es) (mas reciente)"
                    )
                    recetas = recetas_filtradas
                laboratorio = extraer_laboratorio(driver, logger) if click_ok else []
                # Fuera de scope:
                pautas: list[str] = []
                otros_items: dict[str, Any] = {}

                pinfo.extraccion = {
                    "identificacion_campos": len(identificacion),
                    "historial_caracteres": len(historial or ""),
                    "anamnesis_caracteres": len(anamnesis or ""),
                    "motivo_consulta_caracteres": len(motivo_consulta or ""),
                    "diagnosticos": len(diagnosticos or []),
                    "actividades": len(actividades or []),
                    "profesionales": len(profesionales or []),
                    "pautas": len(pautas or []),
                    "examenes_adjuntos_chars": len(examenes or ""),
                    "recetas_prescripciones": len(recetas or []),
                    "laboratorio_ordenes": len(laboratorio or []),
                    "estratificacion_grupo": ((estratificacion or {}).get("grupo")),
                    "estratificacion_cronicos": len((estratificacion or {}).get("cronicos") or []),
                    "estratificacion_agudos": len((estratificacion or {}).get("agudos") or []),
                }

                # Paso 4.3
                try:
                    out_path = guardar_nota_clinica(
                        paciente,
                        identificacion,
                        historial,
                        anamnesis,
                        diagnosticos,
                        actividades,
                        profesionales,
                        pautas,
                        examenes,
                        otros_items,
                        estratificacion,
                        motivo_consulta,
                        recetas,
                        laboratorio,
                        notas_dir,
                        panel_cargo=paciente.panel_cargo,
                    )

                    if out_path is None:
                        raise RuntimeError(
                            f"guardar_nota_clinica no escribio la nota de {paciente.nombre}"
                        )
                    # Paso 4.5 (sesion 2026-09-16 17:45): documento
                    # complementario en data/info_paciente/ con TODA la
                    # info del paciente MENOS la anamnesis cruda. Yadira
                    # lo usa para "mirar al paciente de un vistazo" sin
                    # leer el texto libre de la consulta. La anamnesis
                    # sigue en data/anamnesis/ (respaldo separado).
                    guardar_info_paciente(
                        paciente,
                        identificacion,
                        historial,
                        diagnosticos,
                        actividades,
                        profesionales,
                        recetas,
                        laboratorio,
                        estratificacion,
                        info_paciente_dir=INFO_PACIENTE_DIR,
                        panel_cargo=paciente.panel_cargo,
                    )
                    # Paso 4.4: VALIDACION POST-WRITE + RE-FETCH DE HUECOS.
                    # Regla Yadira 2026-09-16 14:14: despues de escribir,
                    # el script verifica que todos los bloques tengan
                    # contenido. Si falta alguno, va a buscarlo a Rayen
                    # con el `driver` que sigue activo y sobrescribe el
                    # archivo.
                    faltantes = validar_nota_clinica(out_path)
                    if faltantes:
                        logger.warning(
                            f"[crear_notas] {paciente.nombre}: "
                            f"validacion post-write encontro {len(faltantes)} "
                            f"bloque(s) sin contenido: {faltantes}. "
                            f"Re-fetch + re-write."
                        )
                        bloques_reescritos: list[str] = []
                        bloques_aun_vacios: list[str] = []
                        for bloque in faltantes:
                            nuevo = re_extraer_bloque(
                                driver,
                                logger,
                                bloque,
                                click_ok,
                                identificacion=identificacion,
                                historial=historial,
                                anamnesis=anamnesis,
                                motivo_consulta=motivo_consulta,
                                diagnosticos=diagnosticos,
                                actividades=actividades,
                                profesionales=profesionales,
                                recetas=recetas,
                                laboratorio=laboratorio,
                            )
                            if nuevo:
                                _rellenar_bloque_en_nota(out_path, bloque, nuevo)
                                bloques_reescritos.append(bloque)
                            else:
                                bloques_aun_vacios.append(bloque)
                        if bloques_reescritos:
                            logger.info(
                                f"[crear_notas] {paciente.nombre}: "
                                f"re-fetch completo para {bloques_reescritos}."
                            )
                        if bloques_aun_vacios:
                            logger.warning(
                                f"[crear_notas] {paciente.nombre}: "
                                f"no se pudo re-extraer: {bloques_aun_vacios}. "
                                f"Yadira debera revisar manualmente."
                            )

                    stats["guardados"] += 1
                    pinfo.estado = "ok"
                    logger.info(f"[crear_notas] {paciente.nombre} OK -> {out_path.name}")
                except ValueError as ve:
                    # Regla Yadira 2026-09-16 14:50 (correccion): NO
                    # escribir markers. Si la extraccion fallo, el
                    # script debe REINTENTAR (re-click en 'Atencion
                    # actual' + re-extraer anamnesis) hasta N veces.
                    # Solo si agota todos los reintentos, skip
                    # silencioso (Yadira re-corre cuando Rayen este
                    # estable).
                    stats["errores_extraccion"] = stats.get("errores_extraccion", 0) + 1
                    pinfo.errores.append(f"ValueError: {ve!r}")
                    out_reintento = _reintentar_extraccion_anamnesis(
                        driver,
                        logger,
                        paciente,
                        click_ok,
                        identificacion,
                        historial,
                        diagnosticos,
                        actividades,
                        profesionales,
                        recetas,
                        laboratorio,
                        examenes,
                        otros_items,
                        estratificacion,
                        motivo_consulta,
                        pautas,
                        notas_dir,
                    )
                    if out_reintento is not None:
                        stats["guardados"] += 1
                        pinfo.estado = "ok"
                        logger.info(
                            f"[crear_notas] {paciente.nombre} OK "
                            f"(tras reintento) -> {out_reintento.name}"
                        )
                    else:
                        pinfo.estado = "extraccion_fallida"
                        logger.error(
                            f"[crear_notas] {paciente.nombre}: "
                            f"extraccion fallo tras agotar reintentos. "
                            f"Yadira re-corre cuando Rayen este estable."
                        )

            except Exception as e:
                stats["errores"] += 1
                pinfo.estado = "error"
                # Guardar tipo de excepcion + mensaje. Mensajes vacios ("Message: \n")
                # son tipicos de WebDriverException con msg vacio; el TIPO es lo
                # unico que da pista del problema real.
                import traceback as _tb

                err_repr = f"{type(e).__name__}: {e!r}"
                pinfo.errores.append(err_repr)
                tb_short = _tb.format_exc().splitlines()[-3:]
                logger.error(
                    f"[crear_notas] Error con {paciente.nombre}: {err_repr}. "
                    f"Ultimas lineas del traceback: {tb_short}. "
                    f"Sigue con el siguiente."
                )

            pinfo.warnings = warnings_collector.snapshot()
            pinfo.tiempo_segundos = round(_time.time() - t_inicio, 2)
            pacientes_informe.append(pinfo)

            # Despues de CADA paciente (exitoso o no), volver a la lista
            # para el siguiente. Y si llegamos al limite, resetear sesion.
            if ficha_ok:
                fichas_en_sesion += 1
            quedan = len(pacientes) - i
            necesita_reset = fichas_en_sesion >= MAX_FICHAS_POR_SESION and quedan > 0
            if necesita_reset:
                logger.warning(
                    f"[crear_notas] Limite de {MAX_FICHAS_POR_SESION} fichas alcanzado. "
                    f"Reseteando sesion de Rayen..."
                )
                safe_quit(driver, logger)
                driver = None
                driver = run_login(
                    credentials,
                    logger,
                    download_dir=str(ADJUNTOS_DOWNLOAD_DIR.resolve()),
                )
                if not ensure_session_alive(driver, logger):
                    logger.error("Sesion invalida tras re-login.")
                    return 1
                fichas_en_sesion = 0
            elif quedan > 0:
                # Volver a la lista de Pacientes citados para el siguiente
                volver_a_pacientes_citados(driver, logger)

        logger.info(
            f"[crear_notas] === Resumen final === "
            f"procesados={stats['procesados']}, "
            f"abiertos={stats['abiertos']}, "
            f"guardados={stats['guardados']}, "
            f"saltados={stats['saltados']}, "
            f"errores={stats['errores']}"
        )

        # REQ-032: verificacion de target del batch contra el informe.
        # Verificacion de target: el informe dice N fichas abiertas, el
        # script tiene que procesar las N. Si falta alguna, alertar.
        if args.todos:
            total_objetivo = len(pacientes)
            total_ok = stats["abiertos"]
            faltantes_target = total_objetivo - total_ok
            if faltantes_target > 0:
                logger.warning(
                    f"[crear_notas] === TARGET NO CUMPLIDO === "
                    f"Objetivo informe: {total_objetivo} fichas, "
                    f"abiertas OK: {total_ok}, "
                    f"FALTAN: {faltantes_target}. "
                    f"Revisar logs de 'No se encontro a ...' arriba."
                )
            else:
                logger.info(
                    f"[crear_notas] === TARGET OK === "
                    f"Las {total_objetivo} fichas del informe "
                    f"fueron procesadas."
                )

            # 5. Generar informe tecnico (JSON para Miguel).
            # Contiene warnings, errores, tiempos, datos extraidos por
            # paciente. NO va a la ficha, va a un archivo separado.
            informe = generar_informe_tecnico(
                modo="todos",
                informe=str(args.informe.name),
                pacientes=pacientes_informe,
                stats=stats,
            )
            informes_dir = ROOT / "data" / "analysis"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            informe_path = informes_dir / f"informe_tecnico_{ts}.json"
            informe.guardar(informe_path)
            logger.info(f"[crear_notas] Informe tecnico guardado en: {informe_path}")

        # 6. Cerrar navegador automaticamente al terminar
        logger.info("[crear_notas] Cerrando navegador...")
        return 0
    except Exception as e:
        logger.error(f"[crear_notas] Error fatal: {e}")
        return 1
    finally:
        if driver is not None:
            safe_quit(driver, logger)


if __name__ == "__main__":
    sys.exit(main())
