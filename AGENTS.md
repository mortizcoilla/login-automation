# AGENTS.md — Login-Automation

Reglas durables para cualquier agente que entre al workspace. Leelo antes de hacer cambios.

---

## 1. Objetivo único del proyecto

Asistir a Yadira en el flujo clínico diario del CESFAM Raúl Cuevas (San Bernardo): desde que Yadira manda los exámenes de un paciente por Telegram hasta que Yadira revisa el informe enriquecido del día.

Yadira es la doctora. El equipo de agentes (Anita, Pancho, Rubicita) automatiza la cadena de ingreso de información.

---

## 2. Flujo

**Obligatorio diario** (orden REAL de dependencias 4->5->3->6, REQ-008):

```
python -m src.analysis.actualizar_mes_actual yadira && python -m src.analysis.informe_fichas_abiertas && python -m src.tools.crear_notas_clinicas --todos && python -m src.analysis.enriquecer_informe && python -m src.tools.mortadelo --todos
```

1. (paso 4) Anita actualiza el mes -> data/analysis/fichas_completo.db
2. (paso 5) Anita genera el informe base -> data/analysis/informe_fichas_abiertas_<MM-YYYY>.txt
3. (paso 3) Pancho scrapea las fichas del informe -> data/notas_clinicas/,
   data/info_paciente/, data/anamnesis/
4. (paso 6) Anita enriquece el informe (motivo, edad, Examenes,
   Interconsulta, Indicaciones)
5. (paso 7) Mortadelo genera ficha completa + informe de trazabilidad
   -> data/fichas_generadas/ y data/informes_trazabilidad/

**Opt-in independiente** (Yadira lo invoca cuando quiere, REQ-054):
- (paso 8) `python -m src.tools.cargar_ficha --paciente "..." --fecha dd-mm-yyyy`
  o `--todos`: pega la ficha generada (paso 7) en el editor interno de
  Rayen. Comparte el flujo de apertura de ficha con paso 3
  (`src/rayen/flujos/apertura_ficha.py`) hasta el
  `<div>Atencion actual</div>`; a partir de ahi, paso 8 NO hace click
  (no entra al panel de evaluacion), pega el contenido y se detiene.
  Yadira revisa y aprieta Guardar ella misma. Trazabilidad en
  `data/trazabilidad_carga/carga_<ts>.json`.

**Opt-in por paciente** (solo cuando Yadira envia examenes por Telegram):
- (paso 1) Yadira manda fotos.
- (paso 2a) Rubicita archiva en data/examenes_crudos/ (SIN OCR local).
- (paso 2b) `python -m src.tools.consolidar_examenes --paciente "..."`:
  transcribe via API de vision z.ai -> data/examenes/exam_<pac>_<fecha>.md.

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

## 4. Estructura del proyecto (refactor 2026-09-18)

```
src/
  core/            kernel compartido: fechas, nombres, tipos_atencion, rutas
  rayen/           capa Selenium: navegador, navegacion, tabla,
                   flujos/ (apertura_ficha; compartido paso 3 y paso 8),
                   escritura/ (editor_anamnesis; paso 8 unico),
                   extraccion/ (identificacion, historial, atencion_actual,
                   diagnosticos, plan, estratificacion)
  notas/           escritura de documentos: modelos, nota_clinica,
                   info_paciente, anamnesis
  informes/        pasos 4-6: mes.py, base.py, enriquecer.py,
                   parser.py (parser UNICO del informe)
  examenes/        paso 2b: vision_api.py (z.ai), consolidar.py
  analysis/        CLIs finos (paths estables): actualizar_mes_actual,
                   informe_fichas_abiertas, enriquecer_informe
  tools/           CLIs: crear_notas_clinicas, cargar_ficha,
                   recibir_foto_examen, consolidar_examenes, informe_tecnico
  pancho_skills/   capa skills sobre rayen/
  queue_store.py + anita/  subsistema de aprobaciones (futuro flujo
                            de aprobaciones Telegram)
docs/REQUISITOS.md  matriz de trazabilidad REQ <-> codigo <-> tests
```

Detalles y reglas por requisito: `docs/REQUISITOS.md` (REQ-001..058).
Referencia inmutable de comportamiento:
`C:\Workspace\Login-Automation_BACKUP_2026-09-18\` (solo lectura).


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

# Paso 8: Yadira carga la ficha generada en Rayen (opt-in independiente)
python -m src.tools.cargar_ficha --paciente "Nombre Apellido" --fecha dd-mm-yyyy
# o batch desde el informe del mes en curso:
python -m src.tools.cargar_ficha --todos
```

---

## 7. Documentacion

- `docs/DIAGRAMAS.md` — pipeline y arquitectura en diagramas.
  **Se actualiza EN EL MISMO COMMIT de cualquier cambio de flujo, comando,
  modulo o archivo de salida.** Diagrama desactualizado = bug de docs.
- `docs/REQUISITOS.md` — matriz de trazabilidad REQ <-> codigo <-> tests.
  Mismo compromiso: todo cambio de regla actualiza su fila en el mismo commit.

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