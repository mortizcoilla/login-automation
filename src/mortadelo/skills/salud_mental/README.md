# Skill bundle: salud_mental

## Proposito

Asistir a Yadira en fichas cuyo `tipo_atencion` pertenece a salud mental
(4 variantes: ingreso, ingreso multidisciplinario, control y consulta).
Carga la plantilla `INGRESO SALUD MENTAL SIN ECICEP` y la rellena con los
datos del paciente + nota clinica de Yadira.

## Alcance

**Si entra al bundle:**
- `tipo_atencion` resuelve a `INGRESO SALUD MENTAL SIN ECICEP` en `_REGLA`
- Tipos actuales (4, todos en `_REGLA`):
  - `Ingreso salud mental infantil`
  - `Ingreso multidisciplinario salud mental - infantil`
  - `Control salud mental infantil`
  - `Consulta salud mental`

**Que hace:**
1. Carga la plantilla unica `INGRESO SALUD MENTAL SIN ECICEP`
2. Rellena los placeholders con datos de la ficha
3. Genera bloque `** Doctora:` con:
   - Dx diferencial (apoyado en manuales validados)
   - Red flags psiquiátricos (suicidio, psicosis, mania, riesgo heterolesivo)
   - Recomendaciones de derivación (psicología, psiquiatría, hospitalización)
4. **Borra** la marca `** mortadelo` y sus triggers

**Que NO hace:**
- NO usa la Guía de HTA, ECICEP, nino sano, ni ningún manual de otro bundle
- NO improvisa contenido que no este en manuales validados
- NO cierra la ficha
- NO decide farmaco (solo sugiere, en `** Doctora:`)

## Cobertura real (manuales validados)

A 2026-08-22, este bundle tiene **9 manuales validados** (cobertura
amplia). Cobertura clínica:

| Sub-tema | Manual validado | Cobertura |
|---|---|---|
| **Depresion 15+ anos** | `minsal-depresion-2013.md` | ✅ GPC AUGE completa (113 págs) |
| **Trastornos de ansiedad** | `minsal-trastorno-ansioso-2018.md` | ✅ TEPT, panico, TAG, agorafobia (resumen ejecutivo) |
| **Consumo alcohol/drogas < 20** | `minsal-alcohol-drogas-menores20-2013.md` | ✅ AUDIT, CRAFFT, intervención breve (73 págs) |
| **Riesgo suicida (5+ anos)** | `programa-nacional-prevencion-suicidio-2013.md` | ✅ Programa Nacional completo (15 págs) |
| **DSM-5 (referencia general)** | `dsm5.md` | ✅ Criterios diagnosticos (1000 págs) |
| **Marco regulatorio** | `ley-21331-diprece-2022.md` | ✅ Ley 21.331, derechos del paciente (6 págs) |
| **Modelo comunitario** | `construyendo-salud-mental-2024.md` | ✅ Construyendo SM 2024 (78 págs) |
| **Programación APS** | `rpe11-programacion-sm-aps-2021.md` | ✅ RPE Nº11 (26 págs) |
| **Política nacional** | `plan-nacional-sm-2017-2025.md` | ✅ Plan Nacional SM (234 págs) |

## Red flags universales (se incluyen aunque no haya manual)

Mortadelo incluye siempre en `** Doctora:` los red flags psiquiátricos
universales (no requieren manual validado, son semiología básica):

- **Suicidio:** ideación, plan, intento previo, medios disponibles,
  aislamiento social. Cualquiera activa derivación urgente.
- **Psicosis aguda:** alucinaciones, ideas delirantes, desorganización
  del pensamiento. Derivación a urgencia.
- **Mania/hipomanía:** euforia patológica, disminución de sueño,
  grandiosidad, gasto impulsivo, riesgo de danos a terceros.
- **Riesgo heterolesivo:** agresión, impulsividad descontrolada,
  amenazas a terceros. Derivación a urgencia.

## tipo_atencion que mapea

Segun `_REGLA` (4 tipos, todos infantiles, todos a la misma plantilla):

- `Ingreso salud mental infantil`              → INGRESO SALUD MENTAL SIN ECICEP
- `Ingreso multidisciplinario salud mental - infantil` → INGRESO SALUD MENTAL SIN ECICEP
- `Control salud mental infantil`              → INGRESO SALUD MENTAL SIN ECICEP
- `Consulta salud mental`                      → INGRESO SALUD MENTAL SIN ECICEP

**Nota importante:** aunque los nombres digan "infantil", la plantilla
absorbe cualquier caso de salud mental que llegue por estos 4 tipos.
La adaptación pediatrica la hace Yadira al revisar. **NO** se puede
usar esta skill para tipos de atención fuera de estos 4 sin que Yadira
agregue el tipo a `_REGLA` y la plantilla correspondiente.

**Para ampliar a adulto (u otro rango etario):** Yadira debe:
1. Crear el nuevo `tipo_atencion` en Rayen
2. Crear la(s) plantilla(s) nueva(s) en `plantillas/`
3. Avisar a Mavis para que agregue el tipo a `_REGLA` apuntando a la
   plantilla nueva

## Fuente del mapping

El mapping `tipo_atencion -> plantilla` se consume de
`src.reglas_plantillas._REGLA` (dict de Python). No se lee ningún
archivo externo. Para agregar/quitar/renombrar un tipo_atencion del
bundle, editar `_REGLA` en `src/reglas_plantillas.py` y reiniciar el
proceso.

`PLANTILLAS.xlsx` queda en el repo como artefacto histórico de
referencia, pero NO se usa en runtime.

## Reglas duras

Ver `reglas.md` para el detalle. Resumen:

1. Si `tipo_atencion` no resuelve a `INGRESO SALUD MENTAL SIN ECICEP`,
   NO usar este bundle
2. NO mezclar conocimiento de morbilidad, ECICEP, nino sano, etc.
3. NO inventar contenido que no este en los 9 manuales validados
4. SI incluir red flags universales (suicidio, psicosis, manía, riesgo
   heterolesivo) aunque no haya manual explícito
5. SI reportar en `** Doctora:` cuando el caso esta fuera de cobertura
6. SI respetar el flujo SM: anamnesis, EF, screening, plan, derivación
7. SI borrar la marca `** mortadelo` de la ficha rellenada

## Pendientes

1. Conseguir y validar manual SM infantil específico (la GPC depresión
   2013 cubre parcialmente con seccion de adolescentes).
2. Cubrir TDAH, TEA, esquizofrenia, trastorno bipolar (manuales MINSAL
   no disponibles o no vigentes al 2026-08-22).
3. Si Yadira decide ampliar a adulto: crear `tipo_atencion` en Rayen +
   plantilla + agregar a `_REGLA`.
4. Versión completa de GPC Trastorno Ansioso 2018 (hoy solo se tiene
   el resumen ejecutivo de 16 págs; la versión completa tiene +200).
