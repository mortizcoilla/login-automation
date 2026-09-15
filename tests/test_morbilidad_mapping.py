"""Tests del bundle morbilidad.

Estos tests verifican que el bundle consume correctamente la fuente
de verdad (`_REGLA` en `src.reglas_plantillas`). Si Yadira edita el
dict, los tests siguen siendo validos.
"""
from __future__ import annotations

import inspect

import pytest

from src.mortadelo.skills.morbilidad import (
    PLANTILLA,
    es_morbilidad,
    resolver_plantilla,
    tipos_atencion_del_bundle,
)


# ---- Sanity check del bundle ----

def test_plantilla_canonica() -> None:
    """El bundle declara la plantilla unica de morbilidad."""
    assert PLANTILLA == "MORBILIDAD"


def test_tipos_del_bundle_vienen_de_regla() -> None:
    """El bundle expone los tipo_atencion que caen en PLANTILLA,
    derivados de _REGLA (no hardcoded)."""
    tipos = tipos_atencion_del_bundle()
    # Segun _REGLA al 2026-08-22, hay 4 tipo_atencion de morbilidad.
    # Nota: "Control cronico descompensado" no lleva acento en "cronico"
    # (asi esta en el dict original que Yadira definio).
    assert len(tipos) == 4
    assert tipos == frozenset({
        "Morbilidad",
        "Morbilidad telefónica",
        "Morbilidad presencial",
        "Control cronico descompensado",
    })


# ---- es_morbilidad (via resolver canonico) ----

@pytest.mark.parametrize(
    "tipo",
    [
        "Morbilidad",
        "Morbilidad telefónica",
        "Morbilidad presencial",
        "Control crónico descompensado",
        "MORBILIDAD",  # mayusculas
        "morbilidad",  # minusculas
    ],
)
def test_es_morbilidad_true_para_los_4(tipo: str) -> None:
    assert es_morbilidad(tipo) is True


@pytest.mark.parametrize(
    "tipo",
    [
        "Ingreso integral ecicep-g1",
        "Ingreso salud mental infantil",
        "Recetas",
        "Control integral ecicep-g2",
        "Consulta salud mental",
        "Control salud",  # placeholder de niño sano
        "morb",  # parcial: NO matchea
        "",
    ],
)
def test_es_morbilidad_false_para_otros(tipo: str) -> None:
    assert es_morbilidad(tipo) is False


@pytest.mark.parametrize(
    "tipo",
    [
        "Morbilidad  ",  # espacios al final
        "  Control crónico descompensado  ",  # espacios alrededor
    ],
)
def test_es_morbilidad_tolera_whitespace(tipo: str) -> None:
    assert es_morbilidad(tipo) is True


# ---- resolver_plantilla expone la API del repo ----

@pytest.mark.parametrize(
    "tipo,esperado",
    [
        ("Morbilidad", "MORBILIDAD"),
        ("Morbilidad telefónica", "MORBILIDAD"),
        ("Control crónico descompensado", "MORBILIDAD"),
        ("Ingreso integral ecicep-g1", "INGRESO ECICEP"),
        ("Recetas", "RECETA"),
    ],
)
def test_resolver_plantilla_del_bundle(tipo: str, esperado: str) -> None:
    assert resolver_plantilla(tipo) == esperado


def test_resolver_plantilla_none_fuera_del_bundle() -> None:
    assert resolver_plantilla("Tipo inventado") is None
    assert resolver_plantilla("") is None


# ---- Test de la propiedad clave: el bundle NO duplica el mapping ----

def test_el_bundle_consume_regla_no_la_duplica() -> None:
    """El bundle consume resolver_plantilla, no tiene un set propio."""
    from src.mortadelo.skills.morbilidad import mapping as m
    src = inspect.getsource(m)
    assert "TIPO_ATENCION_MORBILIDAD" not in src, (
        "El bundle esta duplicando el mapping. Debe consumir "
        "reglas_plantillas.resolver_plantilla."
    )
    assert "resolver_plantilla" in src
