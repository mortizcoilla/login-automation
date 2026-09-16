"""Tests para la limpieza de capturas de pantalla de logs/screenshots/."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.tools.limpiar_screenshots import limpiar, SCREENSHOTS_DIR


@pytest.fixture
def shots_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Crea un dir temporal que imita logs/screenshots/ y lo apunta via monkeypatch."""
    fake = tmp_path / "screenshots"
    fake.mkdir(parents=True)
    # Apuntar SCREENSHOTS_DIR al dir temporal durante el test.
    monkeypatch.setattr(
        "src.tools.limpiar_screenshots.SCREENSHOTS_DIR", fake
    )
    return fake


def _touch(path: Path, name: str, age_seconds: int = 0) -> Path:
    """Crea un archivo con mtime controlado."""
    f = path / name
    f.write_text("dummy", encoding="utf-8")
    if age_seconds > 0:
        # mtime en el pasado
        old = time.time() - age_seconds
        import os

        os.utime(f, (old, old))
    return f


class TestLimpiar:
    def test_borra_todos_los_archivos(
        self, shots_dir: Path
    ) -> None:
        _touch(shots_dir, "step_1_20260101_120000.png")
        _touch(shots_dir, "step_2_20260101_120100.png")
        _touch(shots_dir, "error_login_20260101_120200.png")
        _touch(shots_dir, "error_login_20260101_120200.html")

        borrados = limpiar()

        assert borrados == 4
        # Verificar que NO matchea archivos fuera del dir.
        assert list(shots_dir.glob("step_*.png")) == []
        assert list(shots_dir.glob("error_*.png")) == []
        assert list(shots_dir.glob("error_*.html")) == []

    def test_solo_borra_archivos_del_patron_correcto(
        self, shots_dir: Path
    ) -> None:
        _touch(shots_dir, "step_1_20260101_120000.png")  # match
        _touch(shots_dir, "error_login_20260101.png")  # match
        _touch(shots_dir, "notas_20260101.txt")  # NO match
        _touch(shots_dir, "log.txt")  # NO match
        _touch(shots_dir, "data.json")  # NO match

        borrados = limpiar()

        assert borrados == 2
        assert (shots_dir / "notas_20260101.txt").exists()
        assert (shots_dir / "log.txt").exists()
        assert (shots_dir / "data.json").exists()

    def test_solo_borra_archivos_viejos_con_older(
        self, shots_dir: Path
    ) -> None:
        # Reciente (hace 30 segundos) -> no se borra con --older=60
        _touch(shots_dir, "step_recent.png", age_seconds=30)
        # Viejo (hace 120 segundos) -> se borra con --older=60
        _touch(shots_dir, "step_old.png", age_seconds=120)

        borrados = limpiar(minutes=1)  # 1 minuto = 60 segundos

        assert borrados == 1
        assert (shots_dir / "step_recent.png").exists()
        assert not (shots_dir / "step_old.png").exists()

    def test_directorio_inexistente_devuelve_cero(self) -> None:
        # Si el dir no existe (caso normal antes de la primera corrida),
        # limpiar() no falla, devuelve 0.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            import os

            fake = Path(tmp) / "no_existe"
            # Sobreescribir SCREENSHOTS_DIR para apuntar a dir inexistente.
            from src.tools import limpiar_screenshots as ls

            ls.SCREENSHOTS_DIR = fake
            try:
                assert ls.limpiar() == 0
            finally:
                ls.SCREENSHOTS_DIR = SCREENSHOTS_DIR  # restaurar

    def test_dir_vacio_devuelve_cero(self, shots_dir: Path) -> None:
        # shots_dir existe pero sin archivos.
        assert limpiar() == 0

    def test_no_falla_si_algunos_archivos_no_se_pueden_borrar(
        self, shots_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Simular que un archivo no se puede borrar (permisos / lock).
        _touch(shots_dir, "step_ok.png")
        _touch(shots_dir, "step_locked.png")

        # Patcher Path.unlink para que falle SOLO en step_locked.png.
        original_unlink = Path.unlink

        def fake_unlink(self, *args, **kwargs):
            if "step_locked" in str(self):
                raise OSError("permiso denegado")
            return original_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", fake_unlink)
        borrados = limpiar()

        # step_ok.png se borro, step_locked.png no.
        assert borrados == 1
        assert not (shots_dir / "step_ok.png").exists()
        assert (shots_dir / "step_locked.png").exists()