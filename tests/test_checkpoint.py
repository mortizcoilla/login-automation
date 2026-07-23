from __future__ import annotations

from src import extract_patients


def test_save_and_load_checkpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(extract_patients, "CHECKPOINT_PATH", str(tmp_path / "cp.json"))
    assert extract_patients.load_checkpoint() == set()
    extract_patients.save_checkpoint({"01-01-2026", "02-01-2026"})
    assert extract_patients.load_checkpoint() == {"01-01-2026", "02-01-2026"}


def test_load_checkpoint_archivo_corrupto(tmp_path, monkeypatch) -> None:
    cp = tmp_path / "cp.json"
    cp.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(extract_patients, "CHECKPOINT_PATH", str(cp))
    assert extract_patients.load_checkpoint() == set()


def test_write_csv_crea_encabezado(tmp_path, monkeypatch) -> None:
    path = tmp_path / "p.csv"
    extract_patients.write_csv([], str(path))
    content = path.read_text(encoding="utf-8-sig")
    assert "fecha" in content
    assert "hora_cita" in content
    assert "nombre_paciente" in content
