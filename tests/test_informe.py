import importlib.util
from pathlib import Path

RUTA = Path(__file__).resolve().parent.parent / "informe" / "generar_informe.py"
spec = importlib.util.spec_from_file_location("generar_informe", RUTA)
generar_informe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generar_informe)


def test_extracto_log_usa_solo_la_ultima_ejecucion(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("\n".join([
        "2026-10-03 08:56:30 | INFO | etl.carga | SQLite: tabla 'listings' cargada con 3 registros",
        "2026-10-03 08:56:48 | INFO | etl.main | INICIO DEL PROCESO ETL - Airbnb Bogotá",
        "2026-10-03 08:56:49 | INFO | etl.carga | SQLite: tabla 'listings' cargada con 19187 registros",
        "2026-10-03 09:04:36 | INFO | etl.main | FIN DEL PROCESO ETL en 467.2 s.",
    ]), encoding="utf-8")
    texto = generar_informe.extracto_log(log)
    assert "3 registros" not in texto
    assert texto.splitlines()[0].endswith("INICIO DEL PROCESO ETL - Airbnb Bogotá")
    assert "FIN DEL PROCESO" in texto


def test_extracto_log_conserva_fin_aunque_haya_muchas_lineas(tmp_path):
    lineas = ["x | INFO | etl.main | INICIO DEL PROCESO ETL"]
    lineas += [f"x | WARNING | etl.t | advertencia {i}" for i in range(100)]
    lineas += ["x | INFO | etl.main | FIN DEL PROCESO ETL"]
    (tmp_path / "log.txt").write_text("\n".join(lineas), encoding="utf-8")
    texto = generar_informe.extracto_log(tmp_path / "log.txt", max_lineas=20)
    assert len(texto.splitlines()) <= 21 and "FIN DEL PROCESO" in texto
