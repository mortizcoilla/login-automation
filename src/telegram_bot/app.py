"""Bot de Telegram Rubicita: entrypoint.

Uso:
    python -m src.telegram_bot.app

Variables de entorno requeridas (en .env):
    TELEGRAM_BOT_TOKEN_RUBICITA   token de @BotFather
    TELEGRAM_ALLOWED_USER_IDS     IDs separados por coma (ej: "123456789,987654321")

Variables opcionales:
    TELEGRAM_POLLING_INTERVAL     segundos entre polls (default 1.0)
    TELEGRAM_LOG_LEVEL            DEBUG|INFO|WARNING|ERROR (default INFO)
    TELEGRAM_NOTAS_DIR            override del dir de notas clinicas (solo tests)
    TELEGRAM_DESTINO_DIR          override del dir destino de examenes (solo tests)

Arquitectura:
    - Polling (no webhook) — el bot vive detras de NAT; no expone HTTPS.
    - Long-running process — correr como servicio Windows (Programador de tareas)
      o con un supervisor ligero (nssm, pm2, TaskScheduler).
    - Handlers: /start, /help (alias), /archivar (mensaje con foto y caption).
    - Auth: whitelist de user IDs (Yadira + operador si hay).

NO pisa modulos existentes. Importa (solo lectura) desde:
    - src.tools.recibir_foto_examen (logica de archivado)
    - src.core.rutas               (paths canonicos — via el tool)
"""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.core.rutas import LOGS_DIR
from src.telegram_bot.config import BotConfig, ConfigurationError
from src.telegram_bot.handlers.debug import register as register_debug_handler
from src.telegram_bot.handlers.photo import cmd_archivar
from src.telegram_bot.handlers.start import cmd_start
from src.telegram_bot.handlers.text import cmd_text_fallback
from src.telegram_bot.middleware.auth import authorized_only

logger = logging.getLogger(__name__)


class _FiltroConflict(logging.Filter):
    """Colapsa la lluvia de tracebacks por instancia duplicada.

    Cuando otra instancia del bot compite por getUpdates, PTB loggea un
    traceback de ~20 lineas POR POLL (1/seg). Este filtro traga esos
    registros y emite UNA linea propia por minuto con el aviso claro.
    """

    _CADA_SEGUNDOS = 60

    def __init__(self) -> None:
        super().__init__()
        self._ultimo_aviso = 0.0

    def filter(self, record: logging.LogRecord) -> bool:
        if "terminated by other getUpdates request" not in record.getMessage():
            return True
        import time

        ahora = time.monotonic()
        if ahora - self._ultimo_aviso >= self._CADA_SEGUNDOS:
            self._ultimo_aviso = ahora
            logger.warning(
                "Otra instancia del bot con el mismo token esta compitiendo "
                "por los updates (repite cada minuto). Revisar otros PCs."
            )
        return False


async def _log_error_ptb(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler de errores PTB: una linea limpia en vez de traceback."""
    logger.error("Error de PTB en update: %s", context.error)


def build_application(config: BotConfig) -> Application:
    """Construye la Application de PTB con handlers + middleware aplicados.

    Handlers registrados:
        - /start y /help -> cmd_start
        - mensaje con caption que matchea ^/archivar y trae foto/doc
          -> cmd_archivar

    Args:
        config: configuracion validada (de BotConfig.from_env()).

    Returns:
        Application lista para .run_polling() o .run_webhook().
    """
    application = (
        Application.builder()
        .token(config.token)
        # Defaults de PTB para read/connect_timeout son 5s, insuficiente
        # cuando el bootstrap hace getMe() y la red del operador es lenta.
        # Subimos a 30s para tolerar un par de paquetes perdidos sin abortar.
        .read_timeout(30.0)
        .connect_timeout(30.0)
        .build()
    )
    application.bot_data["config"] = config

    # Diagnostico: loggea TODO mensaje que llega, antes del grupo 0, sin
    # consumirlo. Si /archivar con foto no llega al handler, esta linea
    # muestra lo que Telegram mando de verdad (caption crudo, user_id).
    register_debug_handler(application)

    auth = authorized_only(config.allowed_user_ids)

    # /start y /help: bienvenida + instrucciones.
    # Errores de handlers/PTB -> una linea limpia en vez de traceback
    # completo en el log (los tracebacks crudos rara vez aportan aqui).
    application.add_error_handler(_log_error_ptb)

    application.add_handler(CommandHandler("start", auth(cmd_start)))
    application.add_handler(CommandHandler("help", auth(cmd_start)))

    # /archivar: solo mensajes con caption /archivar y media (foto o doc).
    # filters.Document.ALL incluye PDFs, imagenes-enviadas-como-archivo, y
    # tambien videos/audios. Filtramos v1 por: PHOTO o IMAGE-doc o PDF.
    media_filter = filters.PHOTO | filters.Document.IMAGE | filters.Document.PDF
    _archivar_pattern = re.compile(r"^\s*/archivar", re.IGNORECASE | re.DOTALL)
    application.add_handler(
        MessageHandler(
            # IGNORECASE: el autofirm del teclado en iOS/Android puede
            # poner mayuscula a la primera letra, produciendo "/Archivar".
            # Sin este flag, el filtro rechaza y el handler no se llama.
            # ^\s*: algunos teclados dejan espacios al inicio del caption.
            filters.CaptionRegex(_archivar_pattern) & media_filter,
            auth(cmd_archivar),
        )
    )

    # Catch-all de texto: cualquier mensaje de texto que no fue capturado
    # por los handlers anteriores cae aca (texto libre, /archivar sin foto,
    # comando desconocido). filters.TEXT & ~filters.COMMAND excluye texto
    # que ya es un comando registrado. Se registra DESPUES del /archivar
    # para que PTB le de prioridad al especializado cuando hay match.
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            auth(cmd_text_fallback),
        )
    )

    return application


def main(argv: list[str] | None = None) -> int:
    """Entry-point: lee config, construye bot, hace polling."""
    try:
        config = BotConfig.from_env()
    except ConfigurationError as exc:
        print(f"[telegram_bot] {exc}", file=sys.stderr)
        return 2

    # Log dual: consola (cuando hay) + archivo rotativo. El archivo es
    # imprescindible cuando corre como tarea de Windows con pythonw (sin
    # consola): es la unica forma de diagnosticar lo que llega.
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOGS_DIR / "telegram_bot.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    # Filtro de conflictos a nivel handler: aplica a TODOS los registros
    # (PTB loggea en "telegram.ext.Application", los filtros de logger
    # raiz no los alcanzarian).
    filtro_conflict = _FiltroConflict()
    consola = logging.StreamHandler()
    consola.addFilter(filtro_conflict)
    file_handler.addFilter(filtro_conflict)
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        handlers=[consola, file_handler],
    )
    # PTB spamea mucho por default; bajar a WARNING salvo el propio logger.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    application = build_application(config)

    logger.info(
        "Bot iniciando con %d usuarios autorizados (polling cada %.1fs)",
        len(config.allowed_user_ids),
        config.polling_interval,
    )
    application.run_polling(
        poll_interval=config.polling_interval,
        allowed_updates=["message"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
