"""Modelos de datos de las notas clinicas (Fase 4a).

PacienteObjetivo: un paciente del informe de fichas abiertas a procesar.
"""

from __future__ import annotations

from dataclasses import dataclass

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
