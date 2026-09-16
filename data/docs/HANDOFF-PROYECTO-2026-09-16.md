# HANDOFF-PROYECTO-2026-09-16

Snapshot completo del proyecto Login-Automation al cierre de la sesión del
2026-09-16. Este es el documento de entrada para cualquier agente (humano
o IA) que abra el proyecto después de hoy.

---

## 1. Resumen ejecutivo (TL;DR)

- **Tests:** 588 passed, 16 failed (las 16 fallas son pre-existentes en
  el "a corregir" zone — ver §7).
- **Working tree:** Limpio. Único ruido: `manuales/`, `scripts_temp/`,
  `src/mortadelo/skills/{nino_sano,salud_mental}/manuales/` (carpetas
  pre-existentes sin commitear, no relacionadas con esta sesión).
- **Último commit:** `ae14ad6 feat(enriquecer): detectar requerimientos
  Yadira->Mortadelo (examenes/IC) en informe`.
- **Refactor mayor de la sesión:** consolidación de toda la data local
  bajo `data/` + nuevo flujo `recibir_foto_examen` con OCR + detección
  de triggers Yadira en el informe enriquecido.

---

## 2. Lo que se hizo esta sesión (orden cronológico)

### 2.1 Reglas duras del pipeline clínico

Commits sobre `src/tools/crear_notas_clinicas.py`:

- `f4222c9` **REGLA DURA Yadira**: `guardar_nota_clinica()` raises
  `ValueError` si `anamnesis.strip()` empty (anamnesis SIEMPRE existe).
- `7619ef1` Bloque Yadira = anamnesis CRUDA (no placeholder).
- `683427f` Respaldo de anamnesis a `data/anamnesis/<paciente>_<fecha>.md`.
- `c8ac690` Respaldo incluye motivo de atención (blockquote antes).
- `8ef7582` Motivo SIEMPRE existe (sin condicional que oculte bugs).
- `fa5d568` Validación post-write + re-fetch de bloques faltantes.
- `ce26d71` Cardinalidad 1-a-1 con informe de fichas abiertas.
- `417bc16` REINTENTAR extracción en vez de marker (3 retries).
- `5a1df59` + `496006c` Reverts de intentos previos (markers, overwrite).

### 2.2 Refactor `data/`

- `c703eed` Mover `manuales_md/`, `notas_clinicas/`, `fichas_clinicas/`,
  `docs/`, `anamnesis/`, `logs/`, `plantillas/` → `data/`. Actualizar
  rutas en ~10 scripts.
- `f070c14` Cleanup: borrar `demo_app.py`, `demo_reporte.py`. Mover
  `login_automation.log` → `data/logs/`.
- `8124b1c` Mover `COMANDOS.txt` → `data/docs/COMANDOS.txt`.
  Renumerar secciones (saca demos). Actualizar "Donde viven los datos".
- `b8c0568` Mover `test_parser_json.py` → `tests/` con formato pytest
  (5 tests).
- `215ed65` Unificar `requirements.txt` + `requirements-dev.txt` en
  `pyproject.toml` (PEP 621). CI pasa a `pip install -e .[dev]`.
- `81255d0` Crear `README.md` con instrucciones de instalación para PC
  nueva.

### 2.3 Nuevo: `data/adjuntos` y `data/examenes`

- `0e09e4a` Documentar `data/adjuntos/` y `data/examenes/` (futuro uso).
- `e33fe45` Refactor de `recibir_foto_examen.py`:
  - `DESTINO_DIR = data/adjuntos/` (era `data/notas_clinicas/_adjuntos/`).
  - Nuevo `EXAMENES_DIR = data/examenes/`.
  - `procesar_examen_con_ocr()` llama vision LLM (`google/gemini-2.5-pro`)
    via lazy import de `generar_ficha_con_llm.invocar_con_fallback`.
  - Naming: `<paciente>_<fecha>_<tipo>.md` con `_safe_filename` (mismo
    regex que `crear_notas_clinicas._safe_filename`).
  - Formato: frontmatter YAML + `## ` headers (canónico del proyecto).
  - Flag CLI `--no-ocr` para tests/backup-only.
- También actualizado `ADJUNTOS_DIR = data/adjuntos/` en
  `crear_notas_clinicas.py` (cache de Chrome queda como `_chrome_dl/`
  subdir).

### 2.4 Nuevo: requerimientos Yadira en informe enriquecido

- `ae14ad6` `enriquecer_informe.py` detecta keywords en el bloque
  `** mortadelo` de la nota:
  - `examenes adjuntos` → columna `Examenes adjuntos = si/no`
  - `crear interconsulta` → columna `Crear interconsulta = si/no`
- Parser ahora acepta 6 u 8 columnas (back-compat con informes viejos).
- Side fix: file path `.txt` → `.md` (notas son `.md` desde 2026-09-16).

---

## 3. Estado actual del repo

### 3.1 Branch y working tree

```
Branch: main
Working tree: LIMPIO (5 items sin trackear, todos pre-existentes)
```

### 3.2 Tests

```
588 passed, 16 failed
```

Las 16 fallas son pre-existentes en "a corregir" zone:
- `test_pcic_base.py` (8 tests del agente mortadelo)
- `test_estratificacion_ecicep.py` (6 tests)
- `test_motivo_consulta.py` (1 test)
- `test_nino_sano_mapping.py` (1 test)

NO las arreglo automáticamente — están testeando código que vive en
"a corregir" zone (`src/mortadelo/`, `src/tools/generar_ficha_con_llm.py`,
`.opencode/agent/`). Es probable que sean tests escritos en anticipación
de features que aún no se implementaron en el agente.

### 3.3 Estructura de `data/`

```
data/
├── adjuntos/                   ← inbox de fotos Yadira (vía Pilita/Telegram)
├── anamnesis/                  ← respaldo de anamnesis Yadira (vacío por ahora)
├── analysis/                   ← DBs (fichas_completo.db, tracking*.db) + informes
├── docs/                       ← COMANDOS.txt, HANDOFFs, guias
├── examenes/                   ← OCR'd digitalized exams (vacío por ahora)
├── fichas_clinicas/            ← output de Mortadelo (vacío)
├── logs/                       ← login_automation.log + screenshots/
├── manuales_md/                ← 41 manuales .md + index.json
├── mortadelo/                  ← bundles legacy (data local)
├── notas_clinicas/             ← 5 notas .md (placeholders panel_cargo=false)
├── Nueva carpeta/              ← VACÍA. Probablemente sobra (sugerencia: borrar)
├── plantillas/                 ← 9 plantillas INMUTABLES Yadira
├── prompts/                    ← prompts LLM
└── test_cases/                 ← fixtures de tests
```

---

## 4. Decisiones técnicas durables (memoria del proyecto)

### 4.1 Reglas duras del pipeline clínico

1. **Anamnesis SIEMPRE existe en Rayen.** Yadira es forzada a llenarla.
   `guardar_nota_clinica()` raises `ValueError` si viene vacía.
2. **Motivo de atención SIEMPRE existe.** Se escribe en el blockquote
   aunque venga vacío (señal visible de bug del extractor).
3. **NO sobrescribir a mano; validar post-write + re-fetch.**
   `validar_nota_clinica()` detecta bloques vacíos y los re-extrae
   desde Rayen (driver aún activo). NO skip-if-exists.
4. **Cardinalidad 1-a-1 con informe de fichas abiertas.** Cada paciente
   del informe = 1 archivo en `notas_clinicas/`.
5. **REINTENTAR extracción antes de skip.** 3 reintentos vía re-click en
   "Atención actual". Si agotó, skip silencioso (sin marker).
6. **NO escribir markers de "EXTRACCION FALLIDA".** El usuario rechazó
   esa estrategia (2026-09-16 14:50).

### 4.2 Reglas duras del formato

- **Markdown canónico:** YAML frontmatter + `## ` headers. Aplica a
  notas clínicas, manuales convertidos, y exámenes digitalizados.
- **Naming:** `<paciente>_<fecha>.md` para notas/anamnesis.
  `<paciente>_<fecha>_<tipo>.md` para exámenes (cuando hay varios tipos
  el mismo día).
- **Inbox naming** (distinto, para que matchee el matcher): lowercase, sin
  tildes, formato `<paciente>_<fecha>_<tipo>_<timestamp>.<ext>`.

### 4.3 Reglas duras de operación

- **Plantillas INMUTABLES** en contenido y orden (Yadira/Rayen).
- **Mortadelo NO decide:** dx final, tratamiento, cerrar ficha.
- **Privacidad:** RUT/nombre/observación NUNCA a cloud. Todo vive en
  `data/` (gitignored). `data/analysis/tracking*.db` es la única DB
  compartible (sin PII).
- **Cada sugerencia en `** Doctora:`** cita fuente: `manual, sección/pág`.
- **Trigger `** mortadelo`** se borra de la ficha rellenada (es trigger,
  no contenido).
- **NO crear scripts por paciente.** Datos específicos van en fixtures.

### 4.4 Zones (no se cambian sin aprobación)

**"Perfecto" zone** (libre para modificar):
- `src/browser_automation.py`
- `src/credentials.py`
- `src/discover_api.py`
- `src/extract_patients.py`
- `src/pancho_skills/`
- `src/analysis/*`
- `src/tools/crear_notas_clinicas.py`
- `src/tools/completar_yadira.py`
- `src/tools/convertir_*.py`
- `src/tools/limpiar_screenshots.py`
- `src/tools/recibir_foto_examen.py` (nuevo en esta sesión)

**"A corregir" zone** (NO modificar):
- `src/plantillas.py`
- `src/reglas_plantillas.py`
- `src/mortadelo/`
- `src/tools/generar_ficha_con_llm.py`
- `src/tools/mortadelo_*.py`
- `.opencode/agent/`
- `src/queue_store.py`

---

## 5. LLM providers (configurados en `.env`)

- `OPENCODE_GO_API_KEY` — opencode-go (default, recomendado)
- `MINIMAX_API_KEY` — minimax directo (no usado)
- `KIMI_API_KEY` — Kimi/Moonshot directo
- `GEMINI_API_KEY` — Google Gemini directo (vision tier)

| Tier       | Default                      | Cuota (5h) |
|------------|------------------------------|------------|
| `rellenar` | `opencode-go/qwen3.7-plus`   | 4.300      |
| `diagnostico` | `opencode-go/minimax-m3`  | 3.200      |
| `vision`   | `google/gemini-2.5-pro`      | (cuota aparte) |

Cadena de fallback por tier en `FALLBACK_POR_TIER` en
`src/tools/generar_ficha_con_llm.py`.

---

## 6. Flujo recomendado

### 6.1 Diario (cron)

```powershell
cd C:\Workspace\Login-Automation
.\venv\Scripts\Activate.ps1
python -m src.analysis.actualizar_mes_actual yadira
```

### 6.2 Cuando Yadira tiene backlog de fichas abiertas

```powershell
# 1. Informe del mes
python -m src.analysis.informe_fichas_abiertas

# 2. Crear notas clinicas para los pacientes del informe
python -m src.tools.crear_notas_clinicas --todos --user yadira

# 3. Enriquecer el informe con motivo, edad, requerimientos
python -m src.analysis.enriquecer_informe

# 4. Llenar fichas (manual o via Mortadelo)
python main.py --user yadira --date dd-mm-aaaa --no-input
```

### 6.3 Cuando Yadira sube examen por Telegram (Pilita)

```powershell
python -m src.tools.recibir_foto_examen `
  --input "C:/path/photo.jpg" `
  --paciente "Cecilia Reyes" `
  --fecha 10-07-2026 `
  --tipo audiometria
# -> guarda en data/adjuntos/cecilia_reyes_10-07-2026_audiometria_HHMMSS.jpg
# -> envia a vision LLM, guarda en data/examenes/Cecilia_Reyes_10-07-2026_audiometria.md
```

---

## 7. Pendientes / Next steps

### 7.1 Actualizar default en `generar_ficha_con_llm.py:2190`

Hay un path hardcoded que apunta al inbox viejo:

```python
# src/tools/generar_ficha_con_llm.py línea 2190
adjuntos_dir = ROOT / "data" / "notas_clinicas" / "_adjuntos"  # ❌ viejo
```

Debería ser:
```python
adjuntos_dir = ROOT / "data" / "adjuntos"  # ✅ nuevo
```

**Bloqueador:** `generar_ficha_con_llm.py` está en "a corregir" zone.
Requiere autorización explícita de Miguel para modificar.

### 7.2 Actualizar `data/docs/rubicita-conventions.md`

La convención documentada dice:
> "Solo en `notas_clinicas/_adjuntos/`. NO en `_chrome_dl/`."

Esto ya no es válido — el inbox ahora es `data/adjuntos/`.

### 7.3 Refinar regex de motivo/edad en `.md`

`MOTIVO_RE` y `EDAD_RE` en `enriquecer_informe.py` aceptan heurística
para `.md` (blockquote `> **Motivo de atencion:**`), pero solo parcial.
Las notas reales con contenido Yadira probablemente necesiten regex más
estrictas para evitar falsos positivos.

Bloqueador: hasta que Yadira vuelva a abrir fichas con Rayen estable,
no hay notas con contenido real para validar la regex.

### 7.4 Limpiar `data/Nueva carpeta/`

Carpeta vacía sin uso. Probablemente sobra — se puede borrar.

### 7.5 Resolver 16 tests pre-existentes fallando

Están en "a corregir" zone. No los arreglo automáticamente. Cuando se
toque `src/mortadelo/` o `src/tools/generar_ficha_con_llm.py`, hay que
revisar si los tests anticipan features no implementadas o si los tests
están desactualizados.

### 7.6 Verificar backup de anamnesis en pipeline real

`data/anamnesis/` está vacío. Se pobla cuando se ejecuta
`crear_notas_clinicas.py` con `--todos` y Rayen estable (panel_cargo=true).
La siguiente corrida real validará:
- Que el archivo se crea correctamente
- Que el motivo de atención está en el blockquote
- Que el formato del frontmatter es correcto

### 7.7 Verificar OCR en pipeline real

`data/examenes/` está vacío. Igual que §7.6, se pobla cuando Yadira
mande una foto real por Telegram. La primera corrida con imagen real
validará:
- Que `invocar_con_fallback(tier="vision", ...)` responde correctamente
- Que el `.md` generado tiene frontmatter + transcripción
- Que el flag `--no-ocr` funciona para tests

---

## 8. Comandos rápidos de referencia

```powershell
# Setup (una sola vez)
pip install -e .[dev]

# Validar todo
pytest

# Lint
ruff check src tests main.py

# Type-check
mypy src

# Smoke test
python main.py --list-users

# Backup de Yadira
git push origin main

# Limpiar screenshots
python -m src.tools.limpiar_screenshots
```

---

## 9. Memoria adicional

Ver `C:\Users\morti\.minimax\agents\mavis\memory\MEMORY.md` para memoria
de larga duración (reglas cross-session, lecciones aprendidas,
infraestructura, etc.).

Última actualización: 2026-09-16 17:10 CLT.