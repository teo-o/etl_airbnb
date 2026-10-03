"""Configuración común de pytest.

Las pruebas escriben sus logs en una carpeta temporal para no mezclar sus
mensajes con los logs reales del proceso ETL en ``logs/``.
"""
import logging

import pytest

from src import config
from src import logger as modulo_logger


@pytest.fixture(autouse=True, scope="session")
def logs_temporales(tmp_path_factory):
    dir_logs = tmp_path_factory.mktemp("logs")
    original = config.DIR_LOGS
    config.DIR_LOGS = dir_logs
    # Módulos como src.cargar_mongo crean su logger al importarse (durante la
    # recolección de pruebas, antes de este fixture): se cierran esos
    # manejadores y se configura de inmediato el log temporal.
    raiz = logging.getLogger(modulo_logger.NOMBRE_RAIZ)
    for h in list(raiz.handlers):
        raiz.removeHandler(h)
        h.close()
    modulo_logger._manejador_archivo = None
    modulo_logger._configurar_raiz(dir_logs)
    yield dir_logs
    for h in list(logging.getLogger(modulo_logger.NOMBRE_RAIZ).handlers):
        h.close()
    modulo_logger._manejador_archivo = None
    config.DIR_LOGS = original
