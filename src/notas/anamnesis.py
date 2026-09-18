"""Respaldo de la anamnesis cruda de Yadira (REQ-026/027).

anam_<pac>_<fecha>.md con motivo blockquote + anamnesis, SIN frontmatter
(pedido directo del usuario 18-09-2026: el bloque inicial estorbaba la
lectura). El nombre del archivo ya identifica paciente y fecha.
"""

from __future__ import annotations

from pathlib import Path

from src.core.nombres import safe_filename as _safe_filename
from src.core.rutas import ANAMNESIS_DIR as ANAMNESIS_BACKUP_DIR
from src.notas.modelos import PacienteObjetivo

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

    md: list[str] = []
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
