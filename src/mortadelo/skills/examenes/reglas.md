# Reglas del skill examenes (lectura de examenes adjuntos)

## Regla 0 — Privacidad ante todo (REGLA SUPREMA)

Los examenes adjuntos contienen PII del paciente (nombre, RUN, edad,
resultados clinicos). El skill examenes JAMAS envia el examen a
servicios externos (cloud, OCR en la nube, vision LLM remoto).
La lectura es 100% local.

## Regla 1 — Mortadelo NO interpreta, solo lee

La funcion `leer_examen()` retorna los datos extraidos del examen
(structured). La interpretacion clinica (ej. "hipoacusia bilateral
significativa, requiere derivacion") la hace Yadira al revisar el
output. Mortadelo entrega los datos crudos y una "interpretacion
basica" que Yadira valida.

**Test de fuego:** si el output dice "diagnostico: hipoacusia
neurosensorial severa", eso es interpretacion automatica. **Mal.**
Lo correcto: "datos del examen: OD 64%, OI 84%. Yadira diagnostica
e indica manejo."

## Regla 2 — Formatos soportados

| Formato | Lectura | Estado |
|---|---|---|
| JPG / PNG (foto) | OCR (pytesseract / easyocr) | Pendiente (stub hoy) |
| PDF | pdfplumber o PyMuPDF | Pendiente (stub hoy) |
| DICOM (imagen medica) | pydicom | No soportado aun |

## Regla 3 — Salida estructurada

La funcion `leer_examen(ruta)` retorna un dict con campos especificos
por tipo de examen. Para audiometrias: OD/OI discriminacion, via
aerea/osea, impedanciometria, tinnitus, conclusion. Para laboratorio:
parametros fuera de rango marcados.

## Regla 4 — Cuando Yadira NO debe transcribir

Si el examen esta adjunto (foto o PDF) y el skill puede leerlo,
Yadira NO necesita transcribir manualmente. Mortadelo extrae los
datos. La nota de Yadira solo debe mencionar que el examen esta
adjunto (ej. "adjunto audiometria 10-07-2026"), no transcribirlo.

## Regla 5 — Errores de lectura

Si el OCR/vision falla (imagen borrosa, PDF corrupto), Mortadelo
reporta el error explicitamente y NO inventa datos. Mejor pedir a
Yadira que revise el adjunto o lo transcriba en su lugar.

## Regla 6 — Manual validado, no inventar

Si el examen es de un tipo NO conocido (ej. espirometria, Holter),
Mortadelo retorna dict vacio y reporta "tipo de examen no reconocido".
Yadira lo procesa manualmente.

## Regla 7 — Integracion con bundles

El output del skill `examenes` se integra al bloque `** Mortadelo ->`
del bundle activo (morbilidad, ecicep, salud_mental, nino_sano) como
un bloque `[EXAMEN ADJUNTO: <tipo>]` con los datos estructurados.
