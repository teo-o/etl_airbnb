import json

import numpy as np
import pandas as pd
import pytest

from src.transformacion import Transformacion


@pytest.fixture
def t():
    return Transformacion()


# ------------------------------------------------------------------ precio
def test_normalizar_precio_quita_simbolos_y_convierte(t):
    s = pd.Series(["$1,234.50", "$284,294.01", None, "  $90,000.00 ", "abc"])
    r = t.normalizar_precio(s)
    assert r.iloc[0] == 1234.50
    assert r.iloc[1] == 284294.01
    assert np.isnan(r.iloc[2])
    assert r.iloc[3] == 90000.0
    assert np.isnan(r.iloc[4])
    assert r.dtype == "float64"


def test_categorizar_precio_por_rangos(t):
    s = pd.Series([50_000, 100_000, 150_000, 250_000, 900_000, np.nan])
    r = t.categorizar_precio(s)
    assert list(r) == ["Económico", "Medio", "Medio", "Alto", "Lujo", "Sin precio"]


def test_marcar_outliers_iqr(t):
    s = pd.Series([10, 11, 12, 13, 12, 11, 1000, np.nan])
    r = t.marcar_outliers_iqr(s)
    assert list(r) == [False, False, False, False, False, False, True, False]


# ------------------------------------------------------------------ fechas
def test_estandarizar_fechas_formato_iso(t):
    df = pd.DataFrame({"f": ["2026-06-22", "2010/10/06", "no es fecha", None]})
    r = t.estandarizar_fechas(df, ["f"], "prueba")
    assert r["f"].iloc[0] == "2026-06-22"
    assert r["f"].iloc[1] == "2010-10-06"
    assert pd.isna(r["f"].iloc[2]) and pd.isna(r["f"].iloc[3])


def test_derivar_variables_fecha(t):
    df = pd.DataFrame({"date": ["2026-06-21", "2027-01-05"]})
    r = t.derivar_variables_fecha(df, "date")
    assert list(r["anio"]) == [2026, 2027]
    assert list(r["mes"]) == [6, 1]
    assert list(r["dia"]) == [21, 5]
    assert list(r["trimestre"]) == [2, 1]
    assert list(r["nombre_mes"]) == ["Junio", "Enero"]
    assert list(r["dia_semana"]) == ["Domingo", "Martes"]


# ------------------------------------------------------------------ texto y tipos
def test_limpiar_texto(t):
    s = pd.Series(["  Hola<br/>mundo\r\n  ", "a   b", None])
    r = t.limpiar_texto(s)
    assert list(r[:2]) == ["Hola mundo", "a b"]
    assert pd.isna(r.iloc[2])


def test_convertir_booleanos(t):
    df = pd.DataFrame({"x": ["t", "f", None]})
    r = t.convertir_booleanos(df, ["x", "no_existe"])
    assert r["x"].tolist()[:2] == [True, False]
    assert pd.isna(r["x"].iloc[2])


def test_convertir_banos(t):
    df = pd.DataFrame({
        "bathrooms": [np.nan, 2.0, np.nan, np.nan],
        "bathrooms_text": ["1 shared bath", "2 baths", "Shared half-bath", "1.5 baths"],
    })
    r = t.convertir_banos(df)
    assert list(r["bathrooms"]) == [1.0, 2.0, 0.5, 1.5]
    assert list(r["bano_compartido"]) == [True, False, True, False]


# ------------------------------------------------------------------ anidados
def test_desanidar_amenities(t):
    df = pd.DataFrame({"id": [1, 2, 3],
                       "amenities": ['["Wifi", "Kitchen"]', '["Wifi"]', None]})
    listings, largo = t.desanidar_amenities(df)
    assert list(listings["cantidad_amenities"]) == [2, 1, 0]
    assert "amenities" not in listings.columns
    assert sorted(map(tuple, largo[["listing_id", "amenity"]].values.tolist())) == [
        (1, "Kitchen"), (1, "Wifi"), (2, "Wifi")]


def test_desanidar_price_quote(t):
    q = {"quote": {"currency": "COP", "is_available": True, "discount_amount": "780208.80",
                   "requested_checkin_date": "2027-04-01", "requested_checkout_date": "2027-04-29"}}
    df = pd.DataFrame({"id": [1, 2], "price_quote_raw": [json.dumps(q), None]})
    r = t.desanidar_price_quote(df)
    assert "price_quote_raw" not in r.columns
    assert r["cotizacion_moneda"].iloc[0] == "COP"
    assert r["cotizacion_descuento"].iloc[0] == 780208.80
    assert r["cotizacion_noches"].iloc[0] == 28
    assert bool(r["cotizacion_disponible"].iloc[0]) is True
    assert pd.isna(r["cotizacion_moneda"].iloc[1])


def test_extraer_hosts_crea_dimension_sin_duplicados(t):
    df = pd.DataFrame({"id": [1, 2, 3], "host_id": [10, 10, 20],
                       "host_name": ["Ana", "Ana", "Luis"],
                       "host_is_superhost": [True, True, False],
                       "price": [1.0, 2.0, 3.0]})
    listings, hosts = t.extraer_hosts(df)
    assert len(hosts) == 2 and hosts["host_id"].is_unique
    assert "host_name" not in listings.columns and "host_id" in listings.columns


# ------------------------------------------------------------------ tablas completas
def test_limpiar_duplicados(t):
    df = pd.DataFrame({"id": [1, 1, 2], "v": [1, 1, 3]})
    assert len(t.limpiar_duplicados(df, ["id"], "x")) == 2


def test_transformar_calendario_resume_por_mes_y_semana(t):
    cal = pd.DataFrame({
        "listing_id": [1] * 4 + [2] * 2,
        "date": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-08-01", "2026-07-01", "2026-07-01"],
        "available": ["t", "f", "f", "t", "t", "t"],
        "minimum_nights": [1] * 6, "maximum_nights": [30] * 6,
    })
    diario, mensual, semanal = t.transformar_calendario(cal)
    assert len(diario) == 5  # el duplicado (2, 2026-07-01) se elimina
    assert diario["disponible"].dtype == bool
    fila = mensual[(mensual.listing_id == 1) & (mensual.mes == 7)].iloc[0]
    assert fila["dias"] == 3 and fila["dias_disponibles"] == 1
    assert fila["tasa_no_disponible"] == pytest.approx(2 / 3)
    assert {"anio", "semana", "dias_registrados", "pct_disponible"} <= set(semanal.columns)


def test_transformar_reviews(t):
    rev = pd.DataFrame({"listing_id": [1, 1, 2], "id": [10, 11, 12],
                        "date": ["2024-01-05", "2024-02-01", "2024-03-01"],
                        "reviewer_id": [1, 2, 3], "reviewer_name": [" Ana ", "B", "C"],
                        "comments": ["Muy<br/>bueno", None, "ok"]})
    r = t.transformar_reviews(rev)
    assert len(r) == 2
    assert r["comments"].iloc[0] == "Muy bueno"
    assert r["reviewer_name"].iloc[0] == "Ana"
    assert {"anio", "mes", "trimestre", "longitud_comentario"} <= set(r.columns)


def test_transformar_listings_genera_tablas(t):
    df = pd.DataFrame({
        "id": [1, 2, 2], "host_id": [10, 20, 20], "host_name": ["A", "B", "B"],
        "host_is_superhost": ["t", "f", "f"], "host_location": ["Bogota, Colombia", None, None],
        "room_type": ["Entire home/apt"] * 3, "bedrooms": [2.0, np.nan, np.nan], "beds": [1.0, 2.0, 2.0],
        "bathrooms": [1.0, np.nan, np.nan], "bathrooms_text": ["1 bath", "2 baths", "2 baths"],
        "price": ["$100,000.00", None, None], "minimum_nights": [1, 2, 2],
        "availability_365": [300, 0, 0], "number_of_reviews": [3, 0, 0],
        "reviews_per_month": [0.5, np.nan, np.nan], "review_scores_rating": [4.8, np.nan, np.nan],
        "description": [None, "x", "x"], "license": [123.0, np.nan, np.nan],
        "neighbourhood_cleansed": [" chapinero ", "Usaquen", "Usaquen"],
        "amenities": ['["Wifi"]', "[]", "[]"], "last_scraped": ["2026-06-22"] * 3,
        "first_review": ["2020-01-01", None, None], "has_availability": ["t", None, None],
        "picture_url": ["u"] * 3,
    })
    tablas = t.transformar_listings(df)
    L = tablas["listings"]
    assert len(L) == 2
    assert L.loc[L.id == 1, "price"].iloc[0] == 100000.0
    assert L.loc[L.id == 2, "categoria_precio"].iloc[0] == "Sin precio"
    assert L.loc[L.id == 2, "bedrooms"].iloc[0] == 2.0  # mediana por room_type
    assert L.loc[L.id == 2, "reviews_per_month"].iloc[0] == 0
    assert bool(L.loc[L.id == 1, "tiene_reviews"].iloc[0]) is True
    assert L.loc[L.id == 1, "license"].iloc[0] == "123"
    assert L.loc[L.id == 2, "license"].iloc[0] == "Sin registro"
    assert L.loc[L.id == 1, "description"].iloc[0] == "Sin información"
    assert L.loc[L.id == 1, "neighbourhood_cleansed"].iloc[0] == "Chapinero"
    assert "picture_url" not in L.columns
    assert set(tablas) == {"listings", "hosts", "listing_amenities"}
    hosts = tablas["hosts"]
    assert hosts.loc[hosts.host_id == 10, "host_location"].iloc[0] == "Bogotá, Colombia"


def test_resumen_registra_filas_antes_y_despues(t):
    t.limpiar_duplicados(pd.DataFrame({"id": [1, 1]}), ["id"], "tabla_x")
    paso = t.resumen[-1]
    assert paso["tabla"] == "tabla_x" and paso["filas_antes"] == 2 and paso["filas_despues"] == 1


def test_calendario_tolera_fechas_invalidas(t):
    cal = pd.DataFrame({"listing_id": [1, 1, 1], "date": ["2026-07-01", "fecha-mala", "2026-07-02"],
                        "available": ["t", "f", "f"], "minimum_nights": [1] * 3, "maximum_nights": [30] * 3})
    diario, mensual, semanal = t.transformar_calendario(cal)
    assert len(diario) == 3
    assert mensual["dias"].sum() == 2 and semanal["dias_registrados"].sum() == 2


def test_licencia_no_numerica_se_conserva(t):
    df = pd.DataFrame({"id": [1, 2, 3], "license": ["RNT 12345", 98765.0, None]})
    r = t.tratar_nulos_listings(df)
    assert list(r["license"]) == ["RNT 12345", "98765", "Sin registro"]
    assert list(r["tiene_licencia"]) == [True, True, False]
