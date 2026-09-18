# AGENTS.md — Login-Automation

Reglas durables para cualquier agente que entre al workspace. Leelo antes de hacer cambios.

---

## 1. Objetivo único del proyecto

Asistir a Yadira en el flujo clínico diario del CESFAM Raúl Cuevas (San Bernardo): desde que Yadira manda los exámenes de un paciente por Telegram hasta que Yadira revisa el informe enriquecido del día.

Yadira es la doctora. El equipo de agentes (Anita, Pancho, Rubicita) automatiza la cadena de ingreso de información.

---

## 2. Flujo (paso 1 al 6)

```
1. Yadira manda fotos de examenes por Telegram
2. Rubicita recibe, respalda fotos crudas en data/Examenes_crudos/,
   corre OCR y consolida en data/examenes/exam_<pac>_<fecha>.md
3. Pancho scrapea Rayen y crea data/notas_clinicas/<pac>_<fecha>.md
4. Anita actualiza el mes en curso (src/analysis/actualizar_mes_actual.py)
5. Anita genera el informe de fichas abiertas (src/analysis/informe_fichas_abiertas.py)
6. Anita enriquece el informe: motivo, edad, Examenes, Interconsulta, Indicaciones
   (src/analysis/enriquecer_informe.py)
```

Mortadelo (paso 7: rellenar la ficha a partir de la nota + info + examenes) esta
**ELIMINADO** y sera reescrito desde cero. Hasta entonces, paso 7 no existe.

---

## 3. Reglas duras

- **Yadira es la fuente de verdad** sobre sus datos. Los agentes no deciden
  diagnosticos ni tratamientos.
- **Las notas son INMUTABLES en contenido y orden**. Solo se permite
  limpieza de formato (viñetas, tablas) que NO cambie la informacion.
- **NO sobrescribir archivos** en `data/notas_clinicas/`.
- **NO crear scripts por paciente**. El script es siempre generico.
- **NO inventar datos** que no esten en `data/info_paciente/`, anamnesis o examenes.
- **Yadira o cualquier paciente es solo un caso**, NO la norma. No usar como
  ejemplo en codigo ni en texto.
- **Sin emojis** en codigo, system prompts ni documentacion tecnica.

---

## 4. Estructura del proyecto

```
C:\Workspace\Login-Automation\
├── data/
│   ├── notas_clinicas/         ← input: notas crudas de Rayen (Pancho)
│   ├── info_paciente/          ← input: metadata de Rayen (Pancho)
│   ├── examenes/               ← input: examenes consolidados OCR (Rubicita)
│   └── Examenes_crudos/        ← input: fotos crudas de Telegram (Rubicita)
├── src/
│   ├── analysis/               ← Anita (pasos 4, 5, 6)
│   │   ├── actualizar_mes_actual.py
│   │   ├── informe_fichas_abiertas.py
│   │   ├── informe_paths.py
│   │   ├── enriquecer_informe.py
│   │   └── ...
│   ├── pancho_skills/          ← Pancho (paso 3: scraping Rayen)
│   └── tools/
│       ├── crear_notas_clinicas.py     ← Pancho (CLI: python -m ...)
│       └── recibir_foto_examen.py      ← Rubicita (CLI: python -m ...)
├── tests/                      ← tests de los scripts vivos
└── docs/                        ← notas
```

**NO existe** en este proyecto (eliminado en sesion 2026-09-17):
- `src/tools/generar_ficha_con_llm.py` (paso 7, sera reescrito).
- `src/tools/mortadelo_batch.py`, `mortadelo_parser.py`, `mortadelo_redactores.py`.
- `src/mortadelo/` (bundles/skills).
- `.opencode/agent/mortadelo.md`.
- `data/anamnesis/`, `data/fichas_clinicas/`, `data/plantillas/`, `data/prompts*/`.
- `scripts_temp/`.

---

## 5. Convencion de nombres

### Archivos
- `data/notas_clinicas/<pac>_<fecha>.md` (output de Pancho).
- `data/info_paciente/info_<pac>_<fecha>.md`.
- `data/examenes/exam_<pac>_<fecha>.md` (consolidado OCR de Rubicita).
- `data/examenes_crudos/<pac>_<n>_<dd-mm-aaaa>.<ext>` (fotos crudas).
- `<pac>` y `nombre_*` se mantienen con mayusculas, tildes y espacios (legible).

### Reporte enriquecido (paso 6)
Columnas: `Fecha | Nombre | Edad | Tipo de atencion | Motivo de la atencion | Examenes | Interconsulta | Indicaciones`

`Examenes`, `Interconsulta`, `Indicaciones` se llenan desde el trigger
`** Mortadelo` en la nota clinica:
- `Examenes = SI` si el trigger contiene "examenes adjuntos" (regex case-insensitive).
- `Interconsulta = SI` si contiene "generar/crear interconsulta".
- `Indicaciones = SI` si contiene "realizar/indicar indicaciones".

---

## 6. Comandos tipicos del flujo (pasos 1-6)

```bash
# Paso 1-2: Rubicita opera automaticamente por Telegram.
#           El operador (o Yadira) puede invocarlo manualmente:
python -m src.tools.recibir_foto_examen \
    --input "C:/ruta/a/foto.jpg" \
    --paciente "Nombre Apellido" \
    --fecha "dd-mm-yyyy" \
    --indice 1

# Paso 3: Pancho scrapea Rayen
python -m src.tools.crear_notas_clinicas --todos --user yadira

# Paso 4: Anita actualiza el mes
python -m src.analysis.actualizar_mes_actual yadira

# Paso 5: Anita genera el informe
python -m src.analysis.informe_fichas_abiertas

# Paso 6: Anita enriquece el informe
python -m src.analysis.enriquecer_informe
```

---

## 7. Documentacion

- `docs/HANDOFF-PROYECTO-2026-08-23.md` — handoff general del proyecto.
- `docs/CREDENCIALES.md` — API keys y credenciales.
- `C:\Users\morti\.minimax\agents\mavis\memory\MEMORY.md` — memoria del agente Mavis (reglas durables adicionales).

---

## 8. Agentes Mavis (fuera de este proyecto)

Los agentes `agents/<nombre>/agent.md` en `C:\Users\morti\.minimax\` son la
cara visible para Yadira (Telegram). Este proyecto (`src/`, `data/`, `tests/`)
solo provee los scripts Python que esos agentes invocan.

- `agents/rubicita/` — recibe fotos por Telegram, invoca `recibir_foto_examen.py`.
- `agents/pancho/` — login + scraping de Rayen, invoca `crear_notas_clinicas.py`.
- `agents/anita/` — orquestacion diaria, invoca scripts de `src/analysis/`.
- `agents/mortadelo/` — **ELIMINADO** (paso 7 sera reescrito).

---