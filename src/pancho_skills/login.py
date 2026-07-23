"""Skill: login en Rayen APS.

Wrapper sobre `browser_automation.run_login` que centraliza el log y la
documentación de la acción. Es la única skill que crea un WebDriver nuevo;
las demás lo reciben como parámetro.
"""

from __future__ import annotations

import logging

from selenium.webdriver.remote.webdriver import WebDriver

from src.browser_automation import run_login


def login_rayen(
    credentials: dict[str, str],
    logger: logging.Logger,
    headless: bool = False,
) -> WebDriver:
    """Autentica en Rayen APS y retorna el WebDriver listo para operar.

    Args:
        credentials: dict con `location`, `username`, `password`.
        logger: logger compartido (se recomienda el logger de Mavis/Pilita).
        headless: si True, ejecuta Chrome sin ventana visible.

    Returns:
        WebDriver autenticado en Rayen.

    Raises:
        FileNotFoundError: si falta el archivo de selectores.
        ValueError: si las credenciales están incompletas.
        selenium.common.exceptions.TimeoutException: si el login tarda demasiado.
        selenium.common.exceptions.WebDriverException: si hay un error de UI.
    """
    logger.info("[pancho] Iniciando login en Rayen APS")
    driver = run_login(credentials, logger, headless=headless)
    logger.info("[pancho] Login exitoso — WebDriver listo para operaciones")
    return driver
