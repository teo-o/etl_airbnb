"""Pruebas de la carga inicial a MongoDB (usa una base temporal)."""
import os
from pathlib import Path

import pytest
from pymongo import MongoClient

from src import cargar_mongo, config

URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_PRUEBA = "airbnb_test_carga"


@pytest.fixture
def mongo_prueba(monkeypatch):
    cliente = MongoClient(URI, serverSelectionTimeoutMS=1500)
    try:
        cliente.admin.command("ping")
    except Exception:
        pytest.skip("MongoDB local no disponible")
    monkeypatch.setattr(config, "MONGO_URI", URI)
    monkeypatch.setattr(config, "MONGO_DB", DB_PRUEBA)
    yield cliente
    cliente.drop_database(DB_PRUEBA)
    cliente.close()


def test_logs_de_modulos_importados_no_van_a_logs_del_proyecto():
    import logging
    rutas = [Path(h.baseFilename).parent for h in logging.getLogger("etl").handlers
             if isinstance(h, logging.FileHandler)]
    assert config.RAIZ / "logs" not in rutas


def test_archivo_fuente_faltante_termina_con_error_controlado(mongo_prueba, monkeypatch, tmp_path, caplog):
    faltantes = {clave: tmp_path / f"{clave}.csv.gz" for clave in config.COLECCIONES}
    monkeypatch.setattr(config, "ARCHIVOS_FUENTE", faltantes)
    with caplog.at_level("ERROR", logger="etl.cargar_mongo"):
        codigo = cargar_mongo.main()
    assert codigo == 1
    assert any("No se encontró el archivo fuente" in r.getMessage() for r in caplog.records)
    assert any("La carga a MongoDB se detuvo" in r.getMessage() for r in caplog.records)


def test_carga_un_csv_pequeno_y_valida_conteo(mongo_prueba, monkeypatch, tmp_path):
    import pandas as pd
    archivos = {}
    for clave, filas in {"listings": 3, "reviews": 2, "calendar": 4}.items():
        ruta = tmp_path / f"{clave}.csv.gz"
        pd.DataFrame({"id": range(filas), "price": ["$1,000.00"] * filas, "vacio": [None] * filas}).to_csv(
            ruta, index=False, compression="gzip")
        archivos[clave] = ruta
    monkeypatch.setattr(config, "ARCHIVOS_FUENTE", archivos)
    assert cargar_mongo.main() == 0
    db = mongo_prueba[DB_PRUEBA]
    assert db["Calendar"].count_documents({}) == 4
    documento = db["Listings"].find_one({}, {"_id": 0})
    assert documento["price"] == "$1,000.00" and "vacio" not in documento


def test_importar_el_modulo_no_crea_archivos_de_log(tmp_path):
    import subprocess
    import sys
    entorno = {**os.environ, "DIR_LOGS": str(tmp_path)}
    subprocess.run([sys.executable, "-c", "import src.cargar_mongo"], cwd=config.RAIZ, env=entorno, check=True)
    assert list(tmp_path.glob("log_*.txt")) == []
