# REQUISITOS — Matriz de trazabilidad

Fuente unica de verdad de las reglas de negocio del proyecto. Cada requisito
tiene ID estable, origen (quien lo decidio y cuando), estado, implementacion
(y archivo) y tests que lo verifican.

Estados:
- **VIGENTE**: regla activa, implementada, con tests (o test pendiente anotado).
- **SUPERSEDED**: regla reemplazada por otra (se indica por cual).
- **PENDIENTE**: decidida pero sin implementar (fase del roadmap).

Como citar en codigo: `# REQ-NNN: <enunciado corto>`. El detalle y el origen
viven SOLO aca (una sola interpretacion).

Convencion de fechas: dd-mm-yyyy.

---

## 1. Reglas duras del dominio (AGENTS.md)

| ID | Requisito | Origen | Estado | Implementacion | Tests |
|----|-----------|--------|--------|----------------|-------|
| REQ-001 | Yadira es la fuente de verdad sobre sus datos. Los agentes no deciden diagnosticos ni tratamientos. | AGENTS.md | VIGENTE | Principio transversal (sin codigo que decidaclinica) | — |
| REQ-002 | Las notas clinicas son inmutables en contenido y orden. Solo se permite limpieza de formato que no cambie la informacion. | AGENTS.md | VIGENTE | `guardar_nota_clinica` estructura fija (`src/tools/crear_notas_clinicas.py`) | `test_crear_notas_clinicas.py` (estructura .md, 12 tests) |
| REQ-003 | ~~NO sobrescribir archivos en `data/notas_clinicas/`~~ | AGENTS.md (pre 16-09) | **SUPERSEDED** por REQ-021 | — | — |
| REQ-004 | NO crear scripts por paciente. El script es siempre generico. | AGENTS.md | VIGENTE | Todos los CLIs operan por parametro/ informe | — |
| REQ-005 | El paso 7 APORTA informacion medica confiable y verificable cuando el dato no esta en los insumos: el LLM (medico experto APS/ECICEP, rol v2) fundamenta cada aporte e indica su base e incertidumbre. La supervision DIRECTA de la Dra. Yadira es el control final: ella detecta y rechaza lo que no corresponda. Los datos factuales (telefono, domicilio) jamas se inventan: quedan (-). Aplica SOLO al paso 7; pasos 2-6 siguen sin inventar nada. | Reformulado por el usuario 18-09-2026 | VIGENTE | `src/mortadelo/` (prompt + ensamblador) | `test_mortadelo.py` |
| REQ-006 | Sin emojis en codigo, system prompts ni documentacion tecnica. | AGENTS.md | VIGENTE | Convencion | — |
| REQ-007 | Paso 7 (Mortadelo) reescrito desde cero (v1): ficha completa + informe de trazabilidad por paciente. Motor LLM via opencode CLI. | Sesion 2026-09-17; v1 18-09-2026 | VIGENTE | `src/mortadelo/` + CLI `src/tools/mortadelo.py` | `test_mortadelo.py` (40) |

## 2. Flujo y orden

| ID | Requisito | Origen | Estado | Implementacion | Tests |
|----|-----------|--------|--------|----------------|-------|
| REQ-008 | Cadena diaria obligatoria (orden real de dependencias 4→5→3→6): `actualizar_mes_actual yadira` → `informe_fichas_abiertas` → `crear_notas_clinicas --todos` → `enriquecer_informe` → `mortadelo --todos` (paso 7 desde 18-09). Runner: `python flujo_diario.py`. | Usuario (Miguel) 18-09-2026 | VIGENTE | CLIs en `src/analysis/` y `src/tools/` (paths estables) | Smoke Fase 6 + golden baselines `data/analysis/golden_baseline_refactor/` |
| REQ-009 | El flujo de examenes (pasos 1-2) es opt-in por paciente e independiente del diario. No todos los pacientes tienen examenes. | Usuario 18-09-2026 | VIGENTE | `src/tools/recibir_foto_examen.py` (2a); consolidacion vision (2b, REQ-047) | `test_recibir_foto_examen.py` (26) |
| REQ-010 | El informe mensual de fichas abiertas es la lista de pacientes del batch del paso 3 (`--todos`). El informe anual esta PROHIBIDO como input del batch. | Sesion 2026-09-09 | VIGENTE | `parsear_informe` + guard `_completo` en `main()` de crear_notas | `test_crear_notas_clinicas.py::TestParsearInforme` (4) |
| REQ-011 | Aislamiento mensual/anual (no negociable): archivos de salida distintos, filtros SQL distintos, ninguno toca el archivo del otro. Enriquecer SOLO opera el mensual y rechaza el anual por guard. | Sesion 2026-09-09 | VIGENTE | `src/analysis/informe_paths.py`, guards en informe_fichas_abiertas y enriquecer_informe | — (pendiente: Fase 4 agrega tests de guard) |

## 3. Paso 2a — Rubicita: archivado de examenes

| ID | Requisito | Origen | Estado | Implementacion | Tests |
|----|-----------|--------|--------|----------------|-------|
| REQ-012 | Alcance 2a: recibir imagen, resolver nombre/fecha contra `data/notas_clinicas/`, renombrar `<pac_norm>_<n>_<dd-mm-aaaa>.<ext>` y archivar en `data/examenes_crudos/`. Copia byte-a-bit. SIN OCR local (decision 2026-09-17). | Yadira/Miguel 17-09-2026 | VIGENTE | `recibir_y_archivar` (`src/tools/recibir_foto_examen.py`) | `test_recibir_foto_examen.py` (26) |
| REQ-013 | La fecha de atencion del informe clinico es la fuente de verdad. Si Yadira da otra fecha (ej. la de hoy), se descarta y se usa la del informe, dejando registro del descarte. | rubicita-conventions.md | VIGENTE | `recibir_y_archivar` (campos `fecha_matcheada`, `fecha_input_descartada`) | incluido en `test_recibir_foto_examen.py` |
| REQ-014 | Sin nombre de paciente no se archiva: "Rubicita NO adivina". Sin nombre y sin fecha y sin match → error. | rubicita-conventions.md | VIGENTE | `recibir_y_archivar` | incluido |
| REQ-015 | Nunca sobrescribir un examen archivado: colision resuelve con sufijo `_v2`, `_v3`, ... | rubicita-conventions.md | VIGENTE | `resolver_path_sin_colision` | incluido |
| REQ-016 | Matching de paciente por tokens (>=3 chars, normalizado sin tildes); con multiples candidatos gana el de mas coincidencias y a igualdad el de fecha mas reciente. | rubicita-conventions.md | VIGENTE | `buscar_match_paciente` | incluido (5 tests) |

## 4. Paso 3 — Pancho: scrapeo de Rayen y notas clinicas

| ID | Requisito | Origen | Estado | Implementacion | Tests |
|----|-----------|--------|--------|----------------|-------|
| REQ-017 | Rayen solo permite 8 fichas abiertas por sesion: al llegar al limite se cierra sesion y se re-logea automaticamente. | Sesion 2026-08 (HANDOFF) | VIGENTE | `MAX_FICHAS_POR_SESION` + reset en `main()` de crear_notas | — (pendiente Fase 3) |
| REQ-018 | El historial de atenciones se limita a los ultimos 6 meses respecto a la fecha de atencion. Lineas con fecha no parseable se CONSERVAN (no se destruye data por parsing). | Sesion 2026-08 | VIGENTE | `filtrar_historial_ultimos_6_meses` | `test_filtrar_historial_6_meses.py` (15) |
| REQ-019 | Match de paciente contra la tabla de Rayen: exacto → parcial unico → ambiguo NO matchea (anti falso positivo). El nombre real de Rayen se guarda como metadato si difiere. | Sesion 2026-08 | VIGENTE | `_buscar_paciente_en_tabla` | — (pendiente Fase 3) |
| REQ-020 | La anamnesis SIEMPRE existe en Rayen (regla dura). Anamnesis vacia = bug del extractor → ValueError, NO se escribe la nota. | Yadira 16-09 14:14 | VIGENTE | `guardar_nota_clinica` | `test_crear_notas_clinicas.py` (placeholders, 9) |
| REQ-021 | La nota clinica SIEMPRE se escribe/sobrescribe con la extraccion nueva (overwrite natural de cada corrida; la ultima extraccion es la que vale). Revoca REQ-003. | Yadira 16-09 14:14 | VIGENTE | `guardar_nota_clinica` | 3 suites (crear_notas, estratificacion, motivo) |
| REQ-022 | Validacion post-write: tras escribir, se verifican todos los bloques; los vacios se re-extraen de Rayen (driver activo) y se re-escriben in place. | Yadira 16-09 14:14 | VIGENTE | `validar_nota_clinica`, `re_extraer_bloque`, `_rellenar_bloque_en_nota` | `test_crear_notas_clinicas.py` (validar 2 + rellenar 3) |
| REQ-023 | Si la extraccion de anamnesis falla: NO escribir markers de fallo; reintentar (re-click "Atencion actual" + re-extraer) hasta 3 veces; agotados los reintentos, skip silencioso. | Yadira 16-09 14:50 | VIGENTE | `_reintentar_extraccion_anamnesis` | — (pendiente Fase 3) |
| REQ-024 | Orden de extraccion: estratificacion ECICEP PRIMERO (abre modal que debe cerrarse con "Salir" antes de cualquier otra extraccion), luego identificacion, historial, recien entonces click en "Atencion actual". | Miguel 26-08 | VIGENTE | `main()` de crear_notas + `extraer_estratificacion_ecicep` | `test_estratificacion_ecicep.py` (24) |
| REQ-025 | El badge de estratificacion es G0..G3 (G0 existe; G4+ no), vive en el header (`button[aria-haspopup]`), sin clase de color (badge-warning fallaba en G1/G3). | Miguel 25-08 | VIGENTE | `_ESTRAT_BADGE_SELECTOR`, `_ESTRAT_CARD_JS` | `test_estratificacion_ecicep.py` |
| REQ-026 | El motivo de atencion JAMAS esta vacio (Rayen lo exige al abrir ficha). El respaldo siempre escribe el blockquote del motivo; vacio es senal visible de bug del extractor. | Yadira 16-09 15:35 | VIGENTE | `guardar_respaldo_anamnesis` | `test_crear_notas_clinicas.py` (respaldo, 8) |
| REQ-027 | Respaldo de anamnesis cruda separado: `data/anamnesis/anam_<pac>_<fecha>.md` con motivo blockquote + anamnesis, SIN frontmatter (pedido usuario 18-09-2026; antes lo llevaba). El filename ya identifica paciente y fecha. Sobrescribir el respaldo es OK. | Yadira 16-09 15:14/15:27; usuario 18-09-2026 | VIGENTE | `src/notas/anamnesis.py::guardar_respaldo_anamnesis` | `test_crear_notas_clinicas.py::TestGuardarRespaldoAnamnesis` (8) |
| REQ-028 | Documento complementario `data/info_paciente/info_<pac>_<fecha>.md` con TODA la info del paciente MENOS anamnesis/motivo (vista rapida). Prefijos `anam_`/`info_` distinguibles. | Yadira 16-09 17:45/18:45 | VIGENTE | `guardar_info_paciente` | incluido (13) |
| REQ-029 | Si tipo de atencion es "Recetas", la nota incluye SOLO la prescripcion con Vigencia mas reciente (evita acumular recetas reemplazadas). | Yadira 26-08 | VIGENTE | `_filtrar_receta_mas_reciente` + aplicacion en `main()` | — (pendiente Fase 3) |
| REQ-030 | Timeout del panel del paciente: 60s (esclado 15→30→60 segun casos reales). Si no carga: nota con placeholders + `panel_cargo: false` en frontmatter + banner de revision manual. NO reintentar el doble-click. | Sesiones 09-09/16-09 | VIGENTE | `paso_4_1_abrir_ficha` + frontmatter | `test_crear_notas_clinicas.py` (panel_cargo, 4) |
| REQ-031 | Doble-click tolerante a stale element: si la fila quedo stale tras la carga del panel, re-buscar por nombre y re-intentar UNA vez. | Sesion 16-09 (bug ECICEP-g3) | VIGENTE | `_doble_click_en_paciente` | — (pendiente Fase 3) |
| REQ-032 | Al final del batch se verifica el target: las N fichas del informe deben quedar abiertas; si falta alguna, warning "TARGET NO CUMPLIDO" con detalle. | Sesion 2026-08 | VIGENTE | seccion final de `main()` | — (pendiente Fase 3) |
| REQ-033 | Exclusion de scope en paso 3: NO se extraen examenes adjuntos, pautas, otros items, plan→imagenologia ni plan→interconsulta (se escriben vacios). | Yadira 26-08 | VIGENTE | `main()` (`examenes = ""`, `pautas = []`, `otros_items = {}`) | — |
| REQ-034 | Fuera de la ficha: nada tecnico (rutas, errores de OCR, stacktraces) va a los documentos de Yadira; lo tecnico va al informe JSON separado `data/analysis/informe_tecnico_<ts>.json`. | Sesion 2026-08 | VIGENTE | `src/tools/informe_tecnico.py` | — (pendiente) |

## 5. Pasos 4-6 — Anita: DB del mes e informes

| ID | Requisito | Origen | Estado | Implementacion | Tests |
|----|-----------|--------|--------|----------------|-------|
| REQ-035 | El paso 4 reconstruye el mes en curso completo: borra los registros del mes y los reinserta con datos frescos, dia por dia, solo dias habiles (lun-vie) hasta hoy. ~2-3 min. | Sesion 2026-08 | VIGENTE | `src/analysis/actualizar_mes_actual.py` | — (pendiente Fase 4) |
| REQ-036 | El paso 4 aborta tras 3 errores consecutivos de dia (no pierde la sesion completa por un dia malo). | Sesion 2026-08 | VIGENTE | `max_errores = 3` en actualizar_mes_actual | — (pendiente Fase 4) |
| REQ-037 | Sanitizacion del tipo de atencion: se eliminan prefijos de instrumento (ME, EN, PS, TO, NU, KT) que Rayen antepone. | Sesion 2026-08 (src.plantillas) | VIGENTE | `sanitizar_tipo` en `src/core/tipos_atencion.py` (unica copia; antes inline x2) | `test_pancho_skills.py` (parcial) + `test_core.py` |
| REQ-038 | Clave unica de atencion en la DB: (fecha, hora, nombre). | Sesion 2026-08 | VIGENTE | esquema INSERT en actualizar_mes_actual | — (pendiente Fase 4) |
| REQ-039 | El informe base (paso 5) tiene 5 columnas: Fecha, Nombre, Edad, Tipo de atencion, Motivo de la atencion. Sin columna Plantilla (removida a peticion de Yadira) ni "Razon de la cita". Los faltantes se escriben `(-)` para que el parser downstream nunca colapse columnas. | Yadira, sesion 09-09 | VIGENTE | `src/analysis/informe_fichas_abiertas.py` | — (golden Fase 4) |
| REQ-040 | Estado "Iniciado" = ficha abierta = deuda clinica: es el unico filtro de los informes. | Sesion 2026-08 | VIGENTE | SQL `estado = 'Iniciado'` | — (golden Fase 4) |
| REQ-041 | El informe enriquecido (paso 6) agrega: Edad decimal (coma chilena, 2 decimales, ano juliano 365.25, SIEMPRE re-derivada de la nota) + Examenes, Interconsulta, Indicaciones (si/no). | Yadira 16-09 17:35 | VIGENTE | `_edad_a_decimal`, `_formatear_tabla` | `test_enriquecer_informe.py` (46) |
| REQ-042 | Trigger `** Mortadelo`: regex case-insensitive tolerante a formato; sigue vigente como senal de Yadira aunque Mortadelo este eliminado. Tres requerimientos: "examenes adjuntos", "generar/crear interconsulta", "realizar/dar/hacer indicaciones". | Yadira 16-09, ampliado 17-09; reconfirmado 18-09 | VIGENTE | `TRIGGER_RE`, `KEYWORDS_REQUERIMIENTOS` (enriquecer_informe) | `test_enriquecer_informe.py` |
| REQ-043 | CORREGIDO (Fase 4b): el parser del informe mapea 8 columnas con el layout deprecado del 16-09 17:26; el output actual tambien tiene 8 columnas con otro orden → correr paso 6 dos veces seguidas sin paso 5 en medio corrompe tipo/motivo. Fix: disambiguacion por parts[3] en el parser unificado. | Hallazgo refactor 18-09 | VIGENTE | `src/informes/parser.py` | `test_informes_parser.py` |

| REQ-053 | BUGFIX (Fase 4b): parsear_informe mapeaba el layout actual de 5 columnas (con Edad) con la tabla legacy -> tipo_atencion="(-)" en 4 notas reales de sept 2026. Corregido en el parser unificado. | Hallazgo refactor 18-09 | VIGENTE | `src/informes/parser.py` | `test_informes_parser.py` |

## 6. Privacidad y credenciales

| ID | Requisito | Origen | Estado | Implementacion | Tests |
|----|-----------|--------|--------|----------------|-------|
| REQ-044 | NUNCA commitear `data/` con PII (nombres, RUN, fotos, examenes). DBs y CSVs viven gitignored en disco local. | COMANDOS.txt / politica | VIGENTE | `.gitignore` (incluye examenes_crudos ambos casings) | — (politica) |
| REQ-045 | Credenciales por `config/users.json` (gitignored) o variables de entorno `USERS_<ID>_*` con precedencia env > json. Nunca en el repo. | Sesion 2026-08 | VIGENTE | `src/credentials.py` | `test_credentials.py` (9) |
| REQ-046 | En queue_store el RUT se persiste hasheado (SHA-256 truncado) y los tokens de aprobacion son de un solo uso con TTL 300s. | Sesion 2026-08 | VIGENTE | `src/queue_store.py` | `test_queue_store.py` (27) + `test_pancho_skills.py` |

## 7. Decisiones de scope y roadmap

| ID | Requisito | Origen | Estado | Implementacion | Tests |
|----|-----------|--------|--------|----------------|-------|
| REQ-047 | Paso 2b (NUEVO): consolidacion de examenes via API de vision de z.ai (GLM vision). Sin OCR local (la maquina no lo soporta). Genera `data/examenes/exam_<pac>_<fecha>.md` desde las fotos crudas; nunca sobrescribe; fallo de API no afecta el archivado 2a. | Usuario 18-09-2026 | VIGENTE | `src/examenes/` + CLI `src/tools/consolidar_examenes.py` | `test_examenes.py` (8) |
| REQ-048 | queue_store + anita se conservan aislados del flujo 3-6: son la base del futuro paso 7 (flujo de aprobacion). No se integran al diario. | Usuario 18-09-2026 | VIGENTE | `src/queue_store.py`, `src/anita/` | `test_anita.py` (12) |
| REQ-049 | No hay orquestador unico del flujo diario: la cadena de 4 comandos (REQ-008) ES la interfaz. El orden queda documentado, no automatizado. | Usuario 18-09-2026 | VIGENTE | Documentacion (README/AGENTS) | — |
| REQ-050 | El cron de Anita (19:00, mini PC Ubuntu) solo genera el reporte de la cola; la integracion Telegram queda pendiente hasta resolver el bug del bot. | Sesion 2026-08 | PENDIENTE | `src/anita/cron_runner.py` (imprime, no envia) | `test_anita.py` (CLI) |
| REQ-051 | CI obligatorio: ruff (check+format), mypy y pytest en Python 3.10/3.11/3.12. | Sesion 2026-08 | VIGENTE | `.github/workflows/ci.yml` | — (gates) |
| REQ-052 | Contrato de la refactorizacion 2026-09-18: la cadena diaria (REQ-008) debe producir exactamente el mismo producto antes y despues. Referencia inmutable: `C:\Workspace\Login-Automation_BACKUP_2026-09-18\` (solo lectura) y golden baselines en `data/analysis/golden_baseline_refactor/`. | Usuario 18-09-2026 | VIGENTE | Verificacion por diff byte-a-byte en cada fase | Smoke Fase 6 |

---

## Reglas de mantenimiento de esta matriz

0. Los diagramas de `docs/DIAGRAMAS.md` se actualizan en el mismo commit
   que cualquier cambio de flujo/estructura/comando (regla compartida).

1. Todo cambio de comportamiento requiere: actualizar la fila del REQ afectado
   (o crear nuevo REQ y marcar el viejo SUPERSEDED apuntando al nuevo).
2. Todo REQ VIGENTE con "pendiente" en Tests es deuda explicita: la fase que
   lo implementa agrega el test y actualiza la fila.
3. Los comentarios `# Sesion 2026-XX-XX` del codigo se reemplazan gradualmente
   por `# REQ-NNN` (el origen historico queda citado aqui, no en el codigo).
