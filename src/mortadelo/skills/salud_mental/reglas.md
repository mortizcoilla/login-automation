# Reglas del bundle salud_mental

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

## Regla 1 — Pertenencia al bundle

**Si `tipo_atencion` no esta en TIPO_ATENCION_SALUD_MENTAL, NO usar este bundle.**

Esto evita contaminacion cruzada. Aunque el caso clinico parezca
psiquiatrico, si Rayen lo clasifico como "Morbilidad" o "Control integral
cronico", corresponde a otro bundle y la plantilla es otra.

Disparador: `mapping.es_salud_mental(tipo_atencion) == True`.

## Regla 2 — Plantilla unica

**Toda ficha SM usa la plantilla `INGRESO SALUD MENTAL SIN ECICEP`.** No
hay version adulto / version infantil. Yadira adapta manualmente lo
pediatrico al revisar.

Disparador: `mapping.resolver_plantilla(tipo_atencion)` siempre devuelve
`"INGRESO SALUD MENTAL SIN ECICEP"` si el tipo es de este bundle.

## Regla 3 — Conocimiento cerrado

**Solo usar el contenido de los manuales validados para este bundle.**

A 2026-08-22, los manuales validados son **8 archivos `.md`**
(ubicados en `manuales/` del propio bundle):

### Cobertura clinica

| Manual | Tema | Poblacion |
|---|---|---|
| `minsal-depresion-2013.md` | GPC AUGE Depresion 15+ anos (2013) | Adolescentes y adultos (15+) |
| `minsal-trastorno-ansioso-2018.md` | GPC Trastorno Ansioso (2018, resumen ejecutivo) | Adultos |
| `minsal-alcohol-drogas-menores20-2013.md` | GPC AUGE Consumo alcohol y drogas (2013) | Adolescentes (< 20) |
| `dsm5.md` | DSM-5 (APA, 2014, referencia diagnostica general) | Todas las edades (referencia) |
| `programa-nacional-prevencion-suicidio-2013.md` | Programa Nacional de Prevencion del Suicidio (MINSAL 2013) | 5+ anos |
| `minsal-gpc-depresion-psicoterapia-2017.md` | Actualizacion en Psicoterapia (MINSAL 2017) | 15+ anos |

### Marco regulatorio y programatico

| Manual | Tema | Alcance |
|---|---|---|
| `ley-21331-diprece-2022.md` | Ley 21.331 — guia legal abreviada (DIPRECE 2022) | Marco regulatorio |
| `construyendo-salud-mental-2024.md` | Construyendo Salud Mental (MINSAL 2024) | Modelo comunitario |
| `plan-nacional-sm-2017-2025.md` | Plan Nacional de Salud Mental 2017-2025 (MINSAL) | Politica nacional |
| `rpe11-programacion-sm-aps-2021.md` | RPE N°11 Programacion SM APS (MINSAL 2021) | Criterios de programacion |

**NO usar** como base de advice:

- Manuales de morbilidad (HTA, DM2, EPOC, etc.)
- Manuales ECICEP
- Manual nino sano
- Cualquier conocimiento del LLM que no venga de los manuales validados

## Regla 4 — Red flags universales (excepcion a Regla 3)

Aunque no haya manual validado para un sub-tema, Mortadelo DEBE incluir
en `** Doctora:` los red flags universales de salud mental cuando
apliquen al caso:

- **Suicidio:** ideation, plan, intento previo, medios disponibles,
  aislamiento social. Cualquiera activa derivacion urgente.
- **Psicosis aguda:** alucinaciones, ideas delirantes, desorganizacion
  del pensamiento. Activa derivacion a urgencia.
- **Mania/hipomania:** euforia patologica, disminucion de sueno,
  grandiosidad, gasto impulsivo, riesgo de danos a terceros.
- **Riesgo heterolesivo:** aggression, impulividad descontrolada,
  amenazas a terceros. Activa derivacion a urgencia.

Estos red flags son conocimiento clinico basico y no requieren manual
validado (estan en cualquier semiologia psiquiatrica). Pero el resto
del contenido (manejo, farmacos, plan) SI requiere manual.

**Cobertura actual (2026-08-22):**
- ✅ Depresion 15+ anos (adolescente y adulto)
- ✅ Trastornos de ansiedad (adulto): TEPT, panico, TAG, agorafobia
- ✅ Consumo problematico de alcohol y drogas (< 20 anos)
- ✅ Riesgo suicida (5+ anos)
- ✅ Marco regulatorio (Ley 21.331) y programatico (RPE 11, Plan Nacional)
- ✅ Modelo comunitario (Construyendo SM 2024)
- ✅ DSM-5 como referencia diagnostica general

**Fuera de cobertura (aun):**
- ❌ TDAH (Ninos y adultos)
- ❌ TEA (Trastorno del Espectro Autista)
- ❌ Esquizofrenia y trastornos psicoticos (manejado a nivel de red flag)
- ❌ Trastorno bipolar (manejado a nivel de red flag)
- ❌ Trastornos de personalidad
- ❌ Demencia (solo referencia, no manejo)

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
- El archivo `plantillas/INGRESO SALUD MENTAL SIN ECICEP.txt` (formato, estructura, texto)
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
