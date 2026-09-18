"""Tests para la lectura de HEADLESS como env var.

Cubre:
- Helper `_env_bool` acepta los valores canonicos y rechaza los demas.
- `_resolve_headless` aplica HEADLESS_DEFAULT cuando el caller pasa None,
  y respeta el bool explicito cuando lo pasa.
- `HEADLESS_DEFAULT` se carga al importar el modulo (testea reimport).
- `login_rayen` delega a `run_login` sin el kwarg `headless` cuando el
  caller no lo pasa (para que la env se aplique mas abajo).
"""

from __future__ import annotations

import importlib
import logging
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("test_headless")


# ---------------------------------------------------------------------------
# _env_bool: pure function, no selenium
# ---------------------------------------------------------------------------
class TestEnvBool:
    def test_true_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.browser_automation import _env_bool

        for val in ("1", "true", "True", "TRUE", "yes", "YES", "on", "On"):
            monkeypatch.setenv("__TEST_BOOL__", val)
            assert _env_bool("__TEST_BOOL__", default=False) is True, val

    def test_false_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.browser_automation import _env_bool

        for val in ("0", "false", "no", "off", "", "anything", " "):
            monkeypatch.setenv("__TEST_BOOL__", val)
            assert _env_bool("__TEST_BOOL__", default=True) is False, val

    def test_unset_returns_default_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.browser_automation import _env_bool

        monkeypatch.delenv("__TEST_BOOL__", raising=False)
        assert _env_bool("__TEST_BOOL__", default=True) is True

    def test_unset_returns_default_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.browser_automation import _env_bool

        monkeypatch.delenv("__TEST_BOOL__", raising=False)
        assert _env_bool("__TEST_BOOL__", default=False) is False

    def test_whitespace_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.browser_automation import _env_bool

        monkeypatch.setenv("__TEST_BOOL__", "  true  ")
        assert _env_bool("__TEST_BOOL__", default=False) is True


# ---------------------------------------------------------------------------
# HEADLESS_DEFAULT: module-level constant (reimport para recalcular)
# ---------------------------------------------------------------------------
def _reload_browser_automation() -> None:
    """Reimportar `src.browser_automation` para que HEADLESS_DEFAULT se
    recalcule desde la env var actual."""
    import src.browser_automation as ba

    importlib.reload(ba)


class TestHeadlessDefault:
    def test_unset_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HEADLESS", raising=False)
        _reload_browser_automation()
        from src.browser_automation import HEADLESS_DEFAULT

        assert HEADLESS_DEFAULT is False

    def test_set_true_is_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEADLESS", "true")
        _reload_browser_automation()
        from src.browser_automation import HEADLESS_DEFAULT

        assert HEADLESS_DEFAULT is True

    def test_set_one_is_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEADLESS", "1")
        _reload_browser_automation()
        from src.browser_automation import HEADLESS_DEFAULT

        assert HEADLESS_DEFAULT is True

    def test_set_yes_is_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEADLESS", "yes")
        _reload_browser_automation()
        from src.browser_automation import HEADLESS_DEFAULT

        assert HEADLESS_DEFAULT is True

    def test_set_explicit_false_stays_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEADLESS", "false")
        _reload_browser_automation()
        from src.browser_automation import HEADLESS_DEFAULT

        assert HEADLESS_DEFAULT is False

    def test_set_garbage_stays_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEADLESS", "no se que")
        _reload_browser_automation()
        from src.browser_automation import HEADLESS_DEFAULT

        assert HEADLESS_DEFAULT is False


# ---------------------------------------------------------------------------
# _resolve_headless: pure function, NO selenium
# ---------------------------------------------------------------------------
class TestResolveHeadless:
    def test_none_uses_default_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HEADLESS", raising=False)
        _reload_browser_automation()
        from src.browser_automation import _resolve_headless

        assert _resolve_headless(None) is False

    def test_none_uses_default_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEADLESS", "true")
        _reload_browser_automation()
        from src.browser_automation import _resolve_headless

        assert _resolve_headless(None) is True

    def test_explicit_true_overrides_env_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEADLESS", "false")
        _reload_browser_automation()
        from src.browser_automation import _resolve_headless

        # Caller fuerza True aunque HEADLESS=false
        assert _resolve_headless(True) is True

    def test_explicit_false_overrides_env_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEADLESS", "true")
        _reload_browser_automation()
        from src.browser_automation import _resolve_headless

        # Caller fuerza False aunque HEADLESS=true
        assert _resolve_headless(False) is False


# ---------------------------------------------------------------------------
# login_rayen: verificar que delega correctamente
# ---------------------------------------------------------------------------
class TestLoginRayenHeadless:
    def test_login_rayen_sin_headless_delega_sin_kwarg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """login_rayen() sin kwarg headless debe llamar run_login sin el
        kwarg headless (osea, run_login aplicara la env var HEADLESS)."""
        monkeypatch.delenv("HEADLESS", raising=False)
        fake_driver = MagicMock()
        with patch("src.pancho_skills.login.run_login", return_value=fake_driver) as mock_run:
            from src.pancho_skills.login import login_rayen

            login_rayen(
                {"location": "x", "username": "y", "password": "z"},
                logging.getLogger("t"),
            )
        # run_login debe recibir headless=None (o no recibirlo, que es lo mismo)
        _, kwargs = mock_run.call_args
        assert kwargs.get("headless") is None

    def test_login_rayen_con_headless_true_delega_true(self) -> None:
        """login_rayen(headless=True) debe propagar True a run_login."""
        fake_driver = MagicMock()
        with patch("src.pancho_skills.login.run_login", return_value=fake_driver) as mock_run:
            from src.pancho_skills.login import login_rayen

            login_rayen(
                {"location": "x", "username": "y", "password": "z"},
                logging.getLogger("t"),
                headless=True,
            )
        _, kwargs = mock_run.call_args
        assert kwargs.get("headless") is True

    def test_login_rayen_con_headless_false_delega_false(self) -> None:
        fake_driver = MagicMock()
        with patch("src.pancho_skills.login.run_login", return_value=fake_driver) as mock_run:
            from src.pancho_skills.login import login_rayen

            login_rayen(
                {"location": "x", "username": "y", "password": "z"},
                logging.getLogger("t"),
                headless=False,
            )
        _, kwargs = mock_run.call_args
        assert kwargs.get("headless") is False
