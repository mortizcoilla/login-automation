"""Tests de la receta cronica vigente en la ficha (REQ-104).

Cadena completa: parseo de la nota del paso 3 -> nodo ganador
([Cronica] con Vigencia mas reciente) -> inyeccion en la base ANTES del
LLM (seccion SIEMPRE creada) -> ensamblador la mantiene byte-identica.

La suite NUNCA llama a la API real ni abre Rayen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.mortadelo.ensamblador import ensamblar_ficha
from src.mortadelo.receta_cronica import (
    PLACEHOLDER_SIN_RECETA,
    TITULO_SECCION,
    cargar_receta_cronica,
    extraer_prescripciones,
    ganadora,
    inyectar_receta_cronica,
)

# Formato REAL de la nota (marcadores duplicados por el escritor de
# nota_clinica: '- ' + linea cruda '- [Cronica] ...' y '  - ' + '\t- F').
_NOTA = """## Atencion actual
- algo
## Plan - Recetas

- - [Cronica] Vigencia: 25 ago. 2026
  - \t- Metformina 850 mg comprimidos (1 Comprimido cada 24 Horas por 90 Dias)
- - [Cronica] Vigencia: 25 ago. 2027
  - \t- Metformina 1000 mg comprimidos (1 Comprimido cada 24 Horas por 90 Dias)
  - \t- Enalapril 10 mg comprimidos (1 Comprimido cada 24 Horas por 30 Dias)
- - [Aguda] Vigencia: 1 oct. 2026
  - \t- Ibuprofeno 400 mg comprimidos (1 Comprimido cada 8 Horas por 5 Dias)

## Plan - Laboratorio

_(sin ordenes de laboratorio)_
"""

_FARMACO_GANADOR = (
    "  - Metformina 1000 mg comprimidos (1 Comprimido cada 24 Horas por 90 Dias)"
)


class TestExtraerPrescripciones:
    def test_tres_prescripciones_con_marcas_normalizadas(self) -> None:
        ps = extraer_prescripciones(_NOTA)
        assert len(ps) == 3
        assert ps[0][0] == "- [Cronica] Vigencia: 25 ago. 2026"
        assert ps[1][0] == "- [Cronica] Vigencia: 25 ago. 2027"
        assert ps[2][0] == "- [Aguda] Vigencia: 1 oct. 2026"

    def test_farmaco_verbatim_tras_una_sola_marca(self) -> None:
        ps = extraer_prescripciones(_NOTA)
        assert ps[1][1] == _FARMACO_GANADOR
        assert ps[1][2] == (
            "  - Enalapril 10 mg comprimidos (1 Comprimido cada 24 Horas por 30 Dias)"
        )

    def test_sin_recetas(self) -> None:
        nota = "## Plan - Recetas\n\n_(sin recetas)_\n\n## Plan - Laboratorio\n"
        assert extraer_prescripciones(nota) == []

    def test_seccion_ausente(self) -> None:
        assert extraer_prescripciones("## Atencion actual\n- x\n") == []


class TestGanadora:
    def test_vigencia_mas_reciente_gana(self) -> None:
        ps = extraer_prescripciones(_NOTA)
        g = ganadora(ps)
        assert g is not None
        assert g[0] == "- [Cronica] Vigencia: 25 ago. 2027"
        assert g[1] == _FARMACO_GANADOR

    def test_aguda_mas_reciente_no_gana(self) -> None:
        ps = extraer_prescripciones(_NOTA)
        cronicas = [p for p in ps if "Cronica" in p[0]]
        assert ganadora(cronicas + [ps[2]])[0] == "- [Cronica] Vigencia: 25 ago. 2027"

    def test_solo_agudas_devuelve_none(self) -> None:
        ps = extraer_prescripciones(_NOTA)
        assert ganadora([ps[2]]) is None

    def test_sin_fechas_parseables_queda_la_ultima(self) -> None:
        a = ["- [Cronica]", "  - Farmaco A"]
        b = ["- [Cronica]", "  - Farmaco B"]
        assert ganadora([a, b]) == b

    def test_una_sola_cronica_es_la_ganadora(self) -> None:
        una = ["- [Cronica] Vigencia: 25 ago. 2026", "  - Metformina 850 mg"]
        assert ganadora([una]) == una


class TestCargarRecetaCronica:
    def test_lee_la_ganadora_de_la_nota(self, tmp_path: Path) -> None:
        (tmp_path / "Test_Paciente_10-09-2026.md").write_text(_NOTA, encoding="utf-8")
        bloque = cargar_receta_cronica("Test Paciente", "10-09-2026", notas_dir=tmp_path)
        assert bloque is not None
        assert bloque.startswith("- [Cronica] Vigencia: 25 ago. 2027")
        assert _FARMACO_GANADOR in bloque

    def test_nota_ausente_devuelve_none(self, tmp_path: Path) -> None:
        assert cargar_receta_cronica("Otro Pac", "10-09-2026", notas_dir=tmp_path) is None

    def test_nota_sin_cronicas_devuelve_none(self, tmp_path: Path) -> None:
        (tmp_path / "Test_Paciente_10-09-2026.md").write_text(
            "## Plan - Recetas\n\n_(sin recetas)_\n", encoding="utf-8"
        )
        assert cargar_receta_cronica("Test Paciente", "10-09-2026", notas_dir=tmp_path) is None


class TestInyectar:
    def test_seccion_siempre_creada_al_final(self) -> None:
        base = "> Control\n\nAnamnesis:\n   - dato"
        out = inyectar_receta_cronica(base, "- [Cronica] Vigencia: 25 ago. 2027")
        assert TITULO_SECCION in out
        assert out.rstrip().endswith("- [Cronica] Vigencia: 25 ago. 2027")

    def test_sin_bloque_deja_placeholder(self) -> None:
        out = inyectar_receta_cronica("> Control\n\nAnamnesis:\n   - dato", None)
        assert TITULO_SECCION in out
        assert PLACEHOLDER_SIN_RECETA in out

    def test_antes_de_indicaciones_con_stubs(self) -> None:
        """Meterla despues de los stubs romperia el llenado REQ-098."""
        base = "> Control\n\nAnamnesis:\n   - dato\n\n5. INDICACIONES\n5.1.\n5.2."
        out = inyectar_receta_cronica(base, "- [Cronica] Vigencia: 25 ago. 2027")
        assert out.index(TITULO_SECCION) < out.index("5. INDICACIONES")

    def test_antes_de_indicaciones_sin_numerar(self) -> None:
        base = "> Control\n\nINDICACIONES:\n- hidratacion\n"
        out = inyectar_receta_cronica(base, "- [Cronica] Vigencia: 1 dic. 2027")
        assert out.index(TITULO_SECCION) < out.index("INDICACIONES:")

    def test_bloque_va_verbatim(self) -> None:
        bloque = "- [Cronica] Vigencia: 25 ago. 2027\n" + _FARMACO_GANADOR
        out = inyectar_receta_cronica("base", bloque)
        assert bloque in out


# --- interplay con el ensamblador ------------------------------------------


_PLANTILLA = (
    "> Control\n\nAnamnesis:\n   - dato\n\n"
    "4. Examen fisico:\n   - estable\n\n"
    "5. INDICACIONES\n5.1.\n5.2.\n"
)


class TestEnsambladorConReceta:
    def _base_inyectada(self, bloque: str | None) -> str:
        return inyectar_receta_cronica(_PLANTILLA, bloque)

    def test_receta_sobrevive_y_stubs_se_llenan(self) -> None:
        base = self._base_inyectada(
            "- [Cronica] Vigencia: 25 ago. 2027\n" + _FARMACO_GANADOR
        )
        llm = base.replace("5.1.\n5.2.", "") + (
            "   - Tomar Metformina con alimentos\n   - Control de glicemia\n"
        )
        r = ensamblar_ficha(base, llm)
        assert _FARMACO_GANADOR in r.texto, "la receta queda byte-identica"
        assert "INDICACIONES" in r.secciones_agregadas
        assert "Tomar Metformina con alimentos" in r.texto
        # orden: receta ANTES de la seccion INDICACIONES
        assert r.texto.index(TITULO_SECCION) < r.texto.index("5. INDICACIONES")

    def test_llm_que_borra_la_receta_la_restaura_desde_la_base(self) -> None:
        base = self._base_inyectada(
            "- [Cronica] Vigencia: 25 ago. 2027\n" + _FARMACO_GANADOR
        )
        llm = "\n".join(ln for ln in base.splitlines() if "Metformina" not in ln)
        r = ensamblar_ficha(base, llm)
        assert _FARMACO_GANADOR in r.texto
        assert "- [Cronica] Vigencia: 25 ago. 2027" in r.texto

    def test_placeholder_sin_cronicas_tambien_sobrevive(self) -> None:
        base = self._base_inyectada(None)
        llm = base
        r = ensamblar_ficha(base, llm)
        assert TITULO_SECCION in r.texto
        assert PLACEHOLDER_SIN_RECETA in r.texto

    def test_trigger_cerrado_no_arrasta_la_receta(self) -> None:
        base = inyectar_receta_cronica(
            "> Control\n\nAnamnesis:\n   - dato\n\n** Mortadelo\n\n- examenes adjuntos\n\n**",
            "- [Cronica] Vigencia: 25 ago. 2027\n" + _FARMACO_GANADOR,
        )
        r = ensamblar_ficha(base, base)
        assert "mortadelo" not in r.texto.lower()
        assert _FARMACO_GANADOR in r.texto


# --- integracion generar_paciente ------------------------------------------

_INFORME = (
    "## ALERTAS\nSin alertas.\n\n## Llenados realizados\n| C | O | F |\n|-|-|-|\n"
    "## Correcciones ortograficas\nNinguna.\n## Diagnostico diferencial\n- x\n"
    "## Recomendaciones\n- y\n## Sin informacion suficiente\nNinguno."
)


def _llm_fake(prompt: str) -> tuple[str, str]:
    if "INFORME DE TRAZABILIDAD" in prompt:
        return _INFORME, "modelo-falso"
    doc = prompt.split("=== DOCUMENTO PRINCIPAL")[1]
    doc = doc.split("\n", 1)[1]  # quita el resto de la linea de encabezado
    doc = doc.split("=== FIN DOCUMENTO PRINCIPAL ===")[0].strip("\n")
    return doc + "\nINDICACIONES:\n   - control en 3 meses\n", "modelo-falso"


class TestGenerarPacienteConReceta:
    def _montar(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nota: str
    ) -> None:
        from src.core.nombres import safe_filename

        monkeypatch.setattr("src.mortadelo.generar.ANAMNESIS_DIR", tmp_path / "anam")
        monkeypatch.setattr("src.mortadelo.generar.NOTAS_DIR", tmp_path / "notas")
        monkeypatch.setattr(
            "src.mortadelo.receta_cronica.NOTAS_DIR", tmp_path / "notas"
        )
        monkeypatch.setattr("src.mortadelo.generar.INFO_PACIENTE_DIR", tmp_path / "info")
        monkeypatch.setattr("src.mortadelo.generar.EXAMENES_DIR", tmp_path / "exam")
        (tmp_path / "anam").mkdir()
        (tmp_path / "notas").mkdir()
        (tmp_path / "info").mkdir()
        (tmp_path / "exam").mkdir()
        (tmp_path / "anam" / f"anam_{safe_filename('Test Paciente')}_10-09-2026.md").write_text(
            "> Control\n\nAnamnesis:\n   - dato\n", encoding="utf-8"
        )
        (tmp_path / "notas" / f"{safe_filename('Test Paciente')}_10-09-2026.md").write_text(
            nota, encoding="utf-8"
        )

    def test_ficha_lleva_la_cronica_ganadora(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._montar(tmp_path, monkeypatch, _NOTA)
        r = _generar(tmp_path)
        assert r.ok is True, r.error
        ficha = Path(r.ficha_path).read_text(encoding="utf-8")
        assert TITULO_SECCION in ficha
        assert _FARMACO_GANADOR in ficha, "queda el farmaco de la vigencia 2027"
        assert "Metformina 850" not in ficha, "la vieja (2026) no entra"
        assert "Ibuprofeno" not in ficha, "la aguda no entra"

    def test_ficha_sin_cronicas_lleva_placeholder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._montar(
            tmp_path, monkeypatch, "## Plan - Recetas\n\n_(sin recetas)_\n"
        )
        r = _generar(tmp_path)
        assert r.ok is True, r.error
        ficha = Path(r.ficha_path).read_text(encoding="utf-8")
        assert TITULO_SECCION in ficha
        assert PLACEHOLDER_SIN_RECETA in ficha

    def test_nota_ausente_lleva_placeholder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._montar(tmp_path, monkeypatch, _NOTA)
        # nota de OTRO paciente (la de Test Paciente se borra)
        (tmp_path / "notas" / "Test_Paciente_10-09-2026.md").unlink()
        r = _generar(tmp_path)
        assert r.ok is True, r.error
        ficha = Path(r.ficha_path).read_text(encoding="utf-8")
        assert PLACEHOLDER_SIN_RECETA in ficha


def _generar(tmp_path: Path):
    from src.mortadelo.generar import generar_paciente

    return generar_paciente(
        "Test Paciente",
        "10-09-2026",
        fichas_dir=tmp_path / "f",
        informes_dir=tmp_path / "i",
        llm=_llm_fake,
    )
