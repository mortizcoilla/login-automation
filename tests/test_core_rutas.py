"""Tests de src/core/rutas.py: overrides de rutas por env (REQ-059).

Los tests re-cargan el modulo con variables seteadas para evaluar los
overrides. El fixture autouse re-carga con env limpio al final de cada
test para que las constantes no queden apuntando a rutas de test.
"""

from __future__ import annotations

import importlib

import pytest

import src.core.rutas as rutas

_VARIABLES_RUTA = (
    "DATA_DIR",
    "NOTAS_CLINICAS_DIR",
    "INFO_PACIENTE_DIR",
    "ANAMNESIS_DIR",
    "EXAMENES_CRUDOS_DIR",
    "EXAMENES_DIR",
    "ADJUNTOS_DIR",
    "FICHAS_GENERADAS_DIR",
    "INFORMES_TRAZABILIDAD_DIR",
    "ANALYSIS_DIR",
    "SCREENSHOTS_DIR",
    "LOGS_DIR",
)


@pytest.fixture(autouse=True)
def _restaurar_rutas(monkeypatch: pytest.MonkeyPatch):
    # Antes Y despues: el .env real puede inyectar overrides via
    # load_dotenv (al importar el modulo en la coleccion), y cada test
    # necesita partir de defaults limpios y dejarlos al terminar.
    # dotenv no-opeado: cada importlib.reload re-ejecuta load_dotenv y
    # sin esto re-leeria el .env real, reinjectando las rutas del usuario.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    for var in _VARIABLES_RUTA:
        monkeypatch.delenv(var, raising=False)
    importlib.reload(rutas)
    yield
    for var in _VARIABLES_RUTA:
        monkeypatch.delenv(var, raising=False)
    importlib.reload(rutas)


def test_sin_env_todos_los_defaults_son_relativos_al_repo() -> None:
    r = importlib.reload(rutas)
    assert r.DATA_DIR == r.ROOT / "data"
    assert r.NOTAS_DIR == r.DATA_DIR / "notas_clinicas"
    assert r.INFO_PACIENTE_DIR == r.DATA_DIR / "info_paciente"
    assert r.ANAMNESIS_DIR == r.DATA_DIR / "anamnesis"
    assert r.EXAMENES_CRUDOS_DIR == r.DATA_DIR / "examenes_crudos"
    assert r.EXAMENES_DIR == r.DATA_DIR / "examenes"
    assert r.ADJUNTOS_DIR == r.DATA_DIR / "adjuntos"
    assert r.FICHAS_GENERADAS_DIR == r.DATA_DIR / "fichas_generadas"
    assert r.INFORMES_TRAZABILIDAD_DIR == r.DATA_DIR / "informes_trazabilidad"
    assert r.ANALISIS_DIR == r.DATA_DIR / "analysis"
    assert r.SCREENSHOTS_DIR == r.DATA_DIR / "logs" / "screenshots"
    assert r.LOGS_DIR == r.ROOT / "logs"


def test_data_dir_mueve_todos_los_productos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    r = importlib.reload(rutas)
    assert tmp_path == r.DATA_DIR
    assert tmp_path / "notas_clinicas" == r.NOTAS_DIR
    assert tmp_path / "informes_trazabilidad" == r.INFORMES_TRAZABILIDAD_DIR
    # Los que cuelgan de ROOT no se mueven con DATA_DIR.
    assert r.LOGS_DIR == r.ROOT / "logs"


def test_override_individual_no_afecta_hermanos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("NOTAS_CLINICAS_DIR", str(tmp_path))
    r = importlib.reload(rutas)
    assert tmp_path == r.NOTAS_DIR
    assert r.INFO_PACIENTE_DIR == r.DATA_DIR / "info_paciente"


def test_ruta_relativa_se_resuelve_contra_la_raiz_del_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EXAMENES_DIR", "otro_lugar/examenes")
    r = importlib.reload(rutas)
    assert r.EXAMENES_DIR == r.ROOT / "otro_lugar" / "examenes"


def test_env_vacio_cae_al_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", "")
    r = importlib.reload(rutas)
    assert r.DATA_DIR == r.ROOT / "data"


def test_informes_siguen_a_analysis_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    monkeypatch.setenv("ANALYSIS_DIR", str(tmp_path))
    r = importlib.reload(rutas)
    assert r.informe_mes_actual_path().parent == tmp_path
    assert r.informe_anual_path().parent == tmp_path
