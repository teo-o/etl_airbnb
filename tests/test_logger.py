import logging
import re

from src import logger as modulo_logger


def test_crea_un_archivo_por_ejecucion_con_formato(tmp_path, monkeypatch):
    monkeypatch.setattr(modulo_logger, "_manejador_archivo", None)
    log = modulo_logger.obtener_logger("prueba", dir_logs=tmp_path)
    log.info("mensaje info")
    log.warning("mensaje warning")
    log.error("mensaje error")
    for h in logging.getLogger("etl").handlers:
        h.flush()

    archivos = list(tmp_path.glob("log_*.txt"))
    assert len(archivos) == 1
    assert re.fullmatch(r"log_\d{8}_\d{4}\.txt", archivos[0].name)
    contenido = archivos[0].read_text(encoding="utf-8")
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| INFO \| etl\.prueba \| mensaje info", contenido)
    assert "| WARNING |" in contenido and "| ERROR |" in contenido


def test_varios_modulos_comparten_el_mismo_archivo(tmp_path, monkeypatch):
    monkeypatch.setattr(modulo_logger, "_manejador_archivo", None)
    a = modulo_logger.obtener_logger("extraccion", dir_logs=tmp_path)
    b = modulo_logger.obtener_logger("carga", dir_logs=tmp_path)
    a.info("uno")
    b.info("dos")
    for h in logging.getLogger("etl").handlers:
        h.flush()
    archivos = list(tmp_path.glob("log_*.txt"))
    assert len(archivos) == 1
    texto = archivos[0].read_text(encoding="utf-8")
    assert "etl.extraccion | uno" in texto and "etl.carga | dos" in texto


def test_las_pruebas_no_escriben_en_logs_del_proyecto():
    from src import config
    log = modulo_logger.obtener_logger("prueba_aislamiento")
    log.info("no debe llegar a logs/ del proyecto")
    assert modulo_logger.ruta_log_actual().parent != config.RAIZ / "logs"
