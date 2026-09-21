# Rubicita — bot de Telegram para Login-Automation

Recibe fotos/PDFs de Yadira por Telegram y los archiva en
`data/examenes_crudos/` con la convencion del proyecto.

Alcance v1: solo recepcion de fotos. NO envia recordatorios, NO aprueba
fichas, NO interactua con queue_store.

## Instalacion

### 1. Crear el bot en Telegram

1. Hablar con @BotFather.
2. `/newbot` -> seguir pasos -> guardar el token que entrega.
3. (Opcional) `/setdescription` y `/setabouttext`.

### 2. Obtener el user_id de Yadira

Una vez creado el bot, que Yadira le escriba `/start`. Ver el log del bot
o temporalmente agregar al `config.py` que loguee el `update.effective_user.id`
del primer mensaje.

Alternativa: que Yadira le escriba a @userinfobot y te pase su ID.

### 3. Configurar el .env

Agregar al `.env`:

```
TELEGRAM_BOT_TOKEN_RUBICITA=<token de BotFather>
TELEGRAM_ALLOWED_USER_IDS=<id_yadira>[,<id_operador>]

# Opcionales:
TELEGRAM_POLLING_INTERVAL=1.0
TELEGRAM_LOG_LEVEL=INFO
# Solo para tests:
# TELEGRAM_NOTAS_DIR=/tmp/notas_test
# TELEGRAM_DESTINO_DIR=/tmp/examenes_test
```

### 4. Instalar la dependencia

```
pip install python-telegram-bot>=20.0
```

(Tambien agregar a `pyproject.toml` -> `[project] dependencies` para que
el flujo `pip install -e .` lo traiga automaticamente.)

### 5. Correr el bot

```
python -m src.telegram_bot.app
```

Dejar corriendo (Programador de Tareas de Windows, NSSM, o supervisord).

## Uso por Yadira

```
/start   -> bienvenida y formato esperado.

/archivar <paciente> [dd-mm-yyyy]
  - foto/PDF como caption
  - <paciente> puede ser parcial (Rubicita busca el nombre completo en
    data/notas_clinicas/)
  - [dd-mm-yyyy] es opcional (si se omite, se usa la fecha del informe)
```

### Ejemplos

```
[foto.jpg con caption:]
/archivar Benedicto Martin

[foto1.jpg con caption:]
/archivar Benedicto Alfonso Martin Colimil 16-09-2026

[PDF.pdf con caption:]
/archivar Marta Perez 18-09-2026
```

### Limites v1

- **Una foto por mensaje.** Para albums (varias fotos simultaneas), enviar
  cada una por separado. Multi-foto esta en el roadmap.
- **Videos/audios NO se procesan.** Si Yadira envia, el bot responde
  "Solo proceso fotos o documentos."
- **Sin albumes (media_group_id)**: si se envian, se procesa cada una
  como mensaje independiente con indice 1 (resolver_path_sin_colision evita
  el overwrite — las siguientes iran con sufijo _v2, _v3).

## Verificacion

```
pytest -q tests/test_telegram_bot_*.py
ruff check src/telegram_bot tests/test_telegram_bot_*.py
mypy src/telegram_bot
```

Los tests mockean PTB y `recibir_y_archivar`. No hacen llamadas reales a
Telegram ni mueven archivos reales (usan tmp dirs).

## Cambios pendientes (mano del operador)

1. `pyproject.toml`: agregar `python-telegram-bot>=20.0` a `[project] dependencies`.
2. `coverage source`: si se quiere meter el nuevo paquete al gate, agregar
   `"src/telegram_bot"` a `pyproject.toml -> [tool.coverage.run] source`.
   Esto NO se hizo automaticamente porque toca un archivo existente.
3. Test end-to-end con Telegram real: requiere token valido + un usuario
   autorizado. Se puede automatizar con pytest + `httpx_mock`, pero esta
   fuera de alcance v1.

## Por que polling y no webhook

- Yadira envia fotos desde su celular al bot que corre en la mini PC
  (Windows, LAN casera, sin IP publica fija).
- Webhook requiere VPS con DNS, HTTPS y uptime: overkill para este caso.
- Polling: 1 proceso local, 1 puerto saliente a Telegram, ~1s de latencia.
- Si en el futuro hay volumen o latencia sub-segundo, se cambia a webhook
  con `application.run_webhook()` sin tocar handlers.

## Estructura del paquete

```
src/telegram_bot/
  __init__.py
  app.py                    # entrypoint + Application builder
  config.py                 # BotConfig.from_env()
  middleware/
    auth.py                 # whitelist de user IDs
  handlers/
    start.py                # /start, /help
    photo.py                # /archivar (foto/PDF con caption)
  services/
    recibir_foto_service.py # fachada sobre recibir_y_archivar()
```

Tests en `tests/test_telegram_bot_*.py`.

## NO pisa modulos existentes

- `pyproject.toml`: NO se modifico. Diff para agregar dep y coverage abajo.
- `.env.example`: NO se modifico. Diff para agregar ALLOWED_USER_IDS abajo.
- `src/tools/recibir_foto_examen.py`: solo lectura via service.
- `src/core/rutas.py`: solo lectura, transitivamente via el service.
