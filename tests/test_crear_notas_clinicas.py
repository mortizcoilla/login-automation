"""Tests para la construccion de notas clinicas en `crear_notas_clinicas`.

Cubre:
- `_safe_filename`: casos con acentos, espacios, caracteres raros
- `guardar_nota_clinica`: estructura completa del .txt (todos los bloques
  INICIO/FIN presentes, cabecera con datos del paciente, secciones
  con placeholders cuando no hay datos)
- `guardar_nota_clinica`: flag `panel_cargo=False` agrega el aviso
  "ATENCION: panel no cargo" al inicio de la nota
- `guardar_nota_clinica`: NO sobrescribe archivos existentes
- `guardar_nota_clinica`: filename formato `<safe>_<fecha>.txt`
- `parsear_informe`: smoke test del parser basico
- `PacienteObjetivo.panel_cargo`: default True, se puede setear False

Sesion 2026-09-16: agregados como guardrail para que el flujo no
regrese silenciosamente a "carpeta vacia" cuando el panel ECICEP
tarda en cargar.
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
# guardar_nota_clinica: estructura completa
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
    def test_crea_archivo_con_nombre_correcto(
        self, kwargs_minimos: dict, tmp_path: Path
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        assert out is not None
        assert out.exists()
        # Nombre: <safe_nombre>_<fecha>.txt (sin acentos en el filename
        # porque los acentos se mantienen con \w UNICODE, pero el caracter
        # 'ñ' tambien se mantiene).
        assert out.name == "Nicolas_Ignacio_Piña_Rojas_10-09-2026.txt"

    def test_cabecera_con_datos_paciente(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "# NOTA CLINICA" in contenido
        assert "# Paciente: Nicolas Ignacio Piña Rojas" in contenido
        assert "# Fecha atencion: 10-09-2026" in contenido

    def test_sin_flag_panel_no_cargo_cuando_panel_cargo_true(
        self, kwargs_minimos: dict
    ) -> None:
        # Default panel_cargo=True -> sin flag de revision.
        # Chequeamos la frase completa para no confundir con "HISTORIAL DE
        # ATENCIONES" que matchea el substring "ATENCION".
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "panel del paciente NO CARGO" not in contenido
        assert "Revisar manualmente en Rayen" not in contenido

    def test_todos_los_bloques_presentes(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        # Cada bloque importante debe tener sus marcadores INICIO/FIN.
        for bloque in [
            "IDENTIFICACION",
            "HISTORIAL DE ATENCIONES",
            "NOTA CLINICA DE YADIRA",
            "DIAGNOSTICOS",
            "ACTIVIDADES",
            "PROFESIONALES",
            "PLAN RECETAS",
            "PLAN LABORATORIO",
        ]:
            assert f"=== INICIO {bloque} ===" in contenido, f"Falta INICIO {bloque}"
            assert f"=== FIN {bloque} ===" in contenido, f"Falta FIN {bloque}"

    def test_separador_70_guiones(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "=" * 70 in contenido

    def test_identificacion_renderiza_campos(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "RUN: 23.012.222-9" in contenido
        assert "Edad: 17 años" in contenido

    def test_historial_renderizado(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "control previo sin novedades" in contenido

    def test_nota_clinica_yadira_con_motivo_y_anamnesis(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        # Motivo y anamnesis dentro del bloque NOTA CLINICA DE YADIRA
        # (sin marcadores propios, separados por linea en blanco).
        assert "Paciente consulta por control" in contenido

    def test_motivo_consulta_se_renderea_si_existe(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["motivo_consulta"] = "Control de HTA cronica"
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "Motivo de atencion: Control de HTA cronica" in contenido

    def test_diagnosticos_se_renderean(
        self, kwargs_minimos: dict
    ) -> None:
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "I10X Hipertension esencial" in contenido

    def test_actividades_con_bullet(
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
        assert "!!! ATENCION: panel del paciente NO CARGO en Rayen." in contenido
        assert "!!! La nota tiene placeholders. Revisar manualmente en Rayen." in contenido

    def test_panel_no_cargo_flag_antes_de_bloques(
        self, kwargs_minimos: dict
    ) -> None:
        # El flag debe estar al inicio, antes del primer === INICIO ===
        # para que Yadira lo vea inmediatamente al abrir el .txt.
        kwargs_minimos["panel_cargo"] = False
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        pos_flag = contenido.index("panel del paciente NO CARGO")
        pos_bloque = contenido.index("=== INICIO IDENTIFICACION ===")
        assert pos_flag < pos_bloque

    def test_panel_cargo_default_es_true(
        self, kwargs_minimos: dict
    ) -> None:
        # Sin pasar panel_cargo -> default True -> sin flag.
        # Frase completa para no confundir con "HISTORIAL DE ATENCIONES".
        assert "panel_cargo" not in kwargs_minimos
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "panel del paciente NO CARGO" not in contenido


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
        assert "(no se pudo extraer la tabla de identificacion)" in contenido

    def test_historial_vacio_muestra_placeholder(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["historial"] = ""
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "(no se pudo extraer el historial)" in contenido

    def test_anamnesis_vacia_se_renderea_vacia(
        self, kwargs_minimos: dict
    ) -> None:
        # Anamnesis vacia -> bloque NOTA CLINICA DE YADIRA existe pero sin texto.
        kwargs_minimos["anamnesis"] = ""
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "=== INICIO NOTA CLINICA DE YADIRA ===" in contenido
        assert "=== FIN NOTA CLINICA DE YADIRA ===" in contenido

    def test_diagnosticos_vacios_muestran_placeholder(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["diagnosticos"] = []
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "(sin diagnosticos)" in contenido

    def test_recetas_vacias_muestran_placeholder(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["recetas"] = []
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "(sin recetas)" in contenido

    def test_extraccion_minima_vacia_no_falla(
        self, paciente_basico: PacienteObjetivo, tmp_path: Path
    ) -> None:
        # El caso del placeholder completo (panel no cargo): todo vacio
        # pero igual debe generar un archivo valido.
        out = guardar_nota_clinica(
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
        assert out is not None
        assert out.exists()
        contenido = out.read_text(encoding="utf-8")
        # Estructura basica presente a pesar de estar todo vacio.
        assert "# NOTA CLINICA" in contenido
        assert "ATENCION" in contenido
        for bloque in ["IDENTIFICACION", "DIAGNOSTICOS", "ACTIVIDADES"]:
            assert f"=== INICIO {bloque} ===" in contenido


# ---------------------------------------------------------------------------
# guardar_nota_clinica: no overwrite
# ---------------------------------------------------------------------------
class TestGuardarNotaClinicaNoSobrescribe:
    def test_no_sobrescribe_archivo_existente(
        self, kwargs_minimos: dict, tmp_path: Path
    ) -> None:
        # Crear el archivo primero (con contenido cualquiera).
        target = tmp_path / "Nicolas_Ignacio_Piña_Rojas_10-09-2026.txt"
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
    def test_nombre_rayen_distinto_se_renderea_en_cabecera(
        self, kwargs_minimos: dict, tmp_path: Path
    ) -> None:
        kwargs_minimos["paciente"].nombre_rayen = "Nicolas Piña"  # truncado
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "# Paciente: Nicolas Ignacio Piña Rojas" in contenido  # original
        assert "# Paciente (Rayen): Nicolas Piña" in contenido  # real

    def test_nombre_rayen_igual_al_informe_no_se_renderea(
        self, kwargs_minimos: dict
    ) -> None:
        kwargs_minimos["paciente"].nombre_rayen = (
            kwargs_minimos["paciente"].nombre
        )
        out = guardar_nota_clinica(**kwargs_minimos)
        contenido = out.read_text(encoding="utf-8")
        assert "Paciente (Rayen)" not in contenido


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