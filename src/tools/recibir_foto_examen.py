"""Recibir fotos de examenes clinicos desde Telegram u otras fuentes.

Cuando Yadira manda una foto a Pilita por Telegram (o cualquier otra
fuente), este script:

1. Guarda la imagen cruda en `data/adjuntos/` como respaldo local.
2. La envia al LLM vision (gemini-2.5-pro) para OCR / digitalizacion.
3. Guarda la transcripcion resultante en `data/examenes/` como .md
   con la misma nomenclatura que `crear_notas_clinicas` usa para
   los nombres de pacientes.

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

Naming del .md digitalizado (data/examenes/):
    <paciente>_<fecha>_<tipo>.md
Donde <paciente> usa `_safe_filename` (mismo regex que
`crear_notas_clinicas._safe_filename`) para preservar mayusculas y
tildes del nombre original. Esto difiere del inbox (lowercase, sin
tildes) porque el .md es metadata, no un archivo que matchea el matcher.

Reglas duras:
- NO sobrescribe archivos existentes (agrega sufijo _v2, _v3, ...).
- NO acepta inputs que no sean archivos de imagen validos.
- SIEMPRE valida que el paciente tiene al menos nombre y apellido.
- NUNCA inventa datos. Si falta info, retorna error explicito.
- Si el OCR falla, el archivo en data/adjuntos/ YA ESTA guardado
  (es el respaldo). El script retorna ok=True con ocr_ok=False y
  el error en ocr_error. Yadira puede reintentar el OCR despues.

Uso tipico (desde Pilita o cualquier gato):
    # Foto ya descargada a disco (respaldo + OCR automatico)
    python -m src.tools.recibir_foto_examen \\
        --input "C:/path/to/photo.jpg" \\
        --paciente "Cecilia Reyes" \\
        --fecha 10-07-2026 \\
        --tipo audiometria

    # Sin tipo (default: examen)
    python -m src.tools.recibir_foto_examen \\
        --input photo.jpg \\
        --paciente "Cecilia Reyes"

    # Solo respaldo (sin OCR, util para tests o si el LLM no responde)
    python -m src.tools.recibir_foto_examen \\
        --input photo.jpg \\
        --paciente "Cecilia Reyes" \\
        --no-ocr

Salida (stdout, JSON para que sea facil de parsear por el agente):
    {
      "ok": true,
      "path": "C:/.../adjuntos/cecilia_reyes_10-07-2026_audiometria_163045.jpg",
      "nombre": "cecilia_reyes_10-07-2026_audiometria_163045.jpg",
      "paciente": "cecilia reyes",
      "fecha": "10-07-2026",
      "tipo": "audiometria",
      "tamano_kb": 234,
      "ocr_ok": true,
      "examen_path": "C:/.../examenes/Cecilia_Reyes_10-07-2026_audiometria.md",
      "ocr_modelo": "google/gemini-2.5-pro",
      "ocr_error": ""
    }
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

# Inbox donde se guardan las fotos crudas (respaldo local).
# Sesion 2026-09-16: se movio desde data/notas_clinicas/_adjuntos/.
DESTINO_DIR = ROOT / "data" / "adjuntos"

# Donde se guardan los examenes digitalizados (.md con la transcripcion
# del OCR). Misma convencion de nombre de paciente que crear_notas_clinicas.
EXAMENES_DIR = ROOT / "data" / "examenes"

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


def _safe_filename(s: str) -> str:
    """Convierte un nombre a filename seguro. Misma regex que
    `crear_notas_clinicas._safe_filename` para que la nomenclatura del
    .md digitalizado sea identica a la de las notas clinicas.

    Mantener sincronizado si crear_notas_clinicas._safe_filename cambia.
    """
    s = re.sub(r"[^\w\s\-]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s.strip())
    return s


def construir_nombre_examen_md(
    nombre_paciente: str,
    fecha_dd_mm_yyyy: str,
    tipo: str,
) -> str:
    """Nombre del .md digitalizado en data/examenes/.

    Formato: <safe_paciente>_<fecha>_<tipo>.md
    A diferencia del inbox (lowercase, sin tildes), aqui preservamos
    mayusculas y tildes porque es metadata, no un archivo para matcher.
    """
    paciente = _safe_filename(nombre_paciente)
    tipo_norm = nombre_archivo_valido(tipo)
    return f"{paciente}_{fecha_dd_mm_yyyy}_{tipo_norm}.md"


def _renderizar_examen_md(
    nombre_paciente: str,
    fecha_atencion: str,
    tipo: str,
    archivo_origen: str,
    transcripcion: str,
    modelo: str,
) -> str:
    """Renderiza el .md del examen digitalizado (frontmatter YAML + headers).

    Mismo formato canonico (frontmatter + ## headers) que
    crear_notas_clinicas y data/manuales_md/.
    """
    timestamp_iso = datetime.now().isoformat(timespec="seconds")
    md = [
        "---",
        f'paciente: "{nombre_paciente}"',
        f'fecha_atencion: "{fecha_atencion}"',
        f'tipo: "{tipo}"',
        f'archivo_origen: "{archivo_origen}"',
        f'modelo_ocr: "{modelo}"',
        f'fecha_digitalizacion: "{timestamp_iso}"',
        "fuente: \"OCR automatico via LLM vision (Yadira debe validar)\"",
        "---",
        "",
        f"# Examen - {nombre_paciente}",
        "",
        "## Metadatos",
        f"- **Tipo:** {tipo}",
        f"- **Fecha atencion:** {fecha_atencion}",
        f"- **Archivo origen:** `{archivo_origen}`",
        f"- **Modelo OCR:** `{modelo}`",
        f"- **Fecha digitalizacion:** {timestamp_iso}",
        "",
        "## Transcripcion",
        "",
        transcripcion.strip(),
        "",
        "## Notas",
        "- Transcripcion automatica con LLM vision (gemini-2.5-pro).",
        "- Yadira debe validar contra la imagen original antes de cerrar la ficha.",
        "",
    ]
    return "\n".join(md)


def procesar_examen_con_ocr(
    img_path: Path,
    nombre_paciente: str,
    fecha_atencion: str,
    tipo: str,
    examenes_dir: Path = EXAMENES_DIR,
) -> dict:
    """Envia la imagen al LLM vision y guarda la transcripcion en data/examenes/.

    Usa `invocar_con_fallback(tier="vision", ...)` de generar_ficha_con_llm.
    Import lazy para no arrastrar selenium si el script se llama solo
    para el respaldo (--no-ocr).

    Returns dict con:
      - ok: bool (True si la transcripcion se guardo)
      - path: ruta al .md generado
      - transcripcion: texto extraido por el LLM
      - modelo: modelo usado
      - error: mensaje de error (si ok=False)
    """
    resultado = {
        "ok": False,
        "path": "",
        "transcripcion": "",
        "modelo": "",
        "error": "",
    }

    # Lazy import: solo si se invoca OCR (no en --no-ocr)
    try:
        from src.tools.generar_ficha_con_llm import invocar_con_fallback
    except ImportError as e:
        resultado["error"] = f"No se pudo importar invocar_con_fallback: {e}"
        return resultado

    # Prompt para el OCR. Inspirado en analizar_adjuntos_imagen() pero
    # con foco en examen especifico (sabemos el tipo de antemano).
    prompt = (
        f"Este es un examen clinico de tipo '{tipo}' del paciente "
        f"{nombre_paciente} (atencion del {fecha_atencion}).\n\n"
        f"Transcribe TODO el contenido clinico visible:\n"
        f"- Valores numericos con sus unidades y rangos de referencia\n"
        f"- Conclusiones o interpretaciones del examinador\n"
        f"- Fecha del examen si esta visible\n"
        f"- Nombre del profesional que firma o interpreta\n"
        f"- Cualquier texto visible (etiquetas, membrete, observaciones)\n\n"
        f"Si la imagen es ruido, ilegible o no es un documento clinico, "
        f"indicalo explicitamente con '[NO ES UN DOCUMENTO CLINICO]'.\n"
        f"NO inventes datos. Si algo no se ve, marcalo como 'no visible'.\n"
        f"NO hagas diagnosticos. Solo describe lo que ves.\n\n"
        f"Formato de salida: texto plano, sin markdown, organizado por "
        f"secciones con MAYUSCULAS como titulo. NO agregues meta-comentarios, "
        f"NO digas 'como IA...', NO agregues despedidas. Solo la transcripcion."
    )

    try:
        texto, modelo = invocar_con_fallback(
            tier="vision",
            prompt=prompt,
            agent="mortadelo",  # no se usa realmente para vision
            timeout=300,
            archivos=[img_path],
        )
    except Exception as e:  # noqa: BLE001
        resultado["error"] = f"Error invocando vision LLM: {type(e).__name__}: {e}"
        return resultado

    if not texto or len(texto.strip()) < 10:
        resultado["error"] = "Vision LLM devolvio vacio o muy corto (<10 chars)"
        return resultado

    # Guardar como markdown en data/examenes/
    try:
        examenes_dir.mkdir(parents=True, exist_ok=True)
        nombre_md = construir_nombre_examen_md(nombre_paciente, fecha_atencion, tipo)
        out_path = examenes_dir / nombre_md
        # Resolver colision (_v2, _v3, ...) igual que en el inbox
        out_path = resolver_path_sin_colision(
            examenes_dir, out_path.stem, ".md"
        )
        contenido = _renderizar_examen_md(
            nombre_paciente, fecha_atencion, tipo,
            archivo_origen=img_path.name,
            transcripcion=texto,
            modelo=modelo,
        )
        out_path.write_text(contenido, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        resultado["error"] = f"Error guardando .md en {examenes_dir}: {e}"
        return resultado

    resultado.update({
        "ok": True,
        "path": str(out_path),
        "transcripcion": texto.strip(),
        "modelo": modelo,
    })
    return resultado


def recibir_foto(
    input_path: Path,
    nombre_paciente: str,
    fecha_atencion: str,
    tipo: Optional[str] = None,
    destino_dir: Path = DESTINO_DIR,
    timestamp: Optional[str] = None,
    no_ocr: bool = False,
) -> dict:
    """Guarda una foto de examen en destino_dir con el nombre convencional.

    Si no_ocr es False (default), despues de guardar la foto la envia al
    LLM vision para OCR y guarda la transcripcion en data/examenes/.
    Si no_ocr es True, solo guarda la foto y omite el OCR (util para
    tests o cuando el LLM no responde).

    Args:
        input_path: ruta al archivo de imagen origen (descargado de Telegram
            o de cualquier otra fuente).
        nombre_paciente: nombre completo del paciente (ej: "Cecilia Reyes").
        fecha_atencion: fecha de la atencion en formato dd-mm-yyyy.
        tipo: tipo de examen (audiometria, ecg, laboratorio, etc.).
            Si es None o vacio, usa "examen".
        destino_dir: directorio destino (default: data/adjuntos/).
        no_ocr: si True, NO invoca el LLM vision (solo respaldo raw).

    Returns:
        dict con:
          - ok: bool (True si la foto se guardo OK)
          - path: ruta absoluta del archivo guardado (si ok=True)
          - nombre: nombre del archivo guardado
          - paciente: nombre del paciente normalizado
          - fecha: fecha validada
          - tipo: tipo normalizado
          - tamano_kb: tamano del archivo guardado
          - ocr_ok: bool (True si el OCR y el .md en data/examenes/ se
                    generaron OK; False si --no-ocr o si el OCR fallo)
          - examen_path: ruta al .md digitalizado (si ocr_ok=True)
          - ocr_modelo: modelo vision usado (si ocr_ok=True)
          - ocr_error: mensaje de error del OCR (si ocr_ok=False y no_ocr=False)
          - ocr_skipped: bool (True si --no-ocr se uso explicitamente)
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
        "ocr_ok": False,
        "examen_path": "",
        "ocr_modelo": "",
        "ocr_error": "",
        "ocr_skipped": False,
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

    # 6.5. OCR con LLM vision (a menos que --no-ocr)
    # El respaldo raw YA esta guardado en este punto. Si el OCR falla,
    # el archivo en data/adjuntos/ sigue existiendo (es el respaldo
    # local). El script retorna ok=True con ocr_ok=False y el error
    # en ocr_error para que Yadira pueda diagnosticar.
    if no_ocr:
        resultado["ocr_skipped"] = True
    else:
        ocr = procesar_examen_con_ocr(
            img_path=destino,
            nombre_paciente=nombre_paciente,
            fecha_atencion=fecha,
            tipo=tipo_norm,
        )
        resultado.update({
            "ocr_ok": ocr["ok"],
            "examen_path": ocr["path"],
            "ocr_modelo": ocr["modelo"],
            "ocr_error": ocr["error"],
        })

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
        description="Recibe una foto de examen: la guarda en data/adjuntos/ "
                    "como respaldo raw y la envia al LLM vision para OCR "
                    "(la transcripcion se guarda en data/examenes/<paciente>_<fecha>_<tipo>.md).",
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
        help=f"Directorio destino del respaldo raw (default: {DESTINO_DIR}).",
    )
    p.add_argument(
        "--timestamp", default=None,
        help="Timestamp explicito (HHMMSS) para el nombre. Default: hora actual. "
             "Util para tests deterministas o para nombrar fotos manualmente.",
    )
    p.add_argument(
        "--no-ocr", action="store_true",
        help="Saltar el paso de OCR. Solo guarda la foto como respaldo raw "
             "en data/adjuntos/. Util para tests o cuando el LLM vision "
             "no responde. El .md digitalizado NO se genera.",
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
        no_ocr=args.no_ocr,
    )
    # Salida en JSON para que sea facil de parsear por Pilita u otro agente.
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
