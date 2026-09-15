# -*- coding: utf-8 -*-
"""Parser de notas clinicas de Yadira para Mortadelo.

Extrae campos estructurados de notas en espanol libre (Rayen) y los mapea
a los placeholders de la plantilla del bundle correspondiente.

Privacidad: NO loguea RUT, nombre ni observacion clinica en stdout/stderr.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---- Secciones extraidas de la nota ----

@dataclass
class NotaParseada:
    motivo_consulta: Optional[str] = None
    APP: Optional[str] = None           # Antecedentes Patologicos Personales
    APQX: Optional[str] = None           # Antecedentes Quirurgicos
    alergias: Optional[str] = None
    APF: Optional[str] = None           # Antecedentes Patologicos Familiares
    farmacos: list[str] = field(default_factory=list)
    habitos: dict[str, str] = field(default_factory=dict)  # TBQ, OH, Drogas
    examen_fisico: dict[str, str] = field(default_factory=dict)
    indicaciones: list[str] = field(default_factory=list)
    diagnosticos: list[str] = field(default_factory=list)
    datos_admin: dict[str, str] = field(default_factory=dict)
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    acompanante: Optional[str] = None
    texto_crudo: str = ""               # nota completa como fallback
    secciones_no_match: list[str] = field(default_factory=list)


# ---- Regex de extraccion ----

RE_MOTIVO = re.compile(
    r"(?:motivo de consulta|consulta por|motivo consulta|acude por|refiere)\s*[:\-]?\s*"
    r"([^\n]+)",
    re.IGNORECASE,
)
# APP: busca "APP:" o "ANTECEDENTES M(ÉDICOS|ÓRBIDOS)" o "Antecedentes m(é|ó)rbidos"
RE_APP = re.compile(
    r"(?:\bAPP\b|ANTECEDENTES\s+M[ÉE]DICOS|"
    r"Antecedentes\s+m[oó]rbidos|APPQX\s*m[oó]rbidos)"
    r"\s*[:\-]?\s*([^\n]+)",
    re.IGNORECASE,
)
RE_APQX = re.compile(
    r"(?:\bAPQX?\b|Antecedentes\s+quir[úu]rgicos)\s*[:\-]?\s*([^\n]+)",
    re.IGNORECASE,
)
# Alergias: "ALERGIAS:" o "Alergia:" o "Alergias:"
RE_ALERGIAS = re.compile(
    r"(?:\bALERGIAS?\b|Alergia:?)\s*[:\-]?\s*([^\n]+)",
    re.IGNORECASE,
)
RE_APF = re.compile(r"\bAPF\s*[:\-]\s*([^\n]+)", re.IGNORECASE)
# Medicamentos: incluye "Fármacos de uso diario" (formato Yadira)
RE_MEDICAMENTOS = re.compile(
    r"\b(?:MEDICAMENTOS|F[áa]rmacos(?:\s+de\s+uso(?:\s+diario)?)?|Fcos:?)\s*[:\-]?\s*\n"
    r"((?:.+\n?){0,15}?)(?=\n\s*\n|\Z)",
    re.IGNORECASE,
)
# Hábitos tóxicos: en una sola linea Yadira pone "Alcohol, tipo, frecuencia, ..."
# El parser lo unifica bajo TBQ; OH y Drogas se infieren del texto
RE_HABITOS = re.compile(
    r"(?:\bTBQ\b|H[áa]bitos\s+t[óo]xicos)\s*[:\-]?\s*([^\n]+?)(?=\n\s*(?:\-|\w)|\n\s*\n|$)",
    re.IGNORECASE | re.DOTALL,
)

# Signos vitales: TA, FC, FR, T, SatO2, IMC
RE_TA = re.compile(r"\bTA\s+(\d{2,3}\s*/\s*\d{2,3})", re.IGNORECASE)
RE_FC = re.compile(r"\b(?:FC|Frec\w* card\w*)\s*[:\s]+(\d{2,3})", re.IGNORECASE)
RE_FR = re.compile(r"\b(?:FR|Frec\w* resp\w*)\s*[:\s]+(\d{1,2})", re.IGNORECASE)
RE_TEMP = re.compile(r"\b(?:T[°º]?|Temp)\s*[:\s]+(\d{2}(?:[.,]\d)?)", re.IGNORECASE)
RE_SATO2 = re.compile(r"\bSat[Oo]?2?\s*[:\s]+(\d{2,3})", re.IGNORECASE)
RE_PESO = re.compile(r"\bPeso\s*[:\s]+(\d{2,3}(?:[.,]\d)?)", re.IGNORECASE)
RE_TALLA = re.compile(r"\b(?:Talla|Altura)\s*[:\s]+(\d{2,3}(?:[.,]\d)?)", re.IGNORECASE)
RE_IMC = re.compile(r"\bIMC\s*[:\s]+(\d{1,2}(?:[.,]\d)?)", re.IGNORECASE)

# Diagnosticos: capturamos hasta 15 lineas o fin
RE_DX = re.compile(
    r"\b(?:DIAGN[ÓO]STICOS?|Dx|Impresi[óo]n diagn[óo]stica|Hallazgos?)\s*[:\-]?\s*\n"
    r"((?:.+\n?){0,15}?)(?=\n\s*\n|\Z)",
    re.IGNORECASE,
)
# Bloque extraido por crear_notas_clinicas.py: === INICIO DIAGNOSTICOS ===
RE_DX_SECCION = re.compile(
    r"=== INICIO DIAGNOSTICOS ===\s*\n"
    r"=+\s*\n"
    r"(.*?)"
    r"\n=+\s*\n"
    r"=== FIN DIAGNOSTICOS ===",
    re.DOTALL,
)
# Linea CIE 10 dentro del bloque: "- CIE 10 [tipo, ...]: Clasificación: <codigo><desc>"
RE_DX_LINEA = re.compile(
    r"-\s*CIE\s*10\s*\[[^\]]+\]\s*:\s*"
    r"(?:Clasificaci[óo]n\s*:\s*)?"
    r"([A-Z]\d{1,3}(?:\.\d{1,2})?)\s*"
    r"([^\n]+?)\s*$",
    re.IGNORECASE,
)
RE_INDICACIONES = re.compile(
    r"\b(?:INDICACIONES?|Indicac|PLAN|Conducta a seguir)\s*[:\-]?\s*\n"
    r"((?:.+\n?){0,15}?)(?=\n\s*\n|\Z)",
    re.IGNORECASE,
)

# Datos administrativos
RE_FECHA = re.compile(r"\bfecha(?:\s+de\s+ingreso)?\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", re.IGNORECASE)
RE_TELEFONO = re.compile(r"(?:tel[ée]fono|fono|celular)\s*[:\-]?\s*([+\d\s().\-]{6,20})", re.IGNORECASE)
RE_DIRECCION = re.compile(
    r"\b(?:direcci[óo]n|domicilio)\s*[:\-]?\s*([^\n]+?)(?=\n|tel[ée]fono|$)",
    re.IGNORECASE,
)
RE_ACOMPANANTE = re.compile(
    r"\b(?:acude\s+)?(?:con|acompa[ñn]ad[oa])\s+(?:de\s+|por\s+)?([^\n]+?)(?=\.|,|\n|$)",
    re.IGNORECASE,
)


def _first(pat: re.Pattern, text: str) -> Optional[str]:
    m = pat.search(text)
    return m.group(1).strip() if m else None


def _all_lines(block: Optional[str]) -> list[str]:
    if not block:
        return []
    return [ln.strip(" -•\t") for ln in block.splitlines() if ln.strip(" -•\t")]


def parsear_nota(nota: str) -> NotaParseada:
    """Extrae campos estructurados de la nota clinica en espanol libre."""
    p = NotaParseada(texto_crudo=nota)

    p.motivo_consulta = _first(RE_MOTIVO, nota)
    p.APP = _first(RE_APP, nota)
    p.APQX = _first(RE_APQX, nota)
    p.alergias = _first(RE_ALERGIAS, nota)
    p.APF = _first(RE_APF, nota)
    p.farmacos = _all_lines(_first(RE_MEDICAMENTOS, nota))
    # Hábitos tóxicos: Yadira escribe todo en una linea (tabaco, OH, drogas)
    # Se intenta separar por palabras clave. Si la nota menciona "Alcohol"
    # sin "niega alcohol", entonces OH = descripcion (no es negativo).
    habitos_txt = _first(RE_HABITOS, nota)
    if habitos_txt:
        bajo = habitos_txt.lower()
        # TBQ: tabaco
        if "niega tabaco" in bajo:
            p.habitos["TBQ"] = "(-)"
        elif "tabaco" in bajo:
            p.habitos["TBQ"] = habitos_txt
        else:
            p.habitos["TBQ"] = "-"
        # OH: alcohol
        if "niega alcohol" in bajo or "niega oh" in bajo:
            p.habitos["OH"] = "(-)"
        elif "alcohol" in bajo or " oh " in bajo or bajo.startswith("oh"):
            p.habitos["OH"] = habitos_txt
        else:
            p.habitos["OH"] = "-"
        # Drogas
        if "niega drogas" in bajo or "niega droga" in bajo:
            p.habitos["Drogas"] = "(-)"
        elif "droga" in bajo:
            p.habitos["Drogas"] = habitos_txt
        else:
            p.habitos["Drogas"] = "-"
    else:
        p.habitos["TBQ"] = "-"
        p.habitos["OH"] = "-"
        p.habitos["Drogas"] = "-"
    p.habitos["_raw"] = habitos_txt or ""

    # Signos vitales
    ta = _first(RE_TA, nota)
    if ta:
        p.examen_fisico["TA"] = ta
    fc = _first(RE_FC, nota)
    if fc:
        p.examen_fisico["FC"] = fc
    fr = _first(RE_FR, nota)
    if fr:
        p.examen_fisico["FR"] = fr
    t = _first(RE_TEMP, nota)
    if t:
        p.examen_fisico["T"] = t
    sato2 = _first(RE_SATO2, nota)
    if sato2:
        p.examen_fisico["SatO2"] = sato2
    peso = _first(RE_PESO, nota)
    if peso:
        p.examen_fisico["Peso"] = peso
    talla = _first(RE_TALLA, nota)
    if talla:
        p.examen_fisico["Talla"] = talla
    imc = _first(RE_IMC, nota)
    if imc:
        p.examen_fisico["IMC"] = imc

    # Diagnosticos: primero intenta parsear la seccion estructurada
    # (=== INICIO DIAGNOSTICOS ===) que crea_notas_clinicas.py extrae
    # de Rayen. Si no existe, cae a la regex generica.
    bloque_dx = RE_DX_SECCION.search(nota)
    if bloque_dx:
        for linea in bloque_dx.group(1).splitlines():
            m = RE_DX_LINEA.search(linea)
            if m:
                codigo = m.group(1)
                desc = m.group(2).strip()
                if desc.lower() == "(sin diagnosticos)":
                    continue
                p.diagnosticos.append(f"{codigo} {desc}")
    if not p.diagnosticos:
        p.diagnosticos = _all_lines(_first(RE_DX, nota))
    p.indicaciones = _all_lines(_first(RE_INDICACIONES, nota))

    # Datos admin
    p.datos_admin["fecha"] = _first(RE_FECHA, nota) or ""
    p.telefono = _first(RE_TELEFONO, nota)
    p.direccion = _first(RE_DIRECCION, nota)
    p.acompanante = _first(RE_ACOMPANANTE, nota)

    return p


# Marcadores que cuentan como "respuesta valida" de Yadira (no como faltante).
# "no", "niega", "(-)" significa que Yadira respondio que NO; eso es data.
RESPUESTAS_NEGATIVAS_VALIDAS = {"no", "niega", "(-)", "-", "—", ""}


def campos_llenos(p: NotaParseada) -> tuple[list[str], list[str], dict[str, str]]:
    """Devuelve (campos_llenos, campos_vacios, valores_negativos).

    campos_llenos: campos con valor positivo (no vacio, no "no"/"niega")
    campos_vacios: campos sin valor (None o string vacio)
    valores_negativos: campos donde Yadira respondio "no"/"niega" (data valida)
    """
    llenos: list[str] = []
    vacios: list[str] = []
    negativos: dict[str, str] = {}
    for attr in ("motivo_consulta", "APP", "APQX", "alergias", "APF",
                 "telefono", "direccion", "acompanante"):
        val = getattr(p, attr)
        if val is None or val.strip() == "":
            vacios.append(attr)
        elif val.strip().lower() in RESPUESTAS_NEGATIVAS_VALIDAS:
            negativos[attr] = val.strip()
        else:
            llenos.append(attr)
    if p.farmacos:
        llenos.append("farmacos")
    else:
        vacios.append("farmacos")
    if p.examen_fisico:
        llenos.append("examen_fisico")
    else:
        vacios.append("examen_fisico")
    if p.diagnosticos:
        llenos.append("diagnosticos")
    else:
        vacios.append("diagnosticos")
    if p.indicaciones:
        llenos.append("indicaciones")
    else:
        vacios.append("indicaciones")
    for hab in ("TBQ", "OH", "Drogas"):
        v = p.habitos.get(hab, "-")
        if v and v.strip() and v.strip() not in ("-", ""):
            llenos.append(f"habitos.{hab}")
        elif v and v.strip() in ("-", ""):
            negativos[f"habitos.{hab}"] = v
        else:
            vacios.append(f"habitos.{hab}")
    return llenos, vacios, negativos
