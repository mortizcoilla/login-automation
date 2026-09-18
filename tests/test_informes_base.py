"""Golden sintetico del paso 5 (informe base) sobre DB fixture (Fase 4c).

Sin PII: datos sinteticos. Verifica el formato de salida (REQ-039/040)
de _cargar_fichas + _imprimir_informe sin login ni escritura en data/ real.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.informes.base import _cargar_fichas, _imprimir_informe


@pytest.fixture
def db_fixture(tmp_path: Path) -> Path:
    db = tmp_path / "fichas.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE fichas (
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            nombre TEXT NOT NULL,
            estado TEXT,
            tipo_atencion TEXT,
            PRIMARY KEY (fecha, hora, nombre)
        )
        """
    )
    filas = [
        ("04-09-2026", "08:00", "Ana Prueba Uno", "Iniciado", "Morbilidad"),
        ("04-09-2026", "09:00", "Beto Prueba Dos", "Cerrado", "Control"),
        ("05-09-2026", "10:00", "Carla Prueba Tres", "Iniciado", "Control integral ecicep-g2"),
    ]
    conn.executemany("INSERT INTO fichas VALUES (?,?,?,?,?)", filas)
    conn.commit()
    conn.close()
    return db


class TestCargarFichas:
    def test_solo_iniciado(self, db_fixture: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("src.informes.base.DB_PATH", db_fixture)
        filas = _cargar_fichas("estado = 'Iniciado' AND fecha LIKE ?", ("%-09-2026",))
        # REQ-040: solo las 2 'Iniciado', ordenadas por fecha
        assert [f["nombre"] for f in filas] == ["Ana Prueba Uno", "Carla Prueba Tres"]


class TestInformeBaseGolden:
    def test_formato_5_columnas_con_placeholders(
        self, db_fixture: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("src.informes.base.DB_PATH", db_fixture)
        filas = _cargar_fichas("estado = 'Iniciado' AND fecha LIKE ?", ("%-09-2026",))
        _imprimir_informe(filas, "09-2026")
        out = capsys.readouterr().out
        # REQ-039: 5 columnas, sin Plantilla ni Razon
        assert "Fecha" in out and "Edad" in out and "Tipo de atencion" in out
        assert "(-)" in out  # placeholders de Edad/Motivo
        assert "Plantilla" not in out
        assert "Razon" not in out
        assert "Total: 2 fichas en estado 'Iniciado'" in out
        # Distribucion final por tipo
        assert "Distribucion por tipo de atencion" in out
