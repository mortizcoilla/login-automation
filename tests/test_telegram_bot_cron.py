"""Tests de Go/Kill/Status: control del cron desde el bot (REQ-105).

El servicio se prueba contra candados y procesos REALES (temporales):
lock huerfano, kill de un proceso vivo, log sintetico. La suite NUNCA
toca el scheduler.lock de produccion (todo va monkeypatcheado a tmp) y
NUNCA lanza la cadena real.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.telegram_bot.handlers import cron as cron_handlers
from src.telegram_bot.services import cron_service


# --- regex de los comandos -------------------------------------------------


class TestCalces:
    def test_go_variantes(self) -> None:
        for t in ("go", "Go", "GO", " go ", "/go", "/ Go", "go."):
            assert cron_handlers.calza_go(t), t

    def test_go_no_calza_con_otra_cosa(self) -> None:
        for t in ("vengo", "google", "go ahora", "", "status", "ya vengo mama"):
            assert not cron_handlers.calza_go(t), t

    def test_kill_variantes(self) -> None:
        for t in ("kill", "Kill", "KILL", " kill ", "/kill", "kill."):
            assert cron_handlers.calza_kill(t), t

    def test_status_variantes(self) -> None:
        for t in ("status", "Status", " STATUS ", " status ", "/status", "status."):
            assert cron_handlers.calza_status(t), t

    def test_status_no_calza_frase(self) -> None:
        assert not cron_handlers.calza_status("cual es el status del pedido")


# --- pid_vivo / estado_cron ------------------------------------------------


def _proceso_dormilon() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _escribir_lock(ruta: Path, pid: int) -> None:
    ruta.write_text(str(pid), encoding="utf-8")


class TestPidVivo:
    def test_pid_de_esta_instancia_esta_vivo(self) -> None:
        assert cron_service.pid_vivo(os.getpid()) is True

    def test_pid_de_proceso_terminado_no_esta_vivo(self) -> None:
        proc = _proceso_dormilon()
        proc.kill()
        proc.wait(timeout=10)
        assert cron_service.pid_vivo(proc.pid) is False


class TestEstadoCron:
    def test_sin_lock_no_corre(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(cron_service, "RUTA_LOCK", tmp_path / "scheduler.lock")
        est = cron_service.estado_cron()
        assert est == {"corriendo": False, "huerfano": False, "pid": None, "paso": None}

    def test_lock_con_pid_vivo_corre(self, tmp_path: Path, monkeypatch) -> None:
        lock = tmp_path / "scheduler.lock"
        _escribir_lock(lock, os.getpid())
        monkeypatch.setattr(cron_service, "RUTA_LOCK", lock)
        est = cron_service.estado_cron()
        assert est["corriendo"] is True
        assert est["pid"] == os.getpid()

    def test_lock_huerfano_pid_muerto(self, tmp_path: Path, monkeypatch) -> None:
        proc = _proceso_dormilon()
        proc.kill()
        proc.wait(timeout=10)
        lock = tmp_path / "scheduler.lock"
        _escribir_lock(lock, proc.pid)
        monkeypatch.setattr(cron_service, "RUTA_LOCK", lock)
        est = cron_service.estado_cron()
        assert est["corriendo"] is False
        assert est["huerfano"] is True
        assert est["pid"] == proc.pid

    def test_lock_corrupto_es_huerfano(self, tmp_path: Path, monkeypatch) -> None:
        lock = tmp_path / "scheduler.lock"
        lock.write_text("no-soy-un-pid", encoding="utf-8")
        monkeypatch.setattr(cron_service, "RUTA_LOCK", lock)
        est = cron_service.estado_cron()
        assert est["corriendo"] is False
        assert est["huerfano"] is True


# --- lectura del log --------------------------------------------------------


def _log_temporal(tmp_path: Path, lineas: list[str]) -> Path:
    log = tmp_path / "scheduler.log"
    log.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return log


class TestPasoEnCurso:
    def test_ultimo_paso_de_la_corrida(self, tmp_path: Path) -> None:
        log = _log_temporal(
            tmp_path,
            [
                f"{datetime.now():%Y-%m-%d %H:%M:%S} [yadira] inicio de cadena (4->5->3->6->2b->7->8)",
                f"{datetime.now():%Y-%m-%d %H:%M:%S} [yadira] paso 1/7: -m src.analysis.actualizar_mes_actual yadira",
                f"{datetime.now():%Y-%m-%d %H:%M:%S} [yadira] paso 2/7: -m src.analysis.informe_fichas_abiertas",
            ],
        )
        paso = cron_service.paso_en_curso(time.time() - 60, log=log)
        assert paso is not None
        assert "paso 2/7" in paso

    def test_paso_de_corrida_anterior_no_cuenta(self, tmp_path: Path) -> None:
        log = _log_temporal(
            tmp_path,
            [
                "2020-01-01 08:00:00 [yadira] paso 3/7: -m src.tools.crear_notas_clinicas",
            ],
        )
        assert cron_service.paso_en_curso(time.time(), log=log) is None


class TestUltimaActividad:
    def test_ultima_linea_relevante(self, tmp_path: Path) -> None:
        log = _log_temporal(
            tmp_path,
            [
                "2020-01-01 08:00:00 check: nada vencido.",
                f"{datetime.now():%Y-%m-%d %H:%M:%S} [yadira] cadena completa OK",
                f"{datetime.now():%Y-%m-%d %H:%M:%S} ruido que no calza",
            ],
        )
        actividad = cron_service.ultima_actividad(log=log)
        assert actividad is not None
        assert "cadena completa OK" in actividad


# --- arrancar / matar -------------------------------------------------------


class TestArrancarCron:
    def test_no_lanza_doble_si_ya_corre(self, tmp_path: Path, monkeypatch) -> None:
        lock = tmp_path / "scheduler.lock"
        _escribir_lock(lock, os.getpid())
        monkeypatch.setattr(cron_service, "RUTA_LOCK", lock)
        fake_popen = MagicMock()
        monkeypatch.setattr(cron_service.subprocess, "Popen", fake_popen)
        ok, detalle = cron_service.arrancar_cron()
        assert ok is False
        assert "ya corre" in detalle
        fake_popen.assert_not_called()

    def test_lanza_runner_forzar_yadira_desprendido(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        lock = tmp_path / "scheduler.lock"
        monkeypatch.setattr(cron_service, "RUTA_LOCK", lock)
        monkeypatch.setattr(cron_service, "LOG_SCHEDULER", tmp_path / "sin.log")

        def fake_popen(cmd, **kwargs):
            # Simula al runner: toma el candado con su PID (vivo).
            _escribir_lock(lock, os.getpid())
            assert "--forzar" in cmd and "yadira" in cmd
            assert "-m" in cmd and "src.scheduler.runner" in cmd
            assert kwargs.get("creationflags"), "debe ir desprendido"
            proc = MagicMock()
            proc.pid = os.getpid()
            proc.poll = lambda: None
            return proc

        monkeypatch.setattr(cron_service.subprocess, "Popen", fake_popen)
        ok, detalle = cron_service.arrancar_cron()
        assert ok is True
        assert "corriendo" in detalle

    def test_proceso_que_sale_de_inmediato_reporta_log(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(cron_service, "RUTA_LOCK", tmp_path / "scheduler.lock")
        proc = MagicMock()
        proc.poll = lambda: 2
        proc.returncode = 2
        monkeypatch.setattr(
            cron_service.subprocess, "Popen", lambda cmd, **kw: proc
        )
        ok, detalle = cron_service.arrancar_cron()
        assert ok is False
        assert "salio de inmediato" in detalle


class TestMatarCron:
    def test_sin_lock_no_hay_nada_que_matar(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(cron_service, "RUTA_LOCK", tmp_path / "scheduler.lock")
        ok, detalle = cron_service.matar_cron()
        assert ok is False
        assert "no corre" in detalle

    def test_lock_huerfano_se_limpia(self, tmp_path: Path, monkeypatch) -> None:
        proc = _proceso_dormilon()
        proc.kill()
        proc.wait(timeout=10)
        lock = tmp_path / "scheduler.lock"
        _escribir_lock(lock, proc.pid)
        monkeypatch.setattr(cron_service, "RUTA_LOCK", lock)
        ok, detalle = cron_service.matar_cron()
        assert ok is True
        assert "huerfano" in detalle
        assert not lock.exists()

    def test_mata_el_proceso_vivo_y_limpia_el_candado(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        proc = _proceso_dormilon()
        lock = tmp_path / "scheduler.lock"
        _escribir_lock(lock, proc.pid)
        monkeypatch.setattr(cron_service, "RUTA_LOCK", lock)
        try:
            ok, detalle = cron_service.matar_cron()
            assert ok is True, detalle
            assert "detenido" in detalle
            assert proc.poll() is not None, "el proceso debe quedar muerto"
            assert not lock.exists(), "el candado debe quedar limpio"
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)


# --- texto de Status --------------------------------------------------------


class TestTextoStatus:
    def test_corriendo_muestra_pid_y_paso(self, tmp_path: Path, monkeypatch) -> None:
        lock = tmp_path / "scheduler.lock"
        _escribir_lock(lock, os.getpid())
        monkeypatch.setattr(cron_service, "RUTA_LOCK", lock)
        monkeypatch.setattr(
            cron_service,
            "paso_en_curso",
            lambda mtime, log=None: "[yadira] paso 3/7: -m src.tools.crear_notas_clinicas",
        )
        texto = cron_service.texto_status()
        assert "ESTA corriendo" in texto
        assert "paso 3/7" in texto
        assert "Kill" in texto

    def test_no_corriendo_muestra_ultima_actividad_y_go(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(cron_service, "RUTA_LOCK", tmp_path / "scheduler.lock")
        monkeypatch.setattr(
            cron_service,
            "ultima_actividad",
            lambda log=None: "2026-10-30 20:05:14 [yadira] FALLO en paso 7/7 (codigo 1).",
        )
        texto = cron_service.texto_status()
        assert "NO esta corriendo" in texto
        assert "FALLO en paso 7/7" in texto
        assert "Go" in texto


# --- handlers ---------------------------------------------------------------


def _make_update() -> MagicMock:
    message = MagicMock()
    message.reply_text = AsyncMock()
    update = MagicMock()
    update.effective_message = message
    user = MagicMock()
    user.id = 123456
    update.effective_user = user
    return update


class TestHandlers:
    def test_go_ok_responde_que_arranco(self, monkeypatch) -> None:
        monkeypatch.setattr(
            cron_service, "arrancar_cron", lambda: (True, "corriendo (PID 42)")
        )
        update = _make_update()
        asyncio.run(cron_handlers.cmd_go(update, MagicMock()))
        reply = update.effective_message.reply_text.await_args.args[0]
        assert "arranco el flujo" in reply
        assert "Status" in reply

    def test_go_cuando_ya_corre_no_arranca_otro(self, monkeypatch) -> None:
        monkeypatch.setattr(
            cron_service, "arrancar_cron", lambda: (False, "ya corre (PID 42)")
        )
        update = _make_update()
        asyncio.run(cron_handlers.cmd_go(update, MagicMock()))
        reply = update.effective_message.reply_text.await_args.args[0]
        assert "ya esta corriendo" in reply

    def test_kill_ok_confirma(self, monkeypatch) -> None:
        monkeypatch.setattr(
            cron_service, "matar_cron", lambda: (True, "flujo detenido (PID 42)")
        )
        update = _make_update()
        asyncio.run(cron_handlers.cmd_kill(update, MagicMock()))
        replies = [c.args[0] for c in update.effective_message.reply_text.await_args_list]
        assert any("detenido" in r for r in replies)

    def test_kill_sin_flujo_lo_dice(self, monkeypatch) -> None:
        monkeypatch.setattr(
            cron_service, "matar_cron", lambda: (False, "no corre")
        )
        update = _make_update()
        asyncio.run(cron_handlers.cmd_kill(update, MagicMock()))
        replies = [c.args[0] for c in update.effective_message.reply_text.await_args_list]
        assert any("no corre" in r or "No pude detenerlo" in r for r in replies)

    def test_status_responde_el_reporte(self, monkeypatch) -> None:
        monkeypatch.setattr(
            cron_service, "texto_status", lambda: "El flujo diario NO esta corriendo."
        )
        update = _make_update()
        asyncio.run(cron_handlers.cmd_status(update, MagicMock()))
        reply = update.effective_message.reply_text.await_args.args[0]
        assert "NO esta corriendo" in reply

    def test_sin_message_no_falla(self) -> None:
        update = MagicMock()
        update.effective_message = None
        update.effective_user = None
        asyncio.run(cron_handlers.cmd_status(update, MagicMock()))
        asyncio.run(cron_handlers.cmd_go(update, MagicMock()))
        asyncio.run(cron_handlers.cmd_kill(update, MagicMock()))
