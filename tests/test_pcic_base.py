"""Tests para el PCIC base + funciones auxiliares del flujo v2."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tools import generar_ficha_con_llm as gfl


# ---- Tests de cargar_pcic_base ----

class TestCargarPcicBase:
    def test_archivo_existe_y_carga(self) -> None:
        texto = gfl.cargar_pcic_base()
        assert texto, "pcic_base.txt no cargo (archivo deberia existir)"
        # Debe incluir los 5 campos
        assert "1) Objetivo" in texto
        assert "2) Opciones" in texto
        assert "3) Acuerdos" in texto
        assert "4) Responsable" in texto
        assert "5) Plazo" in texto
        # Debe incluir las reglas de customizacion
        assert "Reglas de customizacion" in texto or "reglas de customizacion" in texto.lower()
        # Debe mencionar las condiciones basicas
        assert "IMC" in texto
        assert "HTA" in texto or "presion" in texto.lower()
        assert "DM2" in texto or "glicemia" in texto.lower()

    def test_campos_fijos_de_yadira(self) -> None:
        """El template base incluye los textos que Yadira aprobo."""
        texto = gfl.cargar_pcic_base()
        # Plazo
        assert "6 meses" in texto
        # Responsable
        assert "equipo multidisciplinario + paciente" in texto
        # Opciones (debe incluir las 4 que Yadira menciono)
        assert "control medico+nutric" in texto or "control m" in texto
        assert "farmacologico" in texto or "farmacol" in texto
        assert "alimentacion saludable" in texto
        assert "autocuidado" in texto
        # Acuerdos (debe incluir los 3 acuerdos)
        assert "cambio de nutricionista" in texto
        assert "pastillero semanal" in texto
        assert "30 min" in texto or "30min" in texto


# ---- Tests de construir_prompt con la nueva estructura ----

class TestConstruirPromptV2:
    def _demografia_min(self) -> dict:
        return {
            "medico_cabecera": "Dra. Yadira",
            "run": "12.345.678-9",
            "fecha_nacimiento": "01-01-1960",
            "edad": "65",
            "sexo": "Mujer",
            "direccion": "Calle 1",
            "telefono": "+56 9 9999 9999",
            "prevision": "Fonasa C",
            "estado_civil": "Casado(a)",
            "sector": "Sector Verde",
            "numero_ficha": "12345",
        }

    def test_incluye_seccion_pcic_si_pcic_base(self) -> None:
        prompt = gfl.construir_prompt(
            plantilla="PLAN: {OBJETIVO}",
            nota_texto="nota de prueba",
            manual="",
            trigger=None,
            demografia=self._demografia_min(),
            nombre_paciente="Test",
            fecha_atencion="01-01-2026",
            tipo_atencion="CONTROL INTEGRAL",
            pcic_base="1) Objetivo: <custom> / 5) Plazo: 6 meses",
        )
        assert "## PCIC BASE" in prompt
        assert "1) Objetivo: <custom>" in prompt

    def test_omite_seccion_pcic_si_no_hay_base(self) -> None:
        prompt = gfl.construir_prompt(
            plantilla="PLAN",
            nota_texto="x",
            manual="",
            trigger=None,
            demografia=self._demografia_min(),
            nombre_paciente="Test",
            fecha_atencion="01-01-2026",
            tipo_atencion="MORBILIDAD",
            pcic_base="",
        )
        assert "## PCIC BASE" not in prompt

    def test_incluye_trigger_cuando_existe(self) -> None:
        prompt = gfl.construir_prompt(
            plantilla="x",
            nota_texto="x",
            manual="",
            trigger="redactar interconsulta a cardiologia",
            demografia=self._demografia_min(),
            nombre_paciente="Test",
            fecha_atencion="01-01-2026",
            tipo_atencion="MORBILIDAD",
        )
        assert "** mortadelo redactar interconsulta a cardiologia" in prompt
        assert "## INSTRUCCION DE TRIGGER" in prompt

    def test_incluye_examenes_adjuntos(self) -> None:
        prompt = gfl.construir_prompt(
            plantilla="x",
            nota_texto="x",
            manual="",
            trigger=None,
            demografia=self._demografia_min(),
            nombre_paciente="Test",
            fecha_atencion="01-01-2026",
            tipo_atencion="MORBILIDAD",
            examenes_adjuntos=[{"nombre": "audiometria.png", "transcripcion": "OD 64%"}],
        )
        assert "audiometria.png" in prompt
        assert "OD 64%" in prompt
        assert "## EXAMENES ADJUNTOS" in prompt

    def test_orden_secciones_es_el_esperado(self) -> None:
        """El prompt debe ir: TAREA -> DEMOGRAFIA -> EXAMENES -> PCIC -> REGLAS -> PLANTILLA -> NOTA -> OUTPUT."""
        prompt = gfl.construir_prompt(
            plantilla="PLANTILLA_TEST",
            nota_texto="NOTA_TEST",
            manual="MANUAL_TEST",
            trigger=None,
            demografia=self._demografia_min(),
            nombre_paciente="Test",
            fecha_atencion="01-01-2026",
            tipo_atencion="CONTROL INTEGRAL",
            pcic_base="PCIC_TEST",
        )
        idx_tarea = prompt.index("# TAREA")
        idx_demo = prompt.index("## DATOS DEMOGRAFICOS")
        idx_pcic = prompt.index("## PCIC BASE")
        idx_reglas = prompt.index("## REGLAS DEL BUNDLE")
        idx_plantilla = prompt.index("## PLANTILLA INMUTABLE")
        idx_nota = prompt.index("## NOTA CLINICA DE YADIRA")
        idx_output = prompt.index("## OUTPUT ESPERADO")
        assert idx_tarea < idx_demo < idx_pcic < idx_reglas < idx_plantilla < idx_nota < idx_output


# ---- Tests del agente mortadelo ----

class TestMortadeloAgent:
    """Verifica que el archivo .opencode/agent/mortadelo.md existe y tiene
    las reglas clave del flujo v2."""

    @pytest.fixture
    def agent_text(self) -> str:
        path = Path(".opencode/agent/mortadelo.md")
        if not path.exists():
            pytest.skip(f"No existe {path}")
        return path.read_text(encoding="utf-8")

    def test_tiene_permiso_webfetch(self, agent_text: str) -> None:
        assert "- webfetch" in agent_text, (
            "El agente mortadelo necesita permiso webfetch para consultas "
            "medicas (solo cuando no haya info en manuales/conocimiento)."
        )

    def test_tiene_regla_0_siempre_llena(self, agent_text: str) -> None:
        assert "FICHA SIEMPRE SE LLENA" in agent_text.upper() or \
               "siempre se llena" in agent_text.lower()

    def test_tiene_rubrica_4_categorias(self, agent_text: str) -> None:
        """Las 4 categorias: A) Mecanicos, B) Consenso, C) Clinicas, D) Citas."""
        assert "MEC" in agent_text.upper()  # MECANICOS
        assert "CONSENSO" in agent_text.upper()
        assert "CLIN" in agent_text.upper()  # CLINICAS
        assert "CITA" in agent_text.upper()

    def test_tiene_loops_de_verificacion(self, agent_text: str) -> None:
        assert "loop" in agent_text.lower() or "verificaci" in agent_text.lower()

    def test_tiene_sugerencias_para_proxima_ficha(self, agent_text: str) -> None:
        assert "PROXIMA FICHA" in agent_text.upper() or \
               "próxima ficha" in agent_text.lower() or \
               "PROXIMA" in agent_text.upper()

    def test_tiene_seccion_advertencias_inferencia(self, agent_text: str) -> None:
        assert "ADVERTENCIAS DE INFERENCIA" in agent_text.upper() or \
               "advertencias de inferencia" in agent_text.lower()

    def test_tiene_web_access_con_condiciones(self, agent_text: str) -> None:
        """Regla 3: web access SOLO cuando no haya info en manuales/conocimiento."""
        # Buscar las palabras clave de la condicion
        text_lower = agent_text.lower()
        assert "solo" in text_lower
        assert ("manuales" in text_lower or "conocimiento" in text_lower)
        # Fuentes permitidas
        assert "pubmed" in text_lower or "minsal" in text_lower or "oms" in text_lower
        # Fuentes prohibidas
        assert "blog" in text_lower or "wikipedia" in text_lower


# ---- Tests del detector de adjuntos (sin vision LLM) ----

class TestDetectarAdjuntosSinTranscribir:
    """El helper _detectar_adjuntos_sin_transcribir es el mismo matching
    que analizar_adjuntos_imagen pero sin invocar el vision LLM.
    Usado por --dry-run para mostrar el log sin gastar cuota."""

    def test_detecta_por_nombre_paciente(self, tmp_path) -> None:
        # Crear 2 imagenes placeholder
        (tmp_path / "fulanito_examen_25-08-2026.png").write_bytes(b"\x89PNG\r\n")
        (tmp_path / "fulanito_lab_25-08-2026.png").write_bytes(b"\x89PNG\r\n")
        # 1 imagen que no debe matchear
        (tmp_path / "otro_paciente_x.png").write_bytes(b"\x89PNG\r\n")

        resultado = gfl._detectar_adjuntos_sin_transcribir(
            nombre_paciente="Fulanito Mengano",
            fecha_atencion="25-08-2026",
            adjuntos_dir=tmp_path,
        )
        nombres = [p.name for p in resultado]
        assert "fulanito_examen_25-08-2026.png" in nombres
        assert "fulanito_lab_25-08-2026.png" in nombres
        assert "otro_paciente_x.png" not in nombres

    def test_detecta_por_fecha(self, tmp_path) -> None:
        (tmp_path / "examen_25-08-2026.png").write_bytes(b"\x89PNG\r\n")
        (tmp_path / "examen_26-08-2026.png").write_bytes(b"\x89PNG\r\n")
        resultado = gfl._detectar_adjuntos_sin_transcribir(
            nombre_paciente="Cualquier Nombre",
            fecha_atencion="25-08-2026",
            adjuntos_dir=tmp_path,
        )
        assert len(resultado) == 1
        assert resultado[0].name == "examen_25-08-2026.png"

    def test_ignora_archivos_no_imagen(self, tmp_path) -> None:
        (tmp_path / "examen_25-08-2026.png").write_bytes(b"\x89PNG\r\n")
        (tmp_path / "examen_25-08-2026.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "examen_25-08-2026.txt").write_text("texto")
        resultado = gfl._detectar_adjuntos_sin_transcribir(
            nombre_paciente="X",
            fecha_atencion="25-08-2026",
            adjuntos_dir=tmp_path,
        )
        assert len(resultado) == 1
        assert resultado[0].name.endswith(".png")

    def test_dir_inexistente_retorna_vacio(self, tmp_path) -> None:
        resultado = gfl._detectar_adjuntos_sin_transcribir(
            nombre_paciente="X",
            fecha_atencion="25-08-2026",
            adjuntos_dir=tmp_path / "no_existe",
        )
        assert resultado == []

    def test_soporta_extensiones_comunes(self, tmp_path) -> None:
        for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
            (tmp_path / f"imagen_25-08-2026{ext}").write_bytes(b"x")
        resultado = gfl._detectar_adjuntos_sin_transcribir(
            nombre_paciente="X",
            fecha_atencion="25-08-2026",
            adjuntos_dir=tmp_path,
        )
        assert len(resultado) == 6
