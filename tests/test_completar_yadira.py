"""Tests para completar_yadira.py (skeleton LLM, no requiere API real)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.tools.completar_yadira import (
    NOTAS_COMPLETADAS_DIR,
    PLACEHOLDER,
    construir_prompt,
    insertar_bloque_yadira,
    leer_bloques_nota,
)


NOTA_MD_EJEMPLO = """---
paciente: "Maria Lopez"
title: "Nota clinica - Maria Lopez"
fecha_atencion: "14-09-2026"
fuente: "Rayen APS - CESFAM Raul Cuevas, San Bernardo"
source_url: "https://clinico.rayenaps.cl/"
fecha_extraccion: "2026-09-16T03:00:00"
panel_cargo: "false"
---

# Nota clinica - Maria Lopez

## Identificacion

- **RUN:** 12.345.678-9
- **Edad:** 45 años

## Historial de atenciones (ultimos 6 meses)

10-09-2026: control previo

## Nota clinica de Yadira

> **Motivo de atencion:** Control de HTA

_(bloque a completar por el LLM en `notas_clinicas_completadas/`)_

## Diagnosticos

- I10X Hipertension esencial

## Actividades

- Control de presion arterial
"""


# ---------------------------------------------------------------------------
# leer_bloques_nota
# ---------------------------------------------------------------------------
class TestLeerBloquesNota:
    def test_separa_bloques_por_header(self) -> None:
        bloques = leer_bloques_nota(NOTA_MD_EJEMPLO)
        assert "Identificacion" in bloques
        assert "Historial de atenciones (ultimos 6 meses)" in bloques
        assert "Nota clinica de Yadira" in bloques
        assert "Diagnosticos" in bloques
        assert "Actividades" in bloques

    def test_ignora_frontmatter(self) -> None:
        bloques = leer_bloques_nota(NOTA_MD_EJEMPLO)
        # paciente / title / etc NO son bloques.
        assert "paciente" not in bloques

    def test_contenido_bloque_preserva_bullets(self) -> None:
        bloques = leer_bloques_nota(NOTA_MD_EJEMPLO)
        assert "- **RUN:** 12.345.678-9" in bloques["Identificacion"]

    def test_bloque_con_motivo_y_placeholder(self) -> None:
        bloques = leer_bloques_nota(NOTA_MD_EJEMPLO)
        contenido = bloques["Nota clinica de Yadira"]
        assert "> **Motivo de atencion:** Control de HTA" in contenido
        assert PLACEHOLDER in contenido


# ---------------------------------------------------------------------------
# construir_prompt
# ---------------------------------------------------------------------------
class TestConstruirPrompt:
    def test_incluye_secciones_de_datos_y_contexto(self) -> None:
        prompt = construir_prompt(
            bloques={
                "Identificacion": "- RUN: 1-1",
                "Diagnosticos": "- HTA",
                "Actividades": "- Control",
            },
            manuales_disponibles=["minsal-ECICEP"],
            paciente_dict={"paciente": "Test"},
        )
        assert "# TAREA" in prompt
        assert "DATOS DEMOGRAFICOS" in prompt
        assert "# BLOQUES YA EXTRAIDOS" in prompt
        assert "INSTRUCCIONES PARA COMPLETAR" in prompt
        assert "MANUALES DISPONIBLES" in prompt

    def test_incluye_datos_del_paciente(self) -> None:
        prompt = construir_prompt(
            bloques={},
            manuales_disponibles=[],
            paciente_dict={"paciente": "Juan Perez", "run": "1-9"},
        )
        assert "**paciente:** Juan Perez" in prompt
        assert "**run:** 1-9" in prompt

    def test_lista_manuales_disponibles_para_citar(self) -> None:
        prompt = construir_prompt(
            bloques={},
            manuales_disponibles=["minsal-ECICEP", "guia-HTA"],
            paciente_dict={},
        )
        assert "- minsal-ECICEP" in prompt
        assert "- guia-HTA" in prompt

    def test_indica_formato_de_cita(self) -> None:
        # El prompt debe ense\u00f1ar al LLM como citar manuales.
        prompt = construir_prompt(
            bloques={}, manuales_disponibles=[], paciente_dict={}
        )
        assert "[\U0001f9e0 manual: minsal-ECICEP, p.42]" in prompt

    def test_incluye_instrucciones_para_usar_internet(self) -> None:
        # El LLM debe saber que puede buscar en internet (decidido en sesion
        # 2026-09-15: webfetch/websearch permitido en fuentes confiables).
        prompt = construir_prompt(
            bloques={}, manuales_disponibles=[], paciente_dict={}
        )
        assert "internet" in prompt.lower() or "webfetch" in prompt.lower()

    def test_incluye_secciones_de_bloques_en_orden(self) -> None:
        prompt = construir_prompt(
            bloques={
                "Identificacion": "i",
                "Diagnosticos": "d",
                "Actividades": "a",
                "Historial de atenciones (ultimos 6 meses)": "h",
            },
            manuales_disponibles=[],
            paciente_dict={},
        )
        # Orden esperado: Identificacion < Historial < Diagnosticos < Actividades.
        idx_id = prompt.index("## Identificacion")
        idx_hist = prompt.index("## Historial")
        idx_diag = prompt.index("## Diagnosticos")
        idx_act = prompt.index("## Actividades")
        assert idx_id < idx_hist
        assert idx_hist < idx_diag
        assert idx_diag < idx_act


# ---------------------------------------------------------------------------
# insertar_bloque_yadira
# ---------------------------------------------------------------------------
class TestInsertarBloqueYadira:
    def test_reemplaza_placeholder_por_contenido(self) -> None:
        contenido_yadira = (
            "Paciente consulta por control. Sin sintomas.\n"
            "Examen fisico: PA 130/85, FC 78."
        )
        resultado = insertar_bloque_yadira(NOTA_MD_EJEMPLO, contenido_yadira)
        assert PLACEHOLDER not in resultado
        assert "Paciente consulta por control" in resultado
        assert "PA 130/85, FC 78" in resultado

    def test_preserva_motivo_consulta_como_blockquote(self) -> None:
        contenido = "Anamnesis aqui"
        resultado = insertar_bloque_yadira(NOTA_MD_EJEMPLO, contenido)
        # El motivo va como blockquote antes del contenido del LLM.
        idx_motivo = resultado.index("> **Motivo de atencion:**")
        idx_contenido = resultado.index("Anamnesis aqui")
        assert idx_motivo < idx_contenido

    def test_preserva_demografia_y_otros_bloques(self) -> None:
        resultado = insertar_bloque_yadira(NOTA_MD_EJEMPLO, "anamesis X")
        # Identificacion, historial, diagnosticos, actividades deben seguir.
        assert "## Identificacion" in resultado
        assert "## Historial de atenciones" in resultado
        assert "## Diagnosticos" in resultado
        assert "## Actividades" in resultado
        assert "- **RUN:** 12.345.678-9" in resultado
        assert "- I10X Hipertension esencial" in resultado

    def test_preserva_header_del_bloque(self) -> None:
        resultado = insertar_bloque_yadira(NOTA_MD_EJEMPLO, "contenido X")
        assert "## Nota clinica de Yadira" in resultado

    def test_error_si_no_hay_bloque(self) -> None:
        nota_sin_bloque = NOTA_MD_EJEMPLO.replace(
            "## Nota clinica de Yadira\n\n> **Motivo de atencion:** Control de HTA\n\n"
            "_(bloque a completar por el LLM en `notas_clinicas_completadas/`)_\n",
            "",
        )
        assert "## Nota clinica de Yadira" not in nota_sin_bloque
        with pytest.raises(ValueError, match="placeholder"):
            insertar_bloque_yadira(nota_sin_bloque, "x")


# ---------------------------------------------------------------------------
# NOTAS_COMPLETADAS_DIR y PLACEHOLDER exportados
# ---------------------------------------------------------------------------
def test_notas_completadas_dir_es_path() -> None:
    assert isinstance(NOTAS_COMPLETADAS_DIR, Path)
    assert NOTAS_COMPLETADAS_DIR.name == "notas_clinicas_completadas"

def test_placeholder_es_string_no_vacio() -> None:
    assert isinstance(PLACEHOLDER, str)
    assert "LLM" in PLACEHOLDER
    assert "notas_clinicas_completadas" in PLACEHOLDER