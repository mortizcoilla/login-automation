"""Tests del PCIC: pedido en el bloque ** mortadelo, insumo al LLM y
colocacion en la ficha (REQ-103).

La suite nunca llama a la API real.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from src.mortadelo.ensamblador import ensamblar_ficha
from src.mortadelo.generar import cargar_pcic_base, detectar_pedidos
from src.mortadelo.prompt import Pedidos, construir_prompt_ficha


def _base_con_trigger(trigger: str) -> str:
    return f"> Control\n\nAnamnesis:\n   - dato\n\n{trigger}\n"


class TestDeteccionPedidoPcic:
    def test_generar_pcic(self) -> None:
        p = detectar_pedidos(_base_con_trigger("** Mortadelo\n- generar PCIC\n\n**"))
        assert p.pcic is True

    def test_variantes(self) -> None:
        for frase in ("- hacer PCIC", "- Generar el pcic", "- PCIC", "- GENERA PCIC"):
            p = detectar_pedidos(_base_con_trigger(f"** Mortadelo\n{frase}\n\n**"))
            assert p.pcic is True, frase

    def test_bloque_sin_pcic(self) -> None:
        p = detectar_pedidos(
            _base_con_trigger("** Mortadelo\n- examenes adjuntos\n- crear interconsulta\n\n**")
        )
        assert p.pcic is False

    def test_sin_bloque(self) -> None:
        assert detectar_pedidos("> Control\n\nAnamnesis:\n   - dato").pcic is False


class TestCargarPcicBase:
    def test_lee_la_ruta_configurada(self, tmp_path: Path, monkeypatch) -> None:
        base = tmp_path / "pcic_base.txt"
        base.write_text("1) Objetivo: <CUSTOMIZAR>\n2) Opciones: x", encoding="utf-8")
        from src.core import rutas

        monkeypatch.setattr(rutas, "PCIC_BASE_PATH", base)
        texto = cargar_pcic_base(logging.getLogger("t"))
        assert texto is not None and "CUSTOMIZAR" in texto

    def test_archivo_ausente_devuelve_none(self, tmp_path: Path, monkeypatch, caplog) -> None:
        from src.core import rutas

        monkeypatch.setattr(rutas, "PCIC_BASE_PATH", tmp_path / "no-existe.txt")
        with caplog.at_level(logging.WARNING):
            assert cargar_pcic_base(logging.getLogger("t")) is None
        assert "PCIC_BASE_PATH" in caplog.text


class TestPromptPcic:
    PROMPT_ARGS = dict(
        paciente="Juan Perez",
        fecha="10-09-2026",
        base_anamnesis="> Control\nAnamnesis:\n   - dato",
        info_paciente="Edad: 50",
        examenes=None,
    )

    def test_con_pedido_incluye_insumo_y_regla(self) -> None:
        prompt = construir_prompt_ficha(
            **self.PROMPT_ARGS,
            pedidos=Pedidos(pcic=True, trigger_texto="- generar PCIC"),
            pcic_base="1) Objetivo: <CUSTOMIZAR>\n5) Plazo: 6 meses",
        )
        assert "INSUMO 3 - PCIC" in prompt
        assert "1) Objetivo: <CUSTOMIZAR>" in prompt
        assert "Reglas de customizacion" in prompt
        assert "linea EXACTA 'PCIC:'" in prompt
        assert "el de ella MANDA" in prompt  # regla de oro del base

    def test_sin_pedido_no_incluye_nada(self) -> None:
        prompt = construir_prompt_ficha(
            **self.PROMPT_ARGS, pedidos=Pedidos(pcic=False), pcic_base="1) Objetivo: X"
        )
        assert "INSUMO 3" not in prompt

    def test_pedido_sin_base_no_incluye_insumo(self) -> None:
        prompt = construir_prompt_ficha(
            **self.PROMPT_ARGS, pedidos=Pedidos(pcic=True), pcic_base=None
        )
        assert "INSUMO 3" not in prompt


# --- ensamblador -----------------------------------------------------------

_BLOQUE_LLM = (
    "1) Objetivo: control de cifras de presion arterial\n"
    "2) Opciones: control medico+nutric / tratam farmacologico\n"
    "3) Acuerdos: cumplir tratamiento farmacologico con ajuste\n"
    "4) Responsable: equipo multidisciplinario + paciente\n"
    "5) Plazo: 6 meses"
)

_STUBS = "1.\n2.\n3.\n4.\n5."


class TestColocarPcicEnsamblador:
    def test_seccion_vacia_se_llena(self) -> None:
        base = (
            "> Control\n\nAnamnesis:\n   - dato\n\n"
            "ACTUALIZACION PLAN INDIVIDUAL DE CUIDADOS CONSENSUADOS\n"
            f"{_STUBS}\n"
        )
        llm = (
            "> Control\n\nAnamnesis:\n   - dato\n\n"
            "ACTUALIZACION PLAN INDIVIDUAL DE CUIDADOS CONSENSUADOS\n"
            f"{_STUBS}\n"
            f"PCIC:\n{_BLOQUE_LLM}\n"
        )
        r = ensamblar_ficha(base, llm)
        assert "PCIC" in r.secciones_agregadas
        assert "1) Objetivo: control de cifras de presion arterial" in r.texto
        assert r.texto.count("PLAN INDIVIDUAL DE CUIDADOS CONSENSUADOS") == 1
        assert "\n1.\n" not in r.texto, "los stubs fueron reemplazados"

    def test_pcic_de_la_doctora_manda(self) -> None:
        suyo = (
            "1. Objetivo: manejar sintomas de salud mental\n"
            "2. Opciones: farmacos + seguimiento ECICEP\n"
            "3. Acuerdos: suspender consumo de OH\n"
            "4. Responsable: paciente + equipo ECICEP\n"
            "5. Plazo: 6 meses"
        )
        base = (
            "> Control\n\nAnamnesis:\n   - dato\n\n"
            "ACTUALIZACION PLAN INDIVIDUAL DE CUIDADOS CONSENSUADOS\n"
            f"{suyo}\n"
        )
        llm = (
            "> Control\n\nAnamnesis:\n   - dato\n\n"
            "ACTUALIZACION PLAN INDIVIDUAL DE CUIDADOS CONSENSUADOS\n"
            f"{suyo}\n"
            f"PCIC:\n{_BLOQUE_LLM}\n"
        )
        r = ensamblar_ficha(base, llm)
        assert "PCIC" not in r.secciones_agregadas
        assert "1. Objetivo: manejar sintomas de salud mental" in r.texto
        assert "control de cifras de presion arterial" not in r.texto

    def test_variante_numerada_con_extensión(self) -> None:
        """'11. Plan individual de cuidados consensuados y conducta clinica'
        (variante real de la plantilla) vacia -> se llena igual."""
        base = (
            "> Control\n\nAnamnesis:\n   - dato\n\n"
            "10. Otra seccion:\n   - x\n"
            "11. Plan individual de cuidados consensuados y conducta clínica\n"
            f"{_STUBS}\n"
        )
        llm = (
            "> Control\n\nAnamnesis:\n   - dato\n\n"
            "10. Otra seccion:\n   - x\n"
            "11. Plan individual de cuidados consensuados y conducta clínica\n"
            f"{_STUBS}\n"
            f"PCIC:\n{_BLOQUE_LLM}\n"
        )
        r = ensamblar_ficha(base, llm)
        assert "PCIC" in r.secciones_agregadas
        assert "1) Objetivo: control de cifras de presion arterial" in r.texto
        assert "12." not in r.texto  # no habia seccion siguiente; se respetó el fin

    def test_sin_seccion_se_agrega_al_final(self) -> None:
        base = "> Control\n\nAnamnesis:\n   - dato\n\nINDICACIONES:\n- hidratacion\n"
        llm = (
            "> Control\n\nAnamnesis:\n   - dato\n\nINDICACIONES:\n- hidratacion\n"
            f"PCIC:\n{_BLOQUE_LLM}\n"
        )
        r = ensamblar_ficha(base, llm)
        assert "PCIC" in r.secciones_agregadas
        assert "PLAN INDIVIDUAL DE CUIDADOS CONSENSUADOS" in r.texto
        assert "1) Objetivo: control de cifras de presion arterial" in r.texto
        assert r.texto.rstrip().endswith("6 meses")

    def test_llm_sin_bloque_no_cambia_nada(self) -> None:
        base = (
            "> Control\n\nAnamnesis:\n   - dato\n\n"
            "ACTUALIZACION PLAN INDIVIDUAL DE CUIDADOS CONSENSUADOS\n"
            f"{_STUBS}\n"
        )
        llm = base  # sin bloque PCIC
        r = ensamblar_ficha(base, llm)
        assert "PCIC" not in r.secciones_agregadas
        assert f"{_STUBS}" in r.texto, "los stubs siguen intactos"

    def test_seccion_siguiente_sobrevive_al_llenado(self) -> None:
        """Los stubs '1.'-'5.' son el PCIC; '12. Conducta:' es OTRA
        seccion (salto de numeracion) y debe sobrevivir intacta."""
        base = (
            "> Control\n\nAnamnesis:\n   - dato\n\n"
            "11. Plan individual de cuidados consensuados\n"
            f"{_STUBS}\n"
            "12. Conducta:\n   - control en 3 meses\n"
        )
        llm = (
            "> Control\n\nAnamnesis:\n   - dato\n\n"
            "11. Plan individual de cuidados consensuados\n"
            f"{_STUBS}\n"
            "12. Conducta:\n   - control en 3 meses\n"
            f"PCIC:\n{_BLOQUE_LLM}\n"
        )
        r = ensamblar_ficha(base, llm)
        assert "PCIC" in r.secciones_agregadas
        assert "12. Conducta:" in r.texto
        assert "control en 3 meses" in r.texto
        assert r.texto.index("6 meses") < r.texto.index("12. Conducta:")
