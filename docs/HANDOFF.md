# Handoff de sesión — 2026-07-23 (cierre)

> Documento para retomar la conversación en un chat nuevo. El contexto
> del chat se llena; este archivo es la fuente de verdad hasta que se
> decida otra cosa.
>
> Esta versión reemplaza al HANDOFF del mediodía. Cubre la sesión
> completa del 23-07 (mañana + tarde), incluyendo el trabajo de
> tracking de fichas abiertas.

---

## Quiénes somos

- **Miguel** (este chat): ingeniero, constructor del sistema. Trabaja
  en MiniMax Code desde Windows. Magíster en Finanzas + Magíster en
  Dirección de Operaciones y Logística. Esposo de Yadira.
- **Yadira**: médica del CESFAM Raúl Cuevas, San Bernardo. End-user.
  Ella NO usa MiniMax Code; usará el bot desde su teléfono personal
  vía Telegram cuando esté todo listo. Atiende pacientes en Rayen APS
  y necesita cerrar las fichas que se le quedan en estado "Iniciado".
- **El bot/equipo** es para **ella**, no para Miguel. Miguel lo construye
  y mantiene.

## El proyecto

`C:\Workspace\Login-Automation` — repo público en
https://github.com/mortizcoilla/login-automation.

**Última versión commiteada**: `99144e3` (cierre 23-07 noche).

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
- 🐱 **Gustavo** — **analista de datos** (informes, comparaciones 2025 vs 2026,
  estacionalidad). System prompt en `C:\Users\morti\.minimax\agents\gustavo\agent.md`.
  Maneja los scripts de `src/analysis/`.
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

Estado de cada ficha clínica:    SQLite en data/queue.db
Tracking acumulativo de abiertas: SQLite en data/analysis/tracking.db
Reportes:                        src/anita/cron_runner.py (cron 19:00)
Análisis:                        src/analysis/ (live, histórico, tracking)
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
5. **Datos sensibles fuera de chat**: nunca pegar contenido de
   `config/users.json`, `config/api_config.json`, `data/raw_responses/`,
   `data/pacientes_2026.csv` o `data/analysis/tracking.db` en el chat.

## Lo que está construido y funcionando

### Capa clínica (sesión del mediodía)
- ✅ **3 agentes Mavis** (Pilita, Teodoro, Pancho) con system prompts
  completos. 3/3 tests manuales pasaron.
- ✅ **queue_store.py**: state machine SQLite con 6 estados,
  transiciones validadas, audit completo, tokens con TTL y un solo
  uso. 27 tests.
- ✅ **pancho_skills/**: 3 skills reales (login, listar_iniciados,
  leer_ficha) + 2 stubs (historial, enviar) con TODOs explícitos.
  El principio de validación YA está activo: enviar rechaza sin
  token válido. 13 tests.
- ✅ **anita/**: reportes diarios con formato Telegram MarkdownV2.
  CLI invocable por cron. 11 tests.
- ✅ **Demos**: `demo_app.py` (7 escenas coloreadas) y
  `demo_reporte.py`.
- ✅ **Test fixture**: `data/test_cases/caso_hta_femenina_50a.json`
  blinda el principio de validación contra regresiones.

### Capa de análisis de abiertas (sesión de la tarde)
- ✅ **Flow UI arreglado** (`src/browser_automation.py`): wait
  defensivo por el modal "Cargando" después de cada click (menú, Box,
  Pacientes citados). Timeout de `select_date` subido de 20s a 60s.
- ✅ **Selector del menú actualizado**: `span.pl-3.navbar-app-title`
  (en `config/selectors.json`).
- ✅ **`src/analysis/fichas_abiertas_historico.py`**: análisis
  agregado de `data/raw_responses/*.json`. Reporta por día: total
  citadas, distribución por estado, top días con más "Iniciado",
  distribución por tipo. Probado: 82 días, 1.222 citas, 12 "Iniciado"
  en todo el periodo (1.0%), 100% concentradas en mayo. CSV generado
  en `data/analysis/fichas_abiertas_historico.csv`.
- ✅ **`src/analysis/fichas_hoy.py`**: live check del día. Login +
  navegar a Pacientes citados + setear fecha de hoy + listar
  "Iniciado". **Probado en vivo con la cuenta de Yadira (23-07-2026):
  5 fichas confirmadas** (4 ECICEP-G3 + 1 Recetas). Output
  persistente en `data/analysis/fichas_hoy_<dd-mm-yyyy>.txt`. NO
  imprime RUT, nombre ni observación.
- ✅ **`src/analysis/tracking_diario.py`**: tracking acumulativo día
  por día. Recorre desde 01-01-2026 (o desde la fecha mínima de
  primera_vista registrada) hasta hoy, hace upsert por IdCita en
  SQLite, re-loguea si la sesión muere, genera reporte final con
  total abiertas, distribución por tipo, fichas nuevas vs.
  actualizadas. **Probado en vivo con rango 01-07-2026 → 23-07-2026:
  11 fichas distintas detectadas** (Yadira abrió una receta durante
  el run). DB: `data/analysis/tracking.db`.
- ✅ **`src/analysis/debug_flujo.py`**: script de debug que ejecuta
  solo el flujo de login + 3 clicks + verifica que el date input
  exista. Captura screenshots en cada paso (`step_1_menu_*.png`,
  `step_2_box_*.png`, `step_3_pacientes_citados_*.png`,
  `step_4_final_state_*.png`).
- ✅ **Tests**: 106 pasando (sin cambios desde el mediodía).

### Insight clave sobre los datos
- **`raw_responses/*.json`**: son **snapshots por día**, NO histórico
  de arrastre. Cada IdCita aparece en un único día. Por eso
  `fichas_abiertas_historico.py` muestra "12 Iniciado en 82 días" pero
  NO es el backlog real. **El backlog real solo se puede medir con
  tracking acumulativo** (lo que hace `tracking_diario.py`).
- **"Pendiente" ≠ "Iniciado"**: "Pendiente" son pacientes que no
  llegaron (lo reagenda otra persona). "Iniciado" son fichas que la
  médica empezó y no terminó — el foco único de Yadira.
- **Las fichas no cambian de estado**: una vez que Yadira cierra
  una "Iniciado", pasa a "Completado" y no vuelve. Eso hace
  posible el tracking acumulativo.

## Lo que está PENDIENTE (en orden de prioridad)

1. **🟡 Run del año completo** — `python -m src.analysis.tracking_diario`
   (sin flags). Recorre 143 días hábiles (01-01-2026 → 23-07-2026).
   Tiempo estimado: 15-25 min. Re-loguea si la sesión muere. La DB
   ya tiene el run de julio, así que el run del año solo agrega
   enero-junio.
2. **🔴 Submit real a Rayen** — `enviar_ficha` levanta
   `NotImplementedError` en el submit real. Necesita sesión con
   UI de Rayen abierta para descubrir el flujo (clicks/URL/payload).
3. **🟡 Detección de cierres** — agregar `fecha_cierre` a la tabla
   `fichas` del tracking. Cuando una ficha vista en día N NO aparece
   en día N+1, marcarla como cerrada con `fecha_cierre = N+1`. Eso
   requiere que el script corra diario. Sin esto, no podemos
   calcular "tiempo promedio de cierre" ni hacer análisis
   estadísticos sobre cuánto tarda Yadira.
4. **🟡 Análisis estadísticos** — una vez que tengamos cierres,
   queries sobre la DB: tiempo promedio de cierre por tipo, ranking
   de fichas más antiguas abiertas, distribución de carga por
   día-de-semana, etc. Esto era el objetivo último de Yadira:
   "**hacer análisis estadísticos que le permitan mejorar**".
5. **🔴 Endpoints de historial clínico y farma** — `obtener_historial`
   sigue siendo stub. Requiere correr `src/discover_api.py` con
   sesión activa, navegando a los módulos de Historia y Recetas.
6. **🟡 Capturar telegram sender_id de Yadira** — necesario para
   formalizar la validación de identidad.
7. **🟡 Debug del bot Pilotabot que no responde** — el bot aparece
   bonded en Mavis Mobile (Preferences) pero no reacciona a
   `/start` ni a mensajes.
8. **🟢 UI visual "Sala del CESFAM"** (Opción A: HTML+CSS+JS +
   polling contra `data/analysis/tracking.db`). Mockup estático.
9. **🟢 Setup cron real en mini PC Ubuntu** — para producción.
10. **🟢 Crear los 8 gatos restantes** (Pelusa, Gustavo, los 5 del
    novio).

## Comandos útiles

```powershell
cd C:\Workspace\Login-Automation

# Tests
python -m pytest                                            # 106 tests

# Live check del día (probado, funciona)
$env:PYTHONIOENCODING="utf-8"
python -m src.analysis.fichas_hoy

# Tracking de un rango específico (probado, funciona)
python -m src.analysis.tracking_diario --desde 01-07-2026 --hasta 23-07-2026

# Tracking del año completo (pendiente, ~15-25 min)
python -m src.analysis.tracking_diario

# Debug del flujo UI (probado, valida login + 3 clicks)
python -m src.analysis.debug_flujo

# Análisis histórico desde raw_responses/
python -m src.analysis.fichas_abiertas_historico

# Reporte de hoy (anita)
python -m src.anita.cron_runner --db data/queue.db --formato telegram

# Simulación completa
python demo_app.py

# Listar agentes creados
mavis agent list
```

## Memoria del usuario

Archivo: `C:\Users\morti\.minimax\memory\user.md`. Contiene:
- Perfil de Miguel (ingeniero, magíster finanzas + ops/logística,
  esposa de Yadira)
- Perfil de Yadira (médica CESFAM Raúl Cuevas, San Bernardo;
  11 gatos)
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
- **Le molesta que ofrezca "parar hasta mañana"** cuando él dice
  que se soluciona hoy. Asumir: él quiere avanzar, no postergar
- Le importa que cada ficha tenga `fecha_apertura` y `fecha_cierre`
  explícitas para análisis a futuro

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

⚠️ **`data/analysis/tracking.db`** es nuevo. Tiene `tabla fichas`
con (cita_id como proxy hash, tipo_atencion, fecha_primera_vista,
fecha_ultima_vista). No tiene RUT ni nombre, pero sí es trazable
a citas específicas. **NO commitear** (ya está en `.gitignore`).

Para la próxima sesión, no re-compartir estos datos en chat.

## Cómo retomar

1. Abrir nueva conversación con Mavis.
2. Pegar el prompt de retoma (ver más abajo).
3. Mavis lee este HANDOFF y entiende el contexto completo.
4. Decir "Continuamos desde donde quedamos. Próximo paso: [X]"
   donde X es uno de los pendientes priorizados.

---

**Última actualización**: 2026-07-24 23:36 GMT-4
**Commits hasta ahora**: 8 (incluye los nuevos scripts de análisis)
**Último commit**: `85ba8e1` — actualizar_mes_actual + rescatar_anio_2025

**Agente Gustavo creado (24-07-2026 noche)**:
- Ubicación: `C:\Users\morti\.minimax\agents\gustavo\`
- System prompt: `agent.md` (6 KB) — enfocado en analítica
- Maneja los scripts de `src/analysis/`
- Comandos: `informe`, `informe-semanal`, `informe-mensual`, `compara`,
  `lista-hoy`, `cuantas-abiertas`, `tipo-dificil`, `actualizar`
- Privacy: nombres SOLO en informes a Yadira, NUNCA a cloud

**DBs de análisis (24-07-2026)**:
- `data/analysis/fichas_completo.db` — TODAS las fichas con TODOS los campos (2025 + 2026)
- `data/analysis/tracking.db` — tracking de "Iniciado" con upsert + cierres
- `data/analysis/tracking_completo.db` — agregados por día de todos los estados
- Total de registros al cierre: 1774 (solo 2026, año completo)

**Próximo paso sugerido**: correr `rescatar_anio_2025` para tener 2025 en la DB
y poder hacer las comparaciones interanual. ~20-40 min.
