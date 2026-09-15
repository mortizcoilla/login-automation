"""Genera fichas clínicas usando un LLM externo vía opencode.

Flujo (v2 — 1 sola llamada, agente con system prompt completo):
1. Lee la nota clínica (.txt en notas_clinicas/).
2. Detecta el tipo de atención desde el nombre del archivo o desde un informe.
3. Resuelve el mapeo tipo_atencion -> plantilla canónica vía _REGLA.
4. Carga la plantilla INMUTABLE desde plantillas/.
5. Carga las reglas del bundle (reglas.md) para transversal (red flags, cobertura).
6. Carga el PCIC base (data/pcic_base.txt) si aplica a ECICEP.
7. Construye el prompt con todo: demografía + PCIC base + plantilla + nota + reglas.
8. Invoca `opencode run --agent mortadelo --model <modelo>` (1 sola vez).
9. El agente (con su system prompt en .opencode/agent/mortadelo.md) hace
   el resto: llena la ficha, infiere con la rúbrica 4 categorías, marca
   advertencias, y agrega el bloque `** Doctora:` con sugerencias para
   próxima ficha.
10. Parsea la respuesta y la guarda en fichas_clinicas/.

Reglas duras:
- NO sobrescribe archivos existentes en fichas_clinicas/.
- NO modifica notas_clinicas/ ni plantillas/ ni .opencode/.
- La nota de Yadira es INMUTABLE; solo se extrae info.
- La ficha rellenada va a Yadira para validación. Mortadelo/LLM no decide clínicamente.
- Errores técnicos van a un log/informe_tecnico, NO a la ficha.

Uso:
    # 1 nota
    python -m src.tools.generar_ficha_con_llm --nota notas_clinicas/Alejandro_Enrique_Carrasco_Arias_21-08-2026.txt

    # Batch (default: informe del mes en curso)
    python -m src.tools.generar_ficha_con_llm --informe

    # Batch con informe explicito (ej. otro mes o reproceso)
    python -m src.tools.generar_ficha_con_llm --informe data/analysis/informe_fichas_abiertas_08-2026.txt

    # Dry-run: solo construye el prompt, lo guarda en disco para revisar
    python -m src.tools.generar_ficha_con_llm --nota notas_clinicas/X.txt --save-prompt data/prompts/

Reglas:
- Por defecto, --informe apunta al informe del mes en curso (NO anual).
- El informe ANUAL (`_completo.txt`) es para otros propositos; si lo
  pasas explicitamente, el script lo respeta, pero no es el flujo
  normal de produccion.
- Si --informe no se pasa y la nota no trae tipo_atencion, el fallback
  busca en el informe del mes en curso (no en un mes hardcoded).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

# Repo root
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.analysis.informe_paths import informe_mes_actual_path
from src.reglas_plantillas import resolver_plantilla  # type: ignore  # noqa: E402

# NOTA: importamos `cargar_plantilla` solo por retrocompatibilidad con
# callers externos; internamente usamos `cargar_plantilla_para_tipo` que
# lee el archivo directamente con la canonica (evita el bug de re-pasar
# por resolver_plantilla).


# ---------------------------------------------------------------------------
# Carga de .env (API keys LLM, sin commitear)
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """Carga .env (raíz del proyecto) en os.environ si existe.

    Implementacion minima sin dependencia de python-dotenv. Solo lee
    pares KEY=VALUE, ignora comentarios y lineas vacias. NO sobrescribe
    valores que ya esten en el environment (prioridad al shell).
    """
    import os
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    try:
        text = env_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv()


# ---------------------------------------------------------------------------
# Mapeo plantilla canonica -> bundle + manual principal (MVP)
# ---------------------------------------------------------------------------

BUNDLE_POR_PLANTILLA = {
    "MORBILIDAD": "morbilidad",
    "CONTROL INTEGRAL SIN FICHA ANTERIOR": "ecicep",
    "INGRESO ECICEP": "ecicep",
    "INGRESO SALUD MENTAL SIN ECICEP": "salud_mental",
    "CONTROL NIÑO SANO 1 MES": "nino_sano",
    "CONTROL NIÑO SANO 3 MESES": "nino_sano",
    "RECETA": "receta",
}

# Manual principal por bundle (transversal al caso).
# Si despues queremos mas granularidad (cargar el manual especifico al motivo
# de consulta), lo hacemos con heuristica + RAG. Por ahora MVP.
MANUAL_PRINCIPAL_POR_BUNDLE = {
    "morbilidad": "minsal-pscv-2017.md",
    "ecicep": "ecicep-marco.md",
    "salud_mental": "minsal-depresion-2013.md",
    "nino_sano": "minsal-ihan-2025.md",
}

DEFAULT_MODEL = "opencode-go/minimax-m2.7"  # M2.7 es el flagship MiniMax disponible en opencode-go (2026-08-26)
VISION_MODEL = "google/gemini-2.5-pro"  # para OCR de fotos de examenes
PELUSA_MODEL = "opencode-go/qwen3.7-plus"  # auditora de fichas (Qwen3.7+, familia distinta a M2.7)
PELUSA_AGENT = "pelusa"  # agente en .opencode/agent/pelusa.md

# Extensiones de imagen que el LLM con vision puede leer
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


# ---------------------------------------------------------------------------
# Tiers de modelos con fallback en cascada
# ---------------------------------------------------------------------------
# Cada tier tiene un modelo default + una lista de fallbacks ordenados.
# Si el default falla (cuota agotada, rate limit, error), se prueba el
# siguiente. Asi se evita interrumpir el batch cuando un provider se cae.
#
# Tiers:
#   - "rellenar":    extraccion estructurada de datos de la nota -> plantilla
#   - "diagnostico": dx diferencial, sugerencias, red flags (razonamiento)
#   - "vision":      OCR de fotos de examenes / heridas / documentos

DEFAULT_TIERS = {
    "rellenar": "opencode-go/qwen3.7-plus",
    "diagnostico": "opencode-go/minimax-m2.7",
    "vision": "google/gemini-2.5-pro",
}

# Fallbacks en orden. El primero es el que se prueba si el default falla.
# Ajustado segun cuotas OpenCode Go (solicitudes por 5 horas):
#   Kimi K3: 110, Grok 4.5: 120, Qwen3.8 Max: 160, GLM-5.2: 880,
#   DeepSeek V4 Pro: 1050, GPT 5.6 Luna: 2050,
#   Qwen3.7 Plus: 4300, DeepSeek V4 Flash: 7600, Kimi K2.7 Code, MiMo-V2.5: 30.100.
# Costo para 20 fichas/dia x 2 llamadas = 40 calls.
FALLBACK_POR_TIER = {
    "rellenar": [
        "opencode-go/qwen3.7-plus",       # default, 4300
        "opencode-go/deepseek-v4-flash",  # 7600
        "opencode-go/mimo-v2.5",          # 30100 (casi infinita)
        "opencode-go/hy3",                # 8x
        "opencode/hy3-free",              # free tier
    ],
    "diagnostico": [
        "opencode-go/minimax-m2.7",       # default, flagship MiniMax (2026-08-26)
        "opencode-go/qwen3.8-max",        # backup, mejor multilingual
        "opencode-go/kimi-k2.7-code",     # fallback 2
    ],
    "vision": [
        "google/gemini-2.5-pro",          # default
        "google/gemini-3.1-pro-preview",  # mas nuevo
        "google/gemini-2.5-flash",        # mas barato
        "opencode-go/grok-4.5",
        "opencode-go/deepseek-v4-flash-vision-exp",
    ],
}


# ---------------------------------------------------------------------------
# Tipos de atencion que pueden aparecer en la nota o en el informe
# ---------------------------------------------------------------------------
# El "tipo_atencion" puede no estar en la nota. Si esta, se extrae de ahi.
# Si no, se puede pasar como argumento o leer del informe.

TIPO_ATENCION_RE = re.compile(
    r"(?im)^\s*(?:Tipo\s+de\s+atenci[oó]n|Atenci[oó]n)\s*:\s*(.+?)\s*$"
)


@dataclass
class NotaInfo:
    """Lo que extraemos de la nota antes de procesarla."""
    path: Path
    nombre_paciente: str
    fecha_atencion: str
    tipo_atencion: Optional[str]
    texto: str
    trigger: Optional[str]  # instruccion que viene despues de `** mortadelo`


# ---------------------------------------------------------------------------
# Funciones puras
# ---------------------------------------------------------------------------

def parsear_cabecera_nota(texto: str) -> tuple[str, str, Optional[str]]:
    """Lee los headers `# Paciente: ...`, `# Fecha atencion: ...` y
    busca un posible `Tipo de atencion:`.

    Returns (nombre, fecha, tipo_atencion_o_None).
    """
    nombre = ""
    fecha = ""
    tipo = None
    for line in texto.splitlines():
        s = line.strip()
        if s.startswith("# Paciente:"):
            nombre = s.split(":", 1)[1].strip()
        elif s.startswith("# Fecha atencion:"):
            fecha = s.split(":", 1)[1].strip()
        else:
            m = TIPO_ATENCION_RE.match(s)
            if m:
                tipo = m.group(1).strip()
    return nombre, fecha, tipo


def extraer_trigger(texto: str) -> Optional[str]:
    """Detecta `** mortadelo <instruccion>`. Case-insensitive, tolera coma.
    Devuelve la instruccion (sin el `** mortadelo`) o None.
    """
    # Mismo patron que src/mortadelo/trigger.py
    patron = re.compile(
        r"\*\*\s*[Mm][Oo][Rr][Tt][Aa][Dd][Ee][Ll][Oo]\s*[:\-,]?\s*([^\n\r]*)",
        flags=re.IGNORECASE,
    )
    m = patron.search(texto)
    if not m:
        return None
    inst = (m.group(1) or "").strip()
    return inst if inst else None


def leer_nota(path: Path) -> NotaInfo:
    texto = path.read_text(encoding="utf-8")
    nombre, fecha, tipo = parsear_cabecera_nota(texto)
    trigger = extraer_trigger(texto)
    return NotaInfo(
        path=path,
        nombre_paciente=nombre,
        fecha_atencion=fecha,
        tipo_atencion=tipo,
        texto=texto,
        trigger=trigger,
    )


def extraer_demografia(texto: str) -> dict[str, str]:
    """Lee el bloque `=== INICIO IDENTIFICACION ===` y extrae los campos clave.

    Returns dict con: nombre, run, fecha_nacimiento, edad, sexo,
    direccion, telefono, prevision, sector, medico_cabecera.
    Si un campo no esta, devuelve ''.
    """
    campos = {
        "Médico de cabecera:": "medico_cabecera",
        "RUN:": "run",
        "Fecha de nacimiento:": "fecha_nacimiento",
        "Edad Cronológica:": "edad",
        "Sexo Biológico:": "sexo",
        "Dirección:": "direccion",
        "Sector:": "sector",
        "Previsión:": "prevision",
        "Teléfono:": "telefono",
        "Estado civil:": "estado_civil",
        "Número de ficha:": "numero_ficha",
    }
    out: dict[str, str] = {v: "" for v in campos.values()}
    in_bloque = False
    for line in texto.splitlines():
        s = line.strip()
        if s.startswith("=== INICIO IDENTIFICACION"):
            in_bloque = True
            continue
        if s.startswith("=== FIN IDENTIFICACION"):
            in_bloque = False
            continue
        if not in_bloque:
            continue
        for label, key in campos.items():
            if s.startswith(label):
                val = s[len(label):].strip()
                # Si la clave ya tiene valor, concatenar (caso de Teléfono con varios)
                if out[key] and key == "telefono":
                    out[key] = f"{out[key]} | {val}"
                elif not out[key]:
                    out[key] = val
                break
    return out


def buscar_tipo_en_informe(nombre: str, fecha: str, informe_path: Path) -> Optional[str]:
    """Busca el tipo_atencion en el informe por nombre+fecha. Case-insensitive.

    El informe tiene formato de TABLA con lineas como:
        21-08-2026    Alejandro Enrique Carrasco Arias  Control integral ecicep-g2        Consulta
    """
    if not informe_path.exists():
        return None
    texto = informe_path.read_text(encoding="utf-8", errors="replace")
    nombre_n = nombre.lower().strip()
    fecha_n = fecha.strip()
    for line in texto.splitlines():
        s = line.strip()
        # Saltar headers, separadores y lineas vacias
        if not s or s.startswith("===") or s.startswith("INFORME") or s.startswith("Total"):
            continue
        if s.startswith("Fecha") or s.startswith("Distribucion") or s.startswith("---"):
            continue
        # La linea tiene al menos: fecha, nombre, tipo
        # Split por 2+ espacios
        parts = re.split(r"\s{2,}", s)
        if len(parts) < 3:
            continue
        f_informe = parts[0].strip()
        n_informe = parts[1].strip().lstrip("(").rstrip(")").strip()
        # A veces el nombre tiene "(Atencion Preferente)" pegado
        n_informe_clean = re.sub(r"\(.*?\)", "", n_informe).strip()
        t_informe = parts[2].strip()
        if f_informe == fecha_n and (
            n_informe.lower() == nombre_n
            or n_informe_clean.lower() == nombre_n
            or nombre_n in n_informe.lower()
            or n_informe.lower() in nombre_n
        ):
            return t_informe
    return None


def cargar_plantilla_para_tipo(
    tipo_atencion: str, edad_meses: Optional[int] = None
) -> Optional[str]:
    """Resuelve tipo_atencion -> plantilla canonica y la carga.

    NOTA: NO usa `src.plantillas.cargar_plantilla` porque esa funcion
    re-pasa el argumento por `resolver_plantilla`, y la canonica (uppercase)
    no esta en las claves de _REGLA. Aqui leemos el archivo directamente
    con la canonica resuelta.
    """
    canonica = resolver_plantilla(tipo_atencion, edad_meses=edad_meses)
    if not canonica:
        return None
    ruta = ROOT / "plantillas" / f"{canonica}.txt"
    if not ruta.exists():
        return None
    return ruta.read_text(encoding="utf-8")


def cargar_manual_principal(bundle: str) -> str:
    """Carga el manual principal del bundle como texto.

    Si el manual no existe, intenta cargar `reglas.md` del bundle como
    fallback (que SI existe en todos los bundles y tiene red flags +
    cobertura). Si tampoco, devuelve ''.

    El LLM tiene conocimiento medico general; los manuales son para
    citas especificas (paginas/secciones del MINSAL).
    """
    if not bundle:
        return ""
    # 1) Manual principal
    nombre = MANUAL_PRINCIPAL_POR_BUNDLE.get(bundle)
    if nombre:
        path = ROOT / "src" / "mortadelo" / "skills" / bundle / "manuales" / nombre
        if path.exists():
            return path.read_text(encoding="utf-8")
    # 2) Fallback: reglas.md del bundle
    reglas_path = ROOT / "src" / "mortadelo" / "skills" / bundle / "reglas.md"
    if reglas_path.exists():
        return reglas_path.read_text(encoding="utf-8")
    return ""


def cargar_pcic_base() -> str:
    """Carga el template PCIC base de Yadira (data/pcic_base.txt).

    El template incluye el texto fijo (Opciones, Acuerdos, Responsable,
    Plazo) y las reglas de customizacion del Objetivo segun las
    condiciones del paciente (peso, HTA, DM2, tiroides, etc.).

    Si el archivo no existe, devuelve ''. En ese caso, el LLM
    (en el bloque `** Doctora:`) avisara que no hay template PCIC
    disponible y que el PCIC queda como "A VALIDAR POR YADIRA".
    """
    path = ROOT / "data" / "pcic_base.txt"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def construir_prompt(
    plantilla: str,
    nota_texto: str,
    manual: str,
    trigger: Optional[str],
    demografia: dict[str, str],
    nombre_paciente: str,
    fecha_atencion: str,
    tipo_atencion: str,
    examenes_adjuntos: Optional[list[dict]] = None,
    pcic_base: str = "",
) -> str:
    """Construye el prompt UNICO para el agente mortadelo (v2).

    El agente tiene un system prompt completo en
    .opencode/agent/mortadelo.md (rubrica 4 categorias, loops, web
    access, sugerencias para proxima ficha). Este prompt solo le pasa
    los DATOS del caso: demografia, PCIC base, plantilla, nota, manual.

    Args:
        plantilla: texto de la plantilla canonica (INMUTABLE).
        nota_texto: texto completo de la nota clinica extraida de Rayen.
        manual: contenido del reglas.md del bundle (puede ser '').
        trigger: instruccion de Yadira si la nota trae `** mortadelo <instr>`.
        demografia: dict con campos del paciente.
        nombre_paciente, fecha_atencion, tipo_atencion: de la nota.
        examenes_adjuntos: lista de {nombre, transcripcion} si hay OCR previo.
        pcic_base: contenido de data/pcic_base.txt (template PCIC de Yadira).
    """
    lineas: list[str] = []
    lineas.append("# TAREA")
    lineas.append("")
    lineas.append("Rellena la plantilla de abajo con los datos de la nota clinica de Yadira.")
    lineas.append("La ficha SIEMPRE debe quedar COMPLETA. No dejes placeholders vacios.")
    lineas.append("Usa la rubrica de inferencia de tu system prompt (categorias A/B/C/D).")
    lineas.append("Marca cada inferencia con `~` y reportala en `=== ADVERTENCIAS DE INFERENCIA ===`.")
    lineas.append("Para campos clinicos sensibles (categoria B/C), escribe `A VALIDAR CON PACIENTE`")
    lineas.append("o `A VALIDAR POR YADIRA` segun corresponda.")
    lineas.append("Al final, agrega el bloque `** Doctora:` con la estructura de tu system prompt.")
    lineas.append("")
    if trigger:
        lineas.append("## INSTRUCCION DE TRIGGER")
        lineas.append("")
        lineas.append(f"Yadira escribio en la nota: `** mortadelo {trigger}`")
        lineas.append("")
        lineas.append("Ademas de la ficha rellenada, responde a esta instruccion en la seccion")
        lineas.append("`=== INSTRUCCIONES DE TRIGGER ===` del bloque `** Doctora:`.")
        lineas.append("")
    lineas.append("## DATOS DEMOGRAFICOS DEL PACIENTE (usar para la cabecera)")
    lineas.append("")
    lineas.append("```")
    for k, v in demografia.items():
        lineas.append(f"{k}: {v or '(falta en la nota)'}")
    lineas.append("nombre_paciente: " + nombre_paciente)
    lineas.append("fecha_atencion: " + fecha_atencion)
    lineas.append("tipo_atencion: " + tipo_atencion)
    lineas.append("```")
    lineas.append("")
    if examenes_adjuntos:
        lineas.append("## EXAMENES ADJUNTOS (transcripcion automatica con LLM vision)")
        lineas.append("")
        lineas.append("Estas transcripciones vienen de imagenes/PDFs adjuntos a la ficha.")
        lineas.append("INCORPORA los datos clinicos relevantes a la plantilla rellenada")
        lineas.append("(seccion de examenes, antecedentes, o donde corresponda).")
        lineas.append("Si la transcripcion es ruido o ilegible, ignorala.")
        lineas.append("")
        for i, ex in enumerate(examenes_adjuntos, 1):
            lineas.append(f"### Examen adjunto {i}: {ex['nombre']}")
            lineas.append("")
            lineas.append("```")
            lineas.append(ex["transcripcion"].strip())
            lineas.append("```")
            lineas.append("")
    if pcic_base:
        lineas.append("## PCIC BASE (template de Yadira, customizar Objetivo segun paciente)")
        lineas.append("")
        lineas.append("Este es el template que Yadira aprobo. La seccion 1 (Objetivo)")
        lineas.append("se CUSTOMIZA segun las condiciones del paciente (ver reglas de")
        lineas.append("customizacion al final del template). Las secciones 2-5 quedan")
        lineas.append("iguales en la mayoria de los casos.")
        lineas.append("")
        lineas.append("Si la nota de Yadira trae un PCIC explicito (ej. bloque `** PCIC:`),")
        lineas.append("USA ESE en vez del template. El template es fallback.")
        lineas.append("")
        lineas.append("```")
        lineas.append(pcic_base.strip())
        lineas.append("```")
        lineas.append("")
    lineas.append("## REGLAS DEL BUNDLE (reglas.md — transversal: red flags, cobertura, principios)")
    lineas.append("")
    lineas.append("```")
    lineas.append(manual.strip() or "(sin reglas cargadas)")
    lineas.append("```")
    lineas.append("")
    lineas.append("## PLANTILLA INMUTABLE (rellena los placeholders, NO cambies el orden)")
    lineas.append("")
    lineas.append("```")
    lineas.append(plantilla.strip())
    lineas.append("```")
    lineas.append("")
    lineas.append("## NOTA CLINICA DE YADIRA")
    lineas.append("")
    lineas.append("```")
    lineas.append(nota_texto.strip())
    lineas.append("```")
    lineas.append("")
    lineas.append("## OUTPUT ESPERADO (estructura EXACTA — sigue tu system prompt)")
    lineas.append("")
    lineas.append("Sigue la estructura de tu system prompt de mortadelo:")
    lineas.append("- Cabecera demografica (obligatoria ANTES de la plantilla).")
    lineas.append("- Plantilla rellenada completa, sin placeholders vacios.")
    lineas.append("- Inferencias marcadas con `~` en el cuerpo.")
    lineas.append("- Bloque `** Doctora:` con: Resumen / Advertencias de inferencia /")
    lineas.append("  Datos que requieren validacion / Diagnostico diferencial /")
    lineas.append("  Sugerencias para la nota / Sugerencias para el diagnostico /")
    lineas.append("  Red flags a vigilar / Sugerencias para proxima ficha /")
    lineas.append("  (opcional) Instrucciones de trigger.")
    lineas.append("")
    lineas.append("NUNCA escribas despues del bloque `** Doctora:`. Sin despedidas.")
    return "\n".join(lineas)


def construir_prompt_rellenar(
    plantilla: str,
    nota_texto: str,
    demografia: dict[str, str],
    nombre_paciente: str,
    fecha_atencion: str,
    tipo_atencion: str,
    examenes_adjuntos: Optional[list[dict]] = None,
    trigger: Optional[str] = None,
) -> str:
    """Prompt para la LLAMADA 1: rellenar la plantilla (extraccion estructurada).

    Modelo tier bajo (deepseek-flash, qwen, etc.). Tarea mecanica: copiar
    datos de la nota a la plantilla, respetar orden, no inventar.

    NO incluye system prompt complejo (es trabajo simple). NO pide bloque
    `** Doctora:` (eso lo hace la llamada 2 con modelo potente).
    """
    lineas = []
    lineas.append("# SISTEMA")
    lineas.append("")
    lineas.append("Eres Mortadelo, asistente de la Dra. Yadira Hernandez Cabrera (CESFAM Raul Cuevas, San Bernardo).")
    lineas.append("Tu trabajo es EXTRACCION ESTRUCTURADA: copiar datos de la nota clinica a la plantilla.")
    lineas.append("NO diagnosticas. NO prescribes. NO decides clinicamente.")
    lineas.append("")
    lineas.append("# REGLAS DURAS")
    lineas.append("")
    lineas.append("- La plantilla es INMUTABLE: NO cambies el orden, NO agregues secciones, NO elimines lineas.")
    lineas.append("- La nota de Yadira es INMUTABLE: solo extraes info, no la reescribes.")
    lineas.append("- 'no' / 'niega' / '(-)' son respuestas validas. NO las marques como faltantes.")
    lineas.append("- Si la plantilla tiene 2+ MEDICAMENTOS, numerarlos (1., 2., 3., ...).")
    lineas.append("- Si el examen fisico tiene 2+ items, listar con vinetas.")
    lineas.append("- Si falta un dato, marca [FALTA: <razon breve>]. NUNCA inventes.")
    lineas.append("- Si la nota tiene la marca '** mortadelo <instruccion>', BORRALA de la ficha (es trigger interno).")
    lineas.append("")
    lineas.append("# DATOS DEMOGRAFICOS DEL PACIENTE (usar para la cabecera)")
    lineas.append("")
    lineas.append("```")
    for k, v in demografia.items():
        lineas.append(f"{k}: {v or '(falta en la nota)'}")
    lineas.append("nombre_paciente: " + nombre_paciente)
    lineas.append("fecha_atencion: " + fecha_atencion)
    lineas.append("tipo_atencion: " + tipo_atencion)
    lineas.append("```")
    lineas.append("")
    if examenes_adjuntos:
        lineas.append("# EXAMENES ADJUNTOS (transcripcion automatica con LLM vision)")
        lineas.append("")
        lineas.append("Estas transcripciones vienen de imagenes/PDFs adjuntos a la ficha.")
        lineas.append("INCORPORA los datos clinicos relevantes a la plantilla rellenada")
        lineas.append("(seccion de examenes, antecedentes, o donde corresponda).")
        lineas.append("Si la transcripcion es ruido o ilegible, ignorala.")
        lineas.append("")
        for i, ex in enumerate(examenes_adjuntos, 1):
            lineas.append(f"## Examen adjunto {i}: {ex['nombre']}")
            lineas.append("")
            lineas.append("```")
            lineas.append(ex["transcripcion"].strip())
            lineas.append("```")
            lineas.append("")
    lineas.append("# PLANTILLA INMUTABLE (rellena los placeholders, NO cambies el orden)")
    lineas.append("")
    lineas.append("```")
    lineas.append(plantilla.strip())
    lineas.append("```")
    lineas.append("")
    lineas.append("# NOTA CLINICA DE YADIRA")
    lineas.append("")
    lineas.append("```")
    lineas.append(nota_texto.strip())
    lineas.append("```")
    lineas.append("")
    lineas.append("# OUTPUT (estructura EXACTA)")
    lineas.append("")
    lineas.append("```text")
    lineas.append("# Paciente: <nombre_paciente>")
    lineas.append("# RUN: <run>")
    lineas.append("# Fecha de nacimiento: <fecha_nacimiento>")
    lineas.append("# Edad: <edad>")
    lineas.append("# Sexo: <sexo>")
    lineas.append("# Direccion: <direccion>")
    lineas.append("# Telefono: <telefono>")
    lineas.append("# Prevision: <prevision>")
    lineas.append("# Fecha de atencion: <fecha_atencion>")
    lineas.append("# Tipo de atencion: <tipo_atencion>")
    lineas.append("# Medico de cabecera: <medico_cabecera>")
    lineas.append("# Sector: <sector>")
    lineas.append("")
    lineas.append("---")
    lineas.append("")
    lineas.append("<plantilla rellenada, sin modificar el orden, sin agregar secciones>")
    lineas.append("```")
    lineas.append("")
    lineas.append("# REGLAS DE OUTPUT")
    lineas.append("")
    lineas.append("- La cabecera demografica va SIEMPRE al inicio, antes de la plantilla.")
    lineas.append("- Despues de la cabecera, una linea con '---', luego la plantilla rellenada.")
    lineas.append("- La plantilla va COMPLETA, con cada placeholder rellenado o marcado [FALTA: ...].")
    lineas.append("- NO incluyas el bloque `** Doctora:` (eso lo hace otra llamada).")
    lineas.append("- NO incluyas meta-comentarios, NO digas 'como IA...', NO despidas.")
    return "\n".join(lineas)


def construir_prompt_doctora(
    ficha_rellenada: str,
    nota_texto: str,
    manual: str,
    trigger: Optional[str],
    examenes_adjuntos: Optional[list[dict]] = None,
) -> str:
    """Prompt para la LLAMADA 2: generar el bloque `** Doctora:`.

    Modelo tier alto (minimax-m3, kimi-k3, qwen3.8-max). Tarea de
    razonamiento clinico: dx diferencial, sugerencias con citas, red flags.
    """
    lineas = []
    lineas.append("# SISTEMA")
    lineas.append("")
    lineas.append("Eres Mortadelo, asistente de la Dra. Yadira Hernandez Cabrera (CESFAM Raul Cuevas, San Bernardo).")
    lineas.append("Recibes una ficha clinica YA RELLENADA por otro agente. Tu trabajo es UNICAMENTE")
    lineas.append("generar el bloque `** Doctora:` con consejo para Yadira.")
    lineas.append("")
    lineas.append("# REGLA SUPREMA: NUNCA DECIDES")
    lineas.append("")
    lineas.append("- NO diagnosticas (ni confirmas, ni descartas, ni cierras dx).")
    lineas.append("- NO prescribes.")
    lineas.append("- NO cierras la ficha.")
    lineas.append("- NO decides si la atencion esta completa.")
    lineas.append("- SOLO sugieres. Yadira lee, decide, corrige y cierra.")
    lineas.append("")
    lineas.append("# CITAS OBLIGATORIAS")
    lineas.append("")
    lineas.append("Cada sugerencia en `** Doctora:` DEBE incluir su fuente:")
    lineas.append("    sugerencia -> manual, seccion/pagina")
    lineas.append("Si no tienes cita, OMITE la sugerencia. Es preferible omitir a inventar.")
    lineas.append("")
    lineas.append("# FICHA YA RELLENADA (no la modifiques, solo usala como contexto)")
    lineas.append("")
    lineas.append("```")
    lineas.append(ficha_rellenada.strip())
    lineas.append("```")
    lineas.append("")
    lineas.append("# NOTA ORIGINAL DE YADIRA (para contexto)")
    lineas.append("")
    lineas.append("```")
    lineas.append(nota_texto.strip())
    lineas.append("```")
    lineas.append("")
    if examenes_adjuntos:
        lineas.append("# EXAMENES ADJUNTOS (transcripcion automatica con vision)")
        lineas.append("")
        for i, ex in enumerate(examenes_adjuntos, 1):
            lineas.append(f"## {ex['nombre']}")
            lineas.append("")
            lineas.append("```")
            lineas.append(ex["transcripcion"].strip())
            lineas.append("```")
            lineas.append("")
    lineas.append("# MANUAL DE REFERENCIA (MINSAL)")
    lineas.append("")
    lineas.append("```")
    lineas.append(manual.strip() or "(sin manual cargado)")
    lineas.append("```")
    lineas.append("")
    if trigger:
        lineas.append("# INSTRUCCION DE TRIGGER")
        lineas.append("")
        lineas.append(f"Yadira escribio en la nota: `** mortadelo {trigger}`")
        lineas.append("")
        lineas.append("Ademas del bloque `** Doctora:`, responde a esta instruccion en la seccion")
        lineas.append("`=== INSTRUCCIONES DE TRIGGER ===` al FINAL del bloque.")
        lineas.append("")
    lineas.append("# OUTPUT (estructura EXACTA, solo el bloque `** Doctora:`)")
    lineas.append("")
    lineas.append("```text")
    lineas.append("=====================================================")
    lineas.append("** Doctora:")
    lineas.append("")
    lineas.append("=== RESUMEN DE LO QUE SE HIZO ===")
    lineas.append("...")
    lineas.append("")
    lineas.append("=== DATOS QUE FALTAN ===")
    lineas.append("...")
    lineas.append("")
    lineas.append("=== DIAGNOSTICO DIFERENCIAL ===")
    lineas.append("1. <dx candidato 1> - <razon breve>")
    lineas.append("2. <dx candidato 2> - <razon breve>")
    lineas.append("3. ...")
    lineas.append("")
    lineas.append("=== SUGERENCIAS PARA LA NOTA ===")
    lineas.append("- sugerencia -> manual, seccion/pagina")
    lineas.append("")
    lineas.append("=== SUGERENCIAS PARA EL DIAGNOSTICO ===")
    lineas.append("- sugerencia -> manual, seccion/pagina")
    lineas.append("")
    lineas.append("=== RED FLAGS A VIGILAR ===")
    lineas.append("- <red flag> -> manual, seccion/pagina")
    if examenes_adjuntos:
        lineas.append("")
        lineas.append("=== EXAMENES ADJUNTOS ANALIZADOS ===")
        lineas.append("Transcripcion(es) automatica(s) con LLM vision. Yadira debe validar contra la imagen original.")
    if trigger:
        lineas.append("")
        lineas.append("=== INSTRUCCIONES DE TRIGGER ===")
        lineas.append(f"<respuesta a: {trigger}>")
    lineas.append("```")
    lineas.append("")
    lineas.append("# REGLAS DE OUTPUT")
    lineas.append("")
    lineas.append("- Empieza EXACTAMENTE con la linea `=====================================================`.")
    lineas.append("- Despues `** Doctora:` y el contenido.")
    lineas.append("- NO incluyas la ficha rellenada (ya viene en otra llamada).")
    lineas.append("- NO incluyas meta-comentarios, NO digas 'como IA...', NO despidas.")
    lineas.append("- NO escribas nada despues del bloque `** Doctora:` (o de la seccion de trigger si la hay).")
    return "\n".join(lineas)


def _resolver_opencode_exe() -> str:
    """Devuelve la ruta absoluta al .exe de opencode (NO al wrapper .cmd/.ps1).

    Por que NO usamos shutil.which("opencode") + el wrapper:
        - El wrapper .ps1/.cmd pierde el stdin de Python (rompe el pipe).
        - subprocess.run() con el .cmd cuelga porque Windows abre cmd.exe
          intermedio que no cierra stdin correctamente.
        - Invocar el .exe directo via CreateProcess propaga stdin nativo.

    Returns:
        Ruta absoluta al .exe (string).

    Raises:
        RuntimeError si no se encuentra.
    """
    # Candidatos ordenados por probabilidad
    candidatos = [
        Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "opencode-ai" / "bin" / "opencode.exe",
        Path("C:/Program Files/nodejs/node_modules/opencode-ai/bin/opencode.exe"),
        # Linux/macOS via nvm (fallback por si Miguel corre desde WSL)
        Path.home() / ".npm-global" / "lib" / "node_modules" / "opencode-ai" / "bin" / "opencode",
        Path("/usr/local/lib/node_modules/opencode-ai/bin/opencode"),
    ]
    for c in candidatos:
        if c.exists() and c.is_file():
            return str(c)

    # Ultimo fallback: shutil.which + verificar que sea .exe
    import shutil
    found = shutil.which("opencode")
    if found and found.lower().endswith((".exe", "")):
        # Si el which resuelve a un wrapper .cmd o .ps1, saltar
        if not found.lower().endswith((".cmd", ".ps1")):
            return found

    raise RuntimeError(
        "opencode.exe no encontrado. Verificar instalacion con "
        "`npm i -g opencode-ai` y que exista en "
        "%APPDATA%\\npm\\node_modules\\opencode-ai\\bin\\opencode.exe"
    )


def _parsear_eventos_json(output: str) -> str:
    """Extrae el texto final del LLM del stream JSON de opencode.

    opencode --format json emite una linea por evento. El formato REAL es:
        {"type":"text","part":{"type":"text","text":"..."}, ...}
        {"type":"tool_call","part":{"...","tool":"..."}}
        {"type":"step_finish","part":{...}}

    El campo `text` esta anidado en `part.text` (no top-level). Tambien
    soportamos variantes top-level y `message.content` para retrocompat.

    Si no hay eventos text, devolvemos el output completo como fallback.
    """
    import json
    partes: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(ev, dict):
            continue

        # 1) Formato opencode real: text dentro de part.text
        part = ev.get("part")
        if isinstance(part, dict):
            t = part.get("text")
            if isinstance(t, str) and t:
                partes.append(t)
                continue
            # Algunas veces part.content es lista
            content = part.get("content")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and isinstance(c.get("text"), str):
                        partes.append(c["text"])
                continue
            if isinstance(content, str) and content:
                partes.append(content)
                continue

        # 2) Variante top-level text
        if ev.get("type") in ("text", "message", "content") and isinstance(ev.get("text"), str):
            partes.append(ev["text"])
            continue

        # 3) Formato assistant con message.content (Claude/OpenAI style)
        if ev.get("type") == "assistant" and isinstance(ev.get("message"), dict):
            content = ev["message"].get("content")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and isinstance(c.get("text"), str):
                        partes.append(c["text"])
            elif isinstance(content, str):
                partes.append(content)

    if partes:
        return "".join(partes)
    # No hay texto en el stream. Detectar si fue truncation por limite de tokens
    # (reason="length") u otro fallo. Si es asi, lanzar error explicito en vez
    # de devolver JSON crudo que el caller guardaria como ficha vacia.
    import json as _json
    last_finish_reason: Optional[str] = None
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = _json.loads(line)
        except (ValueError, _json.JSONDecodeError):
            continue
        if isinstance(ev, dict):
            part = ev.get("part")
            if isinstance(part, dict):
                reason = part.get("reason")
                if isinstance(reason, str):
                    last_finish_reason = reason
    if last_finish_reason == "length":
        raise RuntimeError(
            "opencode LLM alcanzo limite de tokens de output (reason=length). "
            "El LLM no termino de generar la ficha. Subir max_tokens o simplificar prompt."
        )
    # Fallback: devolver el output crudo (puede ser formatted text no-JSON)
    return output


def invocar_opencode(
    prompt: str,
    model: str = DEFAULT_MODEL,
    agent: str = "mortadelo",
    timeout: int = 600,
    archivos: Optional[list[Path]] = None,
) -> str:
    """Llama a `opencode.exe run --agent <agent> --model <model>` con el prompt
    por stdin y devuelve la respuesta por stdout.

    Invoca el .exe directo (NO el wrapper .cmd/.ps1) para evitar que
    Windows rompa el pipe de stdin.

    Args:
        prompt: texto del prompt (puede ser corto si se pasan archivos adjuntos).
        model: modelo a usar (default: DEFAULT_MODEL).
        agent: nombre del agent opencode (default: mortadelo).
        timeout: segundos para la llamada.
        archivos: lista opcional de Paths para pasar como `--file` (patron
            del chat Mavis). Si se pasan, opencode los trata como adjuntos
            multimodales en vez de inline en el prompt.

    Flags:
        --format json: emite eventos JSON line-delimited (parseable).
        --auto: auto-aprueba permisos del agent para que no se cuelgue
                esperando confirmacion interactiva.
        --print-logs: logs van a stderr (no contaminan stdout).

    Levanta RuntimeError si opencode falla o devuelve codigo != 0.
    """
    opencode_exe = _resolver_opencode_exe()

    cmd = [
        opencode_exe, "run",
        "--agent", agent,
        "--model", model,
        "--format", "json",
        "--auto",
        "--print-logs",
    ]
    if archivos:
        for f in archivos:
            cmd.extend(["--file", str(f)])

    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"opencode fallo (rc={proc.returncode}):\n"
            f"STDERR:\n{proc.stderr[-2000:]}\n"
            f"STDOUT (tail):\n{proc.stdout[-500:]}"
        )
    # Parsear JSON events para extraer texto limpio
    texto = _parsear_eventos_json(proc.stdout)
    return texto.strip() if texto.strip() else proc.stdout.strip()


def invocar_opencode_con_adjuntos(
    prompt: str,
    archivos: list[Path],
    model: str = VISION_MODEL,
    timeout: int = 300,
) -> str:
    """Llama a `opencode.exe run --model <model> --file <archivo>...` con el prompt
    por stdin y los archivos como adjuntos (vision/multimodal).

    Usar para OCR de imagenes de examenes clinicos (audiometrias, radiografias, etc.)
    o para procesar PDFs.

    Invoca el .exe directo (NO el wrapper) para evitar que Windows rompa
    el pipe de stdin.

    NOTA: NO usa `--agent` porque el agent mortadelo no esta pensado para vision.
    El modelo interpreta el prompt y los archivos adjuntos libremente.
    """
    opencode_exe = _resolver_opencode_exe()

    cmd = [
        opencode_exe, "run",
        "--model", model,
        "--format", "json",
        "--auto",
        "--print-logs",
    ]
    for f in archivos:
        cmd.extend(["--file", str(f)])

    proc = subprocess.run(
        cmd,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"opencode (vision) fallo (rc={proc.returncode}):\n"
            f"STDERR:\n{proc.stderr[-2000:]}\n"
            f"STDOUT (tail):\n{proc.stdout[-500:]}"
        )
    texto = _parsear_eventos_json(proc.stdout)
    return texto.strip() if texto.strip() else proc.stdout.strip()


def invocar_con_fallback(
    tier: str,
    prompt: str,
    agent: str = "mortadelo",
    timeout: int = 300,
    archivos: Optional[list[Path]] = None,
) -> tuple[str, str]:
    """Prueba modelos del tier en orden hasta que uno funcione.

    Args:
        tier: "rellenar" | "diagnostico" | "vision"
        prompt: prompt para el LLM
        agent: nombre del agent opencode (default: mortadelo)
        timeout: timeout por intento
        archivos: si se pasan, usa invocar_opencode_con_adjuntos (vision)

    Returns:
        (output, modelo_usado). Si todos fallan, lanza RuntimeError.
    """
    if tier not in FALLBACK_POR_TIER:
        raise ValueError(f"tier desconocido: {tier}")
    modelos = FALLBACK_POR_TIER[tier]
    last_err: Optional[Exception] = None
    for modelo in modelos:
        try:
            log(f"  [{tier}] probando {modelo}...")
            if archivos:
                output = invocar_opencode_con_adjuntos(
                    prompt=prompt,
                    archivos=archivos,
                    model=modelo,
                    timeout=timeout,
                )
            else:
                output = invocar_opencode(
                    prompt=prompt,
                    model=modelo,
                    agent=agent,
                    timeout=timeout,
                )
            output_clean = output.strip()
            if output_clean and len(output_clean) > 10:
                log(f"  [{tier}] OK con {modelo} ({len(output_clean)} chars)")
                return output, modelo
            log(f"  [{tier}] {modelo} devolvio vacio, probando siguiente")
        except subprocess.TimeoutExpired as e:
            last_err = e
            log(f"  [{tier}] {modelo} timeout, probando siguiente")
        except RuntimeError as e:
            last_err = e
            log(f"  [{tier}] {modelo} fallo, probando siguiente")
    raise RuntimeError(
        f"todos los modelos del tier '{tier}' fallaron. ultimo error: {last_err}"
    )


def _invocar_con_fallback_archivos(
    tier: str,
    prompt: str,
    agent: str,
    archivos: list[Path],
    timeout: int = 600,
) -> tuple[str, str]:
    """Como invocar_con_fallback pero usa invocar_opencode (con agent + archivos).

    Para fichas: el agente mortadelo carga su system prompt (rubrica, 9 reglas,
    cita obligatoria, `** Doctora:`). Los archivos se pasan como `--file` (patron
    del chat Mavis) para que el prompt text sea corto y el modelo no se cuelgue.
    """
    if tier not in FALLBACK_POR_TIER:
        raise ValueError(f"tier desconocido: {tier}")
    modelos = FALLBACK_POR_TIER[tier]
    last_err: Optional[Exception] = None
    for modelo in modelos:
        try:
            log(f"  [{tier}] probando {modelo}...")
            output = invocar_opencode(
                prompt=prompt,
                model=modelo,
                agent=agent,
                timeout=timeout,
                archivos=archivos,
            )
            output_clean = output.strip()
            if output_clean and len(output_clean) > 10:
                log(f"  [{tier}] OK con {modelo} ({len(output_clean)} chars)")
                return output, modelo
            log(f"  [{tier}] {modelo} devolvio vacio, probando siguiente")
        except subprocess.TimeoutExpired as e:
            last_err = e
            log(f"  [{tier}] {modelo} timeout, probando siguiente")
        except RuntimeError as e:
            last_err = e
            log(f"  [{tier}] {modelo} fallo, probando siguiente")
    raise RuntimeError(
        f"todos los modelos del tier '{tier}' fallaron. ultimo error: {last_err}"
    )


def _seguridad_nombre_archivo(s: str) -> str:
    """Normaliza string para usarlo como nombre de archivo (sin espacios, sin acentos)."""
    import re
    s = s.lower()
    s = re.sub(r"[^a-z0-9_-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:80] or "archivo"


def _extraer_receta_vigente(texto_nota: str) -> str:
    """Extrae el contenido del bloque `=== INICIO PLAN RECETAS === ... === FIN PLAN RECETAS ===`
    de una nota Yadira. Devuelve el string limpio (sin los marcadores) o
    string vacio si el bloque no existe o esta vacio.

    Formato esperado del bloque:
        - [Controlada (disp. unica)] Vigencia: DD  MMM  YYYY
            - Farmaco dosis presentacion (indicacion | posologia)
            - Farmaco dosis presentacion (indicacion | posologia)
    """
    m = re.search(
        r"=== INICIO PLAN RECETAS ===\s*\n(.*?)\n\s*=== FIN PLAN RECETAS ===",
        texto_nota,
        re.DOTALL,
    )
    if not m:
        return ""
    contenido = m.group(1).strip()
    # Si solo hay separadores o nada, devolver vacio
    lineas = [
        l for l in contenido.splitlines()
        if l.strip() and not l.strip().startswith("===")
    ]
    return "\n".join(lineas).strip()


def _generar_ficha_recetas_directo(
    nota,
    demografia: dict[str, str],
) -> str:
    """Genera la ficha de Recetas DIRECTAMENTE sin pasar por el LLM.

    Regla de Yadira/Miguel (sesion 2026-08-26, memoria 'Recetas: caso especial'):
    "a ella solo se le debe repetir la receta que esta en su nota medica,
    nada mas y nada menos". El LLM no aporta valor en este caso (no genera DX,
    no sugiere farmacos, no analiza) — solo agrega riesgo de alucinacion.

    Output:
        - Cabecera demografica (10 lineas con # Paciente, # RUN, etc.)
        - Linea de la plantilla `RECETA`
        - Receta vigente copiada del bloque PLAN RECETAS de la nota
        - Doctora block minimo: "Sin observaciones adicionales."

    Si PLAN RECETAS esta vacio, el cuerpo dice "No hay receta activa
    registrada en la nota."
    """
    lineas: list[str] = []
    # Cabecera demografica
    lineas.append(f"# Paciente: {demografia.get('nombre', nota.nombre_paciente) or nota.nombre_paciente}")
    lineas.append(f"# RUN: {demografia.get('run', '') or '(falta en la nota)'}")
    lineas.append(f"# Fecha nac: {demografia.get('fecha_nacimiento', '') or '(falta en la nota)'}")
    lineas.append(f"# Edad: {demografia.get('edad', '') or '(falta en la nota)'}")
    lineas.append(f"# Sexo: {demografia.get('sexo', '') or '(falta en la nota)'}")
    lineas.append(f"# Dirección: {demografia.get('direccion', '') or '(falta en la nota)'}")
    lineas.append(f"# Teléfono: {demografia.get('telefono', '') or '(falta en la nota)'}")
    lineas.append(f"# Previsión: {demografia.get('prevision', '') or '(falta en la nota)'}")
    lineas.append(f"# Fecha atención: {nota.fecha_atencion}")
    lineas.append(f"# Tipo atención: {nota.tipo_atencion or 'Recetas'}")
    lineas.append("")
    # Plantilla (literal)
    lineas.append("RECETA")
    lineas.append("")

    # Cuerpo: receta vigente
    receta = _extraer_receta_vigente(nota.texto)
    if receta:
        lineas.append(receta)
    else:
        lineas.append("No hay receta activa registrada en la nota.")

    # Separador + Doctora minimo
    lineas.append("")
    lineas.append("=====================================================")
    lineas.append("** Doctora:")
    lineas.append("")
    lineas.append("Sin observaciones adicionales.")

    return "\n".join(lineas) + "\n"


def _output_degenerado(output: str, min_chars: int = 500, min_body_chars: int = 200) -> bool:
    """Heuristica para detectar output degenerado del LLM.

    Patron visto en 2026-08-26: el LLM produce solo un bloque `** Doctora:`
    con 1-3 lineas de meta-commentary (ej: "Sin observaciones adicionales
    segun bundle X. Ficha completada con datos disponibles.") sin haber
    rellenado la plantilla. Esto es output vacio disfrazado.

    Criterio de "degenerado":
    - Output total < min_chars (500)
    - O BIEN: el body (antes de `** Doctora:`) tiene < min_body_chars (200)
      chars, lo que indica que la plantilla no se relleno.
    - O BIEN: el separador esta PEGADO a `** Doctora:` sin newline
      (regex `={20,}` seguido de ` Doctora:` sin newline). Eso es output
      roto que el sanitizer puede arreglar localmente, pero si el resto
      del body es pequeno y el Doctora esta pegado al separator, el LLM
      no produjo una ficha valida (sesion 2026-08-26, caso Karina Ximena
      Tapia).

    Args:
        output: output limpio (post-limpiar_output) del LLM.
        min_chars: minimo de chars totales para considerar el output valido.
        min_body_chars: minimo de chars en el cuerpo (antes de Doctora).
    """
    if len(output.strip()) < min_chars:
        return True
    if "** Doctora:" in output:
        body = output.split("** Doctora:")[0]
        if len(body.strip()) < min_body_chars:
            return True
        # Caso pegado: separator sin newline antes de ** Doctora:
        # NO retornamos True aca (el sanitizer lo arregla), pero si ademas
        # el body es < 2x min_body_chars, el LLM claramente no produjo
        # contenido util -> degenerado.
        if re.search(r"={20,}\*\* Doctora:", output):
            if len(body.strip()) < 2 * min_body_chars:
                return True
    return False


def _es_trigger_examenes(trigger: str) -> bool:
    """Detecta si el trigger de la nota es de examenes adjuntos.

    Acepta variantes (case-insensitive):
    - `** mortadelo examenes adjuntos`
    - `** mortadelo adjunto examenes`
    - `** mortadelo examenes externos`
    - `** mortadelo adjunto de examenes`
    - Cualquier combinacion de `examen(es)` + `adjunto(s)` en cualquier orden.
    """
    if not trigger:
        return False
    t = trigger.lower()
    # Cualquier combinacion de "examen(es)" + "adjunto(s)" en cualquier orden.
    return bool(
        re.search(r"examen(?:es)?\s+adjuntos?", t)
        or re.search(r"adjuntos?\s+(?:de\s+)?examen(?:es)?", t)
        or re.search(r"examen(?:es)?\s+externos?", t)
    )


def _guardar_adjuntos_tmp(
    nota_path: Path,
    plantilla: str,
    nota_texto: str,
    manual: str,
    pcic_base: str,
    examen_md_path: Optional[Path] = None,
) -> list[Path]:
    """Guarda las piezas grandes en temp files para pasar como `--file`.

    Patron del chat Mavis: el prompt text va corto (~1-2K) y el LLM recibe
    los archivos como adjuntos multimodales. Esto evita que el modelo se
    cuelgue con prompts inline de 35K chars.

    Args:
        nota_path, plantilla, nota_texto, manual, pcic_base: las 4 piezas
            estandar (plantilla, nota Yadira, manual del bundle, PCIC base).
        examen_md_path: si Yadira dejo `** mortadelo examenes adjuntos` en la
            nota y se encontro un `<nombre>.md` en `_adjuntos/`, este Path
            apunta a ese archivo de texto (markdown) con examenes de laboratorio
            / imagen / esp. El LLM lo lee como texto plano (NO vision).

    Returns:
        Lista de Paths a los temp files. El caller es responsable de borrarlos
        despues (PHI en disco).
    """
    import tempfile
    tmp_dir = Path(tempfile.gettempdir()) / "mortadelo_adjuntos"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    stem = _seguridad_nombre_archivo(nota_path.stem)
    paths: list[Path] = []

    # 1) Plantilla
    p = tmp_dir / f"{stem}__plantilla.txt"
    p.write_text(plantilla, encoding="utf-8")
    paths.append(p)

    # 2) Nota clinica Yadira
    p = tmp_dir / f"{stem}__nota.txt"
    p.write_text(nota_texto, encoding="utf-8")
    paths.append(p)

    # 3) Manual reglas del bundle
    if manual:
        p = tmp_dir / f"{stem}__manual.txt"
        p.write_text(manual, encoding="utf-8")
        paths.append(p)

    # 4) PCIC base
    if pcic_base:
        p = tmp_dir / f"{stem}__pcic_base.txt"
        p.write_text(pcic_base, encoding="utf-8")
        paths.append(p)

    # 5) Examen adjunto de Yadira (trigger `** mortadelo examenes adjuntos`).
    # Es TEXTO markdown (no vision). Se pasa como `--file` adicional para que
    # el LLM lo lea y use los datos en la ficha. El original NO se copia a temp
    # (es PHI); en su lugar se crea un symlink o se lee y se reescribe con
    # nombre seguro.
    if examen_md_path and examen_md_path.exists():
        contenido = examen_md_path.read_text(encoding="utf-8")
        p = tmp_dir / f"{stem}__examen_adjunto.md"
        p.write_text(contenido, encoding="utf-8")
        paths.append(p)

    return paths


def _construir_prompt_corto(
    demografia: dict[str, str],
    nombre_paciente: str,
    fecha_atencion: str,
    tipo_atencion: str,
    canonica: str,
    bundle: str,
    trigger: Optional[str],
    examen_adjunto: bool = False,
    es_recetas: bool = False,
) -> str:
    """Prompt CORTO (~1-2K chars) para enviar al agente mortadelo junto con
    los archivos adjuntos. Las piezas grandes (plantilla, nota, manual, PCIC)
    se pasan como `--file`.

    El system prompt del agente mortadelo ya carga la rubrica, las 9 reglas,
    el formato de `** Doctora:`, la citacion obligatoria, etc.

    Args:
        examen_adjunto: si True, hay un 5to adjunto `*_examen_adjunto.md`
            con examenes de laboratorio / imagen / esp. en formato markdown
            (TEXTO, no vision). El LLM debe leerlo y usar los datos.
        es_recetas: si True, la atencion es `Recetas`. Caso especial: el
            LLM SOLO debe repetir la receta vigente del bloque PLAN RECETAS
            de la nota Yadira. Nada mas, nada menos. NO genera DX, NO sugiere
            farmacos nuevos, NO agrega `** Doctora:` con analisis (memoria:
            "Recetas NO es skill", sesion 2026-08-22).
    """
    lineas: list[str] = []
    lineas.append("# TAREA")
    lineas.append("")
    lineas.append(
        "Eres Mortadelo. Rellena la plantilla adjunta (`*_plantilla.txt`) con los datos "
        "de la nota clinica de Yadira adjunta (`*_nota.txt`)."
    )
    lineas.append(
        "Las reglas del bundle estan en `*_manual.txt` (si existe). El template PCIC "
        "esta en `*_pcic_base.txt` (solo si existe; bundle ecicep)."
    )
    if examen_adjunto:
        lineas.append(
            "Hay un 5to adjunto `*_examen_adjunto.md` con examenes externos "
            "(laboratorio, imagen, esp.) en formato markdown (texto plano). "
            "LEELO y USALO en la ficha: los valores van al cuerpo en la "
            "seccion correspondiente (ej. laboratorio -> 'EXAMENES DE "
            "LABORATORIO' de la plantilla), y las interpretaciones clinicas "
            "van al bloque `** Doctora:` si son relevantes."
        )
    lineas.append("")
    lineas.append("## METADATA DEL CASO")
    lineas.append("")
    lineas.append("```")
    for k, v in demografia.items():
        lineas.append(f"{k}: {v or '(falta en la nota)'}")
    lineas.append(f"plantilla_canonica: {canonica}")
    lineas.append(f"bundle: {bundle or '(sin bundle)'}")
    lineas.append(f"nombre_paciente: {nombre_paciente}")
    lineas.append(f"fecha_atencion: {fecha_atencion}")
    lineas.append(f"tipo_atencion: {tipo_atencion}")
    lineas.append("```")
    lineas.append("")
    if trigger:
        lineas.append("## INSTRUCCION DE TRIGGER")
        lineas.append("")
        lineas.append(f"Yadira escribio: `** mortadelo {trigger}`")
        lineas.append("")
        lineas.append(
            "Ademas de la ficha rellenada, responde a esta instruccion en la seccion "
            "`=== INSTRUCCIONES DE TRIGGER ===` del bloque `** Doctora:`."
        )
        lineas.append("")
    lineas.append("## OUTPUT ESPERADO")
    lineas.append("")
    if es_recetas:
        # Caso especial: Recetas. SOLO repetir la receta vigente del PLAN
        # RECETAS de la nota Yadira. Nada mas, nada menos. NO DX, NO
        # sugerencias, NO `** Doctora:` con analisis (memoria: "Recetas
        # NO es skill", sesion 2026-08-22).
        lineas.append("**CASO ESPECIAL: RECETAS.** Esta atencion es `Recetas`.")
        lineas.append("")
        lineas.append("Tu unica tarea es:")
        lineas.append("1. Cabecera demografica (10 lineas con # Paciente, # RUN, etc.).")
        lineas.append("2. La linea de la plantilla `RECETA` tal cual.")
        lineas.append("3. Debajo de `RECETA`, lista la receta vigente del bloque")
        lineas.append("   `=== INICIO PLAN RECETAS === ... === FIN PLAN RECETAS ===`")
        lineas.append("   de la nota Yadira: nombre del farmaco, dosis, frecuencia,")
        lineas.append("   duracion y vigencia. UNA linea por farmaco. Sin agregar nada mas.")
        lineas.append("4. Cierra con la linea de 53 `=` y `** Doctora:` SOLO con el texto:")
        lineas.append("   `Sin observaciones adicionales.`")
        lineas.append("")
        lineas.append("**PROHIBIDO en este caso:**")
        lineas.append("- NO generes DX diferencial.")
        lineas.append("- NO sugieras farmacos nuevos ni cambios de dosis.")
        lineas.append("- NO agregues `=== PARA VALIDAR ===` ni `=== RED FLAGS ===` ni `=== INFERENCIAS ===`.")
        lineas.append("- NO uses `~` para inferencias (no aplica a Recetas).")
        lineas.append("- NO escribas nada en `** Doctora:` aparte de 'Sin observaciones adicionales.'")
        lineas.append("")
        lineas.append("Si el bloque `=== INICIO PLAN RECETAS ===` esta vacio o no aparece,")
        lineas.append("escribe `No hay receta activa registrada en la nota.` en el cuerpo y")
        lineas.append("cierra con `Sin observaciones adicionales.`")
    else:
        lineas.append("Sigue la estructura de tu system prompt de mortadelo:")
        lineas.append("- Cabecera demografica (obligatoria ANTES de la plantilla).")
        lineas.append("- Plantilla rellenada completa, sin placeholders vacios.")
        lineas.append("- Inferencias marcadas con `~` en el cuerpo.")
        lineas.append("- Bloque `** Doctora:` con: Resumen / Advertencias de inferencia /")
        lineas.append("  Datos que requieren validacion / Diagnostico diferencial /")
        lineas.append("  Sugerencias para la nota / Sugerencias para el diagnostico /")
        lineas.append("  Red flags a vigilar / Sugerencias para proxima ficha /")
        lineas.append("  (opcional) Instrucciones de trigger.")
    lineas.append("")
    lineas.append("NUNCA escribas despues del bloque `** Doctora:`. Sin despedidas.")
    return "\n".join(lineas)


def _detectar_adjuntos_sin_transcribir(
    nombre_paciente: str,
    fecha_atencion: str,
    adjuntos_dir: Path,
) -> list[Path]:
    """Heuristica de matching de adjuntos (mismo codigo que
    analizar_adjuntos_imagen) SIN invocar el vision LLM.

    Util para dry-run, donde queremos saber que imagenes se detectarian
    sin gastar minutos en la transcripcion.
    """
    if not adjuntos_dir.exists():
        return []
    partes = nombre_paciente.split()
    nombre_corto = (partes[0] + " " + (partes[-1] if len(partes) > 1 else "")).lower()
    nombre_corto_norm = (
        nombre_corto.replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )
    fecha_dd_mm = fecha_atencion

    candidatos: list[Path] = []
    for f in adjuntos_dir.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if "_chrome_dl" in f.parts:
            continue
        fname_norm = (
            f.name.lower()
            .replace("á", "a").replace("é", "e").replace("í", "i")
            .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
        )
        if (
            fecha_dd_mm in f.name
            or nombre_corto_norm.replace(" ", "") in fname_norm.replace(" ", "")
            or any(p in fname_norm for p in nombre_corto_norm.split() if len(p) >= 4)
        ):
            candidatos.append(f)
    return sorted(candidatos)


def analizar_adjuntos_imagen(
    nombre_paciente: str,
    fecha_atencion: str,
    adjuntos_dir: Path,
) -> list[dict]:
    """Detecta imagenes activas en `adjuntos_dir` y las transcribe con LLM vision.

    Heuristica de "adjunto activo":
    - Archivos de imagen (.jpg/.png/.gif/.webp/.bmp) en adjuntos_dir.
    - Cuyo nombre contiene la fecha de la atencion (formato dd-mm-yyyy) o el
      nombre del paciente normalizado.
    - Excluye el directorio temporal `_chrome_dl` (es cache del browser, no
      examen real).

    Returns lista de dicts {path, tipo_examen, transcripcion}. Si no hay
    adjuntos o falla el OCR, devuelve [].
    """
    if not adjuntos_dir.exists():
        return []

    # Normalizar nombre y fecha para matching
    nombre_norm = (
        nombre_paciente.lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )
    # Tomar solo el primer nombre y primer apellido para matching mas flexible
    partes = nombre_paciente.split()
    nombre_corto = (partes[0] + " " + (partes[-1] if len(partes) > 1 else "")).lower()
    nombre_corto_norm = (
        nombre_corto.replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )
    fecha_dd_mm = fecha_atencion  # ya viene en formato dd-mm-yyyy

    candidatos: list[Path] = []
    for f in adjuntos_dir.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        # Excluir el cache de chrome
        if "_chrome_dl" in f.parts:
            continue
        fname = f.name.lower()
        fname_norm = (
            fname.replace("á", "a").replace("é", "e").replace("í", "i")
            .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
        )
        # Match: contiene la fecha o el nombre (normalizado o corto)
        if (
            fecha_dd_mm in f.name
            or nombre_corto_norm.replace(" ", "") in fname_norm.replace(" ", "")
            or any(p in fname_norm for p in nombre_corto_norm.split() if len(p) >= 4)
        ):
            candidatos.append(f)

    if not candidatos:
        return []

    log(f"  adjuntos imagen detectados: {[c.name for c in candidatos]}")

    resultados = []
    for img in candidatos:
        try:
            prompt = (
                f"Este es un documento clinico adjunto a la ficha del paciente "
                f"{nombre_paciente} (atencion del {fecha_atencion}).\n\n"
                f"Transcribe TODO el contenido clinico visible. El documento puede ser "
                f"CUALQUIERA de los siguientes tipos (detecta automaticamente cual es):\n\n"
                f"== SI ES UN EXAMEN (audiometria, laboratorio, imagen, ECG, etc.) ==\n"
                f"- Tipo de examen\n"
                f"- Valores numericos con sus unidades y rangos de referencia\n"
                f"- Conclusiones o interpretaciones del examinador\n"
                f"- Fecha del examen si esta visible\n"
                f"- Nombre del paciente si esta visible\n"
                f"- Nombre del profesional que firma o interpreta\n\n"
                f"== SI ES UNA FOTO CLINICA (herida, lesion, rash, fondo de ojo, etc.) ==\n"
                f"- Localizacion anatomica (parte del cuerpo)\n"
                f"- Tamano aproximado (cm o comparado con objeto de referencia)\n"
                f"- Color, bordes, textura, elevacion\n"
                f"- Tipo de lesion (ulcera, eritema, vesicula, pustula, macula, papula, "
                f"placa, nodulo, tumor, escara, necrosis, etc.)\n"
                f"- Signos de infeccion (pus, calor, rubor, edema, mal olor)\n"
                f"- Estadio o grado de evolucion\n"
                f"- Cualquier texto visible en la imagen (etiquetas, fechas, etc.)\n"
                f"- Comparacion si hay foto previa (mejor, peor, igual)\n\n"
                f"== SI ES UN DOCUMENTO ADMINISTRATIVO (receta, certificado, IC) ==\n"
                f"- Tipo de documento\n"
                f"- Fechas relevantes\n"
                f"- Profesional que lo emite\n"
                f"- Contenido textual completo\n"
                f"- Diagnosticos o indicaciones mencionados\n\n"
                f"== EN CUALQUIER CASO ==\n"
                f"- Si la imagen es ruido, ilegible o no es un documento clinico, "
                f"indicalo explicitamente con '[NO ES UN DOCUMENTO CLINICO]'.\n"
                f"- NO inventes datos. Si algo no se ve, marcalo como 'no visible'.\n"
                f"- NO hagas diagnosticos. Solo describe lo que ves.\n\n"
                f"Formato de salida: texto plano, sin markdown, organizado por "
                f"secciones con MAYUSCULAS como titulo. NO agregues meta-comentarios, "
                f"NO digas 'como IA...', NO agregues despedidas. Solo la transcripcion."
            )
            transcripcion, modelo_usado = invocar_con_fallback(
                tier="vision",
                prompt=prompt,
                agent="mortadelo",  # no se usa realmente para vision
                timeout=300,
                archivos=[img],
            )
            transcripcion = limpiar_output(transcripcion)
            if transcripcion and len(transcripcion.strip()) > 10:
                resultados.append({
                    "path": img,
                    "nombre": img.name,
                    "transcripcion": transcripcion,
                    "modelo": modelo_usado,
                })
                log(f"  vision OK: {img.name} ({len(transcripcion)} chars, modelo={modelo_usado})")
            else:
                log(f"  vision WARN: {img.name} devolvio vacio o muy corto")
        except subprocess.TimeoutExpired:
            log(f"  vision ERROR: timeout en {img.name}")
        except RuntimeError as e:
            log(f"  vision ERROR: {e}")

    return resultados


def limpiar_output(output: str) -> str:
    """Limpia prefijos comunes que el LLM puede agregar.

    Por ahora: si el output empieza con una linea que NO parece de la plantilla
    (ej. "Aqui tienes la ficha:"), la quitamos. Conservador: si no estamos
    seguros, dejamos el output tal cual.
    """
    if not output:
        return output
    s = output.strip()

    # Caso 1: empieza con ``` y termina con ``` -> los quitamos (envoltura completa)
    if s.startswith("```") and s.endswith("```"):
        lines = s.splitlines()
        if len(lines) >= 2:
            s = "\n".join(lines[1:-1]).strip()

    # Caso 2: empieza con ``` (aunque no cierre) -> quitamos solo la primera linea
    if s.startswith("```"):
        # Quitar primera linea (que es el ``` de apertura) y siguientes que
        # parezcan ser headers (ej "text" o "markdown")
        lines = s.splitlines()
        idx = 0
        while idx < len(lines) and (
            lines[idx].startswith("```") or
            lines[idx].strip() in ("", "text", "markdown", "txt")
        ):
            idx += 1
        s = "\n".join(lines[idx:]).strip()

    # Quitar prefijos comunes solo si aparecen al inicio
    prefijos = [
        "Aqui tienes la ficha:",
        "Aqui tienes:",
        "Aqui va la ficha:",
        "Output:",
        "Ficha rellenada:",
        "Resultado:",
    ]
    for p in prefijos:
        if s.lower().startswith(p.lower()):
            s = s[len(p):].lstrip()

    # Quitar ``` suelto al final si quedo
    if s.endswith("```"):
        s = s[:-3].rstrip()

    return s


def _sanitize_output(output: str, log) -> str:
    """Post-procesado que cierra los huecos que el LLM sigue abriendo pese a las
    reglas del prompt (sesión 2026-08-26). Es el último filtro antes de guardar.

    - Strip CJK / cirílico / hiragana / katakana (caracteres que el LLM desliza en
      algunas palabras, ej: "拒绝", "代谢", "reconcile不一致").
    - Strip de palabras en inglés explícitamente prohibidas (no siglas).
    - Elimina secciones NO permitidas en el bloque Doctora (SUGERENCIAS PARA *,
      RECOMENDACIONES, COBERTURA DEL BUNDLE, SOBRE EL EXAMEN FISICO).
    - Elimina A VALIDAR POR YADIRA / A VALIDAR CON PACIENTE inline en el cuerpo
      (deben estar SOLO en === PARA VALIDAR ===, no en líneas del cuerpo).
    - Garantiza la línea separadora de 53 `=` antes de `** Doctora:`.

    El cuerpo se procesa SOLO antes de `** Doctora:` — los markers en el
    bloque Doctora quedan intactos.

    Devuelve el output limpio y loguea qué se removió.
    """
    cambios: list[str] = []
    original_len = len(output)

    # Separar cuerpo y Doctora para procesar el cuerpo y dejar Doctora intacto
    if "** Doctora:" in output:
        cuerpo, _, doctora = output.partition("** Doctora:")
    else:
        cuerpo, doctora = output, ""

    # 0. Strip meta-planning lead (texto antes de la cabecera demográfica).
    # El LLM a veces arranca con "Voy a generar la ficha...", "Procedo a
    # construir...", "**Datos extraídos de la nota:**" etc. La ficha debe
    # empezar con `# Paciente: ...`.
    first_header = re.search(r"^# (Paciente|RUN|Fecha)", cuerpo, re.MULTILINE)
    if first_header and first_header.start() > 0:
        leading = cuerpo[: first_header.start()].strip()
        if leading:
            cuerpo = cuerpo[first_header.start():]
            # Mostrar solo el primer fragmento
            preview = leading[:80].replace("\n", " ")
            cambios.append(f"strip meta-planning lead: '{preview}...'")

    # 1. Strip CJK / cirílico / hiragana / katakana en TODO el output
    # (cuerpo + Doctora). El LLM desliza estos caracteres también en el bloque
    # Doctora, dentro de PARA VALIDAR y otros lugares.
    full_for_cjk = cuerpo + "** Doctora:" + doctora if doctora else cuerpo
    cjk_re = re.compile(r"[一-鿿぀-ゟ゠-ヿА-яёЁ]+")
    cjk_matches = cjk_re.findall(full_for_cjk)
    if cjk_matches:
        full_for_cjk = cjk_re.sub("", full_for_cjk)
        # Re-separar
        if "** Doctora:" in full_for_cjk:
            cuerpo, _, doctora = full_for_cjk.partition("** Doctora:")
        else:
            cuerpo, doctora = full_for_cjk, ""
        unique = list(dict.fromkeys(cjk_matches))[:10]
        cambios.append(f"strip CJK/cirílico ({len(cjk_matches)} chars: {unique})")

    # 2. Strip palabras en inglés prohibidas (NO siglas como HTA, EMPA, etc.)
    # Lista cerrada. NO matchear palabras parciales para no romper "Screening" o
    # términos médicos internacionalizados. Aplicar en TODO el output.
    english_words = [
        "given", "overall", "out of control", "however", "moreover",
        "regarding", "in order to", "reinstatement", "follow-up",
        "over-the-counter", "screening", "management", "outcome",
        "setting", "target",
    ]
    full_for_en = cuerpo + "** Doctora:" + doctora if doctora else cuerpo
    for word in english_words:
        pat = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        matches = pat.findall(full_for_en)
        if matches:
            full_for_en = pat.sub("", full_for_en)
            if "** Doctora:" in full_for_en:
                cuerpo, _, doctora = full_for_en.partition("** Doctora:")
            else:
                cuerpo, doctora = full_for_en, ""
            cambios.append(f"strip english word '{word}' ({len(matches)}x)")

    # 3. Eliminar secciones NO permitidas en Doctora (las que el LLM agrega fuera
    # del formato). Aplicar tanto en cuerpo como en Doctora por si quedaron
    # dentro del cuerpo.
    full_text = cuerpo + "** Doctora:" + doctora if doctora else cuerpo
    secciones_prohibidas = [
        r"=== SUGERENCIAS PARA LA NOTA ===\n[\s\S]*?(?=\n=== |\Z)",
        r"=== SUGERENCIAS PARA EL DX ===\n[\s\S]*?(?=\n=== |\Z)",
        r"=== SUGERENCIAS PARA PRÓXIMA FICHA ===\n[\s\S]*?(?=\n=== |\Z)",
        r"=== RECOMENDACIONES ===\n[\s\S]*?(?=\n=== |\Z)",
        r"=== COBERTURA DEL BUNDLE ===[\s\S]*?(?=\n=== |\Z)",
        r"=== SOBRE EL EXAMEN FÍSICO ===\n[\s\S]*?(?=\n=== |\Z)",
    ]
    for pat in secciones_prohibidas:
        if re.search(pat, full_text):
            full_text = re.sub(pat, "", full_text)
            nombre = pat.split("===")[1].strip().split("===")[0].strip()
            cambios.append(f"removed forbidden section: {nombre}")

    # 4. Eliminar A VALIDAR POR YADIRA / A VALIDAR CON PACIENTE inline en el CUERPO
    # (antes de `** Doctora:`). El Doctora debe tenerlos SOLO en === PARA VALIDAR ===.
    # Pattern: " — A VALIDAR (POR YADIRA|CON PACIENTE) (opcional razon en parens) [opcional .]"
    inline_av_re = re.compile(
        r"\s*—\s*A VALIDAR (?:POR YADIRA|CON PACIENTE)(?:\s*\([^)]*\))?\.?\s*",
    )
    inline_av_hits = inline_av_re.findall(cuerpo)
    if inline_av_hits:
        cuerpo = inline_av_re.sub("", cuerpo)
        cambios.append(f"strip A VALIDAR inline ({len(inline_av_hits)}x)")

    # 5. Reconstruir. Si el Doctora tenía las secciones prohibidas, hay que
    # re-separar el cuerpo.
    if doctora:
        # El full_text puede haberse modificado por sección prohibida
        if "** Doctora:" in full_text:
            cuerpo, _, doctora = full_text.partition("** Doctora:")
        else:
            cuerpo, doctora = full_text, ""
        output = cuerpo + "** Doctora:" + doctora
    else:
        output = cuerpo

    # 6. Garantizar línea de 53 `=` antes de `** Doctora:`.
    # Caso A — pegado: el LLM produjo `===...** Doctora:` sin newline.
    # El regex `^={50,}\s*$` con MULTILINE NO matchea este caso (porque
    # los `=` no estan solos en su linea), y el codigo insertaria OTRO
    # separador nuevo arriba, empeorando la cosa. Hay que detectar y
    # arreglar primero.
    # Caso B — falta: no hay separador en ninguna linea. Insertar uno
    # propio antes de `** Doctora:`.
    # Caso C — OK: el separador ya esta en su propia linea. No tocar.
    # Sesion 2026-08-26, caso Karina Ximena Tapia: el LLM produjo
    # "=====================================================** Doctora:..."
    # y ademas el body estaba vacio (solo era el separator pegado al Doctora).
    separador = "====================================================="
    if "** Doctora:" in output:
        # Caso A: separador PEGADO a `** Doctora:` (sin newline entre ellos).
        # El match es `={20,}\*\* Doctora:` — al menos 20 `=` consecutivos
        # seguidos inmediatamente del marker. Reemplazamos con separador
        # propio + newline + marker.
        pegado_re = re.compile(r"={20,}\*\* Doctora:")
        if pegado_re.search(output):
            output = pegado_re.sub(f"{separador}\n** Doctora:", output, count=1)
            cambios.append("reparado separator pegado a Doctora (sin newline)")
        # Caso B: no hay separador SOLO en su propia linea. Insertar uno.
        elif not re.search(r"^={50,}\s*$", output, re.MULTILINE):
            # Insertar separador antes del primer ** Doctora:
            output = re.sub(
                r"\*\* Doctora:",
                f"{separador}\n** Doctora:",
                output,
                count=1,
            )
            cambios.append("inserted missing separator before Doctora")
        # Caso C: separador ya esta OK. No tocar.

    # 7. Limpiar espacios duplicados y líneas vacías múltiples (cosmética)
    output = re.sub(r"  +", " ", output)  # dobles espacios
    output = re.sub(r"\n{3,}", "\n\n", output)  # triples saltos

    if cambios:
        log(f"  [sanitize] {len(cambios)} fix(es): {'; '.join(cambios)}")
        log(f"  [sanitize] {original_len} -> {len(output)} chars (delta {len(output) - original_len})")
    else:
        log(f"  [sanitize] output limpio, sin cambios")

    return output


def _prepend_warning_header(ficha_path: Path, issues: list[str], modelo: str, log) -> None:
    """Antepone un header de warning a la ficha cuando Pelusa detecta issues.

    El warning se inserta entre la cabecera demografica y el resto del cuerpo.
    NO reemplaza nada: solo agrega al inicio del archivo.

    Formato del header:
        ⚠️ AUDITORIA: Pelusa detecto N issues (modelo=X)
        - [issue 1]
        - [issue 2]
        =====================================================
        [resto de la ficha original sin modificar]

    El separator (53 `=`) se inserta para que el bloque de warning separe
    visualmente del cuerpo de la ficha (que ya tiene su propio separator
    antes de `** Doctora:`).
    """
    try:
        contenido = ficha_path.read_text(encoding="utf-8")
    except Exception as e:
        log(f"  [pelusa] ERROR leyendo ficha para prepend warning: {e}")
        return
    separador = "=" * 53
    header = (
        f"⚠️ AUDITORIA: Pelusa detecto {len(issues)} issue(s) (modelo={modelo})\n"
        + "\n".join(f"- {iss}" for iss in issues)
        + f"\n{separador}\n"
    )
    ficha_path.write_text(header + contenido, encoding="utf-8")
    log(f"  [pelusa] header de warning prependido a {ficha_path.name}")


def _auditar_con_pelusa(ficha_path: Path, log) -> tuple[bool, list[str]]:
    """Invoca al agente Pelusa (opencode-go/qwen3.7-plus) para auditar una ficha.

    Args:
        ficha_path: ruta al .txt generado por Mortadelo.
        log: callable de log.

    Returns:
        (ok, issues) donde:
            - ok = True si Pelusa responde "OK" o hay error de parser
              (fail-open: si Pelusa falla, NO bloqueamos la ficha).
            - issues = lista de strings (vacia si OK).

    Convencion del system prompt de Pelusa:
        - Respuesta "OK" → todo bien, no se hace nada.
        - Respuesta "ISSUES:" + lista con bullets → se prepende warning header.
        - Cualquier otra respuesta → fail-open (no se prepende nada, se loguea).

    Modelo: opencode-go/qwen3.7-plus (cuota 4,300/5h, familia distinta a M2.7).
    Prompt: 0 (Pelusa tiene su system prompt completo en .opencode/agent/pelusa.md).
    Adjunto: la ficha a auditar (--file).
    """
    import subprocess

    if not ficha_path.exists():
        log(f"  [pelusa] ERROR: ficha no existe: {ficha_path}")
        return True, []

    log(f"  [pelusa] auditando {ficha_path.name} con {PELUSA_MODEL}...")

    # Resolver binario de opencode (mismo helper que usa Mortadelo).
    opencode_exe = _resolver_opencode_exe()

    # Prompt minimo: Pelusa tiene el system prompt completo en su agent file.
    # Solo le decimos "audita el archivo adjunto y reporta".
    prompt = (
        "Audita la ficha clinica adjunta. "
        "Aplica el checklist de tu system prompt. "
        "Responde UNICAMENTE con 'OK' o 'ISSUES:' + lista con bullets, "
        "sin prosa adicional, sin explicaciones."
    )

    try:
        # Mismo patron que usa Mortadelo. Auto + print-logs para que
        # opencode se ejecute sin pedir confirmacion interactiva.
        proc = subprocess.run(
            [
                opencode_exe, "run",
                "--agent", PELUSA_AGENT,
                "--model", PELUSA_MODEL,
                "--format", "json",
                "--auto",
                "--print-logs",
                "--file", str(ficha_path),
            ],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        log(f"  [pelusa] WARN: timeout 90s auditando {ficha_path.name}, skip (fail-open)")
        return True, []
    except Exception as e:
        log(f"  [pelusa] WARN: error invocando opencode: {e}, skip (fail-open)")
        return True, []

    if proc.returncode != 0:
        log(f"  [pelusa] WARN: opencode retorno {proc.returncode}, skip (fail-open)")
        # Sanitizar stderr para el log (puede tener CJK o emojis)
        stderr_safe = (proc.stderr or "")[:200].encode("ascii", "replace").decode("ascii")
        log(f"  [pelusa] stderr: {stderr_safe}")
        return True, []

    # Parsear respuesta de Pelusa desde JSON events de opencode.
    raw = proc.stdout or ""
    texto = _parsear_eventos_json(raw) or raw.strip()

    # Quitar code blocks de markdown si los hay
    if texto.startswith("```"):
        lines = texto.split("\n")
        lines = [l for l in lines if l.strip() != "```"]
        texto = "\n".join(lines).strip()

    # Sanitizar: si quedaron emojis, los reemplazamos por ASCII para que
    # el log en cp1252 (Windows) no falle.
    safe = texto[:100].replace("\n", " ").replace("\u2705", "[OK]").replace("\u274c", "[FAIL]")
    log(f"  [pelusa] respuesta: {safe}...")

    # Caso 1: "OK"
    if texto.strip() == "OK" or texto.strip().startswith("OK\n") or texto.strip().startswith("OK "):
        log(f"  [pelusa] [OK] OK - sin issues")
        return True, []

    # Caso 2: "ISSUES:" + lista
    if "ISSUES:" in texto or texto.strip().startswith("-"):
        issues: list[str] = []
        for line in texto.splitlines():
            line = line.strip()
            if line.startswith("- "):
                issues.append(line[2:].strip())
        if not issues:
            log(f"  [pelusa] WARN: respuesta contiene 'ISSUES:' pero sin bullets, fail-open")
            return True, []
        log(f"  [pelusa] [FAIL] {len(issues)} issue(s) detectado(s)")
        for i, iss in enumerate(issues, 1):
            log(f"  [pelusa]   {i}. {iss}")
        return False, issues

    # Caso 3: respuesta inesperada → fail-open
    log(f"  [pelusa] WARN: respuesta no sigue formato OK/ISSUES:, fail-open")
    return True, []


def guardar_ficha(contenido: str, nombre_salida: str, output_dir: Optional[Path] = None) -> Optional[Path]:
    """Guarda la ficha en output_dir (o fichas_clinicas/ por default). NO sobrescribe.
    Devuelve la ruta si guardo, None si ya existia.
    """
    out_dir = output_dir if output_dir is not None else (ROOT / "fichas_clinicas")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / nombre_salida
    if out_path.exists():
        return None
    out_path.write_text(contenido, encoding="utf-8")
    return out_path


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [generar_ficha_llm] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Validador de citas (post-LLM)
# ---------------------------------------------------------------------------

# Manuales validos del bundle (lista cerrada). El LLM debe citar SOLO estos.
# Si cita uno que no esta aca, es alucinacion.
MANUALES_VALIDOS: set[str] = {
    "ecicep-marco.md",
    "minsal-plan-consensuado.md",
    "minsal-activos-comunitarios.md",
    "minsal-mais.md",
    "minsal-determinantes-sociales.md",
    "minsal-sife.md",
    "ley-20584.md",
    "red-flags-aps.md",
    "minsal-hta-2010.md",
    "minsal-dm2-2017.md",
    "minsal-epoc-2013.md",
    "minsal-pscv-2017.md",
    "minsal-ira-era-aps.md",
    "minsal-depresion-2013.md",
    "minsal-hta-infancia-2023.md",
    "minsal-ihan-2025.md",
    "minsal-trastorno-ansioso-2018.md",
    "gold-epoc-2026.md",
    "esc-esh-hta-2018.md",
    "pcic_base.txt",
    "data/pcic_base.txt",
}


def validar_citas(texto: str) -> list[str]:
    """Encuentra todas las referencias a manuales en el texto y verifica
    que el manual este en MANUALES_VALIDOS.

    Tambien detecta el patron problematico "(sin acceso a contenido especifico
    en esta sesion)" que es confession de alucinacion.

    NO bloquea la ficha — solo emite warnings. Yadira/Miguel pueden revisar.
    """
    warnings: list[str] = []
    texto_lower = texto.lower()

    # 1. Detectar confession de falta de acceso
    patron_confesion = re.compile(
        r"\(sin acceso a contenido especifico[^)]*\)|"
        r"\(sin contenido especifico[^)]*\)|"
        r"\(no tengo acceso al manual[^)]*\)",
        re.IGNORECASE,
    )
    for match in patron_confesion.finditer(texto):
        warnings.append(
            f"el LLM admite falta de acceso al manual en una cita: "
            f"'{match.group(0)[:80]}...'"
        )

    # 2. Encontrar todos los nombres de manuales citados
    patron_manual = re.compile(r"\b([a-z0-9\-]+\.(?:md|txt))\b", re.IGNORECASE)
    citados: set[str] = set()
    for m in patron_manual.finditer(texto):
        citados.add(m.group(1).lower())

    # 3. Verificar contra la lista cerrada
    validos_lower = {m.lower() for m in MANUALES_VALIDOS}
    for manual in citados:
        if manual not in validos_lower:
            # Buscar match parcial (a veces el LLM escribe "minsal-hta" sin año)
            if not any(manual.startswith(v.split(".md")[0].rstrip("-0123456789")) for v in validos_lower):
                warnings.append(
                    f"cita a manual desconocido: '{manual}' "
                    f"(no esta en MANUALES_VALIDOS — posible alucinacion)"
                )

    return warnings


# ---------------------------------------------------------------------------
# Flujo principal
# ---------------------------------------------------------------------------

def procesar_nota(
    nota_path: Path,
    model: Optional[str] = None,
    dry_run: bool = False,
    skip_vision: bool = True,
    save_prompt_dir: Optional[Path] = None,
    adjuntos_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    no_save_prompt: bool = False,
    skip_audit: bool = False,
    timeout: int = 600,
    informe_path: Optional[Path] = None,
) -> Optional[Path]:
    """Procesa 1 nota: lee -> plantilla -> manual + PCIC -> 1 llamada LLM -> guarda.

    Flujo (v2 — 1 sola llamada):
        1. Lee la nota.
        2. Carga plantilla, reglas del bundle, PCIC base.
        3. Construye el prompt unico.
        4. Invoca `opencode run --agent mortadelo --model <modelo>` (1 sola vez).
        5. El agente (con system prompt completo) hace: relleno + inferencia
           + advertencias + bloque `** Doctora:`.
        6. Guarda la salida en output_dir (o fichas_clinicas/ por default).

    Args:
        nota_path: path al .txt de la nota clinica.
        model: modelo a usar (default: DEFAULT_MODEL = minimax-m3).
        dry_run: si True, NO invoca opencode (solo loggea).
        save_prompt_dir: si se pasa, guarda el prompt construido en este
            directorio con nombre {nota_stem}_prompt.txt. Util para revisar
            sin gastar cuota.
        adjuntos_dir: directorio de fotos adjuntas (default: notas_clinicas/_adjuntos/).
        output_dir: directorio de salida (default: fichas_clinicas/).
        no_save_prompt: si True, ignora save_prompt_dir (para tests con PHI).
        timeout: segundos para la llamada a opencode.
        informe_path: path al informe para resolver tipo_atencion cuando la
            nota no lo trae explicito. Si es None, usa el informe del mes
            en curso (default; NUNCA el anual).

    Args:
        nota_path: path al .txt de la nota clinica.
        model: modelo a usar (default: DEFAULT_MODEL = minimax-m3).
        dry_run: si True, NO invoca opencode (solo loggea).
        save_prompt_dir: si se pasa, guarda el prompt construido en este
            directorio con nombre {nota_stem}_prompt.txt. Util para revisar
            sin gastar cuota.
        adjuntos_dir: directorio de fotos adjuntas (default: notas_clinicas/_adjuntos/).
        output_dir: directorio de salida (default: fichas_clinicas/).
        no_save_prompt: si True, ignora save_prompt_dir (para tests con PHI).
        timeout: segundos para la llamada a opencode.

    Devuelve la ruta de la ficha generada, o None si no se pudo.
    """
    if not nota_path.exists():
        log(f"ERROR: nota no existe: {nota_path}")
        return None

    # Pre-check: si la ficha ya existe, saltamos ANTES del LLM (ahorra cuota).
    # guardar_ficha() tambien valida al final, pero queremos evitar la llamada
    # al LLM entera cuando sabemos que el output ya esta en disco.
    _output_dir = output_dir or (ROOT / "fichas_clinicas")
    _existing = _output_dir / nota_path.name
    if _existing.exists():
        log(f"SKIP (pre-check): ficha ya existe: {nota_path.name}")
        return None

    log(f"leyendo nota: {nota_path.name}")
    nota = leer_nota(nota_path)

    # Si la nota no tiene tipo_atencion explicito, buscar en el informe.
    # Default: el del mes en curso (NO hardcoded, NO el anual).
    # Si el caller paso informe_path, se usa ese (ej. reproceso historico).
    if not nota.tipo_atencion:
        informe_para_lookup = informe_path or informe_mes_actual_path()
        tipo_del_informe = buscar_tipo_en_informe(
            nota.nombre_paciente, nota.fecha_atencion, informe_para_lookup
        )
        if tipo_del_informe:
            nota.tipo_atencion = tipo_del_informe
            log(f"  tipo (desde informe): {tipo_del_informe}")

    if not nota.tipo_atencion:
        log(f"WARN: nota sin tipo_atencion y no se encontro en informe: {nota_path.name}")
        return None

    log(f"  paciente: {nota.nombre_paciente}")
    log(f"  fecha:    {nota.fecha_atencion}")
    log(f"  tipo:     {nota.tipo_atencion}")
    if nota.trigger:
        log(f"  trigger:  {nota.trigger}")

    # Demografia (de la seccion IDENTIFICACION de la nota)
    demografia = extraer_demografia(nota.texto)
    log(f"  demografia: run={demografia['run']!r} edad={demografia['edad']!r} "
        f"sector={demografia['sector']!r}")

    plantilla = cargar_plantilla_para_tipo(nota.tipo_atencion)
    if not plantilla:
        log(f"WARN: tipo_atencion sin plantilla: {nota.tipo_atencion}")
        return None

    # Bundle + manual
    canonica = resolver_plantilla(nota.tipo_atencion)
    bundle = BUNDLE_POR_PLANTILLA.get(canonica or "", "")
    manual = cargar_manual_principal(bundle) if bundle else ""
    log(f"  plantilla: {canonica} / bundle: {bundle or '(sin bundle)'} / manual: "
        f"{'cargado' if manual else 'no disponible'}")

    # Recetas: routing directo, sin LLM. Regla de Yadira (sesion 2026-08-26):
    # "a ella solo se le debe repetir la receta que esta en su nota medica,
    # nada mas y nada menos". El LLM no aporta valor en este caso, solo
    # agrega riesgo de alucinacion. Mortadelo genera el txt directamente
    # desde el bloque PLAN RECETAS de la nota.
    if (canonica or "").upper() == "RECETA":
        log("  RECETAS: routing directo, sin LLM (decision de Mortadelo)")
        output = _generar_ficha_recetas_directo(nota, demografia)
        out_path = guardar_ficha(output, nota_path.name, output_dir=output_dir)
        if out_path is None:
            log(f"  SKIP: ficha ya existe: {nota_path.name}")
            return None
        log(f"  OK (directo, sin LLM): ficha guardada en {out_path}")
        return out_path

    # PCIC base: solo si el bundle es ECICEP (es donde aplica el PCIC).
    pcic_base = cargar_pcic_base() if bundle == "ecicep" else ""
    if pcic_base:
        log(f"  PCIC base: cargado ({len(pcic_base)} chars)")
    else:
        log(f"  PCIC base: no aplica (bundle={bundle or 'n/a'})")

    # Analizar adjuntos de imagen (LLM vision) si los hay.
    # Vision NO EXISTE en mortadelo. Yadira jamas le pasara imagenes, y Mortadelo
    # no usa modelos de vision. Este codigo queda solo como documentacion:
    # Mortadelo SOLO procesa texto (plantilla, nota Yadira, manual, pcic, y
    # opcionalmente un .md de examenes si la nota lo dispara con
    # `** mortadelo examenes adjuntos`). NO logueamos nada en vision — no es
    # noticia que no exista.
    adjuntos_dir = ROOT / "notas_clinicas" / "_adjuntos"
    if skip_vision and not dry_run:
        # Vision no existe. Ignorar el folder de adjuntos por completo, en silencio.
        examenes_adjuntos = []
    elif dry_run:
        # Dry-run: detectar para visibilidad, sin transcribir.
        candidatos = _detectar_adjuntos_sin_transcribir(
            nombre_paciente=nota.nombre_paciente,
            fecha_atencion=nota.fecha_atencion,
            adjuntos_dir=adjuntos_dir,
        )
        if candidatos:
            log(f"  adjuntos detectados (dry-run, sin transcribir): "
                f"{[c.name for c in candidatos]}")
        else:
            log(f"  sin adjuntos de imagen")
        examenes_adjuntos = []
    else:
        examenes_adjuntos = analizar_adjuntos_imagen(
            nombre_paciente=nota.nombre_paciente,
            fecha_atencion=nota.fecha_atencion,
            adjuntos_dir=adjuntos_dir,
        )
        if examenes_adjuntos:
            log(f"  examenes adjuntos transcritos: {len(examenes_adjuntos)}")
        else:
            log(f"  sin examenes adjuntos de imagen")

    # Trigger de EXAMENES ADJUNTOS: si Yadira dejo `** mortadelo examenes adjuntos`
    # (o variantes como `** mortadelo adjunto examenes`, `** mortadelo examenes
    # externos`) en la nota, buscar <nombre>.md en _adjuntos/ y adjuntarlo
    # como TEXTO (markdown) al prompt. Esto es INDEPENDIENTE de vision (que no
    # existe en mortadelo) — son archivos .md, no imagenes.
    examen_md_path: Optional[Path] = None
    if nota.trigger and _es_trigger_examenes(nota.trigger):
        # Intentar matchear el archivo por nombre del paciente.
        # Convivencia de naming: notas usan guiones bajos (ej. "Mirta_Del_Carmen_Davila_Luengo"),
        # pero los .md en _adjuntos/ pueden tener guiones bajos O espacios
        # (ej. "Rodrigo Salvador Zenteno Plaza.md"). Tambien `nombre_paciente`
        # puede traer espacios o guiones. Probar las 4 variantes.
        np = nota.nombre_paciente
        np_us = np.replace(" ", "_")
        np_sp = np.replace("_", " ")
        candidatos_md = [
            adjuntos_dir / f"{np}.md",
            adjuntos_dir / f"{np_us}.md",
            adjuntos_dir / f"{np_sp}.md",
        ]
        for candidato in candidatos_md:
            if candidato.exists():
                examen_md_path = candidato
                break
        if examen_md_path:
            log(
                f"  examenes adjuntos (trigger): {examen_md_path.name} "
                f"({examen_md_path.stat().st_size} chars)"
            )
        else:
            log(
                f"  WARN: trigger 'examenes adjuntos' presente pero no se encontro "
                f"<nombre>.md en {adjuntos_dir} (intente: {[c.name for c in candidatos_md]})"
            )

    # Construir el prompt CORTO + guardar las 4 piezas grandes como archivos
    # adjuntos (patron del chat Mavis, evita colgar el modelo con 35K chars inline).
    if save_prompt_dir and not no_save_prompt:
        save_prompt_dir.mkdir(parents=True, exist_ok=True)
        # Para debug/reproducibilidad, guardar el prompt grande original
        prompt_grande = construir_prompt(
            plantilla=plantilla,
            nota_texto=nota.texto,
            manual=manual,
            trigger=nota.trigger,
            demografia=demografia,
            nombre_paciente=nota.nombre_paciente,
            fecha_atencion=nota.fecha_atencion,
            tipo_atencion=nota.tipo_atencion,
            examenes_adjuntos=examenes_adjuntos,
            pcic_base=pcic_base,
        )
        prompt_path = save_prompt_dir / f"{nota_path.stem}_prompt.txt"
        prompt_path.write_text(prompt_grande, encoding="utf-8")
        log(f"  prompt grande guardado en: {prompt_path}")

    # Construir prompt CORTO (metadata + instrucciones, ~1-2K chars).
    # Las piezas grandes se pasan como `--file` (multimodal adjuntos).
    adjuntos_tmp: list[Path] = []
    try:
        # Guardar las piezas grandes en temp files (5 si hay examen adjunto)
        adjuntos_tmp = _guardar_adjuntos_tmp(
            nota_path=nota_path,
            plantilla=plantilla,
            nota_texto=nota.texto,
            manual=manual,
            pcic_base=pcic_base,
            examen_md_path=examen_md_path,
        )
        # Caso especial: Recetas. El canonica es "RECETA" (singular). Detectar
        # tanto por canonica como por tipo_atencion.
        es_recetas = (canonica or "").upper() == "RECETA" or "receta" in (nota.tipo_atencion or "").lower()

        prompt = _construir_prompt_corto(
            demografia=demografia,
            nombre_paciente=nota.nombre_paciente,
            fecha_atencion=nota.fecha_atencion,
            tipo_atencion=nota.tipo_atencion,
            canonica=canonica,
            bundle=bundle,
            trigger=nota.trigger,
            examen_adjunto=examen_md_path is not None,
            es_recetas=es_recetas,
        )
        log(f"  prompt corto: {len(prompt)} chars, {len(adjuntos_tmp)} adjuntos"
            + (" [RECETAS: solo repetir receta, nada mas]" if es_recetas else ""))
    except Exception as e:
        log(f"  ERROR preparando adjuntos: {e}")
        return None

    if dry_run:
        log("  DRY-RUN: prompt + adjuntos listos, no se invoca opencode")
        return None

    # 1 sola llamada — el agente hace todo con su system prompt.
    modelo = model or DEFAULT_MODEL
    log(f"  [1-llamada] invocando {modelo} (agent=mortadelo, "
        f"{len(adjuntos_tmp)} adjuntos)...")
    try:
        output, modelo_usado = _invocar_con_fallback_archivos(
            tier="diagnostico",
            prompt=prompt,
            agent="mortadelo",
            archivos=adjuntos_tmp,
            timeout=timeout,
        )
    except RuntimeError as e:
        log(f"  ERROR: {e}")
        return None
    finally:
        # Limpiar temp files (no dejar PHI en disco)
        for p in adjuntos_tmp:
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass

    output = limpiar_output(output)
    if not output:
        log("  ERROR: opencode devolvio output vacio")
        return None

    # Retry si el output es degenerado (LLM produjo solo meta-commentary
    # sin cuerpo de ficha). Patron visto en Karina/Damian 2026-08-26.
    # Criterio: < 500 chars de output limpio, o > 50% del output en el
    # bloque Doctora con < 200 chars en el cuerpo. En ese caso, re-invoca
    # el siguiente modelo del tier (fallback ya aplicado 1 vez).
    if _output_degenerado(output):
        log(f"  WARN: output degenerado ({len(output)} chars, "
            f"modelo={modelo_usado}) — reintentando con siguiente modelo")
        try:
            output, modelo_usado = _invocar_con_fallback_archivos(
                tier="diagnostico",
                prompt=prompt + "\n\nIMPORTANTE: Tu respuesta debe contener el CUERPO de la ficha completo (cabecera demografica + plantilla rellenada). No respondas solo con un comentario sobre la ficha. Entrega la ficha lista para pegar en Rayen.",
                agent="mortadelo",
                archivos=adjuntos_tmp,
                timeout=timeout,
            )
            output = limpiar_output(output)
        except RuntimeError:
            pass
        if not output or _output_degenerado(output):
            log(f"  ERROR: output sigue degenerado tras retry, descartando")
            return None

    # Sanitize: cierra los huecos que el LLM sigue abriendo pese al prompt
    # (CJK chars, palabras en inglés, secciones prohibidas, A VALIDAR inline).
    output = _sanitize_output(output, log)

    # Post-procesamiento: si el bloque Doctora quedo duplicado, quedarnos
    # con el ultimo bloque completo.
    separador = "====================================================="
    if output.count(separador) >= 2:
        partes = output.split(separador)
        output = separador + partes[-1].lstrip()
        log(f"  WARN: bloque Doctora duplicado por el LLM, me quedo con la ultima version")

    # Validar citas: detectar alucinaciones de manuales antes de guardar.
    # No bloquea — solo loguea warnings para revision.
    warnings_citas = validar_citas(output)
    for w in warnings_citas:
        log(f"  [validar_citas] {w}")
    if warnings_citas:
        log(f"  [validar_citas] {len(warnings_citas)} warning(s) — revisar antes de cerrar la ficha")

    out_path = guardar_ficha(output, nota_path.name, output_dir=output_dir)
    if out_path is None:
        log(f"  SKIP: ficha ya existe en fichas_clinicas/: {nota_path.name}")
        return None
    log(f"  OK: ficha guardada en {out_path} (modelo={modelo_usado})")

    # Auditoria con Pelusa (solo en la rama LLM, no en Recetas que es
    # routing directo y deterministico). Pelusa es fail-open: si falla,
    # la ficha queda como esta. Si detecta issues, prepende un header
    # de warning a la ficha para que Yadira lo vea al abrir.
    if not skip_audit:
        ok_pelusa, issues_pelusa = _auditar_con_pelusa(out_path, log)
        if not ok_pelusa and issues_pelusa:
            _prepend_warning_header(out_path, issues_pelusa, PELUSA_MODEL, log)

    return out_path


def main() -> int:
    # Configurar stdout/stderr en UTF-8 con fallback 'replace' para que el
    # log no se caiga cuando opencode devuelve CJK u otros caracteres
    # que cp1252 (default de Windows) no soporta. Sesion 2026-08-27:
    # el batch se interrumpio con 'charmap' codec errors por esto.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # Python < 3.7 no tiene reconfigure, no es bloqueante

    parser = argparse.ArgumentParser(
        description=(
            "Genera fichas clinicas con LLM externo via opencode (v2: 1 sola llamada, "
            "agente mortadelo con system prompt completo en .opencode/agent/mortadelo.md)."
        )
    )
    parser.add_argument(
        "--nota",
        type=str,
        help="Path a una nota clinica (.txt). Si se omite, se procesan todas las del directorio.",
    )
    parser.add_argument(
        "--informe",
        type=str,
        help=(
            "Path al informe de fichas abiertas (procesa los pacientes listados). "
            f"Default: informe del mes en curso ({informe_mes_actual_path().name}). "
            "Para el informe ANUAL pasar path explicito (operacion distinta, no es el flujo normal)."
        ),
    )
    parser.add_argument(
        "--dir",
        type=str,
        default=str(ROOT / "notas_clinicas"),
        help="Directorio de notas clinicas (default: notas_clinicas/).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"Modelo opencode (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--model-vision",
        type=str,
        default=DEFAULT_TIERS["vision"],
        help=f"Modelo tier vision (default: {DEFAULT_TIERS['vision']}).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Timeout en segundos para la llamada a opencode (default: 300).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo construye el prompt, no invoca opencode.",
    )
    parser.add_argument(
        "--save-prompt",
        type=str,
        default=None,
        help=(
            "Directorio donde guardar el prompt construido (uno por nota, "
            "nombre {nota_stem}_prompt.txt). Util para revisar sin gastar "
            "cuota. Se guarda ANTES de invocar opencode."
        ),
    )
    parser.add_argument(
        "--adjuntos-dir",
        type=str,
        default=None,
        help=(
            "Directorio donde buscar las fotos adjuntas. Default: "
            "notas_clinicas/_adjuntos/. Util para tests externos al "
            "proyecto (ej. C:/Temp/test_rubicita_real/inbox)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help=(
            "Directorio donde guardar la ficha rellenada. Default: "
            "fichas_clinicas/. Util para tests externos (la ficha NO "
            "se guarda en el repo del proyecto)."
        ),
    )
    parser.add_argument(
        "--no-save-prompt",
        action="store_true",
        help=(
            "NO guardar el prompt construido en data/prompts/. Usar en "
            "tests con PHI real para evitar que el prompt con la "
            "transcripcion de vision quede en el repo del proyecto."
        ),
    )
    parser.add_argument(
        "--no-skip-vision",
        action="store_true",
        help=(
            "DESACTIVAR el skip de vision (default: skip=True, vision DEFERRED "
            "per REGLA 9 hasta que haya examenes externos reales). Usar solo "
            "cuando Miguel confirme que el caso tiene examenes que transcribir."
        ),
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help=(
            "DESACTIVAR la auditoria de Pelusa (default: audit=True). Pelusa "
            "lee la ficha final y, si detecta issues, prepende un header de "
            "warning para que Yadira lo vea al abrir. Skip solo en tests."
        ),
    )

    args = parser.parse_args()

    save_prompt_dir: Optional[Path] = Path(args.save_prompt) if args.save_prompt else None
    output_dir: Optional[Path] = Path(args.output_dir) if args.output_dir else None

    # Resolver el informe una sola vez:
    #   - Si el usuario paso --informe, se respeta (incluso si es el anual).
    #   - Si no, default al informe del mes en curso.
    # Esto se usa para (a) construir la lista de pacientes en modo batch
    # y (b) como fallback en procesar_nota() cuando la nota no trae
    # tipo_atencion explicito.
    informe_path_resuelto: Optional[Path] = (
        Path(args.informe) if args.informe else informe_mes_actual_path()
    )

    notas_a_procesar: list[Path] = []

    if args.nota:
        notas_a_procesar.append(Path(args.nota))
    elif informe_path_resuelto is not None:
        informe_path = informe_path_resuelto
        if not informe_path.exists():
            log(f"ERROR: informe no existe: {informe_path}")
            log(f"  Para el flujo mensual, regenera con: python -m src.analysis.informe_fichas_abiertas")
            return 1
        texto = informe_path.read_text(encoding="utf-8")
        # Formato del informe: TABLA con lineas:
        #   21-08-2026    Alejandro Enrique Carrasco Arias  Control integral ecicep-g2        Consulta
        #   21-08-2026    (Atencion Preferente) Karina Bec  Control integral ecicep-g3        Consulta
        # Luego viene un bloque de "Distribucion por tipo de atencion" con
        # lineas tipo "  Morbilidad telefonica        10  ( 58.8%)" — NO son
        # fichas, hay que skipearlas.
        for line in texto.splitlines():
            s = line.strip()
            if not s or s.startswith("===") or s.startswith("INFORME") or s.startswith("Total"):
                continue
            if s.startswith("Fecha") or s.startswith("Distribucion") or s.startswith("---"):
                continue
            # REGLA dura: la primera columna DEBE ser una fecha dd-mm-yyyy.
            # Si no lo es, es una linea de la seccion "Distribucion por tipo de
            # atencion" (que arranca con "  Morbilidad telef..."), y la
            # skipeamos. Esto es mas robusto que matchear prefijos porque
            # las lineas de distribucion vienen indentadas.
            if not re.match(r"^\d{2}-\d{2}-\d{4}\s", s):
                continue
            parts = re.split(r"\s{2,}", s)
            if len(parts) < 3:
                continue
            fecha = parts[0].strip()
            # IMPORTANTE: NO strippear parentesis del nombre. El script de
            # extraccion (crear_notas_clinicas.py) usa _safe_filename que
            # REEMPLAZA los parentesis y sus espacios con "_" (no los
            # elimina). Ej: "(Almendra) Almendra Estefania Ar" ->
            # "Almendra_Almendra_Estefania_Ar" (NO "Almendra_Estefania_Ar").
            # Si el parser strippea los "(...)", el nombre no matchea.
            nombre_raw = parts[1].strip()
            # Misma normalizacion que _safe_filename en crear_notas_clinicas.py:
            # quitar chars no [\w\s-] y reemplazar whitespace por "_".
            nombre_norm = re.sub(r"[^\w\s\-]+", "", nombre_raw, flags=re.UNICODE)
            nombre_norm = re.sub(r"\s+", "_", nombre_norm.strip())
            # tipo = parts[2].strip()  # no lo necesitamos aqui, sale del informe
            if fecha and nombre_norm:
                fname = f"{nombre_norm}_{fecha}.txt"
                fpath = ROOT / "notas_clinicas" / fname
                if fpath.exists():
                    notas_a_procesar.append(fpath)
                else:
                    log(f"  informe apunta a nota inexistente: {fname}")
    else:
        # Batch: todas las .txt en el directorio
        dir_path = Path(args.dir)
        if not dir_path.exists():
            log(f"ERROR: directorio no existe: {dir_path}")
            return 1
        notas_a_procesar = sorted(dir_path.glob("*.txt"))

    if not notas_a_procesar:
        log("no hay notas para procesar")
        return 1

    log(f"procesando {len(notas_a_procesar)} nota(s)")
    if save_prompt_dir:
        log(f"  prompts se guardaran en: {save_prompt_dir}")

    generados = 0
    saltados = 0
    errores = 0
    for nota_path in notas_a_procesar:
        try:
            out = procesar_nota(
                nota_path,
                model=args.model,
                dry_run=args.dry_run,
                skip_vision=not args.no_skip_vision,
                skip_audit=args.skip_audit,
                save_prompt_dir=save_prompt_dir,
                output_dir=output_dir if output_dir is not None else None,
                timeout=args.timeout,
                informe_path=informe_path_resuelto,
            )
            if out is not None:
                generados += 1
            else:
                saltados += 1
        except Exception as e:
            log(f"ERROR inesperado en {nota_path.name}: {e}")
            errores += 1

    log(f"---")
    log(f"RESUMEN: generados={generados} saltados={saltados} errores={errores}")
    return 0 if errores == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
