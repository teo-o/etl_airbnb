"""Fase de EXTRACCIÓN del proceso ETL.

Contiene la clase :class:`Extraccion`, que se conecta a la base MongoDB local
``airbnb_bogota``, consulta las colecciones ``Listings``, ``Reviews`` y
``Calendar`` y las devuelve como DataFrames de pandas. Cada conexión y la
cantidad de registros extraídos por colección quedan en el log de la ejecución.

Ejemplo::

    from src.extraccion import Extraccion

    with Extraccion() as ext:
        datos = ext.extraer_todo()        # {"listings": df, "reviews": df, "calendar": df}
"""
import time

import pandas as pd
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from src import config
from src.logger import obtener_logger


class Extraccion:
    """Extrae colecciones de MongoDB hacia DataFrames de pandas.

    Args:
        uri: cadena de conexión de MongoDB (por defecto ``config.MONGO_URI``).
        nombre_db: base de datos a consultar (por defecto ``config.MONGO_DB``).
        timeout_ms: tiempo máximo para encontrar el servidor.
    """

    def __init__(self, uri: str = config.MONGO_URI, nombre_db: str = config.MONGO_DB,
                 timeout_ms: int = 5000):
        self.uri = uri
        self.nombre_db = nombre_db
        self.timeout_ms = timeout_ms
        self.cliente: MongoClient | None = None
        self.db = None
        self.log = obtener_logger("extraccion")

    # ------------------------------------------------------------------ conexión
    def conectar(self):
        """Abre la conexión y la verifica con un ``ping``.

        Raises:
            ConnectionError: si el servidor no responde.
        """
        try:
            self.cliente = MongoClient(self.uri, serverSelectionTimeoutMS=self.timeout_ms)
            self.cliente.admin.command("ping")
        except PyMongoError as exc:
            self.log.error("Error de conexión a MongoDB (%s): %s", self.uri, exc)
            self.cliente = None
            raise ConnectionError(f"No se pudo conectar a MongoDB en {self.uri}") from exc
        self.db = self.cliente[self.nombre_db]
        self.log.info("Conexión establecida con MongoDB en %s, base de datos '%s'",
                      self.uri, self.nombre_db)
        return self.db

    def cerrar(self) -> None:
        """Cierra la conexión con MongoDB."""
        if self.cliente is not None:
            self.cliente.close()
            self.log.info("Conexión a MongoDB cerrada")
        self.cliente = None
        self.db = None

    def __enter__(self):
        self.conectar()
        return self

    def __exit__(self, *exc):
        self.cerrar()
        return False

    # ----------------------------------------------------------------- consultas
    def listar_colecciones(self) -> list[str]:
        """Devuelve los nombres de las colecciones de la base de datos."""
        if self.db is None:
            self.conectar()
        colecciones = sorted(self.db.list_collection_names())
        self.log.info("Colecciones disponibles: %s", colecciones)
        return colecciones

    def extraer_coleccion(self, nombre: str, filtro: dict | None = None,
                          proyeccion: dict | None = None, lote: int = 100_000) -> pd.DataFrame:
        """Consulta una colección y la devuelve como DataFrame.

        Los documentos se leen por lotes desde el cursor para no duplicar en
        memoria colecciones grandes como ``Calendar`` (7 millones de
        documentos). El campo interno ``_id`` de MongoDB se excluye porque no
        aporta información analítica.

        Args:
            nombre: nombre de la colección (``Listings``, ``Reviews``, ``Calendar``).
            filtro: filtro de MongoDB opcional (p. ej. ``{"date": {"$gte": "2026-07-01"}}``).
            proyeccion: campos a incluir (p. ej. ``{"date": 1}``).
            lote: documentos por lote al construir el DataFrame.

        Raises:
            ValueError: si la colección no existe.
        """
        if self.db is None:
            self.conectar()
        if nombre not in self.db.list_collection_names():
            self.log.error("La colección '%s' no existe en '%s'", nombre, self.nombre_db)
            raise ValueError(f"Colección inexistente: {nombre}")

        proyeccion = dict(proyeccion or {})
        proyeccion["_id"] = 0
        inicio = time.perf_counter()
        cursor = self.db[nombre].find(filtro or {}, proyeccion, batch_size=lote)

        partes, buffer = [], []
        for documento in cursor:
            buffer.append(documento)
            if len(buffer) >= lote:
                partes.append(pd.DataFrame(buffer))
                buffer = []
        if buffer:
            partes.append(pd.DataFrame(buffer))
        df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()

        self.log.info("Colección '%s': %d registros extraídos, %d columnas (%.1f s)",
                      nombre, len(df), df.shape[1], time.perf_counter() - inicio)
        if df.empty:
            self.log.warning("La colección '%s' no devolvió registros", nombre)
        return df

    def extraer_todo(self) -> dict[str, pd.DataFrame]:
        """Extrae Listings, Reviews y Calendar.

        Returns:
            Diccionario ``{"listings": df, "reviews": df, "calendar": df}``.
        """
        datos = {clave: self.extraer_coleccion(nombre)
                 for clave, nombre in config.COLECCIONES.items()}
        total = sum(len(df) for df in datos.values())
        self.log.info("Extracción finalizada: %d registros en total", total)
        return datos


if __name__ == "__main__":
    with Extraccion() as extraccion:
        extraccion.listar_colecciones()
        extraccion.extraer_todo()
