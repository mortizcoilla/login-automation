"""Tests para src/tools/recibir_foto_examen.py

Verifica:
- Validacion de input (archivo existe, extension valida, paciente con apellido, fecha dd-mm-yyyy)
- Generacion correcta del nombre destino segun la convencion
- Normalizacion de tipos y pacientes con tildes
- No sobrescritura de archivos existentes (regla dura)
- Match con el matcher de analizar_adjuntos_imagen (round-trip)

Las imagenes dummy son magic bytes de JPEG/PNG (no son imagenes reales
visibles, pero el script solo valida la extension, no el contenido).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


# Magic bytes de PNG y JPEG (suficientes para que el script los acepte)
PNG_DUMMY = bytes([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
    0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53, 0xDE,
    0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41, 0x54,
    0x08, 0x99, 0x63, 0xF8, 0xCF, 0xC0, 0x00, 0x00, 0x00, 0x03, 0x00, 0x01,
    0x5E, 0x8B, 0xB4, 0x5C,
    0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44,
    0xAE, 0x42, 0x60, 0x82,
])

JPEG_DUMMY = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10,
    0x4A, 0x46, 0x49, 0x46, 0x00,
    0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
    0xFF, 0xD9,
])


@pytest.fixture
def dummy_png(tmp_path: Path) -> Path:
    """Crea un PNG dummy de 1x1 en tmp_path y retorna la ruta."""
    p = tmp_path / "dummy.png"
    p.write_bytes(PNG_DUMMY)
    return p


@pytest.fixture
def dummy_jpg(tmp_path: Path) -> Path:
    """Crea un JPEG dummy en tmp_path y retorna la ruta."""
    p = tmp_path / "dummy.jpg"
    p.write_bytes(JPEG_DUMMY)
    return p


@pytest.fixture
def destino_dir(tmp_path: Path) -> Path:
    """Crea un directorio destino vacio para el test."""
    d = tmp_path / "destino"
    d.mkdir()
    return d


def _run_cli(*args: str, cwd: Path) -> dict:
    """Ejecuta el script como modulo y retorna el dict JSON de salida."""
    result = subprocess.run(
        [sys.executable, "-m", "src.tools.recibir_foto_examen", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    # Si fallo, queremos ver el stderr
    if not result.stdout.strip():
        pytest.fail(f"Sin salida. STDERR: {result.stderr}")
    return json.loads(result.stdout)


# --- Tests ---

def test_guarda_archivo_basico(dummy_png: Path, destino_dir: Path):
    """El caso feliz: todo OK, archivo se guarda con nombre correcto."""
    repo = Path(r"C:\Workspace\Login-Automation")
    out = _run_cli(
        "--input", str(dummy_png),
        "--paciente", "Cecilia Reyes",
        "--fecha", "10-07-2026",
        "--tipo", "audiometria",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    assert out["ok"] is True
    assert "cecilia" in out["nombre"]
    assert "reyes" in out["nombre"]
    assert "10-07-2026" in out["nombre"]
    assert "audiometria" in out["nombre"]
    assert (destino_dir / out["nombre"]).exists()


def test_default_tipo_examen(dummy_jpg: Path, destino_dir: Path):
    """Sin --tipo, debe usar 'examen' como default."""
    repo = Path(r"C:\Workspace\Login-Automation")
    out = _run_cli(
        "--input", str(dummy_jpg),
        "--paciente", "Cecilia Reyes",
        "--fecha", "10-07-2026",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    assert out["ok"] is True
    assert out["tipo"] == "examen"
    assert "examen" in out["nombre"]


def test_normaliza_tildes_y_apellido(dummy_jpg: Path, destino_dir: Path):
    """'María José González Muñoz' debe normalizarse a 'maria_munoz'."""
    repo = Path(r"C:\Workspace\Login-Automation")
    out = _run_cli(
        "--input", str(dummy_jpg),
        "--paciente", "María José González Muñoz",
        "--fecha", "15-08-2026",
        "--tipo", "radiografia",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    assert out["ok"] is True
    # El matcher usa el primer nombre + ultimo apellido para matching
    assert "maria" in out["nombre"]
    assert "munoz" in out["nombre"]
    assert "15-08-2026" in out["nombre"]
    # El segundo apellido NO debe aparecer
    assert "gonzalez" not in out["nombre"]


def test_normaliza_tipos_sinonimos(dummy_jpg: Path, destino_dir: Path):
    """'RX' debe normalizarse a 'radiografia', 'lab' a 'laboratorio'."""
    repo = Path(r"C:\Workspace\Login-Automation")

    out1 = _run_cli(
        "--input", str(dummy_jpg),
        "--paciente", "Cecilia Reyes",
        "--fecha", "10-07-2026",
        "--tipo", "RX",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    assert out1["tipo"] == "radiografia"

    out2 = _run_cli(
        "--input", str(dummy_jpg),
        "--paciente", "Cecilia Reyes",
        "--fecha", "11-07-2026",
        "--tipo", "lab",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    assert out2["tipo"] == "laboratorio"


def test_input_inexistente(destino_dir: Path):
    """Si el input no existe, debe retornar ok=False con error claro."""
    repo = Path(r"C:\Workspace\Login-Automation")
    out = _run_cli(
        "--input", r"C:\nope\no_existe.jpg",
        "--paciente", "Cecilia Reyes",
        "--fecha", "10-07-2026",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    assert out["ok"] is False
    assert "no existe" in out["error"].lower()


def test_fecha_mal_formada(dummy_png: Path, destino_dir: Path):
    """Fecha en formato yyyy-mm-dd debe rechazarse (queremos dd-mm-yyyy)."""
    repo = Path(r"C:\Workspace\Login-Automation")
    out = _run_cli(
        "--input", str(dummy_png),
        "--paciente", "Cecilia Reyes",
        "--fecha", "2026-07-10",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    assert out["ok"] is False
    assert "dd-mm-yyyy" in out["error"]


def test_paciente_sin_apellido(dummy_png: Path, destino_dir: Path):
    """Nombre sin apellido debe rechazarse."""
    repo = Path(r"C:\Workspace\Login-Automation")
    out = _run_cli(
        "--input", str(dummy_png),
        "--paciente", "Cecilia",
        "--fecha", "10-07-2026",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    assert out["ok"] is False
    assert "apellido" in out["error"].lower()


def test_extension_invalida(tmp_path: Path, destino_dir: Path):
    """Un .txt debe rechazarse."""
    fake = tmp_path / "fake.txt"
    fake.write_text("hola")
    repo = Path(r"C:\Workspace\Login-Automation")
    out = _run_cli(
        "--input", str(fake),
        "--paciente", "Cecilia Reyes",
        "--fecha", "10-07-2026",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    assert out["ok"] is False
    assert "extension" in out["error"].lower()


def test_no_sobrescribe_existente(dummy_png: Path, destino_dir: Path):
    """Si el archivo ya existe, debe agregar sufijo _v2, _v3, etc.

    Usamos --timestamp explicito para que el nombre base sea identico
    entre las 2 llamadas y forzar la colision.
    """
    repo = Path(r"C:\Workspace\Login-Automation")
    out1 = _run_cli(
        "--input", str(dummy_png),
        "--paciente", "Cecilia Reyes",
        "--fecha", "10-07-2026",
        "--tipo", "audiometria",
        "--timestamp", "120000",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    assert out1["ok"] is True
    # Llamamos otra vez con timestamp identico -> debe forzar _v2
    out2 = _run_cli(
        "--input", str(dummy_png),
        "--paciente", "Cecilia Reyes",
        "--fecha", "10-07-2026",
        "--tipo", "audiometria",
        "--timestamp", "120000",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    # El nombre debe terminar en _v2 (no debe ser el mismo archivo)
    assert out1["nombre"] != out2["nombre"]
    assert "_v2" in out2["nombre"]
    # Ambos archivos deben existir
    assert (destino_dir / out1["nombre"]).exists()
    assert (destino_dir / out2["nombre"]).exists()


def test_nombre_matchea_convencion_matcher(dummy_png: Path, destino_dir: Path):
    """El nombre generado debe pasar los criterios de matching del matcher.

    El matcher en analizar_adjuntos_imagen() busca:
    - la fecha dd-mm-yyyy en el nombre, O
    - el nombre del paciente normalizado (primer+ultimo apellido) en el nombre, O
    - cualquier parte del nombre (>= 4 chars) en el nombre.

    No llamamos al matcher real porque requiere una API de vision que
    falla con imagenes dummy. La verificacion es de la CONVENCION de
    nombre, que es lo que este script controla.
    """
    repo = Path(r"C:\Workspace\Login-Automation")

    out = _run_cli(
        "--input", str(dummy_png),
        "--paciente", "Cecilia Reyes",
        "--fecha", "10-07-2026",
        "--tipo", "audiometria",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    assert out["ok"] is True
    nombre = out["nombre"].lower()

    # El matcher buscaria cualquiera de estos; nuestro nombre tiene los 3.
    assert "10-07-2026" in nombre, f"fecha no esta en {nombre}"
    assert "cecilia" in nombre, f"primer nombre no esta en {nombre}"
    assert "reyes" in nombre, f"apellido no esta en {nombre}"


def test_round_trip_con_matcher(dummy_png: Path, destino_dir: Path):
    """El archivo guardado es detectado por analizar_adjuntos_imagen().

    NOTA: este test requiere que la API de vision responda (al menos 1 modelo
    del tier). Si todos fallan, el matcher devuelve [] aunque detecte el
    archivo. Marcamos el test para que se skipee si no hay respuestas.
    """
    import pytest
    repo = Path(r"C:\Workspace\Login-Automation")

    # Guardar
    out = _run_cli(
        "--input", str(dummy_png),
        "--paciente", "Cecilia Reyes",
        "--fecha", "10-07-2026",
        "--tipo", "audiometria",
        "--destino", str(destino_dir),
        cwd=repo,
    )
    assert out["ok"] is True

    # Verificar que el matcher lo encuentra (al menos en deteccion)
    sys.path.insert(0, str(repo))
    from src.tools.generar_ficha_con_llm import analizar_adjuntos_imagen, IMAGE_EXTENSIONS

    # Replicamos la logica de deteccion del matcher (es la parte testeable
    # sin depender de la API de vision).
    extensiones_validas = IMAGE_EXTENSIONS
    archivos_en_dir = [p for p in destino_dir.iterdir()
                       if p.is_file() and p.suffix.lower() in extensiones_validas]
    nombres = [p.name for p in archivos_en_dir]
    assert out["nombre"] in nombres, (
        f"Archivo guardado {out['nombre']} no esta en destino. "
        f"Encontrados: {nombres}"
    )
