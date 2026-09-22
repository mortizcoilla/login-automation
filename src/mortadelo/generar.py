"""Orquestacion del paso 7: dos llamadas LLM por paciente + ensamblado.

Flujo por paciente (del informe de fichas abiertas):
  1. Cargar insumos: anamnesis base (anam_*.md o seccion Yadira de la
     nota), info_paciente, examenes (si existe).
  2. Detectar pedidos del trigger ** mortadelo.
  3. LLAMADA 1: prompt de ficha -> ensamblar con garantias -> validar
     -> escribir ficha_<pac>_<fecha>.md en data/fichas_generadas/.
  4. LLAMADA 2: prompt de informe -> estampar encabezado (fecha, MODELO
     USADO por CODIGO, ficha) -> validar -> escribir
     informe_trazabilidad_<pac>_<fecha>.md en data/informes_trazabilidad/.

La funcion `llm_run` es inyectable: la suite de tests NUNCA llama a la
API real (REQ-055).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.core.nombres import safe_filename
from src.core.rutas import (
    ANAMNESIS_DIR,
    EXAMENES_DIR,
    INFO_PACIENTE_DIR,
    NOTAS_DIR,
    ROOT,
)
from src.informes.enriquecer import KEYWORDS_REQUERIMIENTOS, TRIGGER_RE
from src.informes.parser import parsear_pacientes_objetivo
from src.mortadelo.ensamblador import ensamblar_ficha
from src.mortadelo.llm_cli import LLMError, llm_run
from src.mortadelo.prompt import Pedidos, construir_prompt_ficha, construir_prompt_informe
from src.mortadelo.validacion import validar_ficha, validar_informe

FICHAS_DIR = ROOT / "data" / "fichas_generadas"
INFORMES_DIR = ROOT / "data" / "informes_trazabilidad"

_ESPECIALIDAD_RE = re.compile(r"interconsulta(?:\s+a|\s+de)?\s+([a-záéíóúñ]+)", re.IGNORECASE)

Logger = logging.Logger
LLMRun = Callable[[str], tuple[str, str]]


@dataclass
class ResultadoPaciente:
    nombre: str
    fecha: str
    ok: bool = False
    ficha_path: str = ""
    informe_path: str = ""
    modelo_ficha: str = ""
    modelo_informe: str = ""
    advertencias: list[str] = field(default_factory=list)
    error: str = ""


def _leer(path: Path) -> str | None:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else None


def cargar_base_anamnesis(nombre: str, fecha: str) -> str | None:
    """anam_<pac>_<fecha>.md; si no existe, seccion Yadira de la nota."""
    safe = safe_filename(nombre)
    respaldo = _leer(ANAMNESIS_DIR / f"anam_{safe}_{fecha}.md")
    if respaldo:
        return respaldo.strip()
    nota = _leer(NOTAS_DIR / f"{safe}_{fecha}.md")
    if nota and "## Nota clinica de Yadira" in nota and "## Diagnosticos" in nota:
        ini = nota.index("## Nota clinica de Yadira") + len("## Nota clinica de Yadira")
        fin = nota.index("## Diagnosticos")
        cuerpo = "\n".join(nota[ini:fin].strip().splitlines()[1:]).strip()
        return cuerpo or None
    return None


def detectar_pedidos(base_anamnesis: str) -> Pedidos:
    """Extrae el trigger, las keywords y los pedidos libres (REQ-077)."""
    pedidos = Pedidos()
    texto_trigger = _texto_trigger(base_anamnesis)
    if not texto_trigger:
        return pedidos
    pedidos.trigger_texto = texto_trigger
    if KEYWORDS_REQUERIMIENTOS["examenes"].search(texto_trigger):
        pedidos.examenes = True
    if KEYWORDS_REQUERIMIENTOS["interconsulta"].search(texto_trigger):
        m = _ESPECIALIDAD_RE.search(texto_trigger)
        pedidos.interconsulta_especialidad = m.group(1).lower() if m else "especialidad"
    if KEYWORDS_REQUERIMIENTOS["indicaciones"].search(texto_trigger):
        pedidos.indicaciones = True
    pedidos.pedidos_libres = _pedidos_libres(texto_trigger)
    return pedidos


def _pedidos_libres(texto_trigger: str) -> list[str]:
    """Lineas del bloque ** mortadelo que no calzan en las categorias
    estructuradas (examenes/interconsulta/indicaciones): p. ej. "Dame
    sugerencias para la psicologa", "como cerrar el GES". Cada una se
    convierte en seccion explicita del prompt (REQ-077).
    """
    libres: list[str] = []
    for bloque in texto_trigger.split("\n---\n"):
        for linea in bloque.splitlines():
            linea = linea.strip()
            if not linea or "mortadelo" in linea.lower():
                continue
            if any(regex.search(linea) for regex in KEYWORDS_REQUERIMIENTOS.values()):
                continue  # pedido estructurado: tiene su propio manejo
            linea = re.sub(r"^[-*•]\s*", "", linea).strip()
            if linea and linea not in libres:
                libres.append(linea)
    return libres


def _texto_trigger(anamnesis: str) -> str:
    matches = list(TRIGGER_RE.finditer(anamnesis))
    if not matches:
        return ""
    trozos: list[str] = []
    for i, m in enumerate(matches):
        fin = matches[i + 1].start() if i + 1 < len(matches) else len(anamnesis)
        trozo = anamnesis[m.start() : fin]
        if trozo.rstrip().endswith("**"):
            trozo = trozo.rstrip()[:-2]
        trozos.append(trozo.strip())
    return "\n---\n".join(trozos)


def generar_paciente(
    nombre: str,
    fecha: str,
    fichas_dir: Path = FICHAS_DIR,
    informes_dir: Path = INFORMES_DIR,
    llm: LLMRun | None = None,
    logger: Logger | None = None,
) -> ResultadoPaciente:
    """Genera ficha + informe de trazabilidad de UN paciente."""
    logger = logger or logging.getLogger("mortadelo")
    resultado = ResultadoPaciente(nombre=nombre, fecha=fecha)
    llm = llm or llm_run

    base = cargar_base_anamnesis(nombre, fecha)
    if not base:
        resultado.error = f"Sin anamnesis para {nombre} ({fecha}): falta anam_* o la nota clinica"
        return resultado
    info = _leer(INFO_PACIENTE_DIR / f"info_{safe_filename(nombre)}_{fecha}.md") or ""
    examenes = _leer(EXAMENES_DIR / f"exam_{safe_filename(nombre)}_{fecha}.md")
    pedidos = detectar_pedidos(base)

    # LLAMADA 1: ficha -> ensamblar -> validar
    try:
        salida_llm, modelo = llm(
            construir_prompt_ficha(nombre, fecha, base, info, examenes, pedidos)
        )
    except LLMError as e:
        resultado.error = f"LLM ficha: {e}"
        return resultado
    resultado.modelo_ficha = modelo

    ensamblada = ensamblar_ficha(
        base,
        salida_llm,
        pedir_indicaciones=pedidos.indicaciones,
        especialidad_interconsulta=pedidos.interconsulta_especialidad,
    )
    for adv in validar_ficha(ensamblada.texto, base, info):
        resultado.advertencias.append(f"{adv.codigo}: {adv.mensaje}")
        logger.warning(f"[mortadelo] {nombre}: {adv.codigo} {adv.mensaje}")

    fichas_dir.mkdir(parents=True, exist_ok=True)
    ficha_path = fichas_dir / f"ficha_{safe_filename(nombre)}_{fecha}.md"
    ficha_path.write_text(ensamblada.texto, encoding="utf-8")
    resultado.ficha_path = str(ficha_path)

    # LLAMADA 2: informe -> estampar encabezado (modelo por CODIGO) -> validar
    try:
        informe_md, modelo_inf = llm(
            construir_prompt_informe(nombre, fecha, ensamblada.texto, info, examenes, pedidos)
        )
    except LLMError as e:
        resultado.ok = True  # la ficha se genero; el informe fallo
        resultado.error = f"LLM informe: {e}"
        return resultado
    resultado.modelo_informe = modelo_inf

    ts = datetime.now().strftime("%d-%m-%Y %H:%M")
    encabezado = (
        f"# Informe de trazabilidad — {nombre} ({fecha})\n\n"
        f"Generado: {ts} · Modelo ficha: {resultado.modelo_ficha} · "
        f"Modelo informe: {resultado.modelo_informe} · "
        f"Ficha: {ficha_path.name}\n\n"
    )
    for adv in validar_informe(informe_md):
        resultado.advertencias.append(f"{adv.codigo}: {adv.mensaje}")
        logger.warning(f"[mortadelo] {nombre}: {adv.codigo} {adv.mensaje}")

    informes_dir.mkdir(parents=True, exist_ok=True)
    informe_path = informes_dir / f"informe_trazabilidad_{safe_filename(nombre)}_{fecha}.md"
    informe_path.write_text(encabezado + informe_md.strip() + "\n", encoding="utf-8")
    resultado.informe_path = str(informe_path)
    resultado.ok = True
    return resultado


def generar_fichas(
    informe_path: Path,
    fichas_dir: Path = FICHAS_DIR,
    informes_dir: Path = INFORMES_DIR,
    llm: LLMRun | None = None,
    logger: Logger | None = None,
) -> list[ResultadoPaciente]:
    """Paso 7 para todos los pacientes del informe de fichas abiertas."""
    logger = logger or logging.getLogger("mortadelo")
    pacientes = parsear_pacientes_objetivo(informe_path)
    logger.info(f"[mortadelo] {len(pacientes)} pacientes del informe {informe_path.name}")
    resultados: list[ResultadoPaciente] = []
    for pac in pacientes:
        logger.info(f"[mortadelo] Generando: {pac.nombre} ({pac.fecha})")
        r = generar_paciente(
            pac.nombre,
            pac.fecha,
            fichas_dir=fichas_dir,
            informes_dir=informes_dir,
            llm=llm,
            logger=logger,
        )
        logger.info(
            f"[mortadelo] {pac.nombre}: ok={r.ok} "
            f"ficha={'si' if r.ficha_path else 'no'} "
            f"informe={'si' if r.informe_path else 'no'} "
            f"advertencias={len(r.advertencias)}" + (f" error={r.error}" if r.error else "")
        )
        resultados.append(r)
    ok = sum(1 for r in resultados if r.ok)
    logger.info(f"[mortadelo] === Resumen: {ok}/{len(resultados)} pacientes completos ===")
    return resultados
