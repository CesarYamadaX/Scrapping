#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
homologa_celulares.py
======================
Toma un CSV de Sears o de Coppel y para cada celular determina:
  - Nombre Homologado (MARCA MODELO CAPACIDAD RED, en el mismo formato que
    usamos en el diccionario)
  - Red (4G / 4.5G / 5G / 3G / 2G)

El match se hace contra diccionario2.xlsx (hoja CONSOLIDADO, columna
HOMOLOGACION MODELO de la hoja UNICOS), usando la misma logica de
"contencion estricta de tokens" que evita errores peligrosos como confundir
un Galaxy A51 con un A52, o un P60 con un P60 Pro: un candidato del
catalogo solo se acepta si TODAS sus palabras aparecen en el texto de
origen. Si el texto trae ruido extra (colores, "Nuevo", "Reacondicionado",
un "+ BOCINA DE REGALO", etc.) no afecta el match, siempre y cuando el
nombre del modelo si este completo en alguna parte del texto.

USO (con ventanas, doble-click o "python homologa_celulares.py")
------------------------------------------------------------------
Si lo corres sin argumentos, se abren ventanas para:
  1. Elegir el CSV a homologar
  2. (si hace falta) elegir donde esta diccionario2.xlsx
  3. Confirmar si es Sears o Coppel (con un botón para cada uno)
  4. Elegir donde guardar el resultado

    python homologa_celulares.py

USO (por linea de comandos / para automatizar, sin ventanas)
------------------------------------------------------------------
    python homologa_celulares.py coppel.csv --formato coppel --salida resultado.csv --referencia ruta.xlsx

Si pasas el archivo y --formato, no se abre ninguna ventana. --referencia
por default busca el archivo en: C:/Users/c90029859/Documents/diccionario2.xlsx

El resultado agrega tres columnas: "Nombre Homologado", "Red" y "Estado"
(OK / REVISAR / NO_APLICA), esta ultima para que la revision manual de lo
que no se pudo homologar con certeza sea rapida.

REQUISITOS
----------
    pip install pandas openpyxl

    tkinter (para las ventanas) ya viene incluido con Python en Windows y
    Mac. En Linux, si falta: sudo apt install python3-tk
    Si no esta disponible, usa el modo por linea de comandos de arriba.

"""

import argparse
import re
import sys
import collections
from pathlib import Path

import pandas as pd
import openpyxl


# ---------------------------------------------------------------------------
# Ventanas emergentes (tkinter) para elegir archivos sin usar la terminal.
# tkinter viene incluido con Python en Windows/Mac. En Linux a veces hace
# falta instalarlo aparte: sudo apt install python3-tk
# ---------------------------------------------------------------------------

def _root_oculto():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def elegir_archivo_popup():
    from tkinter import filedialog
    root = _root_oculto()
    path = filedialog.askopenfilename(
        title="Selecciona el archivo CSV a homologar (Sears o Coppel)",
        filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")],
    )
    root.destroy()
    return path or None
    


def elegir_referencia_popup():
    from tkinter import filedialog, messagebox
    root = _root_oculto()
    messagebox.showinfo(
        "Falta el catalogo",
        "No encontre diccionario2.xlsx en la ruta configurada.\n\n"
        "Selecciona donde esta ese archivo.",
    )
    path = filedialog.askopenfilename(
        title="Selecciona diccionario2.xlsx",
        filetypes=[("Excel", "*.xlsx"), ("Todos los archivos", "*.*")],
    )
    root.destroy()
    return path or None


def preguntar_formato_popup(guess=None):
    import tkinter as tk
    resultado = {"valor": None}

    root = tk.Tk()
    root.title("Formato del archivo")
    root.attributes("-topmost", True)
    root.resizable(False, False)

    msg = "¿Este archivo es de Sears o de Coppel?"
    if guess:
        msg += f"\n\n(Por las columnas, parece: {guess.upper()})"
    tk.Label(root, text=msg, wraplength=300, justify="center", padx=20, pady=15).pack()

    frame = tk.Frame(root)
    frame.pack(pady=(0, 15))

    def elegir(valor):
        resultado["valor"] = valor
        root.destroy()

    tk.Button(frame, text="Sears", width=12, command=lambda: elegir("sears")).pack(side="left", padx=8)
    tk.Button(frame, text="Coppel", width=12, command=lambda: elegir("coppel")).pack(side="left", padx=8)

    root.protocol("WM_DELETE_WINDOW", lambda: elegir(guess))  # si cierran la ventana, usa la sugerencia
    root.eval("tk::PlaceWindow . center")
    root.mainloop()
    return resultado["valor"]


def elegir_guardado_popup(nombre_sugerido):
    from tkinter import filedialog
    root = _root_oculto()
    path = filedialog.asksaveasfilename(
        title="Guardar resultado como...",
        initialfile=nombre_sugerido,
        defaultextension=".csv",
        filetypes=[("CSV", "*.csv")],
    )
    root.destroy()
    return path or None


def avisar_resultado_popup(total, ok, revisar, no_aplica, salida_path):
    from tkinter import messagebox
    root = _root_oculto()
    messagebox.showinfo(
        "Listo",
        f"Total filas: {total}\n\n"
        f"OK (match confiable): {ok}\n"
        f"REVISAR (revisar a mano): {revisar}\n"
        f"NO_APLICA (no es celular): {no_aplica}\n\n"
        f"Guardado en:\n{salida_path}",
    )
    root.destroy()


# ---------------------------------------------------------------------------
# Listas de referencia usadas para separar marca / modelo / color / capacidad
# de texto libre. Se pueden ampliar si aparecen marcas o palabras nuevas.
# ---------------------------------------------------------------------------

BRANDS = [
    "TECNOMOBILE", "TECNOMOVIL", "REDMAGIC", "BLACKVIEW", "ULEFONE", "FOSSIBOT",
    "OUKITEL", "UMIDIGI", "ONEPLUS", "NOTHING", "INFINIX", "MOTOROLA", "SAMSUNG",
    "HUAWEI", "REALME", "ALCATEL", "LENOVO", "HYUNDAI", "DOOGEE", "XIAOMI",
    "GOOGLE", "NUBIA", "TECNO", "HONOR", "APPLE", "IPHONE", "OPPO", "VIVO",
    "NOKIA", "MEIZU", "CUBOT", "SENWA", "SOYES", "ORBIC", "NAOMI", "IMOBIL",
    "DOPPIO", "LANIX", "ZUUM", "WIKO", "SONY", "BLU", "TCL", "LG", "ZTE",
    "KXD", "ACER",
]
BRANDS = sorted(set(BRANDS), key=len, reverse=True)

# Estos NO son celulares (equipos de oficina/red) - si se detectan, la fila
# se marca como "NO APLICA" en vez de forzar un match.
NON_PHONE_BRANDS = {
    "PANASONIC", "GRANDSTREAM", "CISCO", "TPLINK", "TP-LINK", "UBIQUITI", "HP",
}
NON_PHONE_KEYWORDS = {
    "RELOJ", "WATCH", "AUDIFONO", "AUDIFONOS", "AURICULAR", "AURICULARES",
    "BOCINA", "BUDS", "TABLET", "IPAD", "LAPTOP", "MACBOOK", "IMAC",
    "SMARTWATCH", "BAND", "PULSERA",
}

COLOR_WORDS = {
    "NEGRO", "BLANCO", "AZUL", "ROJO", "VERDE", "GRIS", "DORADO", "PLATEADO",
    "PLATA", "ORO", "ROSA", "MORADO", "VIOLETA", "AMARILLO", "NARANJA", "CAFE",
    "VINO", "TITANIO", "GRAFITO", "LILA", "LAVANDA", "NATURAL", "MEDIANOCHE",
    "ESTELAR", "GLACIAR", "HIELO", "MOCHA", "MOUSSE", "MOUSSEE", "MARRON",
    "CLARO", "OSCURO", "BRILLANTE", "MARINO", "MENTA", "CHAMPAGNE", "CORAL",
    "TURQUESA", "ESMERALDA", "CIELO", "CEREZA", "ROJIZO", "BEIGE", "ACERO",
    "PROFUNDO", "PERLA", "MEDIANOCHE", "STARLIGHT", "MIDNIGHT",
    "BLACK", "WHITE", "BLUE", "RED", "GREEN", "GRAY", "GREY", "GOLD", "SILVER",
    "PINK", "PURPLE", "YELLOW", "ORANGE", "LIGHT",
}

NOISE_WORDS = {
    "DESBLOQUEADO", "DESBLOQUEADA", "LIBERADO", "LIBERADA", "REACONDICIONADO",
    "REACONDICIONADA", "NUEVO", "NUEVA", "SELLADO", "SELLADA", "GARANTIA",
    "DUAL", "SIM", "ESIM", "E-SIM", "RAM", "ROM", "ANDROID", "USO", "RUDO",
    "RESISTENTE", "AGUA", "GOLPES", "EXPANDIBLE", "GRADO", "MESES", "DE",
    "CELULAR", "CELULARES", "SMARTPHONE", "SMARTPHONES", "Y", "CON", "SIN",
    "COLOR", "ALMACENAMIENTO", "PULGADAS", "DESCUENTO", "PROMOCION", "OFERTA",
    "ORIGINAL", "EXCELENTE", "BUENO", "PANTALLA", "REGALO", "COMBO", "A",
    "MP", "HZ", "MHZ", "GHZ", "TELCEL", "AT&T", "MOVISTAR",
}

NET_RE = re.compile(r"\b(4\.5G|5G|4G|3G|2G|LTE)\b", re.IGNORECASE)

# Patrones de capacidad/RAM, en orden de especificidad (el primero que
# aplique "gana" ese tramo de texto). Todos se usan tanto para EXTRAER la
# capacidad real como para LIMPIAR el texto (evita que sobrevivan
# fragmentos sueltos tipo "8256" o "GB" que ensucian el nombre del modelo).
_COMBO_RE = re.compile(r"\b\d+\s*\+\s*\d+\s*(?:GB|MB|TB)\b", re.IGNORECASE)
_GB_RAM_RE = re.compile(r"\b\d+\s*(?:GB|MB|TB)\s*RAM\b", re.IGNORECASE)
_BARE_RAM_RE = re.compile(r"\b\d+\s*RAM\b", re.IGNORECASE)
_BARE_GB_RE = re.compile(r"\b\d+\s*(?:GB|MB|TB)\b", re.IGNORECASE)
_MP_RE = re.compile(r"\b\d+\s*MP\b", re.IGNORECASE)
_SCREEN_SIZE_RE = re.compile(r"\b\d+\.\d+\s*(?:\"|''|PULGADAS)?\b", re.IGNORECASE)
_NUM_IN_PATTERN_RE = re.compile(r"\d+")


def extract_capacity_and_clean(text):
    """Devuelve (capacidad_str_o_None, texto_sin_ram_ni_capacidad).
    Quita los tramos de texto que indican RAM/almacenamiento COMPLETOS
    (numero + unidad + palabra RAM si aplica), para no dejar fragmentos
    sueltos como "8256" o "GB" flotando en el nombre del modelo. Cualquier
    otro numero (como el "15" de "Redmi Note 15") no se toca.

    Nota: no existe una forma 100% confiable de separar RAM de
    almacenamiento en texto libre cuando el listado original ya viene mal
    etiquetado (ej. "8 GB Ram 256 GB Ram" con AMBOS marcados como Ram) -
    en esos casos poco frecuentes puede hacer falta revisar a mano."""
    capacities = []
    working = text

    for m in _COMBO_RE.finditer(working):
        nums = [int(n) for n in _NUM_IN_PATTERN_RE.findall(m.group(0))]
        capacities.append(max(nums))
    working = _COMBO_RE.sub(" ", working)

    working = _GB_RAM_RE.sub(" ", working)
    working = _BARE_RAM_RE.sub(" ", working)

    for m in _BARE_GB_RE.finditer(working):
        nums = [int(n) for n in _NUM_IN_PATTERN_RE.findall(m.group(0))]
        capacities.append(max(nums))
    working = _BARE_GB_RE.sub(" ", working)

    working = _MP_RE.sub(" ", working)
    working = _SCREEN_SIZE_RE.sub(" ", working)

    cap = f"{max(capacities)}GB" if capacities else None
    return cap, working


# ---------------------------------------------------------------------------
# Referencia: cargar diccionario2.xlsx (hoja CONSOLIDADO) y construir el indice
# marca+modelo+capacidad -> red
# ---------------------------------------------------------------------------

def normalize(s):
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def strip_net(name):
    net = ""
    m = re.search(r"\s*(4\.5G|5G|4G|3G|2G|LTE)\s*$", name, re.IGNORECASE)
    if m:
        net = m.group(1).upper()
        name = name[: m.start()].strip()
    return name, net


def load_reference(xlsx_path):
    wb = openpyxl.load_workbook(xlsx_path, read_only=True)
    if "CONSOLIDADO" not in wb.sheetnames:
        raise ValueError(
            f"No encontre la hoja 'CONSOLIDADO' en {xlsx_path}. "
            "Este script espera el archivo diccionario2.xlsx."
        )
    ws = wb["CONSOLIDADO"]
    header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    try:
        col_idx = [str(h).strip().upper() for h in header].index("NOMBRE HOMOLOGADO")
    except ValueError:
        raise ValueError(
            f"No encontre la columna 'Nombre Homologado' en la hoja CONSOLIDADO de {xlsx_path}."
        )

    homologs = collections.Counter()
    for row in ws.iter_rows(min_row=2, values_only=True):
        v = row[col_idx]  # columna "Nombre Homologado" (ya trae marca+modelo+capacidad+red)
        if v:
            homologs[str(v).strip().upper()] += 1

    base_net_counts = collections.defaultdict(collections.Counter)
    for h, cnt in homologs.items():
        base, net = strip_net(h)
        base_net_counts[normalize(base)][net] += cnt

    ref = {}
    for base, netcounts in base_net_counts.items():
        non_empty = {k: v for k, v in netcounts.items() if k}
        ref[base] = max(non_empty.items(), key=lambda x: x[1])[0] if non_empty else ""

    by_brand = collections.defaultdict(list)
    for base in ref:
        brand = base.split(" ")[0] if base else ""
        by_brand[brand].append(base)

    return ref, by_brand


CAP_RE_FOR_MATCH = re.compile(r"\b(\d+)\s*GB\b")


def best_match(search_text, ref, by_brand):
    """Contencion estricta: el candidato del catalogo debe estar COMPLETO
    dentro del texto de origen. Nunca hace match parcial que pudiera
    confundir un modelo con otro (ej. A51 vs A52)."""
    norm = normalize(search_text)
    if norm in ref:
        return norm, ref[norm], 1.0
    tokens = set(norm.split())
    if not tokens:
        return None, "", 0.0
    brand = norm.split(" ")[0]
    candidates = by_brand.get(brand, [])
    cap_m = CAP_RE_FOR_MATCH.search(norm)
    cap = cap_m.group(1) if cap_m else None

    best_base, best_len = None, -1
    for cb in candidates:
        ctoks = set(cb.split())
        if cap:
            ccap_m = CAP_RE_FOR_MATCH.search(cb)
            ccap = ccap_m.group(1) if ccap_m else None
            if ccap and ccap != cap:
                continue
        if ctoks.issubset(tokens) and len(ctoks) >= 2:
            if len(ctoks) > best_len:
                best_len = len(ctoks)
                best_base = cb
    if best_base:
        return best_base, ref[best_base], best_len / max(len(tokens), 1)
    return None, "", 0.0


# Marcas/typos conocidos que rompen el match si no se corrigen antes.
BRAND_TYPO_FIX = {
    "XIOAMI": "XIAOMI",
    "MOTORLA": "MOTOROLA",
    "SASMSUNG": "SAMSUNG",
}


def fix_typos(text):
    tokens = text.split()
    if tokens:
        tokens[0] = BRAND_TYPO_FIX.get(tokens[0], tokens[0])
    return " ".join(tokens)


# Redes conocidas para modelos que MODELOS_UNICOS todavia no tiene
# registrados (investigadas manualmente). Amplia esta lista si encuentras
# mas casos que el catalogo no cubre.
MANUAL_NET_RULES = [
    (r"^SAMSUNG.*Z FLIP", "5G"),
    (r"^SAMSUNG.*Z FOLD", "5G"),
    (r"^INFINIX HOT \d", "4G"),
    (r"^INFINIX SMART \d", "4G"),
    (r"^INFINIX NOTE", "5G"),
    (r"^TECNO CAMON", "5G"),
    (r"^TECNO SPARK", "4G"),
    (r"^BLU ", "4G"),
    (r"^UMIDIGI ", "4G"),
    (r"^CUBOT ", "4G"),
    (r"^OUKITEL ", "4G"),
    (r"^POCO C\d", "4G"),
    (r"^NOTHING PHONE", "5G"),
    (r"^GOOGLE PIXEL 9", "5G"),
    (r"^XIAOMI REDMI NOTE 15 PRO PLUS", "5G"),
    (r"^HONOR X9C", "5G"),
    (r"^NUBIA V80 DESIGN", "4G"),
]


def manual_lookup(base_no_network):
    for pattern, net in MANUAL_NET_RULES:
        if re.match(pattern, base_no_network):
            return net
    return None


# ---------------------------------------------------------------------------
# Extraccion de marca / capacidad / modelo a partir de texto libre
# ---------------------------------------------------------------------------

RAW_TEXT_TYPOS = {
    r"\bXIOAMI\b": "XIAOMI",
    r"\bMOTORLA\b": "MOTOROLA",
    r"\bSASMSUNG\b": "SAMSUNG",
}


def fix_raw_typos(text):
    for pattern, repl in RAW_TEXT_TYPOS.items():
        text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
    return text


def extract_brand(text, given_brand=None):
    if given_brand and str(given_brand).strip():
        b = str(given_brand).strip().upper()
        return BRAND_TYPO_FIX.get(b, b)
    upper = text.upper()
    if re.search(r"\bIPHONE\b", upper):
        return "APPLE"
    for b in BRANDS:
        if re.search(r"\b" + re.escape(b) + r"\b", upper):
            return BRAND_TYPO_FIX.get(b, b) if b != "IPHONE" else "APPLE"
    return None


def is_non_phone(text, brand):
    if brand in NON_PHONE_BRANDS:
        return True
    # Solo revisamos las primeras palabras: un accesorio real lo dice al
    # principio ("Reloj Inteligente ..."), mientras que un telefono que
    # trae un regalo lo menciona al final ("... + BOCINA DE REGALO").
    prefix = " ".join(text.upper().split()[:4])
    return any(re.search(r"\b" + kw + r"\b", prefix) for kw in NON_PHONE_KEYWORDS)


def build_search_text(brand, cleaned_name, capacity):
    """Arma el texto de busqueda a partir del texto YA limpio de RAM y
    capacidad (extract_capacity_and_clean). Quita marca (para no
    duplicarla), red (se vuelve a poner segun el match), colores y ruido
    de marketing. No hace falta que quede perfecto: best_match() tolera
    palabras extra siempre y cuando el modelo real este completo ahi."""
    upper = re.sub(r"[\(\)\[\]\u2014\u2013\-]", " ", cleaned_name.upper())
    upper = NET_RE.sub(" ", upper)
    brand_tokens = set(normalize(brand).split()) if brand else set()

    tokens = upper.split()
    cleaned = []
    for t in tokens:
        t_clean = re.sub(r"[^A-Z0-9]", "", t)
        if not t_clean:
            continue
        if t_clean in brand_tokens:
            continue
        if t_clean in COLOR_WORDS or t_clean in NOISE_WORDS:
            continue
        cleaned.append(t_clean)
    model_part = " ".join(cleaned)
    parts = [brand or "", model_part]
    if capacity:
        parts.append(capacity)
    return " ".join(p for p in parts if p)


def homologa_row(raw_name, given_brand, ref, by_brand):
    if not raw_name or not str(raw_name).strip():
        return None, None, None, "SIN_DATOS", ""

    raw_name = fix_raw_typos(str(raw_name).strip())
    brand = extract_brand(raw_name, given_brand)

    if brand is None:
        return None, None, None, "REVISAR", "No se reconocio la marca"
    if is_non_phone(raw_name, brand):
        return None, None, None, "NO_APLICA", "No es un celular (accesorio/equipo)"

    capacity, cleaned_name = extract_capacity_and_clean(raw_name)
    search_text = build_search_text(brand, cleaned_name, capacity)

    base, net, score = best_match(search_text, ref, by_brand)
    if not (base and net):
        fixed = fix_typos(search_text)
        base2, net2, _ = best_match(fixed, ref, by_brand)
        if base2 and net2:
            base, net = base2, net2

    if not net:
        clean = re.sub(r"\s*(4\.5G|5G|4G|3G|2G|LTE)\s*$", "", search_text, flags=re.IGNORECASE).strip()
        net = manual_lookup(clean) or manual_lookup(fix_typos(clean))

    if base and net:
        return f"{base} {net}", base, net, "OK", ""

    # No se encontro match confiable: entregamos lo mejor que se pudo armar
    # (marca + modelo + capacidad) para que la revision manual sea rapida.
    fallback_name = search_text
    if net:
        fallback_name = f"{search_text} {net}"
    return fallback_name, search_text, net, "REVISAR", "No hay match confiable en el catalogo"


# ---------------------------------------------------------------------------
# Deteccion de formato y flujo principal
# ---------------------------------------------------------------------------

def guess_format(df):
    """Intenta adivinar el formato por las columnas presentes. Devuelve
    'sears', 'coppel', o None si no esta claro."""
    cols = {c.strip().upper() for c in df.columns}
    if {"MARCA", "NOMBRE", "CAPACIDAD"}.issubset(cols):
        return "coppel"
    if "NOMBRE" in cols:
        return "sears"
    return None


def preguntar_formato(df, forzado=None):
    """Si se paso --formato por linea de comandos no pregunta nada. Si no,
    abre una ventana con dos botones (Sears / Coppel), sugiriendo el
    formato que adivino por las columnas."""
    if forzado:
        return forzado
    guess = guess_format(df)
    return preguntar_formato_popup(guess)


def columnas_requeridas(df, formato):
    cols = {c.strip().upper() for c in df.columns}
    if formato == "coppel" and not {"MARCA", "NOMBRE", "CAPACIDAD"}.issubset(cols):
        raise ValueError(
            "Elegiste 'coppel' pero el CSV no tiene las columnas 'Marca', "
            "'Nombre' y 'Capacidad'."
        )
    if formato == "sears" and "NOMBRE" not in cols:
        raise ValueError("Elegiste 'sears' pero el CSV no tiene una columna 'Nombre'.")


def read_csv_robusto(path):
    """Los CSVs de retailers a veces vienen en utf-8, a veces en
    latin-1/cp1252 (tipicos de exportaciones de Excel en Windows). Se
    prueban varias codificaciones hasta que una funcione."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"No pude leer '{path}' con ninguna codificacion conocida.")


def procesar(input_csv, referencia_xlsx, salida_csv=None, formato=None):
    input_path = Path(input_csv)
    df = read_csv_robusto(input_path)
    df.columns = [c.strip() for c in df.columns]

    fmt = preguntar_formato(df, forzado=formato)
    columnas_requeridas(df, fmt)
    print(f"Formato: {fmt}")

    print(f"Cargando catalogo de referencia: {referencia_xlsx} ...")
    ref, by_brand = load_reference(referencia_xlsx)
    print(f"  {len(ref)} modelos unicos en el catalogo.\n")

    nombre_col = next(c for c in df.columns if c.strip().upper() == "NOMBRE")
    marca_col = next((c for c in df.columns if c.strip().upper() == "MARCA"), None)

    homologados, sin_red_lista, redes, estados, notas = [], [], [], [], []
    for _, row in df.iterrows():
        raw_name = row[nombre_col]
        given_brand = row[marca_col] if marca_col else None
        homolog, sin_red, red, estado, nota = homologa_row(raw_name, given_brand, ref, by_brand)
        homologados.append(homolog)
        sin_red_lista.append(sin_red)
        redes.append(red)
        estados.append(estado)
        notas.append(nota)

    df["Nombre Homologado"] = homologados
    df["Nombre Homologado (sin red)"] = sin_red_lista
    df["Red"] = redes
    df["Estado"] = estados
    df["Nota"] = notas

    if salida_csv is None:
        sugerido = input_path.stem + "_homologado.csv"
        salida_csv = elegir_guardado_popup(sugerido)
        if not salida_csv:
            salida_csv = input_path.with_name(sugerido)
    df.to_csv(salida_csv, index=False, encoding="utf-8-sig")

    total = len(df)
    ok = int((df["Estado"] == "OK").sum())
    revisar = int((df["Estado"] == "REVISAR").sum())
    no_aplica = int((df["Estado"] == "NO_APLICA").sum())
    print(f"Total filas:        {total}")
    print(f"  OK (match confiable): {ok}")
    print(f"  REVISAR (revisar a mano): {revisar}")
    print(f"  NO_APLICA (no es celular): {no_aplica}")
    print(f"\nGuardado en: {salida_csv}")
    try:
        avisar_resultado_popup(total, ok, revisar, no_aplica, salida_csv)
    except Exception:
        pass  # sin entorno grafico disponible (ej. servidor/CI) - no pasa nada, ya se imprimio arriba


def main():
    parser = argparse.ArgumentParser(
        description="Homologa nombres de celulares (Sears/Coppel) y determina su red (4G/5G)."
    )
    parser.add_argument(
        "archivo",
        nargs="?",
        default=None,
        help="CSV de entrada (sears.csv o coppel.csv). Si no lo pasas, se abre una ventana para elegirlo.",
    )
    parser.add_argument(
        "--referencia",
        default=r"C:\Users\c90029859\Documents\diccionario2.xlsx",
        help=r"Ruta al archivo diccionario2.xlsx (default: C:\Users\c90029859\Documents\diccionario2.xlsx)",
    )
    parser.add_argument("--salida", default=None, help="Nombre del CSV de salida")
    parser.add_argument(
        "--formato",
        choices=["sears", "coppel"],
        default=None,
        help="Si ya sabes el formato, evita que el script pregunte (sears o coppel)",
    )
    args = parser.parse_args()

    archivo = args.archivo
    if not archivo:
        archivo = elegir_archivo_popup()
        if not archivo:
            print("No se eligio ningun archivo. Saliendo.")
            sys.exit(0)

    referencia = args.referencia
    if not Path(referencia).exists():
        referencia = elegir_referencia_popup()
        if not referencia:
            print("No se eligio el archivo de referencia. Saliendo.")
            sys.exit(1)

    procesar(archivo, referencia, args.salida, formato=args.formato)


if __name__ == "__main__":
    main()