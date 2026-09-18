"""Tests del parser unificado del informe (src/informes/parser.py).

REQ-043: disambiguacion de 8 columnas (layout deprecado vs actual).
REQ-053: bugfix del layout actual de 5 columnas (Edad en parts[2]).
"""

from __future__ import annotations

from pathlib import Path

from src.informes.parser import (
    parsear_filas_enriquecidas,
    parsear_linea_informe,
    parsear_pacientes_objetivo,
)


def _escribir(tmp_path: Path, contenido: str) -> Path:
    f = tmp_path / "informe.txt"
    f.write_text(contenido, encoding="utf-8")
    return f


class TestLayoutActual:
    """5 columnas: Fecha|Nombre|Edad|Tipo|Motivo (REQ-053)."""

    def test_cinco_columnas_mapea_bien(self) -> None:
        fila = parsear_linea_informe("10-09-2026    Nicolas Piña    (-)    Control integral    (-)")
        assert fila is not None
        assert fila["nombre"] == "Nicolas Piña"
        assert fila["tipo_atencion"] == "Control integral"  # no "(-)" (REQ-053)
        assert fila["motivo"] == "(-)"

    def test_cinco_columnas_con_edad_real(self) -> None:
        fila = parsear_linea_informe(
            "10-09-2026    Juan Perez    40,19    Morbilidad    control ht"
        )
        assert fila is not None
        assert fila["tipo_atencion"] == "Morbilidad"
        assert fila["motivo"] == "control ht"

    def test_pacientes_objetivo_razon_es_motivo(self, tmp_path: Path) -> None:
        f = _escribir(tmp_path, "10-09-2026    Juan Perez    (-)    Morbilidad    control ht\n")
        pacs = parsear_pacientes_objetivo(f)
        assert len(pacs) == 1
        assert pacs[0].tipo_atencion == "Morbilidad"
        assert pacs[0].razon == "control ht"

    def test_prefijo_prioridad_se_quita(self) -> None:
        fila = parsear_linea_informe(
            "10-09-2026    (Atención preferente) Juan Perez    (-)    Control    (-)"
        )
        assert fila is not None
        assert fila["nombre"] == "Juan Perez"


class TestLayoutsLegacy:
    def test_cuatro_columnas(self) -> None:
        fila = parsear_linea_informe("10-09-2026    Juan Perez    Control    CONTROL INTEGRAL")
        assert fila is not None
        assert fila["tipo_atencion"] == "Control"
        assert fila["plantilla"] == "CONTROL INTEGRAL"

    def test_seis_columnas(self) -> None:
        fila = parsear_linea_informe(
            "10-09-2026    Juan Perez    (-)    Control    control sm    CONTROL"
        )
        assert fila is not None
        assert fila["tipo_atencion"] == "Control"
        assert fila["motivo"] == "control sm"
        assert fila["plantilla"] == "CONTROL"

    def test_siete_columnas(self) -> None:
        fila = parsear_linea_informe(
            "10-09-2026    Juan Perez    (-)    Control    control sm    no    si"
        )
        assert fila is not None
        assert fila["tipo_atencion"] == "Control"
        assert fila["motivo"] == "control sm"


class TestOchoColumnasDisambiguacion:
    """REQ-043: el layout de 8 cols se decide por parts[3]."""

    def test_layout_actual_8_cols(self) -> None:
        # parts[3] = Tipo (texto) -> layout actual del paso 6
        fila = parsear_linea_informe(
            "10-09-2026    Juan Perez    40,19    Control    control sm    si    no    no"
        )
        assert fila is not None
        assert fila["tipo_atencion"] == "Control"
        assert fila["motivo"] == "control sm"

    def test_layout_deprecado_8_cols(self) -> None:
        # parts[3] = edad decimal -> layout 17:26 deprecado
        fila = parsear_linea_informe(
            "10-09-2026    Juan Perez    40 anos 2 meses    40,19    Control"
            "    control sm    si    no"
        )
        assert fila is not None
        assert fila["tipo_atencion"] == "Control"
        assert fila["motivo"] == "control sm"

    def test_doble_corrida_paso6_no_corrompe(self, tmp_path: Path) -> None:
        """REQ-043 (regresion): re-parsear la salida enriquecida de 8 cols
        conserva tipo y motivo (antes tipo='control sm', motivo='si')."""
        salida_paso6 = (
            "10-09-2026    Juan Perez    40,19    Morbilidad    control ht    si    no    no\n"
        )
        f = _escribir(tmp_path, salida_paso6)
        filas = parsear_filas_enriquecidas(f)
        assert len(filas) == 1
        assert filas[0]["tipo_atencion"] == "Morbilidad"
        assert filas[0]["motivo"] == "control ht"
        assert filas[0]["edad"] is None  # siempre re-derivada


class TestLineasInvalidas:
    def test_header_y_separadores_ignorados(self) -> None:
        assert parsear_linea_informe("INFORME DE FICHAS ABIERTAS") is None
        assert parsear_linea_informe("------------------------") is None
        assert parsear_linea_informe("") is None

    def test_fecha_invalida(self) -> None:
        assert parsear_linea_informe("x   y   z   w   v") is None

    def test_archivo_inexistente_devuelve_vacio(self, tmp_path: Path) -> None:
        assert parsear_pacientes_objetivo(tmp_path / "no.txt") == []
        assert parsear_filas_enriquecidas(tmp_path / "no.txt") == []
