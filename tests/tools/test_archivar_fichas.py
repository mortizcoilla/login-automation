"""Tests del archivo de productos cerrados (REQ-082/088). Sin datos reales."""

from __future__ import annotations

from pathlib import Path

from src.tools.archivar_fichas import (
    PRODUCTOS,
    archivar_cerrados,
    cerrados_por_producto,
)


def _informe(tmp_path: Path, pacientes: list[tuple[str, str]]) -> Path:
    """Informe minimo con el layout del parser (5 columnas, 2+ espacios)."""
    informe = tmp_path / "informe.txt"
    lineas = ["Fichas abiertas"]
    for nombre, fecha in pacientes:
        lineas.append(f"{fecha}  {nombre}  40  Control  motivo x")
    informe.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return informe


def _dirs_falsos(tmp_path: Path) -> dict[str, Path]:
    """Crea las carpetas de los 5 productos y devuelve nombre->dir."""
    dirs = {}
    for nombre, _dir, _prefijo in PRODUCTOS:
        d = tmp_path / nombre
        d.mkdir()
        dirs[nombre] = d
    return dirs


def _sembrar(dirs: dict[str, Path], nombre_producto: str, archivo: str) -> Path:
    ruta = dirs[nombre_producto] / archivo
    ruta.write_text("x", encoding="utf-8")
    return ruta


def test_cerrados_por_producto_cubre_los_5_productos(tmp_path: Path) -> None:
    informe = _informe(tmp_path, [("Amalia Jara", "15-09-2026")])
    dirs = _dirs_falsos(tmp_path)
    # Activa (en el informe) y cerrada (no esta) en cada producto
    _sembrar(dirs, "notas_clinicas", "Amalia_Jara_15-09-2026.md")
    _sembrar(dirs, "notas_clinicas", "Cerrada_Total_10-09-2026.md")
    _sembrar(dirs, "info_paciente", "info_Amalia_Jara_15-09-2026.md")
    _sembrar(dirs, "info_paciente", "info_Cerrada_Total_10-09-2026.md")
    _sembrar(dirs, "anamnesis", "anam_Amalia_Jara_15-09-2026.md")
    _sembrar(dirs, "anamnesis", "anam_Cerrada_Total_10-09-2026.md")
    _sembrar(dirs, "fichas_generadas", "ficha_Amalia_Jara_15-09-2026.md")
    _sembrar(dirs, "fichas_generadas", "ficha_Cerrada_Total_10-09-2026.md")
    _sembrar(dirs, "informes_trazabilidad", "informe_trazabilidad_Amalia_Jara_15-09-2026.md")
    _sembrar(dirs, "informes_trazabilidad", "informe_trazabilidad_Cerrada_Total_10-09-2026.md")

    por_producto = cerrados_por_producto(informe, dirs)
    for nombre in dirs:
        cerrados = [p.name for p in por_producto[nombre]]
        assert cerrados == [f for f in cerrados if "Cerrada_Total" in f], nombre
        assert len(cerrados) == 1, f"{nombre}: solo la cerrada"


def test_informe_ausente_no_archiva_nada(tmp_path: Path) -> None:
    """Guardia: sin informe fresco no hay criterio de cierre."""
    dirs = _dirs_falsos(tmp_path)
    _sembrar(dirs, "notas_clinicas", "X_10-09-2026.md")
    por_producto = cerrados_por_producto(tmp_path / "no_existe.txt", dirs)
    assert all(v == [] for v in por_producto.values())


def test_archivar_mueve_al_folder_unificado(tmp_path: Path) -> None:
    informe = _informe(tmp_path, [("Amalia Jara", "15-09-2026")])
    dirs = _dirs_falsos(tmp_path)
    destino = tmp_path / "archivados"
    _sembrar(dirs, "notas_clinicas", "Amalia_Jara_15-09-2026.md")
    cerrada = _sembrar(dirs, "notas_clinicas", "Cerrada_Total_10-09-2026.md")
    _sembrar(dirs, "anamnesis", "anam_Cerrada_Total_10-09-2026.md")

    movidas = archivar_cerrados(
        informe_path=informe, destino_dir=destino, dirs_override=dirs
    )

    assert sorted(m[1] for m in movidas) == [
        "Cerrada_Total_10-09-2026.md",
        "anam_Cerrada_Total_10-09-2026.md",
    ]
    assert not cerrada.exists(), "salio de la carpeta activa"
    assert (destino / "Cerrada_Total_10-09-2026.md").exists()
    assert (destino / "anam_Cerrada_Total_10-09-2026.md").exists()
    assert (dirs["notas_clinicas"] / "Amalia_Jara_15-09-2026.md").exists()


def test_archivo_sin_fecha_reconocible_no_se_toca(tmp_path: Path) -> None:
    informe = _informe(tmp_path, [("Amalia Jara", "15-09-2026")])
    dirs = _dirs_falsos(tmp_path)
    rara = _sembrar(dirs, "notas_clinicas", "README.md")
    _sembrar(dirs, "info_paciente", "info_sin_fecha.md")

    movidas = archivar_cerrados(informe_path=informe, destino_dir=tmp_path / "a", dirs_override=dirs)

    assert movidas == []
    assert rara.exists()
