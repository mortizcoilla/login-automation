"""Tests de la conciliacion diaria de examenes (REQ-102).

Todo crudo procesable que no aparezca en el frontmatter
archivos_origen de ningun md es PENDIENTE y debe consolidarse antes de
Mortadelo. La suite nunca llama a la API real: transcriptor fake.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf

from src.examenes.conciliar import (
    _archivos_procesados,
    _nombre_y_fecha_de_crudo,
    conciliar_pendientes,
)


def _foto(crudos: Path, nombre: str) -> Path:
    crudos.mkdir(parents=True, exist_ok=True)
    f = crudos / nombre
    f.write_bytes(b"\xff\xd8\xff\xe0fake")
    return f


def _nota(nota_dir: Path, paciente: str, fecha: str) -> None:
    """Nota clinica minima con frontmatter (fuente del match por tokens)."""
    nota_dir.mkdir(parents=True, exist_ok=True)
    safe = paciente.replace(" ", "_")
    (nota_dir / f"{safe}_{fecha}.md").write_text(
        "---\n"
        f'paciente: "{paciente}"\n'
        f'fecha_atencion: "{fecha}"\n'
        "---\n\n"
        "# Nota\n\n",
        encoding="utf-8",
    )


def _fake_ok(p: Path) -> str:
    return f"OCR de {p.name}"


class TestNombreYFechaDeCrudo:
    def test_convencion_paso_2a(self, tmp_path: Path) -> None:
        assert _nombre_y_fecha_de_crudo(tmp_path / "juan_perez_1_10-09-2026.jpg") == (
            "juan_perez",
            "10-09-2026",
        )

    def test_variante_colision_v2(self, tmp_path: Path) -> None:
        assert _nombre_y_fecha_de_crudo(tmp_path / "juan_perez_1_10-09-2026_v2.jpg") == (
            "juan_perez",
            "10-09-2026",
        )

    def test_nombre_ajeno_devuelve_none(self, tmp_path: Path) -> None:
        assert _nombre_y_fecha_de_crudo(tmp_path / "random.jpg") is None
        assert _nombre_y_fecha_de_crudo(tmp_path / "sin_fecha_1.jpg") is None


class TestArchivosProcesados:
    def test_lee_archivos_origen_de_los_mds(self, tmp_path: Path) -> None:
        (tmp_path / "exam_Juan_Perez_10-09-2026.md").write_text(
            "---\n"
            'paciente: "Juan Perez"\n'
            'fecha_atencion: "10-09-2026"\n'
            "archivos_origen:\n"
            '  - "juan_perez_1_10-09-2026.jpg"\n'
            '  - "juan_perez_2_10-09-2026.pdf"\n'
            'modelo_ocr: "x"\n'
            'fecha_digitalizacion: "2026-10-11"\n'
            "---\n\n#cuerpo\n",
            encoding="utf-8",
        )
        assert _archivos_procesados(tmp_path) == {
            "juan_perez_1_10-09-2026.jpg",
            "juan_perez_2_10-09-2026.pdf",
        }

    def test_dir_vacio_o_inexistente(self, tmp_path: Path) -> None:
        assert _archivos_procesados(tmp_path) == set()
        assert _archivos_procesados(tmp_path / "no-existe") == set()


class TestConciliarPendientes:
    def test_sin_pendientes_sale_rapido(self, tmp_path: Path) -> None:
        crudos = tmp_path / "crudos"
        destino = tmp_path / "examenes"
        notas = tmp_path / "notas"
        _foto(crudos, "juan_perez_1_10-09-2026.jpg")
        _nota(notas, "Juan Perez", "10-09-2026")
        # Primera pasada: consolida.
        r1 = conciliar_pendientes(crudos, destino, notas, transcriptor=_fake_ok)
        assert r1["pacientes_consolidados"] == 1
        # Segunda pasada: el crudo ya figura en el md -> nada pendiente.
        r2 = conciliar_pendientes(crudos, destino, notas, transcriptor=_fake_ok)
        assert r2["pendientes"] == 0
        assert r2["pacientes_consolidados"] == 0

    def test_pendiente_nuevo_se_consolidra_canonico(self, tmp_path: Path) -> None:
        crudos = tmp_path / "crudos"
        destino = tmp_path / "examenes"
        notas = tmp_path / "notas"
        _nota(notas, "Juan Perez", "10-09-2026")
        _foto(crudos, "juan_perez_1_10-09-2026.jpg")

        r = conciliar_pendientes(crudos, destino, notas, transcriptor=_fake_ok)

        assert r["pacientes_consolidados"] == 1 and r["fallidos"] == 0
        canonico = destino / "exam_Juan_Perez_10-09-2026.md"
        assert canonico.exists()
        assert "OCR de juan_perez_1_10-09-2026.jpg" in canonico.read_text(encoding="utf-8")

    def test_huerfano_con_nombre_crudo_resuelve_por_match(self, tmp_path: Path) -> None:
        """La foto llego antes de que existiera la nota: quedo archivada
        con el nombre crudo de Yadira y fecha de hoy. La conciliacion la
        re-resuelve contra las notas y consolida con nombre+fecha del
        match (la fecha del INFORME manda sobre la del filename)."""
        crudos = tmp_path / "crudos"
        destino = tmp_path / "examenes"
        notas = tmp_path / "notas"
        _nota(notas, "Gladys Valdes Castillo", "07-10-2026")
        # Archivada con el nombre parcial que Yadira escribio + fecha erronea.
        _foto(crudos, "gladys_castillo_1_11-10-2026.jpg")

        r = conciliar_pendientes(crudos, destino, notas, transcriptor=_fake_ok)

        assert r["pacientes_consolidados"] == 1
        canonico = destino / "exam_Gladys_Valdes_Castillo_07-10-2026.md"
        assert canonico.exists(), "md bajo el nombre COMPLETO y fecha del informe"
        contenido = canonico.read_text(encoding="utf-8")
        assert 'paciente: "Gladys Valdes Castillo"' in contenido
        assert 'fecha_atencion: "07-10-2026"' in contenido
        # El nombre real del archivo fuente (con su fecha de archivo)
        # se preserva en archivos_origen: la fecha del INFORME manda
        # para el md, no se reescribe la historia del archivo.

    def test_variante_huerfana_se_mezcla_al_md_existente(self, tmp_path: Path) -> None:
        """El md canonico existe (consolidado inmediato OK) pero hay una
        variante cruda sin procesar (_v2): se RECONSOLIDA el archivo
        unico con TODAS las imagenes, sin dejar _v2 de md."""
        crudos = tmp_path / "crudos"
        destino = tmp_path / "examenes"
        notas = tmp_path / "notas"
        _nota(notas, "Juan Perez", "10-09-2026")
        _foto(crudos, "juan_perez_1_10-09-2026.jpg")
        conciliar_pendientes(crudos, destino, notas, transcriptor=_fake_ok)

        # La _v2 llego despues (otro envio, misma foto): sigue pendiente.
        _foto(crudos, "juan_perez_1_10-09-2026_v2.jpg")
        r = conciliar_pendientes(crudos, destino, notas, transcriptor=_fake_ok)

        assert r["pacientes_consolidados"] == 1
        mds = list(destino.glob("exam_*.md"))
        assert len(mds) == 1, "archivo unico: sin mds _v2"
        contenido = mds[0].read_text(encoding="utf-8")
        assert "juan_perez_1_10-09-2026.jpg" in contenido
        assert "juan_perez_1_10-09-2026_v2.jpg" in contenido

    def test_sin_match_se_omite_y_no_crachea(self, tmp_path: Path) -> None:
        crudos = tmp_path / "crudos"
        destino = tmp_path / "examenes"
        notas = tmp_path / "notas"
        _foto(crudos, "paciente_desconocido_1_10-09-2026.jpg")

        r = conciliar_pendientes(crudos, destino, notas, transcriptor=_fake_ok)

        assert r["omitidos"] == 1
        assert r["pacientes_consolidados"] == 0
        assert not list(destino.glob("*.md"))

    def test_fallo_de_ocr_cuenta_fallido_y_no_bota(self, tmp_path: Path) -> None:
        crudos = tmp_path / "crudos"
        destino = tmp_path / "examenes"
        notas = tmp_path / "notas"
        _nota(notas, "Juan Perez", "10-09-2026")
        _foto(crudos, "juan_perez_1_10-09-2026.jpg")

        def roto(_p: Path) -> str:
            raise RuntimeError("API caida")

        r = conciliar_pendientes(crudos, destino, notas, transcriptor=roto)
        assert r["fallidos"] == 1
        assert r["pacientes_consolidados"] == 0

    def test_pdf_pendiente_tambien_se_consolidra(self, tmp_path: Path) -> None:
        crudos = tmp_path / "crudos"
        destino = tmp_path / "examenes"
        notas = tmp_path / "notas"
        _nota(notas, "Juan Perez", "10-09-2026")
        crudos.mkdir(parents=True, exist_ok=True)

        doc = pymupdf.open()
        pagina = doc.new_page()
        pagina.insert_text((72, 72), "GLICEMIA 95 mg/dL")
        doc.save(str(crudos / "juan_perez_1_10-09-2026.pdf"))
        doc.close()

        r = conciliar_pendientes(crudos, destino, notas, transcriptor=_fake_ok)
        assert r["pacientes_consolidados"] == 1
        canonico = destino / "exam_Juan_Perez_10-09-2026.md"
        assert "[pagina 1]" in canonico.read_text(encoding="utf-8")

    def test_sin_logger_no_crachea(self, tmp_path: Path) -> None:
        crudos = tmp_path / "crudos"
        _foto(crudos, "juan_perez_1_10-09-2026.jpg")
        r = conciliar_pendientes(
            crudos, tmp_path / "e", tmp_path / "n", transcriptor=_fake_ok, logger=None
        )
        assert r["pendientes"] == 1
