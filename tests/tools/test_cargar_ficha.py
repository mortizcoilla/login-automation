"""Tests para el CLI `cargar_ficha` (paso 8).

Cubren:
- Lectura del archivo de paso 7 (existe / no existe / vacio).
- Path del archivo generado (safe_filename conserva tildes).
- Carga de un paciente: ok, skip por sin insumo, skip por no encontrado.
- Carga de un paciente con panel no cargado -> estado error.
- Iteracion batch: cada paciente genera un ResultadoCarga.
- Trazabilidad: escribe JSON con resumen correcto.
- CLI argparse: --paciente+--fecha y --todos; rechaza informe anual.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.notas.modelos import PacienteObjetivo
from src.tools import cargar_ficha


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("test_cargar_ficha")


@pytest.fixture
def paciente() -> PacienteObjetivo:
    return PacienteObjetivo(
        fecha="15-09-2026",
        nombre="Amalia Andrea Jara Irarrázabal",
        tipo_atencion="Control",
    )


# ---------------------------------------------------------------------------
# Helpers: leer_ficha_generada / _path_ficha_generada
# ---------------------------------------------------------------------------


def test_path_ficha_generada_conserva_tildes(tmp_path: Path) -> None:
    path = cargar_ficha._path_ficha_generada(
        "Amalia Andrea Jara Irarrázabal", "15-09-2026", tmp_path
    )
    # safe_filename conserva mayusculas y tildes (REQ-002).
    assert path.name == "ficha_Amalia_Andrea_Jara_Irarrázabal_15-09-2026.md"


def test_leer_ficha_generada_existe(tmp_path: Path) -> None:
    (tmp_path / "ficha_Amalia_Andrea_Jara_Irarrázabal_15-09-2026.md").write_text(
        "> **Motivo:** control\n\ntexto de la anamnesis\n",
        encoding="utf-8",
    )
    texto = cargar_ficha.leer_ficha_generada(
        "Amalia Andrea Jara Irarrázabal", "15-09-2026", tmp_path
    )
    assert texto is not None
    assert "texto de la anamnesis" in texto


def test_leer_ficha_generada_no_existe(tmp_path: Path) -> None:
    texto = cargar_ficha.leer_ficha_generada(
        "Fantasma", "15-09-2026", tmp_path
    )
    assert texto is None


def test_leer_ficha_generada_archivo_vacio(tmp_path: Path) -> None:
    (tmp_path / "ficha_Fantasma_15-09-2026.md").write_text("   \n  \n", encoding="utf-8")
    texto = cargar_ficha.leer_ficha_generada(
        "Fantasma", "15-09-2026", tmp_path
    )
    # Vacio se considera "no hay insumo util" -> None.
    assert texto is None


# ---------------------------------------------------------------------------
# Carga de un paciente
# ---------------------------------------------------------------------------


def test_cargar_ficha_de_paciente_sin_insumo_es_skip(
    paciente: PacienteObjetivo,
    logger: logging.Logger,
    tmp_path: Path,
) -> None:
    """Si no existe el .md del paso 7 -> skip."""
    fake_driver = MagicMock()
    resultado = cargar_ficha.cargar_ficha_de_paciente(
        fake_driver, logger, paciente, fichas_dir=tmp_path
    )
    assert resultado.estado == "skip"
    assert "sin insumo" in resultado.motivo
    assert resultado.ficha_path == ""


def test_cargar_ficha_de_paciente_no_encontrado_en_tabla_es_skip(
    paciente: PacienteObjetivo,
    logger: logging.Logger,
    tmp_path: Path,
) -> None:
    (tmp_path / "ficha_Amalia_Andrea_Jara_Irarrázabal_15-09-2026.md").write_text(
        "> **Motivo:** control\n\nanamnesis\n",
        encoding="utf-8",
    )
    fake_driver = MagicMock()

    with patch(
        "src.tools.cargar_ficha.abrir_ficha_por_nombre",
        return_value=False,  # paciente no esta en la tabla
    ):
        resultado = cargar_ficha.cargar_ficha_de_paciente(
            fake_driver, logger, paciente, fichas_dir=tmp_path
        )

    assert resultado.estado == "skip"
    assert "no encontrado" in resultado.motivo


def test_cargar_ficha_de_paciente_panel_no_cargo_es_error(
    paciente: PacienteObjetivo,
    logger: logging.Logger,
    tmp_path: Path,
) -> None:
    (tmp_path / "ficha_Amalia_Andrea_Jara_Irarrázabal_15-09-2026.md").write_text(
        "> **Motivo:** control\n\nanamnesis\n",
        encoding="utf-8",
    )
    fake_driver = MagicMock()
    paciente.panel_cargo = False  # simula REQ-030

    with patch(
        "src.tools.cargar_ficha.abrir_ficha_por_nombre",
        return_value=True,
    ), patch(
        "src.tools.cargar_ficha.pegar_en_editor"
    ) as mock_peg:
        resultado = cargar_ficha.cargar_ficha_de_paciente(
            fake_driver, logger, paciente, fichas_dir=tmp_path
        )

    assert resultado.estado == "error"
    assert "panel" in resultado.motivo.lower()
    # No se intento pegar.
    mock_peg.assert_not_called()


def test_cargar_ficha_de_paciente_exitoso(
    paciente: PacienteObjetivo,
    logger: logging.Logger,
    tmp_path: Path,
) -> None:
    texto = "> **Motivo:** control\n\nanamnesis completa\n"
    (tmp_path / "ficha_Amalia_Andrea_Jara_Irarrázabal_15-09-2026.md").write_text(
        texto, encoding="utf-8"
    )
    fake_driver = MagicMock()
    paciente.panel_cargo = True

    with patch(
        "src.tools.cargar_ficha.abrir_ficha_por_nombre",
        return_value=True,
    ), patch(
        "src.tools.cargar_ficha.pegar_en_editor",
        return_value=cargar_ficha.pegador_fake_ok(len(texto)),
    ):
        resultado = cargar_ficha.cargar_ficha_de_paciente(
            fake_driver, logger, paciente, fichas_dir=tmp_path
        )

    assert resultado.estado == "ok"
    assert resultado.caracteres_pegados == len(texto)
    assert resultado.ficha_path != ""


def test_cargar_ficha_de_paciente_pendiente_selector(
    paciente: PacienteObjetivo,
    logger: logging.Logger,
    tmp_path: Path,
) -> None:
    """Si el pegador devuelve 'pendiente selector' -> estado asi."""
    texto = "contenido"
    (tmp_path / "ficha_Amalia_Andrea_Jara_Irarrázabal_15-09-2026.md").write_text(
        texto, encoding="utf-8"
    )
    fake_driver = MagicMock()
    paciente.panel_cargo = True

    with patch(
        "src.tools.cargar_ficha.abrir_ficha_por_nombre",
        return_value=True,
    ), patch(
        "src.tools.cargar_ficha.pegar_en_editor",
        return_value=cargar_ficha.pegador_fake_pendiente_selector(),
    ):
        resultado = cargar_ficha.cargar_ficha_de_paciente(
            fake_driver, logger, paciente, fichas_dir=tmp_path
        )

    assert resultado.estado == "pendiente_selector"


# ---------------------------------------------------------------------------
# Iterador batch
# ---------------------------------------------------------------------------


def test_iterar_pacientes_mezcla_estados(
    logger: logging.Logger,
    tmp_path: Path,
) -> None:
    """Si un paciente falla, el batch sigue con el siguiente."""
    # Paciente1 y Paciente3 tienen insumo; Paciente2 no.
    (tmp_path / "ficha_Paciente1_15-09-2026.md").write_text("a", encoding="utf-8")
    (tmp_path / "ficha_Paciente3_15-09-2026.md").write_text("b", encoding="utf-8")
    pacientes = [
        PacienteObjetivo(
            fecha="15-09-2026",
            nombre="Paciente1",
            tipo_atencion="",
        ),
        PacienteObjetivo(
            fecha="15-09-2026",
            nombre="Paciente2",
            tipo_atencion="",  # sin insumo -> skip
        ),
        PacienteObjetivo(
            fecha="15-09-2026",
            nombre="Paciente3",
            tipo_atencion="",
        ),
    ]
    fake_driver = MagicMock()

    # El primero abre y pega OK; el segundo skip por sin insumo;
    # el tercero abre y pega OK.
    def fake_abrir(driver, log, p):
        p.panel_cargo = True
        return True

    with patch(
        "src.tools.cargar_ficha.abrir_ficha_por_nombre",
        side_effect=fake_abrir,
    ), patch(
        "src.tools.cargar_ficha.pegar_en_editor",
        return_value=cargar_ficha.pegador_fake_ok(1),
    ):
        resultados = cargar_ficha.iterar_pacientes(
            fake_driver, logger, pacientes, fichas_dir=tmp_path
        )

    assert len(resultados) == 3
    estados = [r.estado for r in resultados]
    assert estados == ["ok", "skip", "ok"]


# ---------------------------------------------------------------------------
# Trazabilidad
# ---------------------------------------------------------------------------


def test_escribir_trazabilidad_json_contiene_resumen(
    tmp_path: Path,
) -> None:
    resultados = [
        cargar_ficha.ResultadoCarga(
            nombre="A", fecha="15-09-2026", estado="ok",
            tipo_editor="textarea", caracteres_pegados=100,
            timestamp="2026-09-21T12:00:00",
        ),
        cargar_ficha.ResultadoCarga(
            nombre="B", fecha="15-09-2026", estado="skip",
            motivo="sin insumo", timestamp="2026-09-21T12:00:01",
        ),
    ]
    out = cargar_ficha._escribir_trazabilidad(
        resultados,
        modo="todos",
        args_extras={"user": "yadira"},
        out_dir=tmp_path,
    )
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["modo"] == "todos"
    assert payload["resumen"]["total"] == 2
    assert payload["resumen"]["ok"] == 1
    assert payload["resumen"]["skip"] == 1
    assert payload["resumen"]["pendiente_selector"] == 0


# ---------------------------------------------------------------------------
# CLI argparse
# ---------------------------------------------------------------------------


def test_main_rechaza_modo_individual_sin_argumentos(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sin --paciente/--fecha ni --todos -> argparse error."""
    with pytest.raises(SystemExit):
        cargar_ficha.main()


def test_main_rechaza_informe_anual_con_todos(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """REFUSADO: informe _completo no se puede usar con --todos."""
    fake_args = ["--todos", "--informe", "informe_fichas_abiertas_2026_completo.txt"]
    with (
        patch("sys.argv", ["cargar_ficha"] + fake_args),
        pytest.raises(SystemExit),
    ):
        cargar_ficha.main()


def test_main_ejecuta_login_y_delega_a_iterar(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Happy path: 1 paciente, archivo existe, login OK, iterar OK."""
    fake_driver = MagicMock()
    creds = {"location": "x", "username": "u", "password": "p"}
    informe = tmp_path / "informe.txt"
    informe.write_text("", encoding="utf-8")
    fichas_dir = tmp_path / "fichas"
    fichas_dir.mkdir()
    (fichas_dir / "ficha_Fulana_15-09-2026.md").write_text("a", encoding="utf-8")

    with (
        patch("src.tools.cargar_ficha.load_credentials", return_value=creds),
        patch("src.tools.cargar_ficha.run_login", return_value=fake_driver),
        patch("src.tools.cargar_ficha.safe_quit"),
        patch(
            "src.tools.cargar_ficha.iterar_pacientes",
            return_value=[
                cargar_ficha.ResultadoCarga(
                    nombre="Fulana", fecha="15-09-2026", estado="ok",
                    caracteres_pegados=1, timestamp="2026-09-21T12:00:00",
                ),
            ],
        ) as mock_iter,
        patch("src.tools.cargar_ficha._informe_mes_actual_path", return_value=informe),
        patch.object(cargar_ficha, "TRAZABILIDAD_CARGA_DIR", tmp_path / "traz"),
        patch(
            "sys.argv",
            [
                "cargar_ficha",
                "--paciente",
                "Fulana",
                "--fecha",
                "15-09-2026",
                "--fichas-dir",
                str(fichas_dir),
                "--log-level",
                "WARNING",
            ],
        ),
    ):
        rc = cargar_ficha.main()

    assert rc == 0
    mock_iter.assert_called_once()
