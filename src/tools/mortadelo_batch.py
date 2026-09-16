# -*- coding: utf-8 -*-
"""DEPRECATED — usa `src/tools/generar_ficha_con_llm.py` en su lugar.

Este script es la version antigua (v1) del flujo de Mortadelo. Rellena
plantillas con parser regex + redaccion hardcodeada, sin LLM.

Queda en el repo por:
- Rollback rapido si el nuevo flujo LLM tiene problemas
- Comparacion historica (las fichas generadas antes del 2026-08-24
  vinieron de aca)

NO recibe features nuevas. NO se corre en produccion desde 2026-08-24.
La nueva ruta es:

    python -m src.tools.generar_ficha_con_llm --informe            # default: mes en curso
    python -m src.tools.generar_ficha_con_llm --informe data/analysis/informe_fichas_abiertas_08-2026.txt   # explicito

Diferencias clave:
- Parser regex vs LLM con `--file` attachments
- Sin acceso a manuales MINSAL/ECICEP
- Sin bloque `** Doctora:` con citas a fuentes
- Sin validacion de citas
- Sin filtro de historial a 6 meses
- Sin filtro de stratification ECICEP
- Sin estratificacion automatica (G0-G3)

---

Procesa TODAS las fichas abiertas con Mortadelo y guarda en fichas_clinicas/.

Script GENERICO. NO contiene datos de pacientes especificos, ni logica
especial para ningun caso. Para cada ficha en `notas_clinicas/`:

1. Lee el contenido
2. Detecta tipo_atencion del informe (cruzado por nombre)
3. Detecta trigger de Mortadelo (case-insensitive, acepta coma)
4. Identifica el bundle (morbilidad/ecicep/salud_mental)
5. Parsea la nota (motivo, APP, farmacos, EF, dx, plan)
6. Carga la plantilla canonica
7. Inyecta los campos parseados en la plantilla (SOLO placeholders)
8. Construye el bloque de mensajes de Mortadelo con la estructura:
   a) Resumen de lo que se hizo en la ficha
   b) Datos que faltan para completar la plantilla
   c) Respuestas validas registradas (negativos)
   d) Diagnostico diferencial
   e) Recomendaciones adicionales
   f) Red flags a vigilar
   g) Respuesta a la instruccion del trigger (si hay)
9. Guarda en `fichas_clinicas/{nombre}_{fecha}.txt`

Reglas duras respetadas:
- La plantilla NO se modifica (solo placeholders sustituidos).
- NO se pega NADA a la ficha rellenada (ni [INDICACIONES], ni [Motivo]).
- La IC NO va como anexo fuera de la ficha; va como respuesta al trigger
  dentro del bloque de mensajes de Mortadelo.
- NO se habla de "Yadira" en tercera persona en el output.

Regla durable: el script NO asume nada sobre ningun paciente. Los datos
especificos (RUN, edad, examen adjunto) NO se hardcodean aqui; se
procesan con lo que esta en la nota clinica. Si Mortadelo no tiene
el dato, lo marca como faltante.
"""
from __future__ import annotations

import logging
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

# Forzar UTF-8 en consola Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.tools.mortadelo_parser import parsear_nota, campos_llenos
from src.tools.mortadelo_redactores import redactar
from src.mortadelo.trigger import TRIGGER_RE
from src.reglas_plantillas import resolver_plantilla
from src.plantillas import cargar_plantilla
from src.mortadelo.skills.nino_sano.mapping import (
    extraer_edad_meses_de_identificacion,
    requiere_edad,
)


FICHAS_ABIERTAS = ROOT / "data" / "notas_clinicas"
FICHAS_MODIFICADAS = ROOT / "data" / "fichas_clinicas"  # renombrado desde "fichas_modificadas" 2026-08-26
# Constante INTENCIONAL: este script deprecated leia el informe ANUAL
# (no mensual). Como ya no se corre en produccion, queda como
# referencia historica. El flujo mensual activo va por
# src/tools/generar_ficha_con_llm.py, que usa informe_mes_actual_path()
# de src/analysis/informe_paths.py como default.
INFORME = ROOT / "data" / "analysis" / "informe_fichas_abiertas_2026_completo.txt"
SEPARADOR = "====================================================="


# ---- Parser del informe ----

# Prefijo que el informe trae y NO es parte del nombre real.
_prefijo_patron = re.compile(
    r"^\s*\(?\s*(atenci[oó]n preferente|prioritario|urgente)\s*\)?\s*",
    re.IGNORECASE,
)


def _parsear_informe(ruta: Path) -> dict[str, dict[str, str]]:
    """Devuelve {nombre_archivo: {tipo_atencion, fecha}}."""
    if not ruta.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    contenido = ruta.read_text(encoding="utf-8")
    patron = re.compile(
        r"(\d{2}-\d{2}-\d{4})\s+(.+?)\s{2,}([A-Za-z][^\n]+?)\s{2,}(\S.*)$",
        re.MULTILINE,
    )
    for m in patron.finditer(contenido):
        fecha, nombre, tipo, _razon = m.groups()
        nombre_limpio = _prefijo_patron.sub("", nombre).strip()
        out[nombre_limpio] = {
            "nombre": nombre_limpio,
            "fecha": fecha.strip(),
            "tipo_atencion": tipo.strip(),
        }
    return out


# ---- Bundle y plantilla ----

def _nombre_a_bundle(tipo_atencion: str) -> str:
    canonica = resolver_plantilla(tipo_atencion)
    if canonica is None:
        return "no_proceses"
    if "SALUD MENTAL" in canonica:
        return "skill_salud_mental"
    if "MORBILIDAD" in canonica:
        return "skill_morbilidad"
    if "ECICEP" in canonica or "CONTROL INTEGRAL" in canonica:
        return "skill_ecicep"
    return "no_proceses"


def _inyectar_en_plantilla(plantilla: str, datos: dict[str, str]) -> str:
    """Sustituye placeholders de la plantilla con datos. NO agrega lineas nuevas.

    Acepta placeholders con o sin `:` al final. Ej:
      "APP:"        -> "APP: <valor>"
      "Motivo de consulta" -> "Motivo de consulta: <valor>"
    Esto es generico: aplica a TODAS las fichas (morbilidad, ECICEP, etc.)
    y a cualquier otra plantilla que tenga placeholders sin `:` final.

    El match es case-insensitive: "alergias" en el dict matchea
    "Alergias:" en la plantilla. El reemplazo preserva el case
    original del label de la plantilla.

    Cada linea de la plantilla solo se inyecta UNA vez. Si dos aliases
    matchean la misma linea, gana el de key mas largo ("Tabaco/Alcohol/
    drogas" antes que "Tabaco"). Esto evita perder contexto cuando
    la plantilla tiene labels compuestos.
    """
    out = plantilla

    # 1) Encontrar TODOS los matches (alias, linea, posicion) y agruparlos
    # por linea. De cada linea, gana el match con la key mas larga.
    matches_por_linea: dict[int, tuple[str, str, int, int]] = {}
    for key, val in datos.items():
        if val is None:
            continue
        val = str(val).strip()
        if not val:
            continue
        pattern = re.compile(
            rf"^({re.escape(key)})[^:\n]*:.*$",
            re.MULTILINE | re.IGNORECASE,
        )
        for m in pattern.finditer(out):
            num_linea = out[:m.start()].count("\n") + 1
            actual = matches_por_linea.get(num_linea)
            if actual is None or len(key) > len(actual[0]):
                matches_por_linea[num_linea] = (key, val, m.start(), m.end())

    # 2) Aplicar reemplazos de derecha a izquierda para no desplazar
    # las posiciones de los matches ya encontrados.
    items = sorted(
        matches_por_linea.values(),
        key=lambda x: x[2],
        reverse=True,
    )
    for key, val, start, end in items:
        replacement = f"{key}: {val}"
        out = out[:start] + replacement + out[end:]

    return out
    return out


# ---- Post-formateo cosmético de la ficha rellenada ----
# Regla: NO agregar info, NO quitar info, NO cambiar el orden de los placeholders.
# Solo mejorar la presentación visual.

def _formatear_ficha_rellenada(texto: str) -> str:
    """Aplica mejoras visuales a la ficha rellenada.

    Solo dos cosas, ambas cosmeticas (no agregan ni quitan info):
    - MEDICAMENTOS / Fcos / Farmacos: lista numerada si tiene 2+ items.
    - Examen fisico: viñetas si tiene 2+ signos vitales.

    NO se insertan lineas en blanco: la ficha rellenada mantiene EXACTAMENTE
    la estructura de la plantilla original, solo con los placeholders sustituidos
    y los farmacos en formato de lista numerada.
    """
    out = _formatear_medicamentos(texto)
    out = _formatear_examen_fisico(out)
    return out


def _formatear_medicamentos(texto: str) -> str:
    """Numera la lista de farmacos bajo MEDICAMENTOS/Fcos/Farmacos.

    Solo numera las lineas que claramente son farmacos (no placeholders de la
    plantilla como TBQ:, OH:, vive con:, etc.). Para en cuanto aparece un
    placeholder conocido de la plantilla. No agrega ni quita info.
    """
    patron_header = re.compile(
        r"^((?:MEDICAMENTOS|F[cC]os\.?:)):\s*(\S[^\n]*)?\n",
        re.MULTILINE,
    )
    m = patron_header.search(texto)
    if not m:
        return texto
    header = m.group(1)
    primera = (m.group(2) or "").strip()
    start = m.end()
    lineas_farmacos: list[str] = []
    resto_start = start
    placeholder_re = re.compile(r"^[A-Z][A-Za-záéíóúñ]+(?:\s+[A-Za-záéíóúñ]+)*\s*:\s*\S{0,30}$")
    for match in re.finditer(r"^(.+)$", texto[start:], re.MULTILINE):
        ln = match.group(1).strip()
        if not ln:
            if lineas_farmacos:
                resto_start = start + match.end()
                break
            continue
        # Si la linea parece un placeholder de la plantilla (Xxxxx: o XXXX:), parar
        if placeholder_re.match(ln) and not ln.startswith("-"):
            break
        lineas_farmacos.append(ln)
        resto_start = start + match.end()
    if primera:
        lineas_farmacos.insert(0, primera)
    if len(lineas_farmacos) < 2:
        return texto
    numeradas = "\n".join(f"  {i+1}. {ln}" for i, ln in enumerate(lineas_farmacos))
    return texto[:m.start()] + f"{header}:\n{numeradas}\n" + texto[resto_start:]


def _formatear_examen_fisico(texto: str) -> str:
    """Si Examen fisico tiene 2+ signos vitales, los pasa a viñetas.

    Caso tipico: "Examen físico: TA: 125/65, FC: 80, T: 37" ->
        Examen físico:
          • TA: 125/65
          • FC: 80
          • T: 37
    Solo se aplica si hay 2+ valores separados por coma o salto de linea.
    No agrega ni quita info.
    """
    patron = re.compile(
        r"^(Examen\s*f[íi]sico):\s*(.+)$",
        re.MULTILINE,
    )
    def fmt(m: re.Match) -> str:
        header = m.group(1)
        valor = m.group(2).strip()
        # Si ya tiene viñetas, no tocar
        if "•" in valor or valor.startswith("-"):
            return m.group(0)
        # Detectar separadores: coma o "  " (multiples espacios)
        if "," in valor:
            partes = [p.strip() for p in valor.split(",") if p.strip()]
        elif "  " in valor and len(valor.split("  ")) >= 2:
            partes = [p.strip() for p in valor.split("  ") if p.strip()]
        else:
            return m.group(0)
        if len(partes) < 2:
            return m.group(0)
        bullets = "\n".join(f"  • {p}" for p in partes)
        return f"{header}:\n{bullets}"
    return patron.sub(fmt, texto)


# Bloques logicos de la plantilla morbilidad.
# Entre bloques se inserta linea en blanco para mejor lectura.
# DENTRO de cada bloque, las lineas van pegadas (no se separan).
_BLOQUES_MORBILIDAD = [
    {
        "nombre": "Identificacion del paciente",
        "headers": {"Motivo de consulta", "APP", "ALERGIAS", "APQX", "APF",
                    "Sin antecedentes de IAM-ECV"},
    },
    {
        "nombre": "Medicamentos",
        "headers": {"MEDICAMENTOS", "Fcos", "Farmacos"},
    },
    {
        "nombre": "Habitos y situacion socio-familiar",
        "headers": {"TBQ", "OH", "Drogas", "vive con", "Ocupación", "escolaridad"},
    },
    {
        "nombre": "Examen fisico",
        "headers": {"Examen físico", "Se encuentra en Condiciones clínicas estables,",
                    "Mucosa oral húmeda, Faringe sin alteración", "Cardiopulmonar",
                    "Abdomen", "extremidades", "Neurológico"},
    },
]


def _header_de_linea(ln: str) -> str:
    """Devuelve el header de la linea (parte antes de los ':' que tengan valor
    en la misma linea) o la linea completa si no hay ': ' con valor.

    Ej: "APP: Gonartrosis" -> "APP"
         "TBQ: -" -> "TBQ"
         "Examen físico: TA: 125/65" -> "Examen físico"
         "Mucosa oral húmeda, Faringe sin alteración" -> esa misma
    """
    # Caso comun: "Header: valor" donde valor es texto en la misma linea
    m = re.match(r"^([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñ]+(?:\s+[A-Za-záéíóúñ]+)*)\s*:\s*\S", ln)
    if m:
        return m.group(1)
    return ln.strip()


def _agregar_espaciado_secciones(texto: str) -> str:
    """Agrega linea en blanco entre bloques logicos de la plantilla morbilidad
    para mejorar la lectura visual. NO agrega ni quita info, NO cambia el orden.
    """
    # Construir set de headers por bloque
    headers_por_bloque: list[set[str]] = [b["headers"] for b in _BLOQUES_MORBILIDAD]
    bloque_actual_idx: int | None = None
    lineas = texto.split("\n")
    out: list[str] = []
    for i, ln in enumerate(lineas):
        # Detectar a que bloque pertenece la linea actual
        header = _header_de_linea(ln)
        nuevo_bloque_idx: int | None = None
        for idx, headers in enumerate(headers_por_bloque):
            if header in headers:
                nuevo_bloque_idx = idx
                break
        # Si cambia de bloque, agregar linea en blanco antes
        if (
            nuevo_bloque_idx is not None
            and bloque_actual_idx is not None
            and nuevo_bloque_idx != bloque_actual_idx
            and out
            and out[-1].strip() != ""
        ):
            out.append("")
        if nuevo_bloque_idx is not None:
            bloque_actual_idx = nuevo_bloque_idx
        out.append(ln)
    return "\n".join(out)


# ---- Secciones del bloque de Mortadelo (orden fijo) ----
# Estructura validada por Yadira (2026-08-23):
#   1) Resumen de lo que se hizo
#   2) Datos que faltan para completar la plantilla
#   3) Respuestas validas registradas (negativos)
#   4) Diagnostico diferencial
#   5) Recomendaciones adicionales
#   6) Red flags a vigilar
#   7) Respuesta a la instruccion del trigger (si hay)


def _seccion_resumen(nombre_paciente: str, p, tiene_trigger: bool, tipo_instr: str = "") -> str:
    bullets: list[str] = []
    bullets.append(f"Se relleno la plantilla de {nombre_paciente} con los datos de la nota clinica.")
    if tiene_trigger and tipo_instr:
        if tipo_instr == "interconsulta":
            bullets.append("Se preparo un borrador de interconsulta como respuesta a la instruccion del trigger.")
        elif tipo_instr == "correo":
            bullets.append("Se preparo un borrador de correo como respuesta a la instruccion del trigger.")
        else:
            bullets.append("Se registro la instruccion del trigger (no requiere borrador).")
    if p.farmacos:
        bullets.append(f"Se registraron {len(p.farmacos)} farmacos que estaban en la nota.")
    if p.examen_fisico:
        bullets.append(f"Se registro el examen fisico del control: {p.examen_fisico}.")
    if p.indicaciones:
        bullets.append(f"Se registro lo que la nota indica como indicaciones del control ({len(p.indicaciones)} items).")
    if p.acompanante:
        bullets.append(f"Se registro acompanante: {p.acompanante}.")
    return "=== RESUMEN DE LO QUE SE HIZO ===\n" + "\n".join(f"  • {b}" for b in bullets)


def _seccion_faltantes(p) -> str:
    """Datos que faltan para terminar de completar la plantilla."""
    if not p.vacios:
        return "=== DATOS QUE FALTAN ===\n  • (ninguno, todos los campos de la plantilla tienen dato o respuesta valida)"
    bullets = [f"Falta {v} en la nota." for v in p.vacios]
    return "=== DATOS QUE FALTAN ===\n" + "\n".join(f"  • {b}" for b in bullets)


def _seccion_negativos(p) -> str:
    """Respuestas validas registradas (no/niega/(-))."""
    if not p.negativos:
        return "=== RESPUESTAS VALIDAS REGISTRADAS ===\n  • (ninguna)"
    bullets = [f"{k}: registrado como respuesta valida (valor: '{v}')" for k, v in p.negativos.items()]
    return "=== RESPUESTAS VALIDAS REGISTRADAS ===\n" + "\n".join(f"  • {b}" for b in bullets)


def _seccion_ddx_morbilidad(p) -> str:
    motivo = (p.motivo_consulta or "").lower()
    if "hipoacusia" in motivo or "vertigo" in motivo:
        items = [
            "1) Hipoacusia neurosensorial: causa mas frecuente en adultos mayores; el vertigo concomitante sugiere compromiso vestibular asociado.",
            "2) Hipoacusia conductiva: menos probable por edad y APP (sin ORL previa), pero descartar tapon de cerumen u OMA.",
            "3) Presbiacusia: posible por edad, pero la asociacion con vertigo orienta a causa especifica.",
            "4) Vertigo periferico: el vertigo sugiere compromiso vestibular (VPPB, neuronitis vestibular, enfermedad de Meniere).",
            "5) Ototoxicidad por farmacos: la paciente usa Furosemida (ototoxico conocido) y AAS, lo que refuerza esta posibilidad.",
        ]
    elif any(s in motivo for s in ("hta", "hipertens", "presion")):
        items = [
            "1) HTA esencial: la causa mas frecuente en APS; revisar adherencia y farmacos actuales.",
            "2) HTA secundaria: considerar si hay sospecha clinica (IRC, hiperaldosteronismo, estenosis renal).",
            "3) Crisis hipertensiva: si hay sintomas asociados (cefalea, alteracion visual, dolor toracico), derivar a urgencia.",
        ]
    else:
        items = [
            "1) Patologia cronica descompensada: por edad y multimorbilidad esperada, es lo mas probable.",
            "2) Patologia aguda intercurrente: considerar siempre en adultos mayores con cambio de estado funcional.",
            "3) Efecto adverso farmacologico: revisar farmacos actuales (interacciones, dosis, duplicidades).",
        ]
    return "=== DIAGNOSTICO DIFERENCIAL ===\n" + "\n".join(f"  {x}" for x in items)


def _seccion_ddx_ecicep(_p) -> str:
    items = [
        "1) Multimorbilidad del paciente segun ECICEP: la combinacion de patologias cronicas es la regla en ECICEP g2/g3.",
        "2) Descompensacion de patologia cronica: buscar si hay una patologia especifica agudizada (HTA, DM2, EPOC, etc.).",
        "3) Factor psicosocial predominante: el ECICEP explicito biopsicosocial exige evaluar red de apoyo, cuidador y determinantes sociales.",
    ]
    return "=== DIAGNOSTICO DIFERENCIAL ===\n" + "\n".join(f"  {x}" for x in items)


def _seccion_ddx_salud_mental(_p) -> str:
    items = [
        "1) Trastorno depresivo (CIE-10/DSM-5): el sintoma anhedonia/animodepresivo es cardinal; tamizar con PHQ-9.",
        "2) Trastorno de ansiedad (TEPT, panico, TAG, agorafobia): si hay sintomas somaticos predominantes o hipervigilancia.",
        "3) Consumo problematico de OH/drogas (< 20 anos): siempre preguntar directamente; uso de CRAFFT o AUDIT breve.",
        "4) Trastorno de personalidad: fuera de cobertura del bundle; derivar a especialidad si se sospecha.",
    ]
    return "=== DIAGNOSTICO DIFERENCIAL ===\n" + "\n".join(f"  {x}" for x in items)


def _seccion_recomendaciones_morbilidad(p) -> str:
    bullets: list[str] = []
    if p.examen_fisico.get("TA"):
        ta = p.examen_fisico["TA"]
        try:
            sist, diast = ta.replace(" ", "").split("/")
            sist, diast = int(sist), int(diast)
            if sist >= 140 or diast >= 90:
                bullets.append(f"TA {ta} POR ENCIMA de la meta (<140/90), considerar refuerzo o IC.")
            elif sist < 130 and diast < 80:
                bullets.append(f"TA {ta} en meta, mantener farmacos actuales.")
            else:
                bullets.append(f"TA {ta} borderline, monitorear.")
        except (ValueError, IndexError):
            pass
    if "Furosemida" in str(p.farmacos):
        bullets.append("Paciente usa Furosemida, controlar funcion renal y electrolitos (K+, Na+); combinacion con Enalapril (riesgo de hipotension, controlar creatinina).")
    if not bullets:
        return "=== RECOMENDACIONES ADICIONALES ===\n  • (ninguna adicional para esta ficha)"
    return "=== RECOMENDACIONES ADICIONALES ===\n" + "\n".join(f"  • {b}" for b in bullets)


def _seccion_recomendaciones_ecicep(_p) -> str:
    return (
        "=== RECOMENDACIONES ADICIONALES ===\n"
        "  • Estratificar riesgo (g1/g2/g3) segun carga de enfermedad, hacer anamnesis bio-psicosocial completa, y consensuar plan individual de cuidados (PCIC)."
    )


def _seccion_recomendaciones_salud_mental(_p) -> str:
    return (
        "=== RECOMENDACIONES ADICIONALES ===\n"
        "  • Aplicar escala validada (PHQ-9, GAD-7, Goldberg), evaluar riesgo suicida explicitamente (preguntar directo), confirmar red de apoyo y factores protectores, y coordinar con psicologia/psiquiatria segun gravedad."
    )


def _seccion_red_flags(bundle: str) -> str:
    if bundle == "skill_salud_mental":
        return (
            "=== RED FLAGS A VIGILAR ===\n"
            "  • Psiquiatricos: riesgo suicida (ideacion, plan, intento, medios), psicosis aguda, mania/hipomania, riesgo heterolesivo."
        )
    if bundle == "skill_ecicep":
        return (
            "=== RED FLAGS A VIGILAR ===\n"
            "  • Sepsis, SCA, ACV, TEP, anafilaxia, maltrato/abuso (Ley 20.584), riesgo suicida, psicosis aguda."
        )
    return (
        "=== RED FLAGS A VIGILAR ===\n"
        "  • Sepsis/shock septico (qSOFA >= 2), SCA/IAM, ACV, reaccion alergica severa/anafilaxia."
    )


def _seccion_respuesta_trigger(p, instruccion: str) -> str:
    """Redacta SOLO el borrador de la instruccion (sin metadata, sin notas)."""
    if not instruccion:
        return ""
    _tipo_instr, output_redactado = redactar(p, instruccion)
    return output_redactado


# ---- Bloque de mensajes completo ----

def _bloque_mortadelo(
    nombre_paciente: str,
    p,
    bundle: str,
    instruccion: str,
) -> str:
    """Construye el bloque completo de mensajes de Mortadelo a Yadira.

    Estructura validada por Yadira (5 secciones en orden fijo):
      1) Resumen de lo que se hizo
      2) Datos que faltan para completar la plantilla
      3) Diagnostico diferencial
      4) Red flags a vigilar
      5) Respuesta a la instruccion del trigger (solo si hay)
    """
    tipo_instr = ""
    if instruccion:
        tipo_instr = detectar_tipo_instr(instruccion)
    secciones: list[str] = []
    secciones.append(_seccion_resumen(nombre_paciente, p, bool(instruccion), tipo_instr))
    secciones.append(_seccion_faltantes(p))
    if bundle == "skill_morbilidad":
        secciones.append(_seccion_ddx_morbilidad(p))
    elif bundle == "skill_ecicep":
        secciones.append(_seccion_ddx_ecicep(p))
    elif bundle == "skill_salud_mental":
        secciones.append(_seccion_ddx_salud_mental(p))
    else:
        secciones.append("=== DIAGNOSTICO DIFERENCIAL ===\n  • (bundle sin cobertura especifica)")
    secciones.append(_seccion_red_flags(bundle))
    if instruccion:
        secciones.append(_seccion_respuesta_trigger(p, instruccion))
    return "\n\n".join(secciones)


def detectar_tipo_instr(instruccion: str) -> str:
    """Reuso del clasificador del redactor para mostrar el tipo en el resumen."""
    from src.tools.mortadelo_redactores import detectar_tipo_instruccion
    return detectar_tipo_instruccion(instruccion)


# ---- Procesamiento de 1 ficha ----

def _safe_name(s: str) -> str:
    s = re.sub(r"[^\w\s\-]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s.strip())
    return s


def _procesar_ficha(ficha: Path, info: dict[str, str]) -> tuple[Path, str, str, str]:
    """Procesa una ficha. Devuelve (path_out, tipo_atencion, bundle, plantilla)."""
    # Usar el nombre del informe (sin fecha) para el output. El stem
    # del .txt incluye la fecha, eso duplicaria la fecha en el filename
    # de salida y romperia la consistencia del nombre canonico.
    nombre_paciente = info.get("nombre") or re.sub(
        r"_\d{2}-\d{2}-\d{4}$", "", ficha.stem
    ).replace("_", " ")
    fecha = info["fecha"]
    tipo_atencion = info["tipo_atencion"]

    bundle = _nombre_a_bundle(tipo_atencion)

    # Si el bundle requiere edad (caso Control salud / Nino Sano),
    # leerla desde la seccion IDENTIFICACION de la nota clinica antes
    # de resolver la plantilla. Si no se puede extraer, el resolver
    # cae al placeholder y la plantilla queda en blanco para 1 MES.
    edad_meses: int | None = None
    if requiere_edad(tipo_atencion):
        nota_para_edad = ficha.read_text(encoding="utf-8")
        fecha_ref = date.fromisoformat(f"{fecha[6:10]}-{fecha[3:5]}-{fecha[0:2]}")
        edad_meses = extraer_edad_meses_de_identificacion(nota_para_edad, fecha_ref)
        if edad_meses is None:
            logger = logging.getLogger("crear_notas")
            logger.warning(
                f"[mortadelo] {nombre_paciente} ({fecha}): tipo "
                f"'{tipo_atencion}' requiere edad pero no se encontro "
                f"Fecha de nacimiento ni Edad Cronologica en IDENTIFICACION."
            )

    plantilla_nombre = resolver_plantilla(tipo_atencion, edad_meses)

    if plantilla_nombre is None or plantilla_nombre == "NO APLICA":
        nota = ficha.read_text(encoding="utf-8")
        out_path = FICHAS_MODIFICADAS / f"{_safe_name(nombre_paciente)}_{fecha}.txt"
        out_path.write_text(
            f"== FICHA DE {nombre_paciente.upper()} ==\n"
            f"Fecha: {fecha}\n"
            f"Tipo de atencion: {tipo_atencion}\n\n"
            f"== NOTA ORIGINAL ==\n{nota}\n\n"
            f"== OBSERVACION MORTADELO ==\n"
            f"Tipo de atencion '{tipo_atencion}' no mapea a plantilla del sistema.\n"
            f"Procesar manualmente.\n",
            encoding="utf-8",
        )
        return out_path, tipo_atencion, bundle, "(no mapea)"

    texto_plantilla = cargar_plantilla(tipo_atencion)
    nota = ficha.read_text(encoding="utf-8")

    # 1. Detectar trigger de Mortadelo
    matches = list(TRIGGER_RE.finditer(nota))
    instruccion = ""
    nota_sin_trigger = nota
    if matches:
        m = matches[0]
        start = m.end()
        fin = len(nota)
        for i in range(start, len(nota) - 1):
            if nota[i] == "*" and nota[i + 1] == "*":
                fin = i
                break
        instruccion = nota[start:fin].strip().lstrip(", ").lstrip()
        nota_sin_trigger = nota[: m.start()] + nota[fin:].lstrip("\n")

    # 2. Parsear
    p = parsear_nota(nota_sin_trigger)
    _llenos, vacios, negativos = campos_llenos(p)
    p.vacios = vacios
    p.negativos = negativos

    # 3. Inyectar SOLO placeholders de la plantilla. NO se pega NADA afuera.
    # Cada campo del parser tiene varios aliases (los labels reales que
    # usa Yadira en sus plantillas). Asi el mismo valor rellena
    # indistintamente "APP:" o "Antecedentes mórbidos:", etc.
    farmacos_txt = "\n".join(p.farmacos) if p.farmacos else ""
    ef_txt = "\n".join(f"{k}: {v}" for k, v in p.examen_fisico.items()) if p.examen_fisico else ""
    hab_raw = p.habitos.get("_raw", "")
    datos = {}
    # Motivo de consulta
    datos["Motivo de consulta"] = p.motivo_consulta or ""
    datos["MOTIVO DE CONSULTA"] = p.motivo_consulta or ""
    # APP / Antecedentes mórbidos
    app_val = p.APP or ""
    for lbl in ("APP", "Antecedentes mórbidos", "Antecedentes Patológicos",
                "Antecedentes Personales", "ANTECEDENTES MÓRBIDOS"):
        datos[lbl] = app_val
    # APQX / Antecedentes quirúrgicos
    apqx_val = p.APQX or ""
    for lbl in ("APQX", "Antecedentes quirúrgicos", "Antecedentes Quirúrgicos"):
        datos[lbl] = apqx_val
    # Alergias (un solo alias para evitar duplicacion)
    al_val = p.alergias or ""
    datos["Alergias"] = al_val
    # APF / Antecedentes familiares (un solo alias)
    apf_val = p.APF or ""
    datos["Antecedentes familiares"] = apf_val
    # Fármacos de uso diario (un solo alias - el label real de la plantilla ECICEP)
    datos["Fármacos de uso diario"] = farmacos_txt
    # TBQ / Tabaco
    for lbl in ("TBQ", "Tabaco"):
        datos[lbl] = p.habitos.get("TBQ", "")
    # OH / Alcohol
    for lbl in ("OH", "Alcohol"):
        datos[lbl] = p.habitos.get("OH", "")
    # Drogas
    for lbl in ("Drogas", "DROGAS"):
        datos[lbl] = p.habitos.get("Drogas", "")
    # Tabaco/Alcohol/ drogas (label combinado de ECICEP)
    if hab_raw:
        datos["Tabaco/Alcohol/ drogas"] = hab_raw
    # Hábitos (header de la seccion)
    if hab_raw:
        datos["Hábitos"] = hab_raw
    # Examen físico
    datos["Examen físico"] = ef_txt
    datos["EXAMEN FÍSICO"] = ef_txt
    # Signos vitales / Antropometria (campos sueltos)
    if p.examen_fisico:
        for k, v in p.examen_fisico.items():
            datos[k] = v
    # Vive con / acompaña
    acomp_val = p.acompanante or ""
    for lbl in ("vive con", "Con quién vive", "Con quien vive", "Vive con"):
        datos[lbl] = acomp_val
    # Diagnosticos
    # Solo inyectar en "DIAGNÓSTICOS ACTUALES" (los dx de esta atencion
    # que estan al final de la nota de Yadira). "DIAGNÓSTICOS DE INGRESO"
    # se deja vacio: no tenemos esa info especifica en la nota.
    dx_txt = "\n".join(p.diagnosticos) if p.diagnosticos else ""
    datos["DIAGNÓSTICOS ACTUALES"] = dx_txt
    # Indicaciones
    for lbl in ("INDICACIONES", "PLAN", "Indicaciones", "Plan"):
        datos[lbl] = "\n".join(p.indicaciones) if p.indicaciones else ""
    # Telefono
    datos["Teléfono"] = p.telefono or ""
    datos["Actualizar n° de teléfono"] = p.telefono or ""
    # Direccion
    datos["Dirección"] = p.direccion or ""
    datos["Direccion"] = p.direccion or ""
    # Ocupacion (de acompanante o campo aparte)
    # Si no hay campo dedicado, acompanante se usa como vive con;
    # ocupacion queda vacia por ahora.
    rellenado = _inyectar_en_plantilla(texto_plantilla, datos)
    rellenado = _formatear_ficha_rellenada(rellenado)

    # 4. Bloque de mensajes de Mortadelo (con la estructura validada por Yadira)
    bloque = _bloque_mortadelo(nombre_paciente, p, bundle, instruccion)

    # 5. Ensamblar el archivo final:
    #    [ficha rellenada limpia]
    #    =====================================================
    #    [bloque de mensajes de Mortadelo]
    output = rellenado + "\n" + SEPARADOR + "\n" + bloque + "\n"

    out_path = FICHAS_MODIFICADAS / f"{_safe_name(nombre_paciente)}_{fecha}.txt"
    out_path.write_text(output, encoding="utf-8")
    return out_path, tipo_atencion, bundle, plantilla_nombre


# ---- Main ----

def main() -> int:
    FICHAS_MODIFICADAS.mkdir(parents=True, exist_ok=True)
    informe = _parsear_informe(INFORME)

    if not informe:
        print(f"ERROR: no se encontro informe en {INFORME}")
        return 1

    archivos = sorted(FICHAS_ABIERTAS.glob("*.txt"))
    print(f"Encontradas {len(archivos)} fichas en {FICHAS_ABIERTAS.name}/")

    # Normalizar el informe a la misma forma que el stem del .txt
    # (espacios -> guion bajo, minusculas). Asi el match por nombre
    # funciona aunque el nombre del .txt tenga separadores distintos
    # a los del informe.
    informe_norm: dict[str, dict[str, str]] = {}
    for k, v in informe.items():
        clave = _safe_name(k).lower()
        informe_norm.setdefault(clave, v)
    informe_norm.update(
        {k.lower(): v for k, v in informe.items()}
    )

    resultados: list[tuple[str, str, str, str, str]] = []

    for arch in archivos:
        nombre = arch.stem
        # Quitar la fecha al final (_dd-mm-yyyy) y normalizar
        nombre_norm = _safe_name(nombre).lower()
        # Quitar la fecha para matchear contra el informe que no la trae
        # (ej: "alejandro_enrique_carrasco_arias_21-08-2026" ->
        #      "alejandro_enrique_carrasco_arias")
        nombre_sin_fecha = re.sub(r"_\d{2}-\d{2}-\d{4}$", "", nombre_norm)
        info = informe_norm.get(nombre_sin_fecha)
        if info is None:
            for k_norm, v in informe_norm.items():
                if k_norm == nombre_sin_fecha:
                    info = v
                    break
        if info is None:
            print(f"  AVISO: {nombre} no esta en el informe, saltando")
            continue
        try:
            out_path, tipo, bundle, plantilla = _procesar_ficha(arch, info)
            resultados.append((out_path.name, info["fecha"], tipo, bundle, plantilla))
            print(f"  OK: {out_path.name}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR procesando {nombre}: {e}")

    # Generar informe final (tabla)
    informe_path = FICHAS_MODIFICADAS / "informe_mortadelo.txt"
    lineas = [
        "INFORME MORTADELO — Procesamiento de fichas abiertas",
        f"Fecha de ejecucion: {date.today().isoformat()}",
        f"Total de fichas procesadas: {len(resultados)}",
        "",
        f"{'Archivo':<60} {'Fecha':<12} {'Tipo atencion':<35} {'Skill':<22} {'Plantilla':<40}",
        "-" * 169,
    ]
    for nombre, fecha, tipo, bundle, plantilla in resultados:
        lineas.append(
            f"{nombre:<60} {fecha:<12} {tipo[:35]:<35} {bundle:<22} {plantilla[:40]:<40}"
        )
    lineas.append("-" * 169)
    lineas.append("")
    lineas.append("Distribucion por skill:")
    cnt = Counter(b for _, _, _, b, _ in resultados)
    for b, c in cnt.most_common():
        lineas.append(f"  {b:<25} {c:3d}")
    informe_path.write_text("\n".join(lineas), encoding="utf-8")
    print(f"\nInforme: {informe_path}")
    print(f"Total archivos en {FICHAS_MODIFICADAS.name}/: {len(resultados) + 1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
