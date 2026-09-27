# DIAGRAMAS — Pipeline y arquitectura

Referencia visual del proyecto. Fuente de verdad de reglas:
`docs/REQUISITOS.md`. Este archivo se ACTUALIZA EN CADA CAMBIO de flujo,
estructura o comando (ver "Regla de mantenimiento" al final).

Ultima actualizacion: 2026-09-21 (paso 8 cargar_ficha como opt-in
independiente; limite del flujo compartido paso 3/paso 8 en
`<div>Atencion actual</div>`).

---

## 1. El pipeline diario (flujo de datos)

Orden real de dependencias 4 -> 5 -> 3 -> 6 -> 7 (REQ-008).

```
                        ┌─────────────────────────────────────────────────┐
                        │  FLUJO OBLIGATORIO DIARIO (orden 4 → 5 → 3 → 6) │
                        └─────────────────────────────────────────────────┘

  Yadira trabaja en Rayen (abre/cierra fichas durante el dia)
        │
        ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ (4) python -m src.analysis.actualizar_mes_actual yadira             ┃
┃     CLI fino ──► src/informes/mes.py ──► src/rayen/* (Selenium)     ┃
┃     Login a Rayen + barrido del mes dia por dia                     ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                           ▼
             data/analysis/fichas_completo.db   (mes en curso, SQLite)
                           │
                           ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ (5) python -m src.analysis.informe_fichas_abiertas        [OFFLINE] ┃
┃     CLI fino ──► src/informes/base.py  (lee la DB, sin login)       ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                           ▼
        data/analysis/informe_fichas_abiertas_<MM-YYYY>.txt
        (informe BASE: 5 columnas, solo estado 'Iniciado')
                           │
                           │  es la LISTA de pacientes del batch
                           ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ (3) python -m src.tools.crear_notas_clinicas --todos --user yadira  ┃
┃     Orquestador ──► src/informes/parser.py (lee el informe)         ┃
┃                  ──► src/rayen/tabla.py    (busca paciente, REQ-019)┃
┃                  ──► src/rayen/extraccion/ (7 secciones, REQ-024)   ┃
┃                     └─ ECICEP primero → identif. → historial 6m →   ┃
┃                        atencion actual → dx → plan                  ┃
┃                  ──► src/notas/ (escribe los 3 documentos)          ┃
┃     Reset de sesion cada 8 fichas (REQ-017)                         ┃
┃     REQ-090: higiene de pestañas por paciente via src/rayen/        ┃
┃     pestanas.py — el limite de 8 pestañas de Rayen es SERVER-SIDE;  ┃
┃     ante el modal 'Supero maximo de pestañas' se libera el tablero  ┃
┃     y se reintenta. Desbloqueo manual:                              ┃
┃     python -m src.tools.cerrar_pestanas_rayen --user yadira         ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                           ▼
        data/notas_clinicas/<pac>_<fecha>.md      (nota completa)
        data/info_paciente/info_<pac>_<fecha>.md  (vista rapida, sin anamnesis)
        data/anamnesis/anam_<pac>_<fecha>.md      (respaldo crudo + motivo)
                           │
                           ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ (6) python -m src.analysis.enriquecer_informe            [OFFLINE] ┃
┃     CLI fino ──► src/informes/enriquecer.py                         ┃
┃     Lee el informe base + las notas: motivo, edad decimal (REQ-041),┃
┃     y Examenes/Interconsulta/Indicaciones desde el trigger          ┃
┃     `** Mortadelo` dentro de la nota (REQ-042)                      ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                           ▼
        informe_fichas_abiertas_<MM-YYYY>.txt  (AHORA ENRIQUECIDO, 8 columnas)
                           │
                           ▼
+---------------------------------------------------------------+
| (7) python -m src.tools.mortadelo --todos            [LLM]    |
|     src/mortadelo/: 2 llamadas por paciente (opencode CLI,    |
|     cascada de modelos)                                       |
|     1) prompt ficha -> ENSAMBLADOR: el CODIGO arma con        |
|        garantias (base byte-identica + llenados + ortografia  |
|        validada + trigger fuera + INDICACIONES/INTERCONSULTA  |
|        si el trigger las pidio) -> validacion (5 reglas)      |
|     2) prompt informe -> encabezado con MODELO USADO por      |
|        codigo                                                 |
+----------------------------+---------------------------------+
                             v
   data/fichas_generadas/ficha_<pac>_<fecha>.md          (producto 1)
   data/informes_trazabilidad/informe_trazabilidad_*.md (producto 2)
                             |
                             |  (paso 8: parte final de la cadena diaria)
                             v
+---------------------------------------------------------------+
| (8) python -m src.tools.cargar_ficha --todos / --paciente...  |
|     Lee ficha_<pac>_<fecha>.md (paso 7, OneDrive)             |
|     Login Rayen -> Pacientes citados -> doble click           |
|     (flujo compartido con paso 3 via src/rayen/flujos/        |
|     apertura_ficha.py, entrar_atencion=True)                   |
|     Editor anamnesis: descartar vieja -> Agregar! -> llenar   |
|     (motivo + ficha completa) -> GUARDAR AUTOMATICO (REQ-073) |
|     Sesion reciclada cada 8 fichas; higiene de pestanas       |
+----------------------------+---------------------------------+
                             v
   data/trazabilidad_carga/carga_<ts>.json  (carga por paciente)
                             |
                             v
+---------------------------------------------------------------+
| (A) python -m src.tools.archivar_fichas  (REQ-097)            |
|     Pacientes que ya NO estan en el informe (cerrados en      |
|     Rayen) se mueven de las 5 carpetas activas al archivo.    |
|     Guardia: sin informe fresco no se mueve nada. Nada se     |
|     borra (colisiones _v2).                                   |
+----------------------------+---------------------------------+
                             v
   OneDrive/Login-Automation/archivados/<MM-AAAA>/   (plano por mes)

   Layout OneDrive (REQ-089/097):
     anamnesis/ examenes/ fichas_generadas/ informes_trazabilidad/
       -> SOLO pacientes del informe (activos)
     archivados/09-2026/ ...  -> cerrados, por mes de cierre
     papers/                  -> papers traducidos (REQ-096)
     informe_fichas_abiertas_<MM-YYYY>.txt (raiz; unico, REQ-091)
```

## 4. Regla del limite compartido paso 3 vs paso 8

Ambos flujos comparten la apertura de ficha (login, box, Pacientes
citados, filtrar fecha, doble click sobre el nombre). El limite del
flujo compartido es:

    <li class="verticalnav-tab verticalnav-tab-active">
      <div>Atencion actual</div>
    </li>

Desde el refactor REQ-093 el limite es un PARAMETRO del flujo
compartido (`abrir_ficha_por_nombre(entrar_atencion=)`):
- **Paso 3** (`entrar_atencion=False`): la apertura TERMINA en la
  vista 'Historia clinica' — identificacion e historial se extraen
  desde ahi, y el click a 'Atencion actual' lo hace la extraccion
  despues (REQ-093; antes el waiter cambiaba de vista antes de
  extraer y las notas salian sin tabla).
- **Paso 8** (`entrar_atencion=True`, default): entra a 'Atencion
  actual' hasta el editor (lapiz/Agregar!) para reemplazar la
  anamnesis y Guardar automatico.

## 5. Papers semanales interactivos (REQ-096, sabado 09:00)

```
  Tarea Windows LoginAutomation-PapersSabado (sab 09:00)
        |
        v
  python -m src.estudios.oferta_papers
        |-- analizar_notas (notas -> capitulo mas atendido)
        |-- buscar_papers (PubMed, top 3 del tema)  [offline: no Rayen]
        |-- mini-resumenes (LLM papers: mimo rapido)
        |-- sendMessage directo (avisos.enviar) -----> Yadira (Telegram)
        '-- guarda data/estados/oferta_papers.json (para el 1/2/3)
        |
        v
  Yadira responde "1" / "2" / "3"  (bot Rubicita, handlers/papers.py)
        |
        v
  descargar_texto: PMC completo si es libre; si no, abstract (efetch)
        |
        v
  traducir_paper (LLM papers: glm-5.3-flash free -> mimo respaldo;
                  NO la cascada z.ai de mortadelo)
        |
        v
  OneDrive/Login-Automation/papers/paper_<pmid>_<fecha>.md
        + resumen respondido en el chat
  Yadira responde "enviar" -> el .md llega como documento al telefono
```

LLM de papers (src/estudios/gemini_texto.py): motor gemini si hay
credito (prepago agotado 27-09) con respaldo opencode FREE. OJO
opencode: prompts a UNA linea (el CLI trunca argv en saltos de linea),
--standalone y cwd neutral (si no, el modelo lee el codigo del repo).

---

## 2. El flujo opt-in de examenes (por paciente, cuando hay fotos)

REQ-009 (opt-in) / REQ-012 (2a, archivar) / REQ-047 (2b, vision z.ai).

```
  Yadira manda fotos por Telegram (1)
        │
        ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ (2a) Rubicita / src/tools/recibir_foto_examen              ┃
┃      Resuelve nombre+fecha contra notas_clinicas/           ┃
┃      (la fecha del informe es la verdad, REQ-013)           ┃
┗━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                   ▼
   data/examenes_crudos/<pac_norm>_<n>_<dd-mm-aaaa>.jpg  (copia bit a bit)
                   │  (optativo, cuando lo pides)
                   ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ (2b) python -m src.tools.consolidar_examenes               ┃
┃             --paciente "Nombre Apellido"                   ┃
┃      src/examenes/vision_api.py ──► API z.ai (GLM vision)  ┃
┃      Transcripcion FIEL: el modelo NO interpreta (REQ-001) ┃
┗━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                   ▼
   data/examenes/exam_<pac>_<fecha>.md  (nunca sobrescribe: _v2, _v3...)
```

## 3. La arquitectura de capas (quien puede usar a quien)

Las flechas solo bajan: una capa nunca importa a las capas superiores.

```
┌────────────────────────────────────────────────────────────────┐
│  CLI (paths estables — la interfaz que corre Yadira/Mavis)     │
│  src/analysis/*  src/tools/*                                   │
└──────────────┬─────────────────────────────────────────────────┘
               ▼ usa
┌────────────────────────────────────────────────────────────────┐
│  informes              │  notas              │  examenes        │
│  parser (UNICO)        │  nota_clinica       │  vision_api(z.ai)│
│  mes (paso 4)          │  info_paciente      │  consolidar      │
│  base (paso 5)         │  anamnesis, modelos │                  │
└──────────┬─────────────┴─────────┬───────────┴────────┬─────────┘
           ▼                       ▼                    │
┌─────────────────────────────────────────────┐        │
│  rayen (todo lo que toca Rayen/Selenium)    │        │
│  navegador │ navegacion │ tabla             │        │
│  extraccion/ (6 modulos por seccion)        │        │
└──────────┬──────────────────────────────────┘        │
           ▼                                         ▼
┌────────────────────────────────────────────────────────────────┐
│  core (kernel puro, sin Selenium)                               │
│  fechas dd-mm-yyyy │ nombres (2 convenciones) │ tipos │ rutas   │
└────────────────────────────────────────────────────────────────┘

  Aislado (futuro paso 7):  queue_store.py + anita/  ──► cron 19:00
  Compat: browser_automation.py = shim → re-exporta de rayen/*
```

Tres reglas que resumen la arquitectura:
1. Las flechas solo bajan: `core` no conoce a nadie; `rayen` no conoce a
   `notas`/`informes`; los CLIs solo orquestan.
2. Los pasos offline (5 y 6) no tocan Rayen — se pueden re-correr sin
   login las veces que haga falta.
3. El paso 3 es el unico que lee el informe base como INPUT (lista de
   pacientes) — por eso el orden es 4→5→3→6 y no 3→4→5→6.

---

## Regla de mantenimiento (OBLIGATORIA)

Estos diagramas son documentacion viva, no decorativa:

1. Todo cambio de flujo, comando, modulo o archivo de salida implica
   actualizar este archivo EN EL MISMO COMMIT del cambio.
2. Todo cambio de regla de negocio implica actualizar
   `docs/REQUISITOS.md` en el mismo commit (ya cubierto por sus reglas).
3. Al actualizar, cambiar la linea "Ultima actualizacion" con la fecha
   y el/los commits correspondientes.
4. Si un diagrama queda desactualizado respecto al codigo, es un bug de
   documentacion: tratarlo con la misma prioridad que un test rojo.
