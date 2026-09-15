"""Tests del bundle salud_mental.

Estos tests verifican que el bundle consume correctamente la fuente
de verdad (`_REGLA` en `src.reglas_plantillas`). Si Yadira agrega
un nuevo `tipo_atencion` a `_REGLA` que mapee a `INGRESO SALUD MENTAL
SIN ECICEP`, el bundle lo absorbe automaticamente.
"""
from __future__ import annotations

import inspect

import pytest

from src.mortadelo.skills.salud_mental import (
    PLANTILLA,
    es_salud_mental,
    resolver_plantilla,
    tipos_atencion_del_bundle,
)


# ---- Sanity check del bundle ----

def test_plantilla_canonica() -> None:
    """El bundle declara la plantilla unica de salud mental."""
    assert PLANTILLA == "INGRESO SALUD MENTAL SIN ECICEP"


def test_tipos_del_bundle_vienen_de_regla() -> None:
    """El bundle expone los tipo_atencion que caen en PLANTILLA,
    derivados de _REGLA (no hardcoded)."""
    tipos = tipos_atencion_del_bundle()
    # Segun _REGLA al 2026-08-22, hay 4 tipo_atencion SM
    assert len(tipos) == 4
    # Las claves de tipos_atencion_del_bundle son las keys ORIGINALES
    # del dict (con acentos), no normalizadas.
    assert tipos == frozenset({
        "Ingreso salud mental infantil",
        "Ingreso multidisciplinario salud mental - infantil",
        "Control salud mental infantil",
        "Consulta salud mental",
    })


# ---- es_salud_mental (via resolver canonico) ----

@pytest.mark.parametrize(
    "tipo",
    [
        "Ingreso salud mental infantil",
        "Ingreso multidisciplinario salud mental - infantil",
        "Control salud mental infantil",
        "Consulta salud mental",
        "INGRESO SALUD MENTAL INFANTIL",  # mayusculas
        "consulta salud mental",  # minusculas
    ],
)
def test_es_salud_mental_true_para_los_4(tipo: str) -> None:
    assert es_salud_mental(tipo) is True


@pytest.mark.parametrize(
    "tipo",
    [
        "Morbilidad",
        "Ingreso integral ecicep-g1",
        "Recetas",
        "Control integral ecicep-g2",
        "Control cronico descompensado",
        "ingreso salud mental",  # parcial: NO matchea
        "",
    ],
)
def test_es_salud_mental_false_para_otros(tipo: str) -> None:
    assert es_salud_mental(tipo) is False


@pytest.mark.parametrize(
    "tipo",
    [
        "Consulta salud mental  ",  # espacios al final
        "  Ingreso salud mental infantil  ",  # espacios alrededor
    ],
)
def test_es_salud_mental_tolera_whitespace(tipo: str) -> None:
    """Espacios al inicio/final no invalidan el match."""
    assert es_salud_mental(tipo) is True


# ---- resolver_plantilla expone la API del repo ----

@pytest.mark.parametrize(
    "tipo,esperado",
    [
        ("Ingreso salud mental infantil", "INGRESO SALUD MENTAL SIN ECICEP"),
        ("Morbilidad", "MORBILIDAD"),
        ("Ingreso integral ecicep-g1", "INGRESO ECICEP"),
        ("Recetas", "RECETA"),
        ("Control integral ecicep-g2", "CONTROL INTEGRAL SIN FICHA ANTERIOR"),
    ],
)
def test_resolver_plantilla_del_bundle(tipo: str, esperado: str) -> None:
    """El resolver del bundle es el mismo que el del repo."""
    assert resolver_plantilla(tipo) == esperado


def test_resolver_plantilla_none_fuera_del_bundle() -> None:
    assert resolver_plantilla("Tipo inventado") is None
    assert resolver_plantilla("") is None


# ---- Test de la propiedad clave: el bundle NO duplica el mapping ----

def test_el_bundle_consume_regla_no_la_duplica() -> None:
    """El bundle consume resolver_plantilla, no tiene un set propio."""
    from src.mortadelo.skills.salud_mental import mapping as m
    src = inspect.getsource(m)
    assert "TIPO_ATENCION_SALUD_MENTAL" not in src, (
        "El bundle esta duplicando el mapping. Debe consumir "
        "reglas_plantillas.resolver_plantilla."
    )
    assert "resolver_plantilla" in src


# ---- Cobertura de manuales validados (al 2026-08-22) ----

MANUALES_ESPERADOS = frozenset({
    # Cobertura clinica
    "minsal-depresion-2013.md",
    "minsal-trastorno-ansioso-2018.md",
    "minsal-alcohol-drogas-menores20-2013.md",
    "programa-nacional-prevencion-suicidio-2013.md",
    "dsm5.md",
    # Marco regulatorio y programatico
    "ley-21331-diprece-2022.md",
    "construyendo-salud-mental-2024.md",
    "rpe11-programacion-sm-aps-2021.md",
    "plan-nacional-sm-2017-2025.md",
})


def test_manuales_validados_presentes() -> None:
    """Los 9 manuales validados al 2026-08-22 existen en manuales/."""
    from pathlib import Path
    manuales_dir = Path(__file__).resolve().parent.parent / "src" / "mortadelo" / "skills" / "salud_mental" / "manuales"
    existentes = {f.name for f in manuales_dir.glob("*.md")}
    faltantes = MANUALES_ESPERADOS - existentes
    assert not faltantes, f"Manuales faltantes en {manuales_dir}: {faltantes}"


@pytest.mark.parametrize("manual", sorted(MANUALES_ESPERADOS))
def test_manual_tiene_frontmatter(manual: str) -> None:
    """Cada manual .md tiene frontmatter YAML con source, source_url,
    year y pages (regla del proyecto)."""
    from pathlib import Path
    manuales_dir = Path(__file__).resolve().parent.parent / "src" / "mortadelo" / "skills" / "salud_mental" / "manuales"
    ruta = manuales_dir / manual
    contenido = ruta.read_text(encoding="utf-8")
    assert contenido.startswith("---\n"), f"{manual} no tiene frontmatter YAML"
    assert "source:" in contenido, f"{manual} falta 'source' en frontmatter"
    assert "source_url:" in contenido, f"{manual} falta 'source_url' en frontmatter"
    assert "year:" in contenido, f"{manual} falta 'year' en frontmatter"
    assert "pages:" in contenido, f"{manual} falta 'pages' en frontmatter"
