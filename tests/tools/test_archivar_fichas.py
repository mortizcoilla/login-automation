"""Tests del archivo de fichas cerradas (REQ-082)."""

from __future__ import annotations

from pathlib import Path

from src.tools.archivar_fichas import (
    _FICHA_RE,
    archivar_fichas_cerradas,
    fichas_cerradas,
)


def _informe(tmp_path: Path, pacientes: list[tuple[str, str]]) -> Path:
    """Informe minimo con el layout del parser (5 columnas, REQ-053:
    separadas por 2+ espacios)."""
    informe = tmp_path / "informe.txt"
    lineas = ["Fichas abiertas"]
    for nombre, fecha in pacientes:
        lineas.append(f"{fecha}  {nombre}  40  Control  motivo x")
    informe.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return informe


def test_ficha_regex_separa_paciente_y_fecha() -> None:
    m = _FICHA_RE.match("ficha_Nicolas_Ignacio_Piña_Rojas_10-09-2026.md")
    assert m is not None
    assert m.group("paciente") == "Nicolas_Ignacio_Piña_Rojas"
    assert m.group("fecha") == "10-09-2026"


def test_cerradas_son_las_que_no_estan_en_el_informe(tmp_path: Path) -> None:
    informe = _informe(tmp_path, [("Amalia Jara", "15-09-2026")])
    origen = tmp_path / "fichas"
    origen.mkdir()
    (origen / "ficha_Amalia_Jara_15-09-2026.md").write_text("a", encoding="utf-8")
    (origen / "ficha_Paciente_Cerrado_10-09-2026.md").write_text("b", encoding="utf-8")

    cerradas = fichas_cerradas(informe, origen)
    assert [f.name for f in cerradas] == ["ficha_Paciente_Cerrado_10-09-2026.md"]


def test_informe_ausente_no_archiva_nada(tmp_path: Path) -> None:
    """Guardia: sin informe fresco no hay criterio de cierre."""
    origen = tmp_path / "fichas"
    origen.mkdir()
    (origen / "ficha_X_10-09-2026.md").write_text("a", encoding="utf-8")
    assert fichas_cerradas(tmp_path / "no_existe.txt", origen) == []


def test_archivar_mueve_y_deja_las_activas(tmp_path: Path) -> None:
    informe = _informe(tmp_path, [("Amalia Jara", "15-09-2026")])
    origen = tmp_path / "fichas"
    destino = tmp_path / "archivo"
    origen.mkdir()
    (origen / "ficha_Amalia_Jara_15-09-2026.md").write_text("activa", encoding="utf-8")
    (origen / "ficha_Cerrada_10-09-2026.md").write_text("cerrada", encoding="utf-8")

    movidas = archivar_fichas_cerradas(
        informe_path=informe, origen_dir=origen, destino_dir=destino
    )

    assert [(o, d) for o, d in movidas] == [
        ("ficha_Cerrada_10-09-2026.md", "ficha_Cerrada_10-09-2026.md")
    ]
    assert (origen / "ficha_Amalia_Jara_15-09-2026.md").exists(), "la activa queda"
    assert not (origen / "ficha_Cerrada_10-09-2026.md").exists()
    assert (destino / "ficha_Cerrada_10-09-2026.md").read_text(encoding="utf-8") == (
        "cerrada"
    )


def test_colision_en_destino_sufija(tmp_path: Path) -> None:
    informe = _informe(tmp_path, [("Otro", "16-09-2026")])
    origen = tmp_path / "fichas"
    destino = tmp_path / "archivo"
    origen.mkdir()
    destino.mkdir()
    (origen / "ficha_Cerrada_10-09-2026.md").write_text("nueva", encoding="utf-8")
    (destino / "ficha_Cerrada_10-09-2026.md").write_text("vieja", encoding="utf-8")

    archivar_fichas_cerradas(
        informe_path=informe, origen_dir=origen, destino_dir=destino
    )

    assert (destino / "ficha_Cerrada_10-09-2026.md").read_text(encoding="utf-8") == (
        "vieja"
    )
    assert (destino / "ficha_Cerrada_10-09-2026_v2.md").read_text(encoding="utf-8") == (
        "nueva"
    )
