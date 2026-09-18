"""Documento complementario info_<pac>_<fecha>.md (REQ-028).

Toda la info del paciente MENOS anamnesis/motivo (vista rapida).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.core.nombres import safe_filename as _safe_filename
from src.core.rutas import INFO_PACIENTE_DIR
from src.notas.nota_clinica import _now_iso

# Documento complementario a la nota clinica: contiene TODA la info del
# paciente EXCEPTO la anamnesis cruda de Yadira. Es para "mirar al
# paciente de un vistazo" sin ver el texto libre de la consulta.
# Sesion 2026-09-16 17:45 (pedido Yadira):
#   data/notas_clinicas/<paciente>_<fecha>.md   <- nota completa (incluye anamnesis)
#   data/anamnesis/<paciente>_<fecha>.md        <- solo anamnesis cruda (respaldo)
#   data/info_paciente/<paciente>_<fecha>.md    <- todo MENOS la anamnesis (NUEVO)


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
