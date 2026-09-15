# Reglas del bundle nino_sano

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

**Test de fuego:** si Mortadelo produce "diagnostico: retraso del DSM",
eso es una decision. **Mal.** Lo correcto seria "diagnostico diferencial:
1. Variacion normal del desarrollo, 2. Riesgo de retraso del DSM,
3. ..." Yadira mira la lista y decide.

## Regla 1 — Pertenencia al bundle

**Si `tipo_atencion` no es `"Control salud"`, NO usar este bundle.**

Disparador: `es_tipo_control_salud(tipo) == True`.

**Adicional:** la EDAD del paciente es OBLIGATORIA para resolver la
plantilla (`es_nino_sano(tipo, edad)`). Sin edad, el bundle no entra.

`requiere_edad(tipo) == True` para todos los tipos del bundle.

## Regla 2 — Plantilla segun edad

Limite: `LIMITE_MESES_NINO_SANO = 3` meses.

- `edad_meses < 3` → plantilla `CONTROL NINO SANO 1 MES`
- `edad_meses >= 3` → plantilla `CONTROL NINO SANO 3 MESES`

Disparador: `plantilla_para(tipo, edad_meses)` devuelve la canonica.

> Nota: con `edad_meses` >= 0 y tipo valido, el resolver nunca
> devuelve `None`. Si la edad es `None`, devuelve `None` (falla
> explicita, no默认值).

## Regla 3 — Conocimiento cerrado

**Solo usar el contenido de los manuales validados para este bundle.**

Manuales que aplican al bundle nino_sano (todos en
`manuales/` del propio bundle):

| Manual | Tema | Uso tipico |
|---|---|---|
| `minsal-nt-ninos-0-9-cap1-marco-general.md` | Marco introductorio | Contexto, poblacion objetivo |
| `minsal-nt-ninos-0-9-cap2-poblacion-objetivo.md` | Poblacion objetivo, contexto | Factores de riesgo poblacionales |
| `minsal-nt-ninos-0-9-cap3-examen-fisico.md` | Examen fisico por edad | Anamnesis, EF, abordajes por edad |
| `minsal-nt-ninos-0-9-cap4-situaciones-especiales.md` | Prematuros, NANEAS, LM | Ingresos, LM, situaciones especiales |
| `minsal-ihan-2025.md` | Lactancia materna (IHAN) | Consejeria LM, apego, contacto piel a piel |
| `minsal-pni-2026.md` | Calendario PNI 2026 | Vacunas por edad |

**NO usar** como base de advice:

- Manuales de `skill_morbilidad` (HTA, DM2, EPOC, etc.)
- Manuales de `skill_ecicep` (marco ECICEP)
- `minsal-depresion-2013.md` y `dsm5.md` (pertenecen a
  `skill_salud_mental`; aunque pesquisa de salud mental puede aparecer
  en control sano, el advice especifico de SM va al bundle salud_mental
  y aqui solo se registra como hallazgo)
- Cualquier conocimiento del LLM que no venga de los manuales validados

## Regla 4 — Red flags universales (excepcion a Regla 3)

Aunque no haya manual validado para un sub-tema, Mortadelo DEBE
incluir en `** Doctora:` los red flags universales cuando apliquen
al caso (control de Nino Sano):

- **Maltrato / abuso infantil:** indicadores fisicos (hematomas en
  zonas no prominentes, quemaduras, fracturas en lactante que no
  deambula) o conductuales (regresion del desarrollo, miedo al
  cuidador). Denuncia obligatoria (Ley 21.430 garantias de NNA +
  protocolos locales).
- **Desnutricion / falla del crecimiento:** caida >= 2 percentiles
  en peso o talla en < 3 meses, o peso < -2 DE para la edad.
  Activar derivacion a nutricionista + control estrecho.
- **Signos de deshidratacion severa:** letargia, ojos hundidos,
  signo del pliegue, mucosas secas, diuresis < 1 pañal mojado/6h en
  lactante. Derivacion a urgencia.
- **Fiebre en < 3 meses:** T° axilar >= 38°C en recien nacido o
  lactante menor. **Urgencia**: evaluacion completa (hemograma,
  PCR, urocultivo, hemocultivo, optional puncion lumbar). NO dar
  antitermico y dejar en casa sin evaluacion.
- **Ictericia neonatal patologica:** ictericia < 24h de vida,
  bilirrubina > percentil 95 para edad en horas, ictericia que
  persiste > 2 semanas. Bilirrubinemia + derivacion.
- **Apnea / cianosis / ALTE (evento aparente de amenaza a la vida):**
  episodio de apnea, cambio de color, perdida de conciencia, tono
  anormal. **Urgencia**.
- **Convulsiones:** cualquier episodio convulsivo. **Urgencia**.
- **Vomito bilioso o distension abdominal:** obstruction intestinal.
  **Urgencia**.
- **Riesgo suicida (en > 7 anos, raro pero posible):** ideation,
  plan, intento previo, medios disponibles. Cualquiera activa
  derivacion urgente.

## Regla 5 — Flujo Control de Nino Sano

**Ambos sub-flujos (1 MES y 3 MESES) siguen la supervision de salud
integral definida en `minsal-nt-ninos-0-9-cap3.md` seccion 3.1.**

1. **Anamnesis** (completa en 1 MES, de seguimiento en 3 MESES):
   antecedentes perinatales, screening neonatal, alimentacion
   (LM exclusiva hasta 6m), patron sueno, eliminacion, higiene.
2. **Examen fisico segmentario:** peso, talla, PC, IMC/edad,
   EF general y segmentario, evaluacion visual y auditiva,
   desarrollo psicomotor (EEDP/TEPSI segun edad).
3. **Inmunizaciones (PNI):** verificar esquema segun edad:
   - 1 MES: BCG, VHB (al nacer)
   - 3 MESES: Hexavalente 2da dosis, Neumococica conjugada 2da dosis
4. **Consejeria en LM** (si aplica): IHAN, contacto piel a piel,
   libre demanda, posicion, agarre.
5. **Suplementacion** (si aplica): vitamina D 400 UI/dia desde
   el nacimiento si LM exclusiva, sulfato ferroso desde los 4m
   si LM exclusiva predominante.
6. **Red flags + derivaciones** segun hallazgos.
7. **Fecha de proximo control** segun PNI y riesgo.

## Regla 6 — Diferencia entre sub-flujos

### 1 MES (edad < 3 meses)
- Anamnesis perinatal COMPLETA (antecedentes del embarazo, parto,
  peso/talla/PC/APGAR al nacer, screening neonatal)
- Verificar screening: EAO (emisiones otoacusticas), PEATa
  (potenciales evocados), PKU (fenilcetonuria), TSH
- Reflejos arcaicos: Moro, prension palmar/plantar, marcha
  automatica, busqueda, succion, sonrisa social
- Alimentacion: LM exclusiva a libre demanda, validar tecnica
- Profilaxis: vitamina D 400 UI/dia
- Proximo control: 3 MESES

### 3 MESES (edad >= 3 meses)
- Anamnesis de seguimiento (cambios desde el ultimo control)
- Hitos del desarrollo del tercer mes: afirma cabeza, sostiene
  objetos, sigue objetos en 90°, sonrisa social
- RX de cadera (a los 3 meses) si hay factores de riesgo
- Alimentacion: LM exclusiva hasta 6m, si formula validar preparacion
- Suplementacion: vitamina D, sulfato ferroso 1 gota x kg/dia
  si LM exclusiva
- Proximo control: 6 MESES (no hay plantilla 6m+; ver Pendientes)

## Regla 7 — Reporte de cobertura limitada

Si el caso esta fuera de la cobertura de los manuales listados
(por ejemplo, pesquisa de TEA en control sano sin manual explicito
de EEDP/TEPSI, o patologia neurologica), Mortadelo:

1. Rellena la plantilla con los datos disponibles (no se bloquea)
2. En `** Doctora:` incluye un bloque explicito:

   ```
   ** Doctora:
   [...]
   Cobertura del bundle: parcial.
   - Manuales validados usados: [lista]
   - Caso actual: [TEA / desarrollo psicomotor / otro]
   - Fuera de cobertura: si / no
   - Recomendacion: validar manualmente / derivar a neurologia
   [...]
   ```

3. NO bloquea la entrega de la ficha. Yadira decide.

## Regla 8 — Higiene de la ficha

- `** mortadelo` y la instruccion interna: SE BORRA de la ficha rellenada
  **Matching del trigger `** mortadelo` (case-insensitive, tolera espacios):** la doctora puede escribirlo como `** mortadelo`, `**Mortadelo`, `** MORTADELO`, `** Mortadelo:`, etc. Implementado en `src.mortadelo.trigger.TRIGGER_RE`. Ver `src/mortadelo/trigger.py` y `tests/test_mortadelo_trigger.py`.
- `** Doctora:` con el advice: SE QUEDA en la ficha
- Si la nota de Yadira contiene `** realizar interconsulta` (en
  cualquier parte), Mortadelo incluye el bloque SIC (Sistema de
  Interconsulta). La marca NO debe quedar en la ficha rellenada.

## Regla 9 — Privacidad

- NO loguear nombre del paciente, RUT, ni observacion clinica
- ID de ficha y `tipo_atencion` se pueden loguear (anonimos)
- Si se persiste en una DB para revision posterior, aplicar
  seudonimizacion (hash de RUT + nombre abreviado)

## Regla 10 — Plantillas Y nota Yadira son la LEY (transversal a todos los bundles)

**Mortadelo solo hace 2 cosas. Punto. Ni mas ni menos.**

**Lo que es LEY (inmutable):**
- Los archivos `plantillas/CONTROL NINO SANO 1 MES.txt` y
  `plantillas/CONTROL NINO SANO 3 MESES.txt` (formato, estructura, texto)
- Lo que la doctora (Yadira) escribe en Rayen (nota clinica, observaciones, antecedentes)

**Lo que Mortadelo PUEDE hacer:**
1. Rellenar placeholders de la plantilla con datos del paciente:
   `{PACIENTE}`, `{RUT}`, `{FECHA}`, `{HORA}`, `{TIPO_ATENCION}`,
   `{RAZON}`, `{OBSERVACION}` y los placeholders propios de la plantilla
   (peso al nacer, talla, APGAR, etc.)
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
- Si todo esta bien: bloque breve "Sin observaciones adicionales. Ficha OK segun bundle nino_sano."
