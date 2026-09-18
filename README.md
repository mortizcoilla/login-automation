# Login-Automation

Proyecto para asistir a Yadira en el flujo clínico diario del CESFAM Raúl Cuevas (San Bernardo).

## Que hace

El sistema automatiza la cadena de ingreso de información clínica para que Yadira no se lleve trabajo a casa.

**Flujo (paso 1 al 6)**:

```
1. Yadira manda fotos de examenes por Telegram
2. Rubicita (agente Mavis) respalda las fotos en data/Examenes_crudos/
   y genera el consolidado OCR en data/examenes/exam_<pac>_<fecha>.md
3. Pancho (agente Mavis) scrapea Rayen y crea data/notas_clinicas/<pac>_<fecha>.md
4. Anita (agente Mavis) ejecuta src/analysis/actualizar_mes_actual.py
5. Anita ejecuta src/analysis/informe_fichas_abiertas.py
6. Anita ejecuta src/analysis/enriquecer_informe.py
```

**Paso 7** (rellenar la ficha a partir de la nota + info + examenes) está **eliminado**.
Será reescrito desde cero.

## Estructura del proyecto

```
C:\Workspace\Login-Automation\
├── data/
│   ├── notas_clinicas/         ← output de Pancho (paso 3)
│   ├── info_paciente/          ← input (metadata de Rayen)
│   ├── examenes/               ← output de Rubicita (consolidado OCR, paso 2)
│   └── Examenes_crudos/        ← output de Rubicita (fotos crudas, paso 2)
├── src/
│   ├── analysis/               ← pasos 4, 5, 6 (Anita)
│   ├── pancho_skills/          ← paso 3 (Pancho)
│   └── tools/
│       ├── crear_notas_clinicas.py     ← CLI paso 3
│       └── recibir_foto_examen.py      ← CLI paso 2
├── tests/                      ← tests de los scripts vivos
├── data/docs/                  ← documentacion del proyecto
└── AGENTS.md                   ← reglas durables
```

## Comandos del flujo

```bash
# Paso 2: Rubicita (manual, lo normal es por Telegram)
python -m src.tools.recibir_foto_examen \
    --input "C:/ruta/a/foto.jpg" \
    --paciente "Nombre Apellido" \
    --fecha "dd-mm-yyyy" \
    --indice 1

# Paso 3: Pancho
python -m src.tools.crear_notas_clinicas --todos --user yadira

# Paso 4: Anita
python -m src.analysis.actualizar_mes_actual yadira

# Paso 5: Anita
python -m src.analysis.informe_fichas_abiertas

# Paso 6: Anita
python -m src.analysis.enriquecer_informe
```

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

- `AGENTS.md` — reglas durables para cualquier agente que entre al workspace.
- `data/docs/CREDENCIALES.md` — API keys y credenciales.
- `data/docs/HANDOFF-PROYECTO-2026-08-23.md` — handoff general del proyecto.
- `data/docs/rubicita-conventions.md` — convenciones de Rubicita.

## Agentes Mavis (fuera de este proyecto)

Los agentes en `C:\Users\morti\.minimax\agents\` son la cara visible para Yadira:

- `agents/rubicita/` — recibe fotos por Telegram, invoca `recibir_foto_examen.py`.
- `agents/pancho/` — login + scraping de Rayen, invoca `crear_notas_clinicas.py`.
- `agents/anita/` — orquestacion diaria, invoca scripts de `src/analysis/`.
- `agents/mortadelo/` — **ELIMINADO** (paso 7 se reescribirá desde cero).