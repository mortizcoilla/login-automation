"""Capa de persistencia de la cola de fichas (SQLite).

Este módulo es la fuente de verdad del estado de cada ficha. Pilita, Teodoro
y Pancho operan sobre esta capa. Si MiniMax Code se cierra, el estado
sobrevive en `data/queue.db`.

Estados de una ficha (state machine):
    DRAFT_GENERADO            — el bot produjo un draft
    EN_REVISION_USER          — esperando revisión de Yadira
    EN_CORRECCION             — Yadira pidió cambios
    APROBADO_PENDIENTE_ENVIO  — Yadira aprobó con ✅, falta 📤
    ENVIADO                   — enviada a Rayen (terminal)
    DESCARTADO                — Yadira rechazó (terminal)

Reglas duras:
- El estado de una ficha SOLO cambia vía `avanzar_estado`, que valida que
  la transición sea legal.
- Toda acción queda registrada en `historial_aprobaciones` con timestamp
  y aprobador_id (Telegram sender_id de Yadira, o "simulacion" en tests).
- Los tokens de aprobación se persisten en `tokens` para auditoría
  completa (cuándo se emitió, cuándo se usó, cuándo expiró).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Iterator


class EstadoFicha(str, Enum):
    DRAFT_GENERADO = "DRAFT_GENERADO"
    EN_REVISION_USER = "EN_REVISION_USER"
    EN_CORRECCION = "EN_CORRECCION"
    APROBADO_PENDIENTE_ENVIO = "APROBADO_PENDIENTE_ENVIO"
    ENVIADO = "ENVIADO"
    DESCARTADO = "DESCARTADO"


# Transiciones legales. Cualquier otra lanza TransicionInvalidaError.
TRANSICIONES_LEGALES: dict[EstadoFicha, set[EstadoFicha]] = {
    EstadoFicha.DRAFT_GENERADO: {
        EstadoFicha.EN_REVISION_USER,
        EstadoFicha.DESCARTADO,
    },
    EstadoFicha.EN_REVISION_USER: {
        EstadoFicha.EN_CORRECCION,
        EstadoFicha.APROBADO_PENDIENTE_ENVIO,
        EstadoFicha.DESCARTADO,
    },
    EstadoFicha.EN_CORRECCION: {
        EstadoFicha.EN_REVISION_USER,
        EstadoFicha.DESCARTADO,
    },
    EstadoFicha.APROBADO_PENDIENTE_ENVIO: {
        EstadoFicha.ENVIADO,
        EstadoFicha.EN_REVISION_USER,  # Yadira reconsidera
    },
    # ENVIADO y DESCARTADO son terminales
}


class TransicionInvalidaError(ValueError):
    """La transición de estado no está permitida."""


class FichaNoEncontradaError(KeyError):
    """La ficha no existe en la cola."""


class TokenInvalidoError(PermissionError):
    """El token no es válido, expiró, o ya fue usado."""


@dataclass
class Ficha:
    id: int
    paciente_nombre: str
    rut_hash: str
    tipo_atencion: str
    estado: EstadoFicha
    contenido_actual: str
    hash_contenido_actual: str
    fecha_consulta: str
    created_at: str
    updated_at: str


@dataclass
class Token:
    id: int
    ficha_id: int
    hash_contenido: str
    expira_en: str
    usado_en: str | None = None


# === Conexión y schema ===

@contextmanager
def get_connection(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS fichas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paciente_nombre TEXT NOT NULL,
    rut_hash TEXT NOT NULL DEFAULT '',
    tipo_atencion TEXT NOT NULL,
    estado TEXT NOT NULL,
    contenido_actual TEXT NOT NULL DEFAULT '',
    hash_contenido_actual TEXT NOT NULL DEFAULT '',
    fecha_consulta TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historial_aprobaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ficha_id INTEGER NOT NULL,
    accion TEXT NOT NULL,
    aprobador_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (ficha_id) REFERENCES fichas(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ficha_id INTEGER NOT NULL,
    hash_contenido TEXT NOT NULL,
    expira_en TEXT NOT NULL,
    usado_en TEXT,
    FOREIGN KEY (ficha_id) REFERENCES fichas(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS metricas_diarias (
    fecha TEXT PRIMARY KEY,
    total_iniciadas INTEGER NOT NULL DEFAULT 0,
    total_cerradas INTEGER NOT NULL DEFAULT 0,
    total_enviadas INTEGER NOT NULL DEFAULT 0,
    total_rechazadas INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_fichas_estado ON fichas(estado);
CREATE INDEX IF NOT EXISTS idx_fichas_fecha ON fichas(fecha_consulta);
CREATE INDEX IF NOT EXISTS idx_historial_ficha ON historial_aprobaciones(ficha_id);
CREATE INDEX IF NOT EXISTS idx_tokens_ficha ON tokens(ficha_id);
"""


def inicializar_db(db_path: str | Path) -> None:
    """Crea las tablas si no existen. Idempotente."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


# === Helpers ===

def _row_to_ficha(row: sqlite3.Row) -> Ficha:
    return Ficha(
        id=row["id"],
        paciente_nombre=row["paciente_nombre"],
        rut_hash=row["rut_hash"],
        tipo_atencion=row["tipo_atencion"],
        estado=EstadoFicha(row["estado"]),
        contenido_actual=row["contenido_actual"],
        hash_contenido_actual=row["hash_contenido_actual"],
        fecha_consulta=row["fecha_consulta"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _hash_rut(rut: str) -> str:
    """Hash del RUT. Nunca guardamos el RUT real en la DB."""
    if not rut:
        return ""
    return hashlib.sha256(rut.encode("utf-8")).hexdigest()[:16]


def _hash_contenido(contenido: str) -> str:
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# === Operaciones de fichas ===

def crear_ficha(
    db_path: str | Path,
    paciente_nombre: str,
    tipo_atencion: str,
    fecha_consulta: str,
    rut: str = "",
    contenido: str = "",
) -> Ficha:
    """Crea una ficha nueva en estado DRAFT_GENERADO.

    Si ya existe una ficha con mismo (paciente_nombre, fecha_consulta,
    tipo_atencion), la retorna en vez de duplicar.
    """
    ahora = _now()
    hash_cont = _hash_contenido(contenido) if contenido else ""
    with get_connection(db_path) as conn:
        existing = conn.execute(
            """
            SELECT * FROM fichas
            WHERE paciente_nombre = ? AND fecha_consulta = ? AND tipo_atencion = ?
            """,
            (paciente_nombre, fecha_consulta, tipo_atencion),
        ).fetchone()
        if existing is not None:
            return _row_to_ficha(existing)

        cur = conn.execute(
            """
            INSERT INTO fichas (
                paciente_nombre, rut_hash, tipo_atencion, estado,
                contenido_actual, hash_contenido_actual,
                fecha_consulta, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paciente_nombre,
                _hash_rut(rut),
                tipo_atencion,
                EstadoFicha.DRAFT_GENERADO.value,
                contenido,
                hash_cont,
                fecha_consulta,
                ahora,
                ahora,
            ),
        )
        ficha_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO historial_aprobaciones
                (ficha_id, accion, aprobador_id, timestamp, metadata_json)
            VALUES (?, 'GENERAR_DRAFT', ?, ?, '{}')
            """,
            (ficha_id, "sistema", ahora),
        )
        # actualizar métrica del día
        conn.execute(
            """
            INSERT INTO metricas_diarias (fecha, total_iniciadas)
            VALUES (?, 1)
            ON CONFLICT(fecha) DO UPDATE SET total_iniciadas = total_iniciadas + 1
            """,
            (fecha_consulta,),
        )
        row = conn.execute("SELECT * FROM fichas WHERE id = ?", (ficha_id,)).fetchone()
    return _row_to_ficha(row)


def obtener_ficha(db_path: str | Path, ficha_id: int) -> Ficha:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM fichas WHERE id = ?", (ficha_id,)).fetchone()
    if row is None:
        raise FichaNoEncontradaError(f"Ficha id={ficha_id} no existe")
    return _row_to_ficha(row)


def actualizar_contenido(
    db_path: str | Path,
    ficha_id: int,
    contenido: str,
    aprobador_id: str = "sistema",
    accion: str = "REGENERAR_DRAFT",
) -> Ficha:
    """Actualiza el contenido de la ficha y registra en historial."""
    ahora = _now()
    hash_cont = _hash_contenido(contenido)
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE fichas
            SET contenido_actual = ?, hash_contenido_actual = ?, updated_at = ?
            WHERE id = ?
            """,
            (contenido, hash_cont, ahora, ficha_id),
        )
        conn.execute(
            """
            INSERT INTO historial_aprobaciones
                (ficha_id, accion, aprobador_id, timestamp, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ficha_id, accion, aprobador_id, ahora, json.dumps({"hash": hash_cont[:16]})),
        )
        row = conn.execute("SELECT * FROM fichas WHERE id = ?", (ficha_id,)).fetchone()
    if row is None:
        raise FichaNoEncontradaError(f"Ficha id={ficha_id} no existe")
    return _row_to_ficha(row)


def avanzar_estado(
    db_path: str | Path,
    ficha_id: int,
    nuevo_estado: EstadoFicha,
    aprobador_id: str,
    accion: str,
    metadata: dict[str, Any] | None = None,
) -> Ficha:
    """Transiciona el estado de una ficha, validando que sea legal.

    Lanza TransicionInvalidaError si la transición no está permitida.
    Registra la acción en historial_aprobaciones.

    Args:
        db_path: ruta a la DB.
        ficha_id: id de la ficha.
        nuevo_estado: estado al que se quiere transicionar.
        aprobador_id: 'simulacion' en tests, sender_id de Telegram en prod.
        accion: nombre de la acción (APROBAR, RECHAZAR, ENVIAR, etc.).
        metadata: datos adicionales a guardar (ej. feedback de rechazo).
    """
    ahora = _now()
    meta = metadata or {}
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM fichas WHERE id = ?", (ficha_id,)).fetchone()
        if row is None:
            raise FichaNoEncontradaError(f"Ficha id={ficha_id} no existe")
        estado_actual = EstadoFicha(row["estado"])
        if nuevo_estado not in TRANSICIONES_LEGALES.get(estado_actual, set()):
            raise TransicionInvalidaError(
                f"Transición ilegal: {estado_actual.value} -> {nuevo_estado.value}. "
                f"Transiciones legales desde {estado_actual.value}: "
                f"{[e.value for e in TRANSICIONES_LEGALES.get(estado_actual, set())]}"
            )
        conn.execute(
            "UPDATE fichas SET estado = ?, updated_at = ? WHERE id = ?",
            (nuevo_estado.value, ahora, ficha_id),
        )
        conn.execute(
            """
            INSERT INTO historial_aprobaciones
                (ficha_id, accion, aprobador_id, timestamp, metadata_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ficha_id, accion, aprobador_id, ahora, json.dumps(meta, ensure_ascii=False)),
        )
        # actualizar métricas si corresponde
        if nuevo_estado == EstadoFicha.ENVIADO:
            conn.execute(
                """
                INSERT INTO metricas_diarias (fecha, total_cerradas, total_enviadas)
                VALUES (?, 1, 1)
                ON CONFLICT(fecha) DO UPDATE SET
                    total_cerradas = total_cerradas + 1,
                    total_enviadas = total_enviadas + 1
                """,
                (row["fecha_consulta"],),
            )
        elif nuevo_estado == EstadoFicha.DESCARTADO:
            conn.execute(
                """
                INSERT INTO metricas_diarias (fecha, total_cerradas, total_rechazadas)
                VALUES (?, 1, 1)
                ON CONFLICT(fecha) DO UPDATE SET
                    total_cerradas = total_cerradas + 1,
                    total_rechazadas = total_rechazadas + 1
                """,
                (row["fecha_consulta"],),
            )
        new_row = conn.execute("SELECT * FROM fichas WHERE id = ?", (ficha_id,)).fetchone()
    return _row_to_ficha(new_row)


def listar_fichas_por_estado(
    db_path: str | Path,
    estado: EstadoFicha | None = None,
    fecha_consulta: str | None = None,
) -> list[Ficha]:
    """Lista fichas, opcionalmente filtradas por estado y/o fecha."""
    with get_connection(db_path) as conn:
        query = "SELECT * FROM fichas WHERE 1=1"
        params: list[Any] = []
        if estado is not None:
            query += " AND estado = ?"
            params.append(estado.value)
        if fecha_consulta is not None:
            query += " AND fecha_consulta = ?"
            params.append(fecha_consulta)
        query += " ORDER BY updated_at DESC"
        rows = conn.execute(query, params).fetchall()
    return [_row_to_fila(r) for r in rows] if False else [_row_to_ficha(r) for r in rows]


def listar_fichas_hoy(db_path: str | Path, fecha: str | None = None) -> list[Ficha]:
    """Devuelve las fichas de una fecha (default: hoy)."""
    if fecha is None:
        fecha = datetime.now().strftime("%d-%m-%Y")
    return listar_fichas_por_estado(db_path, fecha_consulta=fecha)


# === Tokens de aprobación (capa de DB) ===

def generar_token(
    db_path: str | Path,
    ficha_id: int,
    contenido: str,
    ttl_segundos: int = 300,
) -> Token:
    """Genera un token de aprobación y lo persiste.

    Un token es de un solo uso. Tiene TTL. El hash_contenido vincula
    el token al contenido específico aprobado.
    """
    ahora = datetime.now()
    expira = ahora + timedelta(seconds=ttl_segundos)
    hash_cont = _hash_contenido(contenido)
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO tokens (ficha_id, hash_contenido, expira_en)
            VALUES (?, ?, ?)
            """,
            (ficha_id, hash_cont, expira.isoformat(timespec="seconds")),
        )
        token_id = cur.lastrowid
    return Token(
        id=token_id,
        ficha_id=ficha_id,
        hash_contenido=hash_cont,
        expira_en=expira.isoformat(timespec="seconds"),
    )


def validar_y_consumir_token(
    db_path: str | Path,
    token_id: int,
    ficha_id: int,
    contenido: str,
) -> None:
    """Valida el token y lo marca como usado.

    Raises:
        TokenInvalidoError: si no existe, está usado, expiró,
            o no corresponde al contenido.
    """
    ahora = _now()
    hash_cont = _hash_contenido(contenido)
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM tokens WHERE id = ?", (token_id,)).fetchone()
        if row is None:
            raise TokenInvalidoError(f"Token id={token_id} no existe")
        if row["ficha_id"] != ficha_id:
            raise TokenInvalidoError("Token no corresponde a esta ficha")
        if row["hash_contenido"] != hash_cont:
            raise TokenInvalidoError("Token no corresponde a este contenido")
        if row["usado_en"] is not None:
            raise TokenInvalidoError("Token ya fue utilizado")
        if row["expira_en"] < ahora:
            raise TokenInvalidoError("Token expirado")
        conn.execute(
            "UPDATE tokens SET usado_en = ? WHERE id = ?",
            (ahora, token_id),
        )


# === Métricas ===

def obtener_metricas_dia(db_path: str | Path, fecha: str | None = None) -> dict[str, int]:
    if fecha is None:
        fecha = datetime.now().strftime("%d-%m-%Y")
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM metricas_diarias WHERE fecha = ?", (fecha,)
        ).fetchone()
    if row is None:
        return {
            "fecha": fecha,
            "total_iniciadas": 0,
            "total_cerradas": 0,
            "total_enviadas": 0,
            "total_rechazadas": 0,
        }
    return dict(row)
