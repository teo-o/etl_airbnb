"""Fase de TRANSFORMACIÓN del proceso ETL.

Contiene la clase :class:`Transformacion`, que recibe los DataFrames crudos
extraídos de MongoDB (``Listings``, ``Reviews`` y ``Calendar``) y produce las
tablas limpias que se cargan en SQLite y XLSX:

=====================  =======================================================
Tabla                  Contenido
=====================  =======================================================
``listings``           un registro por alojamiento, precios numéricos,
                       fechas ISO, flags de calidad y categoría de precio
``hosts``              dimensión de anfitriones (un registro por ``host_id``)
``listing_amenities``  amenities desanidadas (listing_id, amenity)
``calendar``           calendario diario con variables de fecha derivadas
``calendar_mensual``   disponibilidad agregada por alojamiento y mes
``calendar_semanal``   disponibilidad agregada de toda la ciudad por semana
``reviews``            reseñas con texto limpio y variables de fecha
=====================  =======================================================

Cada paso registra en el log las filas antes/después y las advertencias, y
queda anotado en ``self.resumen`` (lista de pasos) para el informe final.
Las decisiones se justifican en el notebook ``exploracion_airbnb.ipynb``.
"""
import json
import time

import numpy as np
import pandas as pd

from src.logger import obtener_logger

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

# Rangos de precio por noche en pesos colombianos (COP). Se eligieron a partir
# de los cuartiles observados en el EDA (Q1≈110 mil, mediana≈161 mil,
# Q3≈230 mil, P90≈360 mil) para que cada categoría tenga un tamaño útil.
RANGOS_PRECIO = [0, 100_000, 200_000, 400_000, np.inf]
ETIQUETAS_PRECIO = ["Económico", "Medio", "Alto", "Lujo"]
SIN_PRECIO = "Sin precio"
SIN_INFORMACION = "Sin información"

# Columnas sin valor analítico: URLs de imágenes/perfiles e identificador del scrape
COLUMNAS_SIN_VALOR = ["picture_url", "host_url", "host_profile_url", "host_picture_url",
                      "host_thumbnail_url", "scrape_id"]
COLUMNAS_BOOLEANAS = ["host_is_superhost", "host_has_profile_pic", "host_identity_verified",
                      "has_availability", "instant_bookable"]
COLUMNAS_FECHA_LISTINGS = ["last_scraped", "host_since", "first_review", "last_review",
                           "calendar_last_scraped", "price_quote_checkin_date",
                           "price_quote_checkout_date"]
COLUMNAS_PRECIO = ["price", "price_quote_total_price", "price_quote_price_per_night"]
COLUMNAS_TEXTO = ["name", "description", "host_about", "host_location"]


class Transformacion:
    """Limpia, normaliza y enriquece los datos de Airbnb Bogotá."""

    def __init__(self):
        self.log = obtener_logger("transformacion")
        self.resumen: list[dict] = []

    # ================================================================ utilidades
    def _registrar(self, paso: str, tabla: str, antes: int, despues: int, detalle: str = ""):
        """Anota un paso de transformación en el log y en ``self.resumen``."""
        self.resumen.append({"paso": paso, "tabla": tabla, "filas_antes": antes,
                             "filas_despues": despues, "detalle": detalle})
        self.log.info("[%s] %s: %d -> %d filas. %s", tabla, paso, antes, despues, detalle)

    # ============================================================ limpieza básica
    def limpiar_duplicados(self, df: pd.DataFrame, subset: list[str], tabla: str) -> pd.DataFrame:
        """Elimina registros duplicados según la clave natural ``subset``.

        Se usa la clave de negocio (``id`` del alojamiento, ``id`` de la
        reseña, ``listing_id``+``date`` en el calendario) en lugar de comparar
        filas completas, porque dos versiones de un mismo registro no deben
        coexistir en la base analítica.
        """
        antes = len(df)
        df = df.drop_duplicates(subset=subset, keep="first").reset_index(drop=True)
        eliminados = antes - len(df)
        if eliminados:
            self.log.warning("[%s] Se eliminaron %d duplicados por %s", tabla, eliminados, subset)
        self._registrar("Eliminación de duplicados", tabla, antes, len(df),
                        f"clave {subset}, {eliminados} duplicados")
        return df

    def eliminar_columnas_sin_valor(self, df: pd.DataFrame, tabla: str) -> pd.DataFrame:
        """Elimina columnas 100 % vacías y columnas sin valor analítico (URLs).

        En este scrape varias columnas del CSV original (``host_since``,
        ``host_response_rate``, ``neighbourhood_group_cleansed``...) vienen
        totalmente vacías; MongoDB ni siquiera las almacena. Si aparecieran
        vacías en otra versión del dataset, también se eliminan aquí.
        """
        vacias = [c for c in df.columns if df[c].isna().all()]
        sin_valor = [c for c in COLUMNAS_SIN_VALOR if c in df.columns]
        a_eliminar = vacias + [c for c in sin_valor if c not in vacias]
        if vacias:
            self.log.warning("[%s] Columnas 100%% vacías eliminadas: %s", tabla, vacias)
        df = df.drop(columns=a_eliminar)
        self._registrar("Eliminación de columnas vacías/sin valor", tabla, len(df), len(df),
                        f"{len(a_eliminar)} columnas eliminadas: {a_eliminar}")
        return df

    # ====================================================== normalización de tipos
    @staticmethod
    def normalizar_precio(serie: pd.Series) -> pd.Series:
        """Convierte precios en texto (``"$284,294.01"``) a ``float``.

        Elimina el símbolo ``$``, los separadores de miles ``,`` y espacios.
        Los valores no convertibles quedan como ``NaN``.
        """
        if pd.api.types.is_numeric_dtype(serie):
            return serie.astype("float64")
        limpio = serie.astype("string").str.replace(r"[\$,\s]", "", regex=True)
        return pd.to_numeric(limpio, errors="coerce").astype("float64")

    @staticmethod
    def convertir_booleanos(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
        """Convierte columnas ``'t'``/``'f'`` a booleanos (nullable)."""
        df = df.copy()
        for col in columnas:
            if col in df.columns and not pd.api.types.is_bool_dtype(df[col]):
                df[col] = df[col].map({"t": True, "f": False}).astype("boolean")
        return df

    @staticmethod
    def limpiar_texto(serie: pd.Series) -> pd.Series:
        """Estandariza texto: quita etiquetas ``<br/>``, saltos de línea y espacios repetidos."""
        return (serie.astype("string")
                .str.replace(r"<br\s*/?>", " ", regex=True)
                .str.replace(r"\s+", " ", regex=True)
                .str.strip())

    def convertir_banos(self, df: pd.DataFrame) -> pd.DataFrame:
        """Deriva el número de baños y si son compartidos desde ``bathrooms_text``.

        ``bathrooms`` tiene nulos que sí están descritos en ``bathrooms_text``
        (``"1 shared bath"``, ``"Shared half-bath"``); se completan con el
        número extraído del texto (``half-bath`` = 0.5).
        """
        df = df.copy()
        if "bathrooms_text" not in df.columns:
            return df
        texto = df["bathrooms_text"].astype("string").str.lower()
        numero = pd.to_numeric(texto.str.extract(r"(\d+(?:\.\d+)?)")[0], errors="coerce")
        numero = numero.mask(numero.isna() & texto.str.contains("half", na=False), 0.5)
        if "bathrooms" in df.columns:
            nulos = int(df["bathrooms"].isna().sum())
            df["bathrooms"] = df["bathrooms"].astype("float64").fillna(numero.astype("float64"))
            self.log.info("bathrooms: %d nulos completados desde bathrooms_text, quedan %d",
                          nulos - int(df["bathrooms"].isna().sum()), int(df["bathrooms"].isna().sum()))
        else:
            df["bathrooms"] = numero.astype("float64")
        df["bano_compartido"] = texto.str.contains("shared", na=False).astype(bool)
        return df

    # ================================================================== fechas
    def estandarizar_fechas(self, df: pd.DataFrame, columnas: list[str], tabla: str) -> pd.DataFrame:
        """Convierte columnas de fecha a texto ISO ``YYYY-MM-DD``.

        Primero se intenta el formato ISO (rápido, sirve para 7 millones de
        filas del calendario); solo los valores que fallan se reintentan con
        un parser flexible. Las fechas inválidas quedan nulas y se reportan
        como advertencia.
        """
        df = df.copy()
        for col in columnas:
            if col not in df.columns:
                continue
            original = df[col].astype("string")
            fechas = pd.to_datetime(original, format="%Y-%m-%d", errors="coerce")
            pendientes = fechas.isna() & original.notna()
            if pendientes.any():
                fechas.loc[pendientes] = pd.to_datetime(original[pendientes], format="mixed",
                                                         errors="coerce")
            iso = original.where(~pendientes)
            iso.loc[pendientes] = fechas[pendientes].dt.strftime("%Y-%m-%d")
            invalidas = int((fechas.isna() & original.notna()).sum())
            if invalidas:
                self.log.warning("[%s] %d valores inválidos en la fecha '%s' quedaron nulos",
                                 tabla, invalidas, col)
            df[col] = iso
        self._registrar("Estandarización de fechas a YYYY-MM-DD", tabla, len(df), len(df),
                        f"columnas {[c for c in columnas if c in df.columns]}")
        return df

    @staticmethod
    def derivar_variables_fecha(df: pd.DataFrame, columna: str) -> pd.DataFrame:
        """Agrega ``anio``, ``mes``, ``dia``, ``trimestre``, ``nombre_mes`` y ``dia_semana``.

        Estas variables permiten analizar estacionalidad (por mes/trimestre) y
        patrones semanales sin recalcular la fecha en cada consulta.
        """
        df = df.copy()
        fecha = pd.to_datetime(df[columna], format="%Y-%m-%d", errors="coerce")
        df["anio"] = fecha.dt.year.astype("Int64")
        df["mes"] = fecha.dt.month.astype("Int64")
        df["dia"] = fecha.dt.day.astype("Int64")
        df["trimestre"] = fecha.dt.quarter.astype("Int64")
        codigos_mes = fecha.dt.month.fillna(0).astype(int).to_numpy() - 1
        codigos_dia = fecha.dt.dayofweek.fillna(-1).astype(int).to_numpy()
        df["nombre_mes"] = pd.Categorical.from_codes(codigos_mes, categories=MESES)
        df["dia_semana"] = pd.Categorical.from_codes(codigos_dia, categories=DIAS_SEMANA)
        return df

    # =========================================================== precio/outliers
    @staticmethod
    def categorizar_precio(precio: pd.Series) -> pd.Series:
        """Asigna una categoría de precio por noche: Económico, Medio, Alto, Lujo o Sin precio."""
        categorias = pd.cut(precio, bins=RANGOS_PRECIO, labels=ETIQUETAS_PRECIO, right=False)
        categorias = categorias.cat.add_categories([SIN_PRECIO]).fillna(SIN_PRECIO)
        return categorias

    @staticmethod
    def marcar_outliers_iqr(serie: pd.Series, factor: float = 1.5) -> pd.Series:
        """Marca como atípicos los valores fuera de ``[Q1 - 1.5·IQR, Q3 + 1.5·IQR]``.

        Los atípicos se marcan y NO se eliminan: un precio alto puede ser un
        alojamiento de lujo real; la decisión de excluirlos queda para cada
        análisis (p. ej. promedios por barrio).
        """
        q1, q3 = serie.quantile(0.25), serie.quantile(0.75)
        iqr = q3 - q1
        return ((serie < q1 - factor * iqr) | (serie > q3 + factor * iqr)).fillna(False).astype(bool)

    # ================================================================ anidados
    def desanidar_amenities(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Separa la lista JSON ``amenities`` en una tabla larga.

        Una lista dentro de una celda no se puede filtrar ni contar en SQL;
        la tabla ``listing_amenities`` (una fila por alojamiento-amenity)
        permite responder "¿cuántos alojamientos tienen Wifi?" con un
        ``GROUP BY``. En ``listings`` queda solo ``cantidad_amenities``.
        """
        def _parsear(valor):
            if not isinstance(valor, str):
                return []
            try:
                return [a.strip() for a in json.loads(valor) if str(a).strip()]
            except json.JSONDecodeError:
                return []

        df = df.copy()
        listas = df["amenities"].map(_parsear)
        invalidas = int((df["amenities"].notna() & (listas.str.len() == 0)
                         & (df["amenities"].astype("string") != "[]")).sum())
        if invalidas:
            self.log.warning("amenities: %d valores no pudieron interpretarse como JSON", invalidas)
        df["cantidad_amenities"] = listas.str.len().astype(int)
        largo = (pd.DataFrame({"listing_id": df["id"], "amenity": listas})
                 .explode("amenity").dropna(subset=["amenity"])
                 .drop_duplicates().reset_index(drop=True))
        largo["amenity"] = largo["amenity"].astype("string")
        df = df.drop(columns=["amenities"])
        self._registrar("Desanidado de amenities", "listing_amenities", len(df), len(largo),
                        f"{largo['amenity'].nunique()} amenities distintas")
        return df, largo

    def desanidar_price_quote(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extrae los campos útiles del JSON anidado ``price_quote_raw``.

        El campo guarda la cotización que Airbnb devolvió al consultar una
        estadía: moneda, disponibilidad, descuento y fechas solicitadas. Se
        conservan esos datos como columnas planas y se elimina el JSON.
        """
        if "price_quote_raw" not in df.columns:
            return df
        df = df.copy()

        def _quote(valor):
            if not isinstance(valor, str):
                return {}
            try:
                return json.loads(valor).get("quote") or {}
            except (json.JSONDecodeError, AttributeError):
                return {}

        quotes = df["price_quote_raw"].map(_quote)
        df["cotizacion_moneda"] = quotes.map(lambda q: q.get("currency")).astype("string")
        df["cotizacion_disponible"] = quotes.map(lambda q: q.get("is_available")).astype("boolean")
        df["cotizacion_descuento"] = pd.to_numeric(quotes.map(lambda q: q.get("discount_amount")),
                                                   errors="coerce").astype("float64")
        entrada = pd.to_datetime(quotes.map(lambda q: q.get("requested_checkin_date")), errors="coerce")
        salida = pd.to_datetime(quotes.map(lambda q: q.get("requested_checkout_date")), errors="coerce")
        df["cotizacion_noches"] = (salida - entrada).dt.days.astype("Int64")
        df = df.drop(columns=["price_quote_raw"])
        self._registrar("Desanidado de price_quote_raw", "listings", len(df), len(df),
                        "moneda, disponibilidad, descuento y noches cotizadas")
        return df

    def extraer_hosts(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Separa la información del anfitrión en la dimensión ``hosts``.

        Un anfitrión con varios alojamientos repite sus datos en cada fila;
        se normaliza a una tabla con un registro por ``host_id`` y en
        ``listings`` queda solo la llave ``host_id``.
        """
        columnas_host = [c for c in df.columns
                         if (c.startswith("host_") or c.startswith("hosts_")
                             or c.startswith("calculated_host_listings_count")) and c != "host_id"]
        hosts = (df[["host_id"] + columnas_host].drop_duplicates(subset=["host_id"])
                 .reset_index(drop=True))
        listings = df.drop(columns=columnas_host)
        self._registrar("Extracción de dimensión hosts", "hosts", len(df), len(hosts),
                        f"{len(columnas_host)} columnas de anfitrión normalizadas")
        return listings, hosts

    # =================================================================== nulos
    def tratar_nulos_listings(self, df: pd.DataFrame) -> pd.DataFrame:
        """Trata los valores faltantes de ``listings`` según su significado.

        * ``bedrooms``, ``beds``, ``bathrooms``, ``minimum_nights``: mediana
          por ``room_type`` (un cuarto privado y un apartamento completo no
          tienen la misma distribución).
        * ``reviews_per_month``: 0, porque el nulo significa "sin reseñas".
        * ``review_scores_*``: se dejan nulos (imputarlos inventaría
          calificaciones) y se agrega el flag ``tiene_reviews``.
        * ``license``: texto del registro (RNT) o ``"Sin registro"`` + flag.
        * ``has_availability``: se deduce de ``availability_365 > 0``.
        * textos descriptivos: ``"Sin información"``.
        * ``price``: se conserva el nulo (no se inventan precios) y se
          reporta como advertencia; su categoría será ``"Sin precio"``.
        """
        df = df.copy()
        nulos_antes = int(df.isna().sum().sum())

        for col in ["bedrooms", "beds", "bathrooms", "minimum_nights"]:
            if col not in df.columns:
                continue
            n = int(df[col].isna().sum())
            if n == 0:
                continue
            if "room_type" in df.columns:
                mediana_grupo = df.groupby("room_type")[col].transform("median")
                df[col] = df[col].fillna(mediana_grupo)
            df[col] = df[col].fillna(df[col].median())
            self.log.info("%s: %d nulos imputados con la mediana por room_type", col, n)

        if "number_of_reviews" in df.columns:
            df["tiene_reviews"] = (df["number_of_reviews"].fillna(0) > 0).astype(bool)
        if "reviews_per_month" in df.columns:
            df["reviews_per_month"] = df["reviews_per_month"].fillna(0.0)

        if "license" in df.columns:
            # El RNT llega como número (112727.0): se guarda como texto sin decimales.
            # Si alguna licencia trae texto (p. ej. "RNT 12345") se conserva tal cual.
            df["tiene_licencia"] = df["license"].notna().astype(bool)
            numerica = pd.to_numeric(df["license"], errors="coerce").astype("Int64").astype("string")
            df["license"] = numerica.fillna(df["license"].astype("string")).fillna("Sin registro")

        if "has_availability" in df.columns and "availability_365" in df.columns:
            n = int(df["has_availability"].isna().sum())
            df["has_availability"] = df["has_availability"].fillna(df["availability_365"] > 0).astype(bool)
            if n:
                self.log.info("has_availability: %d nulos deducidos de availability_365", n)

        for col in COLUMNAS_TEXTO:
            if col in df.columns:
                df[col] = df[col].astype("string").fillna(SIN_INFORMACION)

        if "price" in df.columns:
            sin_precio = int(df["price"].isna().sum())
            if sin_precio:
                self.log.warning("%d alojamientos sin precio publicado: se conservan con "
                                 "categoría '%s'", sin_precio, SIN_PRECIO)

        nulos_despues = int(df.isna().sum().sum())
        self._registrar("Tratamiento de nulos", "listings", len(df), len(df),
                        f"celdas nulas {nulos_antes} -> {nulos_despues}")
        return df

    # ======================================================== tablas completas
    def transformar_listings(self, df: pd.DataFrame) -> dict[str, pd.DataFrame]:
        """Aplica todas las transformaciones a ``Listings``.

        Returns:
            ``{"listings": df, "hosts": df, "listing_amenities": df}``
        """
        inicio = time.perf_counter()
        self.log.info("Transformando listings: %d filas, %d columnas", *df.shape)
        df = self.limpiar_duplicados(df, ["id"], "listings")
        df = self.eliminar_columnas_sin_valor(df, "listings")

        # Moneda: "$284,294.01" -> 284294.01
        for col in COLUMNAS_PRECIO:
            if col in df.columns:
                df[col] = self.normalizar_precio(df[col])
        self._registrar("Normalización de precios", "listings", len(df), len(df),
                        "se eliminan '$' y ',' y se convierte a float (COP)")

        df = self.desanidar_price_quote(df)
        df = self.convertir_booleanos(df, COLUMNAS_BOOLEANAS)
        df = self.estandarizar_fechas(df, COLUMNAS_FECHA_LISTINGS, "listings")
        df = self.convertir_banos(df)
        df = self.tratar_nulos_listings(df)

        # Texto: limpieza de descripciones, barrios en formato título y
        # unificación de "Bogota" -> "Bogotá" en la ubicación del anfitrión.
        for col in ["name", "description", "host_about"]:
            if col in df.columns:
                df[col] = self.limpiar_texto(df[col])
        if "neighbourhood_cleansed" in df.columns:
            df["neighbourhood_cleansed"] = self.limpiar_texto(df["neighbourhood_cleansed"]).str.title()
        if "host_location" in df.columns:
            df["host_location"] = (self.limpiar_texto(df["host_location"])
                                   .str.replace(r"\bBogota\b", "Bogotá", regex=True))
        self._registrar("Estandarización de texto", "listings", len(df), len(df),
                        "espacios, etiquetas HTML, barrios en formato título, 'Bogota' -> 'Bogotá'")

        # Categorías y marcas de calidad
        if "price" in df.columns:
            df["categoria_precio"] = self.categorizar_precio(df["price"])
            df["es_outlier_precio"] = self.marcar_outliers_iqr(df["price"])
            self.log.info("Precio: %d alojamientos marcados como atípicos (IQR); distribución "
                          "por categoría: %s", int(df["es_outlier_precio"].sum()),
                          df["categoria_precio"].value_counts().to_dict())
        if "minimum_nights" in df.columns:
            df["es_estancia_larga"] = (df["minimum_nights"] >= 30).astype(bool)
        if "availability_365" in df.columns:
            df["sin_disponibilidad_anual"] = (df["availability_365"] == 0).astype(bool)
        self._registrar("Categorización de precios y marcas de atípicos", "listings",
                        len(df), len(df), f"rangos COP {RANGOS_PRECIO[1:-1]}")

        df, amenities = self.desanidar_amenities(df)
        df, hosts = self.extraer_hosts(df)
        self.log.info("Listings transformado en %.1f s: %d filas, %d columnas",
                      time.perf_counter() - inicio, *df.shape)
        return {"listings": df, "hosts": hosts, "listing_amenities": amenities}

    def transformar_reviews(self, df: pd.DataFrame, ids_listings: pd.Series | None = None) -> pd.DataFrame:
        """Limpia ``Reviews``: duplicados, comentarios vacíos, texto y fechas.

        Las reseñas sin comentario se eliminan porque el valor de esta tabla
        es el texto; el conteo de reseñas por alojamiento ya está en
        ``listings.number_of_reviews``.
        """
        inicio = time.perf_counter()
        df = self.limpiar_duplicados(df, ["id"], "reviews")

        antes = len(df)
        df = df.dropna(subset=["comments"]).reset_index(drop=True)
        if antes - len(df):
            self.log.warning("[reviews] %d reseñas sin comentario eliminadas", antes - len(df))
        self._registrar("Eliminación de reseñas sin comentario", "reviews", antes, len(df))

        if ids_listings is not None:
            huerfanas = int((~df["listing_id"].isin(ids_listings)).sum())
            if huerfanas:
                self.log.warning("[reviews] %d reseñas de alojamientos que no están en listings",
                                 huerfanas)

        df["comments"] = self.limpiar_texto(df["comments"])
        df["reviewer_name"] = self.limpiar_texto(df["reviewer_name"])
        df["longitud_comentario"] = df["comments"].str.len().astype("Int64")
        df = self.estandarizar_fechas(df, ["date"], "reviews")
        df = self.derivar_variables_fecha(df, "date")
        self._registrar("Variables de fecha derivadas", "reviews", len(df), len(df),
                        "anio, mes, dia, trimestre, nombre_mes, dia_semana")
        self.log.info("Reviews transformado en %.1f s", time.perf_counter() - inicio)
        return df

    def transformar_calendario(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Limpia ``Calendar`` y genera los resúmenes mensual y semanal.

        El calendario diario (≈7 millones de filas) no cabe en una hoja de
        Excel y es poco práctico para análisis; por eso se resume:

        * ``calendar_mensual``: por alojamiento y mes, días disponibles y
          ``tasa_no_disponible`` (proxy de ocupación: días reservados o
          bloqueados por el anfitrión).
        * ``calendar_semanal``: por semana ISO para toda la ciudad.

        Returns:
            ``(calendar_diario, calendar_mensual, calendar_semanal)``
        """
        inicio = time.perf_counter()
        df = self.limpiar_duplicados(df, ["listing_id", "date"], "calendar")
        df["disponible"] = df["available"].map({"t": True, "f": False})
        sin_dato = int(df["disponible"].isna().sum())
        if sin_dato:
            self.log.warning("[calendar] %d días con 'available' inválido se toman como no disponibles",
                             sin_dato)
        df["disponible"] = df["disponible"].fillna(False).astype(bool)
        df = df.drop(columns=["available"])
        df = self.estandarizar_fechas(df, ["date"], "calendar")
        df = self.derivar_variables_fecha(df, "date")
        self._registrar("Variables de fecha derivadas", "calendar", len(df), len(df),
                        "anio, mes, dia, trimestre, nombre_mes, dia_semana")

        # Los días con fecha inválida (quedaron nulos) se conservan en el detalle
        # diario pero no pueden asignarse a un mes o semana en los resúmenes.
        con_fecha = df[df["date"].notna()]
        if len(con_fecha) < len(df):
            self.log.warning("[calendar] %d días sin fecha válida se excluyen de los resúmenes",
                             len(df) - len(con_fecha))

        mensual = (con_fecha.groupby(["listing_id", "anio", "mes"], observed=True)
                   .agg(dias=("disponible", "size"),
                        dias_disponibles=("disponible", "sum"),
                        minimo_noches_promedio=("minimum_nights", "mean"))
                   .reset_index())
        mensual["dias_no_disponibles"] = mensual["dias"] - mensual["dias_disponibles"]
        mensual["tasa_no_disponible"] = mensual["dias_no_disponibles"] / mensual["dias"]
        self._registrar("Resumen mensual del calendario", "calendar_mensual", len(df), len(mensual),
                        "agrupado por listing_id, anio, mes")

        fecha = pd.to_datetime(con_fecha["date"], format="%Y-%m-%d")
        iso = fecha.dt.isocalendar()
        semanal = (pd.DataFrame({"anio": iso["year"].astype(int), "semana": iso["week"].astype(int),
                                 "fecha": fecha, "listing_id": con_fecha["listing_id"],
                                 "disponible": con_fecha["disponible"]})
                   .groupby(["anio", "semana"])
                   .agg(fecha_inicio=("fecha", "min"), dias_registrados=("disponible", "size"),
                        alojamientos=("listing_id", "nunique"), dias_disponibles=("disponible", "sum"))
                   .reset_index())
        semanal["fecha_inicio"] = semanal["fecha_inicio"].dt.strftime("%Y-%m-%d")
        semanal["pct_disponible"] = 100 * semanal["dias_disponibles"] / semanal["dias_registrados"]
        self._registrar("Resumen semanal del calendario", "calendar_semanal", len(df), len(semanal),
                        "agrupado por semana ISO")
        self.log.info("Calendar transformado en %.1f s", time.perf_counter() - inicio)
        return df, mensual, semanal

    def transformar_todo(self, datos: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """Ejecuta la transformación completa sobre el resultado de ``Extraccion.extraer_todo``.

        Returns:
            Diccionario con las 7 tablas limpias listas para la carga.
        """
        self.log.info("Inicio de la transformación")
        tablas = self.transformar_listings(datos["listings"])
        tablas["reviews"] = self.transformar_reviews(datos["reviews"], tablas["listings"]["id"])
        (tablas["calendar"], tablas["calendar_mensual"],
         tablas["calendar_semanal"]) = self.transformar_calendario(datos["calendar"])
        for nombre, tabla in tablas.items():
            self.log.info("Tabla lista para carga '%s': %d filas, %d columnas", nombre, *tabla.shape)
        return tablas
