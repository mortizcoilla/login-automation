# Login-Automation

Automatizacion de login y gestion de plantillas para Rayen APS
(consultorio de la Dra. Yadira Hernandez Cabrera, CESFAM Raul Cuevas,
San Bernardo).

---

## 1. Requisitos del sistema

- **Python 3.10+** (probado en 3.10, 3.11, 3.12, 3.14)
- **Google Chrome** (estable, NO Chrome Dev ni Canary) para Selenium
- **Git** para clonar el repo
- **Windows** con PowerShell 7+ (probado en PS 7.6.5). En Mac/Linux
  funciona pero no esta en el flujo soportado por Yadira.

---

## 2. Instalacion (primera vez en una PC nueva)

```powershell
# 2.1 Clonar el repo
cd C:\Workspace
git clone <url-del-repo> Login-Automation
cd Login-Automation

# 2.2 Crear y activar venv
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2.3 Instalar dependencias
#    Runtime + herramientas de desarrollo (pytest, ruff, mypy)
pip install -e .[dev]

#    Solo runtime (sin pytest/ruff/mypy):
# pip install -e .

# 2.4 Configurar variables de entorno
copy .env.example .env
notepad .env   # editar credenciales y secretos (ver data/docs/CREDENCIALES.md)
```

Notas:
- `pip install -e .[dev]` instala el proyecto en modo "editable":
  cualquier cambio en `src/` se ve reflejado sin reinstalar.
- `.env` NUNCA se commitea (esta en .gitignore). Contiene API keys,
  credenciales Rayen, paths locales.
- Si Python 3.10+ no esta en PATH, ajustar el `python` al launcher
  (`py -3.12 -m venv venv`).

---

## 3. Verificar la instalacion

```powershell
# Suite completa de tests (567 tests, ~15s)
pytest

# Lint rapido
ruff check src tests main.py

# Type-check
mypy src

# Ver usuarios configurados (smoke test de main.py)
python main.py --list-users
```

Si todo esto pasa, la PC esta lista para correr `python main.py --user yadira --date dd-mm-aaaa`.

---

## 4. Primer uso contra Rayen

1. **Login manual** desde Chrome para verificar que Yadira puede entrar.
2. **Capturar la API** (solo si la URL o los headers cambiaron):
   ```powershell
   python -m src.discover_api
   ```
3. **Login + listado de hoy**:
   ```powershell
   python main.py --user yadira --date 16-09-2026 --no-input
   ```

Mas opciones (headless, fechas pasadas, etc.) en `data/docs/COMANDOS.txt`.

---

## 5. Estructura del proyecto

```
Login-Automation/
├── main.py                 ← entry point (login + rellenar plantillas)
├── pyproject.toml          ← dependencias (runtime + [dev]) + tool config
├── AGENTS.md               ← reglas duras para agentes IA
├── actualizar_y_notas.ps1  ← wrapper pipeline (5 pasos)
├── venv/                   ← entorno virtual (NO se commitea)
├── .env                    ← secretos locales (NO se commitea)
├── config/                 ← api_config.json, users.json, selectors.json
├── manuales/               ← PDFs fuente de manuales clinicos
├── src/                    ← codigo del proyecto
│   ├── browser_automation.py
│   ├── credentials.py
│   ├── pancho_skills/      ← login + navegacion en Rayen
│   ├── mortadelo/          ← bundles (skills clinicos)
│   ├── tools/              ← scripts del pipeline
│   └── analysis/           ← scripts de actualizacion de DB y listados
├── tests/                  ← suite pytest (567 tests)
└── data/                   ← TODO lo local-only (gitignored):
    ├── docs/               ← COMANDOS.txt, HANDOFFs, guias
    ├── manuales_md/        ← manuales convertidos a .md + index.json
    ├── plantillas/         ← plantillas Yadira (INMUTABLES)
    ├── notas_clinicas/     ← notas crudas extraidas de Rayen (incluye anamnesis)
    ├── fichas_clinicas/    ← fichas rellenadas por Mortadelo
    ├── anamnesis/          ← respaldo de SOLO la anamnesis Yadira
    ├── info_paciente/      ← TODO lo del paciente MENOS la anamnesis (complemento)
    ├── adjuntos/           ← inbox de fotos de examenes (Yadira/Pilita) — futuro
    ├── examenes/           ← examenes procesados por vision LLM — futuro
    ├── analysis/           ← DBs (fichas_completo.db, tracking*.db) + reportes
    ├── logs/               ← logs del pipeline + screenshots
    ├── prompts/            ← prompts LLM
    └── test_cases/         ← fixtures de tests
```

Para el detalle de que hace cada archivo / DB / script, ver
`data/docs/COMANDOS.txt` (indice completo de comandos operativos).

---

## 6. Privacidad y datos sensibles

- `data/` contiene datos clinicos con PII (RUT, nombre, observacion).
  **NUNCA se commitea**. Esta en .gitignore.
- `.env` contiene API keys y credenciales. **NUNCA se commitea**.
- `data/analysis/tracking*.db` NO tiene PII (solo `cita_id` + `tipo_atencion`).
  Es la unica DB que se puede compartir.
- Para detalle de la politica de credenciales, ver
  `data/docs/CREDENCIALES.md`.

---

## 7. Problemas frecuentes

| Sintoma                                  | Causa probable                              | Solucion                                       |
|------------------------------------------|---------------------------------------------|------------------------------------------------|
| `ModuleNotFoundError: src`               | venv no activado                            | `.\venv\Scripts\Activate.ps1`                   |
| `pip install -e .[dev]` falla            | Python <3.10                                | Instalar Python 3.10+ desde python.org         |
| `chromedriver not found`                 | Selenium no encontro Chrome                 | Instalar Google Chrome estable (NO Dev/Canary)  |
| `pytest` no encontrado                   | Instalaste solo runtime (`pip install -e .`) | `pip install -e .[dev]`                        |
| Login falla pero Chrome abre             | Credenciales en `.env` mal                  | Editar `.env`, comparar con `data/docs/CREDENCIALES.md` |
| `git status` muestra `data/` con archivos | No es bug, es data local (gitignored)        | OK, no commitear                                |

---

Ultima actualizacion: 2026-09-16 (consolidacion data/ + deps en pyproject.toml).