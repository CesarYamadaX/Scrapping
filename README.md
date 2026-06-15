# 📱 Market Scraping MX — Benchmarking de Smartphones

Suite de *web scrapers* para monitorear **precios, catálogo y promociones de smartphones** en los principales **retailers y operadoras de México**. Cada fuente se normaliza a un **esquema común** para poder consolidar todo en un solo dataset y comparar precios entre cadenas, modelos y marcas.

> Pensado para **inteligencia competitiva / benchmarking de pricing**: ver quién tiene cada modelo, a qué precio, con qué descuento y cómo cambia día a día.

---

## 🎯 ¿Qué hace?

- Recorre las páginas de celulares de cada tienda y extrae cada producto listado.
- Normaliza los campos clave (marca, modelo, capacidad, color, precio normal, precio de oferta, % de descuento, SKU, URL).
- Sella cada registro con la **fecha de consulta**, para construir histórico de precios.
- Exporta un **CSV por fuente**, listos para consolidar en un único archivo comparativo.

---

## 🏪 Fuentes cubiertas

| Notebook            | Fuente     | Tipo       | Dominio                   |
|---------------------|------------|------------|---------------------------|
| `Telcel 2.ipynb`    | Telcel     | Operadora  | telcel.com                |
| `Movistar.ipynb`    | Movistar   | Operadora  | tienda.movistar.com.mx    |
| `Liverpool.ipynb`   | Liverpool  | Retail     | liverpool.com.mx          |
| `coppel2.ipynb`     | Coppel     | Retail     | coppel.com                |
| `Sears.ipynb`       | Sears      | Retail     | sears.com.mx              |
| `Elektra.ipynb`     | Elektra    | Retail     | elektra.mx                |
| `Suburbia.ipynb`    | Suburbia   | Retail     | suburbia.com.mx           |

> 💡 La suite se complementa con un scraper de **Mercado Libre** (basado en *Scrapling/StealthyFetcher* para evadir bloqueo anti-bot), que sigue el mismo esquema de salida.

---

## 🏷️ Marcas monitoreadas

Samsung · Apple · Xiaomi / POCO · Honor · Motorola · Huawei · Oppo · Realme · Vivo · OnePlus · Nubia · ZTE · Infinix · Nokia · Cubot

*(varía según el catálogo disponible en cada tienda)*

---

## 🧾 Esquema de salida (CSV)

Todas las fuentes producen columnas estandarizadas para que sean consolidables:

| Columna                | Descripción                                                |
|------------------------|------------------------------------------------------------|
| `Marca`                | Marca del dispositivo                                      |
| `Nombre`               | Nombre del producto tal como aparece en la tienda          |
| `Modelo`               | Modelo homologado *(cuando la fuente lo permite)*          |
| `Color`                | Color detectado a partir del nombre                        |
| `Capacidad`            | Almacenamiento (p. ej. `128 GB`, `256 GB`, `1 TB`)         |
| `SKU`                  | Identificador del producto en la tienda                    |
| `URL`                  | Enlace directo al producto                                 |
| `Precio_original`      | Precio de lista / normal                                   |
| `Precio_descuento`     | Precio con oferta (o `No discount` si no aplica)           |
| `Porcentaje_descuento` | Descuento calculado o publicado                            |
| `FechaConsulta`        | Timestamp de la extracción (para histórico)                |

> Algunas fuentes agregan campos propios como `Tienda` (Sears) o `Carrier` (Coppel).

---

## 🛠️ Stack técnico

- **Python** + **Jupyter Notebooks**
- **Selenium** (navegación dinámica de sitios que cargan contenido por JS)
- **BeautifulSoup** (parsing del HTML)
- **pandas** (estructuración y exportación a CSV)
- **Scrapling / StealthyFetcher** (en el scraper de Mercado Libre, para sitios con anti-bot)

---

## 📂 Estructura del repositorio

```
.
├── Telcel 2.ipynb        # Operadora Telcel
├── Movistar.ipynb        # Operadora Movistar
├── Liverpool.ipynb       # Retail Liverpool
├── coppel2.ipynb         # Retail Coppel
├── Sears.ipynb           # Retail Sears
├── Elektra.ipynb         # Retail Elektra
├── Suburbia.ipynb        # Retail Suburbia
└── README.md
```

---

## 🚀 Requisitos e instalación

```bash
# Dependencias base
pip install selenium beautifulsoup4 pandas lxml

# Para el scraper de Mercado Libre (anti-bot)
pip install scrapling
scrapling install        # descarga el navegador stealth (primera vez)
```

Selenium requiere un **navegador (Chrome)** y su *driver* compatible. Con Selenium ≥ 4.6 el driver se gestiona automáticamente vía Selenium Manager; si no, instala `webdriver-manager`.

---

## ▶️ Uso

1. Abre el notebook de la fuente que quieras (p. ej. `Liverpool.ipynb`).
2. Ejecuta las celdas en orden.
3. Al terminar, se genera un CSV con la fecha del día (p. ej. `liverpool_2026-06-15.csv`).
4. Repite por cada fuente y **consolida** los CSV del día en un único archivo comparativo.

> ⚙️ La mayoría de los notebooks corren en modo *headless*. Si una fuente pide verificación o deja de devolver productos, ejecútala con el navegador visible para inspeccionar.

---

## ⚠️ Aviso legal y de uso responsable

Este proyecto es para **fines de análisis interno, investigación de mercado y educativos**. Antes de usarlo:

- Respeta los **Términos de Servicio** y el `robots.txt` de cada sitio.
- Aplica *rate limiting* y evita cargas que afecten el funcionamiento de los servidores.
- No redistribuyas datos protegidos por derechos de autor ni de carácter personal.

El mantenedor no se hace responsable del uso indebido de estas herramientas. Los selectores dependen del HTML de cada sitio y **pueden romperse** cuando las tiendas actualizan su frontend; requieren mantenimiento periódico.

---

## 🗺️ Roadmap (ideas)

- [ ] Consolidador único multi-fuente con deduplicado por SKU.
- [ ] Migrar las fuentes con bloqueo a Scrapling para mayor robustez.
- [ ] Histórico de precios + detección de cambios día a día.
- [ ] Programación automática (cron / GitHub Actions) y export a base de datos.
- [ ] Dashboard de comparación de precios por modelo y tienda.
