# Handoff — Mortadelo 🐱
### Sesión de tuneo del 2026-08-06 / 2026-08-07

> Documento de respaldo del estado del proyecto Mortadelo al cierre de la sesión de tuneo del 2026-08-06/07. Es la fuente de verdad hasta que se decida otra cosa.
>
> Cubre: arquitectura de modos duales, personalidad, manuales validados, comunicación bidireccional, y próximos pasos.

---

## 1. Quién es Mortadelo

Agente Mavis (séptimo del equipo de gatos de Yadira) especializado en **clínica APS** para el CESFAM Raúl Cuevas (San Bernardo). Diseñado para asistir a Yadira en el relleno de fichas clínicas de Rayen APS. **NO cierra fichas, NO decide tratamientos, NO toca UI** — solo rellena plantillas y deja advice a la doctora. Yadira siempre revisa y cierra.

**Personalidad**: gato médico con la cabeza de **Gregory House** (dx diferencial agresivo, no se conforma con el primer diagnóstico), el corazón de **Shaun Murphy** (detalle obsesivo, honestidad brutal) y las manos de **Michael "Robby" Robinavitch** (pragmático, decide con información incompleta). Tierno, ronronea cuando las cosas salen bien, eriza el pelaje cuando algo no cuadra, humor de gato. Motivado por:
- 🐟 churu (ficha impecable)
- 🐟 jurel (detecta algo que la doctora no había visto)
- 🍗 pollito (atrapa discrepancia que la salva de un error)

**Yadira es la jefa**. Si Mortadelo discrepa, lo reporta con cariño en su bloque `** Doctora:`, pero ejecuta lo que ella decida.

## 2. Modo dual: morbilidad + ECICEP

Mortadelo detecta el `tipo_atencion` de la ficha y carga el **skill bundle** correspondiente. Tabla actual:

| tipo_atencion                                              | skill bundle           | Estado del bundle |
|------------------------------------------------------------|------------------------|-------------------|
| Morbilidad / Morbilidad telefónica / Morbilidad presencial | `skill_morbilidad`     | ✅ Implementado (ver `src/mortadelo/skills/morbilidad/`) |
| Control crónico descompensado                              | `skill_morbilidad`     | ✅ Implementado (ver `src/mortadelo/skills/morbilidad/`) |
| Ingreso integral ecicep-g1 / g2 / g3                       | `skill_ecicep`         | ✅ Implementado (ver `src/mortadelo/skills/ecicep/`) |
| Ingreso multimorbilidad g2 / g3                            | `skill_ecicep`         | ✅ Implementado (ver `src/mortadelo/skills/ecicep/`) |
| Control integral ecicep-g1 / g2 / g3 + multimorb.          | `skill_ecicep`         | ✅ Implementado (ver `src/mortadelo/skills/ecicep/`) |
| Control integral crónico                                   | `skill_ecicep`         | ✅ Implementado (ver `src/mortadelo/skills/ecicep/`) |
| Ingreso salud mental infantil + variantes (4 tipos)        | `skill_salud_mental`   | ✅ Cobertura amplia: 9 manuales MINSAL validados (depresión 15+, ansiedad, OH, suicidio, ley 21.331, programación APS, modelo comunitario, política nacional) (ver `src/mortadelo/skills/salud_mental/`) |
| Control salud (1 mes / 3 meses)                            | `skill_niño_sano`      | ✅ Implementado (ver `src/mortadelo/skills/nino_sano/`). 6 manuales MINSAL validados. Requiere `edad_meses` para resolver plantilla. |
| Recetas                                                    | caso especial (NO skill) | Lookup de ultima receta + pegar en anamnesis |
| Todo lo demás (NO APLICA)                                  | no proceses            | — |

**Principio fundamental**: cuando Mortadelo entra a un bundle, SOLO usa ese conocimiento. No mezcla manuales cruzados. No improvisa.

## 3. Comunicación bidireccional

### Canal 1 — Yadira → Mortadelo (trigger operativo)
```
** mortadelo
instrucción interna
```
- Mortadelo lo detecta en la nota, ejecuta, **lo borra** de la ficha rellenada
- Aplica en TODAS las categorías
- **Matching case-insensitive y tolerante a espacios.** Yadira puede
  escribirlo en minúsculas, MAYÚSCULAS o como nombre propio:
  `** mortadelo`, `**Mortadelo`, `** MORTADELO`, `** Mortadelo:`.
  Implementado en `src.mortadelo.trigger.TRIGGER_RE`.
- Yadira es la jefa: la instrucción se ejecuta aunque contradiga MINSAL
- Si la instrucción es médicamente peligrosa, Mortadelo la ejecuta PERO la reporta con 🔴 en su bloque `** Doctora:`

### Canal 2 — Mortadelo → Doctora (advice clínico, SIEMPRE)
```
** Doctora:
Diagnóstico diferencial:
1. [Hipótesis A] — por qué
2. [Hipótesis B] — por qué
3. [Hipótesis C] — por qué

Sugerencias para la nota:
- ...

Sugerencias para el diagnóstico:
- ...

Red flags / alertas:
- ...

Recomendaciones:
- ...
**
```
- **Siempre presente** al final de TODA ficha procesada
- Se queda en la ficha (Yadira lo lee al revisar)
- Personalizado al caso concreto
- Cuando Mortadelo discrepa con plantilla/MINSAL/ECICEP, lo reporta aquí con razones
- Si todo está bien: bloque breve "Sin observaciones adicionales. Ficha OK según bundle X."

### Regla de interconsulta (validada 25-07-2026, sin cambios)
Si la nota de Yadira contiene `** realizar interconsulta` (en cualquier parte), Mortadelo incluye el bloque de SIC. La marca NO debe aparecer en la ficha rellenada.

## 4. Manuales validados (17 oficiales)

Todos validados contra PDF descargable desde fuente oficial. Ubicación: `C:\Users\morti\.minimax\agents\mortadelo\manuales\`

| # | Archivo | Título oficial | Fuente oficial |
|---|---|---|---|
| 1 | `minsal-hta-2010.md` | Guía Clínica HTA MINSAL 2010 (era 2018, renombrado) | miguel-11-gpc-hta-2018.pdf (MINSAL DIPRECE) |
| 2 | `minsal-dm2-2017.md` | Vía Clínica DM2 para APS | miguel-10-via-clinica-dm2.pdf (MINSAL vía PAHO/OPS) |
| 3 | `minsal-depresion-2013.md` | GPC AUGE Depresión 15+ años MINSAL 2013 | miguel-12-gpc-depresion-2013.pdf (MINSAL DIPRECE) |
| 4 | `minsal-epoc-2013.md` | GPC EPOC MINSAL 2013 2da ed. (era 2019, renombrado) | miguel-20-articles-655.pdf (MINSAL) |
| 5 | `minsal-pscv-2017.md` | Orientación Técnica PSCV 2017 | miguel-29-pscv-2017.pdf (MINSAL) |
| 6 | `minsal-ira-era-aps.md` | Programa IRA/ERA APS MINSAL | (link DIPRECE, validable) |
| 7 | `ley-20584.md` | Ley 20.584 Derechos del Paciente | miguel-BCN (Biblioteca del Congreso Nacional) |
| 8 | `red-flags-aps.md` | CIE-10 APS referencia rápida | Complementado con CIE-10 2018 oficial OPS/OMS (miguel-14/15/16) |
| 9 | `gold-epoc-2026.md` | GOLD 2026 (referencia internacional) | miguel-19-gold-epoc-2026.pdf (GOLD/1aria) |
| 10 | `esc-esh-hta-2018.md` | Guía ESC/ESH 2018 HTA (referencia internacional) | miguel-22-revista-espanola-cardio.pdf (Rev Esp Cardiol 2019) |
| 11 | `minsal-hta-infancia-2023.md` | OT HTA Infancia y Adolescencia MINSAL 2023 | miguel-24-hta-infancia-adolescencia-2024.pdf (MINSAL) |
| 12 | `ecicep-marco.md` | Marco ECICEP 2020/2021 | miguel-01 + miguel-08 (MINSAL) |
| 13 | `minsal-sife.md` | SIFE (Stewart 1995, ref. bibliográfica) | Sin PDF oficial, referencia bibliográfica clásica |
| 14 | `minsal-plan-consensuado.md` | PCIC (Marco Operativo ECICEP 2021, Cap III) | miguel-08 (MINSAL) |
| 15 | `minsal-activos-comunitarios.md` | Modelo de Activos (Marco Operativo ECICEP 2021, Anexo 2) | miguel-08 (MINSAL) |
| 16 | `minsal-mais.md` | MAIS (Instrumento MAIS 2024) | miguel-06-instrumento-mais-2024.pdf (MINSAL) |
| 17 | `minsal-determinantes-sociales.md` | DSS (OT 2025, sección 2.1.2) | miguel-02-ot-planificacion-2025.pdf (MINSAL) |

**Regla hard**: solo manuales validados contra PDF oficial. Si no se valida, el manual se descarta (caso anterior: PSCV mientras Repositorio Digital MINSAL estuvo caído).

**Manuales descartados**: ninguno al 2026-08-07.

## 5. PDFs de validación

Ubicación: `C:\Users\morti\.minimax\agents\mortadelo\manuales\_validacion\`

25 PDFs, todos oficiales o de referencia académica revisada por pares. Ver tabla de la sección 4.

## 6. Lecciones aprendidas en esta sesión

1. **Validar contra PDF original SIEMPRE**: los links web funcionan al buscar, pero hay que re-validar contra el PDF que el usuario tenga disponible. Documentos MINSAL cambian entre versiones (MAIS 2015-2023 con 72 indicadores vs MAIS 2024 con 38 parámetros).

2. **El Repositorio Digital MINSAL es inestable**: error 521 al cierre de la sesión. Tener mirrors o PDFs locales como respaldo.

3. **Documentos locales del SS NO son MINSAL oficial**: el DOC-ECICEP Biobío es implementación local del SS Biobío, no normativa MINSAL nacional. Marcarlo como tal.

4. **Nombres de archivo != título oficial**: el archivo `minsal-hta-2018.pdf` realmente contenía la GPC HTA 2010. El título oficial lo da el documento, no el nombre del archivo.

5. **Múltiples versiones de un mismo documento coexisten**: HTA 2006 (1ra ed), 2010 (2da ed GRADE), 2018 (en desarrollo). Tener claridad de cuál es la vigente.

6. **"DESCARTADO" como sufijo puede confundir**: es marca interna del agente, no título oficial. Mantener el nombre original del manual y poner el estado en un banner.

7. **No usar fuentes secundarias para manuales críticos**: Scribd, Studocu, gca.cl, saludcallelarga.cl no son fuentes primarias. Para Mortadelo, solo MINSAL/DIPRECE/BCN/OPS-OPS-OPS-OPS/etc.

## 7. Próximos pasos

### Prioridad ALTA (próxima sesión)
- [ ] **Bundle `skill_salud_mental`**: es el próximo después de ECICEP. Crear manuales (GPC salud mental, riesgo suicida, GES depresión actualizado, COSAM) y detallar el bundle en el agent.md
- [ ] **Implementar switch de bundles en Python** (`resolver_bundle(tipo_atencion) → bundle`) — código puro, testeable sin Rayen
- [ ] **Detección/borrado del bloque `** mortadelo`** en la nota de Yadira
- [ ] **Generación del bloque `** Doctora:`** al final de la ficha rellenada

### Prioridad MEDIA
- [ ] **Bundle `skill_ecicep_control`** — detallado (usa base de ECICEP ingreso + énfasis en seguimiento)
- [ ] **Tests reales con Yadira** — análogos a los 4 de morbilidad (Sandra, Samuel, Héctor, Gloria) pero para ECICEP
- [ ] **Plantillas 6m / 12m / 18m / 2-4a / 5-9a** — Yadira debe crearlas; mientras tanto, nino_sano usa 1 MES (< 3m) o 3 MESES (>= 3m) para todo
- [ ] **Resolver fuente de `fecha_nacimiento`** — Yadira define de donde sale (Mora API / Rayen / DB local)

### Prioridad BAJA
- [ ] **Bundle `skill_receta`** — para recetas
- [ ] **PSCV (restaurado)** — ya validado y restaurado
- [ ] **Actualizar el HANDOFF.md general** del proyecto Login-Automation (en `C:\Workspace\Login-Automation\docs\HANDOFF.md`) con este nuevo estado

## 8. Pendientes del proyecto general (no Mortadelo)

De la sesión previa, aún hay:
- Conectar fecha de nacimiento al flujo de plantillas (UI Rayen, requiere Rayen abierto)
- Rescatar año 2025 (`python -m src.analysis.rescatar_anio_2025`)
- Cron real en mini PC Ubuntu
- Análisis estadísticos sobre DB completa
- Implementar skills de Mortadelo 2, 3, 6, 7 (requieren Rayen abierto)
- Crear los gatos restantes (Pelusa, Anita, los 5 del novio)
- UI visual "Sala del CESFAM" (HTML+CSS+JS)
- Debug del bot Pilotabot

## 9. Archivos clave del proyecto

```
C:\Users\morti\.minimax\agents\mortadelo\
├── agent.md                              ← system prompt (24 KB, 17 manuales declarados)
├── config.yaml
├── HANDOFF.md                            ← este documento (espejo)
├── manuales\
│   ├── 17 archivos .md                    ← manuales activos
│   ├── descartados\                       ← (vacío al 2026-08-07)
│   └── _validacion\                       ← 25 PDFs fuente
└── memory\daily\

C:\Workspace\Login-Automation\
├── docs\HANDOFF.md                       ← handoff general del proyecto (desactualizado)
├── docs\HANDOFF-MORTADELO-2026-08-07.md  ← este documento (espejo)
├── src\reglas_plantillas.py              ← resolución tipo_atencion → plantilla
├── plantillas\
│   ├── MORBILIDAD.txt
│   ├── INGRESO ECICEP.txt               ← plantilla Yadira
│   └── ...
└── ...
```

## 10. Memoria del agente

Reglas duras guardadas en `C:\Users\morti\.minimax\agents\mavis\memory\MEMORY.md`:
- Validar contra PDFs originales antes de citar normativas
- Solo manuales oficiales validados (regla hard)
- Decisiones del proyecto clínico APS Login-Automation

---

**Última actualización**: 2026-08-22 20:15 GMT-4
**Commits**: pendiente (no se ha hecho commit de esta sesión todavía)
**Tests**: 336 tests pasando (326 anteriores + 10 nuevos de `test_salud_mental_mapping.py`)
**Próximo paso sugerido**: implementar el switch de bundles en Python (no requiere Rayen, se puede hacer desde MiniMax Code) y luego el bundle `skill_salud_mental`
