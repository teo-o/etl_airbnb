"""Pruebas de integración de Extraccion contra el MongoDB local.

Se usa una base temporal ``airbnb_test`` para no tocar los datos reales.
Si MongoDB no está disponible, las pruebas se omiten.
"""
import os

import pytest
from pymongo import MongoClient

from src.extraccion import Extraccion

URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_PRUEBA = "airbnb_test"


@pytest.fixture(scope="module")
def db_prueba():
    cliente = MongoClient(URI, serverSelectionTimeoutMS=1500)
    try:
        cliente.admin.command("ping")
    except Exception:
        pytest.skip("MongoDB local no disponible")
    cliente.drop_database(DB_PRUEBA)  # limpia restos de una ejecución interrumpida
    db = cliente[DB_PRUEBA]
    db["Listings"].insert_many([{"id": i, "price": f"${i},000.00"} for i in range(5)])
    db["Reviews"].insert_many([{"listing_id": 1, "id": i, "date": "2024-01-01"} for i in range(3)])
    db["Calendar"].insert_many([{"listing_id": 1, "date": f"2026-07-{d:02d}", "available": "t"} for d in range(1, 8)])
    yield db
    cliente.drop_database(DB_PRUEBA)
    cliente.close()


def test_extrae_coleccion_sin_id_de_mongo(db_prueba):
    with Extraccion(URI, DB_PRUEBA) as ext:
        df = ext.extraer_coleccion("Listings", lote=2)
    assert len(df) == 5
    assert "_id" not in df.columns
    assert set(df.columns) == {"id", "price"}


def test_extraer_todo_devuelve_las_tres_colecciones(db_prueba):
    with Extraccion(URI, DB_PRUEBA) as ext:
        datos = ext.extraer_todo()
    assert set(datos) == {"listings", "reviews", "calendar"}
    assert [len(datos[k]) for k in ("listings", "reviews", "calendar")] == [5, 3, 7]


def test_filtro_y_proyeccion(db_prueba):
    with Extraccion(URI, DB_PRUEBA) as ext:
        df = ext.extraer_coleccion("Calendar", filtro={"date": {"$gte": "2026-07-05"}},
                                   proyeccion={"date": 1})
    assert list(df.columns) == ["date"] and len(df) == 3


def test_coleccion_inexistente_lanza_error(db_prueba):
    with Extraccion(URI, DB_PRUEBA) as ext:
        with pytest.raises(ValueError):
            ext.extraer_coleccion("NoExiste")


def test_conexion_fallida_lanza_error():
    ext = Extraccion("mongodb://localhost:1", DB_PRUEBA, timeout_ms=300)
    with pytest.raises(ConnectionError):
        ext.conectar()
