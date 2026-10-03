"""Configuración central del proyecto ETL Airbnb Bogotá.

Todos los valores pueden sobreescribirse con variables de entorno, lo que
permite ejecutar el proyecto en otro equipo sin modificar el código.
"""
import os
from pathlib import Path

# Raíz del proyecto (carpeta que contiene src/, data/, logs/, output/)
RAIZ = Path(__file__).resolve().parent.parent

# Conexión a MongoDB local (levantada con docker compose)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "airbnb_bogota")

# Nombres de colecciones exigidos por el taller
COLECCIONES = {
    "listings": "Listings",
    "reviews": "Reviews",
    "calendar": "Calendar",
}

# Rutas
DIR_DATOS = Path(os.getenv("DIR_DATOS", RAIZ / "data" / "raw"))
DIR_LOGS = Path(os.getenv("DIR_LOGS", RAIZ / "logs"))
DIR_SALIDA = Path(os.getenv("DIR_SALIDA", RAIZ / "output"))
RUTA_SQLITE = Path(os.getenv("RUTA_SQLITE", DIR_SALIDA / "airbnb_bogota.db"))

# Archivos fuente (Inside Airbnb, Bogotá, scrape 2026-06-21)
ARCHIVOS_FUENTE = {
    "listings": DIR_DATOS / "listings.csv.gz",
    "reviews": DIR_DATOS / "reviews.csv.gz",
    "calendar": DIR_DATOS / "calendar.csv.gz",
}
