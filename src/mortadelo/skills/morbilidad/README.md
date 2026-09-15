# Skill bundle: morbilidad

## Proposito

Asistir a Yadira en fichas de morbilidad (consulta aguda o seguimiento
de cronicidad descompensada). Carga la plantilla `MORBILIDAD` y la
rellena con los datos del paciente + nota clinica de Yadira.

## Alcance

**Si entra al bundle:**
- `tipo_atencion` resuelve a `MORBILIDAD` en `_REGLA` (ver `mapping.py`)

**tipo_atencion que mapea** (segun `_REGLA` al 2026-08-22):
- `Morbilidad`
- `Morbilidad telefónica`
- `Morbilidad presencial`
- `Control crónico descompensado`

**Que hace:**
1. Carga la plantilla unica `MORBILIDAD`
2. Rellena los placeholders con datos de la ficha
3. Genera bloque `** Doctora:` con dx diferencial, plan, red flags
4. Borra la marca `** mortadelo` y sus triggers

**Que NO hace:**
- NO usa manuales de SM, ECICEP, niño sano, receta
- NO improvisa contenido que no este en manuales validados
- NO cierra la ficha
- NO decide farmaco final (solo sugiere, en `** Doctora:`)

## Cobertura real (manuales validados)

De los 17 manuales validados, **10 aplican a este bundle**:

| Manual | Tema | Uso tipico |
|---|---|---|
| `minsal-hta-2010.md` | HTA MINSAL 2da ed GRADE | Control PA, crisis hipertensiva |
| `minsal-dm2-2017.md` | DM2 vía clínica APS | Glicemia, HbA1c, pie diabetico |
| `minsal-epoc-2013.md` | EPOC MINSAL 2da ed | Disnea, tos cronica, exacerbacion |
| `minsal-pscv-2017.md` | Orientación Técnica PSCV | Riesgo CV, dislipidemia |
| `minsal-ira-era-aps.md` | Programa IRA/ERA APS | SBO niños, neumonia adulto |
| `red-flags-aps.md` | CIE-10 APS referencia rápida | Codificacion, red flags |
| `gold-epoc-2026.md` | GOLD 2026 (internacional) | EPOC severo, GOLD A/B/E |
| `esc-esh-hta-2018.md` | ESC/ESH 2018 HTA (internacional) | HTA refractaria, riesgo CV |
| `minsal-sife.md` | SIFE (Stewart 1995) | Capacidad funcional, discapacidad |
| `minsal-determinantes-sociales.md` | DSS OT 2025 | Contexto social, riesgo social |
| `minsal-mais.md` | MAIS 2024 | Indicadores, parametros |
| `minsal-activos-comunitarios.md` | Modelo de Activos | Derivacion a recursos comunitarios |
| `ley-20584.md` | Ley 20.584 Derechos del Paciente | Consentimiento, autonomia |

**Manuales que NO se usan en este bundle** (pertenecen a otros):
- `minsal-depresion-2013.md` → skill_salud_mental
- `ecicep-marco.md`, `minsal-plan-consensuado.md` → skill_ecicep_ingreso / skill_ecicep_control
- `minsal-hta-infancia-2023.md` → skill_niño_sano

**Limitaciones:**
- Sin manual validado de dolor cronico no-oncologico
- Sin manual validado de cefalea (puede usar SIFE + red flags)
- Sin manual validado de patologia osteoarticular no-GES
- Sin manual validado de patologia dermatologica comun

Mortadelo entra al bundle para cualquier ficha de morbilidad (la
plantilla aplica), pero su advice para los sub-temas no cubiertos
queda limitado a red flags universales y derivacion prudente.

## Reglas duras

Ver `reglas.md` para el detalle. Resumen:

1. Si `tipo_atencion` no resuelve a `MORBILIDAD`, NO usar este bundle
2. NO mezclar conocimiento de SM, ECICEP, niño sano, receta
3. NO inventar contenido que no este en los 10 manuales listados arriba
4. SI incluir red flags universales (sepsis, IAM, ACV, etc.) aunque
   no haya manual explicito
5. SI reportar en `** Doctora:` cuando el caso esta fuera de cobertura
6. SI borrar la marca `** mortadelo` de la ficha rellenada

## Fuente del mapping

El mapping `tipo_atencion -> plantilla` se consume de
`src.reglas_plantillas._REGLA` (dict de Python). No se lee ningun
archivo externo. Para agregar/quitar/renombrar un tipo_atencion del
bundle, editar `_REGLA` en `src/reglas_plantillas.py` y reiniciar
el proceso.

`PLANTILLAS.xlsx` queda en el repo como artefacto historico de
referencia, pero NO se usa en runtime.

## Pendientes

1. Conseguir y validar manual de cefalea en APS (MINSAL tiene guias)
2. Conseguir y validar manual de dolor cronico no-oncologico
3. Conseguir y validar manual de patologia osteoarticular comun
4. Decidir si se separa morbilidad telefonica en bundle propio (hoy
   cae aqui por la plantilla, pero el advice es muy diferente)
