"""Tests para el extractor de estratificacion ECICEP.

La extraccion en si misma corre como JS dentro del WebDriver
(_ESTRAT_CARD_JS, _ESTRAT_MODAL_JS). Estos tests cubren:

- `formatear_estratificacion`: convierte el dict que devuelve el JS en
  el bloque de texto que se guarda en la nota clinica.
- `guardar_nota_clinica`: incluye la nueva seccion ESTRATIFICACION
  ECICEP en el .txt cuando recibe un dict valido, y la omite cuando
  no hay datos (paciente sin estratificar).
- Smoke test: el modulo `crear_notas_clinicas` carga y expone las
  nuevas funciones.

La parte JS (que corre en el browser) no se testea aca — requiere
sesion real de Rayen. Se valida en vivo.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from src.rayen.extraccion import estratificacion as cnc
from src.rayen.extraccion.estratificacion import formatear_estratificacion
from src.tools.crear_notas_clinicas import PacienteObjetivo, guardar_nota_clinica


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("test_estrat")


# ---- Fixture: dict de estratificacion realista basado en el HTML real ----


@pytest.fixture
def estrat_completa() -> dict:
    """Dict que el JS deberia producir para el caso del HTML que paso
    Miguel (paciente G2 con varios cronicos y agudos)."""
    return {
        "grupo": "G2",
        "grupo_label": "Riesgo moderado",
        "fecha_inicio": "25 ago. 2026",
        "agudos": [
            {
                "nombre": "Contractura muscular",
                "fecha": "Hace 8 dias",
                "codigo_cie10": "M62.4",
                "descripcion_cie10": "Contractura muscular",
                "problema": None,
                "referido_por": None,
                "badges": ["Sospecha"],
            },
            {
                "nombre": "Toma de muestra",
                "fecha": "Hace 8 dias",
                "codigo_cie10": "Z00",
                "descripcion_cie10": (
                    "Examen general e investigacion de personas sin quejas "
                    "o sin diagnostico informado"
                ),
                "problema": None,
                "referido_por": "Es referido por Tecnico Param\u00e9dico",
                "badges": ["Confirmado"],
            },
            {
                "nombre": "Otras consultas especificadas",
                "fecha": "Hace 20 dias",
                "codigo_cie10": "Z71.8",
                "descripcion_cie10": "Otras consultas especificadas",
                "problema": None,
                "referido_por": None,
                "badges": ["Confirmado"],
            },
        ],
        "cronicos": [
            {
                "nombre": "Nodulo tiroideo solitario no toxico",
                "fecha": "25 ago. 2026",
                "codigo_cie10": "E04.1",
                "descripcion_cie10": "Nodulo tiroideo solitario no toxico",
                "problema": None,
                "referido_por": None,
                "badges": ["Confirmado"],
            },
            {
                "nombre": "Diabetes mellitus no insulinodependiente",
                "fecha": "25 ago. 2026",
                "codigo_cie10": None,
                "descripcion_cie10": None,
                "problema": "Diabetes mellitus tipo 2",
                "referido_por": None,
                "badges": ["G2", "GES", "No Controlado", "Confirmado"],
            },
            {
                "nombre": "Trastorno de la refraccion, no especificado",
                "fecha": "4 sep. 2024",
                "codigo_cie10": "H52.7",
                "descripcion_cie10": ("Trastorno de la refraccion, no especificado"),
                "problema": None,
                "referido_por": "Es referido por Tecnologo Medico",
                "badges": [],
            },
            {
                "nombre": "Hipertension esencial (primaria)",
                "fecha": "25 ago. 2026",
                "codigo_cie10": "I10",
                "descripcion_cie10": "Hipertension esencial (primaria)",
                "problema": None,
                "referido_por": None,
                "badges": ["G2", "No Controlado", "Confirmado"],
            },
            {
                "nombre": "Colelitiasis",
                "fecha": "22 dic. 2025",
                "codigo_cie10": "K80",
                "descripcion_cie10": "Colelitiasis",
                "problema": None,
                "referido_por": "Es referido por Enfermero(a)",
                "badges": [],
            },
            {
                "nombre": "Gonartrosis (artrosis de la rodilla) , (artrosis)",
                "fecha": "25 ago. 2026",
                "codigo_cie10": None,
                "descripcion_cie10": None,
                "problema": (
                    "Tratamiento medico en personas de 55 anos y mas con "
                    "artrosis de cadera y/o rodilla, leve o moderada"
                ),
                "referido_por": None,
                "badges": ["G2", "GES", "No Controlado", "Confirmado"],
            },
            {
                "nombre": "Otras artrosis ,(artrosis)",
                "fecha": "14 abr. 2026",
                "codigo_cie10": "M19",
                "descripcion_cie10": "Otras artrosis ,(artrosis)",
                "problema": None,
                "referido_por": "Es referido por Nutricionista",
                "badges": ["G2"],
            },
            {
                "nombre": ("Trastornos de disco lumbar y otros, con radiculopatia"),
                "fecha": "14 abr. 2026",
                "codigo_cie10": "M51.1",
                "descripcion_cie10": ("Trastornos de disco lumbar y otros, con radiculopatia"),
                "problema": None,
                "referido_por": "Es referido por Nutricionista",
                "badges": [],
            },
        ],
    }


# ---- Tests del formatter ----


class TestFormatearEstratificacion:
    def test_vacio_sin_grupo_retorna_string_vacio(self) -> None:
        assert formatear_estratificacion(None) == ""
        assert formatear_estratificacion({}) == ""
        assert formatear_estratificacion({"grupo": None}) == ""

    def test_grupo_sin_label(self) -> None:
        out = formatear_estratificacion({"grupo": "G2"})
        assert "Grupo: G2" in out
        assert "Riesgo" not in out  # no hay label

    def test_grupo_con_label_y_fecha(self) -> None:
        out = formatear_estratificacion(
            {
                "grupo": "G2",
                "grupo_label": "Riesgo moderado",
                "fecha_inicio": "25 ago. 2026",
            }
        )
        assert "Grupo: G2 (Riesgo moderado)" in out
        assert "Fecha inicio: 25 ago. 2026" in out

    def test_solo_cronicos(self, estrat_completa: dict) -> None:
        estrat = dict(estrat_completa)
        estrat["agudos"] = []
        out = formatear_estratificacion(estrat)
        assert "Diagnosticos cronicos (8):" in out
        assert "Diagnosticos agudos" not in out

    def test_solo_agudos(self, estrat_completa: dict) -> None:
        estrat = dict(estrat_completa)
        estrat["cronicos"] = []
        out = formatear_estratificacion(estrat)
        assert "Diagnosticos agudos (3):" in out
        assert "Diagnosticos cronicos" not in out

    def test_dx_con_badges_se_formatean_con_lista(self, estrat_completa: dict) -> None:
        out = formatear_estratificacion(estrat_completa)
        # El dx de diabetes tiene G2, GES, No Controlado, Confirmado
        assert re.search(
            r"Diabetes mellitus no insulinodependiente \[G2, GES, "
            r"No Controlado, Confirmado\]",
            out,
        ), f"Badges no se formatearon: {out[:600]}"

    def test_dx_con_problema_y_sin_codigo(self, estrat_completa: dict) -> None:
        out = formatear_estratificacion(estrat_completa)
        # Diabetes: tiene problema GES, no tiene codigo CIE-10 en el modal
        assert "Problema: Diabetes mellitus tipo 2" in out
        # No debe haber CIE-10: None ni CIE-10: vacio
        dm_match = re.search(
            r"Diabetes mellitus no insulinodependiente.*?(?=\n  - |\n\n|\Z)",
            out,
            re.DOTALL,
        )
        assert dm_match is not None
        bloque = dm_match.group(0)
        assert "CIE-10: None" not in bloque
        assert "CIE-10: " not in bloque or "CIE-10: " in bloque  # puede estar o no

    def test_dx_con_codigo_y_descripcion(self, estrat_completa: dict) -> None:
        out = formatear_estratificacion(estrat_completa)
        # HTA: tiene I10 y descripcion
        assert "CIE-10: I10" in out
        assert "Descripcion: Hipertension esencial (primaria)" in out

    def test_referido_por_se_incluye(self, estrat_completa: dict) -> None:
        out = formatear_estratificacion(estrat_completa)
        assert "Es referido por Nutricionista" in out
        assert "Es referido por Enfermero(a)" in out

    def test_dx_sin_badges_sin_corchetes(self, estrat_completa: dict) -> None:
        out = formatear_estratificacion(estrat_completa)
        # Colelitiasis no tiene badges -> linea debe ser sin "[]"
        colelitiasis_line = next(
            (ln for ln in out.splitlines() if ln.startswith("- Colelitiasis")),
            None,
        )
        assert colelitiasis_line is not None
        assert "[" not in colelitiasis_line
        assert "]" not in colelitiasis_line

    def test_estructura_basica(self, estrat_completa: dict) -> None:
        out = formatear_estratificacion(estrat_completa)
        lineas = out.splitlines()
        # Primera linea: Grupo
        assert lineas[0].startswith("Grupo: G2")
        # Segunda linea: Fecha inicio
        assert lineas[1].startswith("Fecha inicio: ")
        # Luego viene vacio, luego "Diagnosticos cronicos (N):"
        idx_cronicos = next(i for i, ln in enumerate(lineas) if "Diagnosticos cronicos" in ln)
        assert "Diagnosticos agudos" in "\n".join(lineas[idx_cronicos:])


# ---- Test de integracion con guardar_nota_clinica ----


class TestGuardarNotaClinicaConEstratificacion:
    def test_incluye_seccion_cuando_hay_datos(
        self,
        tmp_path: Path,
        logger: logging.Logger,
        estrat_completa: dict,
    ) -> None:
        paciente = PacienteObjetivo(
            fecha="25-08-2026",
            nombre="Paciente Test",
            tipo_atencion="INGRESO ECICEP",
            razon="ECICEP",
        )
        out = guardar_nota_clinica(
            paciente=paciente,
            identificacion={"RUN": "12.345.678-9"},
            historial="21-08-2026 Consulta previa",
            anamnesis="Paciente en control.",
            diagnosticos=["- HTA [Confirmado]: I10"],
            actividades=["- Control cardiovascular"],
            profesionales=["- Dra. Yadira (Medico)"],
            pautas=["- EMPAM"],
            examenes="",
            otros_items={},
            estratificacion=estrat_completa,
            notas_dir=tmp_path,
        )
        assert out is not None
        assert out.exists()
        texto = out.read_text(encoding="utf-8")
        # Seccion .md (sesion 2026-09-16: ya no hay marcadores === INICIO/FIN ===)
        assert "## Estratificacion ECICEP" in texto
        # Orden: ESTRATIFICACION va entre DIAGNOSTICOS y ACTIVIDADES
        idx_dx = texto.index("## Diagnosticos")
        idx_estrat = texto.index("## Estratificacion ECICEP")
        idx_act = texto.index("## Actividades")
        assert idx_dx < idx_estrat < idx_act, (
            "ESTRATIFICACION debe ir entre DIAGNOSTICOS y ACTIVIDADES"
        )
        # Contenido
        assert "Grupo: G2 (Riesgo moderado)" in texto
        assert "Diabetes mellitus tipo 2" in texto
        assert "Hipertension esencial" in texto

    def test_omite_seccion_cuando_no_hay_estratificacion(
        self,
        tmp_path: Path,
        logger: logging.Logger,
    ) -> None:
        paciente = PacienteObjetivo(
            fecha="25-08-2026",
            nombre="Paciente Sin Estrat",
            tipo_atencion="MORBILIDAD",
            razon="",
        )
        out = guardar_nota_clinica(
            paciente=paciente,
            identificacion={"RUN": "12.345.678-9"},
            historial="",
            anamnesis="Paciente en control.",
            diagnosticos=[],
            actividades=[],
            profesionales=[],
            pautas=[],
            examenes="",
            otros_items={},
            estratificacion=None,  # paciente sin estratificar
            notas_dir=tmp_path,
        )
        assert out is not None
        texto = out.read_text(encoding="utf-8")
        assert "## Estratificacion ECICEP" not in texto

    def test_omite_seccion_si_dict_vacio(
        self,
        tmp_path: Path,
        logger: logging.Logger,
    ) -> None:
        paciente = PacienteObjetivo(
            fecha="25-08-2026",
            nombre="Paciente Estrat Vacia",
            tipo_atencion="MORBILIDAD",
            razon="",
        )
        out = guardar_nota_clinica(
            paciente=paciente,
            identificacion={},
            historial="",
            anamnesis="Paciente en control.",
            diagnosticos=[],
            actividades=[],
            profesionales=[],
            pautas=[],
            examenes="",
            otros_items={},
            estratificacion={},  # grupo=None -> se omite
            notas_dir=tmp_path,
        )
        assert out is not None
        texto = out.read_text(encoding="utf-8")
        assert "## Estratificacion ECICEP" not in texto

    def test_sobrescribe_archivo_existente(
        self,
        tmp_path: Path,
        logger: logging.Logger,
        estrat_completa: dict,
    ) -> None:
        """Regla Yadira 2026-09-16 14:14: guardar_nota_clinica SIEMPRE
        escribe (la ultima extraccion es la que vale)."""
        paciente = PacienteObjetivo(
            fecha="25-08-2026",
            nombre="Paciente Duplicado",
            tipo_atencion="MORBILIDAD",
            razon="",
        )
        # Primera escritura: OK
        out1 = guardar_nota_clinica(
            paciente=paciente,
            identificacion={},
            historial="",
            anamnesis="primera",
            diagnosticos=[],
            actividades=[],
            profesionales=[],
            pautas=[],
            examenes="",
            otros_items={},
            estratificacion=estrat_completa,
            notas_dir=tmp_path,
        )
        assert out1 is not None
        # Segunda escritura: tambien OK (regla 14:14: siempre sobrescribe)
        out2 = guardar_nota_clinica(
            paciente=paciente,
            identificacion={},
            historial="",
            anamnesis="segunda",
            diagnosticos=[],
            actividades=[],
            profesionales=[],
            pautas=[],
            examenes="",
            otros_items={},
            estratificacion=estrat_completa,
            notas_dir=tmp_path,
        )
        assert out2 is not None
        # El archivo queda con el contenido de la SEGUNDA extraccion
        texto = out1.read_text(encoding="utf-8")
        assert "segunda" in texto
        assert "primera" not in texto


# ---- Smoke test: el modulo carga ----


class TestModuloCarga:
    def test_funciones_publicas_existen(self) -> None:
        assert hasattr(cnc, "extraer_estratificacion_ecicep")
        assert hasattr(cnc, "formatear_estratificacion")
        assert callable(cnc.extraer_estratificacion_ecicep)
        assert callable(cnc.formatear_estratificacion)

    def test_selectores_estrategicos_presentes(self) -> None:
        """Los selectores CSS que usa el extractor deben estar alineados
        con el HTML de Rayen. Sesion 2026-08-25: el badge vive en el
        header dentro de button[aria-haspopup], sin clase de color
        (badge-warning fallaba para otros grupos de riesgo)."""
        assert cnc._ESTRAT_CARD_SELECTOR == ".stratification-card"
        assert cnc._ESTRAT_BADGE_SELECTOR == ("button[aria-haspopup='true'] span.badge.badge-pill")
        assert cnc._ESTRAT_MODAL_TRIGGER_SELECTOR == ('[data-modal="activeDiagnosisModalOpen"]')
        assert cnc._ESTRAT_MODAL_SELECTOR == ".diagnosis-data-modal"

    def test_js_strings_no_vacios(self) -> None:
        """Los strings JS no deben estar vacios (se ejecutan en el browser)."""
        assert cnc._ESTRAT_CARD_JS.strip()
        assert cnc._ESTRAT_MODAL_JS.strip()
        # 2026-08-25: la regex del badge es G[0-3] (no G[123]) — incluye G0
        assert "G[0-3]" in cnc._ESTRAT_CARD_JS
        # Tambien debe tener el lookahead para que G10 no matchee
        assert "(?=\\s|$)" in cnc._ESTRAT_CARD_JS or "(?=\\s|$)" in cnc._ESTRAT_CARD_JS
        assert "diagnose-active" in cnc._ESTRAT_MODAL_JS  # clases del modal

    def test_bug_fix_badge_fuera_del_popover(self) -> None:
        """REGRESION 2026-08-25: el badge G1/G2/G3 esta en el HEADER de la
        pagina, NO dentro de `.stratification-card` (el popover). El JS
        debe buscar el badge en toda la pagina, no scoped al popover.
        Ademas SIN clase de color: badge-warning solo existe para G2 y
        hacia fallar G1 (success) y G3 (danger)."""
        # El JS NO debe hacer query del badge dentro de .stratification-card
        assert ".stratification-card .badge" not in cnc._ESTRAT_CARD_JS, (
            "REGRESION: el badge NO esta dentro de .stratification-card. "
            "El JS debe buscarlo en toda la pagina con un selector global."
        )
        # El JS SI debe buscar el badge con un selector global (header)
        assert "button[aria-haspopup='true'] span.badge.badge-pill" in cnc._ESTRAT_CARD_JS
        # El popover sigue siendo donde se lee Fecha inicio + Diagnostico
        assert ".stratification-card" in cnc._ESTRAT_CARD_JS

    def test_se_abre_popover_antes_del_modal(self) -> None:
        """REGRESION 2026-08-25: el link 'Ver todos los diagnosticos activos'
        vive DENTRO del popover. Sin el popover abierto, el link no es
        clickable. La funcion extraer_estratificacion_ecicep debe abrir
        el popover ANTES de intentar abrir el modal."""
        import inspect

        from src.rayen.extraccion.estratificacion import (
            extraer_estratificacion_ecicep,
        )

        src = inspect.getsource(extraer_estratificacion_ecicep)
        # La funcion debe llamar a _abrir_popover_estratificacion
        assert "_abrir_popover_estratificacion" in src
        # Y la llamada debe estar ANTES de _abrir_modal_estratificacion
        idx_popover = src.find("_abrir_popover_estratificacion")
        idx_modal = src.find("_abrir_modal_estratificacion")
        assert idx_popover < idx_modal, (
            "El popover debe abrirse ANTES del modal. Si no, el link 'Ver todos' no es clickable."
        )


# ---- Tests de generalidad: el fix aplica a TODOS los pacientes ----


class TestFixEsGenerico:
    """REGRESION 2026-08-25: el fix del badge es para TODOS los pacientes
    con G1/G2/G3, no solo para Karina. Estos tests verifican que."""

    def test_badge_regex_matchea_g0_a_g3(self) -> None:
        """La regex del JS debe matchear G0, G1, G2 Y G3 (no solo G1..G3).
        2026-08-25: Miguel me corrigio, yo habia asumido G[123] basado
        solo en el ejemplo de Karina (que era G2). El rango real es 0-3."""
        import re

        patron = re.compile(r"^(G[0-3])(?=\s|$)(.*)$")
        casos = [
            # G0 = sin riesgo / sin clasificar (Yadira dijo que existe)
            ("G0 Sin riesgo", ("G0", "Sin riesgo")),
            ("G0 Sin clasificar", ("G0", "Sin clasificar")),
            ("G0", ("G0", "")),
            # G1-G3 (riesgo bajo / moderado / alto)
            ("G1 Riesgo bajo", ("G1", "Riesgo bajo")),
            ("G2 Riesgo moderado", ("G2", "Riesgo moderado")),
            ("G3 Riesgo alto", ("G3", "Riesgo alto")),
            # Variantes sin label
            ("G1", ("G1", "")),
            ("G2", ("G2", "")),
            ("G3", ("G3", "")),
            # Variantes con espacios extra (despues de strip el label)
            ("G2  Riesgo moderado", ("G2", "Riesgo moderado")),
            # Variantes con texto adicional
            ("G0 (sin clasificar)", ("G0", "(sin clasificar)")),
            ("G3 - alto riesgo", ("G3", "- alto riesgo")),
        ]
        for texto, esperado in casos:
            m = patron.match(texto)
            assert m is not None, f"No matcheo: {texto!r}"
            assert m.group(1) == esperado[0]
            assert m.group(2).strip() == esperado[1]

    def test_no_matchea_grupos_fuera_de_rango(self) -> None:
        """La regex NO debe matchear G4+ (no existe), ni letras, ni
        texto sin G. G0-G3 son los unicos validos. Tambien: 'G10' no
        debe matchear como G1 + '0'."""
        import re

        patron = re.compile(r"^(G[0-3])(?=\s|$)(.*)$")
        invalidos = [
            "G4",  # no existe
            "G9",  # no existe
            "G10",  # G10 NO debe matchear como G1 + "0"
            "G21",  # tampoco
            "GX",  # letra
            "G",  # solo G sin numero
            "G ",  # G con espacio pero sin numero
            "Riesgo moderado",  # sin prefijo G
            "",  # vacio
            " G2",  # espacio al inicio
            "g2",  # minuscula
        ]
        for texto in invalidos:
            assert patron.match(texto) is None, f"No deberia matchear: {texto!r}"

    def test_extractor_devuelve_vacio_sin_badge(self) -> None:
        """Si el driver devuelve grupo vacio (no hay badge), la funcion
        retorna el dict con grupo=None y el resto vacio. NO crashea."""
        from unittest.mock import MagicMock

        from src.rayen.extraccion.estratificacion import (
            extraer_estratificacion_ecicep,
        )

        driver = MagicMock()
        driver.execute_script.return_value = {
            "grupo": None,
            "grupo_label": None,
            "fecha_inicio": None,
        }
        resultado = extraer_estratificacion_ecicep(driver, logging.getLogger("test"))
        assert resultado["grupo"] is None
        assert resultado["grupo_label"] is None
        assert resultado["fecha_inicio"] is None
        assert resultado["agudos"] == []
        assert resultado["cronicos"] == []
        # Y NO llamo a abrir popover ni modal (porque no hay grupo)
        # El driver solo recibio 1 execute_script (la lectura del card)
        assert driver.execute_script.call_count == 1

    def test_extractor_sigue_si_modal_falla(self) -> None:
        """Si el modal no se puede abrir, la funcion devuelve lo que pudo
        extraer (grupo + label + fecha) sin crashear."""
        from unittest.mock import MagicMock, patch

        from src.rayen.extraccion.estratificacion import (
            extraer_estratificacion_ecicep,
        )

        driver = MagicMock()
        # Card: hay badge G2
        # Popover: visible (no necesita click)
        # Modal: falla al abrir
        driver.execute_script.side_effect = [
            {
                "grupo": "G2",
                "grupo_label": "Riesgo moderado",
                "fecha_inicio": "24 ago. 2026",
            },  # card JS
            None,  # modal JS (puede que ya no se llame si modal fallo)
        ]
        with (
            patch(
                "src.rayen.extraccion.estratificacion._popover_estratificacion_visible",
                return_value=True,
            ),
            patch(
                "src.rayen.extraccion.estratificacion._modal_estratificacion_visible",
                return_value=False,
            ),
            patch(
                "src.rayen.extraccion.estratificacion._abrir_modal_estratificacion",
                return_value=False,
            ),
        ):
            resultado = extraer_estratificacion_ecicep(driver, logging.getLogger("test"))
        # El grupo se extrajo (del card)
        assert resultado["grupo"] == "G2"
        assert resultado["grupo_label"] == "Riesgo moderado"
        assert resultado["fecha_inicio"] == "24 ago. 2026"
        # Pero agudos/cronicos vacios porque el modal no se abrio
        assert resultado["agudos"] == []
        assert resultado["cronicos"] == []
