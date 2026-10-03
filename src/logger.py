"""Módulo centralizado de logs del proceso ETL.

Cada ejecución del proceso genera UN archivo ``logs/log_YYYYMMDD_HHMM.txt``
compartido por todos los módulos (extracción, transformación y carga), con
el formato::

    2026-10-03 10:15:02 | INFO | etl.extraccion | Conexión establecida ...

Uso::

    from src.logger import obtener_logger
    log = obtener_logger("extraccion")
    log.info("mensaje")
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

from src import config

FORMATO = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"
NOMBRE_RAIZ = "etl"

# Manejador de archivo único por proceso (se crea en la primera llamada)
_manejador_archivo = None


def _configurar_raiz(dir_logs: Path) -> logging.Logger:
    """Configura el logger raíz 'etl' con un archivo por ejecución y consola."""
    global _manejador_archivo
    raiz = logging.getLogger(NOMBRE_RAIZ)
    if _manejador_archivo is not None:
        return raiz

    # Se limpian manejadores previos (p. ej. de una configuración anterior)
    for h in list(raiz.handlers):
        raiz.removeHandler(h)
        h.close()

    dir_logs = Path(dir_logs)
    dir_logs.mkdir(parents=True, exist_ok=True)
    ruta = dir_logs / f"log_{datetime.now():%Y%m%d_%H%M}.txt"

    formato = logging.Formatter(FORMATO, datefmt=FORMATO_FECHA)
    _manejador_archivo = logging.FileHandler(ruta, mode="a", encoding="utf-8")
    _manejador_archivo.setFormatter(formato)

    # Consola en UTF-8 para que las tildes se vean bien en Windows
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(formato)

    raiz.setLevel(logging.INFO)
    raiz.addHandler(_manejador_archivo)
    raiz.addHandler(consola)
    raiz.propagate = False
    raiz.info("Archivo de log de la ejecución: %s", ruta)
    return raiz


def obtener_logger(nombre: str, dir_logs: Path | None = None) -> logging.Logger:
    """Devuelve el logger ``etl.<nombre>`` que escribe en el log de la ejecución.

    Args:
        nombre: nombre del componente (``extraccion``, ``transformacion``...).
        dir_logs: carpeta de logs; por defecto ``config.DIR_LOGS``.
    """
    _configurar_raiz(dir_logs or config.DIR_LOGS)  # se lee en cada llamada (permite redirigirlo en pruebas)
    return logging.getLogger(f"{NOMBRE_RAIZ}.{nombre}")


def ruta_log_actual() -> Path | None:
    """Ruta del archivo de log de la ejecución actual (o None si no existe)."""
    return Path(_manejador_archivo.baseFilename) if _manejador_archivo else None
