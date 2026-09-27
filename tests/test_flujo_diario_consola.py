"""Tests del filtro de consola de flujo_diario (REQ-008, consola legible).

El filtro decide que se muestra en pantalla; TODO lo suprimido va al
log de corrida (logs/flujo_diario_<ts>.log). Cubren:
- Ruido de navegacion suprimido (modal Cargando, fecha, sort, screenshot).
- Stacktraces de chromedriver suprimidos.
- INFO con timestamp -> solo el mensaje.
- WARNING -> prefijo [!]; ERROR -> prefijo [X].
- Filas y separadores del volcado del informe base suprimidos.
- Linea informativa de progreso se mantiene.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("flujo_diario", _ROOT / "flujo_diario.py")
fd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fd)


def test_ruido_de_navegacion_suprimido() -> None:
    assert fd.clasificar_linea(
        "2026-09-27 02:44:25 - login_automation - INFO - No se detectó modal 'Cargando' — página probablemente ya cargada\n"
    ) is None
    assert fd.clasificar_linea(
        "2026-09-27 02:44:25 - login_automation - INFO - Fecha 24-09-2026 ingresada\n"
    ) is None
    assert fd.clasificar_linea(
        "2026-09-27 02:44:41 - login_automation - INFO - Tabla ordenada por Estado (descendente)\n"
    ) is None
    assert fd.clasificar_linea(
        "2026-09-27 02:44:00 - login_automation - INFO - Screenshot: C:\\x\\y.png\n"
    ) is None


def test_stacktrace_chromedriver_suprimido() -> None:
    assert fd.clasificar_linea("Stacktrace:\n") is None
    assert fd.clasificar_linea("\tchromedriver!GetHandleVerifier [0x7ff72bd51035+5a95]\n") is None
    assert fd.clasificar_linea("  KERNEL32!BaseThreadInitThunk [0x7ff8d2bdcd87+17]\n") is None
    assert fd.clasificar_linea(
        "  (Session info: chrome=153.0.8010.53); For documentation on this error, please visit: https://...\n"
    ) is None


def test_info_deja_solo_el_mensaje() -> None:
    assert fd.clasificar_linea(
        "2026-09-27 23:10:39,343 [INFO] [crear_notas] Pía Karolina Arce Gárate OK -> Pía_Karolina_Arce_Gárate_25-09-2026.md\n"
    ) == "[crear_notas] Pía Karolina Arce Gárate OK -> Pía_Karolina_Arce_Gárate_25-09-2026.md"


def test_warning_y_error_marcan_prefijo() -> None:
    assert fd.clasificar_linea(
        "2026-09-27 02:44:25 - login_automation - WARNING - Panel no aparecio en 60s.\n"
    ) == "[!] Panel no aparecio en 60s."
    assert fd.clasificar_linea(
        "2026-09-27 02:44:25 - login_automation - ERROR - Error con paciente X.\n"
    ) == "[X] Error con paciente X."


def test_volcado_informe_base_suprimido() -> None:
    assert fd.clasificar_linea(
        "24-09-2026    Beatriz Raquel Gallardo Fernánde  (-)    Control integral ecicep-g3    (-)\n"
    ) is None
    assert fd.clasificar_linea("=" * 100 + "\n") is None
    assert fd.clasificar_linea("-" * 100 + "\n") is None


def test_linea_util_se_mantiene() -> None:
    assert fd.clasificar_linea("(3/20) Procesando: Rosalba Olivares Cardone (25-09-2026)\n") == (
        "(3/20) Procesando: Rosalba Olivares Cardone (25-09-2026)"
    )
    assert fd.clasificar_linea("[modo MENSUAL/rango] archivo: informe.txt\n") == (
        "[modo MENSUAL/rango] archivo: informe.txt"
    )


def test_linea_vacia_suprimida() -> None:
    assert fd.clasificar_linea("\n") is None
    assert fd.clasificar_linea("   \n") is None


def test_cadena_tiene_los_6_pasos_y_termina_en_8() -> None:
    assert [num for num, _, _ in fd.PASOS] == ["4", "5", "3", "6", "7", "8"]
    assert "cargar_ficha" in " ".join(fd.PASOS[-1][2])
