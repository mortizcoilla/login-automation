"""Prompts del paso 7 (validados en 4 corridas reales de prueba).

PROMPT_VERSION permite rastrear cambios de redaccion en el tiempo
(REQ-055). El rol medico NO va aqui: vive en el system prompt del
agente (.opencode/agent/mortadelo.md, rol v2 aprobado).
"""

from __future__ import annotations

from dataclasses import dataclass, field

PROMPT_VERSION = 2


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
    pedidos_libres: list[str] = field(default_factory=list)


_REGLAS_FICHA = """Ejecucion:
1. Identifica los campos vacios del documento principal (campo sin valor tras los dos puntos; "niega" y "(-)" son datos validos, no vacios).
2. Completalos primero con informacion de los insumos.
3. Lo que no este en los insumos y sea interpretable clinicamente, completalo con tu criterio experto, fundamentado.
4. Los datos factuales del paciente (telefono, domicilio, acompanantes, fechas administrativas) que no existan en ninguna fuente quedan (-).

Correccion ortografica: corrige faltas de ortografia del texto de la doctora (letras faltantes o sobrantes, tildes, terminos medicos mal escritos) SIN cambiar el contenido, el estilo, las abreviaturas ni el formato. NO corrijas tiempos verbales, NO mejores la redaccion ni la puntuacion: solo ortografia objetiva.

Prohibido: agregar secciones o bloques nuevos (salvo las secciones expresamente pedidas abajo); eliminar secciones existentes; modificar, corregir o reformular los campos ya escritos por la doctora (mas alla de la ortografia objetiva); reformatear (no conviertas texto en vinetas ni vinetas en texto).

IMPORTANTE - bloque ** mortadelo: es una instruccion para el sistema, NO contenido clinico. ELIMINALO del documento final (no debe aparecer en tu salida)."""


def _bloque_trigger(pedidos: Pedidos) -> str:
    if not pedidos.trigger_texto:
        return "Instrucciones de la doctora: sin instrucciones (no hay bloque ** mortadelo)."
    return (
        "Instrucciones de la doctora (bloque ** mortadelo; prioridad maxima):\n"
        f"{pedidos.trigger_texto.strip()}"
    )


def _secciones_condicionales(pedidos: Pedidos) -> str:
    partes: list[str] = []
    if pedidos.indicaciones:
        partes.append(
            "Como la doctora pidio INDICACIONES, agrega AL FINAL del documento una "
            'seccion con titulo "INDICACIONES:" (mayusculas y dos puntos, como los '
            "demas titulos del documento), con las indicaciones segun insumos y "
            "criterio experto, listas para copiar en Rayen."
        )
    if pedidos.interconsulta_especialidad:
        partes.append(
            f"Como la doctora pidio INTERCONSULTA, agrega AL FINAL del documento "
            f"(despues de INDICACIONES si tambien fue pedida) una seccion con titulo "
            f'"INTERCONSULTA A {pedidos.interconsulta_especialidad.upper()}:" '
            "(mayusculas y dos puntos), con el texto de la interconsulta completo y "
            "listo para copiar en Rayen: antecedentes relevantes, motivo, hallazgos "
            "que la justifican y solicitud concreta."
        )
    if pedidos.pedidos_libres:
        lineas = "\n".join(f"  - {pedido}" for pedido in pedidos.pedidos_libres)
        partes.append(
            "Como la doctora pidio ADEMAS lo siguiente, agrega AL FINAL del documento "
            "(despues de INDICACIONES e INTERCONSULTA si tambien fueron pedidas) una "
            "seccion por cada pedido: el titulo de la seccion es el pedido EXACTO en "
            "MAYUSCULAS seguido de dos puntos, y el cuerpo es tu respuesta experta "
            f"(fundamentada en los insumos y en tu criterio clinico):\n{lineas}"
        )
    return " ".join(partes) if partes else ""


def construir_prompt_ficha(
    paciente: str,
    fecha: str,
    base_anamnesis: str,
    info_paciente: str,
    examenes: str | None,
    pedidos: Pedidos,
) -> str:
    """Prompt de la LLAMADA 1 (ficha completa)."""
    bloque_exam = examenes if examenes else "(este paciente no tiene examenes consolidados)"
    secciones = _secciones_condicionales(pedidos)
    if secciones:
        secciones = "\n\n" + secciones
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

{_bloque_trigger(pedidos)}{secciones}

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
    """Prompt de la LLAMADA 2 (informe de trazabilidad)."""
    bloque_exam = examenes if examenes else "(sin examenes consolidados)"
    nota_libres = ""
    if pedidos.pedidos_libres:
        lineas = "\n".join(f"  - {pedido}" for pedido in pedidos.pedidos_libres)
        nota_libres = (
            "\nLa doctora pidio ademas estos pedidos libres (deben estar respondidos "
            f"como secciones al final de la ficha generada):\n{lineas}\n"
            "Verifica que la ficha los responda y registrá cada uno en la seccion "
            "'Llenados realizados'."
        )
    return f"""Genera el INFORME DE TRAZABILIDAD de {paciente} ({fecha}), documento de supervision para la Dra. Yadira. Markdown claro, sencillo y profesional, con EXACTAMENTE estas secciones en este orden:

## ALERTAS
(indicadores de riesgo en los insumos: ideacion suicida, autolesiones, violencia intrafamiliar, consumo de riesgo; si no hay, escribir "Sin alertas.")

## Llenados realizados
(tabla markdown | Campo | Origen | Fundamentacion |; una fila por cada campo vacio que fue completado en la ficha y por cada seccion agregada; Origen = info_paciente / examenes / criterio experto)

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

{_bloque_trigger(pedidos)}{nota_libres}

Salida: exclusivamente el informe markdown, sin comentarios ni bloques de codigo."""
