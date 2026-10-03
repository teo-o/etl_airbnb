"""Carga inicial de los datasets de Airbnb Bogotá en MongoDB local.

Paso previo al ETL exigido por el taller: crea la base ``airbnb_bogota`` e
importa ``listings.csv.gz``, ``reviews.csv.gz`` y ``calendar.csv.gz`` como las
colecciones ``Listings``, ``Reviews`` y ``Calendar``. Luego valida que la
cantidad de documentos coincida con las filas de cada archivo.

Decisiones:
* Se imita el comportamiento de ``mongoimport --type csv``: los números se
  guardan como números y el resto como texto (``price`` queda como
  ``"$284,294.01"``), de modo que la limpieza ocurre en la fase de
  transformación del ETL y no aquí.
* Los campos vacíos (NaN) se omiten del documento, como hace MongoDB con
  datos semiestructurados.
* La carga es idempotente: cada colección se elimina y se vuelve a crear.

Uso::

    python -m src.cargar_mongo
"""
import logging
import math
import time

import pandas as pd
from pymongo import ASCENDING, MongoClient

from src import config
from src.logger import obtener_logger

# El logger se configura en main(): importar el módulo no debe crear archivos de log.
log = logging.getLogger("etl.cargar_mongo")

TAMANO_LOTE = 50_000

# Índices útiles para las consultas de extracción y los cruces posteriores
INDICES = {
    "listings": ["id"],
    "reviews": ["listing_id", "date"],
    "calendar": ["listing_id", "date"],
}


def _a_documentos(lote: pd.DataFrame) -> list[dict]:
    """Convierte un lote del CSV en documentos, omitiendo los campos vacíos."""
    registros = lote.to_dict("records")
    return [
        {k: v for k, v in fila.items() if not (v is None or (isinstance(v, float) and math.isnan(v)))}
        for fila in registros
    ]


def cargar_coleccion(db, clave: str) -> tuple[int, int]:
    """Importa un archivo CSV.gz en su colección. Devuelve (filas_csv, documentos)."""
    nombre = config.COLECCIONES[clave]
    ruta = config.ARCHIVOS_FUENTE[clave]
    if not ruta.exists():
        log.error("No se encontró el archivo fuente %s", ruta)
        raise FileNotFoundError(ruta)

    coleccion = db[nombre]
    coleccion.drop()
    log.info("Importando %s en la colección '%s'...", ruta.name, nombre)
    inicio = time.perf_counter()
    filas = 0
    for lote in pd.read_csv(ruta, chunksize=TAMANO_LOTE, low_memory=False):
        documentos = _a_documentos(lote)
        if documentos:
            coleccion.insert_many(documentos, ordered=False)
        filas += len(lote)
    for campo in INDICES[clave]:
        coleccion.create_index([(campo, ASCENDING)])

    documentos = coleccion.count_documents({})
    log.info("'%s': %d filas en CSV, %d documentos en MongoDB (%.1f s)",
             nombre, filas, documentos, time.perf_counter() - inicio)
    return filas, documentos


def main() -> int:
    """Carga las tres colecciones y valida los conteos."""
    obtener_logger("cargar_mongo")
    cliente = MongoClient(config.MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        cliente.admin.command("ping")
        log.info("Conectado a MongoDB en %s, base '%s'", config.MONGO_URI, config.MONGO_DB)
    except Exception:
        log.exception("No fue posible conectarse a MongoDB. ¿Está corriendo 'docker compose up -d'?")
        return 1

    db = cliente[config.MONGO_DB]
    errores = 0
    try:
        for clave in config.COLECCIONES:
            filas, documentos = cargar_coleccion(db, clave)
            if filas == documentos:
                log.info("Validación OK para '%s'", config.COLECCIONES[clave])
            else:
                errores += 1
                log.error("Validación FALLIDA para '%s': %d filas vs %d documentos",
                          config.COLECCIONES[clave], filas, documentos)
        log.info("Colecciones en '%s': %s", config.MONGO_DB, sorted(db.list_collection_names()))
    except Exception as exc:
        # Archivo faltante, CSV corrupto o error de escritura en MongoDB
        log.error("La carga a MongoDB se detuvo: %s: %s. Revise data/raw/ y vuelva a ejecutar "
                  "'python -m src.cargar_mongo'", type(exc).__name__, exc)
        return 1
    finally:
        cliente.close()
    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
