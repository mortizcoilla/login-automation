"""Tests para el store de la cola de fichas (queue_store)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src import queue_store
from src.queue_store import (
    EstadoFicha,
    FichaNoEncontradaError,
    TokenInvalidoError,
    TransicionInvalidaError,
    avanzar_estado,
    crear_ficha,
    generar_token,
    inicializar_db,
    listar_fichas_hoy,
    listar_fichas_por_estado,
    obtener_ficha,
    obtener_metricas_dia,
    validar_y_consumir_token,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "queue.db"
    inicializar_db(path)
    return path


# === Inicialización ===

def test_inicializar_db_crea_archivo(tmp_path: Path) -> None:
    path = tmp_path / "fresh.db"
    assert not path.exists()
    inicializar_db(path)
    assert path.exists()


def test_inicializar_db_es_idempotente(db_path: Path) -> None:
    """Llamar inicializar dos veces no rompe nada."""
    inicializar_db(db_path)
    inicializar_db(db_path)
    crear_ficha(db_path, "Test", "Control", "23-07-2026")  # sigue funcionando


# === Creación de fichas ===

def test_crear_ficha_devuelve_ficha_en_draft(db_path: Path) -> None:
    ficha = crear_ficha(db_path, "Juan Pérez", "Control Crónico", "23-07-2026")
    assert ficha.id > 0
    assert ficha.paciente_nombre == "Juan Pérez"
    assert ficha.tipo_atencion == "Control Crónico"
    assert ficha.estado == EstadoFicha.DRAFT_GENERADO
    assert ficha.fecha_consulta == "23-07-2026"
    assert ficha.contenido_actual == ""


def test_crear_ficha_es_idempotente_por_paciente_fecha_tipo(db_path: Path) -> None:
    """Si Pancho lista 2 veces el mismo paciente, no se duplica."""
    f1 = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    f2 = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    assert f1.id == f2.id
    assert len(listar_fichas_por_estado(db_path)) == 1


def test_crear_ficha_con_rut_lo_hashea(db_path: Path) -> None:
    """El RUT nunca se guarda en claro, solo el hash."""
    ficha = crear_ficha(
        db_path, "Juan", "Control", "23-07-2026", rut="12345678-9"
    )
    assert "12345678" not in ficha.rut_hash
    assert len(ficha.rut_hash) == 16  # sha256[:16]


def test_crear_ficha_con_contenido_hashea(db_path: Path) -> None:
    contenido = "PACIENTE: Juan\nNOTA: HTA"
    ficha = crear_ficha(db_path, "Juan", "Control", "23-07-2026", contenido=contenido)
    assert ficha.contenido_actual == contenido
    assert len(ficha.hash_contenido_actual) == 64  # sha256 completo


def test_crear_ficha_actualiza_metrica_dia(db_path: Path) -> None:
    crear_ficha(db_path, "A", "Control", "23-07-2026")
    crear_ficha(db_path, "B", "Control", "23-07-2026")
    metricas = obtener_metricas_dia(db_path, "23-07-2026")
    assert metricas["total_iniciadas"] == 2
    assert metricas["total_enviadas"] == 0


# === Transiciones de estado ===

def test_draft_a_revision_usuario(db_path: Path) -> None:
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    f2 = avanzar_estado(
        db_path, f.id, EstadoFicha.EN_REVISION_USER,
        aprobador_id="simulacion", accion="MOSTRAR_USER",
    )
    assert f2.estado == EstadoFicha.EN_REVISION_USER


def test_revision_a_aprobado_pendiente_envio(db_path: Path) -> None:
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    avanzar_estado(db_path, f.id, EstadoFicha.EN_REVISION_USER, "sim", "MOSTRAR")
    f2 = avanzar_estado(
        db_path, f.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO,
        aprobador_id="telegram:111", accion="APROBAR",
    )
    assert f2.estado == EstadoFicha.APROBADO_PENDIENTE_ENVIO


def test_aprobado_a_enviado_termina_flujo(db_path: Path) -> None:
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    avanzar_estado(db_path, f.id, EstadoFicha.EN_REVISION_USER, "sim", "MOSTRAR")
    avanzar_estado(
        db_path, f.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO,
        "telegram:111", "APROBAR",
    )
    f2 = avanzar_estado(
        db_path, f.id, EstadoFicha.ENVIADO,
        aprobador_id="telegram:111", accion="ENVIAR",
    )
    assert f2.estado == EstadoFicha.ENVIADO


def test_transicion_a_enviado_actualiza_metricas(db_path: Path) -> None:
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    avanzar_estado(db_path, f.id, EstadoFicha.EN_REVISION_USER, "sim", "M")
    avanzar_estado(db_path, f.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO, "u", "A")
    avanzar_estado(db_path, f.id, EstadoFicha.ENVIADO, "u", "ENVIAR")
    m = obtener_metricas_dia(db_path, "23-07-2026")
    assert m["total_enviadas"] == 1
    assert m["total_cerradas"] == 1


def test_transicion_invalida_rechaza(db_path: Path) -> None:
    """DRAFT_GENERADO -> ENVIADO directamente debe rechazarse."""
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    with pytest.raises(TransicionInvalidaError, match="Transición ilegal"):
        avanzar_estado(
            db_path, f.id, EstadoFicha.ENVIADO,
            "x", "ENVIO_DIRECTO",
        )


def test_aprobado_puede_volver_a_revision_si_yadira_reconsidera(db_path: Path) -> None:
    """APROBADO_PENDIENTE_ENVIO -> EN_REVISION_USER (reconsiderar) está permitido."""
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    avanzar_estado(db_path, f.id, EstadoFicha.EN_REVISION_USER, "sim", "M")
    avanzar_estado(db_path, f.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO, "u", "A")
    f2 = avanzar_estado(
        db_path, f.id, EstadoFicha.EN_REVISION_USER,
        aprobador_id="u", accion="RECONSIDERAR",
        metadata={"razon": "me arrepentí, quiero editar"},
    )
    assert f2.estado == EstadoFicha.EN_REVISION_USER


def test_enviado_es_terminal(db_path: Path) -> None:
    """Una vez ENVIADO, no se puede transicionar más."""
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    avanzar_estado(db_path, f.id, EstadoFicha.EN_REVISION_USER, "s", "M")
    avanzar_estado(db_path, f.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO, "u", "A")
    avanzar_estado(db_path, f.id, EstadoFicha.ENVIADO, "u", "E")
    with pytest.raises(TransicionInvalidaError):
        avanzar_estado(
            db_path, f.id, EstadoFicha.DESCARTADO,
            "u", "REVERTIR",
        )


def test_descartado_es_terminal(db_path: Path) -> None:
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    avanzar_estado(db_path, f.id, EstadoFicha.DESCARTADO, "u", "DESCARTAR")
    with pytest.raises(TransicionInvalidaError):
        avanzar_estado(
            db_path, f.id, EstadoFicha.EN_REVISION_USER,
            "u", "REACTIVAR",
        )


def test_en_correccion_vuelve_a_revision(db_path: Path) -> None:
    """EN_CORRECCION -> EN_REVISION_USER cuando Teodoro regenera el draft."""
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    avanzar_estado(db_path, f.id, EstadoFicha.EN_REVISION_USER, "s", "M")
    avanzar_estado(
        db_path, f.id, EstadoFicha.EN_CORRECCION,
        "u", "PEDIR_CORRECCION", metadata={"feedback": "agrega creatinina"},
    )
    f2 = avanzar_estado(
        db_path, f.id, EstadoFicha.EN_REVISION_USER,
        aprobador_id="sistema", accion="REGENERAR_DRAFT",
    )
    assert f2.estado == EstadoFicha.EN_REVISION_USER


# === Historial de aprobaciones (auditoría) ===

def test_historial_queda_registrado(db_path: Path) -> None:
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    avanzar_estado(db_path, f.id, EstadoFicha.EN_REVISION_USER, "s", "MOSTRAR_USER")
    avanzar_estado(
        db_path, f.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO,
        aprobador_id="telegram:111", accion="APROBAR",
        metadata={"hash_corto": "abc123"},
    )
    with queue_store.get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM historial_aprobaciones WHERE ficha_id = ? ORDER BY id",
            (f.id,),
        ).fetchall()
    acciones = [r["accion"] for r in rows]
    aprobadores = [r["aprobador_id"] for r in rows]
    assert acciones == ["GENERAR_DRAFT", "MOSTRAR_USER", "APROBAR"]
    assert aprobadores == ["sistema", "s", "telegram:111"]


def test_historial_almacena_metadata_json(db_path: Path) -> None:
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    avanzar_estado(
        db_path, f.id, EstadoFicha.DESCARTADO,
        aprobador_id="telegram:111", accion="DESCARTAR",
        metadata={"razon": "datos incorrectos", "feedback": "el RUT está mal"},
    )
    with queue_store.get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT metadata_json FROM historial_aprobaciones WHERE ficha_id = ? AND accion = 'DESCARTAR'",
            (f.id,),
        ).fetchone()
    meta = json.loads(row["metadata_json"])
    assert meta["razon"] == "datos incorrectos"
    assert meta["feedback"] == "el RUT está mal"


# === Tokens de aprobación ===

def test_generar_y_validar_token(db_path: Path) -> None:
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    contenido = "PACIENTE: Juan\nHTA controlada"
    token = generar_token(db_path, f.id, contenido, ttl_segundos=60)
    assert token.id > 0
    assert token.ficha_id == f.id
    # Validar y consumir debe funcionar
    validar_y_consumir_token(db_path, token.id, f.id, contenido)


def test_token_no_reutilizable(db_path: Path) -> None:
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    contenido = "x"
    token = generar_token(db_path, f.id, contenido)
    validar_y_consumir_token(db_path, token.id, f.id, contenido)
    # Segundo intento debe fallar
    with pytest.raises(TokenInvalidoError, match="ya fue utilizado"):
        validar_y_consumir_token(db_path, token.id, f.id, contenido)


def test_token_rechaza_si_contenido_cambio(db_path: Path) -> None:
    """Si el contenido cambió después de aprobar, el token no sirve."""
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    contenido_v1 = "primera version"
    contenido_v2 = "version modificada por la médica"
    token = generar_token(db_path, f.id, contenido_v1)
    with pytest.raises(TokenInvalidoError, match="no corresponde a este contenido"):
        validar_y_consumir_token(db_path, token.id, f.id, contenido_v2)


def test_token_rechaza_si_otra_ficha(db_path: Path) -> None:
    f1 = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    f2 = crear_ficha(db_path, "Maria", "Control", "23-07-2026")
    contenido = "x"
    token = generar_token(db_path, f1.id, contenido)
    with pytest.raises(TokenInvalidoError, match="no corresponde a esta ficha"):
        validar_y_consumir_token(db_path, token.id, f2.id, contenido)


def test_token_rechaza_si_expirado(db_path: Path) -> None:
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026")
    contenido = "x"
    # TTL de 0 segundos: ya expirado al instante
    token = generar_token(db_path, f.id, contenido, ttl_segundos=0)
    # Forzamos la expiración: ajustamos la fecha de expiración hacia atrás
    with queue_store.get_connection(db_path) as conn:
        pasado = (datetime.now() - timedelta(seconds=10)).isoformat(timespec="seconds")
        conn.execute(
            "UPDATE tokens SET expira_en = ? WHERE id = ?", (pasado, token.id)
        )
    with pytest.raises(TokenInvalidoError, match="expirado"):
        validar_y_consumir_token(db_path, token.id, f.id, contenido)


# === Listados y consultas ===

def test_listar_fichas_por_estado(db_path: Path) -> None:
    f1 = crear_ficha(db_path, "A", "Control", "23-07-2026")
    f2 = crear_ficha(db_path, "B", "Control", "23-07-2026")
    f3 = crear_ficha(db_path, "C", "Morbilidad", "23-07-2026")
    avanzar_estado(db_path, f1.id, EstadoFicha.EN_REVISION_USER, "s", "M")
    avanzar_estado(db_path, f2.id, EstadoFicha.DESCARTADO, "s", "D")

    en_revision = listar_fichas_por_estado(db_path, EstadoFicha.EN_REVISION_USER)
    assert {f.id for f in en_revision} == {f1.id}
    descartadas = listar_fichas_por_estado(db_path, EstadoFicha.DESCARTADO)
    assert {f.id for f in descartadas} == {f2.id}
    drafts = listar_fichas_por_estado(db_path, EstadoFicha.DRAFT_GENERADO)
    assert {f.id for f in drafts} == {f3.id}


def test_listar_fichas_hoy(db_path: Path) -> None:
    crear_ficha(db_path, "A", "Control", "23-07-2026")
    crear_ficha(db_path, "B", "Control", "22-07-2026")  # ayer
    hoy = listar_fichas_hoy(db_path, "23-07-2026")
    assert len(hoy) == 1
    assert hoy[0].paciente_nombre == "A"


def test_obtener_ficha_inexistente_lanza_error(db_path: Path) -> None:
    with pytest.raises(FichaNoEncontradaError):
        obtener_ficha(db_path, 99999)


# === Actualizar contenido (para regeneraciones) ===

def test_actualizar_contenido_cambia_hash(db_path: Path) -> None:
    f = crear_ficha(db_path, "Juan", "Control", "23-07-2026", contenido="v1")
    f2 = queue_store.actualizar_contenido(
        db_path, f.id, "v2 corregida", aprobador_id="sistema",
    )
    assert f2.contenido_actual == "v2 corregida"
    assert f2.hash_contenido_actual != f.hash_contenido_actual
