"""Tests del extractor de receta cronica (REQ-104 fase 2).

Logica pura contra fixtures SINTETICOS del DOM mapeado por Miguel
(vueltas 9-17 del diseño: lineas "Receta Nro.", variantes de tilde/
prefijo/urgencia inline, hojas de farmaco con cola "de la Receta Nº").
Cero datos de pacientes reales. La suite NUNCA abre Rayen.
"""

from __future__ import annotations

import logging

from src.notas.nota_clinica import _texto_receta_cronica
from src.rayen.extraccion.receta_cronica import (
    ESTADO_ENCONTRADA,
    ESTADO_INDETERMINADO,
    extraer_receta_cronica,
    normalizar,
    parsear_lineas_receta,
    seleccionar_ganador,
    vincular_farmacos,
)

_LINEA_CRONICA_1 = (
    "(1) Receta Nro. 596039360, generada el 14-09-2026 12:13, tipo crónica , "
    "estado despachada , fecha de despacho: 15-09-2026"
)
_LINEA_CRONICA_2 = (
    "(2) Receta Nro. 596240871, generada el 15-09-2026 10:46, tipo crónica , "
    "estado despachada , fecha de despacho: 15-09-2026"
)
_LINEA_MORBILIDAD = (
    "Receta Nro. 596300000, generada el 20-09-2026 09:00, tipo morbilidad , "
    "estado despachada , fecha de despacho: 20-09-2026"
)
# Variante urgencia: inline, "Nro" SIN punto, estado con texto largo.
_LINEA_URGENCIA = (
    "Receta Nro 596400000, generada el 25-09-2026 11:30, tipo urgencia , "
    "estado cerrada en farmacia"
)
_HOJA_1 = (
    "Acetato de Medroxiprogesterona 104 mg/0,65 ml Suspension Inyectable , "
    "ampolla: 1 Ampolla cada 90 días por 90 días de la Receta Nº 596039360"
)
_HOJA_2 = (
    "Enalapril 10 mg comprimidos , 1 Comprimido cada 24 horas por 90 días "
    "de la Receta Nro. 596240871"
)


def _nodo(indice: int, fecha: str, *lineas: str) -> dict:
    return {"indice": indice, "fecha": fecha, "lineas": parsear_lineas_receta("\n".join(lineas))}


class TestNormalizar:
    def test_tildes_y_mayusculas(self) -> None:
        assert normalizar("Crónica") == "cronica"
        assert normalizar("  RECETA   Nro.  ") == "receta nro."


class TestParsearLineasReceta:
    def test_cronica_con_prefijo_y_tilde(self) -> None:
        [l1] = parsear_lineas_receta(_LINEA_CRONICA_1)
        assert l1["numero"] == "596039360"
        assert l1["tipo"] == "cronica"
        assert l1["generada"] == "14-09-2026 12:13"
        assert l1["estado"] == "despachada"
        assert l1["linea"] == _LINEA_CRONICA_1

    def test_variante_nro_sin_punto_urgencia_inline(self) -> None:
        [lu] = parsear_lineas_receta(_LINEA_URGENCIA)
        assert lu["numero"] == "596400000"
        assert lu["tipo"] == "urgencia"
        assert lu["estado"] == "cerrada en farmacia"

    def test_morbilidad(self) -> None:
        [lm] = parsear_lineas_receta(_LINEA_MORBILIDAD)
        assert lm["tipo"] == "morbilidad"

    def test_linea_sin_receta_no_parsea(self) -> None:
        assert parsear_lineas_receta("14-09-2026 12:05\nAnamnesis: control") == []

    def test_nodo_con_varias_lineas(self) -> None:
        texto = f"14-09-2026 12:05\n{_LINEA_CRONICA_1}\n{_LINEA_CRONICA_2}"
        lineas = parsear_lineas_receta(texto)
        assert [l["numero"] for l in lineas] == ["596039360", "596240871"]


class TestSeleccionarGanador:
    def test_la_cronica_mas_reciente_gana_aunque_haya_recetas_nuevas(self) -> None:
        nodo_cronicas = _nodo(0, "14-09-2026 12:05", _LINEA_CRONICA_1, _LINEA_CRONICA_2)
        nodo_morbilidad = _nodo(1, "20-09-2026 09:00", _LINEA_MORBILIDAD)
        nodo_urgencia = _nodo(2, "25-09-2026 11:30", _LINEA_URGENCIA)
        g = seleccionar_ganador([nodo_morbilidad, nodo_cronicas, nodo_urgencia])
        assert g is not None
        assert g["indice"] == 0, "la morbilidad (20-09) y urgencia (25-09) no desplazan"

    def test_ultima_cronica_del_nodo_participa(self) -> None:
        vieja = _nodo(0, "01-08-2026 08:00", "(1) Receta Nro. 111, generada el 01-08-2026 08:00, tipo crónica , estado caducada")
        nueva = _nodo(1, "14-09-2026 12:05", _LINEA_CRONICA_1)
        g = seleccionar_ganador([vieja, nueva])
        assert g is not None and g["indice"] == 1

    def test_estado_caducada_no_descarta(self) -> None:
        caducada = _nodo(0, "01-08-2026 08:00", "(1) Receta Nro. 111, generada el 01-08-2026 08:00, tipo crónica , estado caducada")
        g = seleccionar_ganador([caducada])
        assert g is not None, "el estado NO califica ni descarta (vuelta 10)"

    def test_sin_cronicas_devuelve_none(self) -> None:
        assert seleccionar_ganador([_nodo(0, "25-09-2026 11:30", _LINEA_URGENCIA)]) is None


class TestVincularFarmacos:
    def test_cada_farmaco_debajo_de_su_receta(self) -> None:
        cronicas = parsear_lineas_receta(f"{_LINEA_CRONICA_1}\n{_LINEA_CRONICA_2}")
        bloque = vincular_farmacos(cronicas, [_HOJA_1, _HOJA_2])
        assert bloque == [_LINEA_CRONICA_1, _HOJA_1, _LINEA_CRONICA_2, _HOJA_2]

    def test_hoja_sin_cola_viable_va_al_final(self) -> None:
        cronicas = parsear_lineas_receta(_LINEA_CRONICA_1)
        hoja_rara = "Farmaco sin cola de vinculo"
        bloque = vincular_farmacos(cronicas, [_HOJA_1, hoja_rara])
        assert bloque == [_LINEA_CRONICA_1, _HOJA_1, hoja_rara]

    def test_hoja_de_otra_receta_no_se_atribuye(self) -> None:
        cronicas = parsear_lineas_receta(_LINEA_CRONICA_1)
        bloque = vincular_farmacos(cronicas, [_HOJA_2])
        assert bloque == [_LINEA_CRONICA_1, _HOJA_2], "sin vinculo: no se pierde"


class TestNotaPortadora:
    def test_encontrada_lleva_bloque_verbatim(self) -> None:
        t = _texto_receta_cronica({"estado": "encontrada", "bloque": "14-09-2026 12:05\n(x)"})
        assert t == "14-09-2026 12:05\n(x)"

    def test_encontrada_sin_bloque_no_declara_inexistencia(self) -> None:
        assert _texto_receta_cronica({"estado": "encontrada", "bloque": ""}) == "(no verificado - revisar)"

    def test_no_existe(self) -> None:
        assert _texto_receta_cronica({"estado": "no_existe", "bloque": ""}) == "(sin receta cronica vigente)"

    def test_indeterminado_y_none(self) -> None:
        assert _texto_receta_cronica({"estado": "indeterminado"}) == "(no verificado - revisar)"
        assert _texto_receta_cronica(None) == "(no verificado - revisar)"


class _DriverMalo:
    """Driver que falla en todo: el extractor NUNCA debe lanzar."""

    def execute_script(self, *args, **kwargs):
        raise RuntimeError("boom")

    def find_elements(self, *args, **kwargs):
        raise RuntimeError("boom")


class TestExtractorTriEstado:
    def test_fallo_total_es_indeterminado_con_evidencia(self) -> None:
        r = extraer_receta_cronica(_DriverMalo(), logging.getLogger("t"))
        assert r["estado"] == ESTADO_INDETERMINADO
        assert r["bloque"] == ""
        assert r["evidencia"], "evidencia __DEBUG__ para auditar post-hoc"

    def test_los_estados_son_los_del_diseno(self) -> None:
        assert {ESTADO_ENCONTRADA, "no_existe", ESTADO_INDETERMINADO} == {
            "encontrada",
            "no_existe",
            "indeterminado",
        }
