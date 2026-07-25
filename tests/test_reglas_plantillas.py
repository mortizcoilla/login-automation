"""Tests para la regla de uso de plantillas."""
import pytest

from src.reglas_plantillas import (
    _REGLA,
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
            # Control de nino sano
            ("Control salud", "CONTROL DE NIÑO SANO"),
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
