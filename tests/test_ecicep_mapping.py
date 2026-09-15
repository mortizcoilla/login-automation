"""Tests del bundle ecicep (consolidado: ingreso + control)."""
from __future__ import annotations

import inspect

import pytest

from src.mortadelo.skills.ecicep import (
    PLANTILLAS_ECICEP,
    es_ecicep,
    es_ecicep_ingreso,
    es_ecicep_control,
    plantilla_para,
    resolver_plantilla,
    tipos_atencion_del_bundle,
)


# ---- Sanity check del bundle ----

def test_plantillas_ecicep() -> None:
    """El bundle declara las 2 plantillas ECICEP."""
    assert PLANTILLAS_ECICEP == frozenset({
        "INGRESO ECICEP",
        "CONTROL INTEGRAL SIN FICHA ANTERIOR",
    })


def test_tipos_del_bundle_vienen_de_regla() -> None:
    """El bundle expone los tipo_atencion que caen en PLANTILLAS_ECICEP,
    derivados de _REGLA (no hardcoded)."""
    tipos = tipos_atencion_del_bundle()
    # Segun _REGLA al 2026-08-22: 5 ingresos + 7 controles = 12 tipo_atencion
    assert len(tipos) == 12
    assert tipos == frozenset({
        # Ingreso (5)
        "Ingreso integral ecicep-g1",
        "Ingreso integral ecicep-g2",
        "Ingreso integral ecicep-g3",
        "Ingreso multimorbilidad g2",
        "Ingreso multimorbilidad g3",
        # Control (7)
        "Control integral ecicep-g1",
        "Control integral ecicep-g2",
        "Control integral ecicep-g3",
        "Control integral multimorbilidad g1",
        "Control integral multimorbilidad g2",
        "Control integral multimorbilidad g3",
        "Control crónico",
    })


# ---- es_ecicep (cualquier atencion ECICEP) ----

@pytest.mark.parametrize(
    "tipo",
    [
        # Ingreso
        "Ingreso integral ecicep-g1",
        "Ingreso integral ecicep-g2",
        "Ingreso integral ecicep-g3",
        "Ingreso multimorbilidad g2",
        "Ingreso multimorbilidad g3",
        # Control
        "Control integral ecicep-g1",
        "Control integral ecicep-g2",
        "Control integral ecicep-g3",
        "Control integral multimorbilidad g1",
        "Control integral multimorbilidad g2",
        "Control integral multimorbilidad g3",
        "Control crónico",
    ],
)
def test_es_ecicep_true_para_todos_los_ecicep(tipo: str) -> None:
    assert es_ecicep(tipo) is True


@pytest.mark.parametrize(
    "tipo",
    [
        "Morbilidad",
        "Ingreso salud mental infantil",
        "Recetas",
        "Control salud",  # placeholder niño sano
        "ecicep",  # parcial: NO matchea
        "",
    ],
)
def test_es_ecicep_false_para_otros(tipo: str) -> None:
    assert es_ecicep(tipo) is False


# ---- es_ecicep_ingreso ----

@pytest.mark.parametrize(
    "tipo",
    [
        "Ingreso integral ecicep-g1",
        "Ingreso integral ecicep-g2",
        "Ingreso integral ecicep-g3",
        "Ingreso multimorbilidad g2",
        "Ingreso multimorbilidad g3",
    ],
)
def test_es_ecicep_ingreso_true_para_ingresos(tipo: str) -> None:
    assert es_ecicep_ingreso(tipo) is True
    assert es_ecicep(tipo) is True  # tambien es ecicep


@pytest.mark.parametrize(
    "tipo",
    [
        "Control integral ecicep-g1",
        "Control crónico",
        "Morbilidad",
    ],
)
def test_es_ecicep_ingreso_false_para_controles_y_otros(tipo: str) -> None:
    assert es_ecicep_ingreso(tipo) is False


# ---- es_ecicep_control ----

@pytest.mark.parametrize(
    "tipo",
    [
        "Control integral ecicep-g1",
        "Control integral ecicep-g2",
        "Control integral ecicep-g3",
        "Control integral multimorbilidad g1",
        "Control integral multimorbilidad g2",
        "Control integral multimorbilidad g3",
        "Control crónico",
    ],
)
def test_es_ecicep_control_true_para_controles(tipo: str) -> None:
    assert es_ecicep_control(tipo) is True
    assert es_ecicep(tipo) is True  # tambien es ecicep


@pytest.mark.parametrize(
    "tipo",
    [
        "Ingreso integral ecicep-g1",
        "Morbilidad",
    ],
)
def test_es_ecicep_control_false_para_ingresos_y_otros(tipo: str) -> None:
    assert es_ecicep_control(tipo) is False


# ---- plantilla_para ----

@pytest.mark.parametrize(
    "tipo,esperado",
    [
        # Ingreso
        ("Ingreso integral ecicep-g1", "INGRESO ECICEP"),
        ("Ingreso integral ecicep-g2", "INGRESO ECICEP"),
        ("Ingreso integral ecicep-g3", "INGRESO ECICEP"),
        ("Ingreso multimorbilidad g2", "INGRESO ECICEP"),
        ("Ingreso multimorbilidad g3", "INGRESO ECICEP"),
        # Control
        ("Control integral ecicep-g1", "CONTROL INTEGRAL SIN FICHA ANTERIOR"),
        ("Control integral ecicep-g2", "CONTROL INTEGRAL SIN FICHA ANTERIOR"),
        ("Control integral ecicep-g3", "CONTROL INTEGRAL SIN FICHA ANTERIOR"),
        ("Control integral multimorbilidad g1", "CONTROL INTEGRAL SIN FICHA ANTERIOR"),
        ("Control integral multimorbilidad g2", "CONTROL INTEGRAL SIN FICHA ANTERIOR"),
        ("Control integral multimorbilidad g3", "CONTROL INTEGRAL SIN FICHA ANTERIOR"),
        ("Control crónico", "CONTROL INTEGRAL SIN FICHA ANTERIOR"),
    ],
)
def test_plantilla_para_devuelve_canonica(tipo: str, esperado: str) -> None:
    assert plantilla_para(tipo) == esperado


def test_plantilla_para_none_fuera_del_bundle() -> None:
    assert plantilla_para("Morbilidad") is None
    assert plantilla_para("Ingreso salud mental infantil") is None
    assert plantilla_para("Recetas") is None
    assert plantilla_para("") is None
    assert plantilla_para("Tipo inventado") is None


# ---- resolver_plantilla expone la API del repo ----

def test_resolver_plantilla_del_bundle() -> None:
    assert resolver_plantilla("Ingreso integral ecicep-g1") == "INGRESO ECICEP"
    assert resolver_plantilla("Control integral ecicep-g1") == "CONTROL INTEGRAL SIN FICHA ANTERIOR"


def test_resolver_plantilla_none_fuera_del_bundle() -> None:
    assert resolver_plantilla("Tipo inventado") is None


# ---- Test de la propiedad clave: el bundle NO duplica el mapping ----

def test_el_bundle_consume_regla_no_la_duplica() -> None:
    """El bundle consume resolver_plantilla, no tiene un set propio."""
    from src.mortadelo.skills.ecicep import mapping as m
    src = inspect.getsource(m)
    assert "TIPO_ATENCION_ECICEP" not in src, (
        "El bundle esta duplicando el mapping. Debe consumir "
        "reglas_plantillas.resolver_plantilla."
    )
    assert "resolver_plantilla" in src
