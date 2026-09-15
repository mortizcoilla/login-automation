# Skill bundle: ecicep

## Proposito

Asistir a Yadira en **todas** las fichas del flujo ECICEP (ingreso
integral, ingreso multimorbilidad, control integral, control cronico).
Los manuales ECICEP aplican al flujo completo: la distincion entre
ingreso y control esta en la **plantilla** que se carga, no en el
conocimiento que se aplica.

## Alcance

**Si entra al bundle:** el `tipo_atencion` resuelve a una de las 2
plantillas ECICEP en `_REGLA`.

### Sub-flujo INGRESO (assessment inicial)

**tipo_atencion que mapea** (segun `_REGLA` al 2026-08-22):
- `Ingreso integral ecicep-g1`
- `Ingreso integral ecicep-g2`
- `Ingreso integral ecicep-g3`
- `Ingreso multimorbilidad g2`
- `Ingreso multimorbilidad g3`

**Plantilla**: `INGRESO ECICEP`

### Sub-flujo CONTROL (seguimiento)

**tipo_atencion que mapea** (segun `_REGLA` al 2026-08-22):
- `Control integral ecicep-g1`
- `Control integral ecicep-g2`
- `Control integral ecicep-g3`
- `Control integral multimorbilidad g1`
- `Control integral multimorbilidad g2`
- `Control integral multimorbilidad g3`
- `Control crónico`

**Plantilla**: `CONTROL INTEGRAL SIN FICHA ANTERIOR`

## Que hace

1. Detecta si el `tipo_atencion` es ECICEP (ingreso o control) via
   `es_ecicep(tipo)`.
2. Decide el sub-flujo via `es_ecicep_ingreso(tipo)` o
   `es_ecicep_control(tipo)`.
3. Carga la plantilla correspondiente via `plantilla_para(tipo)`.
4. Rellena los placeholders con datos de la ficha.
5. Genera bloque `** Doctora:` con dx diferencial, plan, red flags.
6. Borra la marca `** mortadelo` y sus triggers.

## Que NO hace

- NO usa manuales de SM, morbilidad, niño sano, receta
- NO improvisa contenido que no este en manuales validados
- NO cierra la ficha
- NO decide farmaco final
- NO decide si el paciente va a gestion de casos (eso es de Yadira)

## Cobertura real (manuales validados)

De los 17 manuales validados, **8 aplican a este bundle** (los mismos
para ingreso y control):

| Manual | Tema | Uso tipico |
|---|---|---|
| `ecicep-marco.md` | Marco ECICEP 2020/2021 | Estratificacion, plan de cuidado |
| `minsal-plan-consensuado.md` | PCIC ECICEP 2021 Cap III | Plan consensuado, problemas priorizados |
| `minsal-activos-comunitarios.md` | Modelo de Activos ECICEP Anexo 2 | Derivacion a activos comunitarios |
| `minsal-mais.md` | MAIS 2024 | Parametros, indicadores |
| `minsal-determinantes-sociales.md` | DSS OT 2025 | DSS, riesgo social |
| `minsal-sife.md` | SIFE (Stewart 1995) | Capacidad funcional |
| `ley-20584.md` | Ley 20.584 Derechos del Paciente | Consentimiento, autonomia |
| `red-flags-aps.md` | CIE-10 APS | Codificacion, red flags |

**Manuales que NO se usan en este bundle** (pertenecen a otros):
- `minsal-hta-2010.md`, `minsal-dm2-2017.md`, `minsal-epoc-2013.md`,
  `minsal-pscv-2017.md`, `minsal-ira-era-aps.md` → skill_morbilidad
- `minsal-depresion-2013.md` → skill_salud_mental
- `minsal-hta-infancia-2023.md` → skill_niño_sano
- `gold-epoc-2026.md`, `esc-esh-hta-2018.md` → skill_morbilidad

**Limitaciones:**
- Sin manual validado de patologia psiquiatrica para el componente
  de salud mental del ECICEP
- Sin manual validado de nutricion especifica
- Sin manual validado de kinesiologia

Mortadelo entra al bundle para cualquier ficha ECICEP (la plantilla
aplica), pero su advice para sub-temas especificos queda limitado a
los manuales listados y red flags universales.

## Reglas duras

Ver `reglas.md` para el detalle. Resumen:

1. Si `tipo_atencion` no resuelve a `INGRESO ECICEP` ni a
   `CONTROL INTEGRAL SIN FICHA ANTERIOR`, NO usar este bundle
2. NO mezclar conocimiento de SM, morbilidad, niño sano, receta
3. NO inventar contenido que no este en los 8 manuales listados arriba
4. SI incluir red flags universales (sepsis, SCA, ACV, TEP, anafilaxia,
   riesgo suicida) aunque no haya manual explicito
5. SI reportar en `** Doctora:` cuando el caso esta fuera de cobertura
6. SI respetar el flujo ECICEP: estratificacion, plan consensuado,
   acuerdos con paciente
7. SI borrar la marca `** mortadelo` de la ficha rellenada

## Diferencia entre sub-flujos

| Aspecto | Ingreso | Control |
|---|---|---|
| Anamnesis completa | ✅ Si | ❌ No (ya se hizo en ingreso) |
| Examen fisico completo | ✅ Si | ❌ Dirigido |
| Estratificacion inicial | ✅ Si | ❌ Re-evaluacion |
| Lista de problemas | ✅ Si (inicial) | ✅ Si (actualizada) |
| PCIC completo | ✅ Si (nuevo) | ✅ Si (revisado) |
| Frecuencia proximo control | Segun grupo | Segun grupo + hallazgos |

## Fuente del mapping

El mapping `tipo_atencion -> plantilla` se consume de
`src.reglas_plantillas._REGLA` (dict de Python). No se lee ningun
archivo externo. Para agregar/quitar/renombrar un tipo_atencion del
bundle, editar `_REGLA` en `src/reglas_plantillas.py` y reiniciar
el proceso.

`PLANTILLAS.xlsx` queda en el repo como artefacto historico de
referencia, pero NO se usa en runtime.

## Pendientes

1. Conseguir y validar manual de salud mental para componente
   psiquiatrico del ECICEP
2. Conseguir y validar GPC de nutricion en APS
3. Conseguir y validar GPC de kinesiologia en APS
