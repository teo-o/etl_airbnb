"""Orquestador del proceso ETL Airbnb Bogotá: MongoDB -> pandas -> SQLite/XLSX.

Uso::

    python -m src.main              # ETL completo
    python -m src.main --sin-excel  # solo SQLite (más rápido)

Cada ejecución genera ``logs/log_YYYYMMDD_HHMM.txt`` y deja en ``output/``:
la base ``airbnb_bogota.db``, los archivos XLSX y dos JSON de soporte para el
informe (``resumen_transformaciones.json`` y ``reporte_verificacion.json``).
"""
import argparse
import json
import sys
import time

from src import config
from src.carga import Carga
from src.extraccion import Extraccion
from src.logger import obtener_logger, ruta_log_actual
from src.transformacion import Transformacion


def ejecutar(exportar_excel: bool = True) -> int:
    """Ejecuta Extracción -> Transformación -> Carga. Devuelve el código de salida."""
    log = obtener_logger("main")
    log.info("=" * 70)
    log.info("INICIO DEL PROCESO ETL - Airbnb Bogotá")
    inicio_total = time.perf_counter()
    etapa = "extracción"
    try:
        t0 = time.perf_counter()
        with Extraccion() as extraccion:
            datos = extraccion.extraer_todo()
        log.info("Etapa de extracción finalizada en %.1f s", time.perf_counter() - t0)

        etapa = "transformación"
        t0 = time.perf_counter()
        transformacion = Transformacion()
        tablas = transformacion.transformar_todo(datos)
        del datos  # libera memoria de los datos crudos
        log.info("Etapa de transformación finalizada en %.1f s", time.perf_counter() - t0)

        etapa = "carga"
        t0 = time.perf_counter()
        reporte = Carga().cargar(tablas, exportar_excel=exportar_excel)
        log.info("Etapa de carga finalizada en %.1f s", time.perf_counter() - t0)
    except Exception:
        log.exception("El proceso ETL falló en la etapa de %s", etapa)
        return 1

    config.DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    (config.DIR_SALIDA / "resumen_transformaciones.json").write_text(
        json.dumps(transformacion.resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    (config.DIR_SALIDA / "reporte_verificacion.json").write_text(
        json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")

    fallidas = [n for n, r in reporte.items() if not r["ok"]]
    log.info("FIN DEL PROCESO ETL en %.1f s. Tablas: %d, con diferencias: %d. Log: %s",
             time.perf_counter() - inicio_total, len(reporte), len(fallidas), ruta_log_actual())
    return 1 if fallidas else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Proceso ETL Airbnb Bogotá (MongoDB -> SQLite/XLSX)")
    parser.add_argument("--sin-excel", action="store_true", help="omite la exportación a XLSX")
    args = parser.parse_args(argv)
    return ejecutar(exportar_excel=not args.sin_excel)


if __name__ == "__main__":
    sys.exit(main())
