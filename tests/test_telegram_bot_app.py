"""Tests para src.telegram_bot.app (builder).

PTS Application no expone sus parametros como atributos publicos del
resultado, asi que testeamos el lado del codigo: verificamos que la cadena
de metodos del builder invocada por ``build_application`` incluye lo
esperado (.token, .build) y que el BotConfig se guarda en bot_data.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.telegram_bot.app import build_application
from src.telegram_bot.config import BotConfig


def _make_config() -> BotConfig:
    return BotConfig(
        token="test_token",
        allowed_user_ids=frozenset({1}),
        polling_interval=1.0,
        log_level="INFO",
        notas_dir_path=None,
        destino_dir_path=None,
    )


def test_build_application_pasa_token_al_builder():
    """El builder de PTB debe recibir .token(config.token) y luego .build()."""
    builder = MagicMock()
    final_app = MagicMock()
    final_app.bot_data = {}

    # El builder de PTB es encadenable: token().read_timeout().connect_timeout().build()
    builder.token.return_value = builder
    builder.read_timeout.return_value = builder
    builder.connect_timeout.return_value = builder
    builder.build.return_value = final_app

    from src.telegram_bot import app as app_module

    original = app_module.Application
    try:
        fake_application_cls = MagicMock()
        fake_application_cls.builder.return_value = builder
        app_module.Application = fake_application_cls  # type: ignore[assignment]

        config = _make_config()
        result = build_application(config)
    finally:
        app_module.Application = original  # type: ignore[assignment]

    fake_application_cls.builder.assert_called_once()
    builder.token.assert_called_once_with("test_token")
    builder.build.assert_called_once()
    assert result is final_app


def test_build_application_configura_timeouts_robustos():
    """El bot configura read_timeout y connect_timeout > 5s.

    PTB defaults son 5s; en redes lentas (caso del operador) el bootstrap
    muere en getMe(). Hard-rule del proyecto: el bot debe tolerar al menos
    30s antes de abortar la conexion inicial.
    """
    builder = MagicMock()
    final_app = MagicMock()
    final_app.bot_data = {}

    builder.token.return_value = builder
    builder.read_timeout.return_value = builder
    builder.connect_timeout.return_value = builder
    builder.build.return_value = final_app

    from src.telegram_bot import app as app_module

    original = app_module.Application
    try:
        fake_application_cls = MagicMock()
        fake_application_cls.builder.return_value = builder
        app_module.Application = fake_application_cls  # type: ignore[assignment]

        build_application(_make_config())
    finally:
        app_module.Application = original  # type: ignore[assignment]

    builder.read_timeout.assert_called_once()
    read_t = builder.read_timeout.call_args.args[0]
    assert read_t >= 30.0, f"read_timeout debe ser >= 30s, fue {read_t}"

    builder.connect_timeout.assert_called_once()
    conn_t = builder.connect_timeout.call_args.args[0]
    assert conn_t >= 30.0, f"connect_timeout debe ser >= 30s, fue {conn_t}"


def test_build_application_almacena_config_en_bot_data():
    """El BotConfig queda en application.bot_data para que los handlers
    lo lean (ruta del dir de notas y destino)."""
    builder = MagicMock()
    final_app = MagicMock()
    final_app.bot_data = {}

    builder.token.return_value = builder
    builder.read_timeout.return_value = builder
    builder.connect_timeout.return_value = builder
    builder.build.return_value = final_app

    from src.telegram_bot import app as app_module

    original = app_module.Application
    try:
        fake_application_cls = MagicMock()
        fake_application_cls.builder.return_value = builder
        app_module.Application = fake_application_cls  # type: ignore[assignment]

        config = _make_config()
        build_application(config)
    finally:
        app_module.Application = original  # type: ignore[assignment]

    assert final_app.bot_data["config"] is config
