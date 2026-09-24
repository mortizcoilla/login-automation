"""Tests para src/tools/recibir_foto_examen.py (Rubicita, paso 2a).

Alcance vigente (decision Yadira/Miguel 2026-09-17): SOLO recibe,
resuelve paciente/fecha contra data/notas_clinicas/, RENOMBRA y ARCHIVA
en el directorio de examenes crudos. NO hace OCR ni genera exam_*.md.

Restaurado de git (8709f83) y reescrito contra la API actual en la
sesion de refactor 2026-09-18 (los tests originales probaban la API con
OCR que fue eliminada).
"""

from __future__ import annotations

from pathlib import Path

from src.core.fechas import fecha_hoy_str
from src.tools.recibir_foto_examen import (
    _parsear_frontmatter,
    buscar_match_paciente,
    construir_nombre_destino,
    nombre_a_filename,
    normalizar_texto,
    recibir_y_archivar,
    resolver_path_sin_colision,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"fake-jpeg-payload" * 10


def _crear_foto(tmp_path: Path, nombre: str = "foto.jpg", payload: bytes = JPEG_BYTES) -> Path:
    foto = tmp_path / nombre
    foto.write_bytes(payload)
    return foto


def _crear_nota(
    notas_dir: Path,
    paciente: str,
    fecha_atencion: str,
    filename: str = "nota.md",
) -> Path:
    """Crea una nota clinica .md con el frontmatter que emite
    crear_notas_clinicas (paciente + fecha_atencion entre comillas)."""
    notas_dir.mkdir(parents=True, exist_ok=True)
    nota = notas_dir / filename
    nota.write_text(
        f'---\npaciente: "{paciente}"\nfecha_atencion: "{fecha_atencion}"\n---\n\n# Nota clinica\n',
        encoding="utf-8",
    )
    return nota


# ---------------------------------------------------------------------------
# normalizar_texto / nombre_a_filename
# ---------------------------------------------------------------------------


class TestNormalizacion:
    def test_quita_tildes_y_pasa_a_minusculas(self) -> None:
        assert normalizar_texto("Lucía Ñandú") == "lucia nandu"

    def test_colapsa_espacios_y_guiones_bajos(self) -> None:
        assert normalizar_texto("  Juan   Perez ") == "juan perez"
        assert normalizar_texto("Juan_Perez") == "juan perez"

    def test_nombre_a_filename_espacios_a_guion_bajo(self) -> None:
        assert nombre_a_filename("Benedicto Alfonso Martin") == ("benedicto_alfonso_martin")

    def test_nombre_a_filename_sin_tildes(self) -> None:
        assert nombre_a_filename("Lucía Adela Zambrano") == ("lucia_adela_zambrano")


# ---------------------------------------------------------------------------
# _parsear_frontmatter
# ---------------------------------------------------------------------------


class TestParsearFrontmatter:
    def test_extrae_campos_entre_comillas(self) -> None:
        texto = '---\npaciente: "Juan Perez"\nfecha_atencion: "10-09-2026"\n---\n\ncuerpo\n'
        meta = _parsear_frontmatter(texto)
        assert meta["paciente"] == "Juan Perez"
        assert meta["fecha_atencion"] == "10-09-2026"

    def test_sin_frontmatter_devuelve_vacio(self) -> None:
        assert _parsear_frontmatter("# Nota sin frontmatter\n") == {}

    def test_frontmatter_sin_cierre_devuelve_vacio(self) -> None:
        assert _parsear_frontmatter('---\npaciente: "X"\n') == {}


# ---------------------------------------------------------------------------
# buscar_match_paciente
# ---------------------------------------------------------------------------


class TestBuscarMatchPaciente:
    def _indice(self):
        return [
            {
                "paciente": "Benedicto Alfonso Martin Colimil",
                "paciente_norm": "benedicto alfonso martin colimil",
                "fecha_atencion": "16-09-2026",
                "file": "nota1.md",
            },
            {
                "paciente": "Benedicto Oro Riquelme",
                "paciente_norm": "benedicto oro riquelme",
                "fecha_atencion": "10-09-2026",
                "file": "nota2.md",
            },
        ]

    def test_match_parcial_por_tokens(self) -> None:
        match = buscar_match_paciente("Benedicto Martin", self._indice())
        assert match is not None
        assert match["paciente"] == "Benedicto Alfonso Martin Colimil"

    def test_prefiere_mas_coincidencias(self) -> None:
        # "Benedicto Alfonso" tiene 2 tokens en comun con el primero
        # y 1 con el segundo: gana el primero.
        match = buscar_match_paciente("Benedicto Alfonso", self._indice())
        assert match is not None
        assert match["paciente"] == "Benedicto Alfonso Martin Colimil"

    def test_sin_match_devuelve_none(self) -> None:
        assert buscar_match_paciente("Perico Los Palotes", self._indice()) is None

    def test_nombre_vacio_devuelve_none(self) -> None:
        assert buscar_match_paciente("   ", self._indice()) is None

    def test_tokens_cortos_ignorados(self) -> None:
        # "de" (< 3 chars) no cuenta como token de match
        assert buscar_match_paciente("de", self._indice()) is None


# ---------------------------------------------------------------------------
# construir_nombre_destino / resolver_path_sin_colision
# ---------------------------------------------------------------------------


class TestNombresDestino:
    def test_construir_nombre(self) -> None:
        assert construir_nombre_destino("juan_perez", "10-09-2026", 2, ".JPG") == (
            "juan_perez_2_10-09-2026.jpg"
        )

    def test_colision_agrega_v2(self, tmp_path: Path) -> None:
        (tmp_path / "juan_perez_1_10-09-2026.jpg").write_bytes(b"x")
        destino = resolver_path_sin_colision(tmp_path, "juan_perez_1_10-09-2026.jpg")
        assert destino.name == "juan_perez_1_10-09-2026_v2.jpg"

    def test_sin_colision_mantiene_nombre(self, tmp_path: Path) -> None:
        destino = resolver_path_sin_colision(tmp_path, "juan_perez_1_10-09-2026.jpg")
        assert destino.name == "juan_perez_1_10-09-2026.jpg"


# ---------------------------------------------------------------------------
# recibir_y_archivar — casos de error
# ---------------------------------------------------------------------------


class TestRecibirYArchivarErrores:
    def test_input_inexistente(self, tmp_path: Path) -> None:
        r = recibir_y_archivar(
            input_path=tmp_path / "no_existe.jpg",
            indice_n=1,
            nombre_paciente="Juan Perez",
            fecha_atencion="10-09-2026",
        )
        assert r["ok"] is False
        assert "no existe" in r["error"].lower()

    def test_extension_invalida(self, tmp_path: Path) -> None:
        foto = _crear_foto(tmp_path, "video.mp4", b"x")
        r = recibir_y_archivar(
            input_path=foto,
            indice_n=1,
            nombre_paciente="Juan Perez",
            fecha_atencion="10-09-2026",
        )
        assert r["ok"] is False
        assert "no aceptada" in r["error"]

    def test_indice_menor_que_1(self, tmp_path: Path) -> None:
        foto = _crear_foto(tmp_path)
        r = recibir_y_archivar(
            input_path=foto,
            indice_n=0,
            nombre_paciente="Juan Perez",
            fecha_atencion="10-09-2026",
        )
        assert r["ok"] is False
        assert "indice" in r["error"].lower()

    def test_sin_nombre_rubicita_no_adivina(self, tmp_path: Path) -> None:
        foto = _crear_foto(tmp_path)
        r = recibir_y_archivar(
            input_path=foto,
            indice_n=1,
            nombre_paciente=None,
            fecha_atencion="10-09-2026",
        )
        assert r["ok"] is False
        assert "NO adivina" in r["error"]

    def test_fecha_mal_formada_con_match(self, tmp_path: Path) -> None:
        # Yadira da fecha invalida y hay match: el formato se valida igual.
        foto = _crear_foto(tmp_path)
        notas = tmp_path / "notas"
        _crear_nota(notas, "Juan Perez", "10-09-2026")
        r = recibir_y_archivar(
            input_path=foto,
            indice_n=1,
            nombre_paciente="Juan Perez",
            fecha_atencion="10-13-2026",
            notas_dir=notas,
            destino_dir=tmp_path / "crudos",
        )
        # 10-13-2026 no es valida (mes 13) ni coincide con el informe
        assert r["ok"] is False
        assert "valida" in r["error"]

    def test_sin_fecha_sin_match_archiva_con_hoy(self, tmp_path: Path) -> None:
        """REQ-080/permiso usuaria: la foto NUNCA se pierde — paciente sin
        match y sin fecha se archiva con HOY y el nombre dado."""
        foto = _crear_foto(tmp_path)
        r = recibir_y_archivar(
            input_path=foto,
            indice_n=1,
            nombre_paciente="Desconocido Total",
            fecha_atencion=None,
            notas_dir=tmp_path / "notas",
            destino_dir=tmp_path / "crudos",
        )
        assert r["ok"] is True
        assert r["fecha_resuelta"] == fecha_hoy_str()
        assert (tmp_path / "crudos" / r["nombre"]).exists()


# ---------------------------------------------------------------------------
# recibir_y_archivar — casos de exito
# ---------------------------------------------------------------------------


class TestRecibirYArchivarOk:
    def test_archiva_con_nombre_y_fecha_completos(self, tmp_path: Path) -> None:
        foto = _crear_foto(tmp_path)
        destino_dir = tmp_path / "crudos"
        r = recibir_y_archivar(
            input_path=foto,
            indice_n=1,
            nombre_paciente="Juan Perez",
            fecha_atencion="10-09-2026",
            notas_dir=tmp_path / "notas",  # vacio: sin matching
            destino_dir=destino_dir,
        )
        assert r["ok"] is True, r["error"]
        assert r["nombre"] == "juan_perez_1_10-09-2026.jpg"
        assert r["path"].endswith(r["nombre"])
        assert Path(r["path"]).exists()
        # Copia byte-a-bit (sin re-encode)
        assert Path(r["path"]).read_bytes() == JPEG_BYTES

    def test_match_resuelve_nombre_completo_y_fecha_del_informe(self, tmp_path: Path) -> None:
        # Yadira da nombre parcial y la fecha de HOY; el informe manda.
        foto = _crear_foto(tmp_path)
        notas = tmp_path / "notas"
        _crear_nota(notas, "Benedicto Alfonso Martin Colimil", "16-09-2026")
        r = recibir_y_archivar(
            input_path=foto,
            indice_n=1,
            nombre_paciente="Benedicto Martin",
            fecha_atencion="18-09-2026",
            notas_dir=notas,
            destino_dir=tmp_path / "crudos",
        )
        assert r["ok"] is True, r["error"]
        assert r["paciente_resuelto"] == "Benedicto Alfonso Martin Colimil"
        assert r["fecha_resuelta"] == "16-09-2026"
        assert r["fecha_input_descartada"] is True
        assert r["nombre"] == "benedicto_alfonso_martin_colimil_1_16-09-2026.jpg"

    def test_sin_fecha_usa_la_del_match(self, tmp_path: Path) -> None:
        foto = _crear_foto(tmp_path)
        notas = tmp_path / "notas"
        _crear_nota(notas, "Juan Perez", "10-09-2026")
        r = recibir_y_archivar(
            input_path=foto,
            indice_n=1,
            nombre_paciente="Juan Perez",
            fecha_atencion=None,
            notas_dir=notas,
            destino_dir=tmp_path / "crudos",
        )
        assert r["ok"] is True, r["error"]
        assert r["fecha_resuelta"] == "10-09-2026"

    def test_fecha_coincidente_no_se_descarta(self, tmp_path: Path) -> None:
        foto = _crear_foto(tmp_path)
        notas = tmp_path / "notas"
        _crear_nota(notas, "Juan Perez", "10-09-2026")
        r = recibir_y_archivar(
            input_path=foto,
            indice_n=1,
            nombre_paciente="Juan Perez",
            fecha_atencion="10-09-2026",
            notas_dir=notas,
            destino_dir=tmp_path / "crudos",
        )
        assert r["ok"] is True, r["error"]
        assert r["fecha_input_descartada"] is False

    def test_no_sobrescribe_existente(self, tmp_path: Path) -> None:
        destino_dir = tmp_path / "crudos"
        destino_dir.mkdir()
        (destino_dir / "juan_perez_1_10-09-2026.jpg").write_bytes(b"original")
        foto = _crear_foto(tmp_path)
        r = recibir_y_archivar(
            input_path=foto,
            indice_n=1,
            nombre_paciente="Juan Perez",
            fecha_atencion="10-09-2026",
            notas_dir=tmp_path / "notas",
            destino_dir=destino_dir,
        )
        assert r["ok"] is True, r["error"]
        assert r["nombre"] == "juan_perez_1_10-09-2026_v2.jpg"
        # El original queda intacto
        assert (destino_dir / "juan_perez_1_10-09-2026.jpg").read_bytes() == (b"original")
