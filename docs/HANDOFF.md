# Handoff de sesión — 2026-07-25 (kick off cierre semana)

> Documento para retomar la conversación en un chat nuevo. El contexto
> del chat se llena; este archivo es la fuente de verdad hasta que se
> decida otra cosa.
>
> Esta versión cubre la sesión completa del 23-07 (mañana + tarde) y
> 24-07 (sesión de tracking, DBs, agente Gustavo) y 25-07 (regla de
> plantillas).

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

**Última versión commiteada**: `2441c04` (cierre 25-07 madrugada).

**Stack**: Python 3.10+, Selenium 4.27+, requests, pytest, ruff, mypy,
openpyxl (para Excel).
**Idioma del código y de Yadira**: español de Chile.
**Mini PC Ubuntu** disponible para correr tareas 24/7 (cron, cola,
automatización Rayen).

## El equipo de gatos (Mavis agents)

Yadira juega con sus gatos como "colegas". El equipo se llama por ellos.
Ubicación: `C:\Users\morti\.minimax\agents\<nombre>\`.

**Creados (4)**:
- 🐱 **Pilita** — orquestadora, habla con Yadira por Telegram
- 🐱 **Teodoro** — médico de familia APS, motor de razonamiento
- 🐱 **Pancho** — enfermero de proceso (login, fetch, enviar a Rayen)
- 🐱 **Gustavo** — **analista de datos** (informes, comparaciones 2025 vs 2026,
  estacionalidad). System prompt en
  `C:\Users\morti\.minimax\agents\gustavo\agent.md`. Maneja los
  scripts de `src/analysis/`.

**Pendientes de crear (7)**:
- 🐱 **Pelusa** — salud mental (SIC COSAM, riesgo suicida)
- 🐱 **Anita** — reportes y métricas (cron 19:00)
- 🐱 Luffyalberto, Dominga, Negrita, Mauricia, Rubí (casa del novio)

## Arquitectura

```
Yadira (Telegram) -> Bot -> Bridge Mavis -> Pilita
                                          ├-> Teodoro (clínico)
                                          ├-> Pancho (Rayen)
                                          └-> Gustavo (analítica)

Estado fichas clínicas:    SQLite en data/queue.db
Tracking "Iniciado" + cierres:    SQLite en data/analysis/tracking.db
Tracking completo (todos los estados): SQLite en data/analysis/tracking_completo.db
DB completa 2025+2026 (todos los campos): SQLite en data/analysis/fichas_completo.db
Análisis: src/analysis/ (scripts de tracking y reportes)
```

**Yadira es la única autorizada a aprobar envíos.** Validación por
sender_id de Telegram (pendiente de capturar el real).

## Reglas duras (NO NEGOCIABLES) — revisadas 24-07

1. **Validación humana** (la ÚNICA regla dura): la médica aprueba cada
   ficha antes del envío. Doble gesto: ✅ + 📤. Anclado en código
   (queue_store + pancho_skills.enviar) Y en system prompt de Pilita.
2. ~~Sin LLM externos~~ **LEVANTADA el 24-07**: los datos SÍ pueden
   ir a LLMs cloud (Gemini, OpenAI, etc.) si el flujo lo requiere.
3. ~~Privacidad estricta~~ **LEVANTADA el 24-07**: Yadira decide
   adónde van los datos (Telegram, email, print, etc.). Header
   obligatorio: "⚠️ Confidencial — datos clínicos" en envíos a
   canales externos.
4. **RUT nunca en la DB** (se mantiene): solo se guarda
   `sha256(rut)[:16]`. Es buena práctica local.

## Lo que está construido y funcionando

### Capa clínica (sesión 23-07 AM)
- ✅ **3 agentes Mavis** (Pilita, Teodoro, Pancho) con system prompts
  completos. 3/3 tests manuales pasaron.
- ✅ **queue_store.py**: state machine SQLite con 6 estados,
  transiciones validadas, audit completo, tokens con TTL y un solo
  uso. 27 tests.
- ✅ **pancho_skills/**: 3 skills reales (login, listar_iniciados,
  leer_ficha) + 2 stubs (historial, enviar) con TODOs explícitos.
  El principio de validación YA está activo. 13 tests.
- ✅ **anita/**: reportes diarios con formato Telegram MarkdownV2.
  CLI invocable por cron. 11 tests.
- ✅ **Demos**: `demo_app.py` y `demo_reporte.py`.
- ✅ **Test fixture**: `data/test_cases/caso_hta_femenina_50a.json`
  blinda el principio de validación.

### Capa UI de Rayen (sesión 23-07 PM y 24-07)
- ✅ **Flow UI arreglado** (`src/browser_automation.py`): wait
  defensivo por modal "Cargando" después de cada click (menú, Box,
  Pacientes citados). Timeout `select_date` subido de 20s a 60s.
  Sort_by_estado tolerante a días sin "Iniciado" (commit `857f950`).
- ✅ **Selector del menú actualizado**: `span.pl-3.navbar-app-title`.

### Capa de análisis de abiertas (sesión 24-07)
- ✅ **`src/analysis/fichas_abiertas_historico.py`**: análisis
  agregado de `data/raw_responses/*.json`. Genera
  `data/analysis/fichas_abiertas_historico.csv`.
- ✅ **`src/analysis/fichas_hoy.py`**: live check del día con output
  persistente a `data/analysis/fichas_hoy_<fecha>.txt`. **Probado en
  vivo con 5 fichas confirmadas en 23-07-2026**.
- ✅ **`src/analysis/tracking_diario.py`**: recorrido día por día con
  upsert en SQLite. Soporta `--historico` (fuerza 01-01-2026) y
  `--desde/--hasta`. Re-login defensivo. Marca fichas cerradas.
  **Probado en vivo: 13 abiertas, 23 cerradas (rango julio 2026)**.
- ✅ **`src/analysis/tracking_completo.py`**: agregados por día de
  TODOS los estados.
- ✅ **`src/analysis/listar_fichas_hoy.py`**: live check con TODOS
  los estados y TODOS los campos.
- ✅ **`src/analysis/listar_fichas_abiertas.py`**: live check
  "Iniciado" + tracking (ult. visto, cerrada_el).
- ✅ **`src/analysis/debug_flujo.py`**: debug del flujo UI paso a paso.
- ✅ **`src/analysis/fichas_completo_db.py`**: llena DB SQLite con
  TODAS las fichas del año (todos los campos). UPSERT por
  (fecha, hora, nombre). **Probado: 147 días, 1774 fichas registradas**.
- ✅ **`src/analysis/actualizar_mes_actual.py`**: uso diario, borra
  el mes en curso y lo regenera (sobrescribe).
- ✅ **`src/analysis/rescatar_anio_2025.py`**: recorrido del 2025
  para comparación interanual.

### Capa de plantillas (sesión 25-07)
- ✅ **`src/reglas_plantillas.py`**: regla de uso de plantillas
  extraída de `PLANTILLAS.xlsx`. 6 plantillas canónicas + NO APLICA.
  Función `resolver_plantilla(tipo, edad_meses=None)` con lógica de
  edad para "Control de niño sano" (1 mes vs 3 meses, corte en 3
  meses).
- ✅ **`src/plantillas.py`**: actualizado para usar la regla. Función
  `cargar_plantilla(tipo, edad_meses=None)`.
- ✅ **7 archivos de plantilla** en `plantillas/` (en MAYÚSCULAS):
  `MORBILIDAD.txt`, `RECETA.txt`, `INGRESO ECICEP.txt`,
  `INGRESO SALUD MENTAL SIN ECICEP.txt`, `CONTROL INTEGRAL SIN FICHA
  ANTERIOR.txt`, `CONTROL NIÑO SANO 1 MES.txt`, `CONTROL NIÑO SANO
  3 MESES.txt`, `NO APLICA.txt`.

### Tests
- ✅ **141 tests pasando** (de 45 al inicio de la sesión del 23-07)
- ✅ 32 tests nuevos de `reglas_plantillas.py` con la lógica de edad
- ✅ Tests viejos de `plantillas.py` actualizados al nuevo flujo

## Lo que está PENDIENTE (en orden de prioridad)

1. **🔴 Conectar fecha de nacimiento al flujo de plantillas**: el
   sistema ya acepta `edad_meses`, pero `extraer_datos_fila` no
   trae la fecha de nacimiento del paciente de Rayen. Falta:
   - Identificar dónde está en el DOM de Rayen
   - Calcular edad en meses
   - Pasar a `cargar_plantilla`
   - Tiempo: sesión con Rayen abierto, ~30 min
2. **🟡 Run del año 2025** (`python -m src.analysis.rescatar_anio_2025`):
   20-40 min, llena 2025 para comparación interanual.
3. **🟡 Cron real en mini PC Ubuntu** para `actualizar_mes_actual.py`
   (uso diario, 2-3 min, pensado para producción).
4. **🟡 Análisis estadísticos sobre la DB completa** (queries de
   comparación, estacionalidad, ranking de tipos difíciles).
5. **🟡 Agregar `cita_id` real a `PacienteIniciado`** para dedup más
   robusto. El `proxy_id` actual (hash de hora+tipo+adjunto+razón)
   funciona porque Yadira no reagenda, pero no es estable si cambia
   algún campo.
6. **🔴 Submit real a Rayen** — `enviar_ficha` levanta
   `NotImplementedError` en el submit real. Necesita sesión con
   UI de Rayen abierta.
7. **🟡 Capturar telegram sender_id de Yadira** — necesario para
   formalizar la validación de identidad.
8. **🟡 Debug del bot Pilotabot que no responde** — el bot aparece
   bonded en Mavis Mobile pero no reacciona a `/start` ni a mensajes.
9. **🟢 UI visual "Sala del CESFAM"** (HTML+CSS+JS + polling contra
   `data/analysis/tracking.db`).
10. **🟢 Crear los 7 gatos restantes** (Pelusa, Anita, los 5 del novio).

## Comandos útiles

```powershell
cd C:\Workspace\Login-Automation
$env:PYTHONIOENCODING="utf-8"

# Tests
C:\Workspace\Login-Automation\venv\Scripts\python.exe -m pytest    # 141 tests

# Análisis: tracking y DBs
python -m src.analysis.fichas_hoy                              # live check del dia
python -m src.analysis.tracking_diario                          # tracking con --historico, --desde, --hasta
python -m src.analysis.tracking_completo --historico            # agregados del año
python -m src.analysis.fichas_completo_db --historico           # DB completa del año
python -m src.analysis.actualizar_mes_actual                    # refresca el mes en curso
python -m src.analysis.rescatar_anio_2025                       # completa 2025
python -m src.analysis.listar_fichas_hoy                        # todas las fichas de hoy
python -m src.analysis.listar_fichas_abiertas                   # solo "Iniciado" + tracking
python -m src.analysis.fichas_abiertas_historico                # analisis desde raw_responses/
python -m src.analysis.debug_flujo                              # debug del flujo UI

# Reporte diario (anita)
python -m src.anita.cron_runner --db data/queue.db --formato telegram

# Agentes Mavis
mavis agent list

# Invocar a Gustavo (rol analitica)
# Decirme: "actua como Gustavo y dame el informe del dia"
```

## DBs y archivos de análisis

| Archivo | Tamaño | Qué tiene |
|---|---|---|
| `data/analysis/fichas_completo.db` | 20+ KB | TODAS las fichas con TODOS los campos. 2025 + 2026 |
| `data/analysis/tracking.db` | 16 KB | Tracking de "Iniciado" con upsert + cierres |
| `data/analysis/tracking_completo.db` | 20 KB | Agregados por día de todos los estados |
| `data/analysis/fichas_abiertas_historico.csv` | 2.8 KB | Análisis desde raw_responses |
| `data/analysis/*.txt` | varios | Outputs de las corridas |

**Para inspeccionar**: usar DB Browser for SQLite.

## Insights sobre los datos (al 24-07-2026)

**Total 2026 (147 días hábiles)**:
- 1774 fichas registradas en `fichas_completo.db`
- 82% Completado (1455)
- 13.5% Agendado (239)
- 1.4% Pendiente (25)
- **0.8% Iniciado (14) — la deuda clínica**
- 0.2% No se Presentó (3)

**Tipo de atención que más se le acumula a Yadira**:
- Control Integral ECICEP-G3: 30.8% de las "Iniciado"
- Control Integral ECICEP-G2: 23.1%
- Morbilidad (telefónica + presencial): 30.8%

**Las fichas no se "arrastran" entre días en Rayen**: el listado de
"Iniciado" de un día muestra solo las creadas/pendientes ese día. Por
eso el tracking acumulativo (recorrer día por día) es necesario para
medir backlog.

## Memoria del usuario

Archivo: `C:\Users\morti\.minimax\memory\user.md`. Contiene:
- Perfil de Miguel (ingeniero, magíster finanzas + ops/logística,
  esposo de Yadira)
- Perfil de Yadira (médica CESFAM Raúl Cuevas, San Bernardo;
  11 gatos)
- Los 11 gatos y sus roles (4 creados, 7 pendientes)
- Reglas duras del proyecto clínico
- Proyecto Login-Automation + estado
- Infra disponible (mini PC Ubuntu)

## Estilo de trabajo de Miguel

- Idioma: español de Chile, cálido pero profesional
- Le gusta discutir el approach antes de ejecutar (pero también
  "se soluciona hoy" cuando quiere avanzar)
- Valora las decisiones fundamentadas, no las opciones sin filtro
- Acepta "no sé, hay que investigar" si es honesto
- No le gusta el código que parece "enterprise" sin justificación
- Prefiere SQLite, scripts simples, dependencias mínimas
- **Le molesta que ofrezca "parar hasta mañana"** cuando él dice
  que se soluciona hoy. Asumir: él quiere avanzar, no postergar
- Le importa que cada ficha tenga `fecha_apertura` y `fecha_cierre`
  explícitas para análisis a futuro
- **Las reglas del proyecto se pueden cambiar** si él lo decide
  (ej. privacidad y LLMs cloud se levantaron el 24-07)

## Estado de los archivos de Yadira (datos sensibles)

⚠️ **`config/users.json` tiene password en plano en git history**.
Recomendado: rotar la password de Yadira en algún momento.

⚠️ **`config/api_config.json` tiene cookies reales** con
`.AspNet.Cookies`. Sesión activa hasta que Rayen las rote.

⚠️ **`data/raw_responses/` y `data/pacientes_2026.csv`** tienen
datos clínicos de pacientes. Ley 19.628 (Chile) — datos sensibles.

⚠️ **`data/analysis/*.db`** son nuevos. La DB `fichas_completo.db`
tiene nombres de pacientes (PII). `tracking.db` y `tracking_completo.db`
solo tienen agregados sin PII. **NO se commitean** (en `.gitignore`).

⚠️ **`data/analysis/*.txt`** (outputs de corridas) tienen nombres.
NO se commitean (en `.gitignore`).

Para la próxima sesión, no re-compartir estos datos en chat.

## Cómo retomar

1. Abrir nueva conversación con Mavis.
2. Pegar el prompt de retoma (ver más abajo).
3. Mavis lee este HANDOFF y entiende el contexto completo.
4. Decir "Continuamos desde donde quedamos. Próximo paso: [X]"
   donde X es uno de los pendientes priorizados.

---

**Última actualización**: 2026-07-25 01:17 GMT-4
**Commits hasta ahora**: 11 (3 de la semana + 8 de los últimos 2 días)
**Último commit**: `2441c04` — lógica de edad para "Control de niño sano"
**Tests**: 141 pasando
**Próximo paso sugerido**: conectar fecha de nacimiento al flujo de
plantillas (sesión con Rayen abierto, ~30 min)
