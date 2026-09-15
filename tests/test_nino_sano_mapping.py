"""Tests del bundle nino_sano (Control de Nino Sano 0-9 anos en APS)."""
from __future__ import annotations

import inspect
from datetime import date

import pytest

from src.mortadelo.skills.nino_sano import (
    LIMITE_MESES_NINO_SANO,
    PLANTILLA_1MES,
    PLANTILLA_3MESES,
    PLANTILLAS_NINO_SANO,
    es_nino_sano,
    es_tipo_control_salud,
    plantilla_para,
    requiere_edad,
    resolver_plantilla,
    tipos_atencion_del_bundle,
)
from src.plantillas import calcular_edad_meses


# ---- Sanity check del bundle ----

def test_plantillas_nino_sano() -> None:
    """El bundle declara las 2 plantillas de nino sano."""
    assert PLANTILLAS_NINO_SANO == frozenset({
        "CONTROL NI\u00d1O SANO 1 MES",
        "CONTROL NI\u00d1O SANO 3 MESES",
    })
    assert PLANTILLA_1MES == "CONTROL NI\u00d1O SANO 1 MES"
    assert PLANTILLA_3MESES == "CONTROL NI\u00d1O SANO 3 MESES"


def test_limite_meses_es_3() -> None:
    """El limite canonico es 3 meses (constante en reglas_plantillas)."""
    assert LIMITE_MESES_NINO_SANO == 3


def test_tipos_del_bundle_vienen_de_regla() -> None:
    """El bundle expone los tipo_atencion que caen en PLANTILLAS_NINO_SANO,
    derivados de _REGLA (no hardcoded)."""
    tipos = tipos_atencion_del_bundle()
    # Segun _REGLA al 2026-08-22: 1 tipo (Control salud)
    assert tipos == frozenset({"Control salud"})


# ---- es_tipo_control_salud (sin edad) ----

@pytest.mark.parametrize("tipo", ["Control salud", "CONTROL SALUD", "control SALUD"])
def test_es_tipo_control_salud_true(tipo: str) -> None:
    assert es_tipo_control_salud(tipo) is True


@pytest.mark.parametrize(
    "tipo",
    [
        "Morbilidad",
        "Ingreso salud mental infantil",
        "Recetas",
        "Ingreso integral ecicep-g1",
        "Control integral ecicep-g2",
        "Control crónico",
        "",
    ],
)
def test_es_tipo_control_salud_false(tipo: str) -> None:
    assert es_tipo_control_salud(tipo) is False


# ---- es_nino_sano (con edad) ----

@pytest.mark.parametrize("edad", [0, 1, 2])
def test_es_nino_sano_true_para_menores_de_3(edad: int) -> None:
    assert es_nino_sano("Control salud", edad_meses=edad) is True


@pytest.mark.parametrize("edad", [3, 4, 5, 6, 12, 24, 60, 108])
def test_es_nino_sano_true_para_3_o_mas(edad: int) -> None:
    assert es_nino_sano("Control salud", edad_meses=edad) is True


def test_es_nino_sano_false_sin_edad() -> None:
    """Sin edad, no se puede resolver la plantilla."""
    assert es_nino_sano("Control salud") is False
    assert es_nino_sano("Control salud", edad_meses=None) is False


def test_es_nino_sano_false_edad_negativa() -> None:
    """Edad negativa es caso patologico, no deberia entrar al bundle."""
    assert es_nino_sano("Control salud", edad_meses=-1) is False


@pytest.mark.parametrize(
    "tipo",
    ["Morbilidad", "Recetas", "Ingreso integral ecicep-g1", ""],
)
def test_es_nino_sano_false_para_otros_tipos(tipo: str) -> None:
    assert es_nino_sano(tipo, edad_meses=1) is False
    assert es_nino_sano(tipo, edad_meses=24) is False


# ---- plantilla_para ----

@pytest.mark.parametrize(
    "edad,esperado",
    [
        (0, "CONTROL NI\u00d1O SANO 1 MES"),
        (1, "CONTROL NI\u00d1O SANO 1 MES"),
        (2, "CONTROL NI\u00d1O SANO 1 MES"),
        (3, "CONTROL NI\u00d1O SANO 3 MESES"),
        (4, "CONTROL NI\u00d1O SANO 3 MESES"),
        (5, "CONTROL NI\u00d1O SANO 3 MESES"),
        (6, "CONTROL NI\u00d1O SANO 3 MESES"),
        (12, "CONTROL NI\u00d1O SANO 3 MESES"),
        (24, "CONTROL NI\u00d1O SANO 3 MESES"),
    ],
)
def test_plantilla_para_segun_edad(edad: int, esperado: str) -> None:
    assert plantilla_para("Control salud", edad_meses=edad) == esperado


def test_plantilla_para_none_sin_edad() -> None:
    assert plantilla_para("Control salud") is None
    assert plantilla_para("Control salud", edad_meses=None) is None


@pytest.mark.parametrize(
    "tipo",
    ["Morbilidad", "Recetas", "Ingreso integral ecicep-g1", "Tipo inventado", ""],
)
def test_plantilla_para_none_fuera_del_bundle(tipo: str) -> None:
    assert plantilla_para(tipo, edad_meses=0) is None
    assert plantilla_para(tipo, edad_meses=24) is None


# ---- requiere_edad ----

def test_requiere_edad_true_para_control_salud() -> None:
    assert requiere_edad("Control salud") is True
    assert requiere_edad("CONTROL SALUD") is True


@pytest.mark.parametrize(
    "tipo",
    ["Morbilidad", "Recetas", "Ingreso integral ecicep-g1", ""],
)
def test_requiere_edad_false_para_otros(tipo: str) -> None:
    assert requiere_edad(tipo) is False


# ---- resolver_plantilla expone la API del repo ----

def test_resolver_plantilla_nino_sano_con_edad() -> None:
    assert resolver_plantilla("Control salud", edad_meses=1) == "CONTROL NI\u00d1O SANO 1 MES"
    assert resolver_plantilla("Control salud", edad_meses=3) == "CONTROL NI\u00d1O SANO 3 MESES"


def test_resolver_plantilla_nino_sano_sin_edad_devuelve_none() -> None:
    """Sin edad, no se puede decidir entre 1 MES y 3 MESES."""
    assert resolver_plantilla("Control salud") is None


# ---- Test de la propiedad clave: el bundle NO duplica el mapping ----

def test_el_bundle_consume_regla_no_la_duplica() -> None:
    """El bundle consume resolver_plantilla, no tiene un set propio."""
    from src.mortadelo.skills.nino_sano import mapping as m
    # El modulo importa resolver_plantilla desde reglas_plantillas
    assert hasattr(m, "resolver_plantilla")
    # Y la usa en sus funciones publicas
    src = inspect.getsource(m)
    assert "resolver_plantilla(" in src, (
        "El bundle debe llamar a resolver_plantilla, no declarar su "
        "propio dict de mapping."
    )


# ---- calcular_edad_meses (funcion de soporte) ----

def test_calcular_edad_meses_recien_nacido() -> None:
    """Bebe nacido hoy -> 0 meses."""
    assert calcular_edad_meses(date(2026, 8, 22), date(2026, 8, 22)) == 0


def test_calcular_edad_meses_1_mes_cumplido() -> None:
    """Bebe de 1 mes y 15 dias -> 1 mes (mes cumplido, no 2)."""
    assert calcular_edad_meses(date(2026, 7, 7), date(2026, 8, 22)) == 1


def test_calcular_edad_meses_2_meses_cumplidos() -> None:
    assert calcular_edad_meses(date(2026, 6, 7), date(2026, 8, 22)) == 2


def test_calcular_edad_meses_3_meses_cumplidos() -> None:
    """Justo 3 meses -> CONTROL NINO SANO 3 MESES."""
    edad = calcular_edad_meses(date(2026, 5, 22), date(2026, 8, 22))
    assert edad == 3
    assert plantilla_para("Control salud", edad_meses=edad) == "CONTROL NI\u00d1O SANO 3 MESES"


def test_calcular_edad_meses_no_cumple_mes_aun() -> None:
    """Bebe de 1 mes y 5 dias vs 1 mes y 25 dias -> ambos 1 mes cumplido."""
    # 2026-07-07 + 25 dias = 2026-08-01 -> 0 meses cumplidos (aun no llega a 2 meses)
    # porque 2026-08-01.day (1) < 2026-07-07.day (7)
    assert calcular_edad_meses(date(2026, 7, 7), date(2026, 8, 1)) == 0


def test_calcular_edad_meses_2_anios_3_meses() -> None:
    """2 anos 3 meses = 27 meses."""
    assert calcular_edad_meses(date(2024, 5, 22), date(2026, 8, 22)) == 27


def test_calcular_edad_meses_por_defecto_hoy() -> None:
    """Sin fecha_referencia, usa date.today()."""
    edad = calcular_edad_meses(date(2026, 1, 1))
    # hoy es 2026-08-22 segun el contexto
    # 2026-01-01 a 2026-08-22 = 7 meses (enero 1, feb 1, ... ago 1 = 7 cumplidos,
    # pero 22 < 1? no, 22 >= 1, asi que 7 meses cumplidos)
    assert edad == 7


def test_calcular_edad_meses_futuro_error() -> None:
    """Si fecha_nacimiento > fecha_referencia, ValueError."""
    with pytest.raises(ValueError):
        calcular_edad_meses(date(2027, 1, 1), date(2026, 8, 22))


# ---- Tests de integracion: routing completo ----

def test_routing_completo_1_mes() -> None:
    """Bebe de 25 dias: Control salud -> CONTROL NINO SANO 1 MES."""
    edad = calcular_edad_meses(date(2026, 7, 28), date(2026, 8, 22))
    assert edad == 0  # no ha cumplido 1 mes
    assert es_nino_sano("Control salud", edad) is True
    assert plantilla_para("Control salud", edad) == "CONTROL NI\u00d1O SANO 1 MES"


def test_routing_completo_3_meses() -> None:
    """Bebe de 3 meses: Control salud -> CONTROL NINO SANO 3 MESES."""
    edad = calcular_edad_meses(date(2026, 5, 22), date(2026, 8, 22))
    assert edad == 3
    assert es_nino_sano("Control salud", edad) is True
    assert plantilla_para("Control salud", edad) == "CONTROL NI\u00d1O SANO 3 MESES"


def test_routing_completo_5_meses() -> None:
    """Bebe de 5 meses: cae en 3 MESES (rango hasta nueva plantilla)."""
    edad = calcular_edad_meses(date(2026, 3, 22), date(2026, 8, 22))
    assert edad == 5
    assert es_nino_sano("Control salud", edad) is True
    assert plantilla_para("Control salud", edad) == "CONTROL NI\u00d1O SANO 3 MESES"


def test_routing_no_edad_no_resuelve() -> None:
    """Sin edad, el bundle no entra aunque el tipo sea correcto."""
    assert es_nino_sano("Control salud", None) is False
    assert plantilla_para("Control salud", None) is None
