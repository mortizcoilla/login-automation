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

PowerShell (Windows):

```powershell
git clone https://github.com/mortizcoilla/login-automation.git
cd login-automation
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -e .          # runtime: selenium, requests, python-dotenv
pip install -e .[dev]     # + pytest, ruff, mypy (recomendado)
```

Linux (mini PC Ubuntu):

```bash
git clone https://github.com/mortizcoilla/login-automation.git
cd login-automation
python3 -m venv venv
source venv/bin/activate
pip install -e .[dev]
```

## 3. Configuracion que NO viene en el repo (gitignored)

El repo trae `config/selectors.json` (selectores de Rayen) y
`.env.example` (plantilla). Faltan dos cosas por crear a mano:

### 3.1 Credenciales de Rayen — `config/users.json` (OBLIGATORIO pasos 3-4)

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

Alternativa sin archivo: variables de entorno
`USERS_YADIRA_LOCATION`, `USERS_YADIRA_USERNAME`, `USERS_YADIRA_PASSWORD`
(env tiene prioridad sobre el JSON).

### 3.2 `.env` (OPCIONAL — copiar de .env.example)

```powershell
copy .env.example .env
```

Variables utiles: `LOG_LEVEL`, `TIMEOUT_SECONDS`, `HEADLESS` (vacio =
Chrome visible; `true` para sin ventana) y, para el paso 7,
`MORTADELO_MODELOS` (cascada de modelos, separados por coma) y
`MORTADELO_TIMEOUT`. Las API keys de z.ai/MiniMax NO se usan (motor
exclusivo: opencode CLI).

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
