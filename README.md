# Login-Automation

Proyecto para asistir a Yadira en el flujo clínico diario del CESFAM Raúl Cuevas (San Bernardo).

## Que hace

Automatiza la cadena de ingreso de informacion clinica para que Yadira no
se lleve trabajo a casa.

**Flujo obligatorio diario** (orden real de dependencias 4->5->3->6):

```
python -m src.analysis.actualizar_mes_actual yadira && python -m src.analysis.informe_fichas_abiertas && python -m src.tools.crear_notas_clinicas --todos && python -m src.analysis.enriquecer_informe
```

1. (paso 4) Actualiza el mes desde Rayen -> data/analysis/fichas_completo.db
2. (paso 5) Genera el informe base -> data/analysis/informe_fichas_abiertas_<MM-YYYY>.txt
3. (paso 3) Scrapea las fichas del informe -> notas_clinicas/, info_paciente/, anamnesis/
4. (paso 6) Enriquece el informe: motivo, edad decimal, Examenes, Interconsulta, Indicaciones

**Flujo opt-in por paciente** (cuando Yadira envia examenes por Telegram):
1. Yadira manda fotos.
2. (paso 2a) Rubicita archiva en data/examenes_crudos/ (sin OCR local).
3. (paso 2b) `python -m src.tools.consolidar_examenes --paciente "Nombre"`:
   transcripcion via API de vision z.ai -> data/examenes/exam_<pac>_<fecha>.md.

**Paso 7** (rellenar fichas): eliminado, pendiente de reescritura.

## Estructura (refactor 2026-09-18)

```
src/
  core/       kernel: fechas dd-mm-yyyy, nombres, tipos_atencion, rutas
  rayen/      Selenium: navegador, navegacion, tabla + extraccion/ (6 modulos)
  notas/      escritura: nota_clinica, info_paciente, anamnesis, modelos
  informes/   pasos 4-6: mes, base, enriquecer + parser UNICO del informe
  examenes/   paso 2b: vision_api (z.ai), consolidar
  analysis/   CLIs finos (paths estables del flujo diario)
  tools/      CLIs: crear_notas_clinicas, recibir_foto_examen,
              consolidar_examenes, informe_tecnico
  pancho_skills/  capa skills sobre rayen
  queue_store.py + anita/  aprobaciones (base del futuro paso 7)
docs/REQUISITOS.md  matriz de trazabilidad REQ <-> codigo <-> tests
tests/              339 tests (pytest; mockean Selenium, sin login)
```

## Verificacion

```
pytest --cov     # suite + gate de coverage (core/notas/informes/examenes)
ruff check src tests && ruff format --check src tests
mypy src
```

CI (.github/workflows/ci.yml) corre todo esto en Python 3.10/3.11/3.12.

## Convenciones

- `data/notas_clinicas/<pac>_<fecha>.md` — input de Yadira a Pancho.
- `data/examenes/exam_<pac>_<fecha>.md` — consolidado OCR de Rubicita.
- `data/Examenes_crudos/<pac>_<n>_<dd-mm-aaaa>.<ext>` — fotos crudas.
- Los triggers `** Mortadelo` en la nota activan columnas del informe enriquecido: Examenes, Interconsulta, Indicaciones.

## Que NO hay

- **Mortadelo / paso 7**: eliminado. Reescritura pendiente.
- **Plantillas / data/plantillas/**: eliminadas en sesion 2026-09-17.
- **scripts_temp/**: eliminado.
- **.trash/, data/prompts*/**: eliminados.

## Documentacion

- `docs/DIAGRAMAS.md` — pipeline y arquitectura en diagramas (se actualiza en cada cambio).
- `docs/REQUISITOS.md` — matriz de trazabilidad REQ <-> codigo <-> tests.

- `data/docs/CREDENCIALES.md` — API keys y credenciales.
- `data/docs/HANDOFF-PROYECTO-2026-08-23.md` — handoff general del proyecto.
- `data/docs/rubicita-conventions.md` — convenciones de Rubicita.

## Agentes Mavis (fuera de este proyecto)

Los agentes en `C:\Users\morti\.minimax\agents\` son la cara visible para Yadira:

- `agents/rubicita/` — recibe fotos por Telegram, invoca `recibir_foto_examen.py`.
- `agents/pancho/` — login + scraping de Rayen, invoca `crear_notas_clinicas.py`.
- `agents/anita/` — orquestacion diaria, invoca scripts de `src/analysis/`.
- `agents/mortadelo/` — **ELIMINADO** (paso 7 se reescribirá desde cero).