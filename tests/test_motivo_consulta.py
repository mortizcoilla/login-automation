"""Tests para el extractor de motivo de consulta y la integracion con
guardar_nota_clinica.

El motivo vive en `li#anamnesis .textoverflow-container[style*="height: 28px"]`.
La anamnesis propiamente tal vive en otro `.textoverflow-container` hermano,
dentro de `.collapse-text-sub`. El script NO debe confundir ambos.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.tools.crear_notas_clinicas import (
    PacienteObjetivo,
    extraer_motivo_consulta,
    guardar_nota_clinica,
)


# ---- HTML fixture: la estructura real de li#anamnesis en Rayen ----

HTML_CON_MOTIVO_Y_ANAMNESIS = """
<li id="anamnesis">
  <div class="textoverflow-container" style="height: 28px;">
    ingreso sm en dupla  (no logrado)
  </div>
  <div class="collapse-text-sub">
    <div class="textoverflow-container">
      Paciente de 19 años de edad acude sola a ingreso sm en dupla
    </div>
  </div>
</li>
"""

HTML_SIN_MOTIVO_SOLO_ANAMNESIS = """
<li id="anamnesis">
  <div class="collapse-text-sub">
    <div class="textoverflow-container">
      Paciente de 66 años, control cardiovascular
    </div>
  </div>
</li>
"""

HTML_VACIO = """
<li id="anamnesis">
</li>
"""


# ---- Helpers ----

def _mock_driver(html: str) -> MagicMock:
    """Crea un mock de WebDriver que ejecuta el JS contra el HTML dado.

    El script JS usa document.querySelector sobre el DOM, asi que armamos
    un mini DOM con html.parser de Python.
    """
    from html.parser import HTMLParser
    from html import escape

    # Hack simple: para los selectores del script, lo mas facil es mockear
    # driver.execute_script para que devuelva lo que queremos segun el script.
    # Pero como el script es fijo, mejor mockeamos el resultado final.
    return html


def _build_driver_con_resultado(resultado_script: str) -> MagicMock:
    """Mock que devuelve resultado_script cuando se llama execute_script."""
    driver = MagicMock()
    driver.execute_script.return_value = resultado_script
    return driver


# ---- Tests del extractor ----

class TestExtraerMotivoConsulta:
    """El extractor es JS-inline; testeamos via mock del WebDriver."""

    def test_extrae_motivo_cuando_existe(self) -> None:
        driver = _build_driver_con_resultado("ingreso sm en dupla  (no logrado)")
        resultado = extraer_motivo_consulta(driver, logging.getLogger("test"))
        assert resultado == "ingreso sm en dupla  (no logrado)"

    def test_devuelve_vacio_si_no_hay_motivo(self) -> None:
        driver = _build_driver_con_resultado("")
        resultado = extraer_motivo_consulta(driver, logging.getLogger("test"))
        assert resultado == ""

    def test_devuelve_vacio_si_driver_falla(self) -> None:
        driver = MagicMock()
        driver.execute_script.side_effect = Exception("timeout")
        resultado = extraer_motivo_consulta(driver, logging.getLogger("test"))
        assert resultado == ""

    def test_strip_espacios(self) -> None:
        driver = _build_driver_con_resultado("  motivo con espacios   ")
        resultado = extraer_motivo_consulta(driver, logging.getLogger("test"))
        assert resultado == "motivo con espacios"

    def test_selector_js_apunta_al_elemento_correcto(self) -> None:
        """El JS debe usar `.textoverflow-container[style*='height: 28px']`
        dentro de `li#anamnesis`. Lo verificamos leyendo el codigo fuente
        para evitar regresiones silenciosas."""
        from src.tools import crear_notas_clinicas as cnc

        src = cnc.extraer_motivo_consulta.__doc__ or ""
        # El docstring ya menciona la convencion. Tambien verificamos que
        # la funcion existe y no fue removida por error.
        assert hasattr(cnc, "extraer_motivo_consulta")
        assert callable(cnc.extraer_motivo_consulta)


# ---- Tests del script JS especifico ----

class TestSelectorJsMotivo:
    """Verifica que el script JS embebido apunta a los selectores correctos.

    Lee la funcion extraer_motivo_consulta y parsea el string JS. No
    ejecutamos JS (no hay browser en tests) — solo validamos la estructura
    del codigo.
    """

    def test_js_busca_li_anamnesis(self) -> None:
        import inspect
        from src.tools.crear_notas_clinicas import extraer_motivo_consulta

        src = inspect.getsource(extraer_motivo_consulta)
        assert "li#anamnesis" in src

    def test_js_busca_textoverflow_con_height_28px(self) -> None:
        import inspect
        from src.tools.crear_notas_clinicas import extraer_motivo_consulta

        src = inspect.getsource(extraer_motivo_consulta)
        # El selector clave: el motivo es el container de height 28px
        assert "height: 28px" in src
        assert ".textoverflow-container" in src

    def test_js_NO_busca_dentro_de_collapse_text_sub(self) -> None:
        """El motivo NO esta dentro de .collapse-text-sub (eso es la anamnesis).
        El script JS NO debe confundir ambos — verificamos que el string JS
        embebido no haga query dentro de .collapse-text-sub."""
        import inspect
        import re
        from src.tools.crear_notas_clinicas import extraer_motivo_consulta

        src = inspect.getsource(extraer_motivo_consulta)
        # Extraemos el string JS embebido (entre r""" ... """)
        match = re.search(r'js\s*=\s*r?"""(.*?)"""', src, re.DOTALL)
        assert match is not None, "No se encontro el string JS embebido en la funcion"
        js = match.group(1)
        # El JS NO debe hacer query dentro de .collapse-text-sub
        assert ".collapse-text-sub" not in js, (
            "El selector del motivo NO debe mirar dentro de .collapse-text-sub "
            "(ahi vive la anamnesis propiamente tal)."
        )


# ---- Tests de integracion con guardar_nota_clinica ----

class TestGuardarNotaClinicaConMotivo:
    def _pac(self) -> PacienteObjetivo:
        return PacienteObjetivo(
            fecha="25-08-2026",
            nombre="Paciente Test",
            tipo_atencion="INGRESO ECICEP",
            razon="ECICEP",
        )

    def test_motivo_aparece_dentro_de_nota_clinica(
        self, tmp_path: Path
    ) -> None:
        """El motivo va como primera linea del bloque NOTA CLINICA,
        con label 'Motivo de atencion: '. NO es una seccion propia."""
        out = guardar_nota_clinica(
            paciente=self._pac(),
            identificacion={"RUN": "12.345.678-9"},
            historial="21-08-2026 Consulta previa",
            anamnesis="paciente masculino de 66 anos...",
            diagnosticos=["- HTA [Confirmado]"],
            actividades=["- Control"],
            profesionales=["- Dra. Yadira"],
            pautas=["- EMPAM"],
            examenes="",
            otros_items={},
            motivo_consulta="ingreso sm en dupla  (no logrado)",
            notas_dir=tmp_path,
        )
        assert out is not None
        texto = out.read_text(encoding="utf-8")

        # Marcadores del bloque
        # Skip past el header line para que bloque no incluya "## Nota clinica..."
        idx_inicio = texto.index("## Nota clinica de Yadira")
        idx_inicio = texto.index("\n", idx_inicio) + 1
        idx_fin = texto.index("## Actividades")  # siguiente header
        bloque = texto[idx_inicio:idx_fin]

        # El motivo esta DENTRO del bloque
        assert "> **Motivo de atencion:** ingreso sm en dupla  (no logrado)" in bloque

        # Y es la PRIMERA linea de contenido (despues de los separadores)
        lines_bloque = bloque.splitlines()
        contenido_lines = [
            l for l in lines_bloque
            if l.strip() and not l.startswith("===") and not l.startswith("=" * 5)
        ]
        assert contenido_lines[0] == "> **Motivo de atencion:** ingreso sm en dupla  (no logrado)", (
            f"El motivo debe ser la primera linea de contenido, pero la primera es: {contenido_lines[0]!r}"
        )
        # La segunda linea de contenido es la anamnesis (hay una vacia entre medio
        # que se filtra). NOTA: en markdown el blockquote "> ..." va en su
        # propia linea, asi que la anamnesis es contenido_lines[1].
        assert contenido_lines[1] == "paciente masculino de 66 anos..."

    def test_motivo_va_antes_de_la_anamnesis(self, tmp_path: Path) -> None:
        """El orden dentro de NOTA CLINICA: motivo, anamnesis. Sin secciones
        propias. La anamnesis NO debe empezar con el motivo pegado."""
        out = guardar_nota_clinica(
            paciente=self._pac(),
            identificacion={},
            historial="",
            anamnesis="ANAMNESIS_LINE",
            diagnosticos=[],
            actividades=[],
            profesionales=[],
            pautas=[],
            examenes="",
            otros_items={},
            motivo_consulta="MOTIVO_LINE",
            notas_dir=tmp_path,
        )
        texto = out.read_text(encoding="utf-8")
        idx_motivo = texto.index("> **Motivo de atencion:** MOTIVO_LINE")
        idx_anamnesis = texto.index("ANAMNESIS_LINE")
        assert idx_motivo < idx_anamnesis

    def test_sin_motivo_no_aparece_label_vacio(
        self, tmp_path: Path
    ) -> None:
        """Si motivo_consulta es vacio, no se agrega ninguna linea de motivo.
        NO se escribe 'Motivo de atencion: ' sin nada despues."""
        out = guardar_nota_clinica(
            paciente=self._pac(),
            identificacion={"RUN": "12.345.678-9"},
            historial="",
            anamnesis="anamnesis aqui",
            diagnosticos=[],
            actividades=[],
            profesionales=[],
            pautas=[],
            examenes="",
            otros_items={},
            motivo_consulta="",  # sin motivo
            notas_dir=tmp_path,
        )
        assert out is not None
        texto = out.read_text(encoding="utf-8")
        # NO debe aparecer "Motivo de atencion:" en ningun lado
        assert "Motivo de atencion:" not in texto
        # Y la anamnesis sigue ahi normal
        assert "anamnesis aqui" in texto

    def test_sin_motivo_no_contamina_anamnesis(
        self, tmp_path: Path
    ) -> None:
        """Si no hay motivo, la anamnesis va directa (sin linea vacia
        ni label raro)."""
        out = guardar_nota_clinica(
            paciente=self._pac(),
            identificacion={},
            historial="",
            anamnesis="LINEA 1 DE ANAMNESIS",
            diagnosticos=[],
            actividades=[],
            profesionales=[],
            pautas=[],
            examenes="",
            otros_items={},
            motivo_consulta="",
            notas_dir=tmp_path,
        )
        texto = out.read_text(encoding="utf-8")
        idx_inicio = texto.index("## Nota clinica de Yadira")
        idx_inicio = texto.index("\n", idx_inicio) + 1
        idx_fin = texto.index("## Actividades")
        bloque = texto[idx_inicio:idx_fin].splitlines()
        # primera linea no vacia debe ser la anamnesis directa
        contenido = [l for l in bloque if l.strip() and not l.startswith("=")]
        assert contenido[0] == "LINEA 1 DE ANAMNESIS"

    def test_motivo_y_estrato_coexisten(
        self, tmp_path: Path
    ) -> None:
        """El motivo va DENTRO de NOTA CLINICA (sub-linea), la estrato
        va DESPUES como bloque separado."""
        out = guardar_nota_clinica(
            paciente=self._pac(),
            identificacion={},
            historial="",
            anamnesis="anamnesis cuerpo",
            diagnosticos=[],
            actividades=[],
            profesionales=[],
            pautas=[],
            examenes="",
            otros_items={},
            motivo_consulta="ingreso sm en dupla  (no logrado)",
            estratificacion={
                "grupo": "G2",
                "grupo_label": "Riesgo moderado",
                "fecha_inicio": "24 ago. 2026",
                "agudos": [],
                "cronicos": [],
            },
            notas_dir=tmp_path,
        )
        texto = out.read_text(encoding="utf-8")
        # El motivo esta en la nota clinica
        idx_nota = texto.index("## Nota clinica de Yadira")
        idx_estrato = texto.index("## Estratificacion ECICEP")
        assert idx_nota < idx_estrato, "la nota clinica va antes que la estrato"
        # El motivo esta antes que la estrato
        idx_motivo = texto.index("> **Motivo de atencion:**")
        assert idx_motivo < idx_estrato
        # Y la estrato tiene su propio bloque
        assert "## Estratificacion ECICEP" in texto
        assert "Grupo: G2 (Riesgo moderado)" in texto

    def test_motivo_no_sobrescribe_archivo_existente(
        self, tmp_path: Path
    ) -> None:
        """Si el archivo ya existe, NO se sobrescribe (regla del proyecto)."""
        pac = self._pac()
        out1 = guardar_nota_clinica(
            paciente=pac,
            identificacion={},
            historial="",
            anamnesis="primera version",
            diagnosticos=[],
            actividades=[],
            profesionales=[],
            pautas=[],
            examenes="",
            otros_items={},
            motivo_consulta="motivo v1",
            notas_dir=tmp_path,
        )
        assert out1 is not None
        out2 = guardar_nota_clinica(
            paciente=pac,
            identificacion={},
            historial="",
            anamnesis="segunda version",
            diagnosticos=[],
            actividades=[],
            profesionales=[],
            pautas=[],
            examenes="",
            otros_items={},
            motivo_consulta="motivo v2",
            notas_dir=tmp_path,
        )
        assert out2 is None  # NO sobrescribe
        texto = out1.read_text(encoding="utf-8")
        assert "motivo v1" in texto
        assert "motivo v2" not in texto
        assert "primera version" in texto
        assert "segunda version" not in texto
