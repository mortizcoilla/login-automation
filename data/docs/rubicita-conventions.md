# Convenciones de Rubicita — naming de adjuntos

**Última actualización**: 2026-08-25
**Origen**: acuerdo con Yadira + Miguel durante el setup del test real con el paciente "Perico de los Palototes".

---

## Qué es Rubicita

Rubicita es el agente que recibe las fotos que Yadira manda por Telegram y las deja en el sistema para que Mortadelo las procese. Es un agente **sin vision LLM** — solo manipula archivos (descarga, renombra, guarda). NO analiza el contenido de las imágenes.

## El flujo

```
Yadira (Telegram)              Rubicita                    Mortadelo
       │                            │                            │
       │  "rubicita, adjunto       │                            │
       │   examenes del            │                            │
       │   paciente perico         │                            │
       │   los palotes"            │                            │
       │  [foto1.jpg]              │                            │
       │  [foto2.jpg]              │                            │
       │  [foto3.jpg]              │                            │
       │  [foto4.jpg]              │                            │
       │ ────────────────────────► │                            │
       │                            │ 1. Detecta N fotos        │
       │                            │ 2. Extrae "perico"        │
       │                            │    (o "pericode...")      │
       │                            │ 3. Renombra cada foto:    │
       │                            │    perico_1_25-08-2026.jpg│
       │                            │    perico_2_25-08-2026.jpg│
       │                            │    perico_3_25-08-2026.jpg│
       │                            │    perico_4_25-08-2026.jpg│
       │                            │ 4. Guarda en              │
       │                            │    notas_clinicas/_adjuntos/│
       │                            │ ─────────────────────────►│
       │                            │                            │ 5. Detecta por nombre
       │                            │                            │ 6. Vision LLM transcribe
       │                            │                            │ 7. Incorpora a la ficha
```

## Convención de nombres (Rubicita DEBE respetarla)

**Patrón**:
```
<paciente_normalizado>_<n>_<dd-mm-aaaa>.<ext>
```

Donde:

| Componente | Significado | Reglas |
|---|---|---|
| `<paciente_normalizado>` | Nombre del paciente extraído del mensaje de Yadira | minúsculas, sin acentos (`á→a`, `é→e`, etc.), un solo nombre o nombre+apellido según cómo lo diga Yadira. Si Yadira dice "perico de los palototes", Rubicita decide si guardar `perico` o `pericode` (ambos son válidos mientras Mortadelo pueda matchear). |
| `<n>` | Índice secuencial | 1, 2, 3, ... en el orden en que Yadira mandó las fotos en el mismo mensaje de Telegram. NO reordenar. |
| `<dd-mm-aaaa>` | Fecha de la atención | Extraída del mensaje de Yadira o, si no la da, del contexto de la nota que Pancho dejó en `notas_clinicas/`. |
| `<ext>` | Extensión original del archivo | `.jpg`, `.jpeg`, `.png`, `.pdf`, `.webp`, etc. NO cambiar la extensión. |

**Ejemplos válidos**:
- `perico_1_25-08-2026.jpg`
- `perico_2_25-08-2026.jpg`
- `perico_3_25-08-2026.jpg`
- `perico_4_25-08-2026.jpg`
- `margarita_perez_1_15-09-2026.png`
- `juan_1_03-01-2026.pdf`

**Lo que Rubicita NO debe hacer** (errores comunes a evitar):

- ❌ **NO incluir el tipo de examen en el nombre.** Aunque Yadira diga "te paso la eco, la endoscopia y la epicrisis", Rubicita NO debe nombrar como `perico_ecografia_25-08-2026.jpg`. Rubicita no ve el contenido — si adivina el tipo por el texto, puede equivocarse. El tipo lo detecta Mortadelo con vision LLM al transcribir.
- ❌ **NO cambiar la extensión.** Si Telegram le pasa un `.pdf`, Rubicita guarda `.pdf`, no `.jpg`.
- ❌ **NO reordenar las fotos.** Yadira las manda en un orden; ese orden se preserva (foto 1 = perico_1, foto 2 = perico_2, etc.).
- ❌ **NO agregar prefijos** tipo "foto_", "img_", "exam_", "scan_". Solo `<paciente>_<n>_<fecha>.<ext>`.
- ❌ **NO incluir la fecha de subida** (la fecha de hoy). Solo la fecha de la atención que Yadira indique.
- ❌ **NO guardar en otro directorio.** Solo en `notas_clinicas/_adjuntos/`. NO en `_chrome_dl/` (eso es cache de Chrome, no inbox de Rubicita).

## Casos especiales

### Yadira manda fotos sin decir el nombre del paciente
- Rubicita debe pedirlo: "Hola Yadira, ¿de qué paciente son estas fotos? Dame el nombre y la fecha de la atención."
- NO adivinar. NO usar "sin_nombre" como paciente.

### Yadira manda fotos con varios pacientes mezclados
- Rubicita debe pedir aclaración: "Veo N fotos. ¿Son todas del mismo paciente o de varios?"
- Si son del mismo, procede normal. Si son de varios, pedir nombres por foto o por grupos.

### Yadira manda archivos no-imagen (PDF, DOCX)
- Rubicita los guarda igual, con la extensión original. Mortadelo los procesará con su parser correspondiente.
- Ej: `perico_1_25-08-2026.pdf`.

### La foto llega sin extensión o con extensión incorrecta
- Rubicita debe detectar el tipo MIME real (`file` command o similar) y renombrar con la extensión correcta.
- Si no puede detectar, dejarlo con la extensión que tenga y avisar a Yadira.

### Yadira envía un video o audio
- **Por ahora, Rubicita NO procesa videos ni audios.** Solo imágenes y PDFs. Si llega un video/audio, Rubicita avisa a Yadira: "Por ahora no proceso videos/audios. Si es un examen, mándalo como PDF o foto."

## Cómo se valida que Rubicita hizo bien su trabajo

1. **Mortadelo** (en su system prompt, `.opencode/agent/mortadelo.md` REGLA 8) lee las fotos del inbox, las matchea por nombre, y verifica que el patrón sea el correcto.
2. Si Mortadelo ve un archivo que NO matchea el patrón (ej. `WhatsApp Image 2026-08-25 at 15.20.24.jpeg`), lo reporta en `=== ADVERTENCIAS DE INFERENCIA ===` de la ficha y NO lo procesa.
3. Yadira (en su revisión final) puede pedirle a Miguel que revise el inbox si ve advertencias de ese tipo.

## Cambios futuros

- Cuando Rubicita tenga vision LLM, podría detectar el tipo de examen y proponer un nombre más descriptivo (ej. `perico_ecografia_hombro_25-08-2026.jpg`). Pero por ahora, **se mantiene el patrón simple** porque:
  1. Rubicita actual no puede verificar el tipo.
  2. Mortadelo ya detecta el tipo al transcribir.
  3. Yadira revisa la ficha final antes de cerrar, así que si hay un mismatch, lo corrige manualmente.

## Referencias

- `.opencode/agent/mortadelo.md` REGLA 8 — Cómo recibo los adjuntos (Mortadelo espera este patrón).
- `src/tools/generar_ficha_con_llm.py` `analizar_adjuntos_imagen()` — Matching de adjuntos por nombre.
- `src/pancho_skills/` — Pancho (login + navegación Rayen, rescata la nota).
- `docs/HANDOFF-MORTADELO-2026-08-07.md` — Handoff de Mortadelo.
- `docs/HANDOFF-PROYECTO-2026-08-24.md` — Handoff general del proyecto.
