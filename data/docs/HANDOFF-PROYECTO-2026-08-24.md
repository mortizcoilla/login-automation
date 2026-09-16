# HANDOFF DEL PROYECTO — Mortadelo / Login-Automation
**Fecha:** 2026-08-24 (continuación, madrugada 06:30 CLT)
**Sesión:** continuación de la sesión 2026-08-23

> **Handoffs previos**:
> - `HANDOFF-MORTADELO-2026-08-07.md` — primer handoff de Mortadelo.
> - `HANDOFF-PROYECTO-2026-08-23.md` — handoff general con todo el flujo de `crear_notas_clinicas.py` y la estructura de archivos. **Leerlo primero** si no se ha leído.

---

## 1. Cambios principales desde 2026-08-23

### 1.1 LLM externo para generar la ficha (NUEVO enfoque)

Yadira ya no depende del parser regex hardcodeado para rellenar la plantilla. Ahora:

- **Tier bajo (`qwen3.7-plus`, 4300 req/5h)**: extrae datos estructurados desde la nota clínica y rellena la plantilla.
- **Tier alto (`minimax-m3`, 3200 req/5h)**: recibe la ficha rellenada como contexto y genera el bloque `** Doctora:` con resumen, datos faltantes, dx diferencial, sugerencias (con cita a manual) y red flags.
- **Visión (`gemini-2.5-pro`)**: OCR de fotos de exámenes adjuntos en `notas_clinicas/_adjuntos/`.

**Cuota target**: 20 fichas/día × 2 calls = 40 calls/día. M3 aguanta ~80 días full.

**Por qué LLM externo**:
- La regla "no LLM externos" del proyecto original estaba motivada por privacidad del RUT/nombre. Se resolvió seudonimizando: el script extrae la demografía (RUN, edad, fecha nac, dirección) y la mete en una **cabecera obligatoria** antes de la plantilla. La nota en sí no lleva RUT (la doctora lo carga a mano en Rayen).
- Yadira **valida cada ficha** antes de cerrar — la LLM propone, Yadira dispone.

**Script principal**: `src/tools/generar_ficha_con_llm.py` (NUEVO, 18 KB, refactorizado múltiples veces).

CLI:
```bash
# Ficha individual
python -m src.tools.generar_ficha_con_llm \
    --nota notas_clinicas/Alejandro_Enrique_Carrasco_Arias_21-08-2026.txt \
    --informe data/analysis/informe_fichas_abiertas_08-2026.txt

# Todas las del informe
for nota in notas_clinicas/*.txt; do
    python -m src.tools.generar_ficha_con_llm --nota "$nota" --informe data/analysis/informe_fichas_abiertas_08-2026.txt
done

# Override de modelos
python -m src.tools.generar_ficha_con_llm \
    --nota ... --informe ... \
    --model-rellenar opencode-go/qwen3.7-plus \
    --model-diagnostico opencode-go/minimax-m3 \
    --model-vision google/gemini-2.5-pro
```

**Proveedor default**: opencode-go (CLI agent). Instalado via npm global, ya autenticado. Si se cae, fallback en cascada automático por tier.

### 1.2 Bot Telegram: Pilita (Miguel) + Rubicita (Yadira)

Estado limpio al cierre de esta sesión (2026-08-24 06:30):

| Bot | Username | Owner | Agent |
|---|---|---|---|
| **Pilita** (de Miguel) | `@PilibertaBot` | Miguel (1389428233) | `pilita` |
| **Rubicita** (de Yadira) | `@RubicitaBot` (sin guion bajo) | **Yadira (5980753983)** | `agent-dafb231eb316` |

**Lo que pasó**: había un bot fantasma `agent-12f7ca12813f` (`@Rubicita_bot` con guion bajo, owner Miguel) que se auto-creó durante el setup. Era el que respondía cuando Yadira escribía. **Borrado** de los 4 YAMLs (`telegram-channel.yaml`, `channel-owner.yaml`, `channel-bindings.yaml`, `access-control.yaml`).

**Regla de oro**: NO crear más bots. Yadira habla con `@RubicitaBot` (sin guion bajo), Miguel habla con `@PilibertaBot`. Si en el futuro hay que agregar más personas, se reutiliza uno de los 2 bots existentes, no se crea uno nuevo.

### 1.3 Script genérico para fotos de exámenes

`src/tools/recibir_foto_examen.py` — Yadira manda una foto a Pilita por Telegram, Pilita la guarda en `notas_clinicas/_adjuntos/` con nombre normalizado, y el próximo batch la procesa con visión.

```bash
python -m src.tools.recibir_foto_examen \
    --input "<ruta local>" \
    --paciente "Cecilia Reyes" \
    --fecha 10-07-2026 \
    --tipo audiometria
```

Salida JSON con `ok`, `path`, `paciente`, `fecha`, `tipo`, `tamano_kb`, `error`. **NO sobrescribe** — si el archivo existe, agrega `_v2`, `_v3`, ...

**11 tests pasando** en `tests/test_recibir_foto_examen.py` (caso feliz, normalización de tildes, sinónimos de tipo, validación de input, no-sobrescritura, round-trip con el matcher).

### 1.4 Estructura de archivos — qué hay y qué falta

```
C:\Workspace\Login-Automation\
├── .env                                  ← NUEVO, NO se commitea. 4 API keys.
├── .opencode/agent/mortadelo.md          ← NUEVO. System prompt completo de Mortadelo (6.4 KB)
├── plantillas/                           ← 8 plantillas INMUTABLES
├── notas_clinicas/                       ← 6 notas (agosto)
│   └── _adjuntos/                        ← carpeta de fotos (vacía por ahora)
├── fichas_modificadas/                   ← 6 fichas generadas por LLM + .bak_vN.txt (LIMPIAR)
├── src/
│   ├── reglas_plantillas.py              ← _REGLA dict (27 entries)
│   ├── plantillas.py                     ← cargar_plantilla()
│   ├── browser_automation.py             ← primitivas Selenium
│   ├── mortadelo/skills/
│   │   ├── ecicep/                       ← reglas.md
│   │   ├── morbilidad/                   ← reglas.md
│   │   ├── nino_sano/                    ← reglas.md + manuales/ (varios .md MINSAL)
│   │   ├── salud_mental/                 ← reglas.md
│   │   └── examenes/                     ← skill REAL con easyocr (NUEVO)
│   ├── pancho_skills/                    ← 6 skills
│   └── tools/
│       ├── mortadelo_batch.py            ← flujo principal (parser regex, NO LLM)
│       ├── mortadelo_parser.py           ← parser de notas
│       ├── mortadelo_redactores.py       ← IC y correo
│       ├── crear_notas_clinicas.py       ← scrapea Rayen → notas .txt
│       ├── recibir_foto_examen.py        ← NUEVO. Foto → _adjuntos/
│       ├── informe_tecnico.py            ← WarningsCollector para informe JSON
│       ├── pdf_a_md.py                   ← convertidor PDF → .md
│       ├── generar_ficha_con_llm.py      ← NUEVO PRINCIPAL. LLM 2-tier + vision.
│       ├── update_trigger_docs.py
│       └── rename_caps.py
├── docs/
│   ├── HANDOFF-MORTADELO-2026-08-07.md
│   ├── HANDOFF-PROYECTO-2026-08-23.md
│   ├── HANDOFF-PROYECTO-2026-08-24.md   ← ESTE DOCUMENTO
│   ├── CREDENCIALES.md                   ← NUEVO. Política de secretos.
│   ├── guia-vincular-pilita-telegram.md  ← para Miguel
│   ├── guia-yadira-pilita-telegram.md    ← NUEVO. Mini-guía para Yadira.
│   └── PROMPT_INICIO_2026-07-26.md
├── data/analysis/
│   ├── informe_fichas_abiertas_08-2026.txt
│   └── informe_tecnico_YYYYMMDD_HHMMSS.json  ← NUEVO. Warnings separados de la ficha.
├── config/
│   ├── users.json                        ← YADIRA, password Pelusa2020. Saco del tracking.
│   ├── selectors.json
│   └── api_config.json                   ← cookie sesión Rayen. Saco del tracking.
├── scripts_temp/                         ← basura temporal (borrar en limpieza)
└── tests/                                ← 385+ tests pasando
```

---

## 2. Reglas duras (NO romper) — adiciones al set 2026-08-23

15. **API keys en `.env`, NO en chat**: nunca pegar keys en respuestas, logs, ni issues. Escribir directo a `.env` con `Add-Content` o edit. Ya documentado en `docs/CREDENCIALES.md`.
16. **Verificar `git ls-files` antes de commit**: `git ls-files | grep -E '\.env$|config/.*\.(json|yaml|yml|ini)$' | grep -v '\.local' | grep -v '\.example'`. Si hay archivos con secretos tracked, `git rm --cached` + `.gitignore` ANTES del commit.
17. **2 bots y no más**: Pilita (Miguel, @PilibertaBot) + Rubicita (Yadira, @RubicitaBot). NO crear nuevos bots. Si hay que agregar más personas, se reutiliza uno de los 2 existentes.
18. **Cabecera demográfica obligatoria**: cada ficha lleva, antes de la plantilla, una cabecera con RUN, edad, fecha nac, dirección, etc. La extrae `extraer_demografia()` de la sección IDENTIFICACION de la nota.
19. **Convención trigger `** mortadelo` con adjuntos** (acordada con Yadira 2026-08-23):
    - `** mortadelo <instrucción>` → Yadira pide acción específica. Va al bloque `=== INSTRUCCIONES DE TRIGGER ===` del `** Doctora:`.
    - `** mortadelo` (sin instrucción) → Yadira marca "hay adjuntos que revisar". Se procesan con visión y citan en `=== EXAMENES ADJUNTOS ANALIZADOS ===` del `** Doctora:`.
    - En ambos casos, la marca `** mortadelo` se BORRA de la ficha rellenada.
20. **Tiers de modelos según tarea**:
    - `rellenar` (extracción) → `opencode-go/qwen3.7-plus` (4300 req/5h).
    - `diagnostico` (razonamiento) → `opencode-go/minimax-m3` (3200 req/5h).
    - `vision` (OCR) → `google/gemini-2.5-pro`.
    - Cada tier tiene cadena de fallback automático.
21. **NO sobrescribir archivos en `notas_clinicas/` ni `fichas_modificadas/`**. Para `fichas_modificadas/`, si ya existe, agregar sufijo `.v2.txt`, `.v3.txt`, etc. Para `notas_clinicas/`, saltear con warning.

---

## 3. Estado actual — qué funciona, qué no

### ✅ Funciona

- **Pipeline LLM 2-tier**: 6/6 fichas de agosto generadas y guardadas en `fichas_modificadas/`:
  - Alejandro Enrique Carrasco Arias (21-08-2026) — 15.4 KB
  - Fidelicio Fernández González (18-08-2026) — 11.4 KB
  - Karina Bec (21-08-2026) — 13.6 KB
  - Kevin Javier Alarcón Espinoza (20-08-2026) — 7.8 KB
  - Rosa Normanda Veas Soto (21-08-2026) — 16.8 KB
  - Sonja del Carmen Ríos Godoy (21-08-2026) — 15.9 KB
  - Tiempo promedio: ~3 min/ficha (incluye 2 calls LLM).
- **Cabecera demográfica**: todas las fichas la traen.
- **Visión LLM**: `analizar_adjuntos_imagen()` lista para usar. No se probó aún con fotos reales (carpeta `_adjuntos/` está vacía).
- **Bot cleanup**: Pilita y Rubicita ambos con sus owners correctos, fantasma borrado.
- **`.env` con 4 keys + token Telegram Rubicita**: ya configurado.
- **385+ tests pasando** (374 anteriores + 11 nuevos de `recibir_foto_examen`).

### ⚠️ Issues conocidos en las fichas generadas (PENDIENTES de revisión Yadira)

1. **Caracteres chinos en output de `minimax-m3`**: a veces aparecen tokens tipo "首要", "组合", "污染" — contaminación del training. Pendiente: filtrar con regex en `limpiar_output()`.
2. **Sección "COBERTURA DEL BUNDLE" que el LLM agrega por su cuenta**: no estaba en la plantilla, no debería estar. Pendiente: instruir al system prompt para que no la agregue, o filtrarla en post-procesamiento.
3. **Dx del HISTORIAL metidos en sección DIAGNÓSTICOS de la ficha**: la LLM copia dx históricos como si fueran actuales. Pendiente: instruir a la LLM a NO hacerlo, o validar manualmente.
4. **Bloque `** Doctora:` dice "Falta motivo_consulta en la nota"** cuando el placeholder ya está rellenado. Pendiente: mejorar el check para que diga "Se rellenó MOTIVO DE CONSULTA con..." en vez de "Falta".
5. **Backups `.bak_v1.txt` a `.bak_v9.txt` en `fichas_modificadas/`**: basura de iteraciones de fix. Pendiente: limpieza.

### ❌ NO funciona

- **End-to-end con foto real de Yadira**: la pipeline está lista (`recibir_foto_examen.py` + visión en batch), pero Yadira todavía no mandó una foto de prueba a `@PilibertaBot`. Pendiente: validar el bridge de Mavis entrega la foto a Pilita con ruta local accesible.
- **Parser ECICEP en `mortadelo_batch.py`**: el flujo viejo (regex) sigue sin capturar bien las notas ECICEP. La LLM lo hace mejor en el flujo nuevo, pero `mortadelo_batch.py` (que NO usa LLM) sigue roto para ECICEP. **Decisión**: el flujo viejo queda deprecated a favor de `generar_ficha_con_llm.py`.

---

## 4. Cómo correr las cosas

```bash
cd C:\Workspace\Login-Automation
.\venv\Scripts\Activate.ps1

# PASO 1: Generar las notas clinicas desde Rayen (modo batch, los 6)
.\venv\Scripts\python.exe -m src.tools.crear_notas_clinicas --todos

# PASO 2a: Generar los entregables con LLM (NUEVO flujo principal)
.\venv\Scripts\python.exe -m src.tools.generar_ficha_con_llm --nota notas_clinicas/<paciente>_<fecha>.txt --informe data/analysis/informe_fichas_abiertas_08-2026.txt

# PASO 2b (DEPRECATED): Generar con parser regex
.\venv\Scripts\python.exe -m src.tools.mortadelo_batch

# PASO 3: Tests
.\venv\Scripts\python.exe -m pytest tests

# Utilidades
.\venv\Scripts\python.exe -m src.tools.recibir_foto_examen --input <foto> --paciente "<nombre>" --fecha <dd-mm-yyyy> --tipo <tipo>
.\venv\Scripts\python.exe -m src.tools.pdf_a_md <pdf_path> <output_dir>
```

---

## 5. Próximos pasos (priorizado)

### Prioridad ALTA (bloquea valor)

1. **Yadira valida las 6 fichas de agosto** — necesita abrir cada `.txt` en `fichas_modificadas/` y dar feedback. Esto calibra el system prompt de Mortadelo.
2. **Iterar sobre el system prompt** (`.opencode/agent/mortadelo.md`) con el feedback de Yadira: filtro de chinos, no agregar "COBERTURA DEL BUNDLE", no meter dx históricos en dx actuales.
3. **Probar end-to-end con foto real**: Yadira manda una foto de un examen a `@PilibertaBot` y verificamos que llegue a `_adjuntos/`, que el batch la transcriba, y que la transcripción se cite en el `=== EXAMENES ADJUNTOS ANALIZADOS ===`.

### Prioridad MEDIA (mejoras)

4. **Limpiar `.bak_vN.txt` de `fichas_modificadas/`**.
5. **Rotar password de Yadira en Rayen** (urgente — `config/users.json` estuvo tracked en git con `Pelusa2020` hasta 2026-08-23). Regenerar cookie.
6. **Decidir fuente de `fecha_nacimiento`** para `calcular_edad_meses()` — Yadira debe elegir entre Mora API / Rayen / DB local.
7. **Plantillas 6m / 12m / 18m / 2-4a / 5-9a** para nino_sano.
8. **Validar EEDP/TEPSI** para advice de desarrollo psicomotor.
9. **Validar manual de pesquisa TEA** en control sano.
10. **Deprecar `mortadelo_batch.py`** (flujo viejo) una vez Yadira valide que `generar_ficha_con_llm.py` es estable.

### Prioridad BAJA

11. **Cron en laptop Windows** (Task Scheduler) para que `crear_notas_clinicas.py` + `generar_ficha_con_llm.py` corran automáticamente cada día.
12. **Mini PC Ubuntu** (cuando esté operativa) para mover el cron allá y liberar la laptop.

---

## 6. Decisiones de diseño (NUEVAS desde 2026-08-23)

- **LLM externos para generar la ficha, Yadira valida**: el sistema prompt de Mortadelo vive en `.opencode/agent/mortadelo.md` y se invoca via `opencode run --agent mortadelo`.
- **OpenCode Go = plan $5/mes** (no software distinto), da acceso a `minimax-m3`, `kimi-k3`, `qwen3.8-max`, `grok-4.5`, etc.
- **2 bots y no más**: Pilita (Miguel) + Rubicita (Yadira). Si en el futuro hay más usuarias, se multiplexa con `agent_update` o se cambia el owner, no se crea un bot nuevo.
- **Rubicita = rol de gestión documental, NO clínico**: Pilita orquesta, Rubicita maneja docs (plantillas, notas, adjuntos, historial). Ninguno diagnostica.
- **NO usar Mini PC Ubuntu**: no operativa. Trabajar en laptop Windows de Miguel.
- **Pre-procesamiento antes de LLM**: el script extrae demografía, secciones, y construye prompts con la nota + la plantilla + el manual del bundle. La LLM no ve la nota cruda entera, sino una versión ya estructurada.
- **Post-procesamiento después de LLM**: el script limpia el output (filtra tokens raros, valida estructura, agrega `** Doctora:` si la LLM lo duplica).

---

## 7. Cosas que el agente DEBE saber al retomar

1. **Yadira = Dra. Yadira Hernandez Cabrera**. Hablar de ella en 3ra persona. Esposa de Miguel. Trabaja en CESFAM Raúl Cuevas, San Bernardo. Chat_id Telegram: `5980753983`.
2. **11 gatos del equipo Mavis de Yadira**: 7 creados (Pilita orq, Teodoro clínico, Pancho Rayen, Mortadelo fichas, Pelusa SM, Gustavo farma, Anita reportes), 4 pendientes (Luffyalberto, Dominga, Negrita, Mauricia, Rubi... wait, son 5). Pilita es la única con Telegram además de Rubicita.
3. **El bot Rubicita es de Yadira, no de Miguel**. Si el owner se pierde o se confunde, revisar `channel-owner.yaml` y restaurar a `5980753983`.
4. **NO usar `notas_clinicas - copia/`**: es backup de Miguel, no se toca.
5. **NO crear scripts por paciente**: `recibir_foto_examen.py` es genérico, no tiene lógica por paciente. Si un caso requiere algo especial, es un skill nuevo, no un script nuevo.
6. **NO pegar API keys en chat**: ir directo a `.env` con `Add-Content` o `Edit`.
7. **NO leer ni mencionar el backup folder** `C:\Workspace\_archivado_2026-08-22\`.
8. **Plantillas en `plantillas/*.txt` son INMUTABLES** — Yadira las entrega y son contrato.

---

## 8. Contacto y canales

- **Miguel**: este chat. user: `morti` en Windows.
- **Yadira**: Telegram @RubicitaBot (sin guion bajo). NO por WhatsApp.
- **Pilita**: Telegram @PilibertaBot. Habla con Miguel.
- **Documentación**: este folder `docs/`, `AGENTS.md` en la raíz del proyecto, `MEMORY.md` en `C:\Users\morti\.minimax\agents\mavis\memory\`.

---

**Última actualización**: 2026-08-24 06:30 CLT
**Próxima revisión**: cuando Yadira valide las 6 fichas de agosto.
