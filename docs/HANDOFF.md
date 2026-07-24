# Handoff de sesión — 2026-07-23

> Documento para retomar la conversación en un chat nuevo. El contexto
> del chat se llena; este archivo es la fuente de verdad hasta que se
> decida otra cosa.

---

## Quiénes somos

- **Miguel** (este chat): ingeniero, constructor del sistema. Trabaja
  en MiniMax Code desde Windows.
- **Yadira**: médica del CESFAM San Bernardo, end-user. Ella NO usa
  MiniMax Code; usará el bot desde su teléfono personal vía Telegram
  cuando esté todo listo.
- **El bot/equipo** es para **ella**, no para Miguel. Miguel lo construye
  y mantiene.

## El proyecto

`C:\Workspace\Login-Automation` — repo público en
https://github.com/mortizcoilla/login-automation. Última versión
commiteada: `bc2160e`.

**Stack**: Python 3.10+, Selenium 4.27+, requests, pytest, ruff, mypy.
**Idioma del código y de Yadira**: español de Chile.
**Mini PC Ubuntu** disponible para correr tareas 24/7 (cron, cola,
automatización Rayen).

## El equipo de gatos (Mavis agents)

Yadira juega con sus gatos como "colegas". El equipo se llama por ellos.
Ubicación: `C:\Users\morti\.minimax\agents\<nombre>\`.

**Casa de ella (6, MVP completo):**
- 🐱 **Pilita** — orquestadora, habla con Yadira por Telegram
- 🐱 **Teodoro** — médico de familia APS, motor de razonamiento
- 🐱 **Pancho** — enfermero de proceso (login, fetch, enviar a Rayen)
- 🐱 **Pelusa** — salud mental (SIC COSAM, riesgo suicida)
- 🐱 **Gustavo** — arsenal farmacológico APS
- 🐱 **Anita** — reportes y métricas (cron 19:00)

**Casa del novio (5, pendientes de crear):**
- 🐱 **Luffyalberto** ("macho rudo") — hard validator
- 🐱 **Dominga** ("la jefa") — supervisora
- 🐱 **Negrita** ("consentida") — quick reference
- 🐱 **Mauricia** ("recién llegada") — second opinion
- 🐱 **Rubí** ("la malandra") — red team / devil's advocate

## Arquitectura

```
Tú (Telegram) → Bot → Bridge Mavis → Pilita
                                    ├→ Teodoro (clínico)
                                    ├→ Pancho (Rayen)
                                    └→ [otros gatos]

Estado de cada ficha: SQLite en data/queue.db
Reportes: src/anita/cron_runner.py (cron 19:00)
```

**Yadira es la única autorizada a aprobar envíos.** Validación por
sender_id de Telegram (pendiente de capturar el real).

## Reglas duras (NO NEGOCIABLES)

1. **Validación humana**: la médica aprueba cada ficha antes del
   envío. Doble gesto: ✅ (aprobación) + 📤 (envío). Sin esto, NO
   se envía. Anclado en código (queue_store state machine +
   pancho_skills.enviar) Y en system prompt de Pilita.
2. **Sin LLM externos**: NO Gemini API ni otros cloud. Razonamiento
   local con el system prompt GEM como prompt del agente Teodoro.
3. **Privacidad**: RUT, nombre, observación NUNCA van a cloud. Solo
   contenido clínico seudonimizado para razonamiento local.
4. **RUT nunca en la DB**: solo se guarda `sha256(rut)[:16]`.

## Lo que está construido y funcionando

- ✅ **3 agentes creados** (Pilita, Teodoro, Pancho) con system
  prompts completos. Probados en MiniMax Code el 23-07: 3/3 tests
  manuales pasaron (presentación, análisis clínico, principio de
  validación).
- ✅ **queue_store.py**: state machine SQLite con 6 estados,
  transiciones validadas, audit completo, tokens con TTL y un solo
  uso. 27 tests.
- ✅ **pancho_skills/**: 3 skills reales (login, listar_iniciados,
  leer_ficha) + 2 stubs (historial, enviar) con TODOs explícitos.
  El principio de validación YA está activo: enviar rechaza sin
  token válido. 13 tests.
- ✅ **anita/**: reportes diarios con formato Telegram MarkdownV2.
  CLI invocable por cron. 11 tests.
- ✅ **Tests**: 106 pasando (de 45 al inicio de la sesión).
- ✅ **Demos**: `demo_app.py` (7 escenas coloreadas) y
  `demo_reporte.py`.
- ✅ **Telegram**: bot creado y bonded como `@PilitaBot`, pero **no
  responde a mensajes** (bug pendiente).
- ✅ **Documentación**: `docs/guia-vincular-pilita-telegram.md` con
  el flujo de configuración.
- ✅ **Test fixture**: `data/test_cases/caso_hta_femenina_50a.json`
  blinda el principio de validación contra regresiones.

## Lo que está PENDIENTE (en orden de prioridad)

1. **🔴 Submit real a Rayen** — `enviar_ficha` levanta
   `NotImplementedError` en el submit real. Necesita sesión con
   UI de Rayen abierta para descubrir el flujo (clicks/URL).
2. **🔴 Endpoints de historial clínico y farma** — `obtener_historial`
   es stub. Requiere correr `src/discover_api.py` con sesión
   activa, navegando a los módulos de Historia y Recetas.
3. **🟡 Capturar telegram sender_id de Yadira** — necesario para
   formalizar la validación de identidad.
4. **🟡 Debug del bot Pilotabot que no responde** — el bot aparece
   bonded en Mavis Mobile (Preferences) pero no reacciona a
   `/start` ni a mensajes.
5. **🟢 UI visual "Sala del CESFAM"** (Opción A: HTML+CSS+JS +
   polling contra queue.db). F1: mockup estático. Diseño en
   conversación del 23-07.
6. **🟢 Setup cron real en mini PC Ubuntu** — para producción.
7. **🟢 Crear los 8 gatos restantes** (Pelusa, Gustavo, los 5 del
   novio).

## Comandos útiles

```bash
# Verificar estado del sistema
cd C:\Workspace\Login-Automation
python -m pytest                              # 106 tests
python demo_app.py                            # simulación completa

# Reporte de hoy
$env:PYTHONIOENCODING="utf-8"
python -m src.anita.cron_runner --db data/queue.db --formato telegram

# Listar agentes creados
mavis agent list
```

## Memoria del usuario

Archivo: `C:\Users\morti\.minimax\memory\user.md`. Contiene:
- Perfil de Miguel (ingeniero, magíster finanzas + ops/logística)
- Perfil de Yadira (médica CESFAM San Bernardo)
- Los 11 gatos y sus roles
- Reglas duras del proyecto clínico
- Proyecto Login-Automation + estado
- Infra disponible (mini PC Ubuntu)

## Estilo de trabajo de Miguel

- Idioma: español de Chile, cálido pero profesional
- Le gusta discutir el approach antes de ejecutar
- Valora las decisiones fundamentadas, no las opciones sin filtro
- Acepta "no sé, hay que investigar" si es honesto
- No le gusta el código que parece "enterprise" sin justificación
- Prefiere SQLite, scripts simples, dependencias mínimas

## Estado de los archivos de Yadira (datos sensibles)

⚠️ **`config/users.json` tiene password en plano en git history**.
El `.gitignore` lo excluye a futuro pero ya está en el primer
commit. **Recomendado: rotar la password de Yadira en algún
momento.**

⚠️ **`config/api_config.json` tiene cookies reales** con
`.AspNet.Cookies`. Sesión activa hasta que Rayen las rote.

⚠️ **`data/raw_responses/` y `data/pacientes_2026.csv`** tienen
datos clínicos de pacientes (RUT, nombre, etc.). Ley 19.628
(Chile) — datos sensibles.

Para la próxima sesión, no re-compartir estos datos en chat.

## Cómo retomar

1. Abrir nueva conversación con Mavis.
2. Pegar el contenido de este archivo como primer mensaje.
3. Decir "Continuamos desde donde quedamos. Próximo paso: [X]"
   donde X es uno de los pendientes priorizados.

---

**Última actualización**: 2026-07-23 12:14 GMT-4
**Commits hasta ahora**: 2 (first commit + 2026-07-23)
**Próximo paso sugerido**: submit real a Rayen (prioridad 1)
