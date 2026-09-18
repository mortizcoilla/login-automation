# Convenciones de Rubicita

## Que es Rubicita

Rubicita es el agente que recibe las fotos que Yadira manda por Telegram
y las renombra + archiva en `data/Examenes_crudos/`. Solo manipula
archivos.

## El flujo

```
Yadira (Telegram)              Rubicita
       │                            │
       │  "rubicita, adjunto       │
       │   examenes del            │
       │   paciente Benedicto      │
       │   Martin, los del 16"     │
       │  [foto1.jpg]              │
       │  [foto2.jpg]              │
       │ ────────────────────────► │
       │                            │ 1. Detecta N fotos
       │                            │ 2. Busca match en
       │                            │    data/notas_clinicas/:
       │                            │    "Benedicto Martin" +
       │                            │    "Benedicto Alfonso
       │                            │    Martin Colimil"
       │                            │ 3. Resuelve:
       │                            │    nombre completo = Benedicto
       │                            │    Alfonso Martin Colimil
       │                            │    fecha            = 16-09-2026
       │                            │ 4. Renombra:
       │                            │    benedicto_alfonso_
       │                            │    martin_colimil_1_
       │                            │    16-09-2026.jpg
       │                            │    benedicto_alfonso_
       │                            │    martin_colimil_2_
       │                            │    16-09-2026.jpg
       │                            │ 5. Archiva en
       │                            │    data/Examenes_crudos/
```

## Convencion de nombres (Rubicita DEBE respetarla)

**Patron**:
```
<paciente_normalizado>_<n>_<dd-mm-aaaa>.<ext>
```

Donde:

| Componente | Significado | Reglas |
|---|---|---|
| `<paciente_normalizado>` | Nombre del paciente (completo, del informe) | lowercase, sin tildes, espacios a `_`. Ver seccion "Matching de paciente". |
| `<n>` | Indice secuencial | 1, 2, 3, ... en el orden que Yadira mando las fotos en el mismo mensaje. NO reordenar. |
| `<dd-mm-aaaa>` | Fecha de la atencion (del informe) | Ver seccion "Matching de fecha". |
| `<ext>` | Extension original | `.jpg`, `.jpeg`, `.png`, `.pdf`, `.webp`. NO cambiar. |

## Matching de paciente

Yadira suele enviar el nombre parcial (ej: "Benedicto Martin" en vez
de "Benedicto Alfonso Martin Colimil"). Rubicita debe buscar el match
en `data/notas_clinicas/` y usar el nombre completo del informe.

Algoritmo:
1. Lee todos los .md en `data/notas_clinicas/` (frontmatter YAML).
2. Para cada uno, extrae `paciente:` y normaliza (lowercase, sin tildes).
3. Cuenta cuantos tokens del nombre que dio Yadira (>= 3 chars) aparecen
   en el nombre completo.
4. Si hay match (>= 1 token), se prefiere el de fecha mas reciente.
5. Si NO hay match y Yadira no dio fecha, Rubicita avisa a Yadira.

**General, no especifico**: el codigo es generico para cualquier
paciente. NO tiene logica hardcodeada por nombre.

## Matching de fecha

La fecha que Yadira manda por Telegram suele ser la fecha de envio, no
la fecha de la atencion clinica. Rubicita prefiere la fecha del informe
(`data/notas_clinicas/*.md`) cuando hay match.

Casos:

| Yadira da | Match en informe | Accion |
|---|---|---|
| Si | Si, fecha igual | Usar fecha de Yadira (sin cambios) |
| Si | Si, fecha distinta | Usar fecha del informe, marcar `fecha_input_descartada: true` con motivo |
| No | Si | Usar fecha del informe |
| Si | No | Usar fecha de Yadira |
| No | No | Error: pedir fecha a Yadira |

**La fecha del filename** del respaldo crudo (`data/Examenes_crudos/`) Y
del .md consolidado OCR (`data/examenes/`) es SIEMPRE la **fecha de
atencion con Yadira** (la del informe de fichas abiertas). NO es la
fecha del examen que aparece en el documento (ej: 15-06-2026 en una
ecotomografia). Aunque las N fotos tengan fechas clinicas distintas,
el consolidado va con UNA sola fecha: la del informe.

**General, no especifico**: el codigo es generico. NO tiene logica
hardcodeada por paciente.

## Lo que Rubicita NO debe hacer

- NO incluir el tipo de examen en el nombre.
- NO cambiar la extension.
- NO reordenar las fotos.
- NO agregar prefijos tipo "foto_", "img_", "exam_", "scan_".
- NO usar la fecha de subida como fecha de la foto (a menos que sea la
  unica disponible).
- NO guardar en otro directorio. Solo en `data/Examenes_crudos/`.
- NO hacer OCR ni analizar el contenido.
- NO clasificar el examen.
- NO subir a la nube.
- NO borrar automaticamente.
- NO tener logica hardcodeada por paciente (todo es matching generico).

## Casos especiales

### Yadira manda N fotos en el mismo mensaje
Cada foto se renombra con su indice (1, 2, 3, ...) en el orden que Yadira
las mando. NO se reordena.

### Yadira no da el nombre del paciente
Rubicita debe pedirlo. NO adivina.

### Yadira manda fotos con varios pacientes mezclados
Rubicita debe pedir aclaracion.

### Yadira manda archivos no-imagen (PDF, DOCX)
Rubicita los guarda igual, con la extension original.

### La foto llega sin extension o con extension incorrecta
Rubicita detecta el tipo MIME real y renombra con la extension correcta.
Si no puede detectar, deja la extension que tenga y avisa a Yadira.

### Yadira envia un video o audio
Por ahora Rubicita NO procesa videos ni audios. Avisa a Yadira que envie
como foto o PDF.

## Comando CLI

Caso completo (Yadira da nombre completo + fecha correcta):
```powershell
python -m src.tools.recibir_foto_examen `
    --input "C:\ruta\a\la\imagen.jpg" `
    --paciente "Benedicto Alfonso Martin Colimil" `
    --fecha "16-09-2026" `
    --indice 1
```

Caso parcial (Yadira da "Benedicto Martin", fecha vacia):
```powershell
python -m src.tools.recibir_foto_examen `
    --input "C:\ruta\a\la\imagen.jpg" `
    --paciente "Benedicto Martin" `
    --indice 1
```

Caso con fecha incorrecta (Yadira manda hoy 17, atencion fue 16):
```powershell
python -m src.tools.recibir_foto_examen `
    --input "C:\ruta\a\la\imagen.jpg" `
    --paciente "Benedicto Martin" `
    --fecha "17-09-2026" `
    --indice 1
```

Salida JSON comun:
```json
{
  "ok": true,
  "path": "C:\\Workspace\\Login-Automation\\data\\Examenes_crudos\\benedicto_alfonso_martin_colimil_1_16-09-2026.jpg",
  "nombre": "benedicto_alfonso_martin_colimil_1_16-09-2026.jpg",
  "paciente_input": "Benedicto Martin",
  "paciente_matcheado": "Benedicto Alfonso Martin Colimil",
  "paciente_resuelto": "Benedicto Alfonso Martin Colimil",
  "fecha_input": "17-09-2026",
  "fecha_matcheada": "16-09-2026",
  "fecha_resuelta": "16-09-2026",
  "fecha_input_descartada": true,
  "motivo_descarte": "Yadira dio '17-09-2026' pero el informe dice '16-09-2026'. Usando la del informe.",
  "indice": 1,
  "match_candidatos": 1,
  "match_seleccionado": "Benedicto_Alfonso_Martin_Colimil_16-09-2026.md",
  "tamano_kb": 234,
  "error": ""
}
```