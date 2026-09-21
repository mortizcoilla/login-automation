"""Telegram bot (Rubicita): recibe fotos de Yadira y las archiva en
data/examenes_crudos/. Nivel 1 (paso 2a del flujo de examenes, REQ-012).

Este paquete es NUEVO y aislado. NO modifica ningun modulo existente:
  - config: carga TELEGRAM_BOT_TOKEN_RUBICITA y TELEGRAM_ALLOWED_USER_IDS
  - middleware.auth: whitelist de usuarios Telegram (solo Yadira + operador)
  - handlers: /start, /help, /archivar (recepcion de fotos con caption)
  - services.recibir_foto_service: fachada sobre recibir_y_archivar()
  - app: builder del Application y entrypoint CLI

Entry-point:
    python -m src.telegram_bot.app

La logica de negocio (matching de paciente, archivado byte-a-bit, resolucion
de fecha del informe) sigue viviendo en src/tools/recibir_foto_examen.py.
El bot solo la invoca via el facade de services.
"""
