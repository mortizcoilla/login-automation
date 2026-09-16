"""Tests para la construccion de notas clinicas en `crear_notas_clinicas`.

Sesion 2026-09-16: las notas se guardan en .md (markdown con frontmatter
YAML + headers ##) en armonia con manuales_md/. Antes era .txt con
marcadores '=== INICIO/FIN ==='.

Regla dura Yadira (2026-09-16): la anamnesis SIEMPRE existe en Rayen
(Yadira la llena al abrir la ficha). Si la extraccion retorna vacia,
es un bug y el archivo NO se escribe. Cubierto por tests de rechazo
(`test_anamnesis_vacia_rechaza_escritura_*`) y por el regression guard
sobre `notas_clinicas/` (`TestRegressionGuardNotasClinicas`).

Cubre:
- `_safe_filename`: casos con acentos, espacios, caracteres raros
- `guardar_nota_clinica`: estructura completa del .md (todos los
-  ## headers presentes, frontmatter YAML con datos del paciente,
-  secciones con placeholders cuando no hay datos)
- `guardar_nota_clinica`: RECHAZA escritura si `anamnesis` esta vacia
-  (regla dura Yadira, ver arriba)
- `guardar_nota_clinica`: NO sobrescribe archivos existentes
- `guardar_nota_clinica`: filename formato `<safe>_<fecha>.md`
- `parsear_informe`: smoke test del parser basico
- `PacienteObjetivo.panel_cargo`: default True, se puede setear False
- Regression guard: `notas_clinicas/*.md` no debe contener archivos
-  con `panel_cargo=false` (extraccion rota que el pipeline anterior
-  permitio)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.tools.crear_notas_clinicas import (
    PacienteObjetivo,
    _safe_filename,
    guardar_nota_clinica,
    parsear_informe,
)


# ---------------------------------------------------------------------------
# _safe_filename
# ---------------------------------------------------------------------------
class TestSafeFilename:
    def test_espacios_a_underscore(self) -> None:
        assert _safe_filename("Juan Perez") == "Juan_Perez"

    def test_acentos_se_conservan(self) -> None:
        # \w en modo UNICODE incluye letras acentuadas, asi que se preservan.
        assert _safe_filename("María José") == "María_José"

    def test_signos_de_puntuacion_se_quitan(self) -> None:
        # El regex [^\w\s\-]+ elimina puntuacion pero conserva letras/guion.
        assert _safe_filename("Juan, Perez.") == "Juan_Perez"

    def test_guiones_se_conservan(self) -> None:
        assert _safe_filename("Maria-Jose") == "Maria-Jose"

    def test_multiples_espacios_se_colapsan(self) -> None:
        assert _safe_filename("  Juan   Perez  ") == "Juan_Perez"

    def test_string_vacio(self) -> None:
        assert _safe_filename("") == ""

    def test_solo_puntuacion(self) -> None:
        # Sin letras/guiones queda vacio.
        assert _safe_filename(".,;:") == ""


# ---------------------------------------------------------------------------
# guardar_nota_clinica: estructura completa (markdown)
# ---------------------------------------------------------------------------
@pytest.fixture
def paciente_basico() -> PacienteObjetivo:
    return PacienteObjetivo(
        fecha="10-09-2026",
        nombre="Nicolas Ignacio Piña Rojas",
        tipo_atencion="Control integral ecicep-g3",
        razon="",
    )


@pytest.fixture
def kwargs_minimos(paciente_basico: PacienteObjetivo, tmp_path: Path) -> dict:
    """Argumentos minimos validos para guardar_nota_clinica."""
    return dict(
        paciente=paciente_basico,
        identificacion={"RUN": "23.012.222-9", "Edad": "17 años"},
        historial="2024-03-15: control previo sin novedades",
        anamnesis="Paciente consulta por control de su patologia cronica.",
        diagnosticos=["I10X Hipertension esencial"],
        actividades=["Control de presion arterial"],
        profesionales=["Dr. Lopez"],
        pautas=[],
        notas_dir=tmp_path,
    )


class TestGuardarNotaClinicaEstructura:
    def test_crea_archivo_con_extension_md(
        self, kwargs_minimos: dict, tmp_path: Path
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        assert out is not None
        assert out.exists()
        assert out.suffix == ".md"
        # Nombre: <safe_nombre>_<fecha>.md
        assert out.name == "Nicolas_Ignacio_Piña_Rojas_10-09-2026.md"

    def test_frontmatter_yaml_con_datos_paciente(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        # Debe empezar con frontmatter.
        assert contenido.startswith("---\n")
        # Campos clave en el frontmatter.
        assert 'paciente: "Nicolas Ignacio Piña Rojas"' in contenido
        assert 'title: "Nota clinica - Nicolas Ignacio Piña Rojas"' in contenido
        assert 'fecha_atencion: "10-09-2026"' in contenido
        assert 'tipo_atencion: "Control integral ecicep-g3"' in contenido
        # Fuente Rayen hardcoded.
        assert 'fuente: "Rayen APS - CESFAM Raul Cuevas, San Bernardo"' in contenido
        assert 'source_url: "https://clinico.rayenaps.cl/"' in contenido
        # panel_cargo default True.
        assert 'panel_cargo: "true"' in contenido

    def test_titulo_h1(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "# Nota clinica - Nicolas Ignacio Piña Rojas" in contenido

    def test_sin_flag_panel_no_cargo_cuando_panel_cargo_true(
        self, kwargs_minimos: dict
    ) -> None:
        # Default panel_cargo=True -> sin flag de revision.
        # Frase completa para no confundir con "HISTORIAL DE ATENCIONES".
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "panel del paciente NO CARGO" not in contenido
        assert "Revisar manualmente en Rayen" not in contenido

    def test_todos_los_headers_presentes(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        for header in [
            "## Identificacion",
            "## Historial de atenciones (ultimos 6 meses)",
            "## Nota clinica de Yadira",
            "## Diagnosticos",
            "## Actividades",
            "## Profesionales",
            "## Plan - Recetas",
            "## Plan - Laboratorio",
        ]:
            assert header in contenido, f"Falta header {header}"

    def test_identificacion_como_bullets_clave_valor(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "- **RUN:** 23.012.222-9" in contenido
        assert "- **Edad:** 17 años" in contenido

    def test_historial_renderizado(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "control previo sin novedades" in contenido

    def test_nota_clinica_yadira_con_anamnesis_cruda(
        self, kwargs_minimos: dict
    ) -> None:
        # Regla Yadira 2026-09-16 (corregido 13:42): el bloque Yadira
        # contiene la anamnesis CRUDA que Yadira escribio en Rayen.
        # Es el insumo principal del flujo de enriquecimiento via LLM
        # (`completar_yadira.py`). NO queda vacio ni con placeholder.
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "## Nota clinica de Yadira" in contenido
        # La anamnesis cruda del kwargs_minimos esta presente.
        assert "control de su patologia cronica" in contenido
        # NO hay placeholder (eso era el diseno viejo, pre-13:42).
        assert "bloque a completar por el LLM" not in contenido

    def test_motivo_consulta_como_blockquote(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["motivo_consulta"] = "Control de HTA cronica"
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "> **Motivo de atencion:** Control de HTA cronica" in contenido

    def test_diagnosticos_como_bullets(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "- I10X Hipertension esencial" in contenido

    def test_diagnostico_con_guion_inicial_no_se_duplica(
        self, kwargs_minimos: dict
    ) -> None:
        # Si el diagnostico viene con "- " al inicio (caso del parser),
        # el bullet no debe quedar como "- - ...".
        kwargs_minimos["diagnosticos"] = ["- CIE 10 F32.1 Episodio depresivo"]
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "- - " not in contenido
        assert "- CIE 10 F32.1 Episodio depresivo" in contenido

    def test_actividades_como_bullets(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "- Control de presion arterial" in contenido


# ---------------------------------------------------------------------------
# guardar_nota_clinica: flag panel_cargo
# ---------------------------------------------------------------------------
class TestPanelCargoFlag:
    def test_panel_no_cargo_escribe_flag_atencion(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["panel_cargo"] = False
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert (
            "> \u26a0\ufe0f **ATENCION: panel del paciente NO CARGO en Rayen.**"
            in contenido
        )
        assert (
            "> La nota tiene placeholders. Revisar manualmente en Rayen."
            in contenido
        )

    def test_panel_no_cargo_se_refleja_en_frontmatter(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["panel_cargo"] = False
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert 'panel_cargo: "false"' in contenido

    def test_panel_no_cargo_flag_antes_del_primer_header(
        self, kwargs_minimos: dict
    ) -> None:
        # El flag debe estar antes del primer ## Identificacion para que
        # Yadira lo vea inmediatamente.
        kwargs_minimos["panel_cargo"] = False
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        pos_flag = contenido.index("panel del paciente NO CARGO")
        pos_bloque = contenido.index("## Identificacion")
        assert pos_flag < pos_bloque

    def test_panel_cargo_default_es_true(
        self, kwargs_minimos: dict
    ) -> None:
        # Sin pasar panel_cargo -> default True -> sin flag.
        assert "panel_cargo" not in kwargs_minimos
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "panel del paciente NO CARGO" not in contenido
        assert 'panel_cargo: "true"' in contenido


# ---------------------------------------------------------------------------
# guardar_nota_clinica: valores vacios / placeholder
# ---------------------------------------------------------------------------
class TestGuardarNotaClinicaVacias:
    def test_identificacion_vacia_muestra_placeholder(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["identificacion"] = {}
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "_(no se pudo extraer la tabla de identificacion)_" in contenido

    def test_historial_vacio_muestra_placeholder(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["historial"] = ""
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "_(no se pudo extraer el historial)_" in contenido

    def test_anamnesis_vacia_rechaza_escritura_panel_cargo_true(
        self, kwargs_minimos: dict, tmp_path: Path
    ) -> None:
        # Regla dura Yadira 2026-09-16: la anamnesis SIEMPRE existe en
        # Rayen (Yadira la llena al abrir la ficha). Si la extraccion
        # retorna vacia, es un bug y el archivo NO se escribe.
        kwargs_minimos["anamnesis"] = ""
        kwargs_minimos["panel_cargo"] = True
        with pytest.raises(ValueError, match="anamnesis vacia"):
            guardar_nota_clinica(**kwargs_minimos)
        # Ningun archivo creado.
        assert list(tmp_path.iterdir()) == []

    def test_anamnesis_vacia_rechaza_escritura_panel_cargo_false(
        self, paciente_basico: PacienteObjetivo, tmp_path: Path
    ) -> None:
        # Caso del panel que no cargo: el script retorno panel_cargo=False
        # y anamnesis="". Esto sigue siendo una falla de extraccion (no
        # estamos capturando lo que Yadira SIEMPRE lleno). La regla es
        # dura: NO se escribe el archivo.
        with pytest.raises(ValueError, match="anamnesis vacia"):
            guardar_nota_clinica(
                paciente=paciente_basico,
                identificacion={},
                historial="",
                anamnesis="",
                diagnosticos=[],
                actividades=[],
                profesionales=[],
                pautas=[],
                notas_dir=tmp_path,
                panel_cargo=False,
            )
        assert list(tmp_path.iterdir()) == []

    def test_anamnesis_solo_espacios_tambien_rechaza(
        self, kwargs_minimos: dict, tmp_path: Path
    ) -> None:
        # Un string con solo whitespace tampoco cuenta como anamnesis
        # valida. La regla es dura.
        kwargs_minimos["anamnesis"] = "   \n\t  "
        with pytest.raises(ValueError, match="anamnesis vacia"):
            guardar_nota_clinica(**kwargs_minimos)
        assert list(tmp_path.iterdir()) == []

    def test_anamnesis_no_vacia_pasa_normal(
        self, kwargs_minimos: dict, tmp_path: Path
    ) -> None:
        # Caso normal: la extraccion devolvio texto. Funcion OK.
        kwargs_minimos["anamnesis"] = (
            "Paciente consulta por control de su patologia cronica. "
            "Sin sintomas nuevos."
        )
        out = guardar_nota_clinica(**kwargs_minimos)
        assert out is not None
        assert out.exists()
        contenido = out.read_text(encoding="utf-8")
        assert "## Nota clinica de Yadira" in contenido

    def test_diagnosticos_vacios_muestran_placeholder(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["diagnosticos"] = []
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "_(sin diagnosticos)_" in contenido

    def test_recetas_vacias_muestran_placeholder(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["recetas"] = []
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "_(sin recetas)_" in contenido

    def test_laboratorio_vacio_muestra_placeholder(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["laboratorio"] = []
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "_(sin ordenes de laboratorio)_" in contenido


# ---------------------------------------------------------------------------
# guardar_nota_clinica: no overwrite
# ---------------------------------------------------------------------------
class TestGuardarNotaClinicaNoSobrescribe:
    def test_no_sobrescribe_archivo_existente(
        self, kwargs_minimos: dict, tmp_path: Path
    ) -> None:
        # Crear el archivo primero (con contenido cualquiera).
        target = tmp_path / "Nicolas_Ignacio_Piña_Rojas_10-09-2026.md"
        target.write_text("CONTENIDO PREEXISTENTE", encoding="utf-8")

        out = guardar_nota_clinica(**kwargs_minimos)

        # Devuelve None (no se sobrescribe).
        assert out is None
        # Contenido original intacto.
        assert target.read_text(encoding="utf-8") == "CONTENIDO PREEXISTENTE"

    def test_segunda_llamada_devuelve_none(
        self, kwargs_minimos: dict
    ) -> None:
        # Primera llamada: crea archivo, devuelve path.
        out1 = guardar_nota_clinica(**kwargs_minimos)
        assert out1 is not None
        # Segunda llamada con mismos args: no sobrescribe, devuelve None.
        out2 = guardar_nota_clinica(**kwargs_minimos)
        assert out2 is None


# ---------------------------------------------------------------------------
# guardar_nota_clinica: nombre real de Rayen (match parcial)
# ---------------------------------------------------------------------------
class TestGuardarNotaClinicaNombreRayen:
    def test_nombre_rayen_distinto_aparece_en_frontmatter(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["paciente"].nombre_rayen = "Nicolas Piña"
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert 'paciente: "Nicolas Ignacio Piña Rojas"' in contenido  # original
        assert 'paciente_rayen: "Nicolas Piña"' in contenido  # real

    def test_nombre_rayen_igual_al_informe_no_aparece(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["paciente"].nombre_rayen = (
            kwargs_minimos["paciente"].nombre
        )
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "paciente_rayen" not in contenido


# ---------------------------------------------------------------------------
# parsear_informe: smoke test
# ---------------------------------------------------------------------------
class TestParsearInforme:
    def test_parsea_informe_con_formato_6_columnas(
        self, tmp_path: Path
    ) -> None:
        informe = tmp_path / "informe_test.txt"
        informe.write_text(
            "10-09-2026    Nicolas Ignacio Piña Rojas    (-)    "
            "Control integral ecicep-g3    (-)    CONTROL INTEGRAL SIN FICHA ANTERIOR\n"
            "11-09-2026    Maria Lopez    (-)    "
            "Morbilidad    (-)    MORBILIDAD\n",
            encoding="utf-8",
        )
        pacientes = parsear_informe(informe)
        assert len(pacientes) == 2
        assert pacientes[0].fecha == "10-09-2026"
        assert pacientes[0].nombre == "Nicolas Ignacio Piña Rojas"
        assert pacientes[0].tipo_atencion == "Control integral ecicep-g3"
        assert pacientes[1].fecha == "11-09-2026"
        assert pacientes[1].nombre == "Maria Lopez"

    def test_informe_inexistente_devuelve_lista_vacia(
        self, tmp_path: Path
    ) -> None:
        informe = tmp_path / "no_existe.txt"
        pacientes = parsear_informe(informe)
        assert pacientes == []

    def test_ignora_lineas_sin_fecha(self, tmp_path: Path) -> None:
        informe = tmp_path / "informe_test.txt"
        informe.write_text(
            "ESTA LINEA NO ES UN PACIENTE\n"
            "10-09-2026    Juan Perez    (-)    "
            "Morbilidad    (-)    MORBILIDAD\n",
            encoding="utf-8",
        )
        pacientes = parsear_informe(informe)
        assert len(pacientes) == 1
        assert pacientes[0].nombre == "Juan Perez"

    def test_quita_prefijo_atencion_preferente(
        self, tmp_path: Path
    ) -> None:
        informe = tmp_path / "informe_test.txt"
        informe.write_text(
            "10-09-2026    (atencion preferente) Juan Perez    "
            "(-)    Morbilidad    (-)    MORBILIDAD\n",
            encoding="utf-8",
        )
        pacientes = parsear_informe(informe)
        assert pacientes[0].nombre == "Juan Perez"  # sin prefijo


# ---------------------------------------------------------------------------
# PacienteObjetivo.panel_cargo
# ---------------------------------------------------------------------------
class TestPacienteObjetivoPanelCargo:
    def test_default_es_true(self) -> None:
        p = PacienteObjetivo(
            fecha="10-09-2026",
            nombre="X",
            tipo_atencion="Y",
        )
        assert p.panel_cargo is True

    def test_se_puede_setear_false(self) -> None:
        p = PacienteObjetivo(
            fecha="10-09-2026",
            nombre="X",
            tipo_atencion="Y",
            panel_cargo=False,
        )
        assert p.panel_cargo is False


# ---------------------------------------------------------------------------
# Regression guard: notas_clinicas/ no debe contener archivos con
# extraccion rota. Regla dura Yadira 2026-09-16: la anamnesis SIEMPRE
# existe en Rayen. Si la extraccion retorno vacia (panel_cargo=false),
# NO se deberia haber escrito el archivo.
# ---------------------------------------------------------------------------
class TestRegressionGuardNotasClinicas:
    """Escanea `notas_clinicas/*.md` y falla si encuentra archivos con
    `panel_cargo: "false"` (extraccion rota que el pipeline anterior
    permitio)."""

    NOTAS_DIR = Path(__file__).resolve().parents[1] / "notas_clinicas"

    def test_no_hay_notas_con_panel_cargo_false(
        self, tmp_path: Path
    ) -> None:
        if not self.NOTAS_DIR.exists():
            pytest.skip(
                "no hay directorio notas_clinicas/ en este checkout"
            )
        rotas: list[str] = []
        for f in sorted(self.NOTAS_DIR.glob("*.md")):
            contenido = f.read_text(encoding="utf-8")
            # Detectar el patron: panel_cargo="false" en frontmatter.
            if 'panel_cargo: "false"' in contenido:
                rotas.append(f.name)
        assert not rotas, (
            f"Regla dura Yadira: hay {len(rotas)} notas con "
            f"extraccion rota (panel_cargo=false). Estas notas se "
            f"escribieron con placeholder en vez de fallar. "
            f"Re-ejecutar `crear_notas_clinicas` para estos "
            f"pacientes o borrarlas manualmente:\n  - "
            + "\n  - ".join(rotas)
        )

    def test_todas_las_notas_tienen_seccion_yadira(
        self, tmp_path: Path
    ) -> None:
        if not self.NOTAS_DIR.exists():
            pytest.skip(
                "no hay directorio notas_clinicas/ en este checkout"
            )
        sin_seccion: list[str] = []
        for f in sorted(self.NOTAS_DIR.glob("*.md")):
            contenido = f.read_text(encoding="utf-8")
            if "## Nota clinica de Yadira" not in contenido:
                sin_seccion.append(f.name)
        assert not sin_seccion, (
            f"Estas notas no tienen la seccion '## Nota clinica de "
            f"Yadira' (fueron generadas antes del esquema markdown):\n"
            f"  - " + "\n  - ".join(sin_seccion)
        )