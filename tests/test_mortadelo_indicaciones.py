"""Tests REQ-098: pedidos de la doctora en la ficha + sin marcador de motivo.

- ensamblar_ficha: la primera linea '> **Motivo de atencion:** X' NO va
  en la ficha final (decision usuaria 29-09).
- rellenar_indicaciones:
    * seccion numerada vacia ('5. INDICACIONES' con '5.1.' vacios) ->
      items '5.1.', '5.2.' con los pedidos.
    * seccion con contenido -> pedidos agregados renumerando.
    * sin seccion -> 'INDICACIONES:' al final (REQ-079).
    * lista vacia -> texto intacto.
- _pedidos_crudos: lineas del trigger sin el marcador ni bullets.
"""

from __future__ import annotations

from src.mortadelo.ensamblador import ensamblar_ficha, rellenar_indicaciones
from src.mortadelo.generar import _pedidos_crudos

_FICHA = """1. DATOS GENERALES Y MOTIVO DE CONSULTA
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


def test_ensamblado_quita_marcador_de_motivo() -> None:
    base = "> **Motivo de atencion:** DERIVACION\n\n1. DATOS\n   - APP: no\n"
    ensamblada = ensamblar_ficha(base, base)
    assert not ensamblada.texto.startswith(">")
    assert "Motivo de atencion" not in ensamblada.texto
    assert ensamblada.texto.startswith("1. DATOS")


def test_rellenar_indicaciones_seccion_numerada_vacia() -> None:
    texto, n = rellenar_indicaciones(_FICHA, ["Realiza la derivacion a cirugia"])
    assert n == 1
    assert "   5.1. Realiza la derivacion a cirugia" in texto
    assert "\t5.1." not in texto  # los items vacios se reemplazan
    assert "6. CONTROL" in texto  # la seccion siguiente no se toca


def test_rellenar_indicaciones_agrega_renumerando() -> None:
    con_contenido = _FICHA.replace("\t5.1.\n\t5.2.\n\t...", "\t5.1. Reposo relativo")
    texto, n = rellenar_indicaciones(con_contenido, ["Derivar a cirugia"])
    assert n == 1
    assert "\t5.1. Reposo relativo" in texto  # lo existente se conserva
    assert "   5.2. Derivar a cirugia" in texto


def test_rellenar_indicaciones_sin_seccion_agrega_al_final() -> None:
    texto, n = rellenar_indicaciones("1. DATOS\n   - APP: no\n", ["Indicacion X"])
    assert n == 1
    assert texto.rstrip().endswith("- Indicacion X")
    assert "INDICACIONES:" in texto


def test_rellenar_indicaciones_sin_pedidos_no_toca() -> None:
    texto, n = rellenar_indicaciones(_FICHA, [])
    assert n == 0
    assert texto == _FICHA


def test_pedidos_crudos_limpia_marcador_y_bullets() -> None:
    trigger = "** MORTADELO:  REALIZA LA INTERCONSULTA A CIRUGIA\n- avisar a la paciente\n"
    crudos = _pedidos_crudos(trigger)
    assert crudos == ["REALIZA LA INTERCONSULTA A CIRUGIA", "avisar a la paciente"]
