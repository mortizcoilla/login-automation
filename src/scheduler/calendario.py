"""Calendario semanal configurable del flujo diario (REQ-060).

Fuente de verdad: config/calendario.json (commiteado, sin secretos):

    {
      "doctores": [
        {
          "usuario": "yadira",
          "horarios": [
            {"dia": "lunes", "hora": "17:30"},
            {"dia": "miercoles", "hora": "20:30"}
          ]
        }
      ],
      "max_intentos_por_dia": 3
    }

Cambiar horarios o agregar un doctor = editar este JSON. NO hace falta
re-registrar la tarea de Windows: el runner re-lee el calendario en cada
disparo (la tarea dispara cada 30 min y aqui se decide si corre).

Los dias aceptan el nombre en espanol con o sin tilde (miercoles/
miercoles, sabado/sabado). Las horas son HH:MM 24h, hora local del PC.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path

from src.core.rutas import ROOT

CALENDARIO_DEFAULT = ROOT / "config" / "calendario.json"

# indice del dia segun datetime.weekday(): lunes=0 ... domingo=6.
_DIAS_A_WEEKDAY = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}


class CalendarioError(ValueError):
    """Calendario ausente, malformado o sin entradas validas."""


def _sin_tildes(texto: str) -> str:
    """Minusculas sin tildes: 'Miércoles' -> 'miercoles'."""
    nfkd = unicodedata.normalize("NFD", texto.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


@dataclass(frozen=True)
class EntradaHorario:
    """Un horario puntual: tal doctor, tal dia de la semana, tal hora."""

    usuario: str
    dia_nombre: str  # normalizado, sin tildes (para logs)
    weekday: int
    hora: time


@dataclass(frozen=True)
class Calendario:
    """Calendario validado, listo para consultar vencimientos."""

    entradas: tuple[EntradaHorario, ...]
    max_intentos_por_dia: int = 3


def cargar_calendario(path: Path | None = None) -> Calendario:
    """Lee y valida config/calendario.json.

    Raises:
        CalendarioError: archivo ausente, JSON malformado, dia/hora
            invalida, usuario vacio, o cero entradas validas.
    """
    ruta = path or CALENDARIO_DEFAULT
    if not ruta.exists():
        raise CalendarioError(
            f"No existe {ruta}. Crealo con el formato documentado en "
            f"src/scheduler/calendario.py (doctores + horarios)."
        )
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CalendarioError(f"JSON malformado en {ruta}: {e}") from e

    doctores = data.get("doctores")
    if not isinstance(doctores, list) or not doctores:
        raise CalendarioError(f"{ruta}: falta la lista 'doctores' o esta vacia.")

    entradas: list[EntradaHorario] = []
    for doctor in doctores:
        usuario = str(doctor.get("usuario", "")).strip()
        if not usuario:
            raise CalendarioError(f"{ruta}: hay un doctor sin 'usuario'.")
        horarios = doctor.get("horarios")
        if not isinstance(horarios, list) or not horarios:
            raise CalendarioError(f"{ruta}: el doctor '{usuario}' no tiene 'horarios'.")
        for horario in horarios:
            dia = _sin_tildes(str(horario.get("dia", "")))
            if dia not in _DIAS_A_WEEKDAY:
                raise CalendarioError(
                    f"{ruta}: dia invalido {horario.get('dia')!r} para '{usuario}'. "
                    f"Validos: {', '.join(_DIAS_A_WEEKDAY)} (con o sin tilde)."
                )
            try:
                hora = time.fromisoformat(str(horario.get("hora", "")))
            except ValueError as e:
                raise CalendarioError(
                    f"{ruta}: hora invalida {horario.get('hora')!r} para '{usuario}' "
                    f"({dia}). Formato HH:MM 24h."
                ) from e
            entradas.append(
                EntradaHorario(
                    usuario=usuario,
                    dia_nombre=dia,
                    weekday=_DIAS_A_WEEKDAY[dia],
                    hora=hora,
                )
            )

    if not entradas:
        raise CalendarioError(f"{ruta}: ningun horario valido.")

    max_intentos = int(data.get("max_intentos_por_dia", 3))
    if max_intentos < 1:
        raise CalendarioError(f"{ruta}: max_intentos_por_dia debe ser >= 1.")

    return Calendario(entradas=tuple(entradas), max_intentos_por_dia=max_intentos)


def vencidas(
    calendario: Calendario,
    ahora: datetime,
    estado: dict[str, dict[str, object]],
) -> list[EntradaHorario]:
    """Entradas que corresponde ejecutar en este disparo.

    Criterios (todos obligatorios):
      - el dia de la semana coincide con hoy, y
      - la hora programada ya llego (hora <= ahora), y
      - el doctor no tiene una corrida OK hoy, y
      - los intentos fallidos de hoy no agotaron max_intentos_por_dia.

    Formato de estado (scheduler_estado.json): {usuario: {fecha_ultimo_intento:
    'YYYY-MM-DD', fallos_hoy: int, ok: bool}}. Usuarios sin entrada en el
    estado nunca han corrido: estan vencidos si su hora ya llego.
    """
    hoy_iso = ahora.date().isoformat()
    salida: list[EntradaHorario] = []
    for entrada in calendario.entradas:
        if entrada.weekday != ahora.weekday() or entrada.hora > ahora.time():
            continue
        registro = estado.get(entrada.usuario, {})
        if registro.get("fecha_ultimo_intento") == hoy_iso:
            if registro.get("ok") is True:
                continue
            fallos = registro.get("fallos_hoy", 0)
            if isinstance(fallos, int) and fallos >= calendario.max_intentos_por_dia:
                continue
        salida.append(entrada)
    return salida
