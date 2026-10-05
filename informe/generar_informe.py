"""Genera el informe final en PDF del taller (informe/Informe_ETL_Airbnb_Bogota.pdf).

El informe se arma con los resultados reales del proyecto:

* ``informe/metricas_eda.json`` y ``informe/figuras/*.png`` -> generados por el notebook EDA,
* ``output/resumen_transformaciones.json`` y ``output/reporte_verificacion.json`` -> generados por
  ``python -m src.main``,
* ``logs/log_ejemplo.txt`` -> log de una ejecución completa del ETL.

Uso (después de ejecutar el ETL y el notebook)::

    python informe/generar_informe.py
"""
import json
import re
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

RAIZ = Path(__file__).resolve().parent.parent
DIR_INFORME = RAIZ / "informe"
DIR_FIGURAS = DIR_INFORME / "figuras"
SALIDA_PDF = DIR_INFORME / "Informe_ETL_Airbnb_Bogota.pdf"
INTEGRANTES = [
    ("Mateo Orozco Oquendo", "Coordinación, estructura, logs, MongoDB, orquestador del ETL e informe"),
    ("David Stiven Diaz", "Extracción (clase Extraccion) y carga (clase Carga)"),
    ("Jhon Fredy Gomez", "Transformación (clase Transformacion)"),
    ("Luis Alfredo Gomez", "Análisis exploratorio de datos (notebook EDA)"),
]
REPOSITORIO = "https://github.com/teo-o/etl_airbnb"  # reemplazar por el enlace público

AZUL = colors.HexColor("#1f3b5c")
GRIS = colors.HexColor("#f2f4f7")

estilos = getSampleStyleSheet()
CUERPO = ParagraphStyle("cuerpo", parent=estilos["BodyText"], fontSize=10.5, leading=15, alignment=TA_JUSTIFY)
VINETA = ParagraphStyle("vineta", parent=CUERPO, leftIndent=14, bulletIndent=4)
H1 = ParagraphStyle("h1", parent=estilos["Heading1"], fontSize=16, textColor=AZUL, spaceBefore=6, spaceAfter=8)
H2 = ParagraphStyle("h2", parent=estilos["Heading2"], fontSize=12.5, textColor=AZUL, spaceBefore=8, spaceAfter=4)
PIE = ParagraphStyle("pie", parent=CUERPO, fontSize=8.5, leading=11, textColor=colors.HexColor("#555555"),
                     alignment=TA_CENTER)
CELDA = ParagraphStyle("celda", parent=CUERPO, fontSize=8.5, leading=10.5, alignment=0)
LOG = ParagraphStyle("log", fontName="Courier", fontSize=6.6, leading=8.4)


def num(x, decimales=0):
    """Formato numérico colombiano: 19.187 / 161.460 / 7,3."""
    texto = f"{x:,.{decimales}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def cop(x):
    return "$" + num(x)


def latin1(texto: str) -> str:
    """Las fuentes estándar del PDF usan Latin-1: se reemplazan los símbolos que no lo soportan."""
    reemplazos = {"≈": "aprox.", "→": "->", "≥": ">=", "≤": "<=", "–": "-", "—": "-", "“": '"', "”": '"',
                  "’": "'", "…": "...", "ρ": "rho"}
    for a, b in reemplazos.items():
        texto = texto.replace(a, b)
    return texto.encode("latin-1", "replace").decode("latin-1")


def p(texto, estilo=CUERPO):
    return Paragraph(latin1(texto), estilo)


def vinetas(items):
    return [Paragraph(latin1(t), VINETA, bulletText="•") for t in items]


def figura(nombre, ancho_cm, pie):
    ruta = DIR_FIGURAS / f"{nombre}.png"
    img = Image(str(ruta))
    escala = ancho_cm * cm / img.imageWidth
    img.drawWidth, img.drawHeight = img.imageWidth * escala, img.imageHeight * escala
    return KeepTogether([img, p(pie, PIE), Spacer(1, 8)])


def tabla(filas, anchos, encabezado=True):
    datos = [[p(str(c), CELDA) for c in fila] for fila in filas]
    t = Table(datos, colWidths=[a * cm for a in anchos], repeatRows=1 if encabezado else 0)
    estilo = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8ccd2")),
              ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS])]
    if encabezado:
        estilo += [("BACKGROUND", (0, 0), (-1, 0), AZUL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        datos[0] = [p(f"<b><font color='white'>{c}</font></b>", CELDA) for c in filas[0]]
        t = Table(datos, colWidths=[a * cm for a in anchos], repeatRows=1)
    t.setStyle(TableStyle(estilo))
    return t


def pie_pagina(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawString(2 * cm, 1.2 * cm, latin1("Proceso ETL - Airbnb Bogotá · Inteligencia de Negocios"))
    canvas.drawRightString(letter[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
    canvas.restoreState()


def extracto_log(ruta: Path, max_lineas: int = 48) -> str:
    """Selecciona las líneas más representativas del log: inicio, advertencias, carga y fin."""
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    # Solo la última ejecución completa del ETL (el archivo se abre en modo append)
    inicios = [i for i, l in enumerate(lineas) if "INICIO DEL PROCESO ETL" in l]
    if inicios:
        lineas = lineas[inicios[-1]:]
    claves = ("INICIO", "Conexión establecida", "registros extraídos", "WARNING", "ERROR",
              "Tratamiento de nulos", "Desanidado", "Resumen mensual", "SQLite: tabla", "XLSX:",
              "Verificación", "Etapa de", "FIN DEL PROCESO")
    elegidas = [l for l in lineas if any(c in l for c in claves)]
    if len(elegidas) > max_lineas:
        # se recorta el medio pero se conserva siempre la línea final del proceso
        elegidas = elegidas[:max_lineas - 1] + elegidas[-1:]
    # se acorta la ruta absoluta del log para que no ocupe dos líneas
    return "\n".join(re.sub(r"[A-Z]:\\.*\\(logs\\log_\d+_\d+\.txt)", r"\1", l) for l in elegidas)


def construir():
    m = json.loads((DIR_INFORME / "metricas_eda.json").read_text(encoding="utf-8"))
    resumen = json.loads((RAIZ / "output" / "resumen_transformaciones.json").read_text(encoding="utf-8"))
    verificacion = json.loads((RAIZ / "output" / "reporte_verificacion.json").read_text(encoding="utf-8"))
    reg, pr = m["registros"], m["precio"]
    rt = m["room_type"]
    dm = m["disponibilidad_mensual"]
    hosts = m["hosts"]
    rev_anio = {int(k): v for k, v in m["reviews_por_anio"].items()}

    h = []  # historia del documento

    # ------------------------------------------------------------- 1. Portada
    h += [Spacer(1, 3.2 * cm),
          p("<font size=11 color='#555555'>INTELIGENCIA DE NEGOCIOS</font>", ParagraphStyle("c", alignment=TA_CENTER)),
          Spacer(1, 1.2 * cm),
          p("<b>Taller evaluativo 2</b>", ParagraphStyle("t1", fontSize=24, leading=30, alignment=TA_CENTER, textColor=AZUL)),
          Spacer(1, 0.4 * cm),
          p("Proceso ETL con los datasets de Airbnb<br/>Bogotá, Distrito Capital, Colombia",
            ParagraphStyle("t2", fontSize=17, leading=23, alignment=TA_CENTER, textColor=AZUL)),
          Spacer(1, 0.8 * cm),
          p("MongoDB -> Python (pandas) -> SQLite / XLSX", ParagraphStyle("t3", fontSize=12, alignment=TA_CENTER,
                                                                          textColor=colors.HexColor("#555555"))),
          Spacer(1, 2.6 * cm),
          p("<b>Integrantes y responsabilidades</b>", ParagraphStyle("a", fontSize=12, leading=18, alignment=TA_CENTER)),
          Spacer(1, 0.2 * cm),
          tabla([["Integrante", "Responsabilidad"]] + [list(i) for i in INTEGRANTES], [5.2, 10.3]),
          Spacer(1, 0.8 * cm),
          p(f"<b>Repositorio:</b> {REPOSITORIO}", ParagraphStyle("a3", fontSize=10, alignment=TA_CENTER)),
          Spacer(1, 0.3 * cm),
          p(f"Octubre de {date.today().year}", ParagraphStyle("a4", fontSize=11, alignment=TA_CENTER)),
          PageBreak()]

    # --------------------------------------------------------- 2. Introducción
    h += [p("1. Introducción", H1),
          p("Este informe documenta la construcción de un proceso <b>ETL (Extracción, Transformación y Carga)</b> "
            "automatizado en Python sobre los datos públicos de <i>Inside Airbnb</i> para Bogotá. Los tres archivos "
            "fuente (<i>listings</i>, <i>calendar</i> y <i>reviews</i>) se cargaron primero en una base de datos "
            "<b>MongoDB local</b> (<font face='Courier'>airbnb_bogota</font>, ejecutada con Docker), que es la única "
            "fuente de datos del proceso. A partir de ella:"),
          *vinetas([
              "la clase <b>Extraccion</b> (<font face='Courier'>src/extraccion.py</font>) consulta las colecciones "
              "<i>Listings</i>, <i>Reviews</i> y <i>Calendar</i> y las convierte en DataFrames de pandas;",
              "un <b>análisis exploratorio</b> (<font face='Courier'>notebooks/exploracion_airbnb.ipynb</font>) "
              "evalúa estructura, calidad y distribución de los datos y justifica cada transformación;",
              "la clase <b>Transformacion</b> limpia, normaliza, desanida y resume los datos en siete tablas analíticas;",
              "la clase <b>Carga</b> inserta las tablas en <b>SQLite</b>, las exporta a <b>XLSX</b> y verifica los conteos;",
              "un módulo centralizado de <b>logs</b> registra cada ejecución en "
              "<font face='Courier'>logs/log_YYYYMMDD_HHMM.txt</font> con niveles INFO, WARNING y ERROR.",
          ]),
          p("El objetivo de negocio es dejar los datos listos para responder preguntas como: ¿cuánto cuesta una "
            "noche según el tipo de alojamiento y la localidad?, ¿qué tan profesionalizada está la oferta?, ¿cómo "
            "evoluciona la demanda? y ¿qué disponibilidad tiene la ciudad en los próximos meses?")]

    # ------------------------------------------------------ 3. Descripción dataset
    h += [p("2. Descripción del dataset", H1),
          p("Los datos corresponden al scrape de Inside Airbnb del <b>21 de junio de 2026</b> para Bogotá. "
            "Se importaron a MongoDB con <font face='Courier'>src/cargar_mongo.py</font>, que valida que la "
            "cantidad de documentos de cada colección coincida con las filas del archivo:"),
          tabla([["Colección", "Archivo fuente", "Documentos", "Campos", "Contenido"],
                 ["Listings", "listings.csv.gz", num(reg["listings"]), m["columnas"]["listings"],
                  "Un registro por alojamiento: anuncio, anfitrión, ubicación, capacidad, precio, "
                  "disponibilidad y calificaciones"],
                 ["Reviews", "reviews.csv.gz", num(reg["reviews"]), m["columnas"]["reviews"],
                  "Reseñas: alojamiento, fecha, revisor y comentario (2010-2026)"],
                 ["Calendar", "calendar.csv.gz", num(reg["calendar"]), m["columnas"]["calendar"],
                  "Disponibilidad diaria de cada alojamiento por 365 días (jun-2026 a jun-2027)"]],
                [2.2, 3.1, 2.2, 1.5, 8]),
          Spacer(1, 6),
          p(f"El archivo de alojamientos tiene 90 columnas, pero <b>13 llegan completamente vacías</b> en esta "
            f"versión (por ejemplo <i>host_since</i>, <i>host_response_rate</i>, <i>host_verifications</i> e "
            f"<i>instant_bookable</i>), por lo que MongoDB guarda {m['columnas']['listings']} campos. El calendario "
            "de esta versión <b>no incluye el precio diario</b>: solo indica si cada día está disponible y las "
            "noches mínimas y máximas. Todos los precios están en pesos colombianos (COP).")]

    # ---------------------------------------------------------------- 4. EDA
    h += [p("3. Resumen del análisis exploratorio", H1),
          p("<b>Estructura.</b> <i>Listings</i> mezcla información del anuncio, del anfitrión y de las reseñas en "
            "una sola tabla ancha. Varias columnas tienen tipos inadecuados: el precio es texto "
            "(<font face='Courier'>\"$284,294.01\"</font>), los booleanos vienen como 't'/'f', las fechas son "
            "cadenas y <i>amenities</i> y <i>price_quote_raw</i> son estructuras JSON anidadas guardadas como texto."),
          p("<b>Calidad.</b> Los hallazgos principales fueron:"),
          *vinetas([
              "<b>Nulos con significado:</b> el 22,2 % de los alojamientos no tiene reseñas, lo que explica los "
              "nulos simultáneos de <i>review_scores_*</i>, <i>first_review</i> y <i>reviews_per_month</i>. "
              "<i>bedrooms</i> tiene 15,4 % de nulos, <i>license</i> 15,3 % (sin Registro Nacional de Turismo) y "
              f"{num(pr['sin_precio'])} alojamientos no publican precio.",
              f"<b>Duplicados:</b> no se encontraron duplicados por clave (<i>id</i>, <i>id</i> de reseña, "
              "<i>listing_id + date</i>) ni por fila completa.",
              f"<b>Atípicos de precio:</b> la mediana es {cop(pr['mediana'])} por noche, pero la media es "
              f"{cop(pr['media'])} porque el máximo llega a {cop(pr['max'])}. Por IQR, {num(pr['atipicos_iqr'])} "
              f"alojamientos superan {cop(pr['limite_iqr'])}, y {pr['mayor_10M']} anuncios superan $10 millones "
              "por noche, lo que es claramente un error de carga del anfitrión.",
              f"<b>minimum_nights</b> no presenta valores extremos (máximo {num(m['minimum_nights']['max'])}), pero sí "
              f"tres modas: 1 noche ({num(m['minimum_nights']['1'])}), 2 noches y 30 noches "
              f"({num(m['minimum_nights']['30'])}), estas últimas de estancia mensual. <b>availability_365</b> "
              "está en su rango válido, pero concentrada en valores altos.",
              f"<b>Texto inconsistente:</b> 'Bogota, Colombia' ({num(m['texto']['bogota_sin_tilde'])}) y 'Bogotá, "
              f"Colombia' aparecen como lugares distintos, y {num(m['texto']['comentarios_br'])} comentarios "
              "contienen etiquetas HTML &lt;br/&gt;.",
          ]),
          figura("01_nulos_listings", 13, "Figura 1. Porcentaje de valores faltantes por columna en Listings."),
          figura("02_precio_outliers", 16, "Figura 2. Distribución del precio por noche (escala log) y boxplot: "
                                            "fuerte sesgo a la derecha y atípicos extremos."),
          figura("03_minimum_nights_availability", 16, "Figura 3. Noches mínimas (picos en 1, 2 y 30) y días "
                                                       "disponibles en el próximo año.")]

    # --------------------------------------------------- 5. Gráficas y hallazgos
    corr = m["corr_precio"]
    amen = m["top_amenities_pct"]
    h += [PageBreak(), p("4. Gráficas y hallazgos principales", H1),
          figura("04_room_type_precio", 16, "Figura 4. Cantidad de alojamientos y precio por noche según tipo."),
          p(f"<b>Tipo de alojamiento.</b> El {num(100 * rt['Entire home/apt']['n'] / reg['listings'], 1)} % de la "
            f"oferta son alojamientos completos, con mediana de {cop(rt['Entire home/apt']['mediana_precio'])}, "
            f"el doble que una habitación privada ({cop(rt['Private room']['mediana_precio'])}). Las habitaciones "
            "compartidas y de hotel son marginales."),
          figura("05_precio_localidad", 13.5, "Figura 5. Mediana del precio por noche por localidad."),
          p("<b>Localidad.</b> Chapinero y Usaquén concentran el 45 % de la oferta y tienen las medianas más altas "
            "(aprox. $199 mil y $194 mil): son las zonas de negocios, vida nocturna y embajadas del norte. El centro "
            "histórico (Santa Fe, La Candelaria) y Teusaquillo forman un segundo grupo, mientras que las localidades "
            "del sur y del occidente tienen poca oferta y medianas aprox. 45 % más bajas. El mapa (Figura 6) muestra "
            "la oferta concentrada en el corredor nororiental de la ciudad."),
          figura("06_mapa_precio", 9.5, "Figura 6. Ubicación de los alojamientos coloreada por precio (log)."),
          figura("07_correlaciones", 13.5, "Figura 7. Correlación de Spearman entre variables numéricas."),
          p(f"<b>Correlaciones.</b> El precio se asocia sobre todo con la capacidad (<i>accommodates</i> "
            f"rho={num(corr['accommodates'], 2)}, <i>beds</i> {num(corr['beds'], 2)}, <i>bathrooms</i> "
            f"{num(corr['bathrooms'], 2)}). La calificación casi no influye en el precio "
            f"(rho={num(corr['review_scores_rating'], 2)}) y las noches mínimas tienen una relación negativa débil "
            f"({num(corr['minimum_nights'], 2)}). El número de reseñas y la ocupación estimada están muy "
            "correlacionados (0,80), porque Inside Airbnb estima la ocupación a partir de las reseñas. Se usó Spearman "
            "porque los atípicos de precio distorsionarían la correlación de Pearson."),
          figura("08_top_amenities", 13, "Figura 8. Las 20 amenities más frecuentes."),
          p(f"<b>Amenities.</b> Wifi ({num(amen['Wifi'], 0)} %) y cocina ({num(amen['Kitchen'], 0)} %) son casi "
            f"universales. El espacio de trabajo ({num(amen['Dedicated workspace'], 0)} %) y la aceptación de "
            f"estancias largas ({num(amen['Long term stays allowed'], 0)} %) muestran una oferta orientada al "
            "trabajo remoto, coherente con el pico de 30 noches mínimas."),
          p(f"<b>Oferta profesionalizada.</b> {num(hosts['distintos'])} anfitriones administran los "
            f"{num(reg['listings'])} alojamientos. El {num(100 * hosts['con_uno'] / hosts['distintos'], 1)} % "
            f"tiene un solo anuncio, pero {num(hosts['alojamientos_hosts_10mas'])} alojamientos "
            f"({num(100 * hosts['alojamientos_hosts_10mas'] / reg['listings'], 1)} %) pertenecen a anfitriones "
            f"con 10 o más, y el mayor administra {hosts['max_alojamientos']}."),
          figura("09_reviews_por_anio", 15, "Figura 9. Reseñas por año (proxy de demanda)."),
          p(f"<b>Demanda.</b> Las reseñas cayeron 31 % en 2020 por la pandemia ({num(rev_anio[2020])} frente a "
            f"{num(rev_anio[2019])} en 2019) y desde entonces crecieron con fuerza: {num(rev_anio[2025])} en "
            f"2025, unas 10 veces más que en 2019. 2026 está incompleto (datos hasta el 21 de junio)."),
          figura("10_disponibilidad_mensual", 15, "Figura 10. Porcentaje de días disponibles por mes en el calendario."),
          p(f"<b>Disponibilidad futura.</b> En promedio el {num(m['disponibilidad_global'], 1)} % de los días futuros "
            f"está disponible. Los meses cercanos tienen menos disponibilidad (junio {num(dm['2026-06'], 0)} %, julio "
            f"{num(dm['2026-07'], 0)} %) porque acumulan reservas, mientras que de agosto a febrero ronda el 86-90 %. "
            "Por eso el indicador <i>tasa_no_disponible</i> es un proxy de ocupación (reservas más bloqueos del "
            "anfitrión) y no la ocupación real.")]

    # ------------------------------------------------------ 6. Transformaciones
    h += [PageBreak(), p("5. Descripción de las transformaciones realizadas", H1),
          p("Todas las transformaciones están implementadas y documentadas con docstrings en la clase "
            "<b>Transformacion</b> (<font face='Courier'>src/transformacion.py</font>), no en el notebook. Cada "
            "decisión responde a un hallazgo del EDA:"),
          tabla([["Hallazgo del EDA", "Transformación (método)", "Justificación"],
                 ["Precio como texto '$284,294.01'", "normalizar_precio",
                  "Se eliminan '$' y ',' y se convierte a float en COP para poder calcular."],
                 ["Precio sesgado con atípicos", "categorizar_precio, marcar_outliers_iqr",
                  "Rangos Económico (<100 mil), Medio (100-200 mil), Alto (200-400 mil), Lujo (>400 mil) y "
                  "'Sin precio'. Los atípicos se marcan con es_outlier_precio y no se borran, para no perder "
                  "alojamientos de lujo reales."],
                 ["Nulos con significado", "tratar_nulos_listings",
                  "Mediana por room_type en bedrooms, beds y bathrooms; reviews_per_month = 0; calificaciones nulas "
                  "+ flag tiene_reviews; license 'Sin registro' + tiene_licencia; textos 'Sin información'."],
                 ["Columnas 100 % vacías y URLs", "eliminar_columnas_sin_valor",
                  "No aportan información analítica."],
                 ["bathrooms incompleto", "convertir_banos",
                  "Se completa desde bathrooms_text (half-bath = 0,5) y se crea bano_compartido."],
                 ["amenities (lista JSON)", "desanidar_amenities",
                  "Tabla listing_amenities (listing_id, amenity) + cantidad_amenities en listings."],
                 ["price_quote_raw (JSON)", "desanidar_price_quote",
                  "Columnas cotizacion_moneda, _disponible, _descuento y _noches."],
                 ["Anfitrión repetido por alojamiento", "extraer_hosts",
                  "Dimensión hosts con un registro por host_id."],
                 ["Fechas como texto", "estandarizar_fechas, derivar_variables_fecha",
                  "Formato YYYY-MM-DD y variables anio, mes, dia, trimestre, nombre_mes, dia_semana."],
                 ["Calendario de 7 millones de filas", "transformar_calendario",
                  "calendar_mensual (por alojamiento y mes) y calendar_semanal (ciudad, semana ISO)."],
                 ["Texto inconsistente y HTML", "limpiar_texto",
                  "Quita &lt;br/&gt;, saltos de línea y espacios; barrios en formato título; 'Bogota' -> 'Bogotá'."],
                 ["Valores 't'/'f'", "convertir_booleanos", "Tipo booleano real."],
                 ["Duplicados (0 en esta versión)", "limpiar_duplicados",
                  "Control por clave natural; queda en el log como evidencia."]],
                [4.2, 4.3, 8.5]),
          Spacer(1, 8),
          p("<b>Registros antes y después de cada paso</b> (tomado de "
            "<font face='Courier'>output/resumen_transformaciones.json</font>, generado por el ETL):"),
          tabla([["Tabla", "Paso", "Antes", "Después"]] +
                [[r["tabla"], r["paso"], num(r["filas_antes"]), num(r["filas_despues"])] for r in resumen],
                [3.4, 8.6, 2.5, 2.5]),
          Spacer(1, 8),
          p("<b>Carga.</b> La clase <b>Carga</b> inserta las siete tablas en "
            "<font face='Courier'>output/airbnb_bogota.db</font> (SQLite, con índices por llave) y las exporta a "
            "tres archivos XLSX. El calendario diario supera el límite de 1.048.576 filas de Excel, así que en XLSX "
            "se exportan sus resúmenes y el detalle queda completo en SQLite, con un WARNING en el log. Al final, "
            "<i>verificar_carga</i> compara los registros esperados con los de SQLite y los de cada hoja de Excel:"),
          tabla([["Tabla", "Esperado", "SQLite", "XLSX", "Resultado"]] +
                [[t, num(r["esperado"]), num(r["sqlite"]), "no exportado" if r["xlsx"] is None else num(r["xlsx"]),
                  "OK" if r["ok"] else "ERROR"] for t, r in verificacion.items()],
                [4, 3, 3, 3, 2.5])]

    # ------------------------------------------------------------------ 7. Log
    h += [PageBreak(), p("6. Ejemplo del log generado", H1),
          p("Extracto de <font face='Courier'>logs/log_ejemplo.txt</font>, correspondiente a una ejecución completa de "
            "<font face='Courier'>python -m src.main</font>. Cada línea incluye fecha y hora, nivel, módulo y "
            "descripción del evento. Se muestran el inicio, la extracción, las advertencias, la carga y la "
            "verificación:"),
          Preformatted(latin1(extracto_log(RAIZ / "logs" / "log_ejemplo.txt")), LOG, maxLineLength=122,
                       newLineChars="    ")]

    # ---------------------------------------------------------- 8. Conclusiones
    h += [p("7. Conclusiones sobre la calidad y utilidad de los datos", H1),
          *vinetas([
              "<b>Calidad aceptable pero no lista para analizar.</b> Los datos no tienen duplicados y las claves son "
              "consistentes (todas las reseñas y los días del calendario corresponden a alojamientos existentes), "
              "pero necesitan conversión de tipos, desanidado y tratamiento de nulos antes de cualquier análisis.",
              "<b>El precio es la variable más delicada.</b> Hay errores evidentes del anfitrión (hasta $448 millones "
              "por noche) que distorsionan cualquier promedio. Por eso los análisis de precio deben usar la mediana, "
              "las categorías o excluir los alojamientos marcados con <i>es_outlier_precio</i>.",
              "<b>Hay limitaciones de origen.</b> Este scrape no trae el tiempo de respuesta del anfitrión, su "
              "antigüedad ni el precio diario del calendario, y la disponibilidad del calendario mezcla reservas "
              "con bloqueos. La ocupación es entonces una estimación y no un dato observado.",
              "<b>Los datos son útiles para el negocio.</b> Permiten segmentar el mercado por tipo, localidad y rango "
              "de precio, identificar la concentración de la oferta en Chapinero y Usaquén y en anfitriones "
              "profesionales, medir el crecimiento de la demanda después del COVID y analizar la estacionalidad "
              "con las variables de fecha derivadas.",
              "<b>Un proceso reproducible.</b> El ETL completo (aprox. 7,5 millones de registros) se ejecuta con un "
              "solo comando, deja trazabilidad en logs por ejecución y verifica automáticamente los conteos en "
              "SQLite y Excel. La base SQLite resultante puede migrarse a PostgreSQL o SQL Server para el proyecto final.",
          ])]

    # ------------------------------------------------------------ 9. Referencias
    h += [p("8. Referencias", H1),
          *vinetas([
              "Inside Airbnb. (2026). <i>Bogotá, Distrito Capital, Colombia - Detailed listings, calendar and reviews "
              "data</i> (scrape del 21 de junio de 2026). https://insideairbnb.com/get-the-data/",
              "Inside Airbnb. <i>Data dictionary</i>. https://insideairbnb.com/data-assumptions/",
              "The pandas development team. <i>pandas documentation</i>. https://pandas.pydata.org/docs/",
              "MongoDB, Inc. <i>PyMongo documentation</i>. https://pymongo.readthedocs.io/",
              "Python Software Foundation. <i>logging - Logging facility for Python</i>. "
              "https://docs.python.org/3/library/logging.html",
              "SQLite. <i>SQLite documentation</i>. https://www.sqlite.org/docs.html",
              "Waskom, M. (2021). seaborn: statistical data visualization. <i>Journal of Open Source Software</i>, 6(60), 3021.",
              "Kimball, R. y Ross, M. (2013). <i>The Data Warehouse Toolkit</i> (3.ª ed.). Wiley.",
          ])]

    doc = SimpleDocTemplate(str(SALIDA_PDF), pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm, title="Proceso ETL Airbnb Bogotá",
                            author=", ".join(n for n, _ in INTEGRANTES))
    doc.build(h, onLaterPages=pie_pagina)
    print(f"Informe generado: {SALIDA_PDF}")


if __name__ == "__main__":
    construir()
