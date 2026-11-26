"""Comprobaciones literales: ¿el dato que propone un agente sale tal cual del texto?

El código no interpreta. Solo revisa que lo que propone la IA tenga respaldo literal en un texto: el pedido de la
persona (para el Revisor) o el título de la publicación (para el Lector de atributos). Si no lo tiene, la
propuesta no se usa.

valores(campo, texto) devuelve los valores que ese texto respalda para un campo:
    valores("presupuesto_max", "que no pase de 2 palos")        -> {2000000}
    valores("almacenamiento_gb", "Redmi Note 14 256GB 8GB RAM") -> {256}   (el 8 es de la RAM)
"""
import re
from datetime import date, timedelta

from .config import CIUDADES
from .interpretar import COLORES, DIAS_SEMANA
from .reglas import ALIAS_COLOR, canon_color
from .texto import MESES, normalizar

CIFRA = r"(\d+(?:[.,]\d+)*)"
MESES_RE = "|".join(MESES)


def a_numero(token):
    """'1.800.000' -> 1800000, '2,5' -> 2.5, '3.5' -> 3.5, '16' -> 16."""
    token = str(token).strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", token):
        return int(token.replace(".", ""))
    if "," in token:
        valor = float(token.replace(".", "").replace(",", "."))
    elif "." in token:
        valor = float(token)
    else:
        return int(token)
    return int(valor) if valor == int(valor) else valor


def como_numero(valor):
    """El valor que propuso un agente, como número: 2000000, '2000000' y '2.000.000' dan lo mismo."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return valor
    try:
        return a_numero(str(valor).replace(" ", "").replace("$", ""))
    except ValueError:
        return None


def redondear(valor):
    valor = round(valor, 2)
    return int(valor) if valor == int(valor) else valor


# Cada campo numérico tiene sus patrones: (expresión, multiplicador). El número va en el primer grupo.
PATRONES = {
    "presupuesto_max": [
        (CIFRA + r"\s*(?:millones|millon|palos?|melones?)\b", 1_000_000),
        (CIFRA + r"\s*(?:mil|lucas?|k)\b", 1_000),
        (r"(\d{1,3}(?:\.\d{3})+)(?![.,]?\d)", 1),
        (r"\$\s?(\d+)", 1),
        (r"(?<![\d.,])(\d{5,})(?![\d.,])", 1),
    ],
    "almacenamiento_gb": [
        (CIFRA + r"\s*(?:tb|teras?)\b", 1000),
        (r"(\d+)\s*(?:gb|gigas?)\b(?!\s*(?:de\s*)?ram)", 1),
        (r"(\d{2,4})\s*g\b(?!\s*(?:de\s*)?ram)", 1),          # '256g' sí; '5G' (la red) no
        (r"(\d+)\s*(?:de\s+)?(?:disco|almacenamiento|ssd|memoria interna)\b", 1),
        (r"\bde\s+(16|32|64|128|256|512)\b(?!\s*(?:gb|gigas?|g)?\s*(?:de\s*)?ram)", 1),
    ],
    "ram_gb": [(r"(\d+)\s*(?:gb|gigas?|g)?\s*(?:de\s*)?ram\b", 1)],
    "pulgadas": [
        (CIFRA + r"\s*(?:pulgadas|pulgada|pulg\b|\"|”|'')", 1),
        (r"\b(?:tv|tele|televisor|pantalla|monitor)\s+(?:de\s+)?(\d{2})\b(?![.,]?\d)", 1),
    ],
    "litros": [(CIFRA + r"\s*(?:litros?|lts?|l)\b", 1)],
    "kilos": [(CIFRA + r"\s*(?:kilos?|kgs?)\b", 1)],
    "potencia_w": [(r"(\d+)\s*(?:w|vatios?|watts?)\b", 1)],
}
PALABRAS = {
    "presupuesto_max": {"un millon": 1_000_000, "un palo": 1_000_000, "un melon": 1_000_000, "medio millon": 500_000},
    "almacenamiento_gb": {"una tera": 1000, "un tera": 1000},
}
CONDICIONES = [("reacondicionado", r"reacondicionad|refurbished|renovad"), ("usado", r"\busad[oa]s?\b|de segunda")]
COLORES_EN_INGLES = {"black": "negro", "white": "blanco", "blue": "azul", "red": "rojo", "green": "verde",
                     "gray": "gris", "grey": "gris", "silver": "plateado", "gold": "dorado", "pink": "rosado",
                     "purple": "morado"}
CAMPOS_NUMERICOS = list(PATRONES)


def valores(campo, texto, hoy=None):
    """Los valores que el texto respalda para el campo. Conjunto vacío si no respalda ninguno."""
    t = normalizar(texto)
    if campo in PATRONES:
        encontrados = set()
        for patron, multiplicador in PATRONES[campo]:
            for m in re.finditer(patron, t):
                encontrados.add(redondear(a_numero(m.group(1)) * multiplicador))
        for frase, cifra in PALABRAS.get(campo, {}).items():
            if re.search(r"\b" + frase + r"\b", t):
                encontrados.add(cifra)
        return encontrados
    if campo == "color":
        return {canon_color(COLORES_EN_INGLES.get(p, p)) for p in re.findall(r"[a-z]+", t)
                if p in COLORES or p in ALIAS_COLOR or p in COLORES_EN_INGLES}
    if campo == "edicion":
        encontrados = set()
        if re.search(r"\bdiscos?\b|\bfisica\b", t):
            encontrados.add("disco")
        if re.search(r"\bdigital\b", t):
            encontrados.add("digital")
        return encontrados
    if campo == "condicion":
        encontrados = {estado for estado, patron in CONDICIONES if re.search(patron, t)}
        return encontrados or {"nuevo"}  # si no dice nada, es nuevo
    if campo == "ciudad":
        return {c for c in CIUDADES if re.search(r"\b" + re.escape(normalizar(c)) + r"\b", t)}
    if campo == "fecha_limite":
        return fechas(t, hoy)
    return set()


def fechas(t, hoy):
    """Fechas que respalda una frase: «mañana», «antes del viernes» (jueves o viernes), «el 28», «28 de noviembre»."""
    if hoy is None:
        return set()
    encontradas = set()
    if re.search(r"pasado\s+manana", t):
        encontradas.add(hoy + timedelta(days=2))
    elif re.search(r"\bmanana\b", t):
        encontradas.add(hoy + timedelta(days=1))
    if re.search(r"\bhoy\b", t):
        encontradas.add(hoy)
    for nombre, numero in DIAS_SEMANA.items():
        for m in re.finditer(r"\b" + nombre + r"\b", t):
            dia = hoy + timedelta(days=(numero - hoy.weekday()) % 7 or 7)
            encontradas.add(dia)
            if re.search(r"antes\s+(?:del?|el)\s*$", t[:m.start()]):
                encontradas.add(dia - timedelta(days=1))
    for m in re.finditer(r"\bel\s+(\d{1,2})\b(?!\s*(?:gb|pulgadas|litros|de\s+ram))|\b(\d{1,2})\s+de\s+(?:" + MESES_RE + ")", t):
        numero = int(m.group(1) or m.group(2))
        for meses in (0, 1):
            mes, anio = hoy.month + meses, hoy.year
            if mes > 12:
                mes, anio = mes - 12, anio + 1
            try:
                dia = date(anio, mes, numero)
            except ValueError:
                continue
            if dia >= hoy:
                encontradas.add(dia)
                break
    return {d.isoformat() for d in encontradas if d >= hoy}


def iguales_num(a, b):
    a, b = como_numero(a), como_numero(b)
    return a is not None and b is not None and abs(float(a) - float(b)) < 0.01


def respalda(campo, valor, texto, hoy=None):
    """¿El texto respalda literalmente este valor para este campo?"""
    if valor in (None, ""):
        return False
    t = normalizar(texto)
    if campo in CAMPOS_NUMERICOS:
        return any(iguales_num(valor, v) for v in valores(campo, t))
    if campo == "color":
        return canon_color(valor) in valores("color", t)
    if campo == "ciudad":
        return any(normalizar(c) == normalizar(valor) for c in valores("ciudad", t))
    if campo == "fecha_limite":
        return str(valor)[:10] in valores("fecha_limite", t, hoy)
    return normalizar(valor) in valores(campo, t, hoy)


def numeros(texto):
    """Las cifras escritas con dígitos: 'S26 de 256 GB, 4 millones' -> {'26', '256', '4'}."""
    return set(re.findall(r"\d+", texto or ""))


# ---------------------------------------------------------------- reglas de aceptación de cada agente
# El Revisor solo corrige datos que se pueden comprobar letra por letra: cifras, fecha, ciudad, color, edición y
# estado. Producto, marca y modelo no: la gente los escribe de mil formas («la play 5») y el código no puede
# comprobarlos sin interpretarlos, que es justo el trabajo del Intérprete.
CORREGIBLES = ["almacenamiento_gb", "ram_gb", "pulgadas", "litros", "kilos", "potencia_w", "presupuesto_max",
               "fecha_limite", "ciudad", "color", "edicion", "condicion"]
QUITABLES = ["color", "edicion"]
LEIBLES = ["almacenamiento_gb", "ram_gb", "pulgadas", "litros", "kilos", "potencia_w", "color", "edicion"]
CALIFICADORES = re.compile(r"\b(ampliable|expandible|hasta|compatible|compatibles|soporta|admite|para|max|maximo|"
                           r"opcional|extra|adicional|repuesto|funda|estuche)\b")


def mismo_valor(campo, a, b):
    if campo in CAMPOS_NUMERICOS:
        return iguales_num(a, b)
    if campo == "color":
        return canon_color(a) == canon_color(b)
    return normalizar(a)[:10] == normalizar(b)[:10] if campo == "fecha_limite" else normalizar(a) == normalizar(b)


def aceptar_correccion(campo, valor, evidencia, texto, interpretacion, hoy):
    """Regla del Revisor: devuelve (aceptada, motivo). Solo puede llenar un dato vacío o corregir uno que no tiene
    respaldo en el pedido, y siempre citando el pedazo exacto del pedido."""
    if campo not in CORREGIBLES:
        return False, "el revisor solo corrige cifras, fecha, ciudad, color, edición y estado"
    actual = interpretacion.get(campo)
    if valor in (None, "", "null"):
        if campo not in QUITABLES:
            return False, "solo se pueden quitar el color o la edición"
        if actual in (None, ""):
            return False, "ese dato ya estaba vacío"
        if respalda(campo, actual, texto, hoy):
            return False, f"el pedido sí dice {actual}"
        return True, "quitado: el pedido no lo dice"
    evidencia_n = normalizar(evidencia)
    if len(evidencia_n) < 2 or evidencia_n not in normalizar(texto):
        return False, "la evidencia no aparece en el pedido"
    if not respalda(campo, valor, evidencia, hoy):
        return False, "la evidencia no respalda ese valor"
    if actual not in (None, "") and mismo_valor(campo, actual, valor):
        return False, "no cambia nada"
    if actual not in (None, "") and respalda(campo, actual, texto, hoy):
        return False, f"lo que entendió el intérprete ({actual}) ya tiene respaldo en el pedido"
    return True, "aceptada"


def aceptar_lectura(pub, campo, valor, evidencia, pedido):
    """Regla del Lector: devuelve (aceptada, motivo). El dato tiene que estar escrito en el título, sin condiciones
    y sin ambigüedad, y tiene que ser un dato que la persona pidió y que la ficha no trae."""
    if campo not in LEIBLES:
        return False, "no es un dato que se pueda leer del título"
    if pedido.get(campo) in (None, ""):
        return False, "no es un dato que la persona pidió"
    if pub.get(campo) not in (None, ""):
        return False, "la ficha técnica ya trae ese dato"
    titulo = normalizar(pub.get("titulo"))
    evidencia_n = normalizar(evidencia)
    if len(evidencia_n) < 2 or evidencia_n not in titulo:
        return False, "la evidencia no está en el título"
    antes = " ".join(titulo[:titulo.find(evidencia_n)].split()[-2:])
    if CALIFICADORES.search(evidencia_n) or CALIFICADORES.search(antes):
        return False, "el título lo dice con condiciones (ampliable, compatible, hasta…)"
    if len(valores(campo, titulo)) > 1:
        return False, "el título trae más de un valor para ese dato"
    if not respalda(campo, valor, evidencia):
        return False, "la evidencia no respalda ese valor"
    return True, "aceptada"
