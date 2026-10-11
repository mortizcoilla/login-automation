"""Conciliacion de examenes: TODO crudo procesado, SIEMPRE (REQ-102).

La consolidacion inmediata del bot (REQ-061) puede dejar crudos sin
transcribir: motor OCR caido en el momento del envio, foto llegada
ANTES de que existiera la nota (match imposible -> archivada con el
nombre crudo y la fecha de hoy), etc. Esta pasada diaria cierra esas
fugas ANTES de Mortadelo, para que un 'revisar examenes' del bloque
** mortadelo nunca encuentre '(este paciente no tiene examenes
consolidados)' por descuido.

Mecanica:
1. Escanea EXAMENES_CRUDOS_DIR y lee el frontmatter 'archivos_origen'
   de los md consolidados: un crudo que no aparezca en NINGUN md esta
   PENDIENTE (idempotencia exacta por contenido, sin heuristica de
   nombres ni fechas).
2. Resuelve paciente/fecha de cada pendiente desde su nombre de
   archivo + match por tokens contra data/notas_clinicas/ (EL MISMO
   mecanismo del paso 2a). La fecha del match manda sobre la del
   filename (el informe es la fuente de verdad). Sin match -> omitido
   y se deja para la proxima corrida.
3. Por paciente+fecha con pendientes: consolida TODOS sus archivos
   (los del prefijo resuelto + las variantes crudas pendientes) en el
   md canonico, reemplazando el previo si existia (archivo unico).

Nunca bota la cadena diaria: los fallos por paciente se loguean y
siguen; el CLI --pendientes sale 0 salvo error de uso.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.core.nombres import safe_filename
from src.core.rutas import EXAMENES_CRUDOS_DIR, EXAMENES_DIR, NOTAS_DIR
from src.examenes.consolidar import (
    EXTENSIONES_PROCESABLES,
    buscar_fotos_crudas,
    consolidar_examenes,
    transcriptor_por_ambiente,
)
from src.tools.recibir_foto_examen import (
    _indexar_notas_clinicas,
    buscar_match_paciente,
)

# gladys_valdes_castillo_1_07-10-2026.jpg y ..._07-10-2026_v2.jpg
_CRUDO_RE = re.compile(r"^(?P<prefijo>.+)_(?P<n>\d+)_(?P<fecha>\d{2}-\d{2}-\d{4})(?:_v\d+)?$")


def _archivos_procesados(destino_dir: Path) -> set[str]:
    """Nombres de crudo citados en el frontmatter archivos_origen de
    TODOS los md consolidados: la marca de 'ya procesado'."""
    procesados: set[str] = set()
    if not destino_dir.exists():
        return procesados
    for md in destino_dir.glob("exam_*.md"):
        try:
            texto = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not texto.startswith("---"):
            continue
        fin = texto.find("\n---", 3)
        if fin < 0:
            continue
        bloque = texto[3:fin]
        m = re.search(r"^archivos_origen:\s*$(.*?)(?=^\w|\Z)", bloque, re.MULTILINE | re.DOTALL)
        if m:
            procesados.update(re.findall(r'-\s*"([^"]+)"', m.group(1)))
    return procesados


def _nombre_y_fecha_de_crudo(crudo: Path) -> tuple[str, str] | None:
    """(prefijo_paciente, fecha) del nombre de archivo crudo; None si no
    calza con la convencion del paso 2a."""
    m = _CRUDO_RE.match(crudo.stem)
    if not m:
        return None
    return m.group("prefijo"), m.group("fecha")


def conciliar_pendientes(
    crudos_dir: Path = EXAMENES_CRUDOS_DIR,
    destino_dir: Path = EXAMENES_DIR,
    notas_dir: Path = NOTAS_DIR,
    transcriptor=None,
    logger: logging.Logger | None = None,
) -> dict:
    """Consolida todo crudo procesable que no aparezca en ningun md.

    Returns:
        {pendientes, pacientes_consolidados, omitidos, fallidos,
         detalles: [{paciente, fecha, archivos, ok, error}]}
    """
    log = logger or logging.getLogger("conciliar_examenes")
    transcriptor = transcriptor or transcriptor_por_ambiente()

    procesados = _archivos_procesados(destino_dir)
    pendientes = [
        p
        for p in sorted(crudos_dir.iterdir())
        if p.is_file() and p.suffix.lower() in EXTENSIONES_PROCESABLES and p.name not in procesados
    ]
    resumen: dict = {
        "pendientes": len(pendientes),
        "pacientes_consolidados": 0,
        "omitidos": 0,
        "fallidos": 0,
        "detalles": [],
    }
    if not pendientes:
        log.info("[conciliar] sin examenes pendientes")
        return resumen
    log.info("[conciliar] %d crudo(s) pendiente(s) de consolidacion", len(pendientes))

    indice_notas = _indexar_notas_clinicas(notas_dir)

    # Resolver cada pendiente -> (paciente, fecha) del match.
    grupos: dict[tuple[str, str], list[Path]] = {}
    for crudo in pendientes:
        parseo = _nombre_y_fecha_de_crudo(crudo)
        if parseo is None:
            resumen["omitidos"] += 1
            log.warning("[conciliar] %s: nombre no calza con la convencion 2a; omitido", crudo.name)
            continue
        prefijo, _fecha_archivo = parseo
        match = buscar_match_paciente(prefijo.replace("_", " "), indice_notas)
        if match is None:
            resumen["omitidos"] += 1
            log.warning(
                "[conciliar] %s: sin match en notas_clinicas (prefijo %r); omitido",
                crudo.name,
                prefijo,
            )
            continue
        grupos.setdefault((match["paciente"], match["fecha_atencion"]), []).append(crudo)

    for (paciente, fecha), variantes in grupos.items():
        detalle: dict = {"paciente": paciente, "fecha": fecha, "archivos": [], "ok": False, "error": ""}
        try:
            # Los del prefijo resuelto entran al merge aunque ya esten en
            # un md previo: el archivo unico se RECONSOLIDA completo.
            archivos = list(buscar_fotos_crudas(paciente, fecha, crudos_dir))
            archivos += [p for p in variantes if p.name not in {a.name for a in archivos}]
            archivos.sort(key=lambda p: p.name)
            detalle["archivos"] = sorted(p.name for p in archivos)

            res = consolidar_examenes(
                paciente=paciente,
                fecha=fecha,
                crudos_dir=crudos_dir,
                destino_dir=destino_dir,
                transcriptor=transcriptor,
                fotos=archivos,
            )
            if not res.get("ok"):
                detalle["error"] = res.get("error", "sin detalle")
                resumen["fallidos"] += 1
                log.error("[conciliar] %s (%s): FALLO: %s", paciente, fecha, detalle["error"])
            else:
                # Archivo unico: dejar SOLO el md canonico de esta fecha.
                safe = safe_filename(paciente)
                canonico = destino_dir / f"exam_{safe}_{fecha}.md"
                nuevo = Path(str(res["path"]))
                for previo in destino_dir.glob(f"exam_{safe}_{fecha}*.md"):
                    if previo != nuevo:
                        previo.unlink(missing_ok=True)
                if nuevo != canonico:
                    nuevo.replace(canonico)
                detalle["ok"] = True
                resumen["pacientes_consolidados"] += 1
                log.info(
                    "[conciliar] %s (%s): %d archivo(s) -> %s",
                    paciente,
                    fecha,
                    len(archivos),
                    canonico.name,
                )
        except Exception as e:  # noqa: BLE001 - un paciente no bota la corrida
            detalle["error"] = f"error inesperado: {e}"
            resumen["fallidos"] += 1
            log.exception("[conciliar] %s (%s): excepcion", paciente, fecha)
        resumen["detalles"].append(detalle)

    log.info(
        "[conciliar] fin: %d pendiente(s), %d paciente(s) consolidado(s), "
        "%d omitido(s), %d fallido(s)",
        resumen["pendientes"],
        resumen["pacientes_consolidados"],
        resumen["omitidos"],
        resumen["fallidos"],
    )
    return resumen
