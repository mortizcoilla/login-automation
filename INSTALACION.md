# INSTALACION — Login-Automation en un PC nuevo

Guia completa para dejar el proyecto operativo tras clonar el repo.
Ultima actualizacion: 2026-09-18.

---

## 1. Requisitos previos

| Componente | Version | Para que | Verificacion |
|---|---|---|---|
| Git | cualquiera | clonar | `git --version` |
| Python | >= 3.10 (probado hasta 3.14) | todo el proyecto | `python --version` |
| Google Chrome | actual | pasos 3 y 4 (Selenium) | abrir Chrome |
| Node.js + npm | LTS | CLI de opencode (paso 7) | `node --version` |

Notas:
- ChromeDriver NO se instala a mano: Selenium Manager lo descarga solo
  (selenium >= 4.27).
- El paso 7 (Mortadelo) necesita el CLI de opencode; si ese PC no lo
  usara, los pasos 2-6 funcionan igual sin el.

## 2. Clonar y preparar el entorno

PowerShell (Windows y mini PC):

```powershell
git clone https://github.com/mortizcoilla/login-automation.git
cd login-automation
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e .          # runtime: selenium, requests, python-dotenv
pip install -e .[dev]     # + pytest, ruff, mypy (recomendado)
```

La mini PC tambien usa Windows (mismo procedimiento). El runner
`flujo_diario.py` resuelve solo la ruta del venv de cualquiera de las
dos plataformas, por si algun dia vuelve a Linux.

## 3. Configuracion que NO viene en el repo (gitignored)

El repo trae `config/selectors.json` (selectores de Rayen) y
`.env.example` (plantilla). Faltan dos cosas por crear a mano:

### 3.1 Credenciales de Rayen (OBLIGATORIO pasos 3-4 — users.json O .env)

Opcion A — `config/users.json`:

```json
{
  "users": {
    "yadira": {
      "location": "<sede/box que muestra Rayen>",
      "username": "<usuario>",
      "password": "<clave>"
    }
  }
}
```

Opcion B — en `.env` (ya viene de plantilla, solo rellenar):

```
USERS_YADIRA_LOCATION=...
USERS_YADIRA_USERNAME=...
USERS_YADIRA_PASSWORD=...
```

Si existen ambas fuentes, env tiene prioridad sobre el JSON
(REQ-045, cargador unico `src/credentials.py`).

### 3.2 `.env` (OPCIONAL — copiar de .env.example)

```powershell
copy .env.example .env
```

Variables utiles: `LOG_LEVEL`, `TIMEOUT_SECONDS`, `HEADLESS` (vacio =
Chrome visible; `true` para sin ventana) y, para el paso 7,
`MORTADELO_MODELOS` (cascada de modelos, separados por coma) y
`MORTADELO_TIMEOUT`. Las API keys de z.ai/MiniMax NO se usan (motor
exclusivo: opencode CLI).

El bloque "Rutas de productos" (REQ-059) declara todos los directorios
de salida: `DATA_DIR` reubica todos los productos de una vez y cada
directorio tiene override individual. Con los defaults (comentados) no
hay que editar nada al cambiar de PC: las rutas son relativas al repo.

## 4. CLI de opencode (solo si se usara el paso 7)

```powershell
npm install -g opencode-ai
opencode auth login        # elegir OpenCode Go y autenticar la cuenta
opencode models            | findstr nemotron   # verificar modelos free
```

El agente del paso 7 (`.opencode/agent/mortadelo.md`, rol medico v2)
ya viene en el repo.

## 5. Datos

`data/` esta gitignored (PII clinica) y se crea solo: la primera
corrida de `python flujo_diario.py` construye la DB del mes
(`data/analysis/fichas_completo.db`) y genera notas, info, anamnesis y
los productos del paso 7. Si se migran datos de otro PC, copiar las
carpetas `data/` tal cual (notas_clinicas, info_paciente, anamnesis,
examenes, examenes_crudos, fichas_generadas, informes_trazabilidad).

## 6. Verificacion de la instalacion

```powershell
pytest -q                  # 392 tests verdes (no toca Rayen ni la API)
ruff check src tests       # limpio
mypy src                   # limpio
python -m src.tools.mortadelo --help     # CLI del paso 7 responde
python -m src.tools.crear_notas_clinicas --help
```

Y la prueba real, con login de Rayen a la vista:

```powershell
python flujo_diario.py     # 4 -> 5 -> 3 -> 6 -> 7, pide confirmacion
```

## 7. Cron del flujo diario (opcional, Windows)

El scheduler (`src/scheduler/`, REQ-060) corre la cadena diaria en el
calendario de cada doctor, definido en `config/calendario.json`
(editar ese archivo cambia horarios o agrega doctores: NO hay que
re-registrar nada):

```powershell
python -m src.scheduler.instalar --instalar     # crea la tarea (queda DESACTIVADA)
python -m src.scheduler.instalar --activar      # la deja corriendo
python -m src.scheduler.instalar --estado       # ver estado/proxima corrida
python -m src.scheduler.runner --listar         # que venceria ahora, sin correr
python -m src.scheduler.runner --forzar yadira  # corrida manual inmediata
```

La tarea dispara cada 30 min (silenciosa, pythonw); el runner decide
con el calendario si corre. Si el PC estaba apagado a la hora, corre
al encender. Log: `logs/scheduler.log`; estado del dia:
`data/scheduler_estado.json`. Desactivar sin borrar:
`--desactivar`. Eliminar: `--desinstalar`.

## 7. Problemas frecuentes

- **`Usuario 'yadira' no encontrado`**: falta `config/users.json` (3.1).
- **Chrome no abre / driver falla**: actualizar Chrome; Selenium Manager
  necesita internet la primera vez para bajar chromedriver.
- **`CLI de opencode no encontrado`** en el paso 7: `npm install -g
  opencode-ai` y verificar con `opencode --version`; luego `auth login`.
- **Login de Rayen falla**: la ventana es visible a proposito; validar
  manualmente que la sede/usuario/clave de users.json sean correctos.
- **PowerShell bloquea Activate.ps1**: `Set-ExecutionPolicy -Scope
  Process RemoteSigned` y reintentar.
