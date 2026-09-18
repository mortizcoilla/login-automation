"""Tests para `filtrar_historial_ultimos_6_meses` en crear_notas_clinicas.py.

Regla del proyecto: en la construccion de la nota clinica, el historial de
atenciones se filtra a solo los ultimos 6 meses respecto a la fecha objetivo
de la atencion. Esto reduce ruido y mantiene contexto clinico relevante.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest

from src.rayen.extraccion.historial import (
    _fecha_meses_atras,
    filtrar_historial_ultimos_6_meses,
)

# --- Helpers -----------------------------------------------------------------


def _h(*entradas: str) -> str:
    """Construye un historial en el formato que produce el JS de Rayen."""
    return "\n---\n".join(entradas)


# --- Tests del helper de aritmetica de fechas --------------------------------


class TestFechaMesesAtras:
    """Aritmetica de meses con wrap de ano y clamping de dia."""

    def test_seis_meses_exactos(self) -> None:
        # 25-08-2026 - 6 meses = 25-02-2026 (mismo ano, no anterior)
        assert _fecha_meses_atras(date(2026, 8, 25), 6) == date(2026, 2, 25)

    def test_wrap_de_ano(self) -> None:
        # 15-01-2026 - 6 meses -> 15-07-2025 (cruza ano)
        assert _fecha_meses_atras(date(2026, 1, 15), 6) == date(2025, 7, 15)

    def test_clamp_dia_cuando_mes_destino_es_corto(self) -> None:
        # 31-05-2026 - 6 meses -> 30-11-2025 (Nov tiene 30 dias)
        assert _fecha_meses_atras(date(2026, 5, 31), 6) == date(2025, 11, 30)

    def test_clamp_dia_febrero(self) -> None:
        # 31-03-2026 - 6 meses -> 28-02-2026 (Feb 2026 tiene 28 dias, no bisiesto)
        assert _fecha_meses_atras(date(2026, 3, 31), 6) == date(2025, 9, 30)

    def test_un_mes(self) -> None:
        assert _fecha_meses_atras(date(2026, 8, 25), 1) == date(2026, 7, 25)


# --- Tests del filtro --------------------------------------------------------


class TestFiltrarHistorial6Meses:
    """Filtra historial de atenciones a los ultimos 6 meses."""

    def test_caso_real_almendra_25_08_2026(self) -> None:
        """Caso real: 4 entradas, 2 dentro de 6 meses, 2 fuera."""
        h = _h(
            "25-08-2026 16:18 Atencion no completada Rinofaringitis aguda (Sospecha)",
            "02-07-2026 16:03 Atencion para la anticoncepcion (Confirmada)",
            "04-09-2025 09:57 Atencion para la anticoncepcion (Confirmada)",
            "28-08-2025 09:09 Otras atenciones especificadas (Confirmada)",
        )
        r = filtrar_historial_ultimos_6_meses(h, "25-08-2026")
        assert "25-08-2026" in r
        assert "02-07-2026" in r
        assert "04-09-2025" not in r
        assert "28-08-2025" not in r

    def test_borde_inclusivo_seis_meses(self) -> None:
        """Una atencion exactamente 6 meses antes se CONSERVA (>=)."""
        h = _h("25-02-2026 10:00 Atencion a 6 meses exactos")
        # Fecha objetivo 25-08-2026: el corte es 25-02-2026 (inclusivo)
        r = filtrar_historial_ultimos_6_meses(h, "25-08-2026")
        assert "25-02-2026" in r

    def test_dia_despues_del_corte_se_descarta(self) -> None:
        """Una atencion 6 meses + 1 dia antes se descarta."""
        h = _h("24-02-2026 10:00 Atencion a 6 meses y 1 dia")
        r = filtrar_historial_ultimos_6_meses(h, "25-08-2026")
        assert "24-02-2026" not in r

    def test_todas_fuera_de_ventana(self) -> None:
        """Si todo el historial es antiguo, devuelve mensaje neutro."""
        h = _h(
            "01-01-2020 10:00 Atencion vieja 1",
            "15-06-2019 10:00 Atencion vieja 2",
        )
        r = filtrar_historial_ultimos_6_meses(h, "25-08-2026")
        assert r == "(sin atenciones en los ultimos 6 meses)"

    def test_vacio_se_conserva(self) -> None:
        """Historial vacio pasa tal cual (no es error del filtro)."""
        assert filtrar_historial_ultimos_6_meses("", "25-08-2026") == ""

    def test_placeholder_se_conserva(self) -> None:
        """Placeholders del tipo '(no se pudo...)' pasan tal cual, no se filtran."""
        for placeholder in [
            "(no se pudo extraer el historial)",
            "(sin historial)",
            "No tiene historial",
        ]:
            r = filtrar_historial_ultimos_6_meses(placeholder, "25-08-2026")
            assert r == placeholder, f"Placeholder no conservado: {placeholder!r}"

    def test_linea_sin_fecha_parseable_se_conserva(self) -> None:
        """Lineas sin fecha dd-mm-yyyy al inicio se conservan (conservador:
        no destruimos data por parsing)."""
        h = _h(
            "Texto sin fecha al inicio - dato importante",
            "01-01-2020 10:00 Atencion vieja",
        )
        r = filtrar_historial_ultimos_6_meses(h, "25-08-2026")
        # La linea sin fecha se conserva aunque la otra sea vieja
        assert "Texto sin fecha" in r
        # La vieja se filtra
        assert "01-01-2020" not in r

    def test_fecha_objetivo_invalida_pasa_tal_cual(self) -> None:
        """Si fecha_objetivo no parsea, no se filtra (no romper por parsing)."""
        h = _h("01-01-2020 10:00 Vieja", "25-08-2026 10:00 Reciente")
        r = filtrar_historial_ultimos_6_meses(h, "esto-no-es-fecha")
        # Sin filtro: pasa todo
        assert "01-01-2020" in r
        assert "25-08-2026" in r

    def test_log_informa_cantidad_filtrada(self, caplog: pytest.LogCaptureFixture) -> None:
        """El log indica cuantas entradas quedaron y cuantas se descartaron."""
        h = _h(
            "25-08-2026 10:00 Reciente",
            "01-01-2020 10:00 Antigua",
        )
        # caplog capta del root, pero `crear_notas_clinicas` es un logger
        # con propagate=False por defecto en algunos proyectos. Forzamos
        # capture a nivel root para que pytest lo vea.
        cnc_logger = logging.getLogger("crear_notas_clinicas")
        prev_propagate = cnc_logger.propagate
        cnc_logger.propagate = True
        try:
            with caplog.at_level(logging.INFO):
                filtrar_historial_ultimos_6_meses(h, "25-08-2026", logger=cnc_logger)
            assert any(
                "ultimos 6 meses" in rec.message and "1 anteriores descartadas" in rec.message
                for rec in caplog.records
            ), f"Log no emitido. Records: {[r.message for r in caplog.records]}"
        finally:
            cnc_logger.propagate = prev_propagate

    def test_separador_doble_guion_se_respeta(self) -> None:
        """El output mantiene el separador '\\n---\\n' entre entradas."""
        h = _h(
            "25-08-2026 10:00 A",
            "20-08-2026 10:00 B",
        )
        r = filtrar_historial_ultimos_6_meses(h, "25-08-2026")
        assert "\n---\n" in r
        # Solo 2 lineas (no se anade separador extra al final)
        assert r.count("---") == 1
