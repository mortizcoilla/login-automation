"""Tests para src.telegram_bot.config.BotConfig.from_env().

Cada test fija todas las env vars relevantes (incluyendo 'no definida' via
delenv) para no depender del .env real ni de otras variables del entorno.

`_disable_dotenv` evita que load_dotenv() del codigo lea .env real.
"""

from __future__ import annotations

import dataclasses

import pytest

from src.telegram_bot.config import BotConfig, ConfigurationError


@pytest.fixture(autouse=True)
def _disable_dotenv(monkeypatch):
    """No leer .env real durante estos tests.

    Ademas de neutralizar load_dotenv, borra TELEGRAM_* ya presentes en
    os.environ: otros modulos del proyecto (credentials, core.rutas)
    hacen load_dotenv al importarse y dejan las vars del .env real en el
    proceso, lo que contaminaria estos tests.
    """
    monkeypatch.setattr("src.telegram_bot.config.load_dotenv", lambda: None)
    for var in list(__import__("os").environ):
        if var.startswith("TELEGRAM_"):
            monkeypatch.delenv(var, raising=False)


def _set_minimo(monkeypatch):
    """Helper: setea token + 1 user_id, lo minimo para que from_env funcione."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_RUBICITA", "test_token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "12345")


# --- happy path -----------------------------------------------------------


def test_minimo_valido(monkeypatch):
    _set_minimo(monkeypatch)
    cfg = BotConfig.from_env()
    assert cfg.token == "test_token"
    assert cfg.allowed_user_ids == frozenset({12345})
    assert cfg.polling_interval == 1.0
    assert cfg.log_level == "INFO"
    assert cfg.notas_dir_path is None
    assert cfg.destino_dir_path is None


def test_multiples_usuarios_con_espacios_y_comas(monkeypatch):
    _set_minimo(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "1, 2 ,3,, ,4")
    cfg = BotConfig.from_env()
    assert cfg.allowed_user_ids == frozenset({1, 2, 3, 4})


def test_polling_interval_custom(monkeypatch):
    _set_minimo(monkeypatch)
    monkeypatch.setenv("TELEGRAM_POLLING_INTERVAL", "0.5")
    cfg = BotConfig.from_env()
    assert cfg.polling_interval == 0.5


def test_log_level_normalizado_a_uppercase(monkeypatch):
    _set_minimo(monkeypatch)
    monkeypatch.setenv("TELEGRAM_LOG_LEVEL", "debug")
    cfg = BotConfig.from_env()
    assert cfg.log_level == "DEBUG"


def test_overrides_paths(monkeypatch):
    _set_minimo(monkeypatch)
    monkeypatch.setenv("TELEGRAM_NOTAS_DIR", "/tmp/notas_test")
    monkeypatch.setenv("TELEGRAM_DESTINO_DIR", "/tmp/destino_test")
    cfg = BotConfig.from_env()
    assert cfg.notas_dir_path == "/tmp/notas_test"
    assert cfg.destino_dir_path == "/tmp/destino_test"


def test_overrides_paths_vacios_normalizados_a_none(monkeypatch):
    _set_minimo(monkeypatch)
    monkeypatch.setenv("TELEGRAM_NOTAS_DIR", "  ")
    monkeypatch.setenv("TELEGRAM_DESTINO_DIR", "")
    cfg = BotConfig.from_env()
    assert cfg.notas_dir_path is None
    assert cfg.destino_dir_path is None


# --- errores -------------------------------------------------------------


def test_falta_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN_RUBICITA", raising=False)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "1")
    with pytest.raises(ConfigurationError, match="TELEGRAM_BOT_TOKEN_RUBICITA"):
        BotConfig.from_env()


def test_token_vacio_o_whitespace(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_RUBICITA", "   ")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "1")
    with pytest.raises(ConfigurationError):
        BotConfig.from_env()


def test_falta_user_ids(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_RUBICITA", "x")
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    with pytest.raises(ConfigurationError, match="TELEGRAM_ALLOWED_USER_IDS"):
        BotConfig.from_env()


def test_user_ids_no_es_numero(monkeypatch):
    _set_minimo(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "abc,123")
    with pytest.raises(ConfigurationError, match="enteros"):
        BotConfig.from_env()


def test_user_ids_solo_separadores(monkeypatch):
    _set_minimo(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", ", ,, ,")
    with pytest.raises(ConfigurationError, match="validos"):
        BotConfig.from_env()


def test_polling_interval_cero_o_negativo(monkeypatch):
    _set_minimo(monkeypatch)
    monkeypatch.setenv("TELEGRAM_POLLING_INTERVAL", "0")
    with pytest.raises(ConfigurationError, match=r"polling_interval|> 0|mayor"):
        BotConfig.from_env()


def test_polling_interval_negativo(monkeypatch):
    _set_minimo(monkeypatch)
    monkeypatch.setenv("TELEGRAM_POLLING_INTERVAL", "-1.5")
    with pytest.raises(ConfigurationError):
        BotConfig.from_env()


def test_polling_interval_no_float(monkeypatch):
    _set_minimo(monkeypatch)
    monkeypatch.setenv("TELEGRAM_POLLING_INTERVAL", "abc")
    with pytest.raises(ConfigurationError):
        BotConfig.from_env()


def test_log_level_invalido(monkeypatch):
    _set_minimo(monkeypatch)
    monkeypatch.setenv("TELEGRAM_LOG_LEVEL", "VERBOSE")
    with pytest.raises(ConfigurationError, match="LOG_LEVEL"):
        BotConfig.from_env()


# --- inmutabilidad -------------------------------------------------------


def test_botconfig_es_inmutable():
    """frozen=True del dataclass: no se puede mutar despues de construir."""
    cfg = BotConfig(
        token="x",
        allowed_user_ids=frozenset({1}),
        polling_interval=1.0,
        log_level="INFO",
        notas_dir_path=None,
        destino_dir_path=None,
    )
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        cfg.token = "otro"  # type: ignore[misc]
