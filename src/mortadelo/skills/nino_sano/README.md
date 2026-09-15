# Skill bundle: nino_sano

## Proposito

Asistir a Yadira en **controles de Nino Sano** de 0-9 anos en APS.
El bundle se dispara cuando el `tipo_atencion` es `"Control salud"`,
y la plantilla concreta se decide por **edad**:

- `edad_meses < 3` → plantilla `CONTROL NI\u00d1O SANO 1 MES`
- `edad_meses >= 3` → plantilla `CONTROL NI\u00d1O SANO 3 MESES`

Limite: `LIMITE_MESES_NINO_SANO = 3` meses (constante en
`src.reglas_plantillas`).

> Hoy solo hay 2 plantillas (1 MES y 3 MESES). Las edades intermedias
> (2, 4, 5, 6+ meses) usan la plantilla del rango mas cercano.
> Cuando Yadira agregue plantillas 6m / 12m / 18m, este routing se
> actualiza.

## Alcance

**Si entra al bundle:** `tipo_atencion == "Control salud"` y se conoce
la edad del paciente.

La **edad** es OBLIGATORIA. Sin edad, el bundle no se dispara
(`es_nino_sano` devuelve False y `plantilla_para` devuelve None). La
funcion `calcular_edad_meses(fecha_nacimiento, fecha_referencia)` vive
en `src/plantillas.py`; la fuente de la fecha de nacimiento la trae el
caller (Mora API / Rayen / DB local).

### Sub-flujo 1 MES (edad < 3 meses)

- `tipo_atencion`: "Control salud"
- `edad_meses` en {0, 1, 2}
- **Plantilla**: `CONTROL NI\u00d1O SANO 1 MES`
- **Foco**: antecedentes perinatales, screening neonatal (EAO, PEATa,
  PKU, TSH), reflejos arcaicos, LM exclusiva, vitamina D 400 UI/dia.

### Sub-flujo 3 MESES (edad >= 3 meses)

- `tipo_atencion`: "Control salud"
- `edad_meses` >= 3
- **Plantilla**: `CONTROL NI\u00d1O SANO 3 MESES`
- **Foco**: hitos del 3er mes (afirma cabeza, sigue objetos 90°,
  sonrisa social), RX de cadera, suplementacion (vit D + sulfato
  ferroso), verificar LM hasta los 6m.

## Que hace

1. Detecta si el `tipo_atencion` es Control de Nino Sano via
   `es_tipo_control_salud(tipo)`.
2. Pide la edad al caller (la logica de calculo esta en
   `calcular_edad_meses`).
3. Decide la plantilla via `plantilla_para(tipo, edad_meses)`.
4. Rellena los placeholders con datos de la ficha.
5. Genera bloque `** Doctora:` con dx diferencial, plan, red flags.
6. Borra la marca `** mortadelo` y sus triggers.

## Que NO hace

- NO usa manuales de morbilidad, ECICEP, salud_mental, receta
- NO improvisa contenido que no este en los 6 manuales validados
- NO cierra la ficha
- NO decide farmaco final (ej. suplementacion con hierro: solo
  sugiere, Yadira confirma dosis)
- NO decide derivaciones (ej. RX de cadera: solo sugiere, Yadira
  confirma indicacion)

## Cobertura real (manuales validados)

De los manuales del bundle, **6 archivos `.md`** son la base:

| Manual | Tema | Uso tipico |
|---|---|---|
| `minsal-nt-ninos-0-9-cap1-marco-general.md` | Marco introductorio | Contexto, poblacion objetivo |
| `minsal-nt-ninos-0-9-cap2-poblacion-objetivo.md` | Poblacion objetivo | Factores de riesgo poblacionales |
| `minsal-nt-ninos-0-9-cap3-examen-fisico.md` | Examen fisico por edad | Anamnesis, EF, abordajes por edad (el mas usado) |
| `minsal-nt-ninos-0-9-cap4-situaciones-especiales.md` | Prematuros, NANEAS, LM | Ingresos, LM, situaciones especiales |
| `minsal-ihan-2025.md` | Lactancia materna (IHAN) | Consejeria LM, apego, contacto piel a piel |
| `minsal-pni-2026.md` | Calendario PNI 2026 | Vacunas por edad |

Total: 825 paginas de manuales en `.md` (~1.9 MB), todos validados
contra los PDFs oficiales MINSAL DIPRECE / Salud Responde.

**Manuales que NO se usan en este bundle** (pertenecen a otros):
- `minsal-hta-2010.md`, `minsal-dm2-2017.md`, etc. → skill_morbilidad
- `minsal-hta-infancia-2023.md` → mencionado en morbilidad pero
  controla HTA, no control sano
- `minsal-depresion-2013.md`, `dsm5.md` → skill_salud_mental
- Documentos ECICEP → skill_ecicep

**Limitaciones:**
- Sin manual validado de EEDP/TEPSI explicito (la norma NT 0-9 los
  menciona pero no transcribe los items). Si Yadira detecta hallazgos
  de DSM, Mortadelo registra el hallazgo y sugiere dx diferencial;
  la aplicacion del EEDP/TEPSI queda a Yadira.
- Sin manual validado para pesquisa TEA en control sano (sugerir
  derivacion a neurologia si hay sospecha).
- Sin plantilla 6m+ / 12m+ (Yadira deberia crearlas cuando las
  necesite; ver Pendientes).

## Reglas duras

Ver `reglas.md` para el detalle. Resumen:

1. Si `tipo_atencion` no es "Control salud", NO usar este bundle
2. Si no hay edad, NO usar este bundle
3. NO mezclar conocimiento de morbilidad, ECICEP, salud_mental, receta
4. NO inventar contenido que no este en los 6 manuales listados arriba
5. SI incluir red flags universales (maltrato, desnutricion,
   deshidratacion, fiebre < 3m, ictericia patologica, ALTE,
   convulsiones) aunque no haya manual explicito
6. SI reportar en `** Doctora:` cuando el caso esta fuera de cobertura
7. SI respetar el flujo del control sano: anamnesis, EF segmentario,
   PNI, LM, suplementacion, red flags, proximo control
8. SI borrar la marca `** mortadelo` de la ficha rellenada

## Diferencia entre sub-flujos

| Aspecto | 1 MES | 3 MESES |
|---|---|---|
| Anamnesis perinatal completa | ✅ Si | ❌ No (ya se hizo) |
| Screening neonatal (EAO, PEATa, PKU, TSH) | ✅ Si | ❌ Verificar resultados previos |
| Reflejos arcaicos | ✅ Si (Moro, prension, etc.) | ❌ Re-evaluar tono |
| Hitos del desarrollo | Recien nacido | 3er mes (afirma cabeza, sigue 90°) |
| RX de cadera | ❌ | ✅ Si (factores de riesgo) |
| Vitamina D 400 UI/dia | ✅ Si (LM exclusiva) | ✅ Si (LM exclusiva) |
| Sulfato ferroso | ❌ | ✅ Si (LM exclusiva predominante) |
| Proximo control | 3 MESES | 6 MESES (sin plantilla, ver Pendientes) |

## Fuente del mapping

El mapping `tipo_atencion -> plantilla` se consume de
`src.reglas_plantillas._REGLA` (dict de Python). El caso especial
`"Control salud"` es un placeholder que se expande con `edad_meses`
via `_resolver_control_nino_sano`. No se lee ningun archivo externo.
Para agregar/quitar/renombrar un tipo_atencion del bundle, editar
`_REGLA` en `src/reglas_plantillas.py` y reiniciar el proceso.

`PLANTILLAS.xlsx` queda en el repo como artefacto historico de
referencia, pero NO se usa en runtime.

## Pendientes

1. **Resolver fuente de `fecha_nacimiento`**: Yadira define de donde
   sale (Mora API / Rayen / DB local). Mientras tanto, la funcion
   `calcular_edad_meses` existe y esta probada, pero el caller no la
   llama.
2. **Crear plantillas para 6m / 12m / 18m / 2-4a / 5-9a**: la NT 0-9
   las cubre pero Yadira no las ha escrito. Cuando las cree, el
   routing del bundle se actualiza (cambiar `_resolver_control_nino_sano`
   por algo mas granular, o agregar logica por edad).
3. **Validar EEDP/TEPSI**: la norma los menciona pero no transcribe
   los items. Si Mortadelo va a usarlos para advice, conseguir el
   manual validado de EEDP/TEPSI o las cartillas nacionales del DSM.
4. **Validar manual de pesquisa TEA en control sano**: hoy no hay.
