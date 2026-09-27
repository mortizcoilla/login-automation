"""Fachada sobre src/tools/recibir_foto_examen.py:recibir_y_archivar().

Esta capa es deliberadamente fina. Su razon de existir es:
  - Handlers no importan directamente de src/tools/* (limpieza modular).
  - El bot no deberia romperse si la firma de recibir_y_archivar() cambia;
    el cambio se absorbe aqui.
  - Si en el futuro se quiere enriquecer con reintentos, logging, metricas,
    o coordinar con paso 2b (consolidar examenes), es el unico lugar donde tocar.

Por ahora, thin pass-through.
"""

from __future__ import annotations

from pathlib import Path

from src.tools.recibir_foto_examen import recibir_y_archivar


def archivar_foto_desde_telegram(
    input_path: Path,
    indice_n: int,
    nombre_paciente: str | None,
    fecha_atencion: str | None,
    destino_dir_override: Path | None = None,
    notas_dir_override: Path | None = None,
) -> dict:
    """Invoca recibir_y_archivar() con overrides opcionales para tests.

    Args:
        input_path: ruta al archivo descargado de Telegram (o fixture de test).
        indice_n: numero secuencial de la foto en el grupo (1, 2, 3, ...).
        nombre_paciente: nombre dado por Yadira (puede ser parcial).
        fecha_atencion: dd-mm-yyyy, o None para que se infiera del match.
        destino_dir_override: si se pasa, ignora el default del kernel.
        notas_dir_override: si se pasa, ignora el default del kernel.

    Returns:
        Dict con el resultado de recibir_y_archivar() (ver su contrato).
    """
    kwargs: dict = {
        "input_path": input_path,
        "indice_n": indice_n,
        "nombre_paciente": nombre_paciente,
        "fecha_atencion": fecha_atencion,
    }
    if destino_dir_override is not None:
        kwargs["destino_dir"] = destino_dir_override
    if notas_dir_override is not None:
        kwargs["notas_dir"] = notas_dir_override
    return recibir_y_archivar(**kwargs)
