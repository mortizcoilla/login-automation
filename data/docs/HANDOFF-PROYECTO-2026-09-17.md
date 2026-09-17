# HANDOFF-PROYECTO-2026-09-17

Snapshot completo del proyecto Login-Automation al cierre de la sesión del
2026-09-17. Reemplaza al `HANDOFF-PROYECTO-2026-09-16.md` (snapshot
anterior).

---

## 1. Resumen ejecutivo (TL;DR)

- **Tests:** 629 passed, 16 failed (las 16 fallas son pre-existentes en
  el "a corregir" zone — ver §7).
- **Working tree:** Working copy limpio. Hay archivos untracked (ver §9).
- **Último commit:** `256ac5d docs: documentar prefijos anam_ e info_ en filenames`.
- **Refactor mayor de la sesión:** renombrar archivos generados con
  prefijos `anam_` (anamnesis) e `info_` (info paciente) para distinguir
  los 3 docs que produce `crear_notas_clinicas --todos`.

---

## 2. Lo que se hizo esta sesión (orden cronológico)

### 2.1 Simplificación del informe enriquecido

Commits sobre `src/analysis/enriquecer_informe.py`:

- `251fab1` **Sesión 17:35**: drop verbose Edad. Solo se muestra el
  decimal en el informe (`19,19`). El parser ya no lee Edad del
  informe — siempre la re-deriva de la nota (más confiable).
- `d41705f` **Sesión 17:26**: agregar columna `Edad (decimal)` con
  conversion `1 año = 12 meses = 365.25 días` (año juliano). Helper
  `_edad_a_decimal()` con regex tolerante a tildes/OCR.
- `b333c9b` **Sesión 17:00**: fix crítico. Las regex de motivo/edad
  buscaban en bloques delimitados por `=== INICIO ===` (formato .txt
  legacy), pero las notas son .md. Cambio a búsqueda whole-file
  format-agnostic. Helper `_limpiar_valor_campo()` que strip `**`
  anidados del valor.
- `ae14ad6` **Sesión 16:30**: detectar requerimientos Yadira→Mortadelo
  en el bloque `** mortadelo` de la anamnesis. Nuevas columnas
  `Examenes adjuntos` (si/no) y `Crear interconsulta` (si/no).

### 2.2 Nuevo: info_paciente (sesión 17:45)

Commit `6698351 feat(crear_notas_clinicas): info_paciente complementario
(sin anamnesis)`:

- Nueva carpeta `data/info_paciente/` con doc complementario a la
  nota clínica. Contiene TODO lo del paciente MENOS la anamnesis.
- Nueva función `guardar_info_paciente()` en
  `src/tools/crear_notas_clinicas.py`, llamada automáticamente en
  el main loop después de `guardar_nota_clinica()`.
- Frontmatter `tipo_documento: "info_paciente (sin anamnesis)"`.

Commit `cabde18` **Sesión 17:55**: eliminar la sección `## Notas`
que documentaba la relación con los otros docs (Yadira pidió borrarla).

### 2.3 Naming con prefijos (sesión 18:45)

Commit `41fe3a8 feat(crear_notas): prefijos anam_ e info_ en filenames`:

- `guardar_respaldo_anamnesis()`: nombre ahora `anam_<safe>_<fecha>.md`
- `guardar_info_paciente()`: nombre ahora `info_<safe>_<fecha>.md`
- `guardar_nota_clinica()`: nombre sigue `<safe>_<fecha>.md` (sin cambios)

Commit `256ac5d docs`: README + COMANDOS actualizados con el nuevo naming.

### 2.4 Estado de features de la sesión anterior (sin cambios)

- `data/adjuntos/` y `data/examenes/` con OCR — sigue igual, aún no
  se ha probado con imagenes reales.
- `enriquecer_informe.py` con detección de triggers Yadira — funciona.
- `data/Nueva carpeta/` (vacía, no documentada) — sigue ahí, sin uso.

---

## 3. Estado actual del repo

### 3.1 Branch y working tree

```
Branch: main
Working copy: LIMPIO (archivos tracked)
```

### 3.2 Tests

```
629 passed, 16 failed
```

Las 16 fallas son pre-existentes en "a corregir" zone — sin cambios
respecto al handoff anterior.

### 3.3 Estructura de `data/` (versión 2026-09-17)

```
data/
├── adjuntos/                   ← inbox de fotos Yadira (vía Pilita/Telegram)
├── anamnesis/                  ← respaldo de anamnesis Yadira (vacío)
├── analysis/                   ← DBs (fichas_completo.db, tracking*.db) + informes
├── chunks/                     ← NUEVO — chunks de manuales_md (otro agente)
├── docs/                       ← COMANDOS.txt, HANDOFFs, guias
├── examenes/                   ← OCR'd digitalized exams (vacío)
├── fichas_clinicas/            ← output de Mortadelo (vacío)
├── info_paciente/              ← TODO lo del paciente MENOS la anamnesis (vacío)
├── logs/                       ← login_automation.log + screenshots/
├── manuales_md/                ← 41 manuales .md + index.json
├── mortadelo/                  ← bundles legacy (data local)
├── notas_clinicas/             ← 5 notas .md (placeholders panel_cargo=false)
├── plantillas/                 ← 9 plantillas INMUTABLES Yadira
├── prompts/                    ← prompts LLM
└── test_cases/                 ← fixtures de tests
```

### 3.4 Naming convention (sesión 18:45)

Para cada paciente, el pipeline genera 3 archivos:

| Tipo | Ubicación | Naming |
|------|-----------|--------|
| Nota clínica (completa) | `data/notas_clinicas/` | `<paciente>_<fecha>.md` |
| Respaldo de anamnesis | `data/anamnesis/` | `anam_<paciente>_<fecha>.md` |
| Info paciente (sin anamnesis) | `data/info_paciente/` | `info_<paciente>_<fecha>.md` |

Ejemplo para Nicolás Piña Rojas, 10-09-2026:
- `data/notas_clinicas/Nicolas_Ignacio_Piña_Rojas_10-09-2026.md`
- `data/anamnesis/anam_Nicolas_Ignacio_Piña_Rojas_10-09-2026.md`
- `data/info_paciente/info_Nicolas_Ignacio_Piña_Rojas_10-09-2026.md`

Yadira puede cruzar los 3 archivos por nombre (mismo `<paciente>_<fecha>`).

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

### 4.2 Reglas duras de formato

- **Markdown canónico:** YAML frontmatter + `## ` headers. Aplica a
  notas clínicas, manuales convertidos, exámenes digitalizados, e
  info_paciente.
- **Naming** (sesión 18:45):
  - Notas: `<paciente>_<fecha>.md`
  - Anamnesis: `anam_<paciente>_<fecha>.md`
  - Info paciente: `info_<paciente>_<fecha>.md`
  - Inbox (fotos Yadira): lowercase, sin tildes, formato
    `<paciente>_<fecha>_<tipo>_<timestamp>.<ext>`.

### 4.3 Reglas duras del informe enriquecido

- **Edad siempre decimal** (sesión 17:35). NO se muestra formato
  verbose "X años Y meses Z días". SIEMPRE se re-deriva de la nota.
- **Conversión:** `1 año = 12 meses = 365.25 días` (año juliano).
- **Requermientos Yadira→Mortadelo** se trackean como si/no en el
  informe (keywords `examenes adjuntos`, `crear interconsulta`).

### 4.4 Reglas duras de operación

- **Plantillas INMUTABLES** en contenido y orden (Yadira/Rayen).
- **Mortadelo NO decide:** dx final, tratamiento, cerrar ficha.
- **Privacidad:** RUT/nombre/observación NUNCA a cloud. Todo vive en
  `data/` (gitignored). `data/analysis/tracking*.db` es la única DB
  compartible (sin PII).
- **Cada sugerencia en `** Doctora:`** cita fuente: `manual, sección/pág`.
- **Trigger `** mortadelo`** se borra de la ficha rellenada (es trigger,
  no contenido).
- **NO crear scripts por paciente.** Datos específicos van en fixtures.

### 4.5 Zones (no se cambian sin aprobación)

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
- `src/tools/recibir_foto_examen.py`

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
#    Genera 3 archivos por paciente:
#    - data/notas_clinicas/<paciente>_<fecha>.md
#    - data/anamnesis/anam_<paciente>_<fecha>.md
#    - data/info_paciente/info_<paciente>_<fecha>.md
python -m src.tools.crear_notas_clinicas --todos --user yadira

# 3. Enriquecer el informe con motivo, edad (decimal), requerimientos
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

### 7.3 Resolver 16 tests pre-existentes fallando

Están en "a corregir" zone. No los arreglo automáticamente. Cuando se
toque `src/mortadelo/` o `src/tools/generar_ficha_con_llm.py`, hay que
revisar si los tests anticipan features no implementadas o si los tests
están desactualizados.

### 7.4 Verificar pipeline real con Rayen estable

Los 3 archivos por paciente (`notas_clinicas/`, `anamnesis/`, `info_paciente/`)
se generan vacíos hasta que Yadira abra fichas con Rayen estable. La
próxima corrida real validará:
- Naming con prefijos (`anam_`, `info_`)
- Que el motivo de atención se extrae correctamente del .md
- Que el formato del frontmatter de `info_paciente/` es correcto
- Que la columna decimal Edad funciona con datos reales

### 7.5 Verificar OCR en pipeline real

`data/examenes/` está vacío. Se pobla cuando Yadira mande una foto real
por Telegram.

### 7.6 Limpiar `data/Nueva carpeta/`

Carpeta vacía sin uso. Probablemente sobra — se puede borrar.

### 7.7 Revisar archivos untracked

Hay archivos en el working tree sin commitear (ver §9). Son de origen
mixto (algunos míos de diagnóstico, otros de otro agente externo).
Decidir qué commitear y qué borrar.

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

## 9. Working tree: archivos untracked

Esta sección lista archivos sin commitear. Decidir caso por caso.

### 9.1 Creados por esta sesión (míos, pueden borrarse)

- `scripts_temp/` — scripts ad-hoc de debug. Borrables.
- `src/tools/chunk_md.py`, `embed_chunks.py`, `resumir_chunks.py`,
  `cross_refs.py`, `ner.py`, `referencias.py`, `consultar.py`,
  `detectar_tablas.py`, `mejorar_md.py`, `limpiar.py`, `mavis_app.py` —
  algunos modificados, otros nuevos, **NO los commiteé**. Revisar origen
  antes de commitear.
- `data/chunks/`, `data/cross_refs.json`, `data/ner.json`,
  `data/referencias.json` — outputs de los scripts anteriores.
- `README_MAVIS.md`, `data/LLM_GUIDE.md` — parecen ser de otro agente.

### 9.2 Pre-existentes (de sesiones anteriores)

- `manuales/` — PDFs fuente de manuales clínicos (sin commitear).
- `src/mortadelo/skills/nino_sano/manuales/`,
  `src/mortadelo/skills/salud_mental/manuales/` — PDFs locales por bundle.

---

## 10. Memoria adicional

Ver `C:\Users\morti\.minimax\agents\mavis\memory\MEMORY.md` para memoria
de larga duración (reglas cross-session, lecciones aprendidas,
infraestructura, etc.).

Última actualización: 2026-09-17 01:13 CLT.