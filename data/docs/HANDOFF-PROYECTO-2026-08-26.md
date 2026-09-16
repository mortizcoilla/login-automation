# HANDOFF DEL PROYECTO — Mortadelo / Login-Automation
**Fecha:** 2026-08-26 (continuación, tarde 16:45 CLT)
**Sesión:** continuación de la sesión 2026-08-24 (Limpieza de fichas + prompt compress)

> **Handoffs previos**:
> - `HANDOFF-MORTADELO-2026-08-07.md` — primer handoff de Mortadelo.
> - `HANDOFF-PROYECTO-2026-08-23.md` — handoff general con el flujo de `crear_notas_clinicas.py` y la estructura de archivos. **Leerlo primero** si no se ha leído.
> - `HANDOFF-PROYECTO-2026-08-24.md` — handoff de la sesión 2026-08-24 (LLM externo, opencode-go/minimax-m3, refactor `--file`).

---

## 1. Cambios principales desde 2026-08-24

### 1.1 Prompt de Mortadelo comprimido y endurecido (NUEVO)

**Problema**: el LLM sobre-explicaba en el cuerpo de la ficha con patrones prohibidos:
- `(revisión por sistemas, de NOTA Yadira)`
- `REGISTRADO EN FORMULARIO (no transcritos a la nota)`
- `~ asumido como HbA1c por contexto DM2 + formato %; si fuera hemoglobina en g/dL sería anemia severa — A VALIDAR`
- `transcritos de NOTA Yadira`

Aunque la **REGLA DE LIMPIEZA** ya estaba en mortadelo.md, el LLM no la respetaba fully. Razón: el prompt tenía **518 líneas / 35KB** y el LLM se distrae con tanto contexto.

**Solución**:
- Comprimí mortadelo.md de **518 líneas / 35KB → 116 líneas / 6.9KB** (reducción del 80%)
- Eliminé las 9 REGLAS redundantes y dejé 4 REGLAS CRÍTICAS: jerarquía, completitud, limpieza, inmutabilidad
- Eliminé secciones diferidas (REGLA 8 Rubicita, REGLA 9 vision LLM — Perico no es examen real)
- Eliminé loops verbosos ("Loop 1", "Loop 2", "Loop 3" → replaced by completitud check al final)
- Renombré secciones: `ADVERTENCIAS DE INFERENCIA` → `INFERENCIAS CON FUENTE`, `DATOS QUE REQUIEREN VALIDACIÓN` → `PARA VALIDAR`

### 1.2 Doctora block simplificado (8 → 3-4 secciones)

**Antes (8 secciones siempre, mucho ruido):**
1. RESUMEN DE LO QUE SE HIZO
2. ADVERTENCIAS DE INFERENCIA
3. DATOS QUE REQUIEREN VALIDACIÓN
4. DIAGNÓSTICO DIFERENCIAL
5. SUGERENCIAS PARA LA NOTA  ← genérico, mejor agregado por semana
6. SUGERENCIAS PARA EL DIAGNÓSTICO
7. RED FLAGS A VIGILAR
8. SUGERENCIAS PARA PRÓXIMA FICHA  ← genérico, mejor agregado por semana

**Ahora (3-4 secciones, proporcional a la complejidad):**
1. `INFERENCIAS CON FUENTE` (omitir si no hubo)
2. `PARA VALIDAR` (siempre)
3. `DX DIFERENCIAL` (siempre, + sugerencia concreta embebida)
4. `RED FLAGS` (condicional — solo si hay alertas reales)
5. `INSTRUCCIONES DE TRIGGER` (condicional — solo si la nota traía `** mortadelo X`)

Las secciones 5 y 8 (SUGERENCIAS PARA LA NOTA / PRÓXIMA FICHA) **se mueven a un nuevo script** `informe_semanal_yadira.py` que agrega tips across multiple fichas.

### 1.3 Filtro de historial a últimos 6 meses (NUEVO)

**Problema**: la sección HISTORIAL DE ATENCIONES traía 5-10 entradas de meses atrás, ruido para el LLM.

**Solución**: nueva función `filtrar_historial_ultimos_6_meses(historial, fecha_objetivo, logger)` en `crear_notas_clinicas.py:286-380`. Aplicada en `guardar_nota_clinica()` antes de escribir el bloque. Helper `_fecha_meses_atras(fecha, meses)` con wrap de año + clamping del día.

**Tests**: `tests/test_filtrar_historial_6_meses.py` (15 tests, todos passing). Cubren: 6 meses exactos, wrap de año, clamping, borde inclusivo, vacíos, placeholders, fecha inválida, log emitido.

### 1.4 Validador de citas post-LLM (NUEVO)

**Problema**: el LLM cita manuales que **no existen** o admite no tener acceso (`"sin acceso a contenido específico en esta sesión"`). Las citas son no-verificables.

**Solución**: nueva función `validar_citas(texto) -> list[str]` en `generar_ficha_con_llm.py:1432-1495`. Verifica:
1. Si el LLM confesó falta de acceso (regex `\(sin acceso a contenido especifico[^)]*\)`)
2. Si el manual citado está en la lista cerrada `MANUALES_VALIDOS` (21 manuales: ecicep, minsal-*, gold-*, esc-esh-*, pcic_base.txt, etc.)
3. Si el LLM parafraseó mal (ej. `minsal-ira.md` en vez de `minsal-ira-era-aps.md`)

Integrado en `procesar_nota()` después de la llamada LLM, antes de `guardar_ficha()`. **No bloquea** — solo emite `[validar_citas] WARN: ...` para revisión de Yadira/Miguel.

### 1.5 Citation format sin paginación (NUEVO)

**Problema**: el LLM ponía `pág 12` en las citas, pero los manuales son archivos `.md` sin paginación. Eran alucinaciones.

**Solución**: cambié el formato en mortadelo.md de `manual, sección/pág` → `manual, sección "X"`. Agregué nota explícita: "**No incluyas `pág N`** — los manuales son .md sin paginación física".

### 1.6 Bug fix: `--output-dir` plumbed end-to-end (NUEVO)

**Problema**: el flag `--output-dir` y `--adjuntos-dir` estaban declarados en argparse pero no se pasaban a `procesar_nota()`. El pre-check respetaba `output_dir` pero `guardar_ficha()` no — las fichas se guardaban igual en `fichas_clinicas/`, ignorando el custom dir. Bloqueaba los smoke tests no-destructivos.

**Solución**:
- `guardar_ficha()` ahora acepta `output_dir: Optional[Path] = None`
- `main()` define `output_dir` desde `args.output_dir` y lo pasa a `procesar_nota()`
- `procesar_nota()` ahora lo pasa a `guardar_ficha()`

Esto permite smoke tests con `--output-dir C:\Temp\test_prompt_v6\` sin tocar las 17 fichas en el repo.

---

## 2. Estado actual de las 17 fichas (2026-08-26)

Las 17 fichas en `fichas_clinicas/` están en estado **mixto**:
- 5 fueron re-procesadas con la versión inicial de la REGLA DE LIMPIEZA (Karina_Ximena, Karina_Mabel, Natalia, Marisol, Silvia) → tienen 11-33 "A VALIDAR" inline en cuerpo
- 12 son versiones más viejas, también con "A VALIDAR" inline (1-21 cada una)

**Pendiente**: re-correr las 17 con el **prompt v5** (con todos los fixes) — mover a `.trash/pre-LIMPIEZA-ESTRICTA-2026-08-26-16h35/`, lanzar `python -m src.tools.generar_ficha_con_llm --informe data/analysis/informe_fichas_abiertas_08-2026.txt`, verificar.

**Smoke test v5 (Almendra, 25-08-2026)**: 3:03 min, 3559 chars, 0 patrones prohibidos, 2 secciones en Doctora (PARA VALIDAR + DX DIFERENCIAL). RED FLAGS y TRIGGER omitidos correctamente. Listo para batch.

---

## 3. Mejoras estratégicas pendientes (NO implementadas — para próximas sesiones)

### 3.1 RAG sobre los manuales (alto impacto, esfuerzo medio)

**Problema**: pasamos el manual completo (~50KB) en cada ficha. Con bundle ECICEP podríamos llegar a 200KB de context solo en manuales. Ineficiente y citas imprecisas.

**Diseño**:
- `chromadb` o `faiss-cpu` local (sin cloud, respeta privacidad)
- Embeddings del manual completo (1 vez, off-line)
- En cada llamada: retrieval top-3 chunks por similitud con la nota del paciente
- Solo paso al LLM el chunk relevante, no el manual completo

**Ganancia**: -70% context en manuales, citas más precisas, escalable a 10+ manuales.

**Esfuerzo**: 1 día.

### 3.2 Paralelizar el batch (medio impacto, bajo esfuerzo)

**Problema**: 17 fichas en serie = 30-85 min. Cada llamada es independiente — paralelizable.

**Diseño**: `concurrent.futures.ThreadPoolExecutor` con 3-4 workers en `procesar_nota()`. Opencode puede correr varios `--run` en paralelo (no choca la cuota porque son conexiones HTTP distintas).

**Caveat**: verificar que la cuota de opencode-go aguante 4 calls concurrentes. Si no, throttle a 2-3.

**Esfuerzo**: 1-2 horas.

### 3.3 Modo diff entre versiones (medio impacto, esfuerzo medio)

**Problema**: cuando re-ejecutamos una ficha (por prompt nuevo o corrección), no hay forma fácil de ver qué cambió. Yadira no sabe si la nueva versión es mejor o peor sin leer ambas.

**Diseño**: opción `--diff contra <ficha_v1.txt>` en el wrapper. Genera un diff de las dos versiones, marca qué se agregó/quitó/cambió en el cuerpo y en el Doctora block.

**Esfuerzo**: 3-4 horas.

### 3.4 Script de informe semanal Yadira (NUEVO, prioridad media)

**Diseño propuesto**:
- `src/tools/informe_semanal_yadira.py`
- Lee `notas_clinicas/*.txt` de los últimos N días (default 7)
- Parsea bloques: HISTORIAL, NOTA CLINICA, ESTRATIFICACION
- Agrega:
  - Top 10 huecos más frecuentes en `NOTA CLINICA DE YADIRA` (campos que quedaron sin llenar)
  - Distribución por bundle (cuántas morbilidades, ECICEP, controles)
  - Pacientes con más `A VALIDAR POR YADIRA`
  - Patrones de dx más frecuentes
- Genera `informe_semanal_yadira_AAAA-MM-DD.md` con bullets concretos + TL;DR
- CLI: `python -m src.tools.informe_semanal_yadira --dias 7 --output C:\Temp\`

**Bonus**: se puede cronear los lunes 7am con `cron create` para que Yadira lo reciba sin pedirlo.

**Esfuerzo**: 1 día.

### 3.5 ✅ Renombrar `fichas_modificadas/` → `fichas_clinicas/` (HECHO 2026-08-26)

- Directorio movido con Move-Item (17 archivos transferidos)
- `src/tools/generar_ficha_con_llm.py`: 8 referencias actualizadas
- `src/tools/mortadelo_batch.py`: 1 referencia actualizada
- `AGENTS.md`: 3 referencias actualizadas
- `fichas_modificadas/` quedó vacío (no se pudo eliminar — Remove-Item bloqueado por safety policy)

### 3.6 ✅ Deprecar `mortadelo_batch.py` (HECHO 2026-08-26)

Banner de deprecation agregado al inicio del archivo con:
- Advertencia de deprecation
- Comparacion con la nueva ruta LLM
- Razones para no usar (sin manuales, sin citas, sin filtros)

---

## 4. Comandos útiles para retomar

```powershell
# Smoke test no-destructivo con prompt actual
cd C:\Workspace\Login-Automation
python C:\Temp\test_prompt_v3\test_smoke.py
# Mira el output en C:\Temp\test_prompt_v5\ (o la versión que corresponda)

# Mover las 17 a .trash/ y re-correr batch
New-Item -ItemType Directory -Path ".trash\pre-LIMPIEZA-ESTRICTA-2026-08-26-16h35" -Force
Move-Item fichas_clinicas\*.txt .trash\pre-LIMPIEZA-ESTRICTA-2026-08-26-16h35\

cd C:\Workspace\Login-Automation
python -m src.tools.generar_ficha_con_llm --informe data/analysis/informe_fichas_abiertas_08-2026.txt

# Verificar resultado: 0 patrones prohibidos en cuerpo
$patrones = @("REGISTRADO EN FORMULARIO", "transcritos? de NOTA", "asumido como", "A VALIDAR POR YADIRA \(")
$fichas = Get-ChildItem fichas_clinicas\*.txt
foreach ($f in $fichas) {
  $c = Get-Content $f.FullName -Raw -Encoding UTF8
  $hits = ($c | Select-String -Pattern $patrones[0] -AllMatches).Matches.Count
  Write-Host "$($f.Name): $hits hits"
}
```

---

## 5. Lecciones aprendidas (durable)

- **El prompt verboso distrae al LLM.** Empezamos con 35KB de system prompt; el LLM mezclaba reglas. Comprimir a 7KB mantuvo las reglas críticas y eliminó las redundantes. Output: 7318 → 3559 chars (-51%), 0 patrones prohibidos.

- **Las citas a manuales son no-verificables por diseño.** El LLM no tiene un índice del manual — busca por similarity. Por eso cita secciones que no existen o admite "sin acceso a contenido específico". El validador post-LLM es **esencial**, no opcional.

- **El smoke test no-destructivo requiere plumbing de `--output-dir` end-to-end.** Pre-check respetaba el flag pero `guardar_ficha()` no. Iterar fichas reales para smoke test = riesgo de perder trabajo. Ahora el smoke test corre en `C:\Temp\test_prompt_v6\`.

- **Las 5 secciones eliminadas del Doctora (SUGERENCIAS PARA LA NOTA, SUGERENCIAS PARA PRÓXIMA FICHA) son mejor agregadas por semana**, no por ficha. La idea del informe semanal Yadira es la materialización.

- **El LLM con `--file` attachments es la forma correcta de pasar contenido al LLM.** Antes (prompt inline de 35KB) el LLM se confundía. Ahora 1.5KB de prompt + 4 adjuntos funciona. El truco: `--file` pasa el contenido como multimodal, no como path.

---

## 6. Estado del sistema (resumen ejecutivo)

- **17 fichas en `fichas_clinicas/`** — versión vieja, pendiente re-batch
- **6 fichas en `.trash/`** (versiones pre-LIMPIEZA de 5 pacientes)
- **Mortadelo v5 (prompt)** — 116 líneas / 6.9KB, validado con smoke test limpio
- **Validador de citas** — implementado, integrado, probado con 0/3 warnings
- **Filtro historial 6 meses** — implementado + 15 tests
- **opencode-go/minimax-m3** — modelo default, funciona, ~3 min/ficha
- **Quota opencode-go** — 84.5% disponible (per Miguel), sin problemas

**Próxima sesión**: ejecutar el batch de 17 fichas con prompt v5 y validar resultados.
