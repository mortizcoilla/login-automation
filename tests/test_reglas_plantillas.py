"""Tests para la regla de uso de plantillas."""
import inspect

import pytest

from src.reglas_plantillas import (
    _REGLA,
    _normalizar_clave as normalizar_clave,
    listar_plantillas_canonicas,
    listar_tipos_con_plantilla,
    resolver_plantilla,
)


class TestResolverPlantilla:
    """Casos directos del Excel."""

    @pytest.mark.parametrize(
        "tipo,esperado",
        [
            # Recetas
            ("Recetas", "RECETA"),
            # Morbilidad — todas las variantes van a MORBILIDAD
            ("Morbilidad telefónica", "MORBILIDAD"),
            ("Morbilidad presencial", "MORBILIDAD"),
            ("Control cronico descompensado", "MORBILIDAD"),
            ("Morbilidad", "MORBILIDAD"),
            # Ingreso salud mental sin ECICEP
            ("Ingreso salud mental infantil", "INGRESO SALUD MENTAL SIN ECICEP"),
            ("Control salud mental infantil", "INGRESO SALUD MENTAL SIN ECICEP"),
            ("Consulta salud mental", "INGRESO SALUD MENTAL SIN ECICEP"),
            # Ingreso ECICEP
            ("Ingreso integral ecicep-g3", "INGRESO ECICEP"),
            ("Ingreso multimorbilidad g3", "INGRESO ECICEP"),
            ("Ingreso integral ecicep-g1", "INGRESO ECICEP"),
            # Control integral sin ficha anterior
            ("Control integral ecicep-g3", "CONTROL INTEGRAL SIN FICHA ANTERIOR"),
            ("Control integral multimorbilidad g1", "CONTROL INTEGRAL SIN FICHA ANTERIOR"),
            ("Control crónico", "CONTROL INTEGRAL SIN FICHA ANTERIOR"),
            # Control de nino sano (con edad): ver tests especificos abajo
        ],
    )
    def test_tipos_con_plantilla(self, tipo, esperado):
        assert resolver_plantilla(tipo) == esperado

    @pytest.mark.parametrize(
        "tipo",
        [
            "Gestion administrativa",
            "Seguimiento a distancia multimorbilidad g2",
            "Consultorías adulto",
            "Consultoria salud mental (sesiones)",
            "Control",
            "",
        ],
    )
    def test_tipos_no_aplica(self, tipo):
        assert resolver_plantilla(tipo) is None

    @pytest.mark.parametrize(
        "tipo",
        [
            "Tipo inventado que no existe",
            "Otra cosa random",
            "xyz",
        ],
    )
    def test_tipo_desconocido_devuelve_none(self, tipo):
        assert resolver_plantilla(tipo) is None

    def test_case_insensitive(self):
        # Resolver debe ser case-insensitive (matayon, mayusculas, mezcla)
        assert resolver_plantilla("recetas") == "RECETA"
        assert resolver_plantilla("RECETAS") == "RECETA"
        assert resolver_plantilla("ReCeTaS") == "RECETA"

    def test_con_prefijo_instrumento(self):
        # Si Rayen manda "ME, Control integral ecicep-g3", debe resolver igual
        # porque sanitizar_tipo() quita el prefijo "ME,"
        assert resolver_plantilla("ME, Control integral ecicep-g3") == "CONTROL INTEGRAL SIN FICHA ANTERIOR"

    # Tests para Control de Nino Sano (depende de edad)
    def test_control_nino_sano_sin_edad_devuelve_none(self):
        # Sin edad, no podemos elegir 1 mes vs 3 meses, devolvemos None
        assert resolver_plantilla("Control salud") is None
        assert resolver_plantilla("control salud", edad_meses=None) is None

    def test_control_nino_sano_menor_3_meses(self):
        # Bebé de 0, 1, 2 meses -> 1 mes
        assert resolver_plantilla("Control salud", edad_meses=0) == "CONTROL NIÑO SANO 1 MES"
        assert resolver_plantilla("Control salud", edad_meses=1) == "CONTROL NIÑO SANO 1 MES"
        assert resolver_plantilla("Control salud", edad_meses=2) == "CONTROL NIÑO SANO 1 MES"

    def test_control_nino_sano_3_o_mas_meses(self):
        # Bebé de 3+ meses -> 3 meses
        assert resolver_plantilla("Control salud", edad_meses=3) == "CONTROL NIÑO SANO 3 MESES"
        assert resolver_plantilla("Control salud", edad_meses=6) == "CONTROL NIÑO SANO 3 MESES"
        assert resolver_plantilla("Control salud", edad_meses=12) == "CONTROL NIÑO SANO 3 MESES"
        assert resolver_plantilla("Control salud", edad_meses=24) == "CONTROL NIÑO SANO 3 MESES"

    def test_control_nino_sano_case_insensitive(self):
        assert resolver_plantilla("CONTROL SALUD", edad_meses=2) == "CONTROL NIÑO SANO 1 MES"
        assert resolver_plantilla("Control Salud", edad_meses=4) == "CONTROL NIÑO SANO 3 MESES"

    def test_none_input(self):
        assert resolver_plantilla(None) is None  # type: ignore[arg-type]

    def test_whitespace_input(self):
        assert resolver_plantilla("   ") is None


class TestListar:
    def test_listar_tipos_con_plantilla_no_incluye_no_aplica(self):
        tipos = listar_tipos_con_plantilla()
        for tipo, canonica in tipos:
            assert canonica != "NO APLICA"
            assert tipo != ""

    def test_listar_plantillas_canonicas(self):
        canonicas = listar_plantillas_canonicas()
        # Las 7 plantillas canónicas del Excel
        esperadas = {
            "RECETA",
            "MORBILIDAD",
            "INGRESO SALUD MENTAL SIN ECICEP",
            "INGRESO ECICEP",
            "CONTROL INTEGRAL SIN FICHA ANTERIOR",
            "CONTROL DE NIÑO SANO",
        }
        assert set(canonicas) == esperadas

    def test_regla_no_vacia(self):
        # La regla debe tener entradas (no este vacia)
        assert len(_REGLA) > 10

    def test_todas_valores_uppercase_o_no_aplica(self):
        for canonica in _REGLA.values():
            assert canonica == canonica.upper(), f"'{canonica}' no esta en mayusculas"
            assert canonica in {
                "RECETA", "MORBILIDAD",
                "INGRESO SALUD MENTAL SIN ECICEP", "INGRESO ECICEP",
                "CONTROL INTEGRAL SIN FICHA ANTERIOR", "CONTROL DE NIÑO SANO",
                "NO APLICA",
            }


class TestNormalizarClave:
    """La normalizacion es accent + lowercase + colapsar espacios."""

    def test_lowercase(self):
        assert normalizar_clave("Hola Mundo") == "hola mundo"

    def test_sin_acentos(self):
        assert normalizar_clave("Morbilidad telefónica") == "morbilidad telefonica"
        assert normalizar_clave("Control niño sano") == "control nino sano"

    def test_colapsa_espacios(self):
        assert normalizar_clave("  hola   mundo  ") == "hola mundo"
        assert normalizar_clave("a\tb\nc") == "a b c"

    def test_input_vacio(self):
        assert normalizar_clave("") == ""
        assert normalizar_clave(None) == ""  # type: ignore[arg-type]


class TestReglaEsCodigo:
    """La fuente de verdad es el dict _REGLA en codigo, NO un archivo externo."""

    def test_no_se_lee_excel(self):
        """reglas_plantillas.py no debe mencionar openpyxl ni PLANTILLAS.xlsx.
        Si vuelve a leer el Excel, el dict en codigo deja de ser la fuente."""
        from src import reglas_plantillas
        src = inspect.getsource(reglas_plantillas)
        assert "openpyxl" not in src, (
            "reglas_plantillas.py esta importando openpyxl. "
            "El Excel debe estar fuera del flujo."
        )
        assert "PLANTILLAS.xlsx" not in src, (
            "reglas_plantillas.py referencia PLANTILLAS.xlsx. "
            "El Excel debe estar fuera del flujo."
        )

    def test_regla_es_dict_en_codigo(self):
        """La regla es un dict normal de Python, no algo cargado de disco."""
        from src import reglas_plantillas
        assert isinstance(reglas_plantillas._REGLA, dict)
        assert len(reglas_plantillas._REGLA) > 10

    def test_regla_tiene_entradas_esperadas(self):
        """Verifica que las entradas del dict son las que Yadira definio."""
        assert _REGLA["Recetas"] == "RECETA"
        assert _REGLA["Morbilidad"] == "MORBILIDAD"
        assert _REGLA["Ingreso salud mental infantil"] == "INGRESO SALUD MENTAL SIN ECICEP"
        assert _REGLA["Ingreso integral ecicep-g1"] == "INGRESO ECICEP"
        assert _REGLA["Control salud"] == "CONTROL DE NIÑO SANO"  # placeholder
        assert _REGLA["Gestion administrativa"] == "NO APLICA"


class TestRobustezMatching:
    """El resolver matchea con/sin acentos, mayusculas, espacios."""

    @pytest.mark.parametrize(
        "tipo_input,esperado",
        [
            ("Morbilidad telefónica", "MORBILIDAD"),
            ("Morbilidad telefonica", "MORBILIDAD"),  # sin acento
            ("MORBILIDAD TELEFONICA", "MORBILIDAD"),  # mayusculas sin acento
            ("MoRbIlIdAd TeLeFoNiCa", "MORBILIDAD"),  # mixto
            ("  Morbilidad telefónica  ", "MORBILIDAD"),  # espacios
            ("Morbilidad", "MORBILIDAD"),
            ("Ingreso salud mental infantil", "INGRESO SALUD MENTAL SIN ECICEP"),
            ("Ingreso multidisciplinario salud mental - infantil", "INGRESO SALUD MENTAL SIN ECICEP"),
            ("Ingreso integral ecicep-g1", "INGRESO ECICEP"),
        ],
    )
    def test_resolver_matchea_variantes(self, tipo_input, esperado):
        assert resolver_plantilla(tipo_input) == esperado

    def test_resolver_devuelve_none_para_no_aplica(self):
        assert resolver_plantilla("Gestion administrativa") is None
        assert resolver_plantilla("Seguimiento a distancia multimorbilidad g2") is None
        assert resolver_plantilla("Consultoria salud mental (sesiones)") is None
        assert resolver_plantilla("Control") is None

    def test_resolver_devuelve_none_para_tipo_inexistente(self):
        assert resolver_plantilla("Tipo inventado") is None
        assert resolver_plantilla("xyz") is None
        assert resolver_plantilla("") is None
        assert resolver_plantilla(None) is None  # type: ignore[arg-type]
