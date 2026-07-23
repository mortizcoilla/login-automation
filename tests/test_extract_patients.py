from __future__ import annotations

from datetime import datetime

import pytest

from src import extract_patients


@pytest.fixture
def sample_item() -> dict:
    return {
        "FechaHora": "29-05-2026 15:45-16:00",
        "HoraDeLlegada": "15:37",
        "EstadoCita": {"Nombre": "Iniciado"},
        "NombreUsuarioAps": "Karina Muñoz",
        "Cupos": [{"Descripcion": "Karina Muñoz : 119751349</br></br>Citado por: Maritza"}],
        "TipoDeCupo": "Normal",
        "Razon": "Control",
        "TipoDeAtencion": {"Nombre": "Control Crónico"},
        "Instrumento": {"Codigo": "ME"},
        "Observacion": "  EPICRISIS  ",
        "Nodo": "CESFAM Raúl Cuevas",
        "EsTeleconsulta": False,
        "UsuarioAps": {
            "Rut": "119751349",
            "NumeroDeFicha": "| 119751349| 111598900000",
            "Genero": {"Nombre": "Femenina"},
            "Sector": {"Nombre": "Sector Verde"},
            "InstitucionPrevisional": {"Nombre": "Fonasa"},
        },
    }


def test_extract_flat_record_campos_basicos(sample_item) -> None:
    rec = extract_patients.extract_flat_record(sample_item, "29-05-2026")
    assert rec["fecha"] == "29-05-2026"
    assert rec["hora_cita"] == "29-05-2026 15:45-16:00"
    assert rec["estado"] == "Iniciado"
    assert rec["nombre_paciente"] == "Karina Muñoz"
    assert rec["rut"] == "119751349"
    assert rec["numero_ficha"] == "| 119751349| 111598900000"
    assert rec["genero"] == "Femenina"
    assert rec["sector"] == "Sector Verde"
    assert rec["prevision"] == "Fonasa"
    assert rec["tipo_cupo"] == "Normal"
    assert rec["razon"] == "Control"
    assert rec["tipo_atencion"] == "Control Crónico"
    assert rec["instrumento"] == "ME"
    assert rec["observacion"] == "EPICRISIS"
    assert rec["citado_por"] == "Maritza"
    assert rec["nodo"] == "CESFAM Raúl Cuevas"
    assert rec["es_teleconsulta"] == "False"


def test_extract_flat_record_sin_observacion() -> None:
    item = {
        "Cupos": [],
        "EstadoCita": {},
        "TipoDeAtencion": {},
        "Instrumento": {},
        "UsuarioAps": {},
    }
    rec = extract_patients.extract_flat_record(item, "01-01-2026")
    assert rec["observacion"] == ""
    assert rec["citado_por"] == ""


def test_extract_flat_record_teleconsulta_true() -> None:
    item = {
        "Cupos": [],
        "EstadoCita": {},
        "TipoDeAtencion": {},
        "Instrumento": {},
        "UsuarioAps": {},
        "EsTeleconsulta": True,
    }
    rec = extract_patients.extract_flat_record(item, "01-01-2026")
    assert rec["es_teleconsulta"] == "True"


def test_working_days_excluye_fin_de_semana() -> None:
    inicio = datetime(2026, 1, 1)
    fin = datetime(2026, 1, 10)
    days = extract_patients.working_days(inicio, fin)
    for d in days:
        assert d.weekday() < 5


def test_working_days_incluye_extremos_si_son_lun_a_vie() -> None:
    inicio = datetime(2026, 1, 5)
    fin = datetime(2026, 1, 9)
    days = extract_patients.working_days(inicio, fin)
    assert days[0] == inicio
    assert days[-1] == fin


def test_working_days_invertido_retorna_vacio() -> None:
    assert extract_patients.working_days(datetime(2026, 2, 1), datetime(2026, 1, 1)) == []
