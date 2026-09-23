"""Tests del nucleo del paso 7 (src/mortadelo/).

La suite NUNCA llama a la API real: llm_run es inyectable (REQ-055).
El ensamblador es el foco: sus garantias estructurales son el corazon
del diseño (REQ-056).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.mortadelo.ensamblador import (
    _rango_trigger,
    ensamblar_ficha,
    es_correccion_ortografica,
)
from src.mortadelo.generar import (
    _texto_trigger,
    detectar_pedidos,
    generar_paciente,
)
from src.mortadelo.llm_cli import _limpiar_salida, modelos_cascada
from src.mortadelo.prompt import (
    Pedidos,
    construir_prompt_ficha,
)
from src.mortadelo.validacion import validar_ficha, validar_informe

BASE = """> **Motivo de atencion:** control sm
Paciente de 17 años de edad
Estado civil:
MEDICAMENTOS:
APF: madre ca de colon
Examen fisico: estable, sin edemas
** Mortadelo

- examenes adjuntos
- crear interconsulta urologia

**
"""


# ---------------------------------------------------------------------------
# llm_cli
# ---------------------------------------------------------------------------


class TestLLMCli:
    def test_limpia_encabezado_opencode(self) -> None:
        crudo = "\n> mortadelo · nemotron-3-ultra-free\n\n> **Motivo de atencion:** x\nTexto"
        assert _limpiar_salida(crudo).startswith("> **Motivo")

    def test_limpia_ansi(self) -> None:
        assert _limpiar_salida("\x1b[0mOK").startswith("OK")

    def test_cascada_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MORTADELO_MODELOS", raising=False)
        assert modelos_cascada() == ["opencode/nemotron-3-ultra-free"]

    def test_cascada_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MORTADELO_MODELOS", "a, b ,c")
        assert modelos_cascada() == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# es_correccion_ortografica (la regla que rechaza reformulaciones)
# ---------------------------------------------------------------------------


class TestEsCorreccionOrtografica:
    def test_letra_faltante(self) -> None:
        assert es_correccion_ortografica(
            "en tiempo, espacio y person", "en tiempo, espacio y persona"
        )

    def test_tilde(self) -> None:
        assert es_correccion_ortografica("se realizo examenes", "se realizó exámenes")

    def test_termino_medico_una_letra(self) -> None:
        assert es_correccion_ortografica("herniorragia inguinal", "herniorrafia inguinal")

    def test_rechaza_cambio_tiempo_verbal(self) -> None:
        # operan -> operaron son 2 ediciones: NO es ortografia
        assert not es_correccion_ortografica(
            "en mayo operan por polipos", "en mayo operaron por pólipos"
        )

    def test_rechaza_palabra_agregada(self) -> None:
        assert not es_correccion_ortografica(
            "acude forma extrasistema", "acude de forma extrasistema"
        )

    def test_rechaza_reordenamiento(self) -> None:
        assert not es_correccion_ortografica("perdida de peso", "peso perdido")

    def test_identicas_no_es_correccion(self) -> None:
        assert not es_correccion_ortografica("niega alergias", "niega alergias")

    def test_rechaza_dos_cambios_en_una_palabra(self) -> None:
        assert not es_correccion_ortografica("derivan a urologo", "derivaron al urólogo")


# ---------------------------------------------------------------------------
# ensamblar_ficha: garantias estructurales
# ---------------------------------------------------------------------------


class TestEnsamblarFicha:
    def test_llena_campo_vacio(self) -> None:
        salida = BASE.replace("MEDICAMENTOS:", "MEDICAMENTOS: sin recetas vigentes")
        r = ensamblar_ficha(BASE, salida)
        assert "MEDICAMENTOS: sin recetas vigentes" in r.texto
        assert "Estado civil:" in r.texto  # el otro vacio queda tal cual

    def test_acepta_correccion_ortografica(self) -> None:
        salida = BASE.replace("estable, sin edemas", "estable, sin edema")
        r = ensamblar_ficha(BASE, salida)
        assert "sin edema" in r.texto
        assert len(r.correcciones) == 1

    def test_rechaza_reformulacion(self) -> None:
        salida = BASE.replace(
            "Examen fisico: estable, sin edemas", "Examen físico: paciente estable, sin edemas"
        )
        r = ensamblar_ficha(BASE, salida)
        # la linea original queda byte-identica
        assert "Examen fisico: estable, sin edemas" in r.texto

    def test_rechaza_reformato_a_vinetas(self) -> None:
        salida = BASE.replace(
            "APF: madre ca de colon",
            "APF:\n- madre ca de colon",
        )
        r = ensamblar_ficha(BASE, salida)
        assert "APF: madre ca de colon" in r.texto
        assert "\n- madre ca de colon\n" not in r.texto

    def test_elimina_trigger(self) -> None:
        r = ensamblar_ficha(BASE, BASE)
        assert "** mortadelo" not in r.texto.lower()
        assert "examenes adjuntos" not in r.texto

    def test_no_agrega_indicaciones_aunque_el_llm_las_escriba(self) -> None:
        """REQ-077/078: la ficha no agrega secciones (regla dura)."""
        salida = BASE + "\nINDICACIONES:\n1. Control en 3 meses.\n"
        r = ensamblar_ficha(BASE, salida)
        assert "INDICACIONES:" not in r.texto

    def test_no_agrega_interconsulta_aunque_el_llm_la_escriba(self) -> None:
        salida = BASE + "\nINTERCONSULTA A UROLOGIA:\nEvaluacion de HBP grado IV.\n"
        r = ensamblar_ficha(BASE, salida)
        assert "INTERCONSULTA A UROLOGIA:" not in r.texto

    def test_orden_indicaciones_antes_que_interconsulta(self) -> None:
        """REQ-077/078: las secciones que el LLM invente se DESCARTAN —
        el orden ya no aplica porque la ficha no agrega secciones."""
        ficha = "anamnesis base"
        salida = (
            ficha
            + chr(10) + "INDICACIONES:" + chr(10) + "- x"
            + chr(10) + "INTERCONSULTA A UROLOGIA:" + chr(10) + "- y"
        )
        r = ensamblar_ficha(ficha, salida)
        assert "INDICACIONES:" not in r.texto
        assert "INTERCONSULTA" not in r.texto

    def test_caso_degenerado_salida_basura(self) -> None:
        r = ensamblar_ficha(BASE, "Lo siento, no puedo ayudar con eso.\n```python\nx=1\n```")
        # la ficha final = base sin trigger, nada del modelo
        assert "> **Motivo de atencion:** control sm" in r.texto
        assert "Lo siento" not in r.texto
        assert "```" not in r.texto

    def test_rango_trigger_con_y_sin_cierre(self) -> None:
        lineas = ["texto", "** Mortadelo", "", "- bullet", "**", "despues"]
        assert _rango_trigger(lineas) == (1, 5)
        lineas2 = ["texto", "** mortadelo", "- bullet"]
        assert _rango_trigger(lineas2) == (1, 3)


# ---------------------------------------------------------------------------
# deteccion de pedidos (trigger)
# ---------------------------------------------------------------------------


class TestDetectarPedidos:
    def test_trigger_completo(self) -> None:
        p = detectar_pedidos(BASE)
        assert p.examenes is True
        assert p.interconsulta_especialidad == "urologia"
        assert p.indicaciones is False

    def test_sin_trigger(self) -> None:
        base = "> **Motivo de atencion:** control\nPaciente sin trigger\n"
        p = detectar_pedidos(base)
        assert p.trigger_texto == ""
        assert p.examenes is False
        assert p.interconsulta_especialidad is None

    def test_indicaciones(self) -> None:
        base = BASE.replace("- crear interconsulta urologia", "- realizar indicaciones")
        p = detectar_pedidos(base)
        assert p.indicaciones is True
        assert p.interconsulta_especialidad is None

    def test_texto_trigger_sin_cierre_no_incluye_el_final(self) -> None:
        base = "> **Motivo de atencion:** x\n\n** mortadelo\n- bullet\n"
        assert "bullet" in _texto_trigger(base)


# ---------------------------------------------------------------------------
# validacion
# ---------------------------------------------------------------------------


class TestValidacion:
    def test_ficha_valida_sin_advertencias(self) -> None:
        r = ensamblar_ficha(BASE, BASE)
        assert validar_ficha(r.texto, BASE, "Paciente de 17 años") == []

    def test_v1_primera_linea(self) -> None:
        assert any(a.codigo == "V1_PRIMERA_LINEA" for a in validar_ficha("otra cosa", BASE))

    def test_v2_trigger_presente(self) -> None:
        assert any(a.codigo == "V2_TRIGGER" for a in validar_ficha(BASE, ""))

    def test_v3_edad_inconsistente(self) -> None:
        ficha = BASE.replace("17 años", "19 años").replace(
            "** Mortadelo\n\n- examenes adjuntos\n- crear interconsulta urologia\n\n**\n", ""
        )
        advs = validar_ficha(ficha, BASE, "Paciente de 17 años")
        assert any(a.codigo == "V3_EDAD" for a in advs)

    def test_v5_bloque_codigo(self) -> None:
        assert any(a.codigo == "V5_FORMATO" for a in validar_ficha("```x```", ""))

    def test_informe_sin_secciones(self) -> None:
        advs = validar_informe("# Cualquier cosa")
        assert len(advs) == 3


# ---------------------------------------------------------------------------
# generar_paciente con LLM falso
# ---------------------------------------------------------------------------


class TestGenerarPaciente:
    def _montar(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, base: str, nota: str | None = None
    ) -> None:
        from src.core.nombres import safe_filename

        monkeypatch.setattr("src.mortadelo.generar.ANAMNESIS_DIR", tmp_path / "anam")
        monkeypatch.setattr("src.mortadelo.generar.NOTAS_DIR", tmp_path / "notas")
        monkeypatch.setattr("src.mortadelo.generar.INFO_PACIENTE_DIR", tmp_path / "info")
        monkeypatch.setattr("src.mortadelo.generar.EXAMENES_DIR", tmp_path / "exam")
        (tmp_path / "anam").mkdir()
        (tmp_path / "anam" / f"anam_{safe_filename('Test Paciente')}_10-09-2026.md").write_text(
            base, encoding="utf-8"
        )
        (tmp_path / "info").mkdir()
        (tmp_path / "info" / f"info_{safe_filename('Test Paciente')}_10-09-2026.md").write_text(
            "## Identificacion\n- **Edad Cronologica:** 17 años\n## Plan - Recetas\n_(sin recetas)_\n",
            encoding="utf-8",
        )

    def test_ok_completo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._montar(tmp_path, monkeypatch, BASE)
        fichas, informes = tmp_path / "f", tmp_path / "i"

        def llm_fake(prompt: str) -> tuple[str, str]:
            if "INFORME DE TRAZABILIDAD" in prompt:
                return (
                    "## ALERTAS\nSin alertas.\n\n## Llenados realizados\n| C | O | F |\n|-|-|-|\n"
                    "## Correcciones ortograficas\nNinguna.\n## Diagnostico diferencial\n- x\n"
                    "## Recomendaciones\n- y\n## Sin informacion suficiente\nNinguno.",
                    "modelo-falso",
                )
            return BASE.replace(
                "MEDICAMENTOS:", "MEDICAMENTOS: (-)"
            ) + "\nINTERCONSULTA A UROLOGIA:\nTexto ic.\n", "modelo-falso"

        r = generar_paciente(
            "Test Paciente", "10-09-2026", fichas_dir=fichas, informes_dir=informes, llm=llm_fake
        )
        assert r.ok is True, r.error
        assert Path(r.ficha_path).exists()
        assert Path(r.informe_path).exists()
        ficha = Path(r.ficha_path).read_text(encoding="utf-8")
        assert "MEDICAMENTOS: (-)" in ficha
        # REQ-077/078: la ficha NO agrega secciones aunque el trigger las
        # pida y aunque el LLM las escriba — se reconstruye desde la base.
        assert "INTERCONSULTA A UROLOGIA:" not in ficha
        assert "** mortadelo" not in ficha.lower()
        informe = Path(r.informe_path).read_text(encoding="utf-8")
        assert "Modelo ficha: modelo-falso" in informe  # sello por codigo
        assert informe.startswith("# Informe de trazabilidad")

    def test_sin_anamnesis_skip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._montar(tmp_path, monkeypatch, BASE)
        r = generar_paciente(
            "Desconocido Total",
            "10-09-2026",
            fichas_dir=tmp_path / "f",
            informes_dir=tmp_path / "i",
            llm=lambda p: ("x", "m"),
        )
        assert r.ok is False
        assert "Sin anamnesis" in r.error

    def test_llm_falla_no_escribe_nada(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._montar(tmp_path, monkeypatch, BASE)

        def llm_mala(prompt: str) -> tuple[str, str]:
            from src.mortadelo.llm_cli import LLMError

            raise LLMError("cascada agotada")

        r = generar_paciente(
            "Test Paciente",
            "10-09-2026",
            fichas_dir=tmp_path / "f",
            informes_dir=tmp_path / "i",
            llm=llm_mala,
        )
        assert r.ok is False
        assert "cascada agotada" in r.error
        assert not list((tmp_path / "f").glob("*.md"))


# ---------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------


class TestPrompts:
    PEDIDOS = None

    def test_prompt_ficha_contiene_todo(self) -> None:
        from src.mortadelo.prompt import Pedidos

        p = construir_prompt_ficha(
            "Pac Test",
            "10-09-2026",
            BASE,
            "INFO PAC",
            "EXAM PAC",
            Pedidos(trigger_texto="** mortadelo\n- examenes adjuntos", examenes=True),
        )
        assert "Pac Test" in p and BASE in p and "INFO PAC" in p and "EXAM PAC" in p
        assert "** mortadelo" in p  # como instruccion
        assert "OBLIGATORIO" in p

    def test_prompt_ficha_sin_examenes_lo_declara(self) -> None:
        from src.mortadelo.prompt import Pedidos

        p = construir_prompt_ficha("P", "10-09-2026", BASE, "I", None, Pedidos())
        assert "no tiene examenes consolidados" in p

    def test_prompt_ficha_sin_instruccion_de_secciones(self) -> None:
        """REQ-077/078: la ficha jamas recibe instrucciones de secciones
        — los pedidos se responden en el informe de trazabilidad."""
        pedidos_con_todo = Pedidos(
            indicaciones=True,
            interconsulta_especialidad="psiquiatria",
            pedidos_libres=["Dame sugerencias"],
        )
        prompt = construir_prompt_ficha(
            "X", "22-09-2026", "base", "info", None, pedidos_con_todo
        )
        assert "Como la doctora pidio" not in prompt
        assert "agrega AL FINAL" not in prompt
        assert "Prohibido: agregar secciones" in prompt
