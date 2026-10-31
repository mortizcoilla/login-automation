"""Tests de la receta cronica vigente en la ficha (REQ-104).

Cadena: la nota del paso 3 porta el bloque verbatim del arbol "Receta"
(src/rayen/extraccion/receta_cronica.py) -> esta funcion lo lee
(cargar_estado_receta) y lo INYECTA en la base de anamnesis ANTES del
LLM -> el ensamblador lo mantiene byte-identica.

La suite NUNCA llama a la API real ni abre Rayen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.mortadelo.ensamblador import ensamblar_ficha
from src.mortadelo.receta_cronica import (
    NO_VERIFICADO,
    SIN_MEDICAMENTOS,
    TITULO_SECCION_NUEVA,
    cargar_estado_receta,
    inyectar_receta_cronica,
)

_BLOQUE = (
    "14-09-2026 12:05\n"
    "(1) Receta Nro. 596039360, generada el 14-09-2026 12:13, tipo crónica , "
    "estado despachada , fecha de despacho: 15-09-2026\n"
    "Acetato de Medroxiprogesterona 104 mg/0,65 ml Suspension Inyectable , "
    "ampolla: 1 Ampolla cada 90 días por 90 días de la Receta Nº 596039360"
)

_NOTA_CON_BLOQUE = f"""## Plan - Laboratorio

_(sin ordenes de laboratorio)_

## Receta cronica

{_BLOQUE}
"""

_NOTA_SIN = "## Receta cronica\n\n(sin receta cronica vigente)\n"
_NOTA_INDETERMINADA = "## Receta cronica\n\n(no verificado - revisar)\n"


def _escribir_nota(tmp_path: Path, nota: str) -> Path:
    (tmp_path / "Test_Paciente_10-09-2026.md").write_text(nota, encoding="utf-8")
    return tmp_path


class TestCargarEstadoReceta:
    def test_encontrada_con_bloque_verbatim(self, tmp_path: Path) -> None:
        _escribir_nota(tmp_path, _NOTA_CON_BLOQUE)
        e = cargar_estado_receta("Test Paciente", "10-09-2026", notas_dir=tmp_path)
        assert e == {"estado": "encontrada", "bloque": _BLOQUE}

    def test_no_existe(self, tmp_path: Path) -> None:
        _escribir_nota(tmp_path, _NOTA_SIN)
        e = cargar_estado_receta("Test Paciente", "10-09-2026", notas_dir=tmp_path)
        assert e == {"estado": "no_existe", "bloque": ""}

    def test_indeterminado(self, tmp_path: Path) -> None:
        _escribir_nota(tmp_path, _NOTA_INDETERMINADA)
        e = cargar_estado_receta("Test Paciente", "10-09-2026", notas_dir=tmp_path)
        assert e == {"estado": "indeterminado", "bloque": ""}

    def test_nota_sin_seccion_devuelve_none(self, tmp_path: Path) -> None:
        _escribir_nota(tmp_path, "## Plan - Recetas\n\n_(sin recetas)_\n")
        assert cargar_estado_receta("Test Paciente", "10-09-2026", notas_dir=tmp_path) is None

    def test_nota_ausente_devuelve_none(self, tmp_path: Path) -> None:
        assert cargar_estado_receta("Otro Pac", "10-09-2026", notas_dir=tmp_path) is None


class TestInyectar:
    def test_base_sin_seccion_se_crea_al_final(self) -> None:
        base = "> Control\n\nAnamnesis:\n   - dato\n"
        out = inyectar_receta_cronica(base, {"estado": "encontrada", "bloque": _BLOQUE})
        assert TITULO_SECCION_NUEVA in out
        assert out.rstrip().endswith(_BLOQUE)

    def test_bloque_va_verbatim(self) -> None:
        out = inyectar_receta_cronica("base", {"estado": "encontrada", "bloque": _BLOQUE})
        assert _BLOQUE in out

    def test_no_existe_placeholder_del_diseno(self) -> None:
        out = inyectar_receta_cronica("base", {"estado": "no_existe", "bloque": ""})
        assert SIN_MEDICAMENTOS in out

    def test_indeterminado_visible(self) -> None:
        out = inyectar_receta_cronica("base", {"estado": "indeterminado", "bloque": ""})
        assert NO_VERIFICADO in out

    def test_nota_sin_seccion_no_inyecta_nada(self) -> None:
        base = "> Control\n\nAnamnesis:\n   - dato\n"
        assert inyectar_receta_cronica(base, None) == base

    def test_antes_de_indicaciones_con_stubs(self) -> None:
        """Meterla despues de los stubs romperia el llenado REQ-098."""
        base = "> Control\n\nAnamnesis:\n   - dato\n\n5. INDICACIONES\n5.1.\n5.2."
        out = inyectar_receta_cronica(base, {"estado": "no_existe", "bloque": ""})
        assert out.index(TITULO_SECCION_NUEVA) < out.index("5. INDICACIONES")

    def test_seccion_vacia_de_plantilla_se_rellena(self) -> None:
        base = "> Control\n\n3.3. Farmacos de uso diario:\n\n4. Otro:\n   - x\n"
        out = inyectar_receta_cronica(base, {"estado": "encontrada", "bloque": _BLOQUE})
        assert out.index("3.3. Farmacos de uso diario:") < out.index(_BLOQUE.splitlines()[0])
        assert "4. Otro:" in out and out.index(_BLOQUE) < out.index("4. Otro:")

    def test_lo_escrito_por_yadira_manda_y_el_bloque_va_debajo(self) -> None:
        base = (
            "> Control\n\nFármacos de uso diario:\n"
            "losartan 50mg cada 24 horas\n\n5. INDICACIONES\n- control\n"
        )
        out = inyectar_receta_cronica(base, {"estado": "encontrada", "bloque": _BLOQUE})
        assert "losartan 50mg cada 24 horas" in out, "jamás se borra lo suyo"
        assert out.index("losartan 50mg") < out.index(_BLOQUE.splitlines()[0])
        assert out.index(_BLOQUE.splitlines()[0]) < out.index("5. INDICACIONES")

    def test_variante_medicamentos_con_contenido(self) -> None:
        base = "> Control\n\nMEDICAMENTOS:\nMetformina 850\n\nAPF: sin antecedentes\n"
        out = inyectar_receta_cronica(base, {"estado": "encontrada", "bloque": _BLOQUE})
        assert "Metformina 850" in out
        assert _BLOQUE.splitlines()[0] in out


# --- interplay con el ensamblador ------------------------------------------

_PLANTILLA = (
    "> Control\n\nAnamnesis:\n   - dato\n\n"
    "4. Examen fisico:\n   - estable\n\n"
    "5. INDICACIONES\n5.1.\n5.2.\n"
)


class TestEnsambladorConReceta:
    def _base_inyectada(self, estado: dict | None) -> str:
        return inyectar_receta_cronica(_PLANTILLA, estado)

    def test_bloque_sobrevive_y_stubs_se_llenan(self) -> None:
        base = self._base_inyectada({"estado": "encontrada", "bloque": _BLOQUE})
        llm = base.replace("5.1.\n5.2.", "") + (
            "   - Tomar los medicamentos con alimentos\n   - Control de presion\n"
        )
        r = ensamblar_ficha(base, llm)
        assert _BLOQUE in r.texto, "el bloque queda byte-identico"
        assert "INDICACIONES" in r.secciones_agregadas
        assert "Tomar los medicamentos con alimentos" in r.texto
        assert r.texto.index("FARMACOS DE USO DIARIO") < r.texto.index("5. INDICACIONES")

    def test_llm_que_borra_el_bloque_lo_restaura_desde_la_base(self) -> None:
        base = self._base_inyectada({"estado": "encontrada", "bloque": _BLOQUE})
        llm = "\n".join(
            ln for ln in base.splitlines() if "Medroxiprogesterona" not in ln
        )
        r = ensamblar_ficha(base, llm)
        assert _BLOQUE in r.texto

    def test_placeholder_no_existe_tambien_sobrevive(self) -> None:
        base = self._base_inyectada({"estado": "no_existe", "bloque": ""})
        r = ensamblar_ficha(base, base)
        assert SIN_MEDICAMENTOS in r.texto


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
    def _montar(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nota: str | None) -> None:
        from src.core.nombres import safe_filename

        monkeypatch.setattr("src.mortadelo.generar.ANAMNESIS_DIR", tmp_path / "anam")
        monkeypatch.setattr("src.mortadelo.generar.NOTAS_DIR", tmp_path / "notas")
        monkeypatch.setattr("src.mortadelo.receta_cronica.NOTAS_DIR", tmp_path / "notas")
        monkeypatch.setattr("src.mortadelo.generar.INFO_PACIENTE_DIR", tmp_path / "info")
        monkeypatch.setattr("src.mortadelo.generar.EXAMENES_DIR", tmp_path / "exam")
        (tmp_path / "anam").mkdir()
        (tmp_path / "notas").mkdir()
        (tmp_path / "info").mkdir()
        (tmp_path / "exam").mkdir()
        (tmp_path / "anam" / f"anam_{safe_filename('Test Paciente')}_10-09-2026.md").write_text(
            "> Control\n\nAnamnesis:\n   - dato\n", encoding="utf-8"
        )
        if nota is not None:
            (tmp_path / "notas" / f"{safe_filename('Test Paciente')}_10-09-2026.md").write_text(
                nota, encoding="utf-8"
            )

    def _generar(self, tmp_path: Path):
        from src.mortadelo.generar import generar_paciente

        return generar_paciente(
            "Test Paciente",
            "10-09-2026",
            fichas_dir=tmp_path / "f",
            informes_dir=tmp_path / "i",
            llm=_llm_fake,
        )

    def test_ficha_lleva_el_bloque_de_la_nota(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._montar(tmp_path, monkeypatch, _NOTA_CON_BLOQUE)
        r = self._generar(tmp_path)
        assert r.ok is True, r.error
        ficha = Path(r.ficha_path).read_text(encoding="utf-8")
        assert _BLOQUE in ficha, "bloque verbatim en la ficha final"

    def test_nota_sin_receta_lleva_placeholder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._montar(tmp_path, monkeypatch, _NOTA_SIN)
        r = self._generar(tmp_path)
        assert r.ok is True, r.error
        ficha = Path(r.ficha_path).read_text(encoding="utf-8")
        assert SIN_MEDICAMENTOS in ficha

    def test_nota_sin_seccion_no_inyecta(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._montar(tmp_path, monkeypatch, "## Plan - Recetas\n\n_(sin recetas)_\n")
        r = self._generar(tmp_path)
        assert r.ok is True, r.error
        ficha = Path(r.ficha_path).read_text(encoding="utf-8")
        assert TITULO_SECCION_NUEVA not in ficha
        assert SIN_MEDICAMENTOS not in ficha
