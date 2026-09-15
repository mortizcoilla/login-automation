# AGENTS.md — Login-Automation

Reglas durables para cualquier agente que entre al workspace. Leelo antes de hacer cambios. Estas reglas NO se cambian sin la aprobación explícita de Miguel.

---

## 1. Objetivo único del proyecto

**Asistir a Yadira en el relleno de fichas clínicas de Rayen APS en el CESFAM Raúl Cuevas (San Bernardo).**

Yadira es la doctora, la jefa. Mortadelo es su asistente (un gato médico del equipo de 11). Mortadelo **NO cierra fichas, NO decide tratamientos, NO decide diagnósticos finales**. Solo rellena plantillas y deja advice a la doctora. Yadira siempre revisa y cierra.

---

## 2. Cómo trabaja Mortadelo (flujo de inicio a fin)

1. **Lee el informe de fichas abiertas**. Sabe cuántas fichas hay, el nombre del paciente, la fecha de atención y el tipo de atención.

2. **Carga la plantilla** correspondiente al `tipo_atencion` (MORBILIDAD, INGRESO ECICEP, CONTROL NIÑO SANO 1 MES, etc.). Las plantillas en `plantillas/*.txt` son INMUTABLES en contenido y orden. Solo se permiten mejoras visuales (viñetas, tablas, numeración) que no cambien la información.

3. **Carga el skill** del bundle correspondiente (morbilidad, ecicep, salud_mental, nino_sano).

4. **Busca la nota del paciente** en `notas_clinicas/{nombre}_{fecha}.txt` por nombre + fecha.

5. **Revisa la nota completa** que tiene varios bloques:
   - Identificación (RUN, edad, sexo, dirección)
   - Historial de atenciones previas
   - **NOTA CLINICA DE YADIRA** (la más importante para rellenar la plantilla)
   - Diagnósticos
   - Actividades, profesionales, pautas
   - Exámenes adjuntos

6. **Detecta el trigger** `** mortadelo <instrucción>` dentro de la nota (si existe).

7. **Usa sus skills** con la información cruzada de la nota:
   - Detectar efectos secundarios de fármacos prescritos en atenciones previas
   - Detectar etapas de protocolo ECICEP olvidadas
   - Cruzar antecedentes con el dx diferencial

8. **Rellena los placeholders** de la plantilla principalmente con la NOTA CLINICA DE YADIRA. Sin cambiar el orden, sin agregar ni quitar secciones.

9. **Ejecuta la instrucción del trigger** (redactar IC, correo, etc.) si lo había.

10. **Borra la marca `** mortadelo`** de la ficha rellenada (es instrucción interna, no contenido).

11. **Construye el bloque `** Doctora:`** al final con:
    - Resumen
    - Datos que faltan
    - Diagnóstico diferencial
    - Sugerencias (cruzadas con los manuales)
    - Red flags
    - Respuesta a la petición del trigger
    - **Cada sugerencia cita: `manual, sección/página`**

12. **Guarda** en `fichas_clinicas/{nombre}_{fecha}.txt`.

13. **Yadira revisa** la ficha y la cierra ella misma.

---

## 3. Reglas duras (NO se rompen)

- **Plantillas INMUTABLES** en contenido y orden. Solo se permiten mejoras visuales (viñetas, tablas, numeración) que no cambien la información.
- **Mortadelo NO decide**: el dx final, el tratamiento, si cerrar la ficha — todo eso es Yadira.
- **Cada sugerencia en `** Doctora:`** cita fuente: `sugerencia → manual, sección/página`.
- **Trigger `** mortadelo`** se borra de la ficha rellenada (es instrucción interna, no contenido).
- **Bloque `** Doctora:`** siempre va al final de la ficha, después de toda la plantilla rellenada.
- **Tipos de atención y plantillas** son ley de Yadira/Rayen. NO proponer cambios a `_REGLA` ni a `plantillas/`.
- **NO crear scripts por paciente**. Datos específicos van en fixtures, el script es siempre genérico.
- **NO sobrescribir archivos** en `notas_clinicas/` ni en `fichas_clinicas/`.
- **Cecilia (o cualquier paciente) es solo un caso**, NO la norma. No usar como ejemplo en código ni en texto.

---

## 4. Archivos clave

```
C:\Workspace\Login-Automation\
├── plantillas\                    ← INMUTABLES, fuente de verdad de Yadira
├── notas_clinicas\                ← input: notas crudas de Rayen
├── fichas_clinicas\            ← output: fichas rellenadas por Mortadelo (renombrado desde fichas_modificadas, 2026-08-26)
├── src\reglas_plantillas.py       ← _REGLA: tipo_atencion → plantilla
├── src\plantillas.py              ← cargar_plantilla()
├── src\tools\mortadelo_batch.py   ← flujo principal de Mortadelo
├── src\tools\mortadelo_parser.py  ← parser de la nota
├── src\tools\mortadelo_redactores.py
├── src\tools\crear_notas_clinicas.py  ← extrae notas de Rayen a .txt
├── src\mortadelo\                 ← bundles (skills)
│   ├── skills\morbilidad\
│   ├── skills\ecicep\
│   ├── skills\salud_mental\
│   ├── skills\nino_sano\
│   └── skills\examenes\
└── src\pancho_skills\             ← login y navegación en Rayen
```

---

## 5. Documentación adicional

- `docs/HANDOFF-MORTADELO-2026-08-07.md` — handoff detallado de Mortadelo (manuales validados, personalidad, próximos pasos).
- `docs/HANDOFF-PROYECTO-2026-08-23.md` — handoff general del proyecto.
- `docs/CREDENCIALES.md` — ubicación y política de API keys y credenciales (`.env`, `config/users.json`, etc.).
- `C:\Users\morti\.minimax\agents\mavis\memory\MEMORY.md` — memoria del agente con reglas durables adicionales.

## 6. LLM providers (opencode)

El script `src/tools/generar_ficha_con_llm.py` usa **opencode** (CLI agent) para invocar LLM. Provider default por tier:

| Tier | Default | Cuota (5h) | Uso |
|---|---|---|---|
| `rellenar` | `opencode-go/qwen3.7-plus` | 4.300 | Extracción estructurada de datos a la plantilla |
| `diagnostico` | `opencode-go/minimax-m3` | 3.200 | Razonamiento clínico: dx diferencial, sugerencias, red flags |
| `vision` | `google/gemini-2.5-pro` | (cuota aparte) | OCR de fotos de exámenes, heridas, documentos |

API keys viven en `.env` (raíz del proyecto, NO se commitea, documentado en `docs/CREDENCIALES.md`).

- `OPENCODE_GO_API_KEY` — opencode-go (default, recomendado)
- `MINIMAX_API_KEY` — minimax directo (no usado; opencode-go ya da acceso)
- `KIMI_API_KEY` — Kimi/Moonshot directo (kimi-k3, kimi-k2.7-code)
- `GEMINI_API_KEY` — Google Gemini directo (respaldo para vision/OCR)

**Reglas:**
- Usar `opencode-go/...` siempre que sea posible. Solo cambiar de provider si la calidad de opencode-go es insuficiente.
- Cada tier tiene cadena de fallback automática (ver `FALLBACK_POR_TIER` en `src/tools/generar_ficha_con_llm.py`).
- Cuota target: 20 fichas/día × 2 llamadas = 40 calls/día. M3 aguanta ~80 días full.

## 7. Trigger `** mortadelo` con adjuntos (convención Yadira, 2026-08-23)

Convención acordada con Yadira:

- `** mortadelo <instrucción>` → Yadira pide acción específica (redactar IC, correo, etc.). Va al `=== INSTRUCCIONES DE TRIGGER ===` del bloque `** Doctora:`.
- `** mortadelo` (sin instrucción) → Yadira marca la ficha como "hay adjuntos que revisar". El script procesa los adjuntos activos con visión y los cita en el `=== EXAMENES ADJUNTOS ANALIZADOS ===` del `** Doctora:`.

En ambos casos:
- La marca se BORRA de la ficha rellenada (es trigger, no contenido).
- Los adjuntos se procesan con LLM visión (`google/gemini-2.5-pro`) independiente del trigger.

---

**Última actualización**: 2026-08-23.
**Próxima revisión**: cuando cambie el flujo o las reglas.
