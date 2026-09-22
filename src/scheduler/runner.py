"""Runner del scheduler: decide que vence y ejecuta la cadena diaria.

Invocacion (la tarea de Windows dispara cada 30 min):
    python -m src.scheduler.runner --check

Acciones:
    --check            (default) lee calendario+estado, corre lo vencido.
    --listar           muestra que estaria vencido ahora, SIN correr nada.
    --forzar USUARIO   corre la cadena de ese usuario ignorando calendario
                       y estado (pruebas manuales); actualiza estado igual.

Estado: data/scheduler_estado.json. Se marca el intento ANTES de correr
para que dos disparos consecutivos (30 min) no lancen dos cadenas en
paralelo; al terminar se actualiza ok/fallos. Un dia con fallos reintenta
en el siguiente disparo hasta max_intentos_por_dia (REQ-060).

Este archivo funciona como modulo (-m) y como script directo (la tarea
de Windows lo invoca por path absoluto; bootstrap de sys.path incluido).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

if __package__ in (None, ""):  # script directo: bootstrap para `from src...`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core.rutas import DATA_DIR, LOGS_DIR, ROOT, informe_mes_actual_path
from src.scheduler import avisos
from src.scheduler.calendario import (
    CalendarioError,
    EntradaHorario,
    cargar_calendario,
    vencidas,
)

PY = ROOT / "venv" / "Scripts" / "python.exe"
if not PY.exists():  # fallback por compatibilidad si algun dia corre en Linux
    PY = ROOT / "venv" / "bin" / "python"

ESTADO_PATH = DATA_DIR / "scheduler_estado.json"
LOG_PATH = LOGS_DIR / "scheduler.log"


def _log(mensaje: str) -> None:
    """Una linea con timestamp al log del scheduler y a stdout."""
    linea = f"{datetime.now():%Y-%m-%d %H:%M:%S} {mensaje}"
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(linea + "\n")
    except OSError:
        pass  # el log no puede tumbar la corrida
    print(linea)


def _leer_estado() -> dict[str, dict[str, object]]:
    if not ESTADO_PATH.exists():
        return {}
    try:
        data = json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}  # estado corrupto: tratar como fresco (reintenta igual)
    return data if isinstance(data, dict) else {}


def _guardar_estado(estado: dict[str, dict[str, object]]) -> None:
    ESTADO_PATH.parent.mkdir(parents=True, exist_ok=True)
    ESTADO_PATH.write_text(
        json.dumps(estado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _marcar_intento(usuario: str, estado: dict[str, dict[str, object]]) -> None:
    """Registra el intento ANTES de correr (evita doble cadena en paralelo)."""
    hoy_iso = datetime.now().date().isoformat()
    previo = estado.get(usuario, {})
    fallos_previos = 0
    if previo.get("fecha_ultimo_intento") == hoy_iso:
        valor = previo.get("fallos_hoy", 0)
        if isinstance(valor, int):
            fallos_previos = valor
    estado[usuario] = {
        "fecha_ultimo_intento": hoy_iso,
        "fallos_hoy": fallos_previos + 1,
        "ok": False,
    }
    _guardar_estado(estado)


def _marcar_ok(usuario: str, estado: dict[str, dict[str, object]]) -> None:
    estado[usuario] = {
        "fecha_ultimo_intento": datetime.now().date().isoformat(),
        "fallos_hoy": 0,
        "ok": True,
    }
    _guardar_estado(estado)


def _cadena(usuario: str) -> list[list[str]]:
    """La cadena diaria (REQ-008, orden 4->5->3->6->7) parametrizada."""
    return [
        ["-m", "src.analysis.actualizar_mes_actual", usuario],
        ["-m", "src.analysis.informe_fichas_abiertas"],
        ["-m", "src.tools.crear_notas_clinicas", "--todos", "--user", usuario],
        ["-m", "src.analysis.enriquecer_informe"],
        ["-m", "src.tools.mortadelo", "--todos"],
    ]


def ejecutar_cadena(usuario: str) -> int:
    """Corre los 5 pasos del usuario. 0 si todos terminan en 0; si uno
    falla, el numero de ese paso (semantica &&).

    La salida de los pasos va al log (la tarea corre con pythonw: no hay
    consola donde caer).
    """
    _log(f"[{usuario}] inicio de cadena (4->5->3->6->7)")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    for numero, args in enumerate(_cadena(usuario), 1):
        _log(f"[{usuario}] paso {numero}/5: {' '.join(args)}")
        with LOG_PATH.open("a", encoding="utf-8") as logfh:
            resultado = subprocess.run(
                [str(PY), *args],
                cwd=str(ROOT),
                env=env,
                stdout=logfh,
                stderr=subprocess.STDOUT,
            )
        if resultado.returncode != 0:
            _log(
                f"[{usuario}] FALLO en paso {numero}/5 (codigo {resultado.returncode}). "
                f"La cadena se detiene; reintento en el proximo disparo si hay cupo."
            )
            return numero
    _log(f"[{usuario}] cadena completa OK")
    return 0


def _contar_pacientes_informe() -> int | None:
    """Cuantos pacientes trae el informe del mes (para el aviso de inicio).

    None si el informe aun no existe (paso 5 lo genera DENTRO de la
    cadena): en ese caso el aviso de inicio no menciona conteo.
    """
    try:
        ruta = informe_mes_actual_path()
        if not ruta.exists():
            return None
        from src.informes.parser import parsear_pacientes_objetivo

        return len(parsear_pacientes_objetivo(ruta))
    except Exception as e:  # el aviso no puede romper la cadena
        _log(f"aviso inicio: no pude contar pacientes del informe: {e}")
        return None


def _correr_vencidas(
    vencidas_hoy: list[EntradaHorario], estado: dict[str, dict[str, object]]
) -> int:
    """Corre cada entrada vencida. Devuelve codigo de salida.

    Paso 9 (REQ-076): aviso de inicio antes de la cadena y resumen de
    cierre despues. Un fallo del aviso no afecta la corrida.
    """
    fallidas = 0
    n_pacientes = _contar_pacientes_informe()
    for entrada in vencidas_hoy:
        _marcar_intento(entrada.usuario, estado)
        avisos.enviar(avisos.armar_mensaje_inicio(date.today(), n_pacientes))
        paso_fallido = ejecutar_cadena(entrada.usuario)
        if paso_fallido == 0:
            _marcar_ok(entrada.usuario, estado)
            conteo = avisos.contar_fichas_del_log(LOG_PATH)
            avisos.enviar(
                avisos.armar_mensaje_fin(
                    ok=True,
                    fichas_ok=conteo[0] if conteo else None,
                    paso_fallido=0,
                )
            )
        else:
            fallidas += 1
            avisos.enviar(
                avisos.armar_mensaje_fin(
                    ok=False, fichas_ok=None, paso_fallido=paso_fallido
                )
            )
    return 1 if fallidas else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scheduler", description="Cron del flujo diario (REQ-060)")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--check", action="store_true", help="corre lo vencido segun calendario (default)")
    grupo.add_argument("--listar", action="store_true", help="muestra lo vencido, sin correr")
    grupo.add_argument("--forzar", metavar="USUARIO", help="corre la cadena de USUARIO ya, sin calendario")
    parser.add_argument("--calendario", type=Path, default=None, help="path alternativo del calendario")
    args = parser.parse_args(argv)

    try:
        calendario = cargar_calendario(args.calendario)
    except CalendarioError as e:
        _log(f"ERROR de calendario: {e}")
        return 2

    estado = _leer_estado()
    ahora = datetime.now()

    if args.listar:
        pendientes = vencidas(calendario, ahora, estado)
        if not pendientes:
            print(f"Nada vencido a las {ahora:%H:%M} ({_nombre_hoy(ahora)}).")
            return 0
        for entrada in pendientes:
            print(f"VENCIDO: {entrada.usuario} ({entrada.dia_nombre} {entrada.hora:%H:%M})")
        return 0

    if args.forzar is not None:
        usuario = args.forzar.strip()
        conocidos = {e.usuario for e in calendario.entradas}
        if usuario not in conocidos:
            _log(f"ERROR: '{usuario}' no esta en el calendario (conocidos: {', '.join(sorted(conocidos))})")
            return 2
        _marcar_intento(usuario, estado)
        if ejecutar_cadena(usuario) == 0:
            _marcar_ok(usuario, estado)
            return 0
        return 1

    vencidas_hoy = vencidas(calendario, ahora, estado)
    if not vencidas_hoy:
        _log("check: nada vencido.")
        return 0
    _log(f"check: {len(vencidas_hoy)} vencida(s): " + ", ".join(e.usuario for e in vencidas_hoy))
    return _correr_vencidas(vencidas_hoy, estado)


def _nombre_hoy(ahora: datetime) -> str:
    nombres = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    return nombres[ahora.weekday()]


if __name__ == "__main__":
    sys.exit(main())
