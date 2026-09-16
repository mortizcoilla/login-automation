# Handoff Proyecto Login-Automation — 2026-09-15

**Para**: Miguel (desarrollador) y cualquier agente que entre al workspace.
**Workspace**: `C:\Workspace\Login-Automation\`
**Yadira**: doctora en CESFAM Raúl Cuevas (San Bernardo). Dueña del flujo clínico.
**Mortadelo**: agente Asistente de Yadira. NO decide clínicamente — solo rellena plantillas y deja advice.

---

## 1. Estado actual (15-09-2026)

### ✅ Funcional y verificado

- **Pipeline mensual** end-to-end funciona conceptualmente (todos los scripts compilan, los parsers sincronizados, el formato del informe es consistente).
- **Aislamiento mensual vs anual** garantizado en código y disco (ver `docs/HANDOFF-PROYECTO-2026-09-09.md` no, este es nuevo — ver sección 4).
- **Plantillas (9)**: `MORBILIDAD`, `INGRESO ECICEP`, `INGRESO SALUD MENTAL SIN ECICEP`, `CONTROL NIÑO SANO 1 MES`, `CONTROL NIÑO SANO 3 MESES`, `CONTROL INTEGRAL SIN FICHA ANTERIOR`, `RECETA`, `NO APLICA`, `EPICRISIS` (nueva).
- **Bundles** en `src/mortadelo/skills/`: `morbilidad`, `ecicep`, `salud_mental`, `nino_sano`, `examenes`.
- **Informe del mes** (`data/analysis/informe_fichas_abiertas_09-2026.txt`): 9 pacientes, actualizado al 10-09-2026.

### ⚠️ Bloqueante ahora mismo

- **`notas_clinicas/` está VACÍO**. El último intento de re-run del batch (10-09-2026) no produjo notas por un bug en el parser (ver §4). Las notas del 28-08 también desaparecieron (limpieza manual o por algún paso). Necesita re-correr `crear_notas_clinicas --todos` con el parser ya arreglado.
- **`fichas_clinicas/` sin septiembre**. Sin notas no hay fichas.

### 🔧 Pendiente (no bloqueante, segunda iteración)

- Wire de `Edad` y `Motivo` en el prompt del LLM (`generar_ficha_con_llm.py`).
- Screenshot on extraction failure (para diagnóstico rápido).
- Auto-retry si la nota existente es placeholder (`(no se pudo extraer...)`).

---

## 2. Pipeline actual (5 pasos)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. actualizar_mes_actual yadira                                │
│    Login Rayen, escanea días hábiles del mes en curso,          │
│    borra y reinserta registros de septiembre en fichas.db       │
│    Tiempo: 2-3 min                                              │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. informe_fichas_abiertas                                     │
│    Lee la DB, filtra estado='Iniciado' del mes en curso,        │
│    escribe data/analysis/informe_fichas_abiertas_<MM-YYYY>.txt  │
│    Tiempo: <1 seg                                               │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. crear_notas_clinicas --todos                                 │
│    Lee el informe del mes, para cada paciente abre su ficha     │
│    en Rayen, extrae identificación + nota de Yadira,             │
│    guarda notas_clinicas/<Nombre>_<dd-mm-yyyy>.txt             │
│    Tiempo: 20-45 min para 9 pacientes                           │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. enriquecer_informe                                          │
│    Lee las notas en notas_clinicas/, extrae                     │
│      - 'Motivo de atencion:' del bloque === INICIO NOTA CLINICA DE YADIRA ===
│      - 'Edad Cronológica:' del bloque === INICIO IDENTIFICACION ===
│    Reescribe el informe del mes con columnas Edad y Motivo.     │
│    Tiempo: <1 seg                                               │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. generar_ficha_con_llm                                       │
│    Por cada nota, invoca el agente Mortadelo con opencode,      │
│    rellena la plantilla correspondiente, guarda en               │
│    fichas_clinicas/<Nombre>_<dd-mm-yyyy>.txt                   │
│    Tiempo: 30-50 min para 9 fichas                              │
└─────────────────────────────────────────────────────────────────┘
```

**Comando único** (después del 10-09-2026 fix):
```powershell
python -m src.analysis.actualizar_mes_actual yadira ; `
python -m src.analysis.informe_fichas_abiertas ; `
python -m src.tools.crear_notas_clinicas --todos ; `
python -m src.analysis.enriquecer_informe ; `
python -m src.tools.generar_ficha_con_llm
```

> **Convención 2026-09-09**: mensual y anual son operaciones DISTINTAS. El anual (`informe_fichas_abiertas --todos`) escribe a `_completo.txt` y no toca el mensual. El mensual usa `informe_mes_actual_path()` por default. Si ves `_completo.txt` en un flujo mensual, algo está mal.

---

## 3. Orden de columnas del informe (sesión 2026-09-09)

```
Fecha | Nombre | Edad | Tipo de atencion | Motivo de la atencion | Plantilla
```

- **Sin** "Razon de la cita" (era metadata de Rayen sin valor clínico).
- **Edad** se llena desde `=== INICIO IDENTIFICACION ===` de la nota.
- **Motivo** se llena desde `=== INICIO NOTA CLINICA DE YADIRA ===` de la nota.
- Si un campo está vacío: `(-)`. Sin 24-espacios, sin heurística — siempre `(-)` para que el parser reciba siempre 6 partes.

---

## 4. Cambios recientes (sesión 2026-09-09 → 2026-09-15)

### Nuevo: `src/analysis/informe_paths.py`
Single source of truth para los paths de informes:
- `informe_mes_actual_path()` → `informe_fichas_abiertas_<MM-YYYY>.txt`
- `informe_anual_path()` → `informe_fichas_abiertas_<YYYY>_completo.txt`

Usado por los 3 scripts que tocan informes. Si cambia la convención de nombres, solo se toca acá.

### `src/analysis/informe_fichas_abiertas.py`
- Removida columna "Razon de la cita" del output (no aportaba).
- Agregada columna "Motivo de la atencion" (vacía hasta enricher).
- Banner explícito al ejecutar: `[modo MENSUAL/rango] archivo: X (el anual NO se toca)` o `[modo ANUAL] archivo: Y (el mensual NO se toca)`.
- **Guard de aislamiento**: si el archivo destino coincide con el del otro modo, aborta con error.
- Función `_es_modo_anual()` decide explícitamente el modo (no heurística).
- SQL ya no lee `razon` de la DB.

### `src/tools/crear_notas_clinicas.py`
- `INFORME_DEFAULT` ya no hardcoded a `08-2026.txt`. Computa el path del mes en curso via `informe_mes_actual_path()`.
- `--informe` default = mes en curso (antes: hardcoded 08-2026).
- **Guard**: rechaza `--informe` apuntando al anual con mensaje REFUSADO claro.
- **Parser migrado a `re.split`** (2026-09-15): el regex anclado viejo `[A-Za-z]` rompía con la nueva columna Edad (backtracking metía `(-)` en el nombre → Rayen no encontraba pacientes → 0 notas). Ahora maneja 4/5/6 columnas según el formato.
- **Timeout del doble-click 15s → 30s + retry automático** (2026-09-09): si el panel del paciente no carga en 30s, espera 3s y vuelve a hacer doble-click. Caso Ana Patricia: panel tardaba >15s en cargar, con 30s se cubre.

### `src/tools/generar_ficha_con_llm.py`
- `procesar_nota()` ahora recibe `informe_path: Optional[Path]`.
- Fallback del lookup de `tipo_atencion` (cuando la nota no lo trae) usa `informe_path or informe_mes_actual_path()` — antes era `informe_fichas_abiertas_08-2026.txt` hardcoded.
- Threading: `--informe` se pasa a `procesar_nota()` por cada paciente.

### Nuevo: `src/analysis/enriquecer_informe.py`
- Lee el informe del mes (default via `informe_mes_actual_path()`).
- Por cada paciente busca la nota en `notas_clinicas/`.
- Extrae `Motivo de atencion:` del bloque Yadira y `Edad Cronológica:` del bloque Identificación.
- Reescribe el informe con las columnas Edad y Motivo pobladas, o `(-)` si falta.
- Guard: rechaza el anual con error claro.
- Parser robusto (exige 6 partes).

### `src/tools/mortadelo_batch.py` (deprecated, no se corre desde 2026-08-24)
- Comentario explícito en la constante `INFORME = ..._completo.txt`: este script lee del ANUAL. Intencional, no se toca.

---

## 5. Issues conocidos

### Resueltos recientemente
- ~~Bug del parser con columna Edad (regression)~~ — fixed 2026-09-15.
- ~~`parsear_informe` rompía con informe enriquecido (incluía `(-)` en el nombre)~~ — fixed 2026-09-15.
- ~~Doble-click 15s era muy corto para fichas pesadas (caso Ana Patricia)~~ — fixed 2026-09-09.
- ~~Hardcoded `08-2026` en defaults de los 3 scripts~~ — fixed 2026-09-09.
- ~~Falta de aislamiento mensual vs anual~~ — fixed 2026-09-09.

### Pendientes (no bloqueantes)
- **Wire de Edad/Motivo al LLM**: el parser de `generar_ficha_con_llm.py` solo lee `parts[0]` y `parts[1]` (fecha, nombre). Edad y Motivo ya están en el informe pero no se pasan al prompt del agente Mortadelo. Sin urgencia — el enrichment ya persistió los datos.
- **Screenshot on extraction failure**: si `extraer_identificacion()` devuelve `{}`, no hay evidencia visual de qué pasó. Útil para futuros casos como Ana Patricia.
- **Auto-retry de placeholder**: si la nota guardada tiene solo `(no se pudo extraer...)`, re-intentar automáticamente en el siguiente batch.

### De baja prioridad
- La página de pacientes citados muestra 26 pacientes/día pero solo 9 Iniciado (sesión 2026-09-09). El sort por Estado debería mostrar los Iniciado arriba pero la búsqueda con `Iniciado` no los encuentra. **Workaround actual**: el informe se basa en la DB local (que sí los tiene), no en el sort de Rayen. Funcional, pero podría optimizarse.

---

## 6. Privacidad y git

- `data/analysis/` está en `.gitignore` — DB y reportes tienen PII (nombres).
- `notas_clinicas/` está en `.gitignore` — notas clínicas completas.
- `.env` está en `.gitignore` — credenciales.
- API keys viven en `.env` (ver `docs/CREDENCIALES.md`).

---

## 7. Comandos útiles

```powershell
# Activar venv (PS 7+)
cd C:\Workspace\Login-Automation
.\venv\Scripts\Activate.ps1

# Forzar UTF-8 en consola
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'

# Ver informe del mes en consola
python -m src.analysis.informe_fichas_abiertas

# Ver informe anual (operación distinta, archivo separado)
python -m src.analysis.informe_fichas_abiertas --todos

# Enriquecer el informe del mes con Edad y Motivo
python -m src.analysis.enriquecer_informe

# Re-correr un paciente específico (modo 1-paciente)
python -m src.tools.crear_notas_clinicas --paciente "Nombre Apellido" --fecha 04-09-2026

# Re-correr batch completo del mes
python -m src.tools.crear_notas_clinicas --todos

# Dry-run del LLM (construye prompt pero NO invoca opencode)
python -m src.tools.generar_ficha_con_llm --dry-run --save-prompt data/prompts/

# LLM paso 4 (default: informe del mes en curso)
python -m src.tools.generar_ficha_con_llm
```

---

## 8. Archivos clave

```
src/analysis/
  informe_fichas_abiertas.py   ← paso 2, genera el informe básico
  informe_paths.py             ← single source of truth para paths
  enriquecer_informe.py        ← paso 4, extrae Edad y Motivo

src/tools/
  crear_notas_clinicas.py      ← paso 3, login + extracción
  generar_ficha_con_llm.py     ← paso 5, LLM con opencode
  mortadelo_batch.py           ← DEPRECATED, no se corre

src/mortadelo/skills/          ← bundles por tipo (morbilidad, ecicep, etc.)
src/pancho_skills/             ← login y navegación Rayen
plantillas/                    ← 9 plantillas inmutables

data/analysis/                  ← DB + informes (gitignored)
notas_clinicas/                 ← notas extraídas (gitignored)
fichas_clinicas/                ← fichas rellenadas por LLM (gitignored)
docs/                           ← handoffs y guías
```

---

## 9. Próximo paso inmediato

**Re-correr los pasos 3 y 4** para tener notas y enriquecer el informe:

```powershell
python -m src.tools.crear_notas_clinicas --todos
python -m src.analysis.enriquecer_informe
```

Tiempo estimado: 20-50 min para los 9 pacientes de septiembre. Cuando estén las notas, `generar_ficha_con_llm` puede correr para tener las 8 fichas rellenadas (Samuel Melo — `Gestion administrativa` — quedará sin ficha, como Carolina Pino en agosto).
