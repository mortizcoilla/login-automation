"""Tests para la conversion de notas_clinicas/*.txt a *.md."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.tools.convertir_notas_md import (
    BLOQUES_HEADERS,
    bloque_a_markdown,
    nota_a_markdown,
    parsear_nota_txt,
)


NOTA_TXT_EJEMPLO = """\
# NOTA CLINICA — extraida de Rayen
# Paciente: Maria Lopez
# Fecha atencion: 14-09-2026

!!! ATENCION: panel del paciente NO CARGO en Rayen.
!!! La nota tiene placeholders. Revisar manualmente en Rayen.

======================================================================
=== INICIO IDENTIFICACION ===
======================================================================
RUN: 12.345.678-9
Edad: 45 años
======================================================================
=== FIN IDENTIFICACION ===
======================================================================

======================================================================
=== INICIO HISTORIAL DE ATENCIONES ===
======================================================================
10-09-2026: control previo
01-08-2026: consulta inicial
======================================================================
=== FIN HISTORIAL DE ATENCIONES ===
======================================================================

======================================================================
=== INICIO NOTA CLINICA DE YADIRA ===
======================================================================

Motivo de atencion: Control de HTA

Paciente consulta por control de hipertension. Sin sintomas.
======================================================================
=== FIN NOTA CLINICA DE YADIRA ===
======================================================================

======================================================================
=== INICIO DIAGNOSTICOS ===
======================================================================
- I10X Hipertension esencial
- E78.5 Hiperlipidemia
======================================================================
=== FIN DIAGNOSTICOS ===
======================================================================

======================================================================
=== INICIO ACTIVIDADES ===
======================================================================
Control de presion arterial
Solicitud de examenes
======================================================================
=== FIN ACTIVIDADES ===
======================================================================

======================================================================
=== INICIO PLAN RECETAS ===
======================================================================
Losartan 50mg, 1 comp cada 12h, 30 dias
Atorvastatina 20mg, 1 comp en la noche, 30 dias
======================================================================
=== FIN PLAN RECETAS ===
======================================================================
"""


# ---------------------------------------------------------------------------
# parsear_nota_txt
# ---------------------------------------------------------------------------
class TestParsearNotaTxt:
    def test_extrae_frontmatter_basico(self) -> None:
        result = parsear_nota_txt(NOTA_TXT_EJEMPLO)
        assert result["frontmatter"]["paciente"] == "Maria Lopez"
        assert result["frontmatter"]["fecha_atencion"] == "14-09-2026"

    def test_genera_title_desde_paciente(self) -> None:
        result = parsear_nota_txt(NOTA_TXT_EJEMPLO)
        assert result["frontmatter"]["title"] == "Nota clinica - Maria Lopez"

    def test_detecta_bloques(self) -> None:
        result = parsear_nota_txt(NOTA_TXT_EJEMPLO)
        bloques = result["bloques"]
        assert "IDENTIFICACION" in bloques
        assert "HISTORIAL DE ATENCIONES" in bloques
        assert "NOTA CLINICA" in bloques
        assert "DIAGNOSTICOS" in bloques
        assert "ACTIVIDADES" in bloques
        assert "PLAN RECETAS" in bloques

    def test_bloque_identificacion_con_pares_clave_valor(self) -> None:
        result = parsear_nota_txt(NOTA_TXT_EJEMPLO)
        # Las lineas del bloque estan en orden, sin los marcadores.
        lineas = result["bloques"]["IDENTIFICACION"]
        assert "RUN: 12.345.678-9" in lineas
        assert "Edad: 45 años" in lineas


# ---------------------------------------------------------------------------
# bloque_a_markdown
# ---------------------------------------------------------------------------
class TestBloqueAMarkdown:
    def test_bloque_identificacion_como_bullets_clave_valor(self) -> None:
        lineas = ["RUN: 12.345.678-9", "Edad: 45 años"]
        md = bloque_a_markdown("IDENTIFICACION", lineas)
        assert "## Identificacion" in md
        assert "- **RUN:** 12.345.678-9" in md
        assert "- **Edad:** 45 años" in md

    def test_bloque_actividades_como_bullets(self) -> None:
        lineas = ["Control de presion", "Examenes"]
        md = bloque_a_markdown("ACTIVIDADES", lineas)
        assert "## Actividades" in md
        assert "- Control de presion" in md
        assert "- Examenes" in md

    def test_bloque_placeholder_vacio(self) -> None:
        # Sin lineas -> string vacio (la seccion se omite en el output).
        md = bloque_a_markdown("ACTIVIDADES", [])
        assert md == ""

    def test_bloque_placeholder_sin_items(self) -> None:
        # Lineas tipo "(sin X)" -> italic note al pie.
        md = bloque_a_markdown("ACTIVIDADES", ["(sin actividades)"])
        assert "_(sin actividades)_" in md

    def test_nota_clinica_con_motivo_como_blockquote(self) -> None:
        lineas = ["Motivo de atencion: Control", "Cuerpo de la nota"]
        md = bloque_a_markdown("NOTA CLINICA", lineas)
        assert "> **Motivo de atencion:** Control" in md
        assert "Cuerpo de la nota" in md

    def test_nota_clinica_sin_motivo(self) -> None:
        md = bloque_a_markdown("NOTA CLINICA", ["Solo el cuerpo"])
        assert "> **Motivo de atencion" not in md
        assert "Solo el cuerpo" in md


# ---------------------------------------------------------------------------
# nota_a_markdown (integracion)
# ---------------------------------------------------------------------------
class TestNotaAMarkdown:
    def test_genera_markdown_completo(self) -> None:
        md = nota_a_markdown(NOTA_TXT_EJEMPLO, fecha_extraccion="2026-09-16T02:00:00")
        # Frontmatter.
        assert md.startswith("---\n")
        assert 'paciente: "Maria Lopez"' in md
        assert 'fecha_atencion: "14-09-2026"' in md
        assert 'panel_cargo: "false"' in md
        # Titulo.
        assert "# Nota clinica - Maria Lopez" in md
        # Flag de panel.
        assert "panel del paciente NO CARGO" in md
        # Headers.
        for h in [
            "## Identificacion",
            "## Historial de atenciones",
            "## Nota clinica de Yadira",
            "## Diagnosticos",
            "## Actividades",
            "## Plan - Recetas",
        ]:
            assert h in md
        # Datos del paciente.
        assert "- **RUN:** 12.345.678-9" in md
        # Motivo como blockquote.
        assert "> **Motivo de atencion:** Control de HTA" in md

    def test_panel_cargo_true_sin_flag(self) -> None:
        nota_sin_flag = NOTA_TXT_EJEMPLO.replace(
            "!!! ATENCION: panel del paciente NO CARGO en Rayen.",
            "",
        ).replace(
            "!!! La nota tiene placeholders. Revisar manualmente en Rayen.",
            "",
        )
        md = nota_a_markdown(nota_sin_flag)
        assert 'panel_cargo: "true"' in md
        assert "panel del paciente NO CARGO" not in md

    def test_incluye_fuente_y_source_url(self) -> None:
        md = nota_a_markdown(NOTA_TXT_EJEMPLO)
        assert 'fuente: "Rayen APS - CESFAM Raul Cuevas, San Bernardo"' in md
        assert 'source_url: "https://clinico.rayenaps.cl/"' in md

    def test_incluye_fecha_extraccion_si_se_pasa(self) -> None:
        md = nota_a_markdown(NOTA_TXT_EJEMPLO, fecha_extraccion="2026-09-16T12:34:56")
        assert 'fecha_extraccion: "2026-09-16T12:34:56"' in md

    def test_no_incluye_fecha_extraccion_si_no_se_pasa(self) -> None:
        md = nota_a_markdown(NOTA_TXT_EJEMPLO)
        assert "fecha_extraccion" not in md

    def test_paciente_rayen_en_frontmatter(self) -> None:
        nota_con_rayen = """\
# NOTA CLINICA — extraida de Rayen
# Paciente: Maria L
# Paciente (Rayen): Maria Lopez Garcia
# Fecha atencion: 14-09-2026

======================================================================
=== INICIO IDENTIFICACION ===
======================================================================
RUN: 1-1
======================================================================
=== FIN IDENTIFICACION ===
======================================================================
"""
        md = nota_a_markdown(nota_con_rayen)
        assert 'paciente: "Maria L"' in md
        assert 'paciente_rayen: "Maria Lopez Garcia"' in md