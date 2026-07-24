"""Live check: cuántas fichas 'Iniciado' tiene Yadira HOY en Rayen.

Hace login en Rayen, navega a Pacientes citados, filtra por la fecha
de hoy y cuenta las fichas en estado 'Iniciado'. Es el complemento
vivo del análisis histórico: responde "¿cuántas tengo hoy?".

Privacidad: este script solo emite IDs, hora, tipo de atención,
adjunto y razón resumida. NUNCA imprime RUT, nombre ni observación.
Las credenciales las carga desde env vars (USERS_<ID>_*) o
config/users.json (no se exponen en consola).

Output:
- Consola: igual que antes, en vivo
- Archivo: data/analysis/fichas_hoy_<dd-mm-yyyy>.txt con todo el
  output. Si el script falla, queda registro para diagnóstico.
"""
from __future__ import annotations

import io
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from src.constants import DATE_FORMAT
from src.credentials import list_known_users, load_credentials
from src.logger_config import setup_logger
from src.pancho_skills import listar_iniciados, login_rayen

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUT_DIR = BASE_DIR / "data" / "analysis"


def _safe_quit(driver, logger) -> None:
    """Cierra el browser. Si browser_automation no está disponible, ignora."""
    try:
        from src.browser_automation import safe_quit

        safe_quit(driver, logger)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No se pudo cerrar el browser limpiamente: {e}")


def _resolver_usuario() -> str | None:
    """Detecta un usuario disponible sin prompt.

    Orden de prioridad:
    1. Argumento CLI: `python -m src.analysis.fichas_hoy <user_id>`
    2. Si hay un solo usuario configurado, usarlo
    3. Si hay varios, usar el primero e informar

    NO usa `prompt_user_id()` — el flujo automatizado toma las
    credenciales de env vars (USERS_<ID>_*) o de config/users.json.
    """
    cli_user = sys.argv[1] if len(sys.argv) > 1 else None
    users = list_known_users()
    if cli_user:
        if cli_user not in users:
            print(
                f"ERROR: '{cli_user}' no está configurado. Disponibles: {users}",
                file=sys.stderr,
            )
            return None
        return cli_user
    if not users:
        print(
            "ERROR: no hay usuarios configurados. Define USERS_<ID>_LOCATION/"
            "USERNAME/PASSWORD en .env o en variables de entorno.",
            file=sys.stderr,
        )
        return None
    if len(users) > 1:
        print(
            f"Hay {len(users)} usuarios configurados: {users}. "
            f"Usando '{users[0]}'. Para elegir otro, pasá el user_id como argumento.",
            file=sys.stderr,
        )
    return users[0]


class _TeeStdout:
    """Wrapper de stdout que duplica cada write a un buffer en memoria.

    Permite seguir viendo el output en consola (en vivo) y, al final,
    guardar el contenido completo a un archivo.
    """

    def __init__(self, original):
        self._original = original
        self._buffer = io.StringIO()

    def write(self, s: str) -> int:
        self._original.write(s)
        return self._buffer.write(s)

    def flush(self) -> None:
        self._original.flush()

    def get_output(self) -> str:
        return self._buffer.getvalue()


def _guardar_output(capturado: str, hoy: str) -> Path | None:
    """Guarda el output capturado a un archivo. Retorna la ruta o None si falla."""
    if not capturado.strip():
        return None
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUT_DIR / f"fichas_hoy_{hoy}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(capturado)
        return path
    except OSError as e:
        print(f"WARN: no se pudo guardar output en archivo: {e}", file=sys.stderr)
        return None


def main() -> int:
    logger = setup_logger()
    tee = _TeeStdout(sys.stdout)
    sys.stdout = tee

    try:
        return _run(logger)
    finally:
        sys.stdout = tee._original
        # Guardar el output a archivo. Necesitamos la fecha; la sacamos
        # del output (línea de resultado) o usamos hoy.
        hoy = datetime.now().strftime(DATE_FORMAT)
        out_path = _guardar_output(tee.get_output(), hoy)
        if out_path is not None:
            # Imprimir a stdout ya restaurado
            print(f"\n[output completo guardado en: {out_path.relative_to(BASE_DIR)}]")


def _run(logger: logging.Logger) -> int:
    print("=" * 60)
    print("FICHAS ABIERTAS HOY — Live check")
    print("=" * 60)

    user_id = _resolver_usuario()
    if user_id is None:
        return 1
    print(f"Autenticando como '{user_id}' (credenciales desde env o users.json)...")

    try:
        credentials = load_credentials(user_id)
    except (KeyError, ValueError) as e:
        print(f"ERROR cargando credenciales: {e}", file=sys.stderr)
        return 1

    driver = None
    pacientes: list = []
    hoy = datetime.now().strftime(DATE_FORMAT)
    try:
        driver = login_rayen(credentials, logger, headless=False)
        print(f"\nListando fichas 'Iniciado' para {hoy}...")

        pacientes = listar_iniciados(driver, logger, fecha=hoy)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error durante el live check: {e}")
        return 1
    finally:
        try:
            input("\nPresione Enter para cerrar el browser...")
        except EOFError:
            pass
        _safe_quit(driver, logger)

    if not pacientes:
        print()
        print("=" * 60)
        print(f"RESULTADO: 0 fichas 'Iniciado' en {hoy}")
        print("¡Yadira está al día! (o no había atención este día)")
        print("=" * 60)
        return 0

    tipos: Counter = Counter()
    adjuntos: Counter = Counter()
    horas: Counter = Counter()
    for p in pacientes:
        tipos[p.tipo_atencion] += 1
        if p.adjunto:
            adjuntos[p.adjunto] += 1
        hora_key = p.hora.split("-")[0].strip() if p.hora else "?"
        horas[hora_key] += 1

    print()
    print("=" * 60)
    print(f"RESULTADO: {len(pacientes)} fichas 'Iniciado' en {hoy}")
    print("=" * 60)

    if tipos:
        print("\nDistribución por tipo de atención:")
        for tipo, cant in tipos.most_common():
            pct = 100 * cant / len(pacientes)
            print(f"  {tipo:<40s} {cant:3d}  ({pct:5.1f}%)")

    if adjuntos:
        print("\nDistribución por adjunto (quién las creó):")
        for adj, cant in adjuntos.most_common():
            print(f"  {adj:<40s} {cant:3d}")

    if horas:
        print("\nDistribución por hora de la cita:")
        for hora, cant in sorted(horas.items()):
            print(f"  {hora}  {cant:3d}")

    print("\nDetalle (sin nombres — solo hora, tipo, adjunto):")
    print(f"  {'Hora':<8} {'Tipo':<35} {'Adjunto':<20}")
    print("  " + "-" * 63)
    for p in pacientes:
        print(
            f"  {p.hora[:7]:<8} {p.tipo_atencion[:33]:<35} {p.adjunto[:18]:<20}"
        )
    print()
    print("(Nota: los IDs de cita y los nombres NO se imprimen por")
    print(" privacidad. Si para una sesión de cierre necesitás los")
    print(" IDs, lo hacemos por otro canal.)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
