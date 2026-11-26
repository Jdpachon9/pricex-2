"""De dónde salen las publicaciones.

- desde_api() traduce una publicación con la forma de la API de Mercado Libre al formato interno.
- CatalogoSimulado busca sobre el catálogo congelado de datos/catalogo_simulado.json (versión 1).
- ConectorMercadoLibre es el conector de la versión 2, contra la API real. Está escrito pero NO está probado.
"""
import json
import re
from datetime import datetime
from pathlib import Path

from .config import DOMINIO_A_PRODUCTO, MAX_RESULTADOS_BUSQUEDA, PRODUCTOS
from .texto import normalizar, palabras

CONDICIONES = {"new": "nuevo", "used": "usado", "refurbished": "reacondicionado"}
ATRIBUTOS_API = {
    "BRAND": "marca", "MODEL": "modelo", "INTERNAL_MEMORY": "almacenamiento_gb",
    "SSD_DATA_STORAGE_CAPACITY": "almacenamiento_gb", "STORAGE_CAPACITY": "almacenamiento_gb", "RAM": "ram_gb",
    "DISPLAY_SIZE": "pulgadas", "CAPACITY": "litros", "WASHING_CAPACITY": "kilos", "POWER": "potencia_w",
    "COLOR": "color", "EDITION": "edicion",
}
COLORES = {"negro", "negra", "blanco", "blanca", "azul", "rojo", "roja", "morado", "morada", "verde", "gris",
           "plateado", "dorado", "rosado", "rosada", "grafito", "beige", "amarillo", "naranja"}
PALABRAS_VACIAS = {"de", "del", "la", "el", "los", "las", "con", "para", "por", "una", "uno", "unos", "que", "sin",
                   "gb", "tb", "ram", "original", "originales", "nuevo", "nueva", "pulgadas"} | COLORES


def numero(valor):
    """'256 GB' -> 256, '1 TB' -> 1000, '3,5 L' -> 3.5, '55"' -> 55."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(tb)?", normalizar(valor))
    if not m:
        return None
    cifra = float(m.group(1).replace(",", "."))
    if m.group(2):
        cifra *= 1000
    return int(cifra) if cifra == int(cifra) else cifra


def desde_api(item):
    """Traduce una publicación de la API al formato con el que trabajan las reglas."""
    pub = {campo: None for campo in set(ATRIBUTOS_API.values())}
    for atributo in item.get("attributes") or []:
        campo = ATRIBUTOS_API.get(atributo.get("id"))
        valor = atributo.get("value_name")
        if not campo or valor in (None, ""):
            continue
        if campo in ("marca", "modelo"):
            pub[campo] = str(valor)
        elif campo in ("color", "edicion"):
            pub[campo] = normalizar(valor)
        else:
            pub[campo] = numero(valor)
    envio = item.get("shipping") or {}
    vendedor = item.get("seller") or {}
    reputacion = vendedor.get("seller_reputation") or {}
    cuotas = item.get("installments") or {}
    opiniones = item.get("reviews") or {}
    pub.update({
        "id": item["id"],
        "titulo": item.get("title", ""),
        "dominio": item.get("domain_id"),
        "producto": DOMINIO_A_PRODUCTO.get(item.get("domain_id")),
        "condicion": CONDICIONES.get(item.get("condition"), item.get("condition")),
        "precio": item.get("price"),
        "costo_envio": envio.get("cost") or 0,
        "envio_gratis": bool(envio.get("free_shipping")),
        "entrega_dias": envio.get("eta_days"),
        "tienda_oficial": item.get("official_store_id") is not None,
        "nombre_tienda": item.get("official_store_name"),
        "vendedor": vendedor.get("nickname"),
        "reputacion": reputacion.get("level_id"),
        "ventas": (reputacion.get("transactions") or {}).get("completed") or 0,
        "cuotas": cuotas.get("quantity") if cuotas.get("rate") == 0 else None,
        "calificacion": opiniones.get("rating_average"),
        "opiniones": opiniones.get("total") or 0,
        "enlace": item.get("permalink"),
        "descripcion": item.get("description", ""),
    })
    pub["textos_libres"] = " ".join([pub["titulo"], pub["descripcion"] or ""] +
                                    [str(a.get("value_name", "")) for a in item.get("attributes") or []])
    return pub


def armar_consulta(interpretacion):
    """Convierte la interpretación en el texto que se le manda al buscador."""
    i = interpretacion
    partes = list(PRODUCTOS[i["producto"]][2]) if i.get("producto") in PRODUCTOS else []
    partes += [i.get("marca") or "", i.get("modelo") or ""]
    if i.get("almacenamiento_gb"):
        partes.append(f"{i['almacenamiento_gb']} GB")
    for campo, unidad in (("ram_gb", "GB RAM"), ("pulgadas", "pulgadas"), ("litros", "L"), ("kilos", "kg"),
                          ("potencia_w", "W")):
        if i.get(campo):
            partes.append(f"{i[campo]:g} {unidad}" if isinstance(i[campo], float) else f"{i[campo]} {unidad}")
    partes += [i.get("color") or "", i.get("edicion") or ""]
    return " ".join(p for p in partes if p).strip()


def puntaje(consulta, titulo):
    """Cuántas palabras de la consulta aparecen en el título. Las palabras distintivas valen doble."""
    fuertes, debiles = set(), set()
    for t in palabras(consulta):
        (fuertes if len(t) >= 3 and re.search(r"[a-z]", t) and t not in PALABRAS_VACIAS else debiles).add(t)
    en_titulo = set(palabras(titulo))
    coinciden = fuertes & en_titulo
    return (2 * len(coinciden) + len(debiles & en_titulo)) if coinciden else 0


class CatalogoSimulado:
    """Versión 1: busca sobre un catálogo congelado, como si fuera la API."""

    def __init__(self, ruta):
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        self.congelado_el = datos.get("congelado_el")
        self.crudo = {item["id"]: item for item in datos["results"]}
        self.publicaciones = [desde_api(item) for item in datos["results"]]
        self.por_id = {p["id"]: p for p in self.publicaciones}

    def buscar(self, consulta, limite=MAX_RESULTADOS_BUSQUEDA):
        """Como un buscador: devuelve lo que se parece a la consulta, incluidos accesorios y trampas."""
        encontrados = [(puntaje(consulta, p["titulo"]), p) for p in self.publicaciones]
        encontrados = [(s, p) for s, p in encontrados if s > 0]
        encontrados.sort(key=lambda x: (-x[0], x[1]["precio"], x[1]["id"]))
        return [p for _, p in encontrados[:limite]]


class ConectorMercadoLibre:
    """Versión 2 (escrito, sin probar): busca en la API real de Mercado Libre Colombia.

    Para usarlo hace falta una aplicación registrada en el portal de desarrolladores de Mercado Libre: con su
    Client ID y su Client Secret se obtiene un token de acceso, que va en cada consulta como
    'Authorization: Bearer <token>'. Antes de usarlo hay que confirmar en la documentación oficial los nombres
    de los campos y completar dos datos que la búsqueda no trae: la fecha de entrega para el código postal de la
    persona y las opiniones del producto. Sin esos dos datos, las reglas descartan por "sin dato" lo que pida
    fecha de entrega y no pueden ordenar por calificación.

    Cada respuesta se guarda en disco ("congelar"): los precios cambian todo el día, y para evaluar el asistente
    todos tienen que comparar contra los mismos resultados.
    """

    URL_BUSQUEDA = "https://api.mercadolibre.com/sites/MCO/search"

    def __init__(self, token, carpeta_copias="resultados/busquedas_congeladas", sesion=None):
        self.token = token
        self.carpeta_copias = Path(carpeta_copias)
        self.sesion = sesion

    def buscar(self, consulta, limite=50):
        import requests  # solo se necesita en la versión 2

        cliente = self.sesion or requests
        respuesta = cliente.get(self.URL_BUSQUEDA, params={"q": consulta, "limit": limite},
                                headers={"Authorization": f"Bearer {self.token}"}, timeout=20)
        respuesta.raise_for_status()
        datos = respuesta.json()
        self.carpeta_copias.mkdir(parents=True, exist_ok=True)
        marca_tiempo = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre = re.sub(r"[^a-z0-9]+", "_", normalizar(consulta))[:40]
        (self.carpeta_copias / f"{marca_tiempo}_{nombre}.json").write_text(
            json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        return [desde_api(item) for item in datos.get("results", [])]
