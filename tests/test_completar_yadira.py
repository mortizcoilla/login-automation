"""Tests para completar_yadira.py (skeleton LLM, no requiere API real).

Sesion 2026-09-16 (corregido 13:42): el bloque Yadira contiene la
anamnesis CRUDA de Yadira (no un placeholder). El script lee esa
anamnesis, la pasa al LLM con instrucciones de enriquecerla, y reemplaza
el bloque con la version enriquecida en `notas_clinicas_completadas/`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.tools.completar_yadira import (
    NOTAS_COMPLETADAS_DIR,
    construir_prompt,
    insertar_bloque_yadira,
    leer_bloques_nota,
)


# Anamnesis cruda que Yadira escribio en Rayen al abrir la ficha.
# Es el INSUMO PRINCIPAL del flujo (regla Yadira 2026-09-16).
ANAMNESIS_CRUDA_EJEMPLO = """\
Paciente consulta por control de su hipertension arterial cronica. \
Refiere adherencia al tratamiento farmacologico. Sin sintomas \
cardiovasculares nuevos. Niega cefalea, mareos, disnea, dolor toracico.\
"""

NOTA_MD_EJEMPLO = f"""---
paciente: "Maria Lopez"
title: "Nota clinica - Maria Lopez"
fecha_atencion: "14-09-2026"
fuente: "Rayen APS - CESFAM Raul Cuevas, San Bernardo"
source_url: "https://clinico.rayenaps.cl/"
fecha_extraccion: "2026-09-16T03:00:00"
panel_cargo: "true"
---

# Nota clinica - Maria Lopez

## Identificacion

- **RUN:** 12.345.678-9
- **Edad:** 45 años

## Historial de atenciones (ultimos 6 meses)

10-09-2026: control previo

## Nota clinica de Yadira

> **Motivo de atencion:** Control de HTA

{ANAMNESIS_CRUDA_EJEMPLO}

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

    def test_bloque_yadira_contiene_anamnesis_cruda(self) -> None:
        # Regla dura Yadira 2026-09-16: el bloque Yadira contiene la
        # anamnesis cruda que Yadira lleno en Rayen. Es el insumo
        # principal del flujo de enriquecimiento.
        bloques = leer_bloques_nota(NOTA_MD_EJEMPLO)
        contenido = bloques["Nota clinica de Yadira"]
        assert "> **Motivo de atencion:** Control de HTA" in contenido
        assert "control de su hipertension arterial cronica" in contenido
        assert "Adherencia al tratamiento" in contenido or "adherencia al tratamiento" in contenido


# ---------------------------------------------------------------------------
# construir_prompt
# ---------------------------------------------------------------------------
class TestConstruirPrompt:
    def test_prompt_incluye_anamnesis_como_insumo_principal(self) -> None:
        # Regla Yadira 2026-09-16: la anamnesis de Yadira es el insumo
        # principal. El prompt debe contenerla explicitamente para que
        # el LLM la enriquezca (no la genere de cero).
        bloques = {"Nota clinica de Yadira": ANAMNESIS_CRUDA_EJEMPLO}
        prompt = construir_prompt(
            bloques=bloques,
            manuales_disponibles=["minsal-ECICEP"],
            paciente_dict={"paciente": "Maria Lopez"},
        )
        assert "INSUMO PRINCIPAL" in prompt
        assert "ANAMNESIS CRUDA" in prompt
        assert ANAMNESIS_CRUDA_EJEMPLO in prompt

    def test_incluye_secciones_de_datos_y_contexto(self) -> None:
        prompt = construir_prompt(
            bloques={
                "Nota clinica de Yadira": "x",
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
        assert "ENRIQUECER" in prompt.upper()
        assert "MANUALES DISPONIBLES" in prompt

    def test_incluye_datos_del_paciente(self) -> None:
        prompt = construir_prompt(
            bloques={"Nota clinica de Yadira": "x"},
            manuales_disponibles=[],
            paciente_dict={"paciente": "Juan Perez", "run": "1-9"},
        )
        assert "**paciente:** Juan Perez" in prompt
        assert "**run:** 1-9" in prompt

    def test_lista_manuales_disponibles_para_citar(self) -> None:
        prompt = construir_prompt(
            bloques={"Nota clinica de Yadira": "x"},
            manuales_disponibles=["minsal-ECICEP", "guia-HTA"],
            paciente_dict={},
        )
        assert "- minsal-ECICEP" in prompt
        assert "- guia-HTA" in prompt

    def test_indica_formato_de_cita(self) -> None:
        prompt = construir_prompt(
            bloques={"Nota clinica de Yadira": "x"},
            manuales_disponibles=[],
            paciente_dict={},
        )
        # El prompt debe ensenar al LLM como citar manuales.
        assert "manual:" in prompt and "p." in prompt

    def test_incluye_instrucciones_para_usar_internet(self) -> None:
        prompt = construir_prompt(
            bloques={"Nota clinica de Yadira": "x"},
            manuales_disponibles=[],
            paciente_dict={},
        )
        assert "internet" in prompt.lower() or "webfetch" in prompt.lower()

    def test_instrucciones_enriquecer_no_completar(self) -> None:
        # Regla Yadira 2026-09-16: el LLM enriquece la anamnesis, no
        # la genera desde cero. Prompt debe decirlo explicitamente.
        prompt = construir_prompt(
            bloques={"Nota clinica de Yadira": "x"},
            manuales_disponibles=[],
            paciente_dict={},
        )
        # Debe aparecer la instruccion de enriquecer (no solo completar).
        assert "enriquec" in prompt.lower()

    def test_incluye_secciones_de_bloques_en_orden(self) -> None:
        prompt = construir_prompt(
            bloques={
                "Nota clinica de Yadira": "x",
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
    def test_reemplaza_anamnesis_cruda_por_contenido_enriquecido(self) -> None:
        # El LLM entrega el contenido enriquecido. La funcion lo
        # inserta en lugar de la anamnesis cruda original.
        contenido_enriquecido = (
            "Paciente hipertensa cronica en control. Adherencia al "
            "tratamiento farmacologico. Asintomatica cardiovascular. "
            "[manual: minsal-ECICEP, p.42]"
        )
        resultado = insertar_bloque_yadira(
            NOTA_MD_EJEMPLO, contenido_enriquecido
        )
        # La anamnesis cruda ya no esta (fue reemplazada).
        assert "control de su hipertension arterial cronica" not in resultado
        # El contenido enriquecido SI esta.
        assert "Paciente hipertensa cronica en control" in resultado
        assert "[manual: minsal-ECICEP, p.42]" in resultado

    def test_preserva_motivo_consulta_como_blockquote(self) -> None:
        resultado = insertar_bloque_yadira(
            NOTA_MD_EJEMPLO, "contenido enriquecido"
        )
        # El motivo va como blockquote antes del contenido enriquecido.
        idx_motivo = resultado.index("> **Motivo de atencion:**")
        idx_contenido = resultado.index("contenido enriquecido")
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
            f"## Nota clinica de Yadira\n\n> **Motivo de atencion:** Control de HTA\n\n{ANAMNESIS_CRUDA_EJEMPLO}\n",
            "",
        )
        assert "## Nota clinica de Yadira" not in nota_sin_bloque
        with pytest.raises(ValueError, match="Nota clinica de Yadira"):
            insertar_bloque_yadira(nota_sin_bloque, "x")


# ---------------------------------------------------------------------------
# NOTAS_COMPLETADAS_DIR exportado
# ---------------------------------------------------------------------------
def test_notas_completadas_dir_es_path() -> None:
    assert isinstance(NOTAS_COMPLETADAS_DIR, Path)
    assert NOTAS_COMPLETADAS_DIR.name == "notas_clinicas_completadas"
