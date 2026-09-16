# ============================================================================
# actualizar_y_notas.ps1
# ----------------------------------------------------------------------------
# Pipeline mensual "actualizar mes + informe + notas clinicas".
# NO procesa con LLM. Llega hasta la construccion de notas clinicas en
# notas_clinicas/ y se detiene ahi.
#
# Uso (desde la raiz del repo):
#   .\actualizar_y_notas.ps1
#   # o equivalentemente:
#   python -m src.analysis.actualizar_mes_actual yadira ; `
#   python -m src.analysis.informe_fichas_abiertas ; `
#   python -m src.tools.crear_notas_clinicas --todos
#
# Prereqs:
#   - venv activado (.\venv\Scripts\Activate.ps1) o python en PATH
#   - .env en la raiz con USERS_YADIRA_* (o config/users.json)
#   - Chromedriver disponible (lo gestiona browser_automation.py)
#
# Que hace cada paso:
#   1. actualizar_mes_actual yadira
#       Recorre el mes en curso en Rayen APS y regenera la DB local
#       data/analysis/fichas_completo.db (borra y reinserta el mes).
#       Tiempo: ~2-3 min.
#
#   2. informe_fichas_abiertas
#       Lee la DB local y escribe data/analysis/informe_fichas_abiertas_<MM-YYYY>.txt
#       con las fichas en estado "Iniciado" del mes actual.
#       Sin red, instantaneo.
#
#   3. crear_notas_clinicas --todos
#       Para cada paciente del informe: login en Rayen, abre la ficha, extrae
#       la nota clinica + adjuntos, y guarda en notas_clinicas/<paciente>_<fecha>.txt.
#       Tiempo: ~10-30 s por paciente (10-30 min si son ~30 pacientes).
#
#   4. pytest tests/
#       Corre la suite de tests como guardrail. Solo limpia screenshots si
#       todos pasan.
#
#   5. limpiar_screenshots
#       Borra logs/screenshots/*.png y *.html si el pipeline + tests
#       terminaron OK. Si algo fallo, deja las capturas para debug.
#
# Que NO hace (intencional):
#   - NO invoca el LLM (generar_ficha_con_llm / mortadelo_batch).
#   - NO genera fichas en fichas_clinicas/.
#   - NO envia a Yadira por Telegram.
#   Esos pasos viven en scripts separados del flujo LLM (zona a corregir).
# ============================================================================

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  actualizar_y_notas.ps1" -ForegroundColor Cyan
Write-Host "  Pipeline mensual (sin LLM) — $(Get-Date -Format 'yyyy-MM-dd HH:mm')" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host ""

# --- Paso 1/3: actualizar mes en curso --------------------------------------
Write-Host "[1/3] actualizar_mes_actual yadira" -ForegroundColor Yellow
Write-Host "      Recorriendo Rayen APS para regenerar la DB del mes actual..."
Write-Host ""
python -m src.analysis.actualizar_mes_actual yadira
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] actualizar_mes_actual fallo con codigo $LASTEXITCODE" -ForegroundColor Red
    Write-Host "         Abortando pipeline." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host ""
Write-Host "[1/3] OK" -ForegroundColor Green
Write-Host ""

# --- Paso 2/3: informe de fichas abiertas del mes ---------------------------
Write-Host "[2/3] informe_fichas_abiertas" -ForegroundColor Yellow
Write-Host "      Generando informe del mes en curso desde la DB local..."
Write-Host ""
python -m src.analysis.informe_fichas_abiertas
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] informe_fichas_abiertas fallo con codigo $LASTEXITCODE" -ForegroundColor Red
    Write-Host "         Abortando pipeline." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host ""
Write-Host "[2/3] OK" -ForegroundColor Green
Write-Host ""

# --- Paso 3/3: extraer notas clinicas ---------------------------------------
Write-Host "[3/3] crear_notas_clinicas --todos" -ForegroundColor Yellow
Write-Host "      Abriendo cada ficha del informe y guardando la nota clinica..."
Write-Host ""
python -m src.tools.crear_notas_clinicas --todos
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] crear_notas_clinicas fallo con codigo $LASTEXITCODE" -ForegroundColor Red
    Write-Host "         Notas ya extraidas (si las hubo) quedaron en notas_clinicas/." -ForegroundColor Red
    Write-Host "         Las que faltaron se pueden reintentar con --paciente y --fecha." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host ""
Write-Host "[3/3] OK" -ForegroundColor Green
Write-Host ""

# --- Resumen ---------------------------------------------------------------
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  Pipeline completo." -ForegroundColor Cyan
Write-Host ""
Write-Host "  DB regenerada:        data/analysis/fichas_completo.db" -ForegroundColor Gray
Write-Host "  Informe del mes:      data/analysis/informe_fichas_abiertas_$(Get-Date -Format 'MM-yyyy').txt" -ForegroundColor Gray
$NotasDir = Join-Path $RepoRoot "notas_clinicas"
$CountNotas = (Get-ChildItem -Path $NotasDir -Filter "*.txt" -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "  Notas clinicas (.txt): $CountNotas archivos en notas_clinicas/" -ForegroundColor Gray
Write-Host ""

# --- Paso 4/5: tests como guardrail ----------------------------------------
Write-Host "[4/5] pytest tests/ (guardrail)" -ForegroundColor Yellow
Write-Host "      Corriendo suite de tests para validar construccion de notas..."
Write-Host ""
python -m pytest tests/ -q --no-header --tb=line 2>&1 | Select-Object -Last 5 | ForEach-Object { Write-Host "      $_" }
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] tests fallaron (codigo $LASTEXITCODE)" -ForegroundColor Red
    Write-Host "         Las screenshots se preservan en logs/screenshots/ para debug." -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host ""
Write-Host "[4/5] tests OK" -ForegroundColor Green
Write-Host ""

# --- Paso 5/5: limpiar screenshots ----------------------------------------
Write-Host "[5/5] limpiar_screenshots" -ForegroundColor Yellow
Write-Host "      Borrando capturas de diagnostico de logs/screenshots/..."
Write-Host ""
python -m src.tools.limpiar_screenshots
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[WARN] limpiar_screenshots fallo (codigo $LASTEXITCODE). Capturas quedan en disco." -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "[5/5] OK" -ForegroundColor Green
}
Write-Host ""

Write-Host "  Proximo paso (cuando lo decidas): pipeline LLM para procesar las" -ForegroundColor Gray
Write-Host "  notas — vive en la zona a corregir y se corre con scripts separados." -ForegroundColor Gray
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host ""

exit 0