"""
att_scraper.py — Scraper de AT&T México (https://www.att.com.mx/cotizar-celulares/)
v2 — ajustado a la estructura real del cotizador (React + HeroUI)

Parte de la suite Market Scraping MX. Esquema común del repo:
    Marca | Modelo | Nombre | Color | Capacidad | SKU | URL |
    FechaConsulta | Precio_original | Precio_descuento | Porcentaje_descuento
Columnas propias de la fuente (como 'Tienda' en Sears o 'Carrier' en Coppel):
    Modalidad  -> plan de datos cotizado (p.ej. 'AT&T Prepago')
    Plazo      -> meses de servicio ('N/A' en prepago)

--------------------------------------------------------------------------------
CÓMO ESTÁ CONSTRUIDA LA PÁGINA (lo que dicta el parser)
--------------------------------------------------------------------------------
Cada resultado es una FILA (no una card) con esta forma:

    <div class="col-span-12 grid grid-cols-12 ... border-b last:border-b-0">
      <h1 ...>A79 5G</h1>                          <- nombre, SIN marca
      <div class="... lg:col-span-4 ...">Capacidad
          <select><option value="256 GB">256 GB</option></select>   <- variantes
          <span data-slot="value">256 GB</span>                     <- seleccionado
      </div>
      <div ...>Color             ... NEGRO / MORADO ...</div>
      <div ...>Meses de servicio ... N/A ...</div>
      <div ...>Plan de datos     ... AT&T Prepago ...</div>
      <div ...>Precio del dispositivo
          <span id="pago-mensual-print-249">$7,499.01</span>        <- ancla
      </div>
    </div>

Decisiones de parsing derivadas de eso:

  * OJO: la página abre con un MODAL ('Continuar' / 'Saltar') que bloquea el
    montaje del cotizador. Mientras esté ahí no existe ni un solo
    button[data-slot="trigger"] y todo sale en cero. Hay que cerrarlo primero.
  * ANCLA = span[id^="pago-mensual-print"]. Es el elemento más estable de la fila;
    desde ahí subimos al contenedor. No dependemos de clases de Tailwind, que
    cambian en cada build.
  * Los campos se leen POR ETIQUETA ('Capacidad', 'Color', 'Plan de datos'...),
    no por posición ni por clase. Si AT&T reordena columnas, sigue jalando.
  * El <h1> NO trae marca ('A79 5G' es un Oppo). La marca se arrastra del filtro
    seleccionado; si no hay contexto, se infiere del nombre como último recurso.
  * No hay URL por producto (la navegación es por JS), así que URL = el cotizador.
  * Solo se publica un precio -> Precio_descuento = 'No discount' salvo que
    aparezca un tachado. Se conserva la convención del repo.
  * El sufijo del id ('249') se guarda como SKU, PERO puede ser un índice de fila
    y no un identificador de catálogo -> el dedupe NO se apoya en él, sino en
    Nombre + Capacidad + Color + Modalidad + Plazo.

--------------------------------------------------------------------------------
USO
--------------------------------------------------------------------------------
    pip install selenium beautifulsoup4 pandas lxml openpyxl

    # 1a corrida: con ventana + debug, para ver los controles reales de la página
    python att_scraper.py --no-headless --debug --inspeccionar

    # corrida normal (recorre todas las marcas)
    python att_scraper.py

    # solo algunas marcas
    python att_scraper.py --marcas HONOR SAMSUNG APPLE

    # además itera capacidad x color dentro de cada fila (más lento, más filas)
    python att_scraper.py --variantes
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    from zoneinfo import ZoneInfo  # py3.9+
    TZ_CDMX = ZoneInfo("America/Mexico_City")
except Exception:  # pragma: no cover
    TZ_CDMX = None


# ==============================================================================
# CONFIGURACIÓN
# ==============================================================================

BASE_URL = "https://www.att.com.mx"
URL_COTIZADOR = "https://www.att.com.mx/cotizar-celulares/"

SCHEMA = [
    "Marca", "Modelo", "Nombre", "Color", "Capacidad", "SKU", "URL",
    "FechaConsulta", "Precio_original", "Precio_descuento", "Porcentaje_descuento",
    "Modalidad", "Plazo",
]

FECHA_CORRIDA = (
    datetime.now(TZ_CDMX) if TZ_CDMX is not None else datetime.now()
).strftime("%Y-%m-%d %H:%M:%S")

DEBUG_DIR = "_att_debug"

# Ancla de fila: el span del precio. Todo lo demás se resuelve subiendo desde aquí.
ANCLA_PRECIO = 'span[id^="pago-mensual-print"]'

# Etiquetas de campo tal cual aparecen en la fila
ETIQ_CAPACIDAD = "capacidad"
ETIQ_COLOR = "color"
ETIQ_PLAZO = "meses de servicio"
ETIQ_PLAN = "plan de datos"
ETIQ_PRECIO = "precio del dispositivo"

# Etiquetas candidatas para los filtros superiores (marca / equipo)
ARIA_MARCA = ("seleccionar marca", "marca", "brand", "fabricante")
ARIA_MODELO = ("modelo", "equipo", "dispositivo", "celular")
ARIA_PLAN = ("plan de datos", "plan", "tarifa")

# --- Flujo del cotizador ---------------------------------------------------
# El panel de filtros NO se aplica solo: hay que elegir plan, marcar la marca y
# darle 'Ver resultados'. 'Regresar' vuelve al panel para la siguiente marca.
TEXTO_PLAN_DEFAULT = "AT&T Prepago"
TEXTO_CONTINUAR = "Continuar"
TEXTO_VER_RESULTADOS = "Ver resultados"
TEXTO_LIMPIAR = "Limpiar filtros"
TEXTO_REGRESAR = "Regresar"

MARCAS_CONOCIDAS = {
    "iphone": "APPLE", "apple": "APPLE", "ipad": "APPLE",
    "samsung": "SAMSUNG", "galaxy": "SAMSUNG",
    "xiaomi": "XIAOMI", "redmi": "XIAOMI", "poco": "XIAOMI",
    "honor": "HONOR", "huawei": "HUAWEI",
    "motorola": "MOTOROLA", "moto": "MOTOROLA",
    "oppo": "OPPO", "realme": "REALME", "vivo": "VIVO",
    "oneplus": "ONEPLUS", "nubia": "NUBIA", "zte": "ZTE",
    "infinix": "INFINIX", "tecno": "TECNO", "nokia": "NOKIA",
    "cubot": "CUBOT", "google": "GOOGLE", "pixel": "GOOGLE",
    "nothing": "NOTHING", "tcl": "TCL", "alcatel": "ALCATEL",
    "lanix": "LANIX", "hisense": "HISENSE", "at&t": "AT&T",
}

COLORES = [
    "negro", "black", "blanco", "white", "azul", "blue", "rojo", "red", "verde",
    "green", "amarillo", "yellow", "rosa", "pink", "morado", "purple", "gris",
    "gray", "grey", "dorado", "gold", "plateado", "silver", "plata", "violeta",
    "naranja", "orange", "celeste", "turquesa", "midnight", "starlight", "titanio",
    "titanium", "cyan", "café", "lila", "beige", "coral", "lavanda", "crema",
    "bronce", "arena", "menta", "grafito", "graphite", "marino", "obsidiana",
    "esmeralda", "aqua", "natural", "cosmic",
]


# ==============================================================================
# HELPERS DE NORMALIZACIÓN (mismos criterios que Telcel / Movistar / Coppel)
# ==============================================================================

def limpiar_precio(valor) -> str:
    """'$7,499.01' -> '7499.01'. Devuelve '' si no hay número."""
    if valor is None or valor == "":
        return ""
    if isinstance(valor, (int, float)):
        return f"{float(valor):.2f}"
    txt = str(valor).replace("MXN", "").replace("$", "").strip()
    txt = re.sub(r"[^\d,.\-]", "", txt).replace(",", "")
    m = re.search(r"\d+(?:\.\d+)?", txt)
    return m.group(0) if m else ""


def _a_float(precio: str):
    try:
        return float(precio) if precio not in ("", "No discount", "No inventory", None) else None
    except (TypeError, ValueError):
        return None


def resolver_precios(precio_lista, precio_oferta, descuento_publicado=""):
    """Misma lógica de negocio que el resto del repo."""
    p_ori = limpiar_precio(precio_lista)
    p_desc = limpiar_precio(precio_oferta)

    if not p_ori and p_desc:
        p_ori, p_desc = p_desc, "No discount"
    elif p_ori and not p_desc:
        p_desc = "No discount"
    elif not p_ori and not p_desc:
        p_ori, p_desc = "No inventory", "No discount"

    f_ori, f_desc = _a_float(p_ori), _a_float(p_desc)
    if f_ori is not None and f_desc is not None and f_desc >= f_ori:
        p_desc, f_desc = "No discount", None

    porcentaje = "No discount"
    pub = limpiar_precio(descuento_publicado)
    if f_ori and f_desc and f_ori > f_desc:
        porcentaje = f"{round(100 * (f_ori - f_desc) / f_ori, 2)}%"
    elif pub:
        try:
            v = float(pub)
            if 0 < v <= 100:
                porcentaje = f"{round(v, 2)}%"
        except ValueError:
            pass
    return p_ori, p_desc, porcentaje


def detectar_marca(texto: str, marca_contexto: str = "") -> str:
    """La marca del filtro manda; el <h1> casi nunca la trae."""
    if marca_contexto:
        m = str(marca_contexto).strip()
        return MARCAS_CONOCIDAS.get(m.lower(), m.upper())
    t = str(texto).lower()
    for clave, marca in MARCAS_CONOCIDAS.items():
        if clave in t:
            return marca
    return ""


def detectar_color(texto: str, color_declarado: str = "") -> str:
    if color_declarado:
        return str(color_declarado).strip().capitalize()
    t = str(texto).lower()
    for c in sorted(COLORES, key=len, reverse=True):  # evita 'Ultramarino' -> 'Marino'
        if re.search(rf"(?<![a-záéíóúñ]){re.escape(c)}(?![a-záéíóúñ])", t):
            return c.capitalize()
    return ""


def detectar_capacidad(texto: str, capacidad_declarada: str = "") -> str:
    fuente = str(capacidad_declarada) if capacidad_declarada else str(texto)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(GB|TB|MB)", fuente, re.IGNORECASE)
    return f"{m.group(1)} {m.group(2).upper()}" if m else ""


def construir_modelo(nombre: str, marca: str) -> str:
    """El <h1> ya es prácticamente el modelo; solo se limpia marca/capacidad."""
    limpio = str(nombre)
    if marca:
        limpio = re.sub(rf"\b{re.escape(marca)}\b", "", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"\d+(?:\.\d+)?\s*(GB|TB|MB)", "", limpio, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", limpio).strip(" -|,")


# ==============================================================================
# PARSER DE FILA — anclado a span[id^="pago-mensual-print"]
# ==============================================================================

def _contenedor_de_fila(span_precio):
    """
    Sube desde el span del precio hasta el contenedor de la fila.
    La fila es el primer ancestro que además contiene el <h1> del equipo.
    """
    nodo = span_precio
    for _ in range(8):
        nodo = nodo.parent
        if nodo is None:
            return None
        if nodo.find("h1"):
            return nodo
    return None


def _campos_por_etiqueta(fila) -> dict:
    """
    Devuelve {etiqueta_en_minusculas: {'valor': str, 'opciones': [str, ...]}}.
    La etiqueta es el primer nodo de texto DIRECTO del div del campo;
    el valor seleccionado vive en span[data-slot="value"].
    """
    campos = {}
    for div in fila.find_all("div"):
        etiqueta = None
        for hijo in div.children:
            if isinstance(hijo, str) and hijo.strip():
                etiqueta = hijo.strip()
                break
        if not etiqueta or len(etiqueta) > 40:
            continue

        span_val = div.select_one('span[data-slot="value"]')
        if span_val is not None:
            valor = span_val.get_text(strip=True)
        else:
            spans = div.find_all("span")
            valor = spans[-1].get_text(strip=True) if spans else ""

        opciones = [
            (o.get_text(strip=True) or o.get("value", ""))
            for o in div.find_all("option")
            if (o.get_text(strip=True) or o.get("value"))
        ]

        clave = etiqueta.lower()
        if clave not in campos:
            campos[clave] = {"valor": valor, "opciones": opciones}
    return campos


def parsear_fila(fila, marca_contexto: str = ""):
    h1 = fila.find("h1")
    if not h1:
        return None
    nombre = h1.get_text(strip=True)
    if not nombre or len(nombre) < 2:
        return None

    campos = _campos_por_etiqueta(fila)

    def val(etiqueta: str) -> str:
        for k, v in campos.items():
            if etiqueta in k:
                return v["valor"]
        return ""

    capacidad_raw = val(ETIQ_CAPACIDAD)
    color_raw = val(ETIQ_COLOR)
    plan = val(ETIQ_PLAN)
    plazo = val(ETIQ_PLAZO)

    # Precio: preferimos el ancla; si no, el campo por etiqueta
    span_precio = fila.select_one(ANCLA_PRECIO)
    precio_txt = span_precio.get_text(strip=True) if span_precio else val(ETIQ_PRECIO)

    # SKU = sufijo numérico del id del ancla (ojo: puede ser índice de fila)
    sku = ""
    if span_precio and span_precio.get("id"):
        m = re.search(r"(\d+)$", span_precio["id"])
        if m:
            sku = m.group(1)

    # ¿Hay precio tachado? (por si AT&T publica promoción)
    # OJO: el <s> suele vivir DENTRO del span ancla, así que get_text() concatena
    # ambos importes ('$11,999.00$9,499.00'). Hay que restar el tachado del total.
    precio_lista, precio_vigente = "", precio_txt
    tachado = fila.select_one("[class*='line-through'], s, del")
    if tachado:
        precio_lista = tachado.get_text(strip=True)
        resto = precio_txt.replace(precio_lista, "").strip()
        if not limpiar_precio(resto):
            # el tachado estaba fuera del ancla: el ancla ya es el precio vigente
            resto = precio_txt if precio_txt != precio_lista else ""
        precio_vigente = resto

    p_ori, p_desc, porcentaje = resolver_precios(
        precio_lista or precio_vigente,
        precio_vigente if precio_lista else "",
    )

    marca = detectar_marca(nombre, marca_contexto)
    return {
        "Marca": marca,
        "Modelo": construir_modelo(nombre, marca),
        "Nombre": nombre,
        "Color": detectar_color(nombre, color_raw),
        "Capacidad": detectar_capacidad(nombre, capacidad_raw),
        "SKU": sku,
        "URL": URL_COTIZADOR,
        "FechaConsulta": FECHA_CORRIDA,
        "Precio_original": p_ori,
        "Precio_descuento": p_desc,
        "Porcentaje_descuento": porcentaje,
        "Modalidad": plan or "Cotizador",
        "Plazo": plazo or "",
    }


def parsear_pagina(html: str, marca_contexto: str = "") -> list:
    soup = BeautifulSoup(html, "html.parser")
    filas, vistos = [], set()
    for span in soup.select(ANCLA_PRECIO):
        cont = _contenedor_de_fila(span)
        if cont is None or id(cont) in vistos:
            continue
        vistos.add(id(cont))
        info = parsear_fila(cont, marca_contexto)
        if info:
            filas.append(info)
    return filas


# ==============================================================================
# INTERACCIÓN CON LOS SELECTS DE HEROUI
# ==============================================================================
# HeroUI no usa <select> nativo visible: el <select> del DOM está oculto y solo
# sirve para accesibilidad. Cambiarlo por JS NO dispara el estado de React.
# Hay que hacer click en el trigger y luego en la opción del listbox (portal).

# Textos de botones que hay que despachar ANTES de poder ver el cotizador.
# La página abre con un modal ('Continuar' / 'Saltar') que bloquea el montaje
# del contenido: mientras esté ahí no existe ningún button[data-slot="trigger"].
# 'Saltar' va primero a propósito — 'Continuar' avanza un flujo, no lo omite.
# 'Continuar' queda FUERA del default a propósito: avanza el wizard en vez de
# omitirlo. Se puede reactivar con --saltar si algún día hace falta.
TEXTOS_DESCARTE = ("Saltar", "Omitir", "Cerrar", "Entendido", "Aceptar")


def descartar_overlays(driver, textos=None, intentos: int = 3,
                       max_cierres: int = 1) -> int:
    """Cierra modales / banners que tapan el cotizador. Devuelve cuántos cerró."""
    textos = textos or TEXTOS_DESCARTE
    cerrados = 0
    for _ in range(intentos):
        clicado = False
        for texto in textos:
            try:
                els = driver.find_elements(
                    By.XPATH,
                    "//*[self::button or self::a]"
                    f"[contains(normalize-space(.), '{texto}')]",
                )
            except Exception:
                continue
            for el in els:
                try:
                    if not (el.is_displayed() and el.is_enabled()):
                        continue
                    if len(el.text.strip()) > 25:  # evita links largos del footer
                        continue
                    etiqueta = el.text.strip()
                    if not _click(driver, el, espera=3):
                        continue
                    print(f"  Overlay descartado con '{etiqueta}'")
                    cerrados += 1
                    clicado = True
                    time.sleep(3)
                    break
                except Exception:
                    continue
            if clicado:
                break
        if not clicado or cerrados >= max_cierres:
            break
    return cerrados



def esperar_cotizador(driver, timeout: int = 45) -> bool:
    """
    Espera a que React monte el cotizador. Damos por hidratado cuando aparece
    algún select de HeroUI o alguna fila de resultados.
    """
    limite = time.time() + timeout
    while time.time() < limite:
        try:
            if driver.find_elements(By.CSS_SELECTOR, 'button[data-slot="trigger"][aria-label]'):
                return True
            if driver.find_elements(By.CSS_SELECTOR, ANCLA_PRECIO):
                return True
        except Exception:
            pass
        # el modal puede reaparecer tras una redirección
        descartar_overlays(driver, intentos=1)
        time.sleep(2)
    return False


def construir_driver(headless: bool = True, con_logs: bool = False) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=es-MX")
    # Corrida en un host con poca RAM libre: recortamos todo lo que no haga falta
    # para leer precios. Sin imágenes (los logos/fotos no aportan) baja mucho el
    # consumo; sin caché en disco ni procesos extra se evita que Chrome se muera
    # con InvalidSessionId a mitad de la paginación.
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-application-cache")
    options.add_argument("--disk-cache-size=1")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--js-flags=--max-old-space-size=512")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # El log de red 'performance' se acumula en memoria y NUNCA se drena salvo en
    # modo debug (capturar_json). En una corrida larga (muchas páginas x marcas)
    # ese buffer crecía sin tope y terminaba matando a Chrome con
    # InvalidSessionIdException. Solo se activa cuando de verdad se va a leer.
    if con_logs:
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver


def _triggers(driver, raiz=None) -> list:
    ctx = raiz if raiz is not None else driver
    return ctx.find_elements(By.CSS_SELECTOR, 'button[data-slot="trigger"][aria-label]')


def buscar_trigger(driver, etiquetas: tuple):
    """Encuentra el botón de un select por su aria-label (coincidencia flexible)."""
    for btn in _triggers(driver):
        try:
            aria = (btn.get_attribute("aria-label") or "").lower()
        except Exception:
            continue
        if any(e in aria for e in etiquetas):
            return btn
    return None


def _click(driver, el, espera: float = 0.0) -> bool:
    """
    Click que React Aria SÍ registra.

    Los controles traen data-react-aria-pressable: usePress escucha
    pointerdown/pointerup, no 'click'. Un execute_script('...click()') dispara
    un click sintético que esos handlers ignoran — por eso los dropdowns
    abrían de forma intermitente. Orden: nativo -> ActionChains -> JS.
    """
    if el is None:
        return False
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center', behavior:'instant'});", el
        )
        time.sleep(0.3)
    except Exception:
        pass

    for intento in ("pointer", "nativo", "actions", "js"):
        try:
            if intento == "pointer":
                driver.execute_script(_JS_PRESS, el)
            elif intento == "nativo":
                el.click()
            elif intento == "actions":
                webdriver.ActionChains(driver).move_to_element(el).pause(0.2).click().perform()
            else:
                driver.execute_script("arguments[0].click();", el)
            if espera:
                time.sleep(espera)
            return True
        except Exception:
            continue
    return False


# React Aria (usePress) escucha pointerdown/pointerup, NO 'click'. Además, sus
# listbox se RE-RENDERIZAN al interactuar, así que un handle de Selenium guardado
# queda 'stale' antes de poder clicarlo (ese era el bug: la marca nunca se
# seleccionaba). La solución es buscar el elemento FRESCO dentro del propio JS y
# dispararle los eventos pointer en el mismo paso, sin round-trip que se pueda
# quedar stale.
_JS_PRESS = (
    "const el=arguments[0];"
    "try{el.scrollIntoView({block:'center'});}catch(e){}"
    "const o={bubbles:true,cancelable:true,pointerId:1,pointerType:'mouse',button:0,isPrimary:true};"
    "el.dispatchEvent(new PointerEvent('pointerdown',o));"
    "el.dispatchEvent(new PointerEvent('pointerup',o));"
    "el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));"
)

# Clica una opción de listbox (role=option) buscándola fresca por data-key o por
# texto. Dos pasadas: primero coincidencia exacta, luego parcial.
_JS_CLICK_OPTION = r"""
const target=(arguments[0]||'').replace(/\s+/g,' ').trim().toLowerCase();
if(!target) return false;
function press(o){
  try{o.scrollIntoView({block:'center'});}catch(e){}
  const opt={bubbles:true,cancelable:true,pointerId:1,pointerType:'mouse',button:0,isPrimary:true};
  o.dispatchEvent(new PointerEvent('pointerdown',opt));
  o.dispatchEvent(new PointerEvent('pointerup',opt));
  o.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));
}
const ops=[...document.querySelectorAll('[role="option"]')];
for(const o of ops){
  const key=(o.getAttribute('data-key')||'').replace(/\s+/g,' ').trim().toLowerCase();
  const txt=(o.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();
  if(key===target||txt===target){press(o);return true;}
}
for(const o of ops){
  const key=(o.getAttribute('data-key')||'').replace(/\s+/g,' ').trim().toLowerCase();
  const txt=(o.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();
  if((key&&key.includes(target))||(txt&&txt.includes(target))){press(o);return true;}
}
return false;
"""

# Clica un botón/enlace por su texto EXACTO, excluyendo header/nav/footer.
_JS_CLICK_TEXT = r"""
const target=(arguments[0]||'').replace(/\s+/g,' ').trim().toLowerCase();
if(!target) return false;
for(const b of document.querySelectorAll("button, a, [role='button']")){
  const t=(b.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();
  if(t===target && !b.closest('header,nav,footer')){
    try{b.scrollIntoView({block:'center'});}catch(e){}
    const o={bubbles:true,cancelable:true,pointerId:1,pointerType:'mouse',button:0,isPrimary:true};
    b.dispatchEvent(new PointerEvent('pointerdown',o));
    b.dispatchEvent(new PointerEvent('pointerup',o));
    b.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));
    return true;
  }
}
return false;
"""


def _click_opcion_js(driver, valor: str) -> bool:
    """Clica la opción del listbox por data-key/texto sin sufrir el re-render."""
    try:
        return bool(driver.execute_script(_JS_CLICK_OPTION, valor))
    except Exception:
        return False


def _texto_norm(el) -> str:
    """Texto visible colapsando saltos de línea y espacios múltiples."""
    try:
        return re.sub(r"\s+", " ", el.text or "").strip()
    except Exception:
        return ""


def _clic_por_texto(driver, texto: str, exacto: bool = True,
                    excluir_nav: bool = True, espera: float = 3.0) -> bool:
    """
    Click en un botón/enlace por su texto visible.

    Dos precauciones que importan aquí:
      * excluir_nav evita header y footer: 'AT&T Prepago' existe en AMBOS
        lugares y el del menú te saca de la página.
      * se prefiere el candidato con el texto MÁS CORTO. contains() en XPath
        también hace match con contenedores que envuelven varios botones, y
        clicar el contenedor puede activar el hermano equivocado
        (justo el caso 'AT&T Premium' vs 'AT&T Prepago').
    """
    xp = ("//*[self::button or self::a or self::label"
          " or @role='button' or @role='radio' or @role='tab']")
    if excluir_nav:
        xp += "[not(ancestor::header)][not(ancestor::nav)][not(ancestor::footer)]"
    xp += f"[contains(normalize-space(.), \"{texto}\")]"
    try:
        candidatos = driver.find_elements(By.XPATH, xp)
    except Exception:
        return False

    objetivo = re.sub(r"\s+", " ", str(texto)).strip().lower()
    validos = []
    for el in candidatos:
        t = _texto_norm(el)
        if not t:
            continue
        if exacto and t.lower() != objetivo:
            continue
        try:
            if not (el.is_displayed() and el.is_enabled()):
                continue
        except Exception:
            continue
        validos.append((len(t), el))

    for _, el in sorted(validos, key=lambda x: x[0]):
        if _click(driver, el, espera=espera):
            return True

    # Fallback: algunos botones del wizard (p.ej. 'Ver resultados') están en el
    # DOM pero Selenium los reporta como no visibles hasta que se animan. El
    # click por pointer-events vía JS sí los dispara.
    if exacto and driver.execute_script(_JS_CLICK_TEXT, str(texto)):
        if espera:
            time.sleep(espera)
        return True
    return False


def _abierto(trigger) -> bool:
    try:
        return (trigger.get_attribute("aria-expanded") or "").lower() == "true"
    except Exception:
        return False


def abrir_dropdown(driver, trigger, timeout: int = 8):
    """
    Abre el listbox SOLO si está cerrado. Clicar a ciegas lo togglea: por eso
    fallaba una marca sí y una no.
    """
    if trigger is None:
        return None
    if not _abierto(trigger):
        _click(driver, trigger, espera=1.0)
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: _abierto(trigger) or d.find_elements(By.CSS_SELECTOR, '[role="listbox"]')
        )
        cajas = driver.find_elements(By.CSS_SELECTOR, '[role="listbox"]')
        return cajas[-1] if cajas else None
    except Exception:
        # Diagnóstico: casi siempre es control deshabilitado o click no registrado
        try:
            print(f"      [dropdown] expanded={trigger.get_attribute('aria-expanded')} "
                  f"disabled={trigger.get_attribute('data-disabled')} "
                  f"visible={trigger.is_displayed()}")
        except Exception:
            pass
        return None


def cerrar_dropdown(driver, trigger):
    """Cierra el listbox con ESC. En un filtro múltiple no se cierra solo."""
    try:
        webdriver.ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.8)
    except Exception:
        pass
    if trigger is not None and _abierto(trigger):
        _click(driver, trigger, espera=0.8)


def opciones_de_trigger(driver, trigger) -> list:
    """
    Lee las opciones del <select> oculto asociado al trigger.
    Es solo lectura: para SELECCIONAR sí hay que hacer click.
    """
    if trigger is None:
        return []
    try:
        contenedor = trigger.find_element(By.XPATH, "./ancestor::div[@data-slot='base'][1]")
        opts = contenedor.find_elements(By.CSS_SELECTOR, "option")
        vistos, salida = set(), []
        for o in opts:
            txt = (o.get_attribute("value") or o.get_attribute("textContent") or "").strip()
            if txt and txt not in vistos:
                vistos.add(txt)
                salida.append(txt)
        return salida
    except Exception:
        return []


def _clave_opcion(op) -> str:
    """
    Llave de una opción del listbox.

    Las marcas se renderizan como LOGOS: op.text viene vacío y ningún match por
    texto funciona. React Aria guarda la llave del item en data-key, y esa llave
    coincide con el value del <select> oculto ('motorola', 'honor', ...).
    """
    for attr in ("data-key", "data-value", "value", "aria-label", "title", "id"):
        try:
            v = op.get_attribute(attr)
        except Exception:
            continue
        if v and v.strip():
            return v.strip()
    return ""


def seleccionar_opcion(driver, trigger, texto: str, espera: float = 2.5,
                       cerrar: bool = True, indice: int | None = None) -> bool:
    """
    Abre el listbox, clica la opción y lo vuelve a cerrar.
    Orden de match: data-key -> texto exacto -> texto parcial -> índice.
    """
    if trigger is None:
        return False
    listbox = abrir_dropdown(driver, trigger)
    if listbox is None:
        print(f"    No abrió el listbox para '{texto}'")
        return False

    # Dar un instante a que React monte/renderice las opciones del portal.
    time.sleep(0.4)

    # El click se hace por data-key/texto DENTRO de un único execute_script: así
    # el elemento se localiza fresco en el momento del click y no se sufre el
    # StaleElementReferenceException que provoca el re-render de React Aria (era
    # la causa de que la marca nunca quedara seleccionada). Ver _JS_CLICK_OPTION.
    if _click_opcion_js(driver, texto):
        time.sleep(espera)
        if cerrar:
            cerrar_dropdown(driver, trigger)
        return True

    # Fallback por índice: clica la n-ésima opción tal cual está en el DOM.
    if indice is not None:
        clicado = driver.execute_script(
            "const ops=[...document.querySelectorAll('[role=\"option\"]')];"
            "const i=arguments[0];"
            "if(i<0||i>=ops.length) return false;"
            "const el=ops[i];"
            "try{el.scrollIntoView({block:'center'});}catch(e){}"
            "const o={bubbles:true,cancelable:true,pointerId:1,pointerType:'mouse',button:0,isPrimary:true};"
            "el.dispatchEvent(new PointerEvent('pointerdown',o));"
            "el.dispatchEvent(new PointerEvent('pointerup',o));"
            "el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));"
            "return true;",
            indice,
        )
        if clicado:
            time.sleep(espera)
            if cerrar:
                cerrar_dropdown(driver, trigger)
            print(f"    ('{texto}' seleccionada por índice {indice})")
            return True

    # Diagnóstico: sin esto la siguiente iteración vuelve a ser a ciegas
    try:
        opciones = listbox.find_elements(By.CSS_SELECTOR, '[role="option"]')
    except Exception:
        opciones = []
    muestra = [{"key": _clave_opcion(op), "text": _texto_norm(op)} for op in opciones[:6]]
    print(f"    Opción '{texto}' no encontrada entre {len(opciones)}. Muestra: {muestra}")

    cerrar_dropdown(driver, trigger)
    return False


def inspeccionar_controles(driver):
    """Diagnóstico: imprime todos los selects de la página y sus opciones."""
    print("\n" + "=" * 60)
    print("CONTROLES DETECTADOS EN LA PÁGINA")
    print("=" * 60)
    trs = _triggers(driver)
    if not trs:
        print("  (ninguno)")
        print("  Si solo ves nav/footer, es que un modal sigue encima y el")
        print("  cotizador no se montó. Revisa _att_debug/pagina.html o agrega")
        print("  el texto del botón con --saltar 'TextoDelBoton'.")
    for btn in trs:
        try:
            aria = btn.get_attribute("aria-label")
            opts = opciones_de_trigger(driver, btn)
            print(f"  - aria-label='{aria}'  ({len(opts)} opciones)")
            if opts:
                print(f"      {opts[:15]}{' ...' if len(opts) > 15 else ''}")
        except Exception:
            continue

    radios = opciones_de_radiogroup(driver)
    print(f"\n  Radiogroups ({len(radios)} opciones):")
    for r in radios:
        print(f"      - {r}")

    print("\n  Elementos clicables con texto (primeros 30):")
    for el in driver.find_elements(By.CSS_SELECTOR, "button, a")[:30]:
        try:
            t = el.text.strip()
            if t and len(t) < 40:
                print(f"      - {t!r}")
        except Exception:
            continue
    print("=" * 60 + "\n")


# ==============================================================================
# CAPTURA DE RED (respaldo / descubrimiento de API)
# ==============================================================================

def capturar_json(driver, debug: bool = False) -> list:
    """
    Captura TODAS las respuestas JSON (sin filtrar por URL — la v1 filtraba de más
    y por eso salía vacío). Hay que llamarla seguido: el log se drena al leerlo y
    los cuerpos solo viven un rato en memoria.
    """
    payloads = []
    try:
        logs = driver.get_log("performance")
    except Exception:
        return payloads

    for entrada in logs:
        try:
            msg = json.loads(entrada["message"])["message"]
        except Exception:
            continue
        if msg.get("method") != "Network.responseReceived":
            continue
        resp = msg.get("params", {}).get("response", {})
        url, mime = resp.get("url", ""), resp.get("mimeType", "")
        if "json" not in mime.lower():
            continue
        try:
            body = driver.execute_cdp_cmd(
                "Network.getResponseBody", {"requestId": msg["params"]["requestId"]}
            )["body"]
            data = json.loads(body)
        except Exception:
            continue

        payloads.append({"url": url, "data": data})
        if debug:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            nombre = re.sub(r"[^a-zA-Z0-9]+", "_", url)[-90:] + ".json"
            with open(os.path.join(DEBUG_DIR, nombre), "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
    return payloads


# ==============================================================================
# ORQUESTACIÓN
# ==============================================================================

def _clave_dedupe(item: dict) -> str:
    """
    NO se usa SKU: el sufijo de 'pago-mensual-print-N' parece un índice de fila,
    no un identificador de catálogo. La combinación de atributos sí es estable.
    """
    return "|".join([
        str(item.get("Nombre", "")).lower().strip(),
        str(item.get("Capacidad", "")),
        str(item.get("Color", "")),
        str(item.get("Modalidad", "")),
        str(item.get("Plazo", "")),
    ])


def _trigger_de_fila(driver, idx_fila: int, etiqueta: str):
    """
    Devuelve (fila_el, trigger) para el select 'etiqueta' de la fila idx_fila.
    Se RE-BUSCA cada vez: cada selección re-renderiza la fila y los handles
    anteriores quedan stale.
    """
    anclas = driver.find_elements(By.CSS_SELECTOR, ANCLA_PRECIO)
    if idx_fila >= len(anclas):
        return None, None
    fila_el = anclas[idx_fila].find_element(
        By.XPATH, "./ancestor::div[contains(@class,'grid-cols-12')][1]"
    )
    for btn in _triggers(driver, fila_el):
        aria = (btn.get_attribute("aria-label") or "").lower()
        if etiqueta in aria:
            return fila_el, btn
    return fila_el, None


def _leer_fila(driver, idx_fila: int, marca_ctx: str):
    """Parsea la fila idx_fila desde el HTML actual (tras revelarse el precio)."""
    soup = BeautifulSoup(driver.page_source, "html.parser")
    spans = soup.select(ANCLA_PRECIO)
    if idx_fila >= len(spans):
        return None
    cont = _contenedor_de_fila(spans[idx_fila])
    return parsear_fila(cont, marca_ctx) if cont is not None else None


def iterar_variantes_de_fila(driver, idx_fila: int, marca_ctx: str,
                             todas: bool = True) -> list:
    """
    En una fila ya renderizada, elige variante(s) y lee el precio en cada una.

    OJO: al montar los resultados, cada fila arranca con Capacidad/Color en
    'Seleccionar' y SIN precio; el importe solo aparece tras fijar una variante
    concreta. Por eso hay que seleccionar sí o sí al menos la primera combinación,
    incluso sin --variantes. El plan (AT&T Prepago) ya viene del wizard, no se
    toca aquí.

    todas=False -> solo la primera Capacidad x primer Color (una fila).
    todas=True  -> recorre todas las combinaciones (el precio cambia por variante).
    """
    resultados = []
    try:
        _, trig_cap = _trigger_de_fila(driver, idx_fila, ETIQ_CAPACIDAD)
        _, trig_col = _trigger_de_fila(driver, idx_fila, ETIQ_COLOR)
        caps = opciones_de_trigger(driver, trig_cap) or [""]
        cols = opciones_de_trigger(driver, trig_col) or [""]
        if not todas:
            caps, cols = caps[:1], cols[:1]

        for cap in caps:
            if cap:
                _, trig_cap = _trigger_de_fila(driver, idx_fila, ETIQ_CAPACIDAD)
                seleccionar_opcion(driver, trig_cap, cap, espera=1.5)
            for col in cols:
                if col:
                    _, trig_col = _trigger_de_fila(driver, idx_fila, ETIQ_COLOR)
                    seleccionar_opcion(driver, trig_col, col, espera=1.5)
                time.sleep(0.8)
                info = _leer_fila(driver, idx_fila, marca_ctx)
                if info:
                    resultados.append(info)
    except Exception as e:
        print(f"    Variantes fila {idx_fila}: {type(e).__name__}: {e}")
    return resultados


def _etiqueta_de_radio(driver, inp) -> str:
    """
    Texto visible de un radio. Se resuelve por aria-labelledby, NO por value:
    el input de 'AT&T Prepago' trae value='AT&T Planes'. Hacer match por value
    falla o, peor, cae en 'AT&T Premium' (que viene checked por default).
    """
    try:
        lid = inp.get_attribute("aria-labelledby")
        if lid:
            for parte in lid.split():
                try:
                    el = driver.find_element(By.ID, parte)
                    t = _texto_norm(el)
                    if t:
                        return t
                except Exception:
                    continue
    except Exception:
        pass
    return ""


def _sin_parentesis(txt: str) -> str:
    """
    'AT&T Prepago (En tienda física)' -> 'at&t prepago'.
    La etiqueta real trae un descriptor entre paréntesis que rompía el match
    exacto contra 'AT&T Prepago'.
    """
    t = re.sub(r"\s*\([^)]*\)\s*", " ", str(txt))
    return re.sub(r"\s+", " ", t).strip().lower()


def seleccionar_radio(driver, texto: str, espera: float = 3.5) -> bool:
    """
    Selecciona una opción de un radiogroup de React Aria.

    El input real es invisible (opacity 0.0001, tabindex -1) y no expone
    role='radio', así que no lo encuentra ninguna búsqueda por rol ni por texto.
    Se clica el <label> que lo envuelve, que es el patrón de React Aria.
    """
    objetivo = _sin_parentesis(texto)
    if not objetivo:
        return False

    grupos = driver.find_elements(By.CSS_SELECTOR, '[role="radiogroup"]')
    if not grupos:
        return False

    disponibles = []
    for grupo in grupos:
        try:
            inputs = grupo.find_elements(By.CSS_SELECTOR, 'input[type="radio"]')
        except Exception:
            continue

        for inp in inputs:
            etiqueta = _etiqueta_de_radio(driver, inp)
            if not etiqueta:
                continue
            disponibles.append(etiqueta)
            if _sin_parentesis(etiqueta) != objetivo:
                continue

            if inp.is_selected():
                print(f"  Servicio ya seleccionado: {etiqueta}")
                return True

            # Se clica el label; el input está prácticamente invisible
            objetivos_click = []
            try:
                objetivos_click.append(inp.find_element(By.XPATH, "./ancestor::label[1]"))
            except Exception:
                pass
            objetivos_click.append(inp)

            for el in objetivos_click:
                if _click(driver, el, espera=espera) and inp.is_selected():
                    print(f"  Servicio seleccionado: {etiqueta}")
                    return True

            # último recurso: forzar los eventos que React Aria sí escucha
            try:
                driver.execute_script(
                    "arguments[0].dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));"
                    "arguments[0].dispatchEvent(new PointerEvent('pointerup',{bubbles:true}));"
                    "arguments[0].click();", inp)
                time.sleep(espera)
                if inp.is_selected():
                    print(f"  Servicio seleccionado (pointer events): {etiqueta}")
                    return True
            except Exception:
                pass

            print(f"  El click en '{etiqueta}' no prendió el radio.")

    if disponibles:
        print(f"  '{texto}' no coincide con los servicios: {disponibles}")
    return False


def opciones_de_radiogroup(driver) -> list:
    """Lista las etiquetas visibles de todos los radiogroups (diagnóstico)."""
    salida = []
    for grupo in driver.find_elements(By.CSS_SELECTOR, '[role="radiogroup"]'):
        for inp in grupo.find_elements(By.CSS_SELECTOR, 'input[type="radio"]'):
            et = _etiqueta_de_radio(driver, inp)
            if et:
                try:
                    marca = " (checked)" if inp.is_selected() else ""
                except Exception:
                    marca = ""
                salida.append(et + marca)
    return salida


def plan_actual(driver) -> str:
    """
    Lee qué plan está realmente aplicado, tomándolo de la primera fila.
    Es la única fuente de verdad: el filtro puede no haber prendido.
    """
    try:
        filas = parsear_pagina(driver.page_source)
    except Exception:
        return ""
    return filas[0].get("Modalidad", "") if filas else ""


def seleccionar_plan(driver, plan: str, silencioso: bool = False) -> bool:
    """
    Prueba las formas en que el cotizador puede exponer el servicio, en orden
    de probabilidad real:
      1) radiogroup '2. Selecciona un servicio'  <- este es el caso real
      2) select de HeroUI con aria-label de plan
      3) botón / chip / tab con ese texto exacto
      4) (después de los resultados) el select 'Plan de datos' de cada fila
    """
    if not plan:
        return True

    # 1) radiogroup — el caso real del cotizador
    if seleccionar_radio(driver, plan):
        return True

    # 2) select global
    trig = buscar_trigger(driver, ARIA_PLAN)
    if trig is not None and seleccionar_opcion(driver, trig, plan, espera=3.5):
        print(f"  Plan fijado por select: {plan}")
        return True

    # 3) botón / chip / tab
    if _clic_por_texto(driver, plan, espera=4):
        print(f"  Plan fijado por botón: {plan}")
        return True

    if not silencioso:
        opciones = opciones_de_radiogroup(driver)
        print(f"  Aviso: no se encontró control de plan para '{plan}'.")
        if opciones:
            print(f"  Servicios disponibles: {opciones}")
    return False


def fijar_plan_en_filas(driver, plan: str) -> int:
    """
    Fija el plan en el select 'Plan de datos' de CADA fila.
    Es el camino más confiable cuando el filtro global no manda: el valor
    queda escrito en la propia fila que después parseamos.
    """
    if not plan:
        return 0
    ajustadas = 0
    try:
        n = len(driver.find_elements(By.CSS_SELECTOR, ANCLA_PRECIO))
    except Exception:
        return 0

    for i in range(n):
        try:
            anclas = driver.find_elements(By.CSS_SELECTOR, ANCLA_PRECIO)
            if i >= len(anclas):
                break
            fila_el = anclas[i].find_element(
                By.XPATH, "./ancestor::div[contains(@class,'grid-cols-12')][1]"
            )
            for btn in _triggers(driver, fila_el):
                aria = (btn.get_attribute("aria-label") or "").lower()
                if "plan" in aria:
                    if seleccionar_opcion(driver, btn, plan, espera=2.0):
                        ajustadas += 1
                    break
        except Exception:
            continue
    return ajustadas


def esperar_filas(driver, timeout: int = 25) -> int:
    """Espera a que aparezcan filas de resultados. Devuelve cuántas hay."""
    limite = time.time() + timeout
    while time.time() < limite:
        try:
            n = len(driver.find_elements(By.CSS_SELECTOR, ANCLA_PRECIO))
            if n:
                return n
        except Exception:
            pass
        time.sleep(1.5)
    return 0


# --- Paginación de resultados -------------------------------------------------
# La lista de resultados muestra 10 equipos por página; el resto vive en más
# páginas (HeroUI Pagination: botones 'Ir a página N' + 'Página siguiente').
# Hay que recorrerlas todas y revelar el precio fila por fila en cada una.

def _pagina_actual(driver) -> int:
    """Número de la página marcada como activa (aria-current='page')."""
    try:
        el = driver.find_element(By.CSS_SELECTOR, 'button[aria-current="page"]')
        return int(re.sub(r"\D", "", el.text) or 0)
    except Exception:
        return 0


def _total_paginas(driver) -> int:
    """Mayor 'Ir a página N' visible (la última página del set)."""
    maximo = 1
    try:
        for b in driver.find_elements(By.CSS_SELECTOR, 'button[aria-label^="Ir a página"]'):
            m = re.search(r"(\d+)", b.get_attribute("aria-label") or "")
            if m:
                maximo = max(maximo, int(m.group(1)))
    except Exception:
        pass
    return maximo


def ir_pagina_siguiente(driver, timeout: int = 20) -> bool:
    """
    Avanza a la siguiente página de resultados. Devuelve False si ya no hay
    (el botón 'Página siguiente' viene deshabilitado en la última).
    """
    try:
        btn = driver.find_element(By.CSS_SELECTOR, 'button[aria-label="Página siguiente"]')
    except Exception:
        return False
    disabled = (btn.get_attribute("disabled") is not None
                or (btn.get_attribute("aria-disabled") or "").lower() == "true")
    if disabled:
        return False

    antes = _pagina_actual(driver)
    _click(driver, btn, espera=1.0)
    # esperar a que cambie el indicador de página y vuelvan a existir filas
    limite = time.time() + timeout
    while time.time() < limite:
        if _pagina_actual(driver) != antes and driver.find_elements(By.CSS_SELECTOR, ANCLA_PRECIO):
            time.sleep(1.0)
            return True
        time.sleep(1.0)
    return True  # seguimos aunque el indicador no se haya movido a tiempo


def _abrir_cotizador(headless: bool, debug: bool, textos_descarte) -> webdriver.Chrome:
    """Abre un navegador nuevo, carga el cotizador, cierra el modal y espera a
    que React hidrate. Devuelve el driver listo para operar."""
    driver = construir_driver(headless=headless, con_logs=debug)
    driver.get(URL_COTIZADOR)
    time.sleep(6)
    # El modal de bienvenida ('Continuar'/'Saltar') bloquea el montaje del
    # cotizador: hay que cerrarlo antes de nada.
    descartar_overlays(driver, textos=textos_descarte)
    if not esperar_cotizador(driver):
        print("    Aviso: el cotizador no terminó de montar en el tiempo esperado.")
    return driver


# Páginas de resultados a procesar por sesión de navegador antes de reiniciarlo.
# Revelar precios abre/cierra cientos de dropdowns y el consumo sube página a
# página; en un host con poca RAM, reiniciar cada pocas páginas evita que Chrome
# muera con InvalidSessionId. Se retoma exactamente en la página siguiente.
PAGINAS_POR_SESION = 3


def _entrar_resultados(driver, marca, marcas_todas, plan) -> int:
    """Selecciona marca + servicio y avanza el wizard hasta la lista de
    resultados. Devuelve el total de páginas (0 si no hubo resultados)."""
    if marca:
        trig = buscar_trigger(driver, ARIA_MARCA)
        idx = marcas_todas.index(marca) if marca in marcas_todas else None
        if not seleccionar_opcion(driver, trig, marca, espera=2.5, indice=idx):
            print("    (no se pudo seleccionar la marca)")
            return 0
        # El servicio (AT&T Prepago) se fija en el radiogroup ANTES de avanzar el
        # wizard: así el precio ya sale para ese plan.
        if plan and not seleccionar_plan(driver, plan):
            print(f"    Aviso: no se pudo fijar el servicio '{plan}'")
        time.sleep(1.5)
        # Wizard por pasos: 'Continuar' -> paso de presupuesto -> 'Ver resultados'.
        _clic_por_texto(driver, TEXTO_CONTINUAR, espera=3)
        if not _clic_por_texto(driver, TEXTO_VER_RESULTADOS, espera=4):
            print(f"    Aviso: no apareció '{TEXTO_VER_RESULTADOS}'")

    if not esperar_filas(driver):
        return 0
    return _total_paginas(driver)


def _avanzar_a_pagina(driver, objetivo: int) -> bool:
    """Fast-forward hasta la página objetivo clicando 'siguiente' (barato: no se
    revelan precios). Devuelve True si llegó."""
    intentos = 0
    while _pagina_actual(driver) < objetivo:
        if not ir_pagina_siguiente(driver):
            return False
        intentos += 1
        if intentos > 300:
            return False
    return True


def _cosechar_pagina(driver, marca, plan, variantes, estricto, debug, data, vistos):
    """Revela el precio fila por fila en la página actual y acumula lo nuevo.
    Devuelve (n_anclas, filas_con_precio, filas_nuevas)."""
    for _ in range(3):  # scroll para renderizar todas las filas
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.2)
    if debug:
        capturar_json(driver, debug=True)

    # Cada fila arranca SIN precio: hay que elegir una variante (Capacidad x
    # Color) para que el importe aparezca. Por eso se recorre fila por fila
    # incluso sin --variantes (ahí solo se toma la 1ª combinación).
    n = len(driver.find_elements(By.CSS_SELECTOR, ANCLA_PRECIO))
    filas = []
    for i in range(n):
        filas.extend(iterar_variantes_de_fila(driver, i, marca, todas=variantes))

    if plan and estricto and filas:
        filas = [f for f in filas
                 if f.get("Modalidad", "").strip().lower() == plan.strip().lower()]

    nuevas = 0
    for info in filas:
        k = _clave_dedupe(info)
        if k in vistos:
            continue
        vistos.add(k)
        data.append(info)
        nuevas += 1
    return n, len(filas), nuevas


def scrape_att(headless=True, debug=False, marcas_filtro=None,
               variantes=False, inspeccionar=False, textos_descarte=None,
               plan=TEXTO_PLAN_DEFAULT, estricto=False) -> list:
    print("=" * 60)
    print("INICIANDO SCRAPING DE AT&T MÉXICO")
    print("=" * 60)

    data, vistos = [], set()

    # 1) Lista de marcas (navegador corto que se cierra enseguida).
    print(f"Cargando: {URL_COTIZADOR}")
    driver = _abrir_cotizador(headless, debug, textos_descarte)
    marcas_todas = []
    try:
        if inspeccionar:
            inspeccionar_controles(driver)
        trig = buscar_trigger(driver, ARIA_MARCA)
        if trig is None:
            print("Aviso: no se encontró el selector de marca.")
            marcas = [""]
        else:
            marcas_todas = opciones_de_trigger(driver, trig) or [""]
            marcas = list(marcas_todas)
            if marcas_filtro:
                pedidas = {m.lower() for m in marcas_filtro}
                marcas = [m for m in marcas if m.lower() in pedidas] or marcas
        print(f"Marcas detectadas ({len(marcas)}): {marcas}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    # 2) Cada marca se recorre en TANDAS de páginas (PAGINAS_POR_SESION) y con un
    #    navegador NUEVO por tanda. Reiniciar Chrome libera la memoria que se va
    #    acumulando al revelar precios (cientos de dropdowns) y hace que un crash
    #    a mitad de camino no tumbe la corrida: se retoma en la página siguiente y
    #    lo ya recolectado se conserva.
    for marca in marcas:
        print(f"\nMarca: {marca or '(sin filtro)'}")
        pagina_inicio, total_pag, nuevas_marca = 1, None, 0
        sin_avance = 0

        while True:
            driver, hechas = None, 0
            try:
                driver = _abrir_cotizador(headless, debug, textos_descarte)
                total_pag = _entrar_resultados(driver, marca, marcas_todas, plan)
                if total_pag == 0:
                    if pagina_inicio == 1:
                        print("    sin resultados para este plan")
                    break
                if pagina_inicio == 1 and total_pag > 1:
                    print(f"    {total_pag} páginas de resultados")
                if pagina_inicio > total_pag:
                    break
                if pagina_inicio > 1 and not _avanzar_a_pagina(driver, pagina_inicio):
                    print(f"    no se pudo avanzar a la pág {pagina_inicio}, se corta la marca")
                    break

                p = pagina_inicio
                while p <= total_pag and hechas < PAGINAS_POR_SESION:
                    n, con_precio, nuevas = _cosechar_pagina(
                        driver, marca, plan, variantes, estricto, debug, data, vistos)
                    nuevas_marca += nuevas
                    print(f"    pág {p}/{total_pag}: {con_precio} con precio "
                          f"(ancla {n}) | nuevas {nuevas} | acumulado {len(data)}")
                    hechas += 1
                    p += 1
                    if p <= total_pag and hechas < PAGINAS_POR_SESION:
                        if not ir_pagina_siguiente(driver):
                            p = total_pag + 1  # ya no hay más
                            break
                pagina_inicio = p
            except Exception as e:
                print(f"    pág {pagina_inicio}+ interrumpida: "
                      f"{type(e).__name__}: {str(e)[:120]}")
                # saltar la página que venía fallando para no reintentarla en bucle
                pagina_inicio = pagina_inicio + hechas + 1
            finally:
                if driver is not None:
                    try:
                        driver.quit()
                    except Exception:
                        pass

            sin_avance = sin_avance + 1 if hechas == 0 else 0
            if sin_avance >= 3:
                print("    3 tandas sin avanzar, se abandona la marca")
                break
            if total_pag is not None and pagina_inicio > total_pag:
                break

        print(f"    total {marca or '(sin filtro)'}: {nuevas_marca}")

    print(f"\n{'='*60}")
    print(f"SCRAPING COMPLETADO — productos únicos: {len(data)}")
    print(f"{'='*60}")

    return data


def exportar(data: list):
    if not data:
        print("No se encontraron productos válidos.")
        print("Corre con --no-headless --debug --inspeccionar para ver los controles reales.")
        return None

    df = pd.DataFrame(data)
    for col in SCHEMA:
        if col not in df.columns:
            df[col] = ""
    df = df[SCHEMA]

    print(f"\nProductos antes de limpiar: {len(df)}")
    df = df[df["Nombre"].astype(str).str.len() > 1]
    df = df[df["Precio_original"] != "No inventory"]
    df = df.drop_duplicates(
        subset=["Nombre", "Capacidad", "Color", "Modalidad", "Plazo"], keep="first"
    )
    df = df.sort_values(["Marca", "Nombre", "Capacidad"]).reset_index(drop=True)
    print(f"Productos después de limpiar: {len(df)}")

    ahora = datetime.now(TZ_CDMX) if TZ_CDMX is not None else datetime.now()
    fecha_hoy, hora_hoy = ahora.strftime("%Y-%m-%d"), ahora.strftime("%H%M%S")

    csv_out = f"att_celulares_{fecha_hoy}.csv"
    xlsx_out = f"Daily Pricing Mapping ATT ({fecha_hoy}) {hora_hoy}.xlsx"
    df.to_csv(csv_out, index=False, encoding="utf-8-sig")
    try:
        df.to_excel(xlsx_out, index=False)
        print(f"Datos exportados a {csv_out} y {xlsx_out}")
    except Exception as e:
        print(f"Datos exportados a {csv_out} (sin XLSX: {e})")

    print("\n=== ESTADÍSTICAS ===")
    print(f"Total de productos: {len(df)}")
    print("\nProductos por marca:")
    print(df["Marca"].value_counts())
    print(f"\nCon descuento: {len(df[df['Porcentaje_descuento'] != 'No discount'])}")
    print("\n=== PRIMEROS 10 ===")
    print(df.head(10).to_string())
    return df


def main():
    ap = argparse.ArgumentParser(description="Scraper de AT&T México (cotizador de celulares)")
    ap.add_argument("--no-headless", action="store_true", help="Abrir el navegador con ventana")
    ap.add_argument("--debug", action="store_true", help="Guardar JSON/HTML crudos en ./_att_debug/")
    ap.add_argument("--inspeccionar", action="store_true", help="Listar los controles de la página")
    ap.add_argument("--variantes", action="store_true", help="Iterar capacidad x color por fila (lento)")
    ap.add_argument("--marcas", nargs="*", default=None, help="Limitar a ciertas marcas")
    ap.add_argument("--saltar", nargs="*", default=None,
                    help="Textos de botones a clicar para cerrar modales (default: Saltar, Omitir, Cerrar...)")
    ap.add_argument("--plan", default=TEXTO_PLAN_DEFAULT,
                    help=f"Plan a cotizar (default: '{TEXTO_PLAN_DEFAULT}'). Vacío para no clicar ninguno.")
    ap.add_argument("--estricto", action="store_true",
                    help="Descartar filas cuyo plan no sea el pedido (default: conservarlas etiquetadas)")
    args = ap.parse_args()

    data = scrape_att(
        headless=not args.no_headless,
        debug=args.debug,
        marcas_filtro=args.marcas,
        variantes=args.variantes,
        inspeccionar=args.inspeccionar,
        textos_descarte=args.saltar,
        plan=args.plan,
        estricto=args.estricto,
    )
    exportar(data)


if __name__ == "__main__":
    main()