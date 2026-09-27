"""Tests para src.telegram_bot.middleware.auth.authorized_only.

No requieren pytest-asyncio: usamos asyncio.run() directamente.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.telegram_bot.middleware.auth import authorized_only


def _update_con_user(user_id: int, username: str = "yadira") -> MagicMock:
    update = MagicMock()
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.first_name = "Test"
    update.effective_user = user

    msg = MagicMock()
    msg.reply_text = AsyncMock()
    update.effective_message = msg
    return update


def _update_sin_user() -> MagicMock:
    update = MagicMock()
    update.effective_user = None
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    update.effective_message = msg
    return update


# --- happy paths --------------------------------------------------------


def test_deja_pasar_usuario_autorizado():
    """user.id esta en allowed_ids -> handler se invoca una vez."""
    inner = AsyncMock()
    wrapped = authorized_only(frozenset({123}))(inner)

    update = _update_con_user(user_id=123)
    context = MagicMock()

    asyncio.run(wrapped(update, context))

    inner.assert_awaited_once_with(update, context)


def test_pasa_argumentos_correctos():
    """El handler se llama con el (update, context) que llegaron."""
    inner = AsyncMock()
    wrapped = authorized_only(frozenset({42}))(inner)

    update = _update_con_user(user_id=42)
    context = MagicMock()
    context.something = "specific"

    asyncio.run(wrapped(update, context))

    args, _ = inner.call_args
    assert args[0] is update
    assert args[1] is context


# --- rechazos -----------------------------------------------------------


def test_rechaza_usuario_no_autorizado():
    """user.id NO esta en allowed_ids -> handler NO se invoca."""
    inner = AsyncMock()
    wrapped = authorized_only(frozenset({123}))(inner)

    update = _update_con_user(user_id=999)
    context = MagicMock()

    asyncio.run(wrapped(update, context))

    inner.assert_not_awaited()


def test_drop_silencioso_sin_user():
    """Sin effective_user (canal raro) -> drop silencioso."""
    inner = AsyncMock()
    wrapped = authorized_only(frozenset({123}))(inner)

    update = _update_sin_user()
    context = MagicMock()

    asyncio.run(wrapped(update, context))

    inner.assert_not_awaited()


def test_rechazado_no_recibe_respuesta():
    """Por seguridad, NO respondemos a usuarios no autorizados
    (evita info leak sobre la existencia del bot)."""
    inner = AsyncMock()
    wrapped = authorized_only(frozenset({123}))(inner)

    update = _update_con_user(user_id=999)
    context = MagicMock()

    asyncio.run(wrapped(update, context))

    update.effective_message.reply_text.assert_not_awaited()


# --- contrato del decorador ---------------------------------------------


def test_decorator_factory_devuelve_decorador():
    allowed = frozenset({1})
    decorator = authorized_only(allowed)
    assert callable(decorator)


def test_decorador_envuelve_handler():
    async def handler(u, c):
        return None

    wrapped = authorized_only(frozenset({1}))(handler)
    assert callable(wrapped)


def test_multiples_usuarios_permitidos():
    """Cualquiera de los IDs en el frozenset esta autorizado."""
    inner = AsyncMock()
    wrapped = authorized_only(frozenset({100, 200, 300}))(inner)

    for uid in (100, 200, 300):
        inner.reset_mock()
        update = _update_con_user(user_id=uid)
        context = MagicMock()
        asyncio.run(wrapped(update, context))
        inner.assert_awaited_once_with(update, context)
