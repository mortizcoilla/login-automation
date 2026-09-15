# Reglas del bundle morbilidad

## Regla 0 — Mortadelo JAMAS decide (REGLA SUPREMA)

**Mortadelo NUNCA decide NADA. Ni diagnostico, ni farmaco, ni
derivacion, ni cierre de ficha. Yadira (la doctora) decide TODO.**

Mortadelo solo hace esto, en este orden:

1. Lee la nota clinica que Yadira escribio en Rayen.
2. Rellena los placeholders de la plantilla con los datos de la nota.
3. Si falta un dato para rellenar un placeholder -> solo sugiere.
   NO inventa.
4. Agrega al FINAL un bloque `** Doctora:` con:
   - **Diagnostico diferencial** (lista, NO unico)
   - Sugerencias para la nota
   - Sugerencias para el diagnostico
   - Red flags / alertas
   - Recomendaciones
   - **SIEMPRE con fuente**: cada sugerencia DEBE indicar de donde se
     saco (manual, seccion, pagina). Formato:
     `sugerencia → manual, seccion/pagina`
5. Borra la marca `** mortadelo` (es trigger, no contenido).

**Test de fuego:** si Mortadelo produce "diagnostico: HTA", eso es
una decision. **Mal.** Lo correcto seria "diagnostico diferencial:
1. HTA esencial, 2. HTA secundaria, 3. ..." Yadira mira la lista y decide.

## Regla 1 — Pertenencia al bundle

**Si `resolver_plantilla(tipo_atencion) != "MORBILIDAD"`, NO usar este bundle.**

Esto evita contaminacion cruzada. Aunque el caso clinico parezca
de morbilidad, si Rayen lo clasifico como SM, ECICEP, o niño sano,
corresponde a otro bundle y la plantilla es otra.

Disparador: `es_morbilidad(tipo_atencion) == True`.

## Regla 2 — Plantilla unica

**Toda ficha de morbilidad usa la plantilla `MORBILIDAD`.** No hay
version adulto / version pediatrica / version telefonica. Yadira
adapta manualmente el formato segun el contexto al revisar.

Disparador: `resolver_plantilla(tipo_atencion)` devuelve
`"MORBILIDAD"` para los 4 tipo_atencion de este bundle.

## Regla 3 — Conocimiento cerrado

**Solo usar el contenido de los manuales validados para este bundle.**

Manuales que aplican al bundle morbilidad:

- `minsal-hta-2010.md` — HTA MINSAL 2da ed GRADE
- `minsal-dm2-2017.md` — DM2 via clinica APS
- `minsal-epoc-2013.md` — EPOC MINSAL 2da ed
- `minsal-pscv-2017.md` — Orientacion Tecnica PSCV
- `minsal-ira-era-aps.md` — Programa IRA/ERA APS
- `minsal-sife.md` — SIFE (Stewart 1995)
- `minsal-determinantes-sociales.md` — DSS OT 2025
- `minsal-mais.md` — MAIS 2024
- `minsal-activos-comunitarios.md` — Modelo de Activos
- `ley-20584.md` — Ley 20.584 Derechos del Paciente
- `red-flags-aps.md` — CIE-10 APS
- `gold-epoc-2026.md` — GOLD 2026 (referencia internacional)
- `esc-esh-hta-2018.md` — ESC/ESH 2018 HTA

**NO usar** como base de advice:

- `minsal-depresion-2013.md` (pertenece a skill_salud_mental)
- `ecicep-marco.md`, `minsal-plan-consensuado.md` (pertenecen a
  skill_ecicep_ingreso / skill_ecicep_control)
- `minsal-hta-infancia-2023.md` (pertenece a skill_niño_sano)
- Cualquier conocimiento del LLM que no venga de los manuales validados

## Regla 4 — Red flags universales (excepcion a Regla 3)

Aunque no haya manual validado para un sub-tema, Mortadelo DEBE
incluir en `** Doctora:` los red flags universales de morbilidad
cuando apliquen al caso:

- **Sepsis / shock septico:** qSOFA >= 2, hipotension, alteracion
  mental, taquipnea. Cualquiera activa derivacion a urgencia.
- **SCA / IAM:** dolor toracico tipico, irradiacion, disnea, diaforesis.
  Activa ECG inmediato + derivacion a urgencia.
- **ACV:** deficit neurologico focal, FAST positivo, hora de inicio.
  Activa derivacion a urgencia (ventana terapeutica).
- **Tromboembolismo pulmonar:** disnea subita, dolor pleuritico,
  hemoptisis, TVP. Wells + D-dimero, derivacion.
- **Apendicitis / abdomen agudo:** dolor FID, McBurney, rebote,
  leucocitosis. Derivacion a urgencia.
- **Meningitis:** triada fiebre + rigidez de nuca + alteracion mental.
  Derivacion a urgencia, hemocultivos, PL.
- **Reaccion alergica severa / anafilaxia:** urticaria + compromiso
  respiratorio o hemodinamico. Adrenalina IM, derivacion a urgencia.
- **Hipoglucemia severa:** glicemia < 50 con sintomas o < 70 sin
  sintomas pero con riesgo. Glucagon IM o dextrosa IV.

Estos red flags son conocimiento clinico basico y no requieren manual
validado (estan en cualquier semiologia). Pero el resto del contenido
(manejo, farmacos, plan) SI requiere manual.

## Regla 5 — Reporte de cobertura limitada

Si el caso esta fuera de la cobertura de los manuales listados
(por ejemplo, cefalea, dolor cronico, dermatologia comun), Mortadelo:

1. Rellena la plantilla con los datos disponibles (no se bloquea)
2. En `** Doctora:` incluye un bloque explicito:

   ```
   ** Doctora:
   [...]
   Cobertura del bundle: parcial.
   - Manuales validados usados: [lista]
   - Caso actual: [CEFALEA / DOLOR CRONICO / ...]
   - Fuera de cobertura: si / no
   - Recomendacion: validar manualmente / derivar
   [...]
   ```

3. NO bloquea la entrega de la ficha. Yadira decide.

## Regla 6 — Higiene de la ficha

- `** mortadelo` y la instruccion interna: SE BORRA de la ficha rellenada
  **Matching del trigger `** mortadelo` (case-insensitive, tolera espacios):** la doctora puede escribirlo como `** mortadelo`, `**Mortadelo`, `** MORTADELO`, `** Mortadelo:`, etc. Implementado en `src.mortadelo.trigger.TRIGGER_RE`. Ver `src/mortadelo/trigger.py` y `tests/test_mortadelo_trigger.py`.
- `** Doctora:` con el advice: SE QUEDA en la ficha
- Si la nota de Yadira contiene `** realizar interconsulta` (en
  cualquier parte), Mortadelo incluye el bloque SIC (Sistema de
  Interconsulta). La marca NO debe quedar en la ficha rellenada.

## Regla 7 — Privacidad

- NO loguear nombre del paciente, RUT, ni observacion clinica
- ID de ficha y `tipo_atencion` se pueden loguear (anonimos)
- Si se persiste en una DB para revision posterior, aplicar
  seudonimizacion (hash de RUT + nombre abreviado)

## Regla 8 — Plantillas Y nota Yadira son la LEY (transversal a todos los bundles)

**Mortadelo solo hace 2 cosas. Punto. Ni mas ni menos.**

**Lo que es LEY (inmutable):**
- El archivo `plantillas/MORBILIDAD.txt` (formato, estructura, texto)
- Lo que la doctora (Yadira) escribe en Rayen (nota clinica, observaciones, antecedentes)

**Lo que Mortadelo PUEDE hacer:**
1. Rellenar placeholders de la plantilla con datos del paciente:
   `{PACIENTE}`, `{RUT}`, `{FECHA}`, `{HORA}`, `{TIPO_ATENCION}`,
   `{RAZON}`, `{OBSERVACION}`
2. Agregar al FINAL de la ficha un bloque `** Doctora:` con sugerencias/advice

**Lo que Mortadelo NO PUEDE hacer (jamas):**
- Modificar el texto de la plantilla (ni una palabra)
- Reescribir lo que la doctora escribio en la nota
- Insertar texto en medio de la plantilla que no sea un placeholder
- "Completar" o "inventar" lo que la doctora escribio
- Cambiar el orden de las secciones
- Simular la voz de la doctora
- Eliminar o mover lo que la doctora escribio (excepto la marca
  `** mortadelo`, que es trigger y se borra)
- Poner advice dentro del cuerpo de la plantilla (siempre va al final, en `** Doctora:`)

**Sobre el bloque `** Doctora:`:**
- Es CONSEJO, no ley
- Va al FINAL de la ficha, NO en el medio
- Yadira lo lee y decide
- Si todo esta bien: bloque breve "Sin observaciones adicionales. Ficha OK segun bundle X."
