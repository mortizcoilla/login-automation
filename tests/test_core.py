"""Tests de src/core/: fechas, nombres, tipos_atencion, rutas (Fase 2).

REQ-012/016 (convenciones de nombre y matching), REQ-037 (sanitizacion),
REQ-011 (paths de informes, aislamiento mensual/anual).
"""

from __future__ import annotations

from datetime import date

import pytest

from src.core.fechas import DATE_FORMAT, es_fecha_valida, fecha_hoy_str, parsear_fecha
from src.core.nombres import nombre_a_filename, normalizar_texto, safe_filename
from src.core.rutas import (
    ANALISIS_DIR,
    EXAMENES_CRUDOS_DIR,
    NOTAS_DIR,
    ROOT,
    informe_anual_path,
    informe_mes_actual_path,
)
from src.core.tipos_atencion import sanitizar_tipo

# ---------------------------------------------------------------------------
# core.fechas
# ---------------------------------------------------------------------------


class TestFechas:
    def test_formato_constante(self) -> None:
        assert DATE_FORMAT == "%d-%m-%Y"

    def test_fecha_valida(self) -> None:
        assert es_fecha_valida("16-09-2026") is True

    def test_mes_invalido_no_pasa(self) -> None:
        # Patron correcto pero mes 13 no existe: el patron solo no basta.
        assert es_fecha_valida("10-13-2026") is False

    def test_dia_invalido(self) -> None:
        assert es_fecha_valida("32-01-2026") is False

    def test_formato_wrong(self) -> None:
        assert es_fecha_valida("2026-09-16") is False
        assert es_fecha_valida("16/09/2026") is False
        assert es_fecha_valida("") is False

    def test_parsear_fecha(self) -> None:
        assert parsear_fecha("16-09-2026") == date(2026, 9, 16)

    def test_parsear_fecha_invalida_raise(self) -> None:
        with pytest.raises(ValueError):
            parsear_fecha("no-fecha")

    def test_fecha_hoy_str_formato(self) -> None:
        assert es_fecha_valida(fecha_hoy_str())


# ---------------------------------------------------------------------------
# core.nombres — DOS convenciones intencionalmente distintas
# ---------------------------------------------------------------------------


class TestNormalizarTexto:
    def test_quita_tildes_y_minusculas(self) -> None:
        assert normalizar_texto("Lucía Ñandú") == "lucia nandu"

    def test_colapsa_espacios(self) -> None:
        assert normalizar_texto("  Juan   Perez ") == "juan perez"

    def test_guion_bajo_es_espacio(self) -> None:
        assert normalizar_texto("Juan_Perez") == "juan perez"


class TestNombreAFilename:
    """Convencion examenes crudos (REQ-012): lowercase, sin tildes, '_'."""

    def test_basico(self) -> None:
        assert nombre_a_filename("Benedicto Alfonso Martin") == ("benedicto_alfonso_martin")

    def test_tildes(self) -> None:
        assert nombre_a_filename("Lucía Adela Zambrano") == "lucia_adela_zambrano"


class TestSafeFilename:
    """Convencion notas/info/anam (REQ-002/027/028): conserva caso y tildes."""

    def test_conserva_mayusculas_y_tildes(self) -> None:
        assert safe_filename("Nicolás Ignacio Piña Rojas") == ("Nicolás_Ignacio_Piña_Rojas")

    def test_limpia_parentesis_y_comas(self) -> None:
        assert safe_filename("Juan (a) Perez, Jr.") == "Juan_a_Perez_Jr"

    def test_espacios_multiples(self) -> None:
        assert safe_filename("Maria   Del  Carmen") == "Maria_Del_Carmen"

    def test_compatibilidad_con_notas_existentes(self) -> None:
        # Regresion: los archivos reales de data/notas_clinicas conservan
        # tildes en el filename (ej. Lucía_Adela_Zambrano_Quintana_14-09-2026.md).
        assert safe_filename("Lucía Adela Zambrano Quintana") == ("Lucía_Adela_Zambrano_Quintana")


# ---------------------------------------------------------------------------
# core.tipos_atencion
# ---------------------------------------------------------------------------


class TestSanitizarTipo:
    """REQ-037: remueve prefijos de instrumento (ME, EN, PS, TO, NU, KT)."""

    def test_prefijo_me(self) -> None:
        assert sanitizar_tipo("ME, Control de nino sano") == "Control de nino sano"

    def test_prefijo_en(self) -> None:
        assert sanitizar_tipo("EN, Morbilidad") == "Morbilidad"

    def test_sin_prefijo(self) -> None:
        assert sanitizar_tipo("Control") == "Control"

    def test_vacio(self) -> None:
        assert sanitizar_tipo("") == ""

    def test_solo_espacios(self) -> None:
        assert sanitizar_tipo("   ") == ""


# ---------------------------------------------------------------------------
# core.rutas
# ---------------------------------------------------------------------------


class TestRutas:
    def test_root_apunta_al_repo(self) -> None:
        # ROOT es la raiz del repo: contiene pyproject.toml y src/.
        assert (ROOT / "pyproject.toml").exists()
        assert (ROOT / "src").is_dir()

    def test_dirs_de_datos_bajo_data(self) -> None:
        assert NOTAS_DIR == ROOT / "data" / "notas_clinicas"
        assert EXAMENES_CRUDOS_DIR == ROOT / "data" / "examenes_crudos"
        assert ANALISIS_DIR == ROOT / "data" / "analysis"

    def test_informe_mensual(self) -> None:
        assert informe_mes_actual_path(date(2026, 9, 18)).name == (
            "informe_fichas_abiertas_09-2026.txt"
        )

    def test_informe_anual(self) -> None:
        assert informe_anual_path(2026).name == ("informe_fichas_abiertas_2026_completo.txt")

    def test_mensual_y_anual_nunca_colisionan(self) -> None:
        """REQ-011: el aislamiento empieza por paths distintos SIEMPRE."""
        assert informe_mes_actual_path(date(2026, 9, 18)) != informe_anual_path(2026)

    def test_shim_informe_paths_reexporta(self) -> None:
        from src.analysis.informe_paths import (
            informe_anual_path as anual_shim,
        )
        from src.analysis.informe_paths import (
            informe_mes_actual_path as mensual_shim,
        )

        assert mensual_shim is informe_mes_actual_path
        assert anual_shim is informe_anual_path
