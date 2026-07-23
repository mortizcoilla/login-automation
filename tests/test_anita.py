"""Tests para Anita (reportes diarios)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import queue_store
from src.anita import format_telegram, report_generator
from src.anita.format_telegram import formatear_telegram
from src.anita.report_generator import generar_reporte
from src.queue_store import (
    EstadoFicha,
    crear_ficha,
    inicializar_db,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "queue.db"
    inicializar_db(path)
    return path


def _simular_dia_completo(db_path: Path) -> None:
    """Crea 5 fichas en distintas estados para alimentar el reporte."""
    f1 = crear_ficha(db_path, "A", "Control Crónico", "23-07-2026")
    f2 = crear_ficha(db_path, "B", "Control Crónico", "23-07-2026")
    f3 = crear_ficha(db_path, "C", "Morbilidad", "23-07-2026")
    f4 = crear_ficha(db_path, "D", "ECICEP-G1", "23-07-2026")
    f5 = crear_ficha(db_path, "E", "Morbilidad", "23-07-2026")
    # Flujo de f1: completa (enviada)
    queue_store.avanzar_estado(db_path, f1.id, EstadoFicha.EN_REVISION_USER, "s", "M")
    queue_store.avanzar_estado(db_path, f1.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO, "u", "A")
    queue_store.avanzar_estado(db_path, f1.id, EstadoFicha.ENVIADO, "u", "E")
    # Flujo de f2: aprobada pero no enviada
    queue_store.avanzar_estado(db_path, f2.id, EstadoFicha.EN_REVISION_USER, "s", "M")
    queue_store.avanzar_estado(db_path, f2.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO, "u", "A")
    # Flujo de f3: en revisión todavía
    queue_store.avanzar_estado(db_path, f3.id, EstadoFicha.EN_REVISION_USER, "s", "M")
    # Flujo de f4: descartada
    queue_store.avanzar_estado(db_path, f4.id, EstadoFicha.DESCARTADO, "u", "D")
    # f5 queda en DRAFT_GENERADO


# === Generador de reporte ===

def test_reporte_vacio(db_path: Path) -> None:
    r = generar_reporte(str(db_path), "23-07-2026")
    assert r.fecha == "23-07-2026"
    assert r.total_iniciadas == 0
    assert r.total_cerradas == 0
    assert r.tasa_cierre_pct == 0
    assert r.por_tipo == {}
    assert r.por_estado == {}


def test_reporte_con_fichas(db_path: Path) -> None:
    _simular_dia_completo(db_path)
    r = generar_reporte(str(db_path), "23-07-2026")
    assert r.total_iniciadas == 5
    assert r.total_enviadas == 1
    assert r.total_rechazadas == 1
    assert r.total_cerradas == 2  # 1 enviada + 1 rechazada
    assert r.total_pendientes == 3
    assert r.tasa_cierre_pct == 40.0  # 2/5 = 40%
    assert r.por_tipo == {
        "Control Crónico": 2,
        "Morbilidad": 2,
        "ECICEP-G1": 1,
    }
    assert r.por_estado == {
        "DRAFT_GENERADO": 1,
        "EN_REVISION_USER": 1,
        "APROBADO_PENDIENTE_ENVIO": 1,
        "ENVIADO": 1,
        "DESCARTADO": 1,
    }


def test_reporte_default_hoy(db_path: Path) -> None:
    """Si no se pasa fecha, usa hoy."""
    from datetime import datetime
    hoy = datetime.now().strftime("%d-%m-%Y")
    crear_ficha(db_path, "A", "Control", hoy)
    r = generar_reporte(str(db_path))  # sin fecha
    assert r.fecha == hoy
    assert r.total_iniciadas == 1


# === Formateo para Telegram ===

def test_formato_telegram_sin_fichas(db_path: Path) -> None:
    r = generar_reporte(str(db_path), "23-07-2026")
    texto = formatear_telegram(r)
    assert "Reporte del día" in texto
    assert "23-07-2026" in texto
    assert "No se registraron fichas" in texto


def test_formato_telegram_con_fichas(db_path: Path) -> None:
    _simular_dia_completo(db_path)
    r = generar_reporte(str(db_path), "23-07-2026")
    texto = formatear_telegram(r)
    # Verificar secciones principales
    assert "Reporte del día" in texto
    assert "Resumen general" in texto
    assert "Por tipo de atención" in texto
    assert "Estado actual" in texto
    assert "Resultado de cierre" in texto
    # Verificar datos clave
    assert "Iniciadas: *5*" in texto
    assert "Cerradas: *2*" in texto
    assert "Tasa de cierre: *40.0%*" in texto
    # Verificar tipos mencionados (sin escape de guiones en el output)
    assert "Control Crónico" in texto
    assert "Morbilidad" in texto
    assert "ECICEP-G1" in texto


def test_formato_telegram_escapa_caracteres_especiales(db_path: Path) -> None:
    """Telegram MarkdownV2 requiere escapar algunos caracteres."""
    crear_ficha(db_path, "Test", "Control [especial]", "23-07-2026")
    r = generar_reporte(str(db_path), "23-07-2026")
    texto = formatear_telegram(r)
    # Los corchetes sí deben estar escapados (afectan links)
    assert r"Control \[especial\]" in texto


def test_formato_telegram_usa_terminos_amigables(db_path: Path) -> None:
    _simular_dia_completo(db_path)
    r = generar_reporte(str(db_path), "23-07-2026")
    texto = formatear_telegram(r)
    # Con 1 ficha en cada estado, debe usar singular correctamente
    assert "1 ficha enviada ✅" in texto
    assert "1 ficha descartada" in texto
    assert "esperando revisión" in texto
    assert "aprobada, falta enviar" in texto  # singular
    # El nombre técnico NO debe aparecer tal cual
    assert "ENVIADO" not in texto
    assert "DESCARTADO" not in texto


def test_formato_telegram_pluraliza_correctamente(db_path: Path) -> None:
    """Con varias fichas en el mismo estado, debe usar plural."""
    f1 = crear_ficha(db_path, "A", "Control", "23-07-2026")
    f2 = crear_ficha(db_path, "B", "Control", "23-07-2026")
    f3 = crear_ficha(db_path, "C", "Control", "23-07-2026")
    for f in [f1, f2, f3]:
        queue_store.avanzar_estado(db_path, f.id, EstadoFicha.EN_REVISION_USER, "s", "M")
    r = generar_reporte(str(db_path), "23-07-2026")
    texto = formatear_telegram(r)
    assert "3 fichas esperando revisión" in texto
    assert "3 fichas en draft" not in texto  # las 3 están en revisión, no en draft


# === CLI del cron ===

def test_cron_runner_sin_db_existe_falla(tmp_path: Path, capsys) -> None:
    from src.anita.cron_runner import main
    rc = main(["--db", str(tmp_path / "nope.db")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "DB no existe" in err


def test_cron_runner_dry_run_sin_db_es_ok(tmp_path: Path, capsys) -> None:
    from src.anita.cron_runner import main
    rc = main(["--db", str(tmp_path / "nope.db"), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "--dry-run" in out


def test_cron_runner_formato_telegram(db_path: Path, capsys) -> None:
    from src.anita.cron_runner import main
    _simular_dia_completo(db_path)
    rc = main(["--db", str(db_path), "--fecha", "23-07-2026", "--formato", "telegram"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Reporte del día" in out


def test_cron_runner_formato_json(db_path: Path, capsys) -> None:
    import json
    from src.anita.cron_runner import main
    _simular_dia_completo(db_path)
    rc = main(["--db", str(db_path), "--fecha", "23-07-2026", "--formato", "json"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["total_iniciadas"] == 5
    assert data["tasa_cierre_pct"] == 40.0
