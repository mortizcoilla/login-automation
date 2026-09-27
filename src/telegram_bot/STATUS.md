# STATUS — Bot Telegram Rubicita (paso 2a)

Feature en rama `feat/telegram-bot-rubicita`.
Sesion de trabajo: 2026-09-21 12:43 — 14:50 CLT (Login-Automation).

---

## Resumen

Bot de Telegram que recibe fotos/PDF de Yadira y las archiva en
`data/examenes_crudos/` (paso 2a del flujo de examenes). NO hace OCR ni
vision; invoca la logica existente en `src/tools/recibir_foto_examen.py`
via una fachada fina.

Modulo nuevo, aislado: NO toca ningun modulo preexistente del proyecto.

---

## Estado: que funciona

| Componente | Estado | Tests |
|---|---|---|
| Carga de configuracion desde `.env` (token, user_ids, paths) | OK | 16 |
| Auth middleware (whitelist de user IDs) | OK | 8 |
| Handler `/start` y `/help` (bienvenida + instrucciones) | OK | parte de handlers tests |
| Handler `/archivar` (foto/PDF + caption) | OK | 14 |
| Handler fallback de texto (libre, comando desconocido, /archivar sin foto) | OK | 6 |
| Servicio fachada sobre `recibir_y_archivar()` | OK | 6 |
| Builder con timeouts robustos (read+connect 30s) | OK | 3 |
| Logging INFO al entry de cmd_archivar (diagnostico) | OK | — |

**53/53 tests pytest verde**. Ruff limpio.

---

## Hallazgos durante desarrollo (cronologico)

### 1. Bootstrap timeout (5s default era insuficiente)

Sintoma: el bot arrancaba pero moria en `getMe()` con `httpcore.ReadTimeout`.
La red estaba OK (TCP/443 alcanzable, HTTPS con `Invoke-WebRequest` respondia 200).
Diagnostico: PTB v22.8 defaults `read_timeout=5.0`. Subimos a 30s en builder.
Verificado: introspeccion real del paquete instalado (`ptb default read_timeout:
5.0`), no de memoria.

### 2. `bootstrap_retries` no existe en PTB v22.8 (yo me lo invente)

Sintoma: `AttributeError: 'ApplicationBuilder' object has no attribute 'bootstrap_retries'`.
Causa: mi memoria de training data era de una version vieja de PTB. Confundi
el parametro de `run_polling(bootstrap_retries=N)` con un builder method.
Fix: introspeccion real → confirmado que solo hay timeouts config.
Leccion aplicada: futuros fixes se introspeccionan PRIMERO con
`dir(ApplicationBuilder())` + `inspect.getsource()`, no de memoria.

### 3. Bot no respondia a texto plano ("hola" sin foto)

Sintoma: usuario mando "hola" al bot y no hubo respuesta.
Causa: el bot solo tenia handlers para `/start` y `/archivar + foto`.
Texto libre caia en el vacio.
Fix: nuevo handler `cmd_text_fallback` (archivo `src/telegram_bot/handlers/text.py`).
Cubre tres casos:
- Texto libre ("hola") -> responde con WELCOME.
- Comando desconocido ("/foo") -> "Comando X no reconocido" + WELCOME.
- `/archivar` sin foto adjunta -> hint especifico pidiendo la foto.

### 4. `CaptionRegex.__init__()` no acepta `flags` como keyword

Sintoma: `TypeError: CaptionRegex.__init__() got an unexpected keyword argument 'flags'`.
Causa: la version de PTB instalada solo acepta `pattern` (str o Pattern).
Fix: pre-compilar con `re.compile(r"^/archivar", re.IGNORECASE | re.DOTALL)`
y pasar la Pattern al constructor.

### 5. `/archivar` con foto no llegaba al handler

Sintoma: el bot procesaba "Hola" (visible en log) pero los `/archivar` con foto
no aparecian en log ni arquivaban archivos.
Diagnostico: filter mismatch. La combinacion `filters.CaptionRegex(...) &
(filters.PHOTO | filters.Document.IMAGE | filters.Document.PDF)` requiere que
Telegram envie la foto con caption exacto arrancando en `/archivar`. Si el
caption llega con alguna variacion (autocapitalize de iOS, espacios al inicio,
caracteres invisibles), el handler no se invoca.
Fix aplicado (parcial): agregar `re.IGNORECASE | re.DOTALL` al pattern.
Fix completo (a validar): si el cambio de flags no es suficiente, hay que:
- agregar log al entry de cmd_archivar (hecho), y
- abrir un handler paralelo de debug que loguee TODO lo que llega.

Estado actual del fix: **en observacion**. El usuario reinicio el bot con
la version nueva y debia enviar un nuevo `/archivar` para verificar si el
log `cmd_archivar invocado:` aparece. Esta pendiente confirmar con datos
antes de proponer el fix completo.

---

## Issues pendientes (con datos del estado al cierre)

### P0 — Verificar fix de filter IGNORECASE

Accion: usuario reinicia el bot y manda `/archivar Paciente Prueba` con foto.
Confirmar:
- (a) `cmd_archivar invocado: ...caption='/archivar...' has_photo=True...`
  aparece en log: filter OK, problema era IGNORECASE.
- (b) NO aparece en log: filter sigue rechazando, requiere fix de fondo
  (handler paralelo de debug para auditar el payload de Telegram).

### P1 — TG bot token esta en .env y en historial de chat

Token del `Miguelbrino_bot` y otros tokens del .env fueron compartidos en
transcript del chat. Todos esos tokens/secrets deben rotarse al cerrar la
sesion de pruebas:
- `@BotFather` `/revoke` para cada bot.
- Regenerar keys de: opencode-go, MiniMax, kimi, gemini, z.ai.
- Actualizar `.env` con las nuevas keys (`.env` ya esta gitignored).

### P2 — cmd_archivar sin test para el path de "fallo de descarga"

`tg_file.download_to_drive` se mockea como `AsyncMock` pero no hay test que
verifique el camino de error (timeout de red, file_id invalido). Tests
actuales asumen exito. Agregar cuando se tenga un caso real.

### P3 — Multi-photo (album) y media_group_id

v1 solo soporta 1 foto por mensaje. Albums de Telegram (varias fotos con
mismo `media_group_id`) caen al cmd_archivar por cada foto, con `indice=1`,
provocando colisiones resueltas por `resolver_path_sin_colision` (suffix
`_v2`, `_v3`, ...). No es correcto semanticamente.
Plan: cuando se haga multi-photo, registrar el media_group_id en
`bot_data` y esperar N segundos para consolidar antes de archivar.

### P4 — `set_bot_token.ps1` no commiteado (one-shot)

`set_bot_token.ps1` esta en el workspace root pero NO se incluye en este
commit porque tiene `user_id=1389428233` hardcoded (PII menor). Si se
quiere preservar como utilidad, parametrizar `user_id` y/o mover a
`scripts/setup_bot.ps1`. Si no, borrar despues de las pruebas:

```powershell
Remove-Item .\set_bot_token.ps1
```

---

## Archivos creados (no pisan nada existente)

```
src/telegram_bot/
  __init__.py
  app.py                      # builder + entrypoint
  config.py                   # BotConfig.from_env()
  README.md                   # uso, deployment, troubleshooting
  STATUS.md                   # este archivo
  middleware/__init__.py
  middleware/auth.py           # whitelist de user IDs
  handlers/__init__.py
  handlers/start.py           # /start, /help
  handlers/photo.py           # /archivar (foto/PDF + caption)
  handlers/text.py            # fallback para texto libre
  services/__init__.py
  services/recibir_foto_service.py    # fachada sobre recibir_y_archivar()

tests/test_telegram_bot_config.py       # 16 tests
tests/test_telegram_bot_middleware.py   # 8  tests
tests/test_telegram_bot_handlers.py     # 14 tests
tests/test_telegram_bot_handlers_text.py# 6  tests
tests/test_telegram_bot_services.py     # 6  tests
tests/test_telegram_bot_app.py          # 3  tests
```

Total: 53 tests. ruff limpio.

NO commiteado:
- `set_bot_token.ps1` (one-shot con user_id hardcoded)
- `data/test_rubicita/` (sandbox externo en `$env:USERPROFILE`, fuera del repo)
- `.env` (gitignored; contiene tokens reales)

---

## Pendientes para commit / merge a `main`

1. **Verificar fix de filter** (P0): dato fresco necesario.
2. **Rotar tokens** (P1): hacerlo antes de merge, no despues.
3. **Borrar `set_bot_token.ps1`** (P4): o parametrizar antes de commitear.
4. **Documentar rama en AGENTS.md y README.md**: AGENTS.md §8 dice
   "agents/mortadelo/ ELIMINADO" (stale); deberia mencionar que el bot
   corre con opencode CLI + telegraph agents/.
5. **Cerrar drift documental**: AGENTS.md deberia listar el paquete
   nuevo en la estructura §4.

---

## Comandos utiles para re-arrancar el sandbox

```powershell
# 1. Crear sandbox externo (una sola vez)
New-Item -Path "$env:USERPROFILE\rubicita_test\notas_clinicas" -ItemType Directory -Force
New-Item -Path "$env:USERPROFILE\rubicita_test\examenes_crudos" -ItemType Directory -Force
# Plus una nota de paciente ficticia con frontmatter en notas_clinicas/.

# 2. Configurar .env (una sola vez, paste-and-edit)
notepad C:\Workspace\Login-Automation\.env
# Agregar: TELEGRAM_BOT_TOKEN_RUBICITA=...  TELEGRAM_ALLOWED_USER_IDS=...
#          TELEGRAM_NOTAS_DIR=...           TELEGRAM_DESTINO_DIR=...

# 3. Arrancar bot
cd C:\Workspace\Login-Automation
.\venv\Scripts\python.exe -m src.telegram_bot.app

# 4. Limpiar al terminar
Remove-Item -Recurse -Force $env:USERPROFILE\rubicita_test
Remove-Item .\set_bot_token.ps1   # si existe
```
