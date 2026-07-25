from __future__ import annotations

import os
from datetime import datetime

import pytest

from src import plantillas


@pytest.fixture
def tmp_plantillas(tmp_path, monkeypatch):
    # Archivos con nombres canonicos (uppercase), segun la regla de uso.
    # La nueva logica de cargar_plantilla usa reglas_plantillas.py para
    # resolver el nombre del archivo, no el tipo de Rayen directamente.
    (tmp_path / "MORBILIDAD.txt").write_text("Hola {PACIENTE}", encoding="utf-8")
    (tmp_path / "RECETA.txt").write_text("Receta para {PACIENTE}", encoding="utf-8")
    (tmp_path / "vacio.txt").write_text("", encoding="utf-8")
    (tmp_path / "completadas").mkdir()
    monkeypatch.setattr(plantillas, "PLANTILLAS_DIR", str(tmp_path))
    monkeypatch.setattr(plantillas, "COMPLETADAS_DIR", str(tmp_path / "completadas"))
    return tmp_path


def test_listar_tipos(tmp_plantillas) -> None:
    tipos = plantillas.listar_tipos_atencion()
    assert "MORBILIDAD" in tipos
    assert "RECETA" in tipos
    assert "vacio" in tipos
    assert all(isinstance(t, str) for t in tipos)


def test_cargar_plantilla_existente(tmp_plantillas) -> None:
    # "Morbilidad" (tipo de Rayen) -> "MORBILIDAD" (plantilla canonica)
    assert plantillas.cargar_plantilla("Morbilidad") == "Hola {PACIENTE}"


def test_cargar_plantilla_inexistente(tmp_plantillas) -> None:
    assert plantillas.cargar_plantilla("No existe") is None


def test_cargar_plantilla_sanitiza_prefijo(tmp_plantillas) -> None:
    # "ME, Recetas" -> sanitiza a "Recetas" -> RECETA
    assert plantillas.cargar_plantilla("ME, Recetas") == "Receta para {PACIENTE}"


def test_cargar_plantilla_con_nombre_sanitizado(tmp_plantillas) -> None:
    # "Recetas" -> RECETA
    assert plantillas.cargar_plantilla("Recetas") == "Receta para {PACIENTE}"


def test_rellenar_plantilla(tmp_plantillas) -> None:
    out = plantillas.rellenar_plantilla(
        "Paciente: {PACIENTE}\nRUT: {RUT}\nFecha: {FECHA}",
        {"nombre": "Juan", "rut": "12345678-9", "fecha": "15-05-2026"},
    )
    assert "Paciente: Juan" in out
    assert "RUT: 12345678-9" in out
    assert "Fecha: 15-05-2026" in out


def test_rellenar_usa_hoy_por_defecto(tmp_plantillas) -> None:
    out = plantillas.rellenar_plantilla("Fecha: {FECHA}", {})
    expected = datetime.now().strftime("%d-%m-%Y")
    assert expected in out


def test_rellenar_tipo_atencion_sanitizado(tmp_plantillas) -> None:
    out = plantillas.rellenar_plantilla(
        "Tipo: {TIPO_ATENCION}", {"tipo_atencion": "ME, Morbilidad"}
    )
    assert "Tipo: Morbilidad" in out


def test_guardar_plantilla(tmp_plantillas) -> None:
    ruta = plantillas.guardar_plantilla("contenido", "Juan Pérez")
    assert os.path.exists(ruta)
    assert "Juan" in ruta
    with open(ruta, encoding="utf-8") as f:
        assert "contenido" in f.read()


def test_guardar_caracteres_especiales(tmp_plantillas) -> None:
    ruta = plantillas.guardar_plantilla("x", "María José / López")
    assert os.path.exists(ruta)
    assert "/" not in os.path.basename(ruta)


def test_placeholders_disponibles() -> None:
    placeholders = plantillas.placeholders_disponibles()
    assert "{PACIENTE}" in placeholders
    assert "{FECHA}" in placeholders
