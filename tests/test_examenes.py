"""Tests del paso 2b (examenes): consolidacion con vision mockeada (REQ-047).

La suite NUNCA llama a la API real: se inyecta un transcriptor fake.
"""

from __future__ import annotations

from pathlib import Path

from src.examenes.consolidar import buscar_fotos_crudas, consolidar_examenes
from src.examenes.vision_api import VisionAPIError


def _foto(crudos: Path, nombre: str) -> Path:
    crudos.mkdir(parents=True, exist_ok=True)
    f = crudos / nombre
    f.write_bytes(b"\xff\xd8\xff\xe0fake")
    return f


def _fake_ok(p: Path) -> str:
    return f"TRANSCRIPCION de {p.name}"


def _fake_falla(p: Path) -> str:
    raise VisionAPIError("quota exceeded")


class TestBuscarFotosCrudas:
    def test_por_prefijo_y_orden(self, tmp_path: Path) -> None:
        _foto(tmp_path, "juan_perez_1_10-09-2026.jpg")
        _foto(tmp_path, "juan_perez_2_10-09-2026.jpg")
        _foto(tmp_path, "otro_paciente_1_10-09-2026.jpg")
        fotos = buscar_fotos_crudas("Juan Perez", None, tmp_path)
        assert [f.name for f in fotos] == [
            "juan_perez_1_10-09-2026.jpg",
            "juan_perez_2_10-09-2026.jpg",
        ]

    def test_filtro_por_fecha(self, tmp_path: Path) -> None:
        _foto(tmp_path, "juan_perez_1_10-09-2026.jpg")
        _foto(tmp_path, "juan_perez_1_12-09-2026.jpg")
        fotos = buscar_fotos_crudas("Juan Perez", "12-09-2026", tmp_path)
        assert [f.name for f in fotos] == ["juan_perez_1_12-09-2026.jpg"]

    def test_ignora_pdfs(self, tmp_path: Path) -> None:
        (tmp_path / "juan_perez_1_10-09-2026.pdf").write_bytes(b"x")
        assert buscar_fotos_crudas("Juan Perez", None, tmp_path) == []


class TestConsolidar:
    def test_ok_dos_fotos(self, tmp_path: Path) -> None:
        crudos = tmp_path / "crudos"
        _foto(crudos, "juan_perez_1_10-09-2026.jpg")
        _foto(crudos, "juan_perez_2_10-09-2026.jpg")
        r = consolidar_examenes(
            "Juan Perez",
            crudos_dir=crudos,
            destino_dir=tmp_path / "out",
            transcriptor=_fake_ok,
            modelo="glm-test",
        )
        assert r["ok"] is True, r["error"]
        out = Path(r["path"])
        assert out.name == "exam_Juan_Perez_10-09-2026.md"
        texto = out.read_text(encoding="utf-8")
        assert 'paciente: "Juan Perez"' in texto
        assert "TRANSCRIPCION de juan_perez_1_10-09-2026.jpg" in texto
        assert "archivos_origen:" in texto
        assert 'modelo_ocr: "glm-test (vision API)"' in texto
        # fecha resuelta desde el nombre del archivo
        assert r["fecha_resuelta"] == "10-09-2026"

    def test_no_sobrescribe(self, tmp_path: Path) -> None:
        crudos = tmp_path / "crudos"
        _foto(crudos, "juan_perez_1_10-09-2026.jpg")
        out = tmp_path / "out"
        out.mkdir()
        (out / "exam_Juan_Perez_10-09-2026.md").write_text("original", encoding="utf-8")
        r = consolidar_examenes(
            "Juan Perez", crudos_dir=crudos, destino_dir=out, transcriptor=_fake_ok
        )
        assert r["ok"] is True
        assert Path(r["path"]).name == "exam_Juan_Perez_10-09-2026_v2.md"
        assert (out / "exam_Juan_Perez_10-09-2026.md").read_text(encoding="utf-8") == "original"

    def test_sin_fotos_error(self, tmp_path: Path) -> None:
        r = consolidar_examenes("Nadie", crudos_dir=tmp_path, destino_dir=tmp_path)
        assert r["ok"] is False
        assert "No hay fotos" in r["error"]

    def test_api_falla_no_escribe_nada(self, tmp_path: Path) -> None:
        crudos = tmp_path / "crudos"
        _foto(crudos, "juan_perez_1_10-09-2026.jpg")
        out = tmp_path / "out"
        r = consolidar_examenes(
            "Juan Perez", crudos_dir=crudos, destino_dir=out, transcriptor=_fake_falla
        )
        assert r["ok"] is False
        assert "fallaron" in r["error"]
        assert not list(out.glob("*.md")) if out.exists() else True

    def test_fallo_parcial_marca_la_foto(self, tmp_path: Path) -> None:
        crudos = tmp_path / "crudos"
        _foto(crudos, "juan_perez_1_10-09-2026.jpg")
        _foto(crudos, "juan_perez_2_10-09-2026.jpg")
        llamadas = {"n": 0}

        def mixto(p: Path) -> str:
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                raise VisionAPIError("timeout")
            return "OK"

        r = consolidar_examenes(
            "Juan Perez",
            crudos_dir=crudos,
            destino_dir=tmp_path / "out",
            transcriptor=mixto,
        )
        assert r["ok"] is True  # al menos una transcripcion
        texto = Path(r["path"]).read_text(encoding="utf-8")
        assert "transcripcion fallo: timeout" in texto
        assert "OK" in texto
