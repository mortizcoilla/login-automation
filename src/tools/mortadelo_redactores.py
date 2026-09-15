# -*- coding: utf-8 -*-
"""Redactores de instrucciones de Yadira para Mortadelo.

Cuando Yadira deja un trigger `** mortadelo <instruccion>`, Mortadelo
identifica el tipo de instruccion y genera un output estructurado
usando los datos extraidos del parser.

Tipos soportados:
- interconsulta / IC: genera una IC medica con los datos del paciente
- correo / email: genera un correo formal
- completar: completa campos faltantes (no genera output extra)
- otro: cualquier otra instruccion (queda registrada)

La decision clinica SIEMPRE es de Yadira. Mortadelo solo redacta.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from src.tools.mortadelo_parser import NotaParseada


# ---- Deteccion de tipo de instruccion ----

RE_INSTR_INTERCONSULTA = re.compile(
    r"\b(?:interconsulta|I\.?C\.?|derivaci[óo]n|derivar)\b",
    re.IGNORECASE,
)
RE_INSTR_CORREO = re.compile(
    r"\b(?:correo|email|mail|mensaje)\b",
    re.IGNORECASE,
)
RE_INSTR_COMPLETAR = re.compile(
    r"\b(?:completar|completa|terminar|rellenar)\b",
    re.IGNORECASE,
)


def detectar_tipo_instruccion(instruccion: str) -> str:
    """Clasifica la instruccion de Yadira en uno de los tipos soportados."""
    if not instruccion:
        return "otro"
    if RE_INSTR_INTERCONSULTA.search(instruccion):
        return "interconsulta"
    if RE_INSTR_CORREO.search(instruccion):
        return "correo"
    if RE_INSTR_COMPLETAR.search(instruccion):
        return "completar"
    return "otro"


# ---- Redactor de interconsulta ----

def redactar_interconsulta(p: NotaParseada, instruccion: str) -> str:
    """Genera una interconsulta medica con los datos del paciente.

    NO incluye diagnostico final (regla: Mortadelo JAMAS decide). Solo
    organiza los datos de la nota en formato estandar de IC.
    """
    hoy = date.today().strftime("%d-%m-%Y")
    bloques: list[str] = []

    bloques.append("== INTERCONSULTA (borrador para revision) ==")
    bloques.append("")

    # Destinatario (no sabemos, dejar placeholder neutro)
    if "otorrino" in instruccion.lower() or "ORL" in instruccion.upper() or "aud" in instruccion.lower():
        bloques.append("PARA: Servicio de Otorrinolaringologia")
    elif "psiquia" in instruccion.lower():
        bloques.append("PARA: Servicio de Psiquiatria")
    elif "oftalmo" in instruccion.lower() or "oftalm" in instruccion.lower():
        bloques.append("PARA: Servicio de Oftalmologia")
    else:
        bloques.append("PARA: [completar destinatario]")

    bloques.append("DE:    Dra. Yadira Hernandez Cabrera - CESFAM Raul Cuevas, San Bernardo")
    bloques.append(f"FECHA: {hoy}")
    bloques.append("")

    # Identificacion del paciente (de la nota, no tenemos RUT)
    bloques.append("IDENTIFICACION DEL PACIENTE:")
    if p.acompanante:
        bloques.append(f"  Acompana: {p.acompanante}")
    bloques.append("  Edad: [completar]")  # no tenemos edad en parser
    bloques.append("  RUT: [completar]")
    bloques.append("")

    # Motivo de la interconsulta
    bloques.append("MOTIVO DE LA INTERCONSULTA:")
    if p.motivo_consulta:
        bloques.append(f"  {p.motivo_consulta}")
    else:
        bloques.append("  [detallar motivo]")
    bloques.append("")

    # Antecedentes relevantes
    if p.APP or p.APF or p.farmacos or p.alergias:
        bloques.append("ANTECEDENTES RELEVANTES:")
        if p.APP:
            bloques.append(f"  - APP: {p.APP}")
        if p.APF:
            bloques.append(f"  - APF: {p.APF}")
        if p.alergias and p.alergias.lower() not in ("no", "niega", "(-)"):
            bloques.append(f"  - Alergias: {p.alergias}")
        elif p.alergias:
            bloques.append("  - Alergias: No refiere")
        if p.farmacos:
            bloques.append("  - Farmacos:")
            for fco in p.farmacos:
                bloques.append(f"      * {fco}")
        bloques.append("")

    # Examen fisico
    if p.examen_fisico:
        bloques.append("EXAMEN FISICO (datos del control):")
        for k, v in p.examen_fisico.items():
            bloques.append(f"  - {k}: {v}")
        bloques.append("")

    # Indicaciones / plan
    if p.indicaciones:
        bloques.append("INDICACIONES DEL CONTROL:")
        for ind in p.indicaciones:
            bloques.append(f"  - {ind}")
        bloques.append("")

    # Adjuntos
    bloques.append("ADJUNTOS:")
    bloques.append("  - Ficha clinica del paciente")
    bloques.append("  - Examenes relevantes (segun motivo)")
    bloques.append("  - Resultado de audiometria / examen especifico (si aplica)")
    bloques.append("")

    # Lo que solicito (placeholder neutro)
    bloques.append("SOLICITO:")
    bloques.append("  - Evaluacion por la especialidad segun motivo")
    bloques.append("  - [detallar que necesita del especialista]")
    bloques.append("  - Sugerencias de manejo y/o estudio complementario")
    bloques.append("  - Contrarreferencia con plan de seguimiento")
    bloques.append("")

    bloques.append("== /INTERCONSULTA ==")

    return "\n".join(bloques)


# ---- Redactor de correo ----

def redactar_correo(p: NotaParseada, instruccion: str) -> str:
    """Genera un correo formal con los datos del paciente."""
    hoy = date.today().strftime("%d-%m-%Y")
    bloques: list[str] = []

    bloques.append("== CORREO (borrador para revision) ==")
    bloques.append("")
    bloques.append("ASUNTO: [completar]")
    bloques.append(f"FECHA: {hoy}")
    bloques.append("PARA:  [destinatario]")
    bloques.append("DE:    Dra. Yadira Hernandez Cabrera - CESFAM Raul Cuevas")
    bloques.append("")
    bloques.append("Estimado/a:")
    bloques.append("")
    bloques.append("  Por medio del presente, ")
    if p.motivo_consulta:
        bloques.append(f"  motivo: {p.motivo_consulta}.")
    else:
        bloques.append("  motivo: [detallar motivo del correo].")
    bloques.append("")

    if p.APP or p.farmacos:
        bloques.append("  Antecedentes relevantes:")
        if p.APP:
            bloques.append(f"    - {p.APP}")
        if p.farmacos:
            bloques.append("    - Farmacos: " + ", ".join(p.farmacos[:3]))
        bloques.append("")

    if p.indicaciones:
        bloques.append("  Plan:")
        for ind in p.indicaciones:
            bloques.append(f"    - {ind}")
        bloques.append("")

    bloques.append("  Quedo atento/a a su respuesta.")
    bloques.append("")
    bloques.append("  Saludos cordiales,")
    bloques.append("  Dra. Yadira Hernandez Cabrera")
    bloques.append("  CESFAM Raul Cuevas, San Bernardo")
    bloques.append("")
    bloques.append("== /CORREO ==")
    return "\n".join(bloques)


# ---- Redactor generico ----

def redactar(p: NotaParseada, instruccion: str) -> tuple[str, str]:
    """Devuelve (tipo, output_redactado) segun el tipo de instruccion."""
    tipo = detectar_tipo_instruccion(instruccion)
    if tipo == "interconsulta":
        return tipo, redactar_interconsulta(p, instruccion)
    if tipo == "correo":
        return tipo, redactar_correo(p, instruccion)
    if tipo == "completar":
        return tipo, "[INSTRUCCION COMPLETAR: la ficha ya fue procesada. Verificar campos arriba.]"
    return "otro", f"[INSTRUCCION REGISTRADA: {instruccion}.]"
