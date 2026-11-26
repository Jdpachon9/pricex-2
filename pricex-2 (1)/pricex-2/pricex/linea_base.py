"""Línea base: interpretar el pedido SIN IA, con patrones de texto escritos a mano.

Se escribió mirando solo los 30 pedidos de diseño (datos/pedidos.csv) y patrones generales del español, y se
congeló antes de escribir las variantes (datos/variantes.csv). Su huella quedó en
resultados/sin_ia/linea_base_congelada.txt: si este archivo cambia, la comparación ya no es justa.
"""
import re
from datetime import timedelta

from .config import CIUDADES, FECHA_HOY
from .interpretar import COLORES, DIAS_SEMANA, vacia
from .texto import normalizar

PATRONES_PRODUCTO = [  # el orden importa: "cargador de celular" es un cargador, no un celular
    ("control", r"\bcontrol(es)?\b|\bdualsense\b"),
    ("cargador", r"\bcargador(es)?\b"),
    ("pulsera_inteligente", r"\bsmart ?band\b|\bpulsera inteligente\b"),
    ("lector_libros", r"\bkindle\b|\blector de libros\b"),
    ("tablet", r"\btablet\b|\btab s\d"),
    ("consola", r"\bplaystation\b|\bps ?5\b|\bxbox\b|\bconsola\b|\bnintendo\b"),
    ("memoria_microsd", r"\bmicro ?sd\b|\bmemoria sd\b"),
    ("disco_ssd", r"\bssd\b|\bdisco solido\b"),
    ("portatil", r"\bportatil(es)?\b|\blaptop\b|\bideapad\b|\bmacbook\b"),
    ("celular", r"\bcelular(es)?\b|\bcelu\b|\btelefono\b|\bsmartphone\b|\biphone\b|\bgalaxy [as]\d|\bredmi note\b"),
    ("televisor", r"\btelevisor(es)?\b|\btele\b|\btv\b"),
    ("monitor", r"\bmonitor(es)?\b"),
    ("audifonos", r"\baudifonos?\b|\bauriculares?\b|\bwh-?1000"),
    ("freidora_de_aire", r"\bfreidora\b|\bair ?fryer\b"),
    ("nevera", r"\bnevera\b|\bnevecon\b|\brefrigerador\b"),
    ("lavadora", r"\blavadora\b"),
    ("silla_oficina", r"\bsilla\b"),
    ("taladro", r"\btaladro\b"),
    ("cafetera", r"\bcafetera\b"),
]
PATRONES_MARCA = [
    ("Apple", r"\bapple\b|\biphone\b"), ("Samsung", r"\bsamsung\b|\bgalaxy\b"),
    ("Sony", r"\bsony\b|\bplaystation\b|\bps ?5\b|\bdualsense\b"), ("Xiaomi", r"\bxiaomi\b|\bredmi\b"),
    ("Amazon", r"\bamazon\b|\bkindle\b"), ("Lenovo", r"\blenovo\b|\bideapad\b"), ("HP", r"\bhp\b"),
    ("Asus", r"\basus\b"), ("Acer", r"\bacer\b"), ("Dell", r"\bdell\b"), ("LG", r"\blg\b"),
    ("Kalley", r"\bkalley\b"), ("Haceb", r"\bhaceb\b"), ("Mabe", r"\bmabe\b"), ("Oster", r"\boster\b"),
    ("Nespresso", r"\bnespresso\b"), ("Bosch", r"\bbosch\b"), ("DeWalt", r"\bdewalt\b"),
    ("Kingston", r"\bkingston\b"), ("SanDisk", r"\bsandisk\b"), ("JBL", r"\bjbl\b"), ("Motorola", r"\bmotorola\b"),
]


def variante(texto):
    t = (texto or "").strip()
    return {"+": "+", "plus": "+", "ultra": " Ultra", "fe": " FE", "pro": " Pro", "pro max": " Pro Max",
            "fe+": " FE+", "fe plus": " FE+", "slim": " Slim", "edge": " Edge", "pro+": " Pro+"}.get(t, "")


def modelo_sin_ia(t):
    m = re.search(r"\b(?:galaxy )?tab (s\d{1,2})( fe\+| fe plus| fe| ultra|\+)?", t)
    if m:
        return f"Galaxy Tab {m.group(1).upper()}{variante(m.group(2))}"
    m = re.search(r"\b(?:galaxy|samsung) ([sa]\d{2})(\+| plus| ultra| fe)?", t)
    if m:
        return f"Galaxy {m.group(1).upper()}{variante(m.group(2))}"
    m = re.search(r"\biphone (\d{2})( pro max| pro| plus)?", t)
    if m:
        return f"iPhone {m.group(1)}{variante(m.group(2))}"
    m = re.search(r"\bwh-? ?1000 ?xm ?(\d)", t)
    if m:
        return f"WH-1000XM{m.group(1)}"
    m = re.search(r"\b(?:playstation|ps) ?5( slim| pro)?", t)
    if m:
        return f"PlayStation 5{variante(m.group(1))}"
    m = re.search(r"\bdualsense( edge)?", t)
    if m:
        return f"DualSense{variante(m.group(1))}"
    m = re.search(r"\bredmi note (\d{2})( pro\+| pro)?", t)
    if m:
        return f"Redmi Note {m.group(1)}{variante(m.group(2))}"
    m = re.search(r"\bsmart ?band (\d{1,2})( pro)?", t)
    if m:
        return f"Smart Band {m.group(1)}{variante(m.group(2))}"
    m = re.search(r"\bkindle( paperwhite)?( signature)?", t)
    if m:
        return "Kindle" + (" Paperwhite" if m.group(1) else "") + (" Signature Edition" if m.group(2) else "")
    m = re.search(r"\bideapad( slim)? (\d)", t)
    if m:
        return f"IdeaPad{' Slim' if m.group(1) else ''} {m.group(2)}"
    return None


def monto(cifra, unidad):
    """'2,5' + 'millones' -> 2500000; '1.800.000' -> 1800000; '400' + 'lucas' -> 400000."""
    unidad = unidad or ""
    if re.fullmatch(r"\d+[.,]\d{1,2}", cifra) and unidad:
        valor = float(cifra.replace(",", "."))
    else:
        valor = float(re.sub(r"[.,]", "", cifra))
    if unidad.startswith(("millon", "palo")):
        valor *= 1_000_000
    elif unidad in ("mil", "lucas", "luca", "k"):
        valor *= 1000
    return int(valor) if valor >= 10000 else None


def proximo(dia_semana, hoy):
    adelante = (DIAS_SEMANA[dia_semana] - hoy.weekday()) % 7 or 7
    return hoy + timedelta(days=adelante)


def interpretar_sin_ia(texto, hoy=FECHA_HOY):
    """Interpreta el pedido con patrones de texto. No entiende: reconoce palabras."""
    t = normalizar(texto)
    r = vacia()
    r["condicion"] = "nuevo"
    if re.search(r"\[tarjeta\]|\b(con|de) mi tarjeta\b|\bpag(alo|amelo|ame)\b|\bcompra(lo|melo)? tu\b", t):
        r.update(accion="aclarar", motivo_aclaracion="pagos", condicion=None)
        return r
    if re.search(r"\botras? tiendas?\b|\botros? almacen(es)?\b|\botras? paginas?\b", t):
        r.update(accion="aclarar", motivo_aclaracion="otra_tienda", condicion=None)
        return r
    r["producto"] = next((p for p, patron in PATRONES_PRODUCTO if re.search(patron, t)), None)
    r["marca"] = next((m for m, patron in PATRONES_MARCA if re.search(patron, t)), None)
    r["modelo"] = modelo_sin_ia(t)

    m = re.search(r"(\d{1,3}) ?(?:gb|gigas?)? (?:de )?ram\b", t)
    if m:
        r["ram_gb"] = int(m.group(1))
    sin_ram = re.sub(r"\d{1,3} ?(?:gb|gigas?)? (?:de )?ram\b", " ", t)
    m = (re.search(r"(\d) ?(?:tb|teras?)\b", sin_ram))
    if m:
        r["almacenamiento_gb"] = int(m.group(1)) * 1000
    else:
        m = (re.search(r"(\d{2,4}) ?(?:gb|gigas?)\b", sin_ram)
             or re.search(r"(\d{3,4}) (?:gb )?de (?:disco|almacenamiento|ssd)\b", sin_ram))
        if not m and r["producto"] in ("celular", "tablet"):
            m = re.search(r"\bde (64|128|256|512)\b", sin_ram)
        if m:
            r["almacenamiento_gb"] = int(m.group(1))
    m = re.search(r"(\d{2,3}) ?(?:pulgadas|pulg)\b", t)
    if m:
        r["pulgadas"] = int(m.group(1))
    m = re.search(r"(\d+(?:[.,]\d+)?) ?(?:litros|lts?|l)\b", t)
    if m:
        litros = float(m.group(1).replace(",", "."))
        r["litros"] = int(litros) if litros == int(litros) else litros
    m = re.search(r"(\d{1,2}) ?(?:kilos|kg)\b", t)
    if m:
        r["kilos"] = int(m.group(1))
    m = re.search(r"(\d{1,3}) ?(?:w|watts|vatios)\b", t)
    if m:
        r["potencia_w"] = int(m.group(1))
    m = re.search(r"\b(" + "|".join(COLORES) + r")\b", t)
    if m:
        r["color"] = COLORES[m.group(1)]
    if re.search(r"lector de discos?|con discos?\b|edicion (?:fisica|con disco)", t):
        r["edicion"] = "disco"
    elif re.search(r"\bdigital\b", t):
        r["edicion"] = "digital"
    if re.search(r"reacondicionad", t):
        r["condicion"] = "reacondicionado"
    elif re.search(r"\busad[oa]s?\b|segunda mano", t):
        r["condicion"] = "usado"
    m = re.search(r"(?:maximo|max|hasta|no pase de|menos de|tope de|presupuesto de)\s+(?:de\s+)?\$?\s*"
                  r"(\d+(?:[.,]\d+)*)\s*(millones|millon|palos|palo|mil|lucas|luca)?", t)
    if m:
        r["presupuesto_max"] = monto(m.group(1), m.group(2))
    if re.search(r"\bpasado manana\b", t):
        r["fecha_limite"] = (hoy + timedelta(days=2)).isoformat()
    elif re.search(r"\bmanana\b", t):
        r["fecha_limite"] = (hoy + timedelta(days=1)).isoformat()
    else:
        m = re.search(r"\bantes del? (" + "|".join(DIAS_SEMANA) + r")\b", t)
        if m:
            r["fecha_limite"] = (proximo(m.group(1), hoy) - timedelta(days=1)).isoformat()
        else:
            m = re.search(r"\bpara el (" + "|".join(DIAS_SEMANA) + r")\b", t)
            if m:
                r["fecha_limite"] = proximo(m.group(1), hoy).isoformat()
    r["ciudad"] = next((c for c in CIUDADES if re.search(r"\b" + normalizar(c) + r"\b", t)), None)
    r["accion"] = "recomendar"
    return r
