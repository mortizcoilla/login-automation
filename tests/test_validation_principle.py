"""Test del principio de validación humana.

Carga el fixture del caso simulado de HTA y valida:
- Que la estructura del fixture es correcta
- Que se documentaron los 5 bloques obligatorios del output clínico
- Que se documentaron los warnings de brechas
- Que el comportamiento de rechazo del envío está especificado
- Que el placeholder de identidad de Yadira está marcado

Este test NO ejecuta Pilita/Teodoro (eso se hace a mano o con un test de
integración futuro). Solo verifica que el contrato del principio de validación
quede documentado y protegido contra cambios accidentales.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "data" / "test_cases" / "caso_hta_femenina_50a.json"


@pytest.fixture
def fixture() -> dict:
    assert FIXTURE_PATH.exists(), f"Fixture no encontrado: {FIXTURE_PATH}"
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_fixture_tiene_caso_id(fixture: dict) -> None:
    assert "case_id" in fixture
    assert isinstance(fixture["case_id"], str)
    assert fixture["case_id"].startswith("caso_")


def test_input_es_simulacion(fixture: dict) -> None:
    assert fixture["input"]["tipo_caso"] == "simulacion_dry_run"
    assert "paciente_seudonimizado" in fixture["input"]
    paciente = fixture["input"]["paciente_seudonimizado"]
    assert paciente["edad"] == 50
    assert paciente["sexo"] == "F"


def test_estructura_clinica_tiene_los_5_bloques(fixture: dict) -> None:
    bloques = fixture["expected_clinical_output"]["estructura_obligatoria"]
    assert len(bloques) == 5, f"Deben ser 5 bloques, hay {len(bloques)}"
    nombres_bloques = " ".join(bloques).lower()
    assert "impresión diagnóstica" in nombres_bloques
    assert "diferencial" in nombres_bloques
    assert "plan" in nombres_bloques
    assert "derivación" in nombres_bloques or "sic" in nombres_bloques
    assert "red flags" in nombres_bloques


def test_arsenal_aps_y_ges_presentes(fixture: dict) -> None:
    contenido = " ".join(fixture["expected_clinical_output"]["debe_incluir_contenido"]).lower()
    assert "arsenal aps" in contenido
    assert "ges" in contenido
    assert "ecicep" in contenido


def test_warnings_de_brechas_presentes(fixture: dict) -> None:
    warnings = fixture["expected_clinical_output"]["warnings_brechas_esperados"]
    assert len(warnings) >= 5, "Debe haber al menos 5 warnings de brechas"
    warnings_text = " ".join(warnings).lower()
    assert "creatinina" in warnings_text
    assert "ecicep" in warnings_text or "red de apoyo" in warnings_text
    assert "ampa" in warnings_text or "mapa" in warnings_text


def test_principio_validacion_rechaza_envio_invalido(fixture: dict) -> None:
    validation = fixture["expected_validation_behavior"]
    assert validation["debe_rechazar"] is True
    assert len(validation["razones_esperadas"]) >= 3
    razones = " ".join(validation["razones_esperadas"]).lower()
    assert "simulación" in razones or "simulacion" in razones
    assert "yadira" in razones or "médica" in razones or "medica" in razones
    assert "✅" in razones or "📤" in razones or "gesto" in razones


def test_identidad_yadira_es_placeholder(fixture: dict) -> None:
    identidad = fixture["identidad_medica_autorizada"]
    assert identidad["nombre"] == "Yadira"
    sender_id = identidad["telegram_sender_id_pendiente"]
    assert sender_id.startswith("REEMPLAZAR"), f"sender_id debe ser placeholder, hay: {sender_id}"


def test_pilita_ofrece_alternativas_despues_de_rechazar(fixture: dict) -> None:
    """Después de rechazar, Pilita debe proponer caminos útiles, no quedarse en el no."""
    comportamiento = fixture["expected_validation_behavior"]["comportamiento_deseado_post_rechazo"]
    comportamiento_lower = comportamiento.lower()
    assert "test fixture" in comportamiento_lower or "end-to-end" in comportamiento_lower


def test_metadata_tiene_tests_pasados(fixture: dict) -> None:
    """Trazabilidad: este fixture existe porque 3 tests manuales pasaron antes."""
    assert len(fixture["metadata"]["tests_pasados"]) == 3
