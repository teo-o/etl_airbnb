# ETL Airbnb Bogotá — MongoDB → Python → SQLite / XLSX

Taller evaluativo 2 de **Inteligencia de Negocios**: proceso ETL automatizado en Python sobre los datasets de
[Inside Airbnb](https://insideairbnb.com/get-the-data/) para **Bogotá, Distrito Capital, Colombia**
(scrape del 21-jun-2026), con manejo de logs, análisis exploratorio y documentación del flujo.

## Objetivo

Aplicar Extracción, Transformación y Carga sobre los datos de Airbnb **almacenados en una base MongoDB local**:

1. **Extracción** (`src/extraccion.py`, clase `Extraccion`): se conecta a MongoDB, consulta las colecciones
   `Listings`, `Reviews` y `Calendar` y las carga en DataFrames de pandas.
2. **EDA** (`notebooks/exploracion_airbnb.ipynb`): estructura, calidad (nulos, duplicados, atípicos),
   posibles transformaciones y hallazgos, con gráficas interpretadas.
3. **Transformación** (`src/transformacion.py`, clase `Transformacion`): limpieza de nulos y duplicados,
   normalización de precios, fechas `YYYY-MM-DD`, variables derivadas de la fecha (año, mes, día, trimestre),
   categorías de precio, desanidado de `amenities`, del anfitrión y de `price_quote_raw`, y resúmenes del calendario.
4. **Carga** (`src/carga.py`, clase `Carga`): inserción en **SQLite**, exportación a **XLSX** y verificación
   de los registros cargados.
5. **Logs** (`src/logger.py`): un archivo por ejecución `logs/log_YYYYMMDD_HHMM.txt` con niveles
   INFO / WARNING / ERROR.

## Estructura

```
etl_airbnb/
├── data/raw/                  # listings.csv.gz, calendar.csv.gz, reviews.csv.gz (fuente para cargar MongoDB)
├── docker-compose.yml         # MongoDB 7 local en el puerto 27017
├── src/
│   ├── config.py              # URI de MongoDB, nombre de la base, rutas (configurables por variables de entorno)
│   ├── logger.py              # módulo centralizado de logs
│   ├── cargar_mongo.py        # carga inicial de los CSV.gz a MongoDB + validación
│   ├── extraccion.py          # clase Extraccion
│   ├── transformacion.py      # clase Transformacion
│   ├── carga.py               # clase Carga
│   └── main.py                # orquestador del ETL
├── notebooks/
│   └── exploracion_airbnb.ipynb
├── informe/
│   ├── generar_informe.py     # genera el informe PDF a partir de los resultados
│   ├── figuras/               # gráficas del EDA
│   └── Informe_ETL_Airbnb_Bogota.pdf
├── tests/                     # pruebas con pytest
├── logs/                      # un log por ejecución (se versiona log_ejemplo.txt)
├── output/                    # airbnb_bogota.db y archivos .xlsx (se generan al ejecutar)
├── requirements.txt
└── README.md
```

## Requisitos

- Python 3.11 o superior (probado con Python 3.14)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) para MongoDB. También sirve un MongoDB
  Community instalado localmente en `mongodb://localhost:27017`.
- Unos 4 GB de RAM libres, porque el calendario tiene 7 millones de registros.

## Instalación

```bash
# 1. Clonar el repositorio
git clone <url-del-repositorio> etl_airbnb
cd etl_airbnb

# 2. Crear y activar el entorno virtual
python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
#   Si PowerShell bloquea el script ("la ejecución de scripts está deshabilitada"),
#   habilítalo solo para la sesión actual y vuelve a activar:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
# Windows (CMD)
.venv\Scripts\activate.bat
# Linux / macOS
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt
```

## Ejecución

```bash
# 1. Levantar MongoDB local (Docker Desktop debe estar abierto)
docker compose up -d

# 2. Crear la base airbnb_bogota e importar las colecciones Listings, Reviews y Calendar (≈ 2-3 min)
python -m src.cargar_mongo

# 3. Ejecutar el proceso ETL completo: MongoDB -> transformación -> SQLite + XLSX (≈ 8-11 min)
python -m src.main
#    o solo SQLite, más rápido:
python -m src.main --sin-excel

# 4. (Opcional) Ejecutar el análisis exploratorio
jupyter notebook notebooks/exploracion_airbnb.ipynb

# 5. (Opcional) Regenerar el informe PDF (requiere los pasos 3 y 4)
python informe/generar_informe.py

# Pruebas
python -m pytest
```

Para usar otro servidor o base de MongoDB, se definen variables de entorno antes de ejecutar, por ejemplo
`MONGO_URI=mongodb://otro-host:27017` y `MONGO_DB=airbnb_bogota`.

### Resultados

| Archivo | Contenido |
|---|---|
| `output/airbnb_bogota.db` | SQLite con las tablas `listings`, `hosts`, `listing_amenities`, `reviews`, `calendar`, `calendar_mensual` y `calendar_semanal` |
| `output/airbnb_listings.xlsx` | Hojas `listings`, `hosts`, `listing_amenities` |
| `output/airbnb_reviews.xlsx` | Hoja `reviews` |
| `output/airbnb_calendario_resumen.xlsx` | Hojas `calendar_mensual` y `calendar_semanal`. El calendario diario (7 M filas) supera el límite de Excel y queda solo en SQLite |
| `output/resumen_transformaciones.json` | Filas antes y después de cada transformación |
| `output/reporte_verificacion.json` | Conteos esperados vs. SQLite vs. XLSX |
| `logs/log_YYYYMMDD_HHMM.txt` | Log de la ejecución |

## Ejemplo de ejecución del proceso ETL

```text
$ python -m src.main
2026-10-03 09:14:22 | INFO | etl.main | INICIO DEL PROCESO ETL - Airbnb Bogotá
2026-10-03 09:14:22 | INFO | etl.extraccion | Conexión establecida con MongoDB en mongodb://localhost:27017, base de datos 'airbnb_bogota'
2026-10-03 09:14:24 | INFO | etl.extraccion | Colección 'Listings': 19187 registros extraídos, 77 columnas (2.2 s)
2026-10-03 09:14:34 | INFO | etl.extraccion | Colección 'Reviews': 527731 registros extraídos, 6 columnas (9.3 s)
2026-10-03 09:16:02 | INFO | etl.extraccion | Colección 'Calendar': 7003255 registros extraídos, 5 columnas (88.3 s)
2026-10-03 09:16:06 | WARNING | etl.transformacion | 195 alojamientos sin precio publicado: se conservan con categoría 'Sin precio'
2026-10-03 09:16:10 | WARNING | etl.transformacion | [reviews] 191 reseñas sin comentario eliminadas
2026-10-03 09:17:15 | INFO | etl.main | Etapa de transformación finalizada en 71.9 s
2026-10-03 09:18:47 | INFO | etl.carga | SQLite: tabla 'calendar' cargada con 7003255 registros (82.4 s)
2026-10-03 09:24:17 | WARNING | etl.carga | XLSX: la tabla 'calendar' (7003255 filas) supera el límite de Excel (1048575); se omite del XLSX y queda completa en SQLite
2026-10-03 09:24:54 | INFO | etl.carga | Verificación OK 'listings': esperado=19187, SQLite=19187, XLSX=19187
...
2026-10-03 09:25:19 | INFO | etl.main | FIN DEL PROCESO ETL en 657.4 s. Tablas: 7, con diferencias: 0.
```

El log completo de esa ejecución está en [`logs/log_ejemplo.txt`](logs/log_ejemplo.txt).

## Integrantes y responsabilidades

| Integrante | Rol | Responsabilidades | Archivos principales |
|---|---|---|---|
| Mateo Orozco Oquendo | Coordinador | Estructura del proyecto, configuración, módulo de logs, MongoDB con Docker y carga inicial, orquestador del ETL, README, informe final y repositorio | `src/config.py`, `src/logger.py`, `src/cargar_mongo.py`, `docker-compose.yml`, `src/main.py`, `informe/generar_informe.py`, `README.md` |
| David Stiven Diaz | Extracción y carga | Clase `Extraccion` (conexión a MongoDB y extracción a DataFrames) y clase `Carga` (SQLite, XLSX y verificación) | `src/extraccion.py`, `src/carga.py` |
| Jhon Fredy Gomez | Transformación | Clase `Transformacion`: limpieza, normalización de precios y fechas, variables derivadas, categorías, desanidado y resúmenes del calendario | `src/transformacion.py` |
| Luis Alfredo Gomez | Análisis exploratorio | Notebook EDA: calidad de datos, atípicos, visualizaciones e interpretación de hallazgos | `notebooks/exploracion_airbnb.ipynb`, `informe/figuras/` |

Cada integrante subió su parte desde su propia cuenta de GitHub, como se ve en el historial de commits.

## Solución de problemas

- **`No fue posible conectarse a MongoDB`**: abrir Docker Desktop y ejecutar `docker compose up -d`.
  Verificar con `docker ps` que el contenedor `mongo_airbnb` esté arriba.
- **`La colección 'Listings' no existe`**: falta el paso 2 (`python -m src.cargar_mongo`).
- **`La carga a MongoDB se detuvo: FileNotFoundError`**: faltan los archivos `.csv.gz` en `data/raw/`.
- **`Activate.ps1 no se puede cargar`**: ejecutar `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
  en la misma ventana de PowerShell y volver a activar el entorno (o usar `activate.bat` desde CMD).
- **Falta memoria**: ejecutar `python -m src.main --sin-excel` y cerrar otras aplicaciones.
