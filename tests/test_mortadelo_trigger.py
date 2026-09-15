"""Tests del trigger `** mortadelo` (case-insensitive, tolera espacios)."""
from __future__ import annotations

import pytest

from src.mortadelo.trigger import (
    TRIGGER_RE,
    contar_triggers,
    contiene_trigger,
    extraer_triggers,
)


# ---- Variantes validas (deben detectarse) ----

@pytest.mark.parametrize(
    "texto",
    [
        # Patron canonico
        "** mortadelo",
        # Nombre propio con y sin espacio
        "**Mortadelo",
        "** Mortadelo",
        "**  Mortadelo",  # multiples espacios
        # Mayusculas
        "**MORTADELO",
        "** MORTADELO",
        # Minusculas sin espacio
        "**mortadelo",
        # Mayusculas/minusculas mixtas
        "**MoRtAdElO",
        "** mortaDELO",
        # Con terminadores de instruccion
        "** mortadelo:",
        "**Mortadelo -",
        "** mortadelo\n",
        "**Mortadelo\n",
        # Coma como terminador (caso Cecilia Reyes, 2026-08-22)
        "** Mortadelo,",
        "**Mortadelo, realiza la interconsulta",
        "**mortadelo, agrega el peso",
    ],
)
def test_contiene_trigger_variantes_validas(texto: str) -> None:
    assert contiene_trigger(texto) is True


@pytest.mark.parametrize(
    "texto",
    [
        "** mortadelo por favor revisa la nota",
        "Anamnesis: ...\n** mortadelo\nObservaciones: ...",
        "**Mortadelo agregar dx diferencial",
        "Paciente: Juan Perez\n** MORTADELO\n  - Sugerir farmaco\n  - Confirmar dx",
        "  **  mortadelo  con espacios al rededor",
    ],
)
def test_contiene_trigger_en_contexto(texto: str) -> None:
    """El trigger se detecta dentro de notas reales con contexto."""
    assert contiene_trigger(texto) is True


# ---- Casos invalidos (NO deben detectarse) ----

@pytest.mark.parametrize(
    "texto",
    [
        "",                                    # nota vacia
        "mortadelo",                           # sin **
        "* mortadelo",                         # un solo *
        "** mortadelox",                       # sin word boundary
        "**mortadelin",                        # sin word boundary
        "** otro_mortadelo",                   # prefijo con underscore
        "**mortadelo_falso",                   # sufijo pegado
        "**mortadelo.",                        # punto inmediato (no trigger completo)
    ],
)
def test_no_detecta_variantes_invalidas(texto: str) -> None:
    assert contiene_trigger(texto) is False


# ---- Conteo de triggers ----

def test_contar_triggers_cero() -> None:
    assert contar_triggers("nota sin trigger") == 0
    assert contar_triggers("") == 0


def test_contar_triggers_uno() -> None:
    assert contar_triggers("** mortadelo revisa") == 1


def test_contar_triggers_multiples() -> None:
    nota = (
        "Anamnesis: ...\n"
        "** mortadelo agrega el peso\n"
        "Observaciones: ...\n"
        "**Mortadelo y la talla tambien\n"
        "Fin."
    )
    assert contar_triggers(nota) == 2


def test_contar_triggers_variantes_distintas() -> None:
    """Mezcla de variantes cuenta cada ocurrencia."""
    nota = "**mortadelo uno\n** Mortadelo dos\n**MORTADELO tres"
    assert contar_triggers(nota) == 3


# ---- Extraccion de matches ----

def test_extraer_triggers_vacio() -> None:
    assert extraer_triggers("") == []
    assert extraer_triggers("nota sin trigger") == []


def test_extraer_triggers_posiciones() -> None:
    nota = "antes ** mortadelo medio **Mortadelo fin"
    matches = extraer_triggers(nota)
    assert len(matches) == 2
    # Primer match empieza despues de "antes "
    assert matches[0].start() == 6
    assert matches[0].group() == "** mortadelo"
    # Segundo match empieza despues de "medio "
    assert matches[1].start() == nota.index("**Mortadelo")
    assert matches[1].group() == "**Mortadelo"


# ---- La regex publica no tiene flags problematicos ----

def test_trigger_re_es_case_insensitive() -> None:
    assert TRIGGER_RE.flags & __import__("re").IGNORECASE


# ---- Borrar el trigger de la nota (uso tipico) ----

def test_borrar_trigger_simple() -> None:
    """Caso de uso: detectar y borrar el trigger con re.sub."""
    nota = "Anamnesis: ..\n** mortadelo agrega peso\nObservaciones: .."
    limpio = TRIGGER_RE.sub("", nota)
    # La nota queda sin el trigger pero con el resto del texto
    assert "** mortadelo" not in limpio
    assert "**Mortadelo" not in limpio
    assert "Anamnesis" in limpio
    assert "Observaciones" in limpio


def test_borrar_multiples_triggers() -> None:
    nota = "**mortadelo uno\ntexto\n**Mortadelo dos"
    limpio = TRIGGER_RE.sub("", nota)
    assert "**mortadelo" not in limpio.lower() or "**" not in limpio.lower()
    # Mejor: verificar que no quedan las marcas exactas
    assert "**mortadelo" not in limpio
    assert "**Mortadelo" not in limpio
    assert "uno" in limpio
    assert "dos" in limpio
