"""Tests para src/analysis/enriquecer_informe.py

Sesion 2026-09-16: agregar deteccion de requerimientos Yadira->Mortadelo
y actualizar el parser para aceptar 8 columnas (back-compat con 6).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.analysis.enriquecer_informe import (
    KEYWORDS_REQUERIMIENTOS,
    _extraer_requerimientos,
    _formatear_tabla,
    _parsear_informe_basico,
)
from src.mortadelo.trigger import TRIGGER_RE


# ---------------------------------------------------------------------------
# _extraer_requerimientos() — deteccion de los 2 requerimientos Yadira
# ---------------------------------------------------------------------------

def test_extraer_requerimientos_sin_nota(tmp_path: Path):
    """Si la nota no existe, devuelve dict con ambos False."""
    nota = tmp_path / "no_existe.md"
    resultado = _extraer_requerimientos(nota)
    assert resultado == {"examenes_adjuntos": False, "crear_interconsulta": False}


def test_extraer_requerimientos_sin_trigger(tmp_path: Path):
    """Nota sin ** mortadelo -> ambos False."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "---\n"
        "paciente: 'Test'\n"
        "---\n\n"
        "# Nota clinica\n\n"
        "Anamnesis del paciente sin triggers.\n",
        encoding="utf-8",
    )
    resultado = _extraer_requerimientos(nota)
    assert resultado == {"examenes_adjuntos": False, "crear_interconsulta": False}


def test_extraer_requerimientos_examenes_si(tmp_path: Path):
    """Trigger con bullet 'examenes adjuntos' -> examenes_adjuntos=True."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "---\n"
        "paciente: 'Test'\n"
        "---\n\n"
        "# Nota clinica\n\n"
        "Anamnesis...\n\n"
        "** mortadelo\n\n"
        "- examenes adjuntos\n"
        "- otra cosa\n\n"
        "**\n\n"
        "Fin.\n",
        encoding="utf-8",
    )
    resultado = _extraer_requerimientos(nota)
    assert resultado["examenes_adjuntos"] is True
    assert resultado["crear_interconsulta"] is False


def test_extraer_requerimientos_crear_interconsulta_si(tmp_path: Path):
    """Trigger con bullet 'crear interconsulta' -> crear_interconsulta=True."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "---\n"
        "paciente: 'Test'\n"
        "---\n\n"
        "Anamnesis...\n\n"
        "** mortadelo\n\n"
        "- crear interconsulta\n\n"
        "**\n",
        encoding="utf-8",
    )
    resultado = _extraer_requerimientos(nota)
    assert resultado["crear_interconsulta"] is True
    assert resultado["examenes_adjuntos"] is False


def test_extraer_requerimientos_ambos_si(tmp_path: Path):
    """Trigger con ambos bullets -> ambos True."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "** mortadelo\n\n"
        "- examenes adjuntos\n"
        "- crear interconsulta\n\n"
        "**\n",
        encoding="utf-8",
    )
    resultado = _extraer_requerimientos(nota)
    assert resultado["examenes_adjuntos"] is True
    assert resultado["crear_interconsulta"] is True


def test_extraer_requerimientos_tildes_toleradas(tmp_path: Path):
    """'exámenes adjuntos' (con tilde) debe matchear (case-insensitive)."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "** mortadelo\n\n"
        "- Exámenes Adjuntos\n\n"
        "**\n",
        encoding="utf-8",
    )
    resultado = _extraer_requerimientos(nota)
    assert resultado["examenes_adjuntos"] is True


def test_extraer_requerimientos_crea_typo_tolerado(tmp_path: Path):
    """'crea interconsulta' (sin la 'r' final) debe matchear."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "** mortadelo\n\n"
        "- crea interconsulta a cardiologia\n\n"
        "**\n",
        encoding="utf-8",
    )
    resultado = _extraer_requerimientos(nota)
    assert resultado["crear_interconsulta"] is True


def test_extraer_requerimientos_sin_bullets_libre(tmp_path: Path):
    """Keyword en texto libre (no bullet) tambien debe matchear."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "** mortadelo: revisar examenes adjuntos del paciente\n",
        encoding="utf-8",
    )
    resultado = _extraer_requerimientos(nota)
    assert resultado["examenes_adjuntos"] is True


def test_extraer_requerimientos_multiples_triggers(tmp_path: Path):
    """Multiples triggers ** mortadelo: keywords se acumulan."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "** mortadelo\n\n- examenes adjuntos\n\n**\n\n"
        "...texto intermedio...\n\n"
        "** mortadelo\n\n- crear interconsulta\n\n**\n",
        encoding="utf-8",
    )
    resultado = _extraer_requerimientos(nota)
    assert resultado["examenes_adjuntos"] is True
    assert resultado["crear_interconsulta"] is True


def test_extraer_requerimientos_trigger_sin_keywords(tmp_path: Path):
    """Trigger presente pero sin keywords -> ambos False."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "** mortadelo: agrega el peso y la talla\n",
        encoding="utf-8",
    )
    resultado = _extraer_requerimientos(nota)
    assert resultado == {"examenes_adjuntos": False, "crear_interconsulta": False}


# ---------------------------------------------------------------------------
# _parsear_informe_basico() — back-compat 6/8 cols
# ---------------------------------------------------------------------------

def test_parser_acepta_6_columnas(tmp_path: Path):
    """Informe viejo con 6 columnas se parsea correctamente."""
    informe = tmp_path / "informe.txt"
    informe.write_text(
        "10-09-2026    Juan Perez    (-)    Control    (-)    CONTROL INTEGRAL SIN FICHA ANTERIOR\n",
        encoding="utf-8",
    )
    filas = _parsear_informe_basico(informe)
    assert len(filas) == 1
    assert filas[0]["fecha"] == "10-09-2026"
    assert filas[0]["nombre"] == "Juan Perez"
    assert "examenes_adjuntos" not in filas[0]  # no estan en formato viejo


def test_parser_acepta_8_columnas(tmp_path: Path):
    """Informe nuevo con 8 columnas parsea las 2 adicionales."""
    informe = tmp_path / "informe.txt"
    informe.write_text(
        "10-09-2026    Juan Perez    (-)    Control    (-)    CONTROL    si    no\n",
        encoding="utf-8",
    )
    filas = _parsear_informe_basico(informe)
    assert len(filas) == 1
    assert filas[0]["examenes_adjuntos"] == "si"
    assert filas[0]["crear_interconsulta"] == "no"


def test_parser_ignora_lineas_invalidas(tmp_path: Path):
    """Lineas con != 6 u 8 cols se ignoran. Lineas sin fecha dd-mm-yyyy tambien."""
    informe = tmp_path / "informe.txt"
    informe.write_text(
        "Header que se ignora\n"
        "-----------\n"
        "10-09-2026    Juan Perez    (-)    Control    (-)    CONTROL    si    no\n"
        "no es una fila valida\n"
        "x   y   z   w   v   u   t   s\n"  # 8 cols pero fecha invalida
        "10-09-2026    Maria Lopez    (-)    Control    (-)    CONTROL\n",  # 6 cols validas
        encoding="utf-8",
    )
    filas = _parsear_informe_basico(informe)
    assert len(filas) == 2
    assert filas[0]["nombre"] == "Juan Perez"
    assert filas[0]["examenes_adjuntos"] == "si"
    assert filas[1]["nombre"] == "Maria Lopez"


# ---------------------------------------------------------------------------
# _formatear_tabla() — incluye las 2 cols nuevas
# ---------------------------------------------------------------------------

def test_formatear_tabla_incluye_nuevas_columnas():
    """El header debe incluir 'Examenes adjuntos' y 'Crear interconsulta'."""
    filas = [
        {
            "fecha": "10-09-2026",
            "nombre": "Juan Perez",
            "edad": "(-) ",
            "tipo_atencion": "Control",
            "motivo": "(-) ",
            "plantilla": "CONTROL",
            "examenes_adjuntos": True,
            "crear_interconsulta": False,
        },
    ]
    out = _formatear_tabla(filas, "09-2026")
    assert "Examenes adjuntos" in out
    assert "Crear interconsulta" in out
    # Las celdas
    assert "si" in out  # examenes_adjuntos=True
    assert "no" in out  # crear_interconsulta=False


def test_formatear_tabla_renderiza_si_no():
    """Las celdas de las 2 cols nuevas son 'si'/'no' segun el bool."""
    filas_si = [
        {
            "fecha": "01-01-2026", "nombre": "A", "edad": "(-)", "tipo_atencion": "X",
            "motivo": "(-)", "plantilla": "Y",
            "examenes_adjuntos": True, "crear_interconsulta": True,
        },
        {
            "fecha": "02-01-2026", "nombre": "B", "edad": "(-)", "tipo_atencion": "X",
            "motivo": "(-)", "plantilla": "Y",
            "examenes_adjuntos": False, "crear_interconsulta": False,
        },
    ]
    out = _formatear_tabla(filas_si, "01-2026")
    # El primer paciente tiene ambos si; el segundo ambos no.
    # Verificamos que aparece "si" antes de "no" (orden de las filas).
    assert out.find("si") < out.find("no")


# ---------------------------------------------------------------------------
# KEYWORDS_REQUERIMIENTOS — sanity check
# ---------------------------------------------------------------------------

def test_keywords_tienen_2_claves():
    """El dict de keywords debe tener exactamente 2 keys: examenes_adjuntos y crear_interconsulta."""
    assert set(KEYWORDS_REQUERIMIENTOS.keys()) == {"examenes_adjuntos", "crear_interconsulta"}


def test_keywords_son_regex_compilados():
    """Los valores del dict deben ser objetos re.Pattern."""
    for v in KEYWORDS_REQUERIMIENTOS.values():
        assert isinstance(v, type(TRIGGER_RE)), f"{v} no es re.Pattern"