"""Escritura y validacion de la nota clinica .md (Fase 4a).

REQ-020/021/022: anamnesis vacia=ValueError; SIEMPRE se sobrescribe;
validacion post-write con relleno de bloques.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.nombres import safe_filename as _safe_filename
from src.notas.modelos import PacienteObjetivo
from src.rayen.extraccion.estratificacion import formatear_estratificacion
from src.rayen.extraccion.historial import filtrar_historial_ultimos_6_meses


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


def _now_iso() -> str:
    """Helper: timestamp ISO 8601 al segundo. Usado para el frontmatter."""

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
