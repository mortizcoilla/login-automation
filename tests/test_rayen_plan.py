"""Tests de rayen.extraccion.plan: regla REQ-029 (tipo=Recetas).

REQ-029: si el tipo de atencion es "Recetas", la nota incluye SOLO la
prescripcion con la Vigencia mas reciente. Funciones puras, sin Selenium.
"""

from __future__ import annotations

from src.rayen.extraccion.plan import (
    _filtrar_receta_mas_reciente,
    _parsear_vigencia,
    _tipo_atencion_es_recetas,
)


class TestTipoAtencionEsRecetas:
    def test_recetas_simple(self) -> None:
        assert _tipo_atencion_es_recetas("Recetas") is True

    def test_recetas_con_espacios_y_mayusculas(self) -> None:
        assert _tipo_atencion_es_recetas("  RECETAS  ") is True

    def test_recetas_con_tilde(self) -> None:
        # Tilde en la 'e': el comparador normaliza NFD
        assert _tipo_atencion_es_recetas("Recétas") is True

    def test_otro_tipo(self) -> None:
        assert _tipo_atencion_es_recetas("Morbilidad") is False
        assert _tipo_atencion_es_recetas("Control") is False

    def test_none_y_vacio(self) -> None:
        assert _tipo_atencion_es_recetas(None) is False
        assert _tipo_atencion_es_recetas("") is False


class TestParsearVigencia:
    def test_formato_canonico(self) -> None:
        from datetime import date

        assert _parsear_vigencia("- [Cronica] Vigencia: 25 ago. 2027") == date(2027, 8, 25)

    def test_sin_punto_en_mes(self) -> None:
        from datetime import date

        assert _parsear_vigencia("Vigencia: 3 sept 2026") == date(2026, 9, 3)

    def test_sin_match(self) -> None:
        assert _parsear_vigencia("- Sertralina 50 mg") is None
        assert _parsear_vigencia("") is None


class TestFiltrarRecetaMasReciente:
    def test_una_sola_receta_pasa_igual(self) -> None:
        recetas = ["- [Cronica] Vigencia: 25 ago. 2027\n\t- Metformina"]
        assert _filtrar_receta_mas_reciente(recetas) == recetas

    def test_cero_recetas(self) -> None:
        assert _filtrar_receta_mas_reciente([]) == []

    def test_queda_la_vigencia_mas_reciente(self) -> None:
        vieja = "- [Cronica] Vigencia: 25 ago. 2026\n\t- Metformina 850"
        nueva = "- [Cronica] Vigencia: 25 ago. 2027\n\t- Metformina 1000"
        # Orden de extraccion: vieja primero, nueva despues
        assert _filtrar_receta_mas_reciente([vieja, nueva]) == [nueva]

    def test_desordenadas_queda_la_mas_reciente(self) -> None:
        vieja = "- [Aguda] Vigencia: 1 ene. 2026\n\t- Ibuprofeno"
        nueva = "- [Cronica] Vigencia: 1 dic. 2027\n\t- Enalapril"
        assert _filtrar_receta_mas_reciente([nueva, vieja]) == [nueva]

    def test_sin_fechas_parseables_cae_en_la_ultima(self) -> None:
        """Sin vigencia parseable, se asume la ULTIMA del orden de Rayen
        (suele ser la mas reciente)."""
        r1 = "- [Cronica]\n\t- Farmaco A"
        r2 = "- [Cronica]\n\t- Farmaco B"
        assert _filtrar_receta_mas_reciente([r1, r2]) == [r2]
