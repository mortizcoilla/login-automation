"""Tests del scheduler (REQ-060): calendario, vencimientos y runner.

Sin red, sin Rayen, sin tarea de Windows: solo logica pura y
monkeypatch de subprocess/paths.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.scheduler import runner
from src.scheduler.calendario import Calendario, CalendarioError, cargar_calendario, vencidas

# Lunes 2026-09-21, miercoles 2026-09-23, sabado 2026-09-26.
_LUN_1731 = datetime(2026, 9, 21, 17, 31)
_LUN_1729 = datetime(2026, 9, 21, 17, 29)
_MIE_2031 = datetime(2026, 9, 23, 20, 31)
_MIE_1800 = datetime(2026, 9, 23, 18, 0)
_SAB = datetime(2026, 9, 26, 12, 0)


# --- carga del calendario -----------------------------------------------------


def test_calendario_del_repo_tiene_los_5_horarios_de_yadira() -> None:
    cal = cargar_calendario()  # config/calendario.json real del repo
    assert cal.max_intentos_por_dia == 3
    assert {e.usuario for e in cal.entradas} == {"yadira"}
    pares = sorted((e.weekday, e.hora.strftime("%H:%M")) for e in cal.entradas)
    assert pares == [
        (0, "17:30"),  # lunes
        (1, "17:30"),  # martes
        (2, "20:30"),  # miercoles
        (3, "17:30"),  # jueves
        (4, "16:30"),  # viernes
    ]


def _escribir_calendario(tmp_path: Path, data: dict) -> Path:
    ruta = tmp_path / "calendario.json"
    ruta.write_text(json.dumps(data), encoding="utf-8")
    return ruta


def test_dias_con_tilde_se_normalizan(tmp_path: Path) -> None:
    ruta = _escribir_calendario(
        tmp_path,
        {
            "doctores": [
                {
                    "usuario": "otro",
                    "horarios": [
                        {"dia": "Miércoles", "hora": "20:30"},
                        {"dia": "SÁBADO", "hora": "09:00"},
                    ],
                }
            ]
        },
    )
    cal = cargar_calendario(ruta)
    assert {(e.weekday, e.usuario) for e in cal.entradas} == {(2, "otro"), (5, "otro")}


def test_multiples_doctores(tmp_path: Path) -> None:
    ruta = _escribir_calendario(
        tmp_path,
        {
            "doctores": [
                {"usuario": "yadira", "horarios": [{"dia": "lunes", "hora": "17:30"}]},
                {"usuario": "carlos", "horarios": [{"dia": "lunes", "hora": "09:00"}]},
            ]
        },
    )
    cal = cargar_calendario(ruta)
    assert len(cal.entradas) == 2
    # lunes 17:31: vencen ambos (las dos horas ya pasaron).
    assert {e.usuario for e in vencidas(cal, _LUN_1731, {})} == {"yadira", "carlos"}
    # lunes 09:00: solo carlos (el turno de yadira todavia no llega).
    temprano = vencidas(cal, datetime(2026, 9, 21, 9, 0), {})
    assert [e.usuario for e in temprano] == ["carlos"]


@pytest.mark.parametrize(
    "data",
    [
        {"doctores": []},
        {},
        {"doctores": [{"usuario": "", "horarios": [{"dia": "lunes", "hora": "10:00"}]}]},
        {"doctores": [{"usuario": "x", "horarios": []}]},
        {"doctores": [{"usuario": "x", "horarios": [{"dia": "dominguito", "hora": "10:00"}]}]},
        {"doctores": [{"usuario": "x", "horarios": [{"dia": "lunes", "hora": "25:00"}]}]},
        {
            "doctores": [{"usuario": "x", "horarios": [{"dia": "lunes", "hora": "10:00"}]}],
            "max_intentos_por_dia": 0,
        },
    ],
)
def test_calendario_invalido_levanta_error(tmp_path: Path, data: dict) -> None:
    ruta = _escribir_calendario(tmp_path, data)
    with pytest.raises(CalendarioError):
        cargar_calendario(ruta)


def test_calendario_ausente_levanta_error(tmp_path: Path) -> None:
    with pytest.raises(CalendarioError):
        cargar_calendario(tmp_path / "no_existe.json")


# --- vencimientos y estado ----------------------------------------------------


def _cal_yadira() -> Calendario:
    return cargar_calendario()


def test_vencimiento_por_dia_y_hora() -> None:
    cal = _cal_yadira()
    assert [e.dia_nombre for e in vencidas(cal, _LUN_1731, {})] == ["lunes"]
    assert vencidas(cal, _LUN_1729, {}) == []  # aun no son las 17:30
    assert [e.dia_nombre for e in vencidas(cal, _MIE_2031, {})] == ["miercoles"]
    assert vencidas(cal, _MIE_1800, {}) == []  # miercoles 18:00: su hora es 20:30
    assert vencidas(cal, _SAB, {}) == []  # sabado: nadie corre


def test_ya_corrio_ok_hoy_no_revence() -> None:
    cal = _cal_yadira()
    estado = {"yadira": {"fecha_ultimo_intento": "2026-09-21", "fallos_hoy": 0, "ok": True}}
    assert vencidas(cal, _LUN_1731, estado) == []


def test_fallo_hoy_revence_hasta_agotar_intentos() -> None:
    cal = _cal_yadira()
    agotado = {"yadira": {"fecha_ultimo_intento": "2026-09-21", "fallos_hoy": 3, "ok": False}}
    assert vencidas(cal, _LUN_1731, agotado) == []
    con_cupo = {"yadira": {"fecha_ultimo_intento": "2026-09-21", "fallos_hoy": 2, "ok": False}}
    assert [e.usuario for e in vencidas(cal, _LUN_1731, con_cupo)] == ["yadira"]


def test_fallo_ayer_vuelve_a_vencer_hoy() -> None:
    cal = _cal_yadira()
    ayer = {"yadira": {"fecha_ultimo_intento": "2026-09-20", "fallos_hoy": 3, "ok": False}}
    assert [e.usuario for e in vencidas(cal, _LUN_1731, ayer)] == ["yadira"]


# --- runner -------------------------------------------------------------------


@pytest.fixture()
def runner_aislado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Estado/log del runner en tmp; subprocess grabado, siempre OK."""
    monkeypatch.setattr(runner, "ESTADO_PATH", tmp_path / "estado.json")
    monkeypatch.setattr(runner, "LOG_PATH", tmp_path / "logs" / "scheduler.log")
    llamadas: list[list[str]] = []

    class _Ok:
        returncode = 0

    def _fake_run(cmd: list[str], **kwargs: object) -> _Ok:
        llamadas.append(cmd[1:])  # sin el path del interprete
        return _Ok()

    monkeypatch.setattr(runner.subprocess, "run", _fake_run)
    return llamadas


def test_cadena_ok_corre_5_pasos(runner_aislado, tmp_path: Path) -> None:
    assert runner.ejecutar_cadena("yadira") == 0
    assert len(runner_aislado) == 5
    assert runner_aislado[0] == ["-m", "src.analysis.actualizar_mes_actual", "yadira"]
    assert runner_aislado[2][-2:] == ["--user", "yadira"]
    assert runner_aislado[4] == ["-m", "src.tools.mortadelo", "--todos"]


def test_cadena_con_fallo_se_detiene_en_el_primer_paso(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "ESTADO_PATH", tmp_path / "estado.json")
    monkeypatch.setattr(runner, "LOG_PATH", tmp_path / "logs" / "scheduler.log")
    llamadas: list[list[str]] = []

    class _Falla:
        returncode = 2

    def _fake_run_fail(cmd: list[str], **kwargs: object) -> _Falla:
        llamadas.append(cmd[1:])
        return _Falla()

    monkeypatch.setattr(runner.subprocess, "run", _fake_run_fail)
    assert runner.ejecutar_cadena("yadira") != 0
    assert len(llamadas) == 1  # corto en el paso 1, semantica &&


def test_estado_marcar_intento_y_ok(runner_aislado, tmp_path: Path) -> None:
    estado: dict = {}
    runner._marcar_intento("yadira", estado)
    guardado = json.loads((tmp_path / "estado.json").read_text(encoding="utf-8"))
    assert estado == guardado
    assert guardado["yadira"]["fallos_hoy"] == 1
    assert guardado["yadira"]["ok"] is False
    runner._marcar_ok("yadira", estado)
    guardado = json.loads((tmp_path / "estado.json").read_text(encoding="utf-8"))
    assert guardado["yadira"] == {
        "fecha_ultimo_intento": datetime.now().date().isoformat(),
        "fallos_hoy": 0,
        "ok": True,
    }


def test_estado_corrupto_se_trata_como_fresco(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "ESTADO_PATH", tmp_path / "estado.json")
    (tmp_path / "estado.json").write_text("{no es json", encoding="utf-8")
    assert runner._leer_estado() == {}


def test_listar_nada_vencido_en_domingo(
    runner_aislado, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    cal = _escribir_calendario(
        tmp_path,
        {"doctores": [{"usuario": "yadira", "horarios": [{"dia": "domingo", "hora": "10:00"}]}]},
    )
    assert runner.main(["--listar", "--calendario", str(cal)]) == 0
    assert "Nada vencido" in capsys.readouterr().out


def test_forzar_usuario_desconocido_falla_sin_correr(
    runner_aislado, tmp_path: Path
) -> None:
    cal = _escribir_calendario(
        tmp_path,
        {"doctores": [{"usuario": "yadira", "horarios": [{"dia": "lunes", "hora": "17:30"}]}]},
    )
    assert runner.main(["--forzar", "fantasma", "--calendario", str(cal)]) == 2
    assert runner_aislado == []  # no ejecuto nada
