"""Tests para src/analysis/enriquecer_informe.py

Sesion 2026-09-16: agregar deteccion de requerimientos Yadira->Mortadelo
y actualizar el parser para aceptar 8 columnas (back-compat con 6).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.analysis.enriquecer_informe import (
    KEYWORDS_REQUERIMIENTOS,
    _edad_a_decimal,
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
    # Sesion 2026-09-16 17:26: el parser siempre setea las keys (con None
    # si no estan en el formato viejo), para que el main loop pueda
    # detectar que faltan y enriquecer.
    assert filas[0]["examenes_adjuntos"] is None
    assert filas[0]["crear_interconsulta"] is None
    assert filas[0]["edad_decimal"] is None


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


# ---------------------------------------------------------------------------
# _extraer_motivo() y _extraer_edad() — busqueda format-agnostic
# (sesion 2026-09-16: cambio de block-search a whole-file search para
# soportar tanto .md como .txt legacy)
# ---------------------------------------------------------------------------

from src.analysis.enriquecer_informe import _extraer_motivo, _extraer_edad


def test_extraer_motivo_md_bullet_bold(tmp_path: Path):
    """Formato .md: `- **Motivo de atencion:** control sm`"""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "---\n"
        "paciente: 'Test'\n"
        "---\n\n"
        "# Nota clinica\n\n"
        "## Identificacion\n\n"
        "- **Edad Cronologica:** 40 anos\n\n"
        "## Nota clinica de Yadira\n\n"
        "- **Motivo de atencion:** control sm\n\n"
        "Anamnesis...\n",
        encoding="utf-8",
    )
    assert _extraer_motivo(nota) == "control sm"


def test_extraer_motivo_md_blockquote_bold(tmp_path: Path):
    """Formato .md blockquote: `> **Motivo de atencion:** control sm`"""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "> **Motivo de atencion:** control integral g3\n",
        encoding="utf-8",
    )
    assert _extraer_motivo(nota) == "control integral g3"


def test_extraer_motivo_md_bullet_sin_bold_en_label(tmp_path: Path):
    """Formato .md sin bold en label (variante): `- Motivo de atencion: x`"""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "- Motivo de atencion: reingreso sm\n",
        encoding="utf-8",
    )
    assert _extraer_motivo(nota) == "reingreso sm"


def test_extraer_motivo_txt_legacy(tmp_path: Path):
    """Formato .txt legacy: `Motivo de atencion: x` (sin marcadores ===)"""
    nota = tmp_path / "paciente.txt"
    nota.write_text(
        "=== INICIO NOTA CLINICA DE YADIRA ===\n"
        "Motivo de atencion: control sm\n"
        "Anamnesis: ...\n"
        "=== FIN NOTA CLINICA DE YADIRA ===\n",
        encoding="utf-8",
    )
    assert _extraer_motivo(nota) == "control sm"


def test_extraer_motivo_con_tildes(tmp_path: Path):
    """'atenci\u00f3n' (con tilde) debe matchear igual que sin tilde."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "- **Motivo de atención:** control integral\n",
        encoding="utf-8",
    )
    assert _extraer_motivo(nota) == "control integral"


def test_extraer_motivo_valor_con_bold_inicial(tmp_path: Path):
    """Si el valor empieza con `**` (Yadira uso bold), debe saltarselo."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "> **Motivo de atencion:** ** control sm\n",
        encoding="utf-8",
    )
    assert _extraer_motivo(nota) == "control sm"


def test_extraer_motivo_sin_campo(tmp_path: Path):
    """Nota sin el campo -> None."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "---\n"
        "paciente: 'Test'\n"
        "---\n\n"
        "Anamnesis sin motivo.\n",
        encoding="utf-8",
    )
    assert _extraer_motivo(nota) is None


def test_extraer_motivo_sin_nota(tmp_path: Path):
    """Si la nota no existe -> None."""
    nota = tmp_path / "no_existe.md"
    assert _extraer_motivo(nota) is None


def test_extraer_edad_md_bullet_bold(tmp_path: Path):
    """Formato .md: `- **Edad Cronologica:** 40 anos 2 meses 30 dias`"""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "## Identificacion\n\n"
        "- **Edad Cronologica:** 40 anos 2 meses 30 dias\n"
        "- **RUN:** 12345\n",
        encoding="utf-8",
    )
    assert _extraer_edad(nota) == "40 anos 2 meses 30 dias"


def test_extraer_edad_md_bullet_bold_con_tilde(tmp_path: Path):
    """Tildes en el label: 'Cronol\u00f3gica'."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "- **Edad Cronológica:** 19 años 2 meses 10 días\n",
        encoding="utf-8",
    )
    assert _extraer_edad(nota) == "19 años 2 meses 10 días"


def test_extraer_edad_sin_tilde_en_label(tmp_path: Path):
    """Sin tilde en el label (variante OCR/encoding)."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "- **Edad Cronologica:** 67 anos 9 meses 15 dias\n",
        encoding="utf-8",
    )
    assert _extraer_edad(nota) == "67 anos 9 meses 15 dias"


def test_extraer_edad_txt_legacy(tmp_path: Path):
    """Formato .txt legacy: 'Edad Cronologica: x' (sin marcadores ===)."""
    nota = tmp_path / "paciente.txt"
    nota.write_text(
        "=== INICIO IDENTIFICACION ===\n"
        "Edad Cronologica: 40 anos\n"
        "RUN: 12345\n"
        "=== FIN IDENTIFICACION ===\n",
        encoding="utf-8",
    )
    assert _extraer_edad(nota) == "40 anos"


def test_extraer_edad_sin_campo(tmp_path: Path):
    """Nota sin el campo -> None."""
    nota = tmp_path / "paciente.md"
    nota.write_text(
        "---\n"
        "paciente: 'Test'\n"
        "---\n\n"
        "Sin edad.\n",
        encoding="utf-8",
    )
    assert _extraer_edad(nota) is None


def test_extraer_edad_sin_nota(tmp_path: Path):
    """Si la nota no existe -> None."""
    nota = tmp_path / "no_existe.md"
    assert _extraer_edad(nota) is None


# ---------------------------------------------------------------------------
# Smoke test end-to-end: enriquecimiento real sobre notas de prueba
# ---------------------------------------------------------------------------

def test_enriquecer_extrae_motivo_y_edad_de_nota_real():
    """Smoke test: con una nota que tenga ambos campos, motivo y edad
    deben extraerse correctamente."""
    import tempfile
    import os
    from src.analysis.enriquecer_informe import (
        _safe_filename, _extraer_motivo, _extraer_edad,
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(
            "---\n"
            "paciente: 'Paciente Smoke Test'\n"
            "---\n\n"
            "# Nota clinica - Paciente Smoke Test\n\n"
            "## Identificacion\n\n"
            "- **RUN:** 12345678-9\n"
            "- **Edad Cronológica:** 45 años 6 meses 12 días\n\n"
            "## Nota clinica de Yadira\n\n"
            "> **Motivo de atencion:** ** control integral\n\n"
            "Anamnesis del paciente...\n"
        )
        tmp_path_str = f.name
    try:
        nota = Path(tmp_path_str)
        assert _extraer_motivo(nota) == "control integral"
        assert _extraer_edad(nota) == "45 años 6 meses 12 días"
    finally:
        os.unlink(tmp_path_str)


# ---------------------------------------------------------------------------
# _edad_a_decimal() — sesion 2026-09-16 17:26 (pedido por Yadira)
# ---------------------------------------------------------------------------

def test_edad_a_decimal_caso_canonico():
    """'19 anios 2 meses 10 dias' -> '19,19'."""
    assert _edad_a_decimal("19 anios 2 meses 10 dias") == "19,19"


def test_edad_a_decimal_con_tildes():
    """Acepta 'años' (con tilde)."""
    assert _edad_a_decimal("19 años 2 meses 10 días") == "19,19"


def test_edad_a_decimal_sin_meses():
    """Sin meses, solo anos: '67 años' -> '67,00'."""
    assert _edad_a_decimal("67 años") == "67,00"


def test_edad_a_decimal_sin_dias():
    """Sin dias: '40 años 6 meses' -> '40,50'."""
    # 40 + 6/12 + 0/365.25 = 40.5 -> 40,50
    assert _edad_a_decimal("40 años 6 meses") == "40,50"


def test_edad_a_decimal_sin_tildes_en_label():
    """OCR variante sin tildes en 'anos'/'dias'."""
    # 17 + 4/12 + 12/365.25 = 17 + 0.3333 + 0.0328 = 17.3662 -> 17,37
    assert _edad_a_decimal("17 anos 4 meses 12 dias") == "17,37"


def test_edad_a_decimal_singular():
    """Acepta singular: '1 ano 1 mes 1 dia'."""
    # 1 + 1/12 + 1/365.25 = 1 + 0.0833 + 0.0027 = 1.0861 -> 1,09
    assert _edad_a_decimal("1 ano 1 mes 1 dia") == "1,09"


def test_edad_a_decimal_decimal_grande():
    """Decimal > 99 funciona (3 digitos)."""
    # 100 + 0/12 + 0/365.25 = 100 -> 100,00
    assert _edad_a_decimal("100 anos") == "100,00"


def test_edad_a_decimal_formato_invalido():
    """Si no matchea el patron, devuelve None."""
    assert _edad_a_decimal("foobar") is None
    assert _edad_a_decimal("") is None


def test_edad_a_decimal_strip_whitespace():
    """Strip whitespace alrededor."""
    assert _edad_a_decimal("  19 anos 2 meses 10 dias  ") == "19,19"


def test_edad_a_decimal_precision_2_decimales():
    """El formato es exactamente 2 decimales con coma."""
    result = _edad_a_decimal("19 anos 2 meses 10 dias")
    assert result is not None
    # '19,19' tiene exactamente 2 decimales despues de la coma
    parte_decimal = result.split(",")[1]
    assert len(parte_decimal) == 2


# ---------------------------------------------------------------------------
# Parser con 9 columnas (sesion 2026-09-16 17:26)
# ---------------------------------------------------------------------------

def test_parser_acepta_9_columnas_con_decimal(tmp_path: Path):
    """Informe nuevo (9 cols) parsea edad_decimal correctamente."""
    informe = tmp_path / "informe.txt"
    informe.write_text(
        "10-09-2026    Juan Perez    40 anos 2 meses 10 dias    40,19    Control    control sm    CONTROL    no    no\n",
        encoding="utf-8",
    )
    filas = _parsear_informe_basico(informe)
    assert len(filas) == 1
    assert filas[0]["edad"] == "40 anos 2 meses 10 dias"
    assert filas[0]["edad_decimal"] == "40,19"
    assert filas[0]["examenes_adjuntos"] == "no"
    assert filas[0]["crear_interconsulta"] == "no"


def test_parser_acepta_8_columnas_sin_decimal(tmp_path: Path):
    """Informe intermedio (8 cols, version 16:30) sin decimal."""
    informe = tmp_path / "informe.txt"
    informe.write_text(
        "10-09-2026    Juan Perez    40 anos    Control    control sm    CONTROL    no    no\n",
        encoding="utf-8",
    )
    filas = _parsear_informe_basico(informe)
    assert len(filas) == 1
    assert filas[0]["edad"] == "40 anos"
    assert filas[0]["edad_decimal"] is None  # se calcula despues


def test_formatear_incluye_columna_edad_decimal():
    """_formatear_tabla debe incluir la nueva columna 'Edad (anios)'."""
    filas = [
        {
            "fecha": "10-09-2026", "nombre": "Juan",
            "edad": "19 anos 2 meses 10 dias", "edad_decimal": "19,19",
            "tipo_atencion": "Control", "motivo": "control sm",
            "plantilla": "CONTROL",
            "examenes_adjuntos": True, "crear_interconsulta": False,
        },
    ]
    out = _formatear_tabla(filas, "09-2026")
    assert "Edad (anios)" in out
    assert "19,19" in out