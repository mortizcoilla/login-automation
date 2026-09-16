"""Recibir fotos de examenes clinicos desde Telegram u otras fuentes.

Cuando Yadira manda una foto a Pilita por Telegram (o cualquier otra
fuente), este script la guarda en `notas_clinicas/_adjuntos/` con un
nombre que el matcher de `analizar_adjuntos_imagen()` (en
`generar_ficha_con_llm.py`) ya sabe encontrar.

Convencion de nombre (alineada con el matcher existente):
    <paciente_corto>_<fecha_dd_mm_yyyy>_<tipo>_<timestamp>.jpg

Donde:
- paciente_corto = primer_nombre + primer_apellido, lowercase, sin tildes
- fecha_dd_mm_yyyy = fecha de la atencion (formato dd-mm-yyyy)
- tipo = audiometria | ecg | laboratorio | imagen | radiografia |
         receta | certificado | otro (default: "examen")
- timestamp = HHMMSS para evitar colisiones si hay varias fotos el mismo dia

El matcher en `analizar_adjuntos_imagen()` busca en el nombre del archivo:
- la fecha dd-mm-yyyy, O
- el nombre del paciente normalizado, O
- cualquier parte del nombre (>= 4 chars)

Por eso esta convencion es robusta: matchea por paciente, por fecha, o
por ambos. Es importante: NO usar guiones altos en el nombre del
paciente, ni el segundo apellido (eso lo confunde con la busqueda por
"primer_apellido").

Reglas duras:
- NO sobrescribe archivos existentes (agrega sufijo _v2, _v3, ...).
- NO acepta inputs que no sean archivos de imagen validos.
- SIEMPRE valida que el paciente tiene al menos nombre y apellido.
- NUNCA inventa datos. Si falta info, retorna error explicito.

Uso tipico (desde Pilita o cualquier gato):
    # Foto ya descargada a disco
    python -m src.tools.recibir_foto_examen \\
        --input "C:/path/to/photo.jpg" \\
        --paciente "Cecilia Reyes" \\
        --fecha 10-07-2026 \\
        --tipo audiometria

    # Sin tipo (default: examen)
    python -m src.tools.recibir_foto_examen \\
        --input photo.jpg \\
        --paciente "Cecilia Reyes"

Salida (stdout, JSON para que sea facil de parsear por el agente):
    {"ok": true, "path": "C:/.../cecilia_reyes_10-07-2026_audiometria_163045.jpg", ...}
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional


# Repo root (este archivo vive en src/tools/, asi que subimos 2 niveles)
ROOT = Path(__file__).resolve().parents[2]

# Destino por convencion del proyecto
DESTINO_DIR = ROOT / "data" / "notas_clinicas" / "_adjuntos"

# Extensiones de imagen aceptadas (mismas que IMAGE_EXTENSIONS en generar_ficha_con_llm.py)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}

# Tipos validos (cualquier otro cae en "otro")
TIPOS_VALIDOS = {
    "audiometria", "ecg", "electrocardiograma",
    "laboratorio", "lab", "sangre",
    "imagen", "radiografia", "rx", "ecografia", "eco",
    "receta", "certificado", "ic", "interconsulta",
    "fondo_ojo", "dermatologia", "lesion", "herida",
    "otro", "examen",  # "examen" es el default generico
}


def normalizar_texto(texto: str) -> str:
    """Quita tildes, pasa a minusculas, colapsa espacios y guiones.

    Usado para construir el nombre de archivo y para matching.
    """
    # NFD separa la letra base del acento, luego filtramos las marcas.
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[\s_]+", " ", sin_tildes).strip().lower()


def paciente_corto(nombre_completo: str) -> str:
    """Devuelve 'primer_nombre primer_apellido' normalizado.

    Sin tildes, lowercase, sin segundo apellido (eso ayuda al matcher
    porque el archivo generado es mas corto y matchea mejor).

    Raises:
        ValueError: si el nombre no tiene al menos 2 palabras.
    """
    partes = nombre_completo.strip().split()
    if len(partes) < 2:
        raise ValueError(
            f"Nombre '{nombre_completo}' debe tener al menos nombre y apellido. "
            f"Ejemplo: 'Cecilia Reyes'"
        )
    nombre = partes[0]
    apellido = partes[-1] if len(partes) > 1 else partes[0]
    return f"{nombre} {apellido}"


def nombre_archivo_valido(nombre: str) -> str:
    """Limpia un string para usarlo como nombre de archivo (sin espacios
    raros, sin caracteres especiales que rompan el matcher).
    """
    # Quitar acentos, lowercase, reemplazar espacios por underscore
    norm = normalizar_texto(nombre)
    # Reemplazar cualquier cosa que no sea alfanumerico o guion bajo
    limpio = re.sub(r"[^a-z0-9_]+", "_", norm)
    # Colapsar guiones bajos multiples
    limpio = re.sub(r"_+", "_", limpio).strip("_")
    return limpio


def validar_fecha(fecha: str) -> str:
    """Valida que la fecha este en formato dd-mm-yyyy. Retorna igual si OK.

    Raises:
        ValueError: si no matchea el formato o no es fecha real.
    """
    if not re.match(r"^\d{2}-\d{2}-\d{4}$", fecha):
        raise ValueError(
            f"Fecha '{fecha}' debe estar en formato dd-mm-yyyy "
            f"(ejemplo: 10-07-2026)"
        )
    try:
        datetime.strptime(fecha, "%d-%m-%Y")
    except ValueError as e:
        raise ValueError(f"Fecha '{fecha}' no es valida: {e}")
    return fecha


def normalizar_tipo(tipo: Optional[str]) -> str:
    """Normaliza el tipo de examen a un valor canonico."""
    if not tipo:
        return "examen"
    t = normalizar_texto(tipo)
    # Mapear sinonimos al canonico mas corto
    mapa = {
        "electrocardiograma": "ecg",
        "lab": "laboratorio",
        "sangre": "laboratorio",
        "rx": "radiografia",
        "eco": "ecografia",
        "ic": "interconsulta",
        "lesion": "dermatologia",
        "herida": "dermatologia",
        "certificado": "certificado",
        "receta": "receta",
        "audiometria": "audiometria",
        "ecg": "ecg",
        "laboratorio": "laboratorio",
        "imagen": "imagen",
        "radiografia": "radiografia",
        "ecografia": "ecografia",
        "interconsulta": "interconsulta",
        "fondo ojo": "fondo_ojo",
        "dermatologia": "dermatologia",
        "otro": "otro",
        "examen": "examen",
    }
    return mapa.get(t, "otro" if t not in {"examen", "audiometria", "ecg",
                                            "laboratorio", "imagen",
                                            "radiografia", "ecografia",
                                            "interconsulta", "fondo_ojo",
                                            "dermatologia", "certificado",
                                            "receta"} else t)


def construir_nombre_destino(
    nombre_paciente: str,
    fecha_dd_mm_yyyy: str,
    tipo: str,
    timestamp: Optional[str] = None,
) -> str:
    """Construye el nombre de archivo destino segun la convencion.

    Formato: <paciente>_<fecha>_<tipo>[_<timestamp>].<ext>
    """
    paciente = nombre_archivo_valido(paciente_corto(nombre_paciente))
    tipo_norm = nombre_archivo_valido(tipo)
    if timestamp is None:
        timestamp = datetime.now().strftime("%H%M%S")
    else:
        timestamp = re.sub(r"[^0-9]", "", timestamp)
    return f"{paciente}_{fecha_dd_mm_yyyy}_{tipo_norm}_{timestamp}"


def resolver_path_sin_colision(destino_dir: Path, base_nombre: str, extension: str) -> Path:
    """Retorna un path que no exista, agregando _v2, _v3, ... si hay colision.

    NO sobrescribe archivos existentes (regla dura).
    """
    candidato = destino_dir / f"{base_nombre}{extension}"
    if not candidato.exists():
        return candidato
    n = 2
    while True:
        candidato = destino_dir / f"{base_nombre}_v{n}{extension}"
        if not candidato.exists():
            return candidato
        n += 1
        if n > 999:
            raise RuntimeError(f"Demasiadas colisiones para {base_nombre} en {destino_dir}")


def recibir_foto(
    input_path: Path,
    nombre_paciente: str,
    fecha_atencion: str,
    tipo: Optional[str] = None,
    destino_dir: Path = DESTINO_DIR,
    timestamp: Optional[str] = None,
) -> dict:
    """Guarda una foto de examen en destino_dir con el nombre convencional.

    Args:
        input_path: ruta al archivo de imagen origen (descargado de Telegram
            o de cualquier otra fuente).
        nombre_paciente: nombre completo del paciente (ej: "Cecilia Reyes").
        fecha_atencion: fecha de la atencion en formato dd-mm-yyyy.
        tipo: tipo de examen (audiometria, ecg, laboratorio, etc.).
            Si es None o vacio, usa "examen".
        destino_dir: directorio destino (default: notas_clinicas/_adjuntos/).

    Returns:
        dict con:
          - ok: bool
          - path: ruta absoluta del archivo guardado (si ok=True)
          - nombre: nombre del archivo guardado
          - paciente: nombre del paciente normalizado
          - fecha: fecha validada
          - tipo: tipo normalizado
          - tamano_kb: tamano del archivo guardado
          - error: mensaje de error (si ok=False)

    Raises:
        No raise. Todos los errores van al dict de retorno.
    """
    resultado = {
        "ok": False,
        "path": "",
        "nombre": "",
        "paciente": "",
        "fecha": "",
        "tipo": "",
        "tamano_kb": 0,
        "error": "",
    }

    # 1. Validar input existe y es imagen
    if not input_path.exists():
        resultado["error"] = f"Archivo no existe: {input_path}"
        return resultado
    if not input_path.is_file():
        resultado["error"] = f"No es un archivo: {input_path}"
        return resultado

    extension = input_path.suffix.lower()
    if extension not in IMAGE_EXTENSIONS:
        resultado["error"] = (
            f"Extension '{extension}' no es una imagen valida. "
            f"Aceptadas: {sorted(IMAGE_EXTENSIONS)}"
        )
        return resultado

    # 2. Validar paciente
    try:
        paciente = paciente_corto(nombre_paciente)
    except ValueError as e:
        resultado["error"] = str(e)
        return resultado

    # 3. Validar fecha
    try:
        fecha = validar_fecha(fecha_atencion)
    except ValueError as e:
        resultado["error"] = str(e)
        return resultado

    # 4. Normalizar tipo
    tipo_norm = normalizar_tipo(tipo)

    # 5. Construir nombre y resolver path sin colision
    try:
        destino_dir.mkdir(parents=True, exist_ok=True)
        base = construir_nombre_destino(paciente, fecha, tipo_norm, timestamp=timestamp)
        destino = resolver_path_sin_colision(destino_dir, base, extension)
    except Exception as e:  # noqa: BLE001
        resultado["error"] = f"Error construyendo path destino: {e}"
        return resultado

    # 6. Copiar
    try:
        shutil.copy2(input_path, destino)
    except Exception as e:  # noqa: BLE001
        resultado["error"] = f"Error copiando a {destino}: {e}"
        return resultado

    # 7. Exito
    resultado.update({
        "ok": True,
        "path": str(destino),
        "nombre": destino.name,
        "paciente": paciente,
        "fecha": fecha,
        "tipo": tipo_norm,
        "tamano_kb": destino.stat().st_size // 1024,
    })
    return resultado


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Recibe una foto de examen y la guarda en _adjuntos/ "
                    "con el nombre que mortadelo_batch sabe encontrar.",
    )
    p.add_argument(
        "--input", required=True,
        help="Ruta al archivo de imagen origen (descargado de Telegram, "
             "Rayen, o donde sea).",
    )
    p.add_argument(
        "--paciente", required=True,
        help="Nombre completo del paciente (ej: 'Cecilia Reyes'). "
             "Debe tener al menos nombre y apellido.",
    )
    p.add_argument(
        "--fecha", required=True,
        help="Fecha de la atencion en formato dd-mm-yyyy (ej: 10-07-2026).",
    )
    p.add_argument(
        "--tipo", default=None,
        help="Tipo de examen: audiometria, ecg, laboratorio, imagen, "
             "radiografia, ecografia, receta, certificado, interconsulta, "
             "fondo_ojo, dermatologia, otro. Default: examen.",
    )
    p.add_argument(
        "--destino", default=None,
        help=f"Directorio destino (default: {DESTINO_DIR}).",
    )
    p.add_argument(
        "--timestamp", default=None,
        help="Timestamp explicito (HHMMSS) para el nombre. Default: hora actual. "
             "Util para tests deterministas o para nombrar fotos manualmente.",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    destino = Path(args.destino) if args.destino else DESTINO_DIR
    resultado = recibir_foto(
        input_path=Path(args.input),
        nombre_paciente=args.paciente,
        fecha_atencion=args.fecha,
        tipo=args.tipo,
        destino_dir=destino,
        timestamp=args.timestamp,
    )
    # Salida en JSON para que sea facil de parsear por Pilita u otro agente.
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
