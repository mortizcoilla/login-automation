# HANDOFF DEL PROYECTO — Mortadelo / Login-Automation
**Fecha:** 2026-08-23 (sesion extendida madrugada, hasta ~04:45)
**Sesion:** continuacion de la sesion 7

---

## 1. Quien eres / quien soy

- **Miguel Ortiz Coilla** (`morti` en Windows). Ingeniero, regulacion electrica + finanzas. Dueno del producto.
- **Yo soy Mavis** (agent name local), corriendo dentro de MiniMax Code. En este proyecto represento a **Mortadelo**, el agente que rellena fichas clinicas para la **Dra. Yadira Hernandez Cabrera** (medica CESFAM Raul Cuevas, San Bernardo). **IMPORTANTE**: Yadira ES la doctora. Hablar de "Yadira y la doctora" como personas distintas es un error.

---

## 2. Que es el proyecto

**Mortadelo** es un agente que toma notas clinicas en espanol libre (escritas por Yadira en Rayen) y las usa para rellenar plantillas clinicas estandar, generando un "entregable" por ficha. NO decide clinicamente, NO crea plantillas, NO cierra fichas.

### Estructura del entregable de Mortadelo (validada por Yadira)

```
1) Plantilla rellenada con info de la nota clinica
2) =====================================================
3) === RESUMEN DE LO QUE SE HIZO ===            (que hizo Mortadelo en la ficha)
4) === DATOS QUE FALTAN ===                    (placeholder vacio en la nota)
5) === DIAGNOSTICO DIFERENCIAL ===              (lista de posibles dx con razon breve)
6) === RED FLAGS A VIGILAR ===                  (alertas criticas)
7) [Bloque de IC/correo si hay trigger]         (respuesta a instruccion de Yadira)
```

La mejora visual permitida en la ficha rellenada es SOLO la numeracion de MEDICAMENTOS cuando hay 2+ farmacos. NO se agregan lineas en blanco ni se reordenan secciones.

---

## 3. Estructura del codigo

```
C:\Workspace\Login-Automation\
├── notas_clinicas/                       ← 16 notas clinicas (.txt) generadas por crear_notas_clinicas
├── fichas_modificadas/                   ← 16 entregables generados por mortadelo_batch + informe
├── plantillas/                           ← 8 plantillas INMUTABLES (no tocar)
├── src/
│   ├── plantillas.py                     → cargar_plantilla(), calcular_edad_meses()
│   ├── reglas_plantillas.py              → _REGLA (dict tipo_atencion -> plantilla)
│   ├── analysis/
│   │   ├── informe_fichas_abiertas.py
│   │   └── listar_fichas_abiertas.py
│   ├── mortadelo/
│   │   ├── trigger.py                    → `** mortadelo` (case-insensitive, acepta coma)
│   │   ├── README.md
│   │   └── skills/
│   │       ├── ecicep/, morbilidad/, nino_sano/, salud_mental/, examenes/ (stub)
│   ├── pancho_skills/                    → 6 skills de Pancho (login, leer, listar, enviar, historial)
│   ├── browser_automation.py             → primitivas Selenium (run_login, select_date, etc.)
│   └── tools/
│       ├── mortadelo_batch.py            ← SCRIPT PRINCIPAL que genera los entregables
│       ├── mortadelo_parser.py           ← parser de notas (con bug para ECICEP)
│       ├── mortadelo_redactores.py       → IC y correo
│       ├── pdf_a_md.py                   → convertidor PDF → .md
│       ├── crear_notas_clinicas.py       ← SCRIPT NUEVO: scrapea Rayen y crea las notas clinicas
│       ├── update_trigger_docs.py
│       └── rename_caps.py
├── tests/                                → 374 tests pasando
├── docs/
│   ├── HANDOFF-MORTADELO-2026-08-07.md   ← handoff ANTERIOR
│   ├── HANDOFF-PROYECTO-2026-08-23.md   ← ESTE DOCUMENTO
│   ├── guia-vincular-pilita-telegram.md  ← como conectar Pilita a Telegram
│   └── PROMPT_INICIO_2026-07-26.md
├── data/analysis/
│   ├── informe_fichas_abiertas_2026_completo.txt   ← 22 fichas (todo el anio)
│   ├── informe_fichas_abiertas_08-2026.txt        ← 16 fichas (agosto 2026) ← USASTE ESTE
│   └── fichas_completo.db              ← DB local de fichas scrapeadas
├── config/
│   ├── users.json                       ← credenciales de Yadira
│   ├── selectors.json                   ← selectores CSS de la UI de Rayen
│   └── api_config.json
├── main.py                              ← entry point original (login + listado)
└── pyproject.toml                       ← deps (runtime + [dev]) + tool config (ruff/mypy/pytest)
```

---

## 4. Reglas duras (NO romper)

1. **Plantillas INMUTABLES**: `plantillas/*.txt` no se tocan jamas.
2. **Mortadelo JAMAS decide**: no diagnostica, no prescribe, no cierra fichas.
3. **NO crear scripts por paciente**: datos especificos van en fixtures; script siempre generico.
4. **Tipos de atencion y plantillas son LEY**: NO proponer cambios a `_REGLA` ni a `plantillas/`.
5. **NO insertar texto en medio/final de la plantilla** que no sea un placeholder.
6. **NO cambiar el orden de las secciones** de la plantilla.
7. **NO borrar lo que la doctora escribio** (excepto `** mortadelo` que es trigger).
8. **Sugerencias en `** Doctora:` DEBEN citar fuente**: `sugerencia → manual, seccion/pagina`.
9. **"no"/"niega"/"(-)"** son respuestas validas de Yadira, no campos faltantes.
10. **NO ofrecer cosas al final de una sesion exitosa**.
11. **Yadira es la doctora** — nunca hablar de ella en tercera persona al usuario.
12. **Mortadelo itera mucho sobre UI** — preguntar antes de cambios estructurales.
13. **NO usar `notas_clinicas - copia/`**: es respaldo de Miguel, no se toca.
14. **crear_notas_clinicas.py NO sobrescribe** archivos existentes en `notas_clinicas/`.

---

## 5. Estado actual — lo que funciona y lo que NO

### Funciona correctamente

- **Morbilidad** (8 fichas): parser captura APP, alergias, APQX, APF, motivo, farmacos, habitos, EF. Inyecta en plantilla. Numeracion de MEDICAMENTOS funciona. 374 tests pasan.
- **Salud mental** (1 ficha con trigger): funciona, IC se genera al final.
- **Estructura del entregable** (7 puntos): implementada tal cual Yadira la describio.
- **Trigger** `** mortadelo` (case-insensitive, acepta coma): funciona.
- **crear_notas_clinicas.py** (NUEVO, sesion madrugada 2026-08-23):
  - Login en Rayen + navegacion a Pacientes citados (pasos 1-3 via `run_login`)
  - Por cada paciente: filtrar fecha + buscar por nombre + doble click
  - Extrae: identificacion, historial, anamnesis, diagnosticos, actividades, profesionales, pautas
  - Guarda en `notas_clinicas/{nombre}_{fecha}.txt` con 7 bloques marcados
  - Modo batch (`--todos`): itera los 16 del informe 08-2026
  - Reset de sesion cada 8 fichas (limite de Rayen)
  - Cierra navegador automaticamente al final

### NO funciona — bugs pendientes

#### BUG 1: Parser para ECICEP no captura la mayoria de los campos (sigue pendiente)

**Sintoma:** Las 7 fichas ECICEP salen con la plantilla casi vacia en `fichas_modificadas/`.

**Causa:** El parser en `src/tools/mortadelo_parser.py` fue construido para notas de morbilidad. Reconoce "APP:", "ALERGIAS:", "MEDICAMENTOS:", "TBQ:", "OH:", "Drogas:" — pero las notas ECICEP usan OTROS nombres.

**Fix necesario:** Agregar regex ECICEP al parser, o crear un parser dual que detecte el tipo de nota.

#### BUG 2: Fidelicio y Yrma tienen "MEDICAMENTOS" con texto raro (sigue pendiente)

**Causa:** El parser captura cosas que NO son farmacos como farmacos.

---

## 6. Script nuevo: `crear_notas_clinicas.py`

Es el script que scrappea Rayen y genera las notas clinicas en `notas_clinicas/`. Convierte la informacion dispersa de la UI de Rayen en archivos `.txt` que luego `mortadelo_batch.py` procesa.

### Modos de uso

```powershell
# 1 paciente especifico
.\venv\Scripts\python.exe -m src.tools.crear_notas_clinicas --paciente "Monserrat Sofia Delgado Ramirez" --fecha 05-08-2026

# Los 16 del informe 08-2026
.\venv\Scripts\python.exe -m src.tools.crear_notas_clinicas --todos

# Otro informe
.\venv\Scripts\python.exe -m src.tools.crear_notas_clinicas --todos --informe data\analysis\informe_fichas_abiertas_07-2026.txt
```

### Flujo del script

1. Carga credenciales de `config/users.json` (usuario "yadira")
2. `run_login` → login + click box + click Pacientes citados (pasos 1-3)
3. Por cada paciente:
   - `select_date(fecha)` + `sort_by_estado`
   - `get_pacientes_del_dia` + busqueda por nombre exacto
   - Doble click en la fila → abre la ficha
   - `extraer_identificacion` → tabla de identificacion (RUN, fecha nac, etc.)
   - `extraer_historial` → "Historial de atenciones"
   - `click_atencion_actual` → abre la seccion Evaluacion
   - `extraer_anamnesis` → `li#anamnesis` con `textContent` via JavaScript (sin truncar)
   - `extraer_diagnosticos` → `li[id^="diagnose-"]` con nombre, badges, clasificacion
   - `extraer_actividades` → `li[id^="activity-"]`
   - `extraer_profesionales` → `li[id^="multiProfessional-"]`
   - `extraer_pautas` → `li[id^="pauta-"]`
   - `guardar_nota_clinica` → escribe `.txt` con 7 bloques marcados
4. Despues de cada paciente:
   - Si `fichas_en_sesion < 8`: click en "Pacientes citados" para volver a la lista
   - Si `fichas_en_sesion == 8` y quedan pacientes: `safe_quit` + `run_login` de nuevo
5. Al final: stats (procesados, abiertos, guardados, saltados, errores) + cierre automatico del navegador

### Constante importante

```python
MAX_FICHAS_POR_SESION = 8
```

Bug de Rayen: solo permite abrir 8 fichas sin guardar datos. El script resetea sesion despues de la 8va.

### Estructura del archivo `.txt` generado

7 bloques, todos con el mismo formato `=== INICIO X ===` / `=== FIN X ===`:

```
# NOTA CLINICA — extraida de Rayen
# Paciente: Monserrat Sofia Delgado Ramirez
# Fecha atencion: 05-08-2026

======================================================================
=== INICIO IDENTIFICACION ===
======================================================================
RUN: 23.296.493-6
Fecha de nacimiento: 11-04-2010 00:00
... (todos los campos de la tabla)
======================================================================
=== FIN IDENTIFICACION ===
======================================================================

======================================================================
=== INICIO HISTORIAL DE ATENCIONES ===
======================================================================
[contenido del historial]
======================================================================
=== FIN HISTORIAL DE ATENCIONES ===
======================================================================

======================================================================
=== INICIO NOTA CLINICA DE YADIRA ===
======================================================================
[anamnesis completa - es el insumo principal para Mortadelo]
======================================================================
=== FIN NOTA CLINICA DE YADIRA ===
======================================================================

======================================================================
=== INICIO DIAGNOSTICOS ===
======================================================================
- CIE 10 [Nueva, Principal, Confirmado]: Clasificación: F98 ...
- Sosp t mixto [Nueva, Sospecha]: Clasificación: F41 ...
======================================================================
=== FIN DIAGNOSTICOS ===
======================================================================

======================================================================
=== INICIO ACTIVIDADES ===
======================================================================
- 1 Controles salud mental
- 1 Nivel de riesgo en salud mental - riesgo moderado (n2)
======================================================================
=== FIN ACTIVIDADES ===
======================================================================

======================================================================
=== INICIO PROFESIONALES ===
======================================================================
- Andrea Peña Farfan (Psicólogo(a))
- Yadira Hernández Cabrera (Médico)
======================================================================
=== FIN PROFESIONALES ===
======================================================================

======================================================================
=== INICIO PAUTAS ===
======================================================================
- Cuestionario de Salud de Goldberg (5 ago. 2026)
- Control de Salud Mental (5 ago. 2026)
======================================================================
=== FIN PAUTAS ===
======================================================================
```

### Selectores CSS clave

| Elemento | Selector |
|---|---|
| Tabla identificacion | `div.scrollable.side-nav-margin table.table tbody tr` (pares th:td) |
| Historial de atenciones | `h5.history-title-right` |
| "Atencion actual" | `//li[contains(@class, 'verticalnav-tab')][.//div[normalize-space(text())='Atención actual']]` |
| Anamnesis (NOTA CLINICA DE YADIRA) | `li#anamnesis .collapse-text-sub .textoverflow-container` (con `textContent` via JS) |
| Diagnosticos | `li[id^="diagnose-"]` (nombre, badges, clasificacion) |
| Actividades | `li[id^="activity-"]` (textoverflow-container) |
| Profesionales | `li[id^="multiProfessional-"]` (nombre + rol) |
| Pautas | `li[id^="pauta-"]` (w-75 + date-display) |
| Volver a lista | `//a[contains(@href, '/main') and normalize-space(text())='Pacientes citados']` |

### Limitaciones

- **No sobrescribe** archivos existentes en `notas_clinicas/`
- **Si un paciente falla**, sigue con el siguiente + log del error
- **Login con ventana visible** (no headless) para validar visualmente

---

## 7. Como correr las cosas

```powershell
# Activar venv
cd C:\Workspace\Login-Automation
.\venv\Scripts\Activate.ps1

# PASO 1: Generar las notas clinicas desde Rayen (modo batch, los 16)
.\venv\Scripts\python.exe -m src.tools.crear_notas_clinicas --todos

# PASO 2: Generar los entregables desde las notas clinicas
.\venv\Scripts\python.exe -m src.tools.mortadelo_batch

# Tests
.\venv\Scripts\python.exe -m pytest tests

# Convertir PDF a .md (para nuevos manuales)
.\venv\Scripts\python.exe -m src.tools.pdf_a_md <pdf_path> <output_dir>
```

---

## 8. Lo que falta (priorizado)

### Prioridad ALTA (bloquea valor)

1. **Arreglar parser para ECICEP** (BUG 1) — 7 de 16 fichas salen vacias en `fichas_modificadas/`.
2. **Arreglar captura de farmacos para Fidelicio y Yrma** (BUG 2).
3. **Decidir fuente de `fecha_nacimiento`** para `calcular_edad_meses()` — Yadira debe elegir entre Mora API / Rayen / DB local.

### Prioridad MEDIA (mejoras)

4. **Plantillas 6m / 12m / 18m / 2-4a / 5-9a** para nino_sano.
5. **Validar EEDP/TEPSI** para advice de desarrollo psicomotor.
6. **Validar manual de pesquisa TEA** en control sano.
7. **Implementar skill `examenes` real** (OCR con pytesseract o vision LLM). Hoy es STUB.
8. **Switch de bundles en Python** (no requiere Rayen).
9. **Conectar Mortadelo a Rayen** directamente (hoy las notas se scrapean con `crear_notas_clinicas.py` y luego se procesan con `mortadelo_batch.py` — son 2 pasos).

### Prioridad BAJA

10. Documentar reglas del proyecto para Estudios_Tarifarios.

---

## 13. Fotos de exámenes vía Telegram (2026-08-24)

Yadira puede mandar fotos de exámenes (audiometrías, laboratorio, RX, etc.)
a @PilibertaBot por Telegram. Pilita las guarda en `notas_clinicas/_adjuntos/`
con un nombre que `mortadelo_batch` ya sabe encontrar, y la visión se corre
en el próximo batch (no inmediatamente).

### Flujo

```
Yadira (Telegram) ──foto + caption──> @PilibertaBot
                                         │
                                         ▼
                              [Mavis IM bridge]
                                         │
                                         ▼
                                    Pilita
                                         │
                                         ▼
                   src.tools.recibir_foto_examen
                   (valida, normaliza, copia)
                                         │
                                         ▼
                       notas_clinicas/_adjuntos/
                       <paciente>_<fecha>_<tipo>_<HHMMSS>.<ext>
                                         │
                                         ▼
                              [próximo mortadelo_batch]
                                         │
                                         ▼
                              analizar_adjuntos_imagen()
                              (Gemini 2.5 Pro vision)
                                         │
                                         ▼
                          === EXAMENES ADJUNTOS ANALIZADOS ===
                          en la ficha rellenada
```

### Convención del caption de Yadira

Yadira escribe la foto con un caption tipo:
- `Cecilia Reyes - audiometria`  (sin fecha explícita → Pilita pregunta o usa hoy)
- `Cecilia Reyes - 10-07-2026 - audiometria`  (fecha explícita, recomendada)
- `Maria Munoz - laboratorio 15-08-2026`  (cualquier orden)

**Reglas que Pilita aplica** (en `agent.md`):
1. Extrae paciente (nombre + apellido(s))
2. Extrae fecha (dd-mm-yyyy; si no hay, pregunta a Yadira)
3. Extrae tipo (audiometria | ecg | laboratorio | radiografia | etc.; default "examen")
4. Si no entiende el caption, PREGUNTA — nunca adivina (privacidad clínica)

### Script principal

`src/tools/recibir_foto_examen.py` (genérico, no atado a pacientes):

```bash
python -m src.tools.recibir_foto_examen \
    --input "<ruta local de la foto>" \
    --paciente "Cecilia Reyes" \
    --fecha 10-07-2026 \
    --tipo audiometria
```

Salida JSON:
```json
{
  "ok": true,
  "path": "C:/.../notas_clinicas/_adjuntos/cecilia_reyes_10-07-2026_audiometria_163045.png",
  "nombre": "cecilia_reyes_10-07-2026_audiometria_163045.png",
  "paciente": "Cecilia Reyes",
  "fecha": "10-07-2026",
  "tipo": "audiometria",
  "tamano_kb": 0,
  "error": ""
}
```

### Reglas duras del script

1. **NO sobrescribe**: si el archivo ya existe, agrega `_v2`, `_v3`, ...
2. **NO acepta inputs inválidos**: archivo inexistente, extensión no-imagen,
   paciente sin apellido, fecha mal formada — todo retorna `ok=false` con
   error explicativo en JSON.
3. **Normaliza tildes y espacios**: `María José` → `maria_jose`,
   `María José González Muñoz` → `maria_munoz` (para matching robusto).
4. **NUNCA inventa datos**: si falta info, falla explicito.
5. **Default seguro**: sin `--tipo` usa `examen`; sin `--fecha` falla.

### Tests

`tests/test_recibir_foto_examen.py` — 11 tests, todos pasan:
- Caso feliz (con y sin tipo)
- Normalización de tildes y apellidos
- Sinonimos de tipo (RX→radiografia, lab→laboratorio)
- Validación de input (archivo, fecha, paciente, extensión)
- No-sobrescritura
- Round-trip con el matcher de `analizar_adjuntos_imagen()`

### Estado

- ✅ Script creado y testeado
- ✅ Convención documentada
- ✅ Pilita sabe qué hacer (instrucciones en su `agent.md`)
- ⏳ **Pendiente**: probar end-to-end con Yadira mandando una foto real a @PilibertaBot
  y verificar que (a) llega al bridge, (b) Pilita la procesa, (c) termina en `_adjuntos/`,
  (d) el próximo batch la transcribe con visión.

---

## 9. Decisiones de diseño importantes

- **Dict en codigo, no Excel**: `_REGLA` en `src/reglas_plantillas.py` es dict de Python.
- **ECICEP es UN bundle, no dos**: `skill_ecicep` con sub-flujos ingreso/control.
- **Recetas NO es bundle**: caso especial (lookup + paste).
- **Trigger acepta coma como terminador**: `r"\*\*\s*Mortadelo(?=[\s:,;\-]|$)"`.
- **"no" es data valida**: `campos_llenos()` retorna 3-tupla `(llenos, vacios, negativos)`.
- **Output `ficha + === + 5 secciones + IC(opcional)`**: estructura validada por Yadira.
- **NOTAS CLINICAS en 7 bloques marcados**: cada bloque `=== INICIO X ===` / `=== FIN X ===`, Mortadelo los parsea con regex.
- **Reset cada 8 fichas** (limite de Rayen, bug no resueltable por nuestra parte).

---

## 10. Contexto del usuario Miguel

- Estilo directo, sin rodeos. Si se enoja, GRITA con mayusculas. El enojo generalmente es por cosas que repite 5 veces y yo no capto.
- "QUE PARTE DE LA INSTRUCCION NO SE ENTIENDE?" es su pregunta retorica cuando siente que no estoy cumpliendo. La respuesta es "NINGUNA, esta aplicado".
- No quiere cambios estructurales sin preguntar. Pregunta antes de modificar `_REGLA`, `plantillas/`, o crear scripts por paciente.
- Aprecia cuando le muestro evidencia (output real, no explicaciones).
- **Regla importante**: si te enojas, admitir el error, ajustar directo, no hacer excusas.
- **No le gusta que sea redundante** — mostrar a pacientes DIFERENTES, no siempre a Cecilia.
- Frases clave:
  - "Mortadelo jamas decidira, JAMAS!!"
  - "LAS PLANTILLAS Y LO QUE ESCRIBA LA DOCTORA EN RAYEN SON LA LEY!!"
  - "NO debes asumir que X sera la norma"
  - "para mejor claridad he cambiado el nombre de X a Y" (cuando renombra carpetas)
  - "ESTAS TRATANDO DE BOICOTEARME?" (cuando algo no funciona)

---

## 11. Datos especificos guardados en memoria (no en codigo)

- Apellido Yadira: **Hernandez Cabrera**. CESFAM Raul Cuevas, San Bernardo.
- Paciente Cecilia Reyes (caso de muestra, NO regla): RUN 7.429.988-1, fecha nac 06-02-1950, edad 76a, ficha Rayen 74299881, direccion Calle rio san pedro 19266, fono +56 9 72432928, prevision Fonasa C. Audiometria 10-07-2026 con OD 64%/OI 84% discr, tinnitus bilateral mayor OI. **No esta en codigo**, solo en memoria.
- 374 tests pasando.
- 11 gatos del equipo de Yadira (7 creados: Pilita, Teodoro, Pancho, Mortadelo, Pelusa, Gustavo, Anita; 5 pendientes: Luffyalberto, Dominga, Negrita, Mauricia, Rubi).

---

## 12. Para retomar

1. Lee este handoff completo.
2. Si el contexto de Rayen se perdio (cookies, sesion expirada), corre `crear_notas_clinicas.py --todos` para regenerar las 16 notas clinicas.
3. Corre `mortadelo_batch.py` para regenerar los 16 entregables en `fichas_modificadas/`.
4. **NO** tocar `plantillas/*.txt`, `_REGLA`, ni la nota de Yadira.
5. **NO** mencionar/leer `notas_clinicas - copia/` (es respaldo de Miguel).
6. Si el enojo de Miguel escala, parar y pedirle que copie la linea especifica del archivo que esta mal. No especular.
7. Bug #1 (parser ECICEP) sigue pendiente — es la prioridad #1.
