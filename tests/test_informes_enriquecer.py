from pathlib import Path


class TestColumnaMortadelo:
    """REQ-084: columna Mortadelo = si/no segun la existencia del bloque."""

    def test_bloque_sin_keywords_marca_mortadelo_si(self, tmp_path: Path) -> None:
        """El caso real: 'sugerencias para la psicologa' no cae en las
        3 keywords, pero el bloque EXISTE — la columna debe decir si."""
        from src.informes.enriquecer import _extraer_requerimientos

        nota = tmp_path / "nota.md"
        nota.write_text(
            "## Diagnosticos\n\n"
            "** mortadelo\n- Dame sugerencias para la psicologa\n",
            encoding="utf-8",
        )
        r = _extraer_requerimientos(nota)
        assert r["mortadelo"] is True
        assert r["examenes"] is False
        assert r["interconsulta"] is False
        assert r["indicaciones"] is False

    def test_sin_bloque_mortadelo_no(self, tmp_path: Path) -> None:
        from src.informes.enriquecer import _extraer_requerimientos

        nota = tmp_path / "nota.md"
        nota.write_text("## Diagnosticos\n\n- Control de salud estable\n", encoding="utf-8")
        r = _extraer_requerimientos(nota)
        assert r["mortadelo"] is False

    def test_tabla_incluye_columna_mortadelo(self) -> None:
        from src.informes.enriquecer import _formatear_tabla

        tabla = _formatear_tabla(
            [
                {
                    "fecha": "22-09-2026",
                    "nombre": "Test",
                    "edad": "30,0",
                    "tipo_atencion": "Consulta",
                    "motivo": "control",
                    "examenes": True,
                    "interconsulta": False,
                    "indicaciones": False,
                    "mortadelo": True,
                }
            ],
            "09-2026",
        )
        assert "Mortadelo" in tabla
        lineas_datos = [li for li in tabla.splitlines() if "22-09-2026" in li]
        assert lineas_datos, "fila de datos presente"
        # la celda mortadelo = si
        assert " si" in lineas_datos[0][-12:]


class TestFiltroTipoAtencion:
    """REQ-086: Morbilidad telefonica/presencial -> 'Morbilidad'."""

    def test_telefonica_y_presencial_se_colapsan(self) -> None:
        from src.informes.enriquecer import _normalizar_tipo_atencion

        assert _normalizar_tipo_atencion("Morbilidad telefónica") == "Morbilidad"
        assert _normalizar_tipo_atencion("Morbilidad presencial") == "Morbilidad"
        assert _normalizar_tipo_atencion("morbilidad TELEFÓNICA") == "Morbilidad"

    def test_otros_tipos_quedan_iguales(self) -> None:
        from src.informes.enriquecer import _normalizar_tipo_atencion

        assert (
            _normalizar_tipo_atencion("Control integral ecicep-g3")
            == "Control integral ecicep-g3"
        )
        assert _normalizar_tipo_atencion("Ingreso salud mental infantil") == (
            "Ingreso salud mental infantil"
        )
        assert _normalizar_tipo_atencion("") == ""
