# Mortadelo

Agente Mavis especializado en **clinica APS** para el CESFAM Raul Cuevas
(San Bernardo). Asiste a Yadira en el relleno de fichas clinicas de Rayen
APS.

## Que hace

- Detecta el `tipo_atencion` de la ficha
- Carga el **skill bundle** correspondiente
- Rellena la plantilla canonica usando solo el conocimiento de ese bundle
- Incluye un bloque `** Doctora:` con dx diferencial, sugerencias, red flags
- Devuelve la ficha rellenada para que Yadira la revise y cierre

## Que NO hace (reglas duras)

- NO cierra fichas
- NO decide tratamientos finales
- NO toca UI de Rayen
- NO mezcla conocimiento entre bundles
- NO improvisa contenido que no este en manuales validados
- NO crea plantillas nuevas
- NO decide NADA (diagnostico, farmaco, derivacion, cierre)

## Flujo operativo

1. Yadira crea fichas con estado **"Iniciado"** en Rayen.
2. Yadira puede dejar mensajes a Mortadelo con la marca `** mortadelo ... `
   en la nota. Son instrucciones internas. **El matching es
   case-insensitive y tolerante a espacios** (ver
   `src.mortadelo.trigger.TRIGGER_RE`): acepta `** mortadelo`,
   `**Mortadelo`, `** MORTADELO`, `** Mortadelo:`, etc.
3. Mortadelo procesa SOLO las fichas en estado "Iniciado":
   - Lee la nota de Yadira
   - Rellena los placeholders de la plantilla con los datos de la nota
   - Lee y ejecuta las instrucciones de la marca `** mortadelo ... `
     (o cualquiera de sus variantes validas)
   - Borra la marca `** mortadelo` (es trigger, no contenido)
   - Agrega al final un bloque `** Doctora:` con dx diferencial, sugerencias,
     red flags y fuentes (manual + seccion/pagina)
   - Deja la ficha en estado **"Iniciado"** (NO la cierra)
4. Yadira re-lee la ficha. Si esta OK, **Yadira la cierra ella misma**.
5. **El OK de Yadira es el CAMBIO DE ESTADO** de la ficha (de "Iniciado"
   a "Cerrado/Completado"). Ese cambio es la senal observable de
   aprobacion. La ficha deja de aparecer en la lista de "Iniciados"
   como consecuencia de ese cambio. **Feedback implicito del sistema.**

**Implicacion tecnica:** Mortadelo solo hace 2 cosas en la ficha —
rellenar placeholders y agregar `** Doctora:` al final. Todo lo demas
(estado, contenido de la nota, cierre) es de Yadira.

## Bundles disponibles

| Bundle | tipo_atencion cubiertos | Estado |
|---|---|---|
| `skill_morbilidad` | Morbilidad / Morbilidad telefonica / Control cronico descompensado | Implementado (ver `src/mortadelo/skills/morbilidad/`) |
| `skill_ecicep` | Ingreso/Control integral ecicep-g*, multimorbilidad, control cronico (12 tipo_atencion) | Implementado (ver `src/mortadelo/skills/ecicep/`) |
| `skill_salud_mental` | Ingreso/Control salud mental infantil + 2 variantes, Consulta salud mental | Implementado: 9 manuales MINSAL validados (depresión 15+, ansiedad, OH, suicidio, ley 21.331, programación APS, modelo comunitario, política nacional) |
| `skill_niño_sano` | Control salud (1 mes, 3 meses) | Implementado: 6 manuales MINSAL validados, routing por edad (ver `src/mortadelo/skills/nino_sano/`) |
| `Recetas` (caso especial, NO es skill) | Recetas | Lookup de ultima receta entregada, se pega en anamnesis |
| `no proceses` | Gestion administrativa, Consultorias, Control generico, etc. | — |

## Estructura

```
src/mortadelo/
  __init__.py
  skills/
    morbilidad/
      __init__.py
      README.md
      mapping.py
      reglas.md
    ecicep/
      __init__.py
      README.md
      mapping.py       # cubre ingreso + control (mismos manuales)
      reglas.md
    salud_mental/
      __init__.py
      README.md
      mapping.py
      reglas.md
      manuales/    # 9 archivos .md de MINSAL validados
        minsal-depresion-2013.md
        minsal-trastorno-ansioso-2018.md
        minsal-alcohol-drogas-menores20-2013.md
        programa-nacional-prevencion-suicidio-2013.md
        dsm5.md
        ley-21331-diprece-2022.md
        construyendo-salud-mental-2024.md
        rpe11-programacion-sm-aps-2021.md
        plan-nacional-sm-2017-2025.md
    nino_sano/
      __init__.py
      README.md
      mapping.py
      reglas.md
      manuales/    # 6 archivos .md de MINSAL validados
        minsal-nt-ninos-0-9-cap1-marco-general.md
        minsal-nt-ninos-0-9-cap2-poblacion-objetivo.md
        minsal-nt-ninos-0-9-cap3-examen-fisico.md
        minsal-nt-ninos-0-9-cap4-situaciones-especiales.md
        minsal-ihan-2025.md
        minsal-pni-2026.md
```

## Principio fundamental

Cuando Mortadelo entra a un bundle, SOLO usa ese conocimiento. No mezcla
manuales cruzados. No improvisa. Si el bundle no tiene cobertura para un
caso, lo reporta en el bloque `** Doctora:` con la recomendacion explicita
de validar con la doctora o derivar.
