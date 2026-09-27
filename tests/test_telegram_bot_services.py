"""Tests para el facade src.telegram_bot.services.recibir_foto_service.

Mockeamos `recibir_y_archivar` (del tool existente) para NO ejecutar la
logica real: matching, I/O de disco, normalizacion. Eso ya tiene su propia
suite (test_recibir_foto_examen.py). Acá solo verificamos el pass-through
de kwargs.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.telegram_bot.services.recibir_foto_service import (
    archivar_foto_desde_telegram,
)


def test_pasa_kwargs_al_tool():
    """Los kwargs obligatorios se envian tal cual al tool."""
    with patch("src.telegram_bot.services.recibir_foto_service.recibir_y_archivar") as tool:
        tool.return_value = {"ok": True}
        resultado = archivar_foto_desde_telegram(
            input_path=Path("/tmp/x.jpg"),
            indice_n=1,
            nombre_paciente="Benedicto",
            fecha_atencion="16-09-2026",
        )

    tool.assert_called_once_with(
        input_path=Path("/tmp/x.jpg"),
        indice_n=1,
        nombre_paciente="Benedicto",
        fecha_atencion="16-09-2026",
    )
    assert resultado == {"ok": True}


def test_overrides_se_pasan_al_tool():
    """Si se pasan overrides de dirs, viajan al tool."""
    with patch("src.telegram_bot.services.recibir_foto_service.recibir_y_archivar") as tool:
        tool.return_value = {"ok": True}
        archivar_foto_desde_telegram(
            input_path=Path("/x.jpg"),
            indice_n=2,
            nombre_paciente="Marta",
            fecha_atencion=None,
            destino_dir_override=Path("/dest"),
            notas_dir_override=Path("/notas"),
        )

    tool.assert_called_once_with(
        input_path=Path("/x.jpg"),
        indice_n=2,
        nombre_paciente="Marta",
        fecha_atencion=None,
        destino_dir=Path("/dest"),
        notas_dir=Path("/notas"),
    )


def test_sin_overrides_no_pasa_dirs_al_tool():
    """Sin overrides -> no se pasan 'destino_dir' ni 'notas_dir' (usa defaults)."""
    with patch("src.telegram_bot.services.recibir_foto_service.recibir_y_archivar") as tool:
        tool.return_value = {"ok": True}
        archivar_foto_desde_telegram(
            input_path=Path("/x.jpg"),
            indice_n=1,
            nombre_paciente=None,
            fecha_atencion=None,
        )

    call = tool.call_args
    assert "destino_dir" not in call.kwargs
    assert "notas_dir" not in call.kwargs


def test_override_solo_destino():
    """Override de uno solo (no ambos) -> solo ese viaja."""
    with patch("src.telegram_bot.services.recibir_foto_service.recibir_y_archivar") as tool:
        tool.return_value = {"ok": True}
        archivar_foto_desde_telegram(
            input_path=Path("/x.jpg"),
            indice_n=1,
            nombre_paciente="x",
            fecha_atencion=None,
            destino_dir_override=Path("/destino"),
        )

    tool.assert_called_once_with(
        input_path=Path("/x.jpg"),
        indice_n=1,
        nombre_paciente="x",
        fecha_atencion=None,
        destino_dir=Path("/destino"),
    )


def test_retorna_el_dict_del_tool_sin_modificar():
    """El facade devuelve exactamente lo que retorna el tool (pass-through)."""
    with patch("src.telegram_bot.services.recibir_foto_service.recibir_y_archivar") as tool:
        tool.return_value = {"ok": False, "error": "Extension invalida"}
        r = archivar_foto_desde_telegram(
            input_path=Path("/x.jpg"),
            indice_n=1,
            nombre_paciente="x",
            fecha_atencion=None,
        )
    assert r == {"ok": False, "error": "Extension invalida"}


def test_datetime_o_excepciones_del_tool_se_propagans():
    """Si el tool lanza (no deberia, pero por las dudas), el facade propaga."""
    with patch("src.telegram_bot.services.recibir_foto_service.recibir_y_archivar") as tool:
        tool.side_effect = RuntimeError("disk full")
        try:
            archivar_foto_desde_telegram(
                input_path=Path("/x.jpg"),
                indice_n=1,
                nombre_paciente="x",
                fecha_atencion=None,
            )
        except RuntimeError as exc:
            assert "disk full" in str(exc)
        else:
            raise AssertionError("Debio haber propagado la excepcion")
