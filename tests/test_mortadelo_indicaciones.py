"""Tests REQ-098 (v2): INDICACIONES clinicas del LLM en la ficha + sin marcador.

- ensamblar_ficha: la primera linea '> **Motivo de atencion:** X' NO va
  en la ficha final (decision usuaria 29-09).
- Seccion INDICACIONES de plantilla VACIA (stubs '5.1.') + LLM que la
  lleno -> la ficha queda con las lineas del LLM normalizadas a '> - '.
- La doctora ya escribio indicaciones -> se conserva la base.
- El LLM con bullets '- ' o numerados -> igual normalizado a '> - '.
- Docs sin plantilla: 'INDICACIONES:' del LLM al final (REQ-079).
"""

from __future__ import annotations

from src.mortadelo.ensamblador import ensamblar_ficha

_BASE = """> **Motivo de atencion:** DERIVACION
1. DATOS GENERALES Y MOTIVO DE CONSULTA
   - Edad: 28 años

2. ANTECEDENTES MÉDICOS Y FARMACOLÓGICOS
   - APP: no

5. INDICACIONES
\t5.1.
\t5.2.
\t...

6. CONTROL
   - sin datos
"""

_LLM = """1. DATOS GENERALES Y MOTIVO DE CONSULTA
   - Edad: 28 años

2. ANTECEDENTES MÉDICOS Y FARMACOLÓGICOS
   - APP: no

5. INDICACIONES
> - Derivación a Cirugía (interconsulta generada). Acudir con carné y esta ficha.
> - Cuidado de la cicatriz labial: masaje cicatrizal 3-5 min, 2-3 veces al día.

6. CONTROL
   - sin datos
"""


def test_ensamblado_quita_marcador_de_motivo() -> None:
    ensamblada = ensamblar_ficha(_BASE, _LLM)
    assert not ensamblada.texto.startswith(">")
    assert "Motivo de atencion" not in ensamblada.texto
    assert ensamblada.texto.startswith("1. DATOS GENERALES")


def test_indicaciones_del_llm_entran_en_la_seccion_vacia() -> None:
    ensamblada = ensamblar_ficha(_BASE, _LLM)
    texto = ensamblada.texto
    assert "5. INDICACIONES" in texto
    assert "> - Derivación a Cirugía (interconsulta generada)" in texto
    assert "> - Cuidado de la cicatriz labial" in texto
    # los stubs vacios de la plantilla ya no estan
    assert "\t5.1." not in texto and "5.2.\n" not in texto.split("6. CONTROL")[0]
    # la seccion siguiente no se toca
    assert "6. CONTROL" in texto
    assert "INDICACIONES" in ensamblada.secciones_agregadas


def test_indicaciones_de_la_doctora_se_conservan() -> None:
    base = _BASE.replace("\t5.1.\n\t5.2.\n\t...", "\t5.1. Reposo relativo")
    ensamblada = ensamblar_ficha(base, _LLM)
    assert "\t5.1. Reposo relativo" in ensamblada.texto
    assert "Derivación a Cirugía" not in ensamblada.texto


def test_llm_con_bullets_normales_se_normaliza() -> None:
    llm = _LLM.replace("> - Derivación", "- Derivación").replace(
        "> - Cuidado", "5.1. Cuidado"
    )
    ensamblada = ensamblar_ficha(_BASE, llm)
    assert "> - Derivación a Cirugía" in ensamblada.texto
    assert "> - Cuidado de la cicatriz labial" in ensamblada.texto


def test_sin_plantilla_indicaciones_al_final() -> None:
    base = "> **Motivo de atencion:** x\n\nPaciente de 17 años de edad\n"
    llm = "Paciente de 17 años de edad\n\nINDICACIONES:\n> - Control en 3 meses.\n"
    ensamblada = ensamblar_ficha(base, llm)
    assert "INDICACIONES:" in ensamblada.texto
    assert ensamblada.texto.rstrip().endswith("Control en 3 meses.")


def test_seccion_vacia_sin_llm_queda_como_la_base() -> None:
    ensamblada = ensamblar_ficha(_BASE, _BASE)
    assert "\t5.1." in ensamblada.texto  # stubs intactos, nada inventado
