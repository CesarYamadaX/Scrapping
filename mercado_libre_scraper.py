import re
import time
import unicodedata
from datetime import datetime
import pandas as pd
from scrapling.fetchers import StealthyFetcher

# ========================== AJUSTES GLOBALES ==============================
HEADLESS         = True   # False para ver el navegador
NETWORK_IDLE     = True
SOLVE_CLOUDFLARE = True
GOOGLE_SEARCH    = True
MAX_PAGES        = 20
WAIT_SELECTOR    = ".poly-card, .ui-search-result, .poly-component"
USER_DATA_DIR    = "scrapling_profile_ml"

# ========================== CONFIG DE MARCAS ==============================
BRANDS = {
    "SAMSUNG": {"urls": [
        "https://listado.mercadolibre.com.mx/tienda/samsung/_Container_ao-mobile-samsug#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D2%26applied_value_id%3D295%26applied_value_name%3DSamsung%26applied_value_order%3D18%26applied_value_results%3D4%26is_custom%3Dfalse%26view_more_flag%3Dtrue",
    ], "paginate": True},
    "APPLE": {"urls": [
        "https://listado.mercadolibre.com.mx/_Tienda_apple_af_to_Container_ao-mobile-apple_NoIndex_True",
        "https://listado.mercadolibre.com.mx/_Desde_49_Tienda_apple_af_to_Container_ao-mobile-apple_NoIndex_True",
        "https://listado.mercadolibre.com.mx/_Desde_97_Tienda_apple_af_to_Container_ao-mobile-apple_NoIndex_True",
        "https://listado.mercadolibre.com.mx/_Desde_145_Tienda_apple_af_to_Container_ao-mobile-apple_NoIndex_True",
    ], "paginate": False},
    "XIAOMI": {"urls": [
        "https://listado.mercadolibre.com.mx/tienda/poco/_Container_ao-mobile-xiaomi#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D3%26applied_value_id%3D3894%26applied_value_name%3DPOCO%26applied_value_order%3D10%26applied_value_results%3D6%26is_custom%3Dfalse",
        "https://listado.mercadolibre.com.mx/tienda/xiaomi/_Container_ao-mobile-xiaomi_NoIndex_True#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D3%26applied_value_id%3D573%26applied_value_name%3DXiaomi%26applied_value_order%3D14%26applied_value_results%3D1%26is_custom%3Dfalse%26view_more_flag%3Dtrue",
    ], "paginate": False},
    "NUBIA": {"urls": [
        "https://listado.mercadolibre.com.mx/_Tienda_nubia_af_to_Container_ao-mobile-zte#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D3%26applied_value_id%3D64116%26applied_value_name%3Dnubia%26applied_value_order%3D8%26applied_value_results%3D3%26is_custom%3Dfalse",
        "https://listado.mercadolibre.com.mx/_Tienda_nubia_af_to_Container_ao-mobile-nubia#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D1%26applied_value_id%3D64116%26applied_value_name%3Dnubia%26applied_value_order%3D2%26applied_value_results%3D7%26is_custom%3Dfalse",
    ], "paginate": False},
    "ONEPLUS": {"urls": [
        "https://listado.mercadolibre.com.mx/_Tienda_oneplus_af_to_Container_ao-mobile-oneplus_NoIndex_True#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D2%26applied_value_id%3D52307%26applied_value_name%3DONEPLUS%26applied_value_order%3D1%26applied_value_results%3D2%26is_custom%3Dfalse",
    ], "paginate": False},
    "CUBOT": {"urls": [
        "https://listado.mercadolibre.com.mx/_Tienda_cubot_af_to_Container_ao-mobile-cubot#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D4%26applied_value_id%3D5776%26applied_value_name%3DCUBOT%26applied_value_order%3D1%26applied_value_results%3D18%26is_custom%3Dfalse",
    ], "paginate": False},
    "INFINIX": {"urls": [
        "https://listado.mercadolibre.com.mx/_Tienda_infinix_af_to_Container_ao-mobile-infinix#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D2%26applied_value_id%3D6302%26applied_value_name%3DINFINIX%26applied_value_order%3D3%26applied_value_results%3D39%26is_custom%3Dfalse",
    ], "paginate": False},
    "HUAWEI": {"urls": [
        "https://listado.mercadolibre.com.mx/_Tienda_huawei_af_to_Container_ao-mobile-huawei#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D3%26applied_value_id%3D2591%26applied_value_name%3DHuawei%26applied_value_order%3D4%26applied_value_results%3D8%26is_custom%3Dfalse",
    ], "paginate": False},
    "MOTOROLA": {"urls": [
        "https://listado.mercadolibre.com.mx/tienda/motorola/_Container_ao-mobile-motorola#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D2%26applied_value_id%3D1466%26applied_value_name%3DMotorola%26applied_value_order%3D13%26applied_value_results%3D8%26is_custom%3Dfalse%26view_more_flag%3Dtrue",
    ], "paginate": True},
    "HONOR": {"urls": [
        "https://listado.mercadolibre.com.mx/tienda/honor/_Container_ao-mobile-honor#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D2%26applied_value_id%3D2853%26applied_value_name%3DHONOR%26applied_value_order%3D7%26applied_value_results%3D3%26is_custom%3Dfalse",
    ], "paginate": False},
    "OPPO": {"urls": [
        "https://listado.mercadolibre.com.mx/tienda/oppo/#global_position=1",
    ], "paginate": True},
    "ZTE": {"urls": [
        "https://listado.mercadolibre.com.mx/tienda/mercado-libre/_Container_ao-mobile-zte_NoIndex_True#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D3%26applied_value_id%3D4281%26applied_value_name%3DMercado+Libre%26applied_value_order%3D6%26applied_value_results%3D1%26is_custom%3Dfalse%26view_more_flag%3Dtrue",
        "https://listado.mercadolibre.com.mx/tienda/mercado-libre-electronica/_Container_ao-mobile-zte#applied_filter_id%3Dofficial_store%26applied_filter_name%3DTiendas+oficiales%26applied_filter_order%3D3%26applied_value_id%3D2856%26applied_value_name%3DMercado+Libre+Electronica%26applied_value_order%3D7%26applied_value_results%3D6%26is_custom%3Dfalse",
    ], "paginate": False},
}

# ========================== UTILIDADES ====================================
COLORES = [
    'titanio negro', 'titanio blanco', 'titanio del desierto', 'titanio natural',
    'negro', 'black', 'blanco', 'white', 'azul', 'blue', 'rojo', 'red',
    'verde', 'green', 'amarillo', 'yellow', 'rosa', 'pink', 'morado', 'purple', 'purpura',
    'gris', 'gray', 'grey', 'dorado', 'gold', 'plateado', 'silver', 'plata', 'cian',
    'lila', 'grafito', 'lavanda', 'ultramarino', 'medianoche', 'cafe',
    'menta', 'multicolor', 'beige', 'violeta', 'naranja', 'midnight', 'titanio', 'starlight',
    'phantom', 'cream', 'lavender', 'mint',
]

def _sin_acentos(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def _first(node, css):
    if node is None:
        return None
    found = node.css(css)
    return found[0] if found else None

def _txt(node, css):
    el = _first(node, css)
    if el is None:
        return ""
    try:
        return el.get_all_text(strip=True)
    except Exception:
        return (el.text or "").strip()

def _limpiar_precio(precio):
    if precio and precio not in ("No discount", "No inventory"):
        cleaned = re.sub(r'[^\d.]', '', precio.replace(',', ''))
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None

# ========================== EXTRACCION DE PRODUCTO ========================
def extraer_info_producto(product, marca, fecha_consulta):
    try:
        nombre = ""
        for sel in (".poly-component__title", ".ui-search-item__title",
                    ".ui-search-item__title-label", "h2.ui-search-item__title",
                    "a.ui-search-link", ".poly-box .poly-component__title"):
            nombre = _txt(product, sel)
            if nombre:
                break

        color = ""
        if nombre:
            nl = _sin_acentos(nombre.lower())
            for c in COLORES:
                if re.search(r'(?<![a-z])' + re.escape(c) + r'(?![a-z])', nl):
                    color = c.capitalize()
                    break

        capacidad = ""
        if nombre:
            m = re.search(r'(16|32|64|128|256|512|1)\s*(GB|TB)', nombre, re.IGNORECASE)
            if m:
                capacidad = f"{m.group(1)} {m.group(2).upper()}"

        url_producto = ""
        for sel in (".poly-component__title-wrapper a.poly-component__title",
                    "a.poly-component__title",
                    "a.poly-component__link.poly-component__link--carousel",
                    "a.poly-component__link", "a.ui-search-link",
                    "a.ui-search-item__group__element",
                    ".poly-component__title a", "h2.ui-search-item__title a"):
            link = _first(product, sel)
            if link is not None:
                href = link.attrib.get("href", "") or ""
                if href.startswith("http"):
                    url_producto = href
                    break
                elif href.startswith("/"):
                    url_producto = "https://www.mercadolibre.com.mx" + href
                    break

        sku = ""
        if url_producto:
            m = re.search(r'(MLM\d+)', url_producto)
            if m:
                sku = m.group(1)
        if not sku:
            sku = product.attrib.get("data-id") or product.attrib.get("data-item-id") or ""

        precio_original = precio_descuento = porcentaje_descuento = ""
        price_container = _first(product, ".poly-component__price")
        if price_container is not None:
            t = _txt(price_container, "s.andes-money-amount--previous .andes-money-amount__fraction")
            if t:
                precio_original = "$" + t
            t = _txt(price_container, ".poly-price__current .andes-money-amount__fraction")
            if t:
                precio_descuento = "$" + t
            t = _txt(price_container, ".andes-money-amount__discount")
            if t and "OFF" in t.upper():
                porcentaje_descuento = re.sub(r'(?i)off', '', t).strip()

        if not precio_original and not precio_descuento:
            for sel in (".andes-money-amount__fraction--previous",
                        ".ui-search-price__original-value",
                        ".price-tag-fraction--strikethrough",
                        ".ui-search-price__part--original"):
                t = _txt(product, sel)
                if t:
                    precio_original = "$" + t
                    break
            for sel in (".andes-money-amount__fraction", ".price-tag-fraction"):
                el = _first(product, sel)
                if el is not None:
                    parent = el.parent
                    pcls = str(parent.attrib.get("class", "")) if parent is not None else ""
                    if not any(k in pcls for k in ("previous", "strikethrough", "original")):
                        precio_descuento = "$" + el.get_all_text(strip=True)
                        break

        if not precio_original and precio_descuento:
            precio_original, precio_descuento = precio_descuento, "No discount"
        elif precio_original and not precio_descuento:
            precio_descuento = "No discount"
        elif not precio_original and not precio_descuento:
            precio_original, precio_descuento = "No inventory", "No discount"

        if not porcentaje_descuento:
            po, pd = _limpiar_precio(precio_original), _limpiar_precio(precio_descuento)
            porcentaje_descuento = (
                f"{round(100*(po-pd)/po, 2)}%" if (po and pd and po > pd) else "No discount"
            )

        return {
            "Marca": marca, "Nombre": nombre, "Color": color, "Capacidad": capacidad,
            "SKU": sku, "URL": url_producto, "FechaConsulta": fecha_consulta,
            "Precio_original": precio_original, "Precio_descuento": precio_descuento,
            "Porcentaje_descuento": porcentaje_descuento,
        }
    except Exception as e:
        print(f"  Error al extraer producto: {e}")
        return None

# ========================== FETCH =========================================
def fetch_page(url):
    return StealthyFetcher.fetch(
        url,
        headless=HEADLESS,
        network_idle=NETWORK_IDLE,
        solve_cloudflare=SOLVE_CLOUDFLARE,
        google_search=GOOGLE_SEARCH,
        wait_selector=WAIT_SELECTOR,
        wait_selector_state="visible",
        user_data_dir=USER_DATA_DIR,
        timeout=60000,
    )

def _buscar_productos(page):
    for sel in (".ui-search-result", ".ui-search-results__item",
                ".poly-card", ".poly-component", "div[data-item-id]"):
        prods = page.css(sel)
        if prods:
            return prods
    return page.css('div[class*="search-result"], div[class*="poly"]')

def _siguiente_url(page):
    for sel in (
        "li.andes-pagination__button--next:not(.andes-pagination__button--disabled) a",
        ".andes-pagination__button--next a.andes-pagination__link",
        "a[title='Siguiente']",
    ):
        found = page.css(sel)
        if found:
            href = found[0].attrib.get("href", "") or ""
            if href.startswith("http"):
                return href
    return None

# ========================== SCRAPER =======================================
def scrape_brand(marca, urls, paginate=True, max_pages=MAX_PAGES):
    print(f"\n=== Scrapeando {marca} ===")
    data, vistos = [], set()
    fecha_consulta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for seed in urls:
        url, pagina = seed, 1
        while url and pagina <= max_pages:
            try:
                page = fetch_page(url)
            except Exception as e:
                print(f"  Error al descargar pagina {pagina}: {e}")
                break

            status = getattr(page, "status", None)
            productos = _buscar_productos(page)
            print(f"  Pagina {pagina} (HTTP {status}): {len(productos)} productos")

            for p in productos:
                info = extraer_info_producto(p, marca, fecha_consulta)
                if info and (info["Nombre"] or info["URL"]):
                    clave = info["SKU"] or info["URL"] or info["Nombre"]
                    if clave not in vistos:
                        vistos.add(clave)
                        data.append(info)

            if not paginate:
                break
            nxt = _siguiente_url(page)
            if not nxt:
                break
            url, pagina = nxt, pagina + 1
            time.sleep(1)

    print(f"  -> {marca}: {len(data)} productos unicos")
    return data

def scrape_and_export(marca):
    cfg = BRANDS[marca]
    data = scrape_brand(marca, cfg["urls"], paginate=cfg.get("paginate", True))
    if data:
        df = pd.DataFrame(data)
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")
        nombre = f"mercadolibre_{marca.lower()}_{fecha_hoy}.csv"
        df.to_csv(nombre, index=False, encoding="utf-8-sig")
        print(f"  Guardado: {nombre}  ({len(df)} filas)")
        return df
    print(f"  Sin productos para {marca}.")
    return None

# ========================== CONSOLIDACION =================================
def consolidar():
    import glob, os
    fecha_hoy = datetime.now().strftime("%Y-%m-%d")
    archivos = glob.glob(f"mercadolibre_*_{fecha_hoy}.csv")
    if not archivos:
        print("No hay CSVs de hoy para consolidar.")
        return

    dfs = []
    for f in sorted(archivos):
        try:
            dfs.append(pd.read_csv(f, encoding="utf-8-sig"))
            print(f"  Leido: {f}")
        except Exception as e:
            print(f"  Error leyendo {f}: {e}")

    if not dfs:
        return

    df = pd.concat(dfs, ignore_index=True)
    if "SKU" in df.columns:
        antes = len(df)
        df = df.drop_duplicates(subset=["SKU"], keep="first")
        print(f"  Duplicados eliminados: {antes - len(df)}")

    df = df.sort_values(["Marca", "Nombre"], na_position="last")
    salida = f"mercadolibre_consolidado_{fecha_hoy}.csv"
    df.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"\nConsolidado guardado: {salida}  ({len(df)} productos)")

    if "Marca" in df.columns:
        print("\nProductos por marca:")
        for marca, n in df["Marca"].value_counts().items():
            print(f"  {marca}: {n}")

# ========================== MAIN ==========================================
if __name__ == "__main__":
    import sys

    # Si se pasa una marca como argumento, solo scrapea esa
    # Ejemplo: python mercado_libre_scraper.py SAMSUNG
    # Sin argumentos: scrapea todas las marcas
    marcas = sys.argv[1:] if len(sys.argv) > 1 else list(BRANDS.keys())

    print(f"Marcas a scrapear: {', '.join(marcas)}")
    for marca in marcas:
        if marca.upper() not in BRANDS:
            print(f"Marca desconocida: {marca}. Opciones: {', '.join(BRANDS.keys())}")
            continue
        scrape_and_export(marca.upper())

    print("\n=== Consolidando resultados del dia ===")
    consolidar()
    print("\nListo.")
