# 📱 Market Scraping MX — Benchmarking de smartphones y dispositivos

Suite de scrapers para monitorear **precios, catálogo, inventario y promociones** de smartphones, tablets, audífonos, smartwatches y accesorios en retailers y operadoras de México.

El proyecto normaliza la información de distintas fuentes a esquemas comparables y genera archivos **CSV y Excel** para análisis de precios, benchmarking competitivo y seguimiento histórico.

> El repositorio está orientado a inteligencia competitiva: identificar qué productos están disponibles, en qué canal se venden, cuál es su precio regular, qué descuento tienen y cómo cambia su catálogo.

---

## 🎯 ¿Qué hace?

- Extrae catálogos desde páginas web y APIs de retailers y operadoras.
- Captura una fila por producto o SKU; en fuentes con variantes, conserva la combinación de capacidad y color.
- Normaliza marca, modelo, nombre, color, capacidad, SKU, URL, precios y porcentaje de descuento.
- Registra una fecha de consulta consistente para construir históricos.
- Deduplica productos por SKU o URL.
- Separa smartphones, tablets, audífonos, smartwatches, accesorios y otras categorías cuando la fuente lo permite.
- Exporta resultados individuales y archivos consolidados para análisis posterior.

---

## 🏪 Fuentes y scrapers

| Archivo | Fuente | Método | Cobertura |
|---|---|---|---|
| `ATT_Tienda_Online.ipynb` | AT&T México | API de Infonova mediante `requests` | Smartphones y accesorios; clasifica audífonos y smartwatches |
| `Elektra_API.ipynb` | Elektra | API VTEX ejecutada desde Chrome | Smartphones, audífonos y smartwatches vendidos por Elektra |
| `Telcel_3.ipynb` | Telcel | Selenium + BeautifulSoup | Teléfonos, tablets, accesorios y Vida Conectada |
| `Telcel 2.ipynb` | Telcel | Selenium + BeautifulSoup | Scraper base de teléfonos y capacidades |
| `Movistar.ipynb` | Movistar | Selenium + BeautifulSoup | Smartphones con paginación y deduplicación por SKU |
| `Liverpool.ipynb` | Liverpool | Selenium + BeautifulSoup | Catálogo de smartphones |
| `coppel2.ipynb` | Coppel | Selenium + BeautifulSoup | Smartphones y datos comerciales del catálogo |
| `Sears.ipynb` | Sears | Selenium + BeautifulSoup | Smartphones, wearables y campos `Store` / `Carrier` |
| `Suburbia.ipynb` | Suburbia | Selenium | Catálogo de productos con manejo de bloqueos |
| `mercado_libre_scraper.py` | Mercado Libre | Scrapling / `StealthyFetcher` | Tiendas oficiales de distintas marcas; exportación y consolidación |

### Cobertura especial

- **AT&T:** consulta directamente la API del catálogo, aplana variantes y usa `Categoria` para distinguir smartphones, accesorios, audífonos y smartwatches.
- **Elektra:** consulta la API VTEX filtrando `sellerId:1`, para conservar únicamente productos vendidos por Elektra y no por otros vendedores del marketplace.
- **Telcel:** recorre teléfonos y tablets por capacidad usando el filtro `Memoria`; accesorios y Vida Conectada se recorren mediante paginación simple. El notebook puede trabajar en paralelo con `ThreadPoolExecutor`.
- **Mercado Libre:** utiliza `Scrapling` con navegador stealth, soporte para Cloudflare, paginación configurable y consolidación diaria por SKU.

---

## 🧾 Esquema de salida

La mayoría de los scrapers generan columnas compatibles:

| Columna | Descripción |
|---|---|
| `Marca` | Marca normalizada del producto |
| `Modelo` | Modelo separado del nombre cuando la fuente lo permite |
| `Nombre` | Nombre publicado por la tienda |
| `Color` | Color detectado o leído desde la fuente |
| `Capacidad` | Almacenamiento, por ejemplo `128 GB`, `256 GB` o `1 TB` |
| `SKU` | Identificador del producto o de la variante |
| `URL` | Enlace al producto |
| `FechaConsulta` | Fecha y hora de extracción |
| `Precio_original` | Precio de lista o precio normal |
| `Precio_descuento` | Precio de oferta; `No discount` si no aplica |
| `Porcentaje_descuento` | Descuento publicado o calculado |
| `Categoria` | Categoría del producto cuando la fuente la proporciona |

Algunas fuentes agregan columnas propias, como `Store`, `Carrier` u otros campos comerciales.

### Valores especiales

- `No discount`: no se detectó una oferta válida.
- `No inventory`: el producto no tiene inventario o no tiene un precio disponible.
- `NA`: la categoría no utiliza capacidad, por ejemplo accesorios o wearables.

---

## 🛠️ Stack técnico

- **Python 3.9+** y **Jupyter Notebooks**
- **pandas** para transformación y exportación
- **Selenium** para sitios con contenido dinámico, paginación o protección anti-bot
- **BeautifulSoup** para parsing de HTML
- **requests** para consultas directas a APIs
- **Scrapling / StealthyFetcher** para Mercado Libre
- **openpyxl** para exportar archivos Excel
- **zoneinfo** para registrar la hora de Ciudad de México

---

## 🚀 Instalación

Se recomienda utilizar un entorno virtual:

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

Instala las dependencias principales:

```bash
pip install pandas requests beautifulsoup4 lxml selenium openpyxl
```

Para Mercado Libre:

```bash
pip install scrapling
scrapling install
```

Opcionalmente, para entornos corporativos con certificados SSL interceptados:

```bash
pip install truststore
```

Selenium necesita Chrome o Chromium. En versiones recientes de Selenium, Selenium Manager suele descargar y administrar el driver automáticamente.

---

## ▶️ Uso

### Notebooks

1. Abre el notebook de la fuente que quieras ejecutar.
2. Revisa las variables de configuración y las URLs objetivo.
3. Ejecuta las celdas en orden.
4. Verifica los archivos generados y las estadísticas finales.

Los notebooks suelen exportar resultados con fecha y, cuando corresponde, hora de ejecución. Algunos scrapers generan un CSV por capacidad o categoría y después consolidan la información en un archivo Excel.

### Mercado Libre

Ejecutar todas las marcas configuradas:

```bash
python mercado_libre_scraper.py
```

Ejecutar únicamente una marca:

```bash
python mercado_libre_scraper.py SAMSUNG
```

El script genera archivos diarios por marca y un consolidado como:

```text
mercadolibre_samsung_YYYY-MM-DD.csv
mercadolibre_consolidado_YYYY-MM-DD.csv
```

---

## 📂 Estructura actual

```text
.
├── ATT_Tienda_Online.ipynb
├── Elektra_API.ipynb
├── Liverpool.ipynb
├── Movistar.ipynb
├── Sears.ipynb
├── Suburbia.ipynb
├── Telcel 2.ipynb
├── Telcel_3.ipynb
├── coppel2.ipynb
├── mercado_libre_scraper.py
└── README.md
```

Los archivos CSV y Excel generados durante una corrida se consideran resultados de ejecución y no forman parte del código fuente del repositorio.

---

## ⚠️ Aviso legal y uso responsable

Este proyecto está destinado a análisis interno, investigación de mercado y fines educativos. Antes de utilizarlo:

- Respeta los Términos de Servicio y el `robots.txt` de cada sitio.
- Aplica límites de frecuencia y evita solicitudes innecesarias.
- No sobrecargues los servidores ni intentes evadir controles de acceso de forma indebida.
- Verifica que la recopilación y el uso de los datos cumplan con la legislación aplicable.
- No redistribuyas información personal ni datos protegidos por derechos de autor.

Los selectores, endpoints y estructuras de las tiendas pueden cambiar sin aviso. Por ello, un scraper puede requerir mantenimiento cuando la fuente actualice su frontend, API o mecanismos anti-bot.

---

## 🗺️ Próximos pasos

- [ ] Consolidar todas las fuentes en un esquema único multi-retailer.
- [ ] Añadir validaciones automáticas de columnas, precios, URLs e inventario.
- [ ] Centralizar funciones compartidas de normalización y cálculo de descuentos.
- [ ] Crear un histórico de precios con detección de cambios día a día.
- [ ] Automatizar ejecuciones con cron o GitHub Actions.
- [ ] Exportar resultados a una base de datos.
- [ ] Crear un dashboard de comparación por modelo, categoría y tienda.

---

## 📌 Estado del proyecto

Los scrapers se encuentran en evolución y se actualizan conforme cambian los catálogos y las estructuras de los sitios objetivo. Las salidas mostradas por los notebooks son ejemplos de ejecuciones y pueden variar con el tiempo.
