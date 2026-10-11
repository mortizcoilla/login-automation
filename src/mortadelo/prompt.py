"""Prompts del paso 7 (validados en 4 corridas reales de prueba).

PROMPT_VERSION permite rastrear cambios de redaccion en el tiempo
(REQ-055). El rol medico NO va aqui: vive en el system prompt del
agente (.opencode/agent/mortadelo.md, rol v2 aprobado).
"""

from __future__ import annotations

from dataclasses import dataclass, field

PROMPT_VERSION = 5


@dataclass
class Pedidos:
    """Lo que Yadira pidio en el bloque ** mortadelo (mas el trigger crudo).

    pedidos_libres: los pedidos que NO calzan en las categorias
    estructuradas (examenes/interconsulta/indicaciones) — p. ej. "Dame
    sugerencias para la psicologa" o "como cerrar el GES". Cada uno se
    convierte en una seccion explicita del prompt (REQ-077).
    """

    trigger_texto: str = ""
    examenes: bool = False
    interconsulta_especialidad: str | None = None
    indicaciones: bool = False
    pcic: bool = False
    pedidos_libres: list[str] = field(default_factory=list)


_REGLAS_FICHA = """Ejecucion:
1. Identifica los campos vacios del documento principal (campo sin valor tras los dos puntos; "niega" y "(-)" son datos validos, no vacios).
2. Completalos primero con informacion de los insumos.
3. Lo que no este en los insumos y sea interpretable clinicamente, completalo con tu criterio experto, fundamentado.
4. Los datos factuales del paciente (telefono, domicilio, acompanantes, fechas administrativas) que no existan en ninguna fuente quedan (-).
5. INDICACIONES (OBLIGATORIAS): todo documento DEBE terminar con indicaciones para el paciente.
   - Si el documento trae una SECCION NUMERADA de INDICACIONES con items vacios (p. ej. "5. INDICACIONES" seguido de "5.1.", "5.2." vacios): manteniendo el numero y titulo de la seccion EXACTAMENTE igual, reemplaza los items vacios por vinetas en el formato exacto "- indicacion" (una por linea, SIN el signo >), con las indicaciones clinicas para el paciente: lo que la doctora pidio en el bloque ** mortadelo CONVERTIDO en indicacion clinica concreta (p. ej. si pidio interconsulta a cirugia: "Derivacion a Cirugia (interconsulta generada). Acudir con carnet y esta ficha.") MAS las indicaciones apropiadas segun diagnosticos, tratamiento e insumos (cuidados, ejercicios, higiene, signos de alarma, etc.).
   - Si el documento trae el campo "indicac"/"indicaciones" CON contenido, dejalo exactamente como esta.
   - Si trae el campo VACIO ("indicac:", "indicaciones:"), completalo EN ESA MISMA linea con las indicaciones para el paciente segun diagnosticos, tratamiento e insumos.
   - Si el documento NO trae ni seccion ni campo, agregalo AL FINAL como una seccion "INDICACIONES:" con vinetas "- ". Esta es la UNICA excepcion permitida a la prohibicion de agregar secciones.

Correccion ortografica: corrige faltas de ortografia del texto de la doctora (letras faltantes o sobrantes, tildes, terminos medicos mal escritos) SIN cambiar el contenido, el estilo, las abreviaturas ni el formato. NO corrijas tiempos verbales, NO mejores la redaccion ni la puntuacion: solo ortografia objetiva.

Prohibido: agregar secciones, bloques o titulos nuevos (la UNICA excepcion es la seccion INDICACIONES de la regla 5); eliminar secciones existentes; modificar, corregir o reformular los campos ya escritos por la doctora (mas alla de la ortografia objetiva); reformatear (no conviertas texto en vinetas ni vinetas en texto).

IMPORTANTE - bloque ** mortadelo: es una instruccion para el SISTEMA, no contenido clinico. ELIMINALO de tu salida (sus pedidos se responden en el INFORME de trazabilidad, NO en la ficha). La ficha queda exactamente con las secciones del documento original."""


def _bloque_trigger(pedidos: Pedidos) -> str:
    if not pedidos.trigger_texto:
        return "Instrucciones de la doctora: sin instrucciones (no hay bloque ** mortadelo)."
    return (
        "Instrucciones de la doctora (bloque ** mortadelo; prioridad maxima):\n"
        f"{pedidos.trigger_texto.strip()}"
    )


def _bloque_pcic(pedidos: Pedidos, pcic_base: str | None) -> str:
    """Insumo + regla del PCIC (REQ-103), solo cuando el bloque ** mortadelo
    pide PCIC y la base esta disponible.

    El LLM entrega el plan al final de su salida bajo la linea exacta
    'PCIC:'; el ENSAMBLADOR decide donde va (la plantilla con la seccion
    vacia se llena, la ya escrita por la doctora manda, la ausente se
    agrega al final). Aca solo instruimos la generacion.
    """
    if not pedidos.pcic or not pcic_base:
        return ""
    return f"""=== INSUMO 3 - PCIC: base aprobada y reglas de customizacion ===
{pcic_base.strip()}
=== FIN INSUMO 3 ===

PCIC (excepcion a la prohibicion de agregar secciones, igual que INDICACIONES):
- Si la doctora YA escribio su PCIC en el documento (bloque numerado 1) Objetivo ... 5) Plazo bajo un titulo que diga 'plan individual de cuidados consensuados'), el de ella MANDA: no lo toques y NO agregues la seccion PCIC.
- Si NO esta escrito, AGREGA AL FINAL de tu salida una seccion que empiece con la linea EXACTA 'PCIC:' y debajo el plan numerado 1) a 5) con el formato EXACTO del insumo:
  1) Objetivo: customizalo con las 'Reglas de customizacion' del insumo usando los diagnosticos activos, signos vitales y examenes del paciente (combina con '/', omite las que no apliquen; sin condiciones claras usa el objetivo generico del insumo).
  2) a 5) mantenlos del template con ajuste minimo de redaccion al contexto del paciente."""


def construir_prompt_ficha(
    paciente: str,
    fecha: str,
    base_anamnesis: str,
    info_paciente: str,
    examenes: str | None,
    pedidos: Pedidos,
    pcic_base: str | None = None,
) -> str:
    """Prompt de la LLAMADA 1 (ficha completa).

    REQ-077/078: la ficha NUNCA agrega secciones — los pedidos del
    bloque ** mortadelo se responden en el informe de trazabilidad
    (llamada 2).
    """
    bloque_exam = examenes if examenes else "(este paciente no tiene examenes consolidados)"
    primera = base_anamnesis.splitlines()[0] if base_anamnesis.splitlines() else ""
    return f"""Completa el documento ANAMNESIS de {paciente} ({fecha}) utilizando los insumos entregados.

=== DOCUMENTO PRINCIPAL (ANAMNESIS a completar; su primera linea es el motivo en blockquote) ===
{base_anamnesis}
=== FIN DOCUMENTO PRINCIPAL ===

=== INSUMO 1 - Informacion del paciente ===
{info_paciente}
=== FIN INSUMO 1 ===

=== INSUMO 2 - Examenes ===
{bloque_exam}
=== FIN INSUMO 2 ===

{_bloque_trigger(pedidos)}

{_bloque_pcic(pedidos, pcic_base)}

{_REGLAS_FICHA}
Salida: exclusivamente el contenido del documento actualizado, respetando el formato original. Sin comentarios ni explicaciones, sin bloques de codigo. OBLIGATORIO: la primera linea de tu salida es EXACTAMENTE la primera linea del documento original, copiada tal cual, incluidos sus simbolos '>':
{primera}"""


def construir_prompt_informe(
    paciente: str,
    fecha: str,
    ficha_generada: str,
    info_paciente: str,
    examenes: str | None,
    pedidos: Pedidos,
) -> str:
    """Prompt de la LLAMADA 2 (informe de trazabilidad).

    REQ-077/078: los pedidos del bloque ** mortadelo (estructurados y
    libres) se responden AQUI, en la seccion 'Solicitudes de la
    doctora' — la ficha no agrega secciones.
    """
    bloque_exam = examenes if examenes else "(sin examenes consolidados)"
    return f"""Genera el INFORME DE TRAZABILIDAD de {paciente} ({fecha}), documento de supervision para la Dra. Yadira. Markdown claro, sencillo y profesional, con EXACTAMENTE estas secciones en este orden:

## ALERTAS
(indicadores de riesgo en los insumos: ideacion suicida, autolesiones, violencia intrafamiliar, consumo de riesgo; si no hay, escribir "Sin alertas.")

## Solicitudes de la doctora
(El bloque ** mortadelo puede traer instrucciones de la doctora y datos de apoyo. Por CADA instruccion — generar/realizar interconsulta a una especialidad, indicaciones para el paciente, sugerencias para la psicologa u otro profesional, como cerrar un GES, u otras — escribe en NEGRITA el pedido y debajo tu respuesta experta completa, fundamentada en los insumos: si pide interconsulta, el texto completo listo para copiar; si pide sugerencias o indicaciones, el listado concreto. Los datos de apoyo del bloque — telefono, agudeza visual, formulas — integrálos en las respuestas correspondientes. Si el bloque no trae instrucciones, escribe "Sin solicitudes.")

## Llenados realizados
(tabla markdown | Campo | Origen | Fundamentacion |; una fila por cada campo vacio que fue completado en la ficha; Origen = info_paciente / examenes / criterio experto)

## Correcciones ortograficas
(tabla markdown | Original | Corregido |; SOLO las correcciones de ortografia objetiva aplicadas al texto de la doctora; si ninguna, "Ninguna.")

## Diagnostico diferencial
(lista con guiones, basada en los insumos)

## Recomendaciones
(lista con guiones para la doctora; incluye polifarmacia y oportunidades de desprescripcion cuando aplique)

## Sin informacion suficiente
(campos factuales que quedaron (-) y por que; si ninguno, "Ninguno.")

=== FICHA COMPLETA GENERADA ===
{ficha_generada}
=== FIN FICHA ===

=== INSUMO 1 - Informacion del paciente ===
{info_paciente}
=== FIN INSUMO 1 ===

=== INSUMO 2 - Examenes ===
{bloque_exam}
=== FIN INSUMO 2 ===

{_bloque_trigger(pedidos)}

Salida: exclusivamente el informe markdown, sin comentarios ni bloques de codigo."""
