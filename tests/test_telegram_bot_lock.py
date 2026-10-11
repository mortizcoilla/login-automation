"""Tests REQ-094: candado single-instance del bot de Telegram.

Cubren:
- Lock fresco (no existe) -> se adquiere.
- Lock con PID de OTRO proceso VIVO -> NO se adquiere (dup real).
- Lock con PID muerto (crash sin limpiar) -> se recupera y se adquiere.
- Lock corrupto (basura) -> se recupera y se adquiere.
- Lock con el PROPIO pid (re-entrada tras fork raro) -> se adquiere.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from src.telegram_bot.app import _adquirir_lock, _pid_vivo


def test_lock_fresco_se_adquiere(tmp_path: Path) -> None:
    lock = tmp_path / "telegram_bot.lock"
    assert _adquirir_lock(lock) is True
    assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())


def test_lock_con_otro_proceso_vivo_no_se_adquiere(tmp_path: Path) -> None:
    lock = tmp_path / "telegram_bot.lock"
    hijo = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"]
    )
    try:
        # esperar a que el proceso exista de verdad
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not _pid_vivo(hijo.pid):
            time.sleep(0.1)
        assert _pid_vivo(hijo.pid) is True  # precondicion del test
        lock.write_text(str(hijo.pid), encoding="utf-8")
        assert _adquirir_lock(lock) is False
        assert lock.read_text(encoding="utf-8").strip() == str(hijo.pid)
    finally:
        hijo.terminate()
        hijo.wait(timeout=10)


def test_lock_con_pid_muerto_se_recupera(tmp_path: Path) -> None:
    lock = tmp_path / "telegram_bot.lock"
    lock.write_text("999999999", encoding="utf-8")  # PID inexistente
    assert _adquirir_lock(lock) is True


def test_pid_vivo_pid_propio_es_true() -> None:
    assert _pid_vivo(os.getpid()) is True


def test_pid_vivo_proceso_terminado_es_false() -> None:
    """Regresion 2026-10-11: un proceso TERMINADO cuyo objeto sigue
    referenciado (Popen retiene el handle, igual que el Task
    Scheduler) se abre con OpenProcess y el _pid_vivo viejo lo daba
    por vivo -> el bot no recuperaba el lock y quedaba muerto tras
    reiniciar la tarea. El codigo de salida (no STILL_ACTIVE) lo
    delata como muerto."""
    hijo = subprocess.Popen([sys.executable, "-c", "pass"])
    hijo.wait(timeout=30)
    assert hijo.poll() is not None  # terminado de verdad
    assert _pid_vivo(hijo.pid) is False


def test_lock_corrupto_se_recupera(tmp_path: Path) -> None:
    lock = tmp_path / "telegram_bot.lock"
    lock.write_text("no-es-un-pid", encoding="utf-8")
    assert _adquirir_lock(lock) is True


def test_lock_con_propio_pid_se_adquiere(tmp_path: Path) -> None:
    lock = tmp_path / "telegram_bot.lock"
    lock.write_text(str(os.getpid()), encoding="utf-8")
    assert _adquirir_lock(lock) is True
