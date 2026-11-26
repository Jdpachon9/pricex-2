"""Paso 3: escribir la respuesta para la persona.

Las opciones y su orden ya los decidieron las reglas. Aquí solo se redacta el mensaje, de una de dos formas:
- con una plantilla fija (siempre disponible, sin IA);
- con el modelo de IA, que redacta más natural. Su mensaje pasa por verificar_mensaje(): si trae una cifra que
  no está en los datos, un enlace o no menciona la opción elegida, se descarta y se usa la plantilla.

Al modelo nunca le llega texto escrito por los vendedores (títulos, descripciones, apodos): solo datos
estructurados y nombres armados con la marca, el modelo y los atributos. Así una publicación no le puede dar
órdenes.
"""
import json
import re
import time

from .config import DIFERENCIA_EMPATE_PRECIO, FECHA_HOY, MIN_OPINIONES, PRODUCTOS
from .reglas import MOTIVOS, texto_valor
from .texto import decimal, fecha_larga, pesos

REPUTACION = {"5_green": "verde", "4_light_green": "verde claro", "3_yellow": "amarilla"}
ORDEN_DETALLES = ["pulgadas", "ram_gb", "almacenamiento_gb", "litros", "kilos", "potencia_w"]
ARTICULO = {"celular": "el", "portatil": "el", "freidora_de_aire": "la", "televisor": "el", "audifonos": "los",
            "consola": "la", "tablet": "la", "lector_libros": "el", "nevera": "la", "lavadora": "la",
            "silla_oficina": "la", "taladro": "el", "cafetera": "la", "disco_ssd": "el", "memoria_microsd": "la",
            "cargador": "el", "monitor": "el", "pulsera_inteligente": "la", "control": "el"}
FRASES_MOTIVO = {  # (una, varias)
    "texto_sospechoso": ("traía instrucciones escondidas para el asistente", "traían instrucciones escondidas para el asistente"),
    "otro_producto": ("era otro producto o un accesorio", "eran otros productos o accesorios"),
    "otra_marca": ("era de otra marca", "eran de otra marca"),
    "otro_modelo": ("era otro modelo", "eran otro modelo"),
    "otra_especificacion": ("tenía otra capacidad, tamaño o edición", "tenían otra capacidad, tamaño o edición"),
    "otro_color": ("era de otro color", "eran de otro color"),
    "sin_dato": ("no confirmaba un dato que pediste", "no confirmaban un dato que pediste"),
    "otro_estado": ("no estaba en el estado que pediste", "no estaban en el estado que pediste"),
    "vendedor_no_confiable": ("era de un vendedor con mala reputación o pocas ventas",
                              "eran de vendedores con mala reputación o pocas ventas"),
    "llega_tarde": ("no llegaba a tiempo", "no llegaban a tiempo"),
    "sobre_presupuesto": ("pasaba de tu presupuesto", "pasaban de tu presupuesto"),
}
CERCANOS = ["otro_color", "otra_especificacion", "otro_modelo", "vendedor_no_confiable", "llega_tarde", "otro_estado",
            "sin_dato"]


def nombre_publicacion(pub):
    """'Samsung Galaxy S26 (256 GB, negro)'. Se arma con atributos, nunca con el título del vendedor."""
    base = f"{pub.get('marca') or ''} {pub.get('modelo') or ''}".strip()
    if pub.get("producto") not in (None, "celular"):
        base = f"{PRODUCTOS[pub['producto']][1].capitalize()} {base}"
    detalles = [texto_valor(c, pub[c]) for c in ORDEN_DETALLES if pub.get(c)]
    if pub.get("edicion"):
        detalles.append(f"edición {pub['edicion']}")
    if pub.get("color"):
        detalles.append(pub["color"])
    return base + (f" ({', '.join(detalles)})" if detalles else "")


def texto_vendedor(o):
    if o.get("tienda_oficial"):
        return "tienda oficial de la marca"
    ventas = f"{o.get('ventas', 0):,}".replace(",", ".")
    return f"vendedor con reputación {REPUTACION.get(o.get('reputacion'), 'sin dato')} ({ventas} ventas)"


def texto_calificacion(o):
    if o.get("calificacion") is None or o.get("opiniones", 0) < MIN_OPINIONES:
        return f"sin suficientes opiniones ({o.get('opiniones', 0)})"
    opiniones = f"{o['opiniones']:,}".replace(",", ".")
    return f"{decimal(o['calificacion'])} estrellas con {opiniones} opiniones"


def nombre_en_frase(pub):
    """'el portátil Asus Vivobook 15 (16 GB de RAM, 512 GB)': con artículo y en minúscula, para una oración."""
    nombre = nombre_publicacion(pub)
    if pub.get("producto") not in (None, "celular"):
        nombre = nombre[0].lower() + nombre[1:]
    return f"{ARTICULO.get(pub.get('producto'), 'el')} {nombre}"


def resumen_descartes(conteo, maximo=3):
    partes = sorted(conteo.items(), key=lambda x: (-x[1], list(MOTIVOS).index(x[0])))
    frases = [f"{n} {FRASES_MOTIVO[m][0 if n == 1 else 1]}" for m, n in partes[:maximo]]
    otras = sum(n for _, n in partes[maximo:])
    if otras:
        frases.append(f"{otras} por otras razones")
    return frases[0] if len(frases) == 1 else ", ".join(frases[:-1]) + " y " + frases[-1]


def por_que_la_primera(decision, pedido):
    razon, opciones = decision["razon"], decision["opciones"]
    if not opciones:
        return None
    primera = opciones[0]
    if razon in ("tienda_oficial", "llega_antes"):
        barata = next((o for o in opciones if o["id"] == decision["mas_barata"]),
                      min(opciones, key=lambda o: o["total"]))
        diferencia = primera["total"] - barata["total"]
        porcentaje = decimal(100 * diferencia / barata["total"])
        motivo = "es tienda oficial" if razon == "tienda_oficial" else "llega antes"
        return (f"Cuesta {pesos(diferencia)} más ({porcentaje} %) que la más barata, pero la diferencia es menor al "
                f"{round(100 * DIFERENCIA_EMPATE_PRECIO)} % y {motivo}.")
    if razon == "menor_precio":
        return "Es la de menor precio total entre las que cumplen todo lo que pediste."
    if razon == "mejor_calificada":
        bajo, alto = decision["rango_calificacion"]
        rango = decimal(alto) if bajo == alto else f"de {decimal(bajo)} a {decimal(alto)}"
        return (f"Está entre las mejor calificadas por los compradores ({rango} estrellas) y es la de menor precio "
                f"total de ese grupo.")
    if razon == "menor_precio_sin_calificaciones":
        return "Ninguna tiene suficientes opiniones para comparar calificaciones, así que gana el menor precio total."
    if razon == "mas_cercana_al_presupuesto":
        exceso = primera["total"] - pedido["presupuesto_max"]
        return (f"Ninguna cabe en tu presupuesto de {pesos(pedido['presupuesto_max'])}; esta es la más cercana: "
                f"{pesos(exceso)} por encima.")
    return None


def mas_cercanas(decision, maximo=3):
    """Las descartadas que más se parecen a lo pedido, con su motivo: sirven cuando no hay resultados."""
    vistas, cercanas = set(), []
    for d in decision["descartes"]:
        if d["motivo"] not in CERCANOS or "pub" not in d:
            continue
        nombre = nombre_publicacion(d["pub"])
        if nombre in vistas:
            continue
        vistas.add(nombre)
        cercanas.append(f"{nombre}: {d['detalle']}")
        if len(cercanas) == maximo:
            break
    return cercanas


def datos_para_explicar(texto_pedido, pedido, decision, hoy=FECHA_HOY):
    """Lo único que ve el modelo para redactar: datos estructurados, sin texto de los vendedores."""
    opciones = []
    for o in decision["opciones"]:
        opciones.append({
            "puesto": o["puesto"], "nombre": nombre_publicacion(o), "nombre_en_frase": nombre_en_frase(o),
            "precio": pesos(o["precio"]), "envio": "gratis" if not o.get("costo_envio") else pesos(o["costo_envio"]),
            "total": pesos(o["total"]), "llega": fecha_larga(o["llega"]) if o.get("llega") else "sin fecha",
            "vendedor": texto_vendedor(o), "cuotas": f"{o['cuotas']} cuotas sin interés" if o.get("cuotas") else None,
            "calificacion": texto_calificacion(o),
        })
    criterio = ("Todas son el mismo modelo, así que se ordenan por precio total (precio más envío)."
                if decision["pedido_exacto"] else
                "Son productos distintos: primero la calificación de los compradores (con 30 opiniones o más) y, "
                "entre las mejor calificadas, el menor precio total.")
    exceso = None
    if decision["situacion"] == "fuera_de_presupuesto" and decision["opciones"]:
        exceso = pesos(decision["opciones"][0]["total"] - pedido["presupuesto_max"])
    return {
        "fecha_hoy": f"{fecha_larga(hoy)} de {hoy.year}",
        "pedido": texto_pedido,
        "situacion": decision["situacion"],
        "mismo_modelo": decision["pedido_exacto"],
        "criterio": criterio,
        "por_que_la_primera": por_que_la_primera(decision, pedido),
        "opciones": opciones,
        "presupuesto": pesos(pedido["presupuesto_max"]) if pedido.get("presupuesto_max") else None,
        "exceso_sobre_presupuesto": exceso,
        "ciudad": decision["ciudad"],
        "ciudad_supuesta": not pedido.get("ciudad"),
        "revisadas": decision["revisadas"],
        "descartadas": {"total": len(decision["descartes"]),
                        "resumen": resumen_descartes(decision["conteo_descartes"]) if decision["descartes"] else None},
        "mas_cercanas": mas_cercanas(decision) if decision["situacion"] == "sin_resultados" else [],
    }


# ---------------------------------------------------------------- plantillas (sin IA)
def frase_precio(o):
    if o["envio"] == "gratis":
        return f"{o['total']} con envío gratis"
    return f"{o['total']}, con {o['envio']} de envío incluido"


def frase_llegada(o, datos):
    if o["llega"] == "sin fecha":
        return "La publicación no dice cuándo llega."
    donde = f"si la entrega es en {datos['ciudad']}" if datos["ciudad_supuesta"] else f"a {datos['ciudad']}"
    return f"Llega el {o['llega']} {donde}."


def frase_otras(datos):
    otras = datos["opciones"][1:]
    if not otras:
        return ""
    if datos["mismo_modelo"]:
        partes = [f"{o['total']} (llega el {o['llega']})" for o in otras]
        return "Otras opciones del mismo modelo: " + " y ".join(partes) + "."
    return "Otras opciones: " + " y ".join(f"{o['nombre']} por {o['total']}" for o in otras) + "."


def mensaje_plantilla(datos):
    ops, s = datos["opciones"], datos["situacion"]
    descartes = (f"Revisé {datos['revisadas']} publicaciones y descarté {datos['descartadas']['total']}: "
                 f"{datos['descartadas']['resumen']}." if datos["descartadas"]["total"] else "")
    if s == "sin_resultados":
        partes = ["No encontré publicaciones que cumplan todo lo que pediste."]
        if datos["mas_cercanas"]:
            partes.append("Lo más cercano: " + "; ".join(datos["mas_cercanas"]) + ".")
        partes += [descartes, "¿Quieres que cambie algo del pedido?"]
        return " ".join(p for p in partes if p)
    primera = ops[0]
    if s == "fuera_de_presupuesto":
        partes = [f"Ninguna opción que cumpla lo que pediste cabe en tu presupuesto de {datos['presupuesto']}.",
                  f"La más cercana es {primera['nombre_en_frase']} por {frase_precio(primera)}, "
                  f"{datos['exceso_sobre_presupuesto']} por encima."]
    else:
        partes = [f"Te recomiendo {primera['nombre_en_frase']} por {frase_precio(primera)}.",
                  datos["por_que_la_primera"]]
    partes.append(frase_llegada(primera, datos))
    if primera.get("cuotas"):
        partes.append(f"Tiene {primera['cuotas']}.")
    partes.append(frase_otras(datos))
    if s == "fuera_de_presupuesto":
        partes.append("¿Quieres subir el presupuesto o cambiar algo del pedido?")
    partes += [descartes, "Tú decides: la compra se hace en el enlace de cada opción."]
    return " ".join(p for p in partes if p)


def pregunta_plantilla(pedido):
    if not pedido.get("producto"):
        return "¿Qué producto estás buscando y hasta cuánto quieres gastar? Con eso te muestro las mejores opciones."
    return ("Para elegir bien necesito un poco más: ¿hasta cuánto quieres gastar y qué es lo más importante para ti "
            "(marca, tamaño, capacidad)?")


ACLARACIONES = {
    "otra_tienda": "Solo comparo publicaciones de Mercado Libre, así que no puedo decirte precios de otras tiendas. "
                   "Si me dices qué producto buscas, te muestro las mejores opciones aquí.",
    "pagos": "No hago compras ni pagos, y no recibo datos de tarjetas: si escribiste uno, lo tapé antes de procesar "
             "tu mensaje. Dime qué producto buscas y te muestro las mejores opciones; la compra la haces tú desde "
             "el enlace.",
    "otro": "Solo te ayudo a comparar productos para comprar en Mercado Libre. ¿Qué producto buscas?",
}


# ---------------------------------------------------------------- redacción con IA y su verificación
def instrucciones_redactor():
    return "\n".join([
        "Eres quien redacta las respuestas de PriceX 2.0, un asistente que ayuda a comparar productos en Mercado "
        "Libre Colombia. Recibes un JSON con el pedido de la persona y las opciones que ya eligieron las reglas. "
        "Escribe el mensaje para la persona.",
        "",
        "REGLAS",
        "- Usa solo los datos del JSON. No agregues características, promesas ni opiniones que no estén ahí.",
        "- Copia cada cifra exactamente como aparece en el JSON: precios, fechas, porcentajes y calificaciones. "
        "No redondees ni calcules cifras nuevas.",
        "- No escribas enlaces: la aplicación pone un botón con el enlace de cada opción.",
        "- El orden de las opciones ya está decidido: no lo cambies ni recomiendes otra.",
        "- Explica en una frase por qué la primera, usando el campo por_que_la_primera.",
        "- Si situacion es \"fuera_de_presupuesto\", dilo primero y muestra la más cercana. Si es "
        "\"sin_resultados\", di que no encontraste opciones que cumplan todo y resume por qué se descartaron.",
        "- Máximo 90 palabras, en español de Colombia, tratando a la persona de tú, sin emojis.",
        "- Termina recordando que la persona decide y compra desde el enlace.",
        "",
        "RESPUESTA",
        "Solo un JSON con esta forma: {\"mensaje\": \"...\"}",
    ])


CIFRA = re.compile(r"(?<![A-Za-z\d.,])\d+(?:[.,]\d+)*(?![A-Za-z\d])")


def valor_cifra(token):
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", token):
        return int(token.replace(".", ""))
    if "," in token:
        return round(float(token.replace(".", "").replace(",", ".")), 2)
    return round(float(token), 2) if "." in token else int(token)


def cifras(texto):
    return {valor_cifra(t) for t in CIFRA.findall(texto or "")}


MESES_RE = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre"
CIFRAS_CON_TIPO = {  # cada tipo de cifra se compara con las cifras del mismo tipo que hay en los datos
    "precio": re.compile(r"\$\s?(\d{1,3}(?:\.\d{3})+|\d+)"),
    "cuotas": re.compile(r"(\d+)\s+cuotas"),
    "porcentaje": re.compile(r"(\d+(?:,\d+)?)\s?%"),
    "fecha": re.compile(r"(\d{1,2}) de (" + MESES_RE + ")"),
    "calificacion": re.compile(r"(\d,\d)\s+estrellas"),
}


def cifras_con_tipo(texto):
    resultado = {}
    for tipo, patron in CIFRAS_CON_TIPO.items():
        resultado[tipo] = {" de ".join(m) if isinstance(m, tuple) else m for m in patron.findall(texto or "")}
    return resultado


def verificar_mensaje(mensaje, datos):
    """Revisa el mensaje del modelo. Devuelve la lista de problemas: vacía si se puede mostrar."""
    problemas = []
    if not mensaje or not mensaje.strip():
        return ["mensaje vacío"]
    if re.search(r"https?://|www\.", mensaje, re.IGNORECASE):
        problemas.append("trae un enlace")
    texto_datos = json.dumps(datos, ensure_ascii=False)
    en_datos, en_mensaje = cifras_con_tipo(texto_datos), cifras_con_tipo(mensaje)
    for tipo in CIFRAS_CON_TIPO:
        sobran = sorted(en_mensaje[tipo] - en_datos[tipo])
        if sobran:
            problemas.append(f"{tipo} que no está en los datos: " + ", ".join(sobran))
    inventadas = sorted(str(c) for c in cifras(mensaje) - cifras(texto_datos) - {1, 2, 3})
    if inventadas:
        problemas.append("cifras que no están en los datos: " + ", ".join(inventadas))
    if datos["opciones"] and datos["opciones"][0]["total"] not in mensaje:
        problemas.append("no menciona el precio de la opción elegida")
    if len(mensaje.split()) > 130:
        problemas.append("demasiado largo")
    return problemas


def extraer_mensaje(texto):
    texto = re.sub(r"^\s*```(?:json)?|```\s*$", "", (texto or "").strip())
    for candidato in (texto, texto[texto.find("{"): texto.rfind("}") + 1]):
        try:
            dato = json.loads(candidato)
        except ValueError:
            continue
        if isinstance(dato, dict) and isinstance(dato.get("mensaje"), str):
            return dato["mensaje"].strip()
    return None


def explicar_con_ia(datos, llamar):
    """Pide el mensaje al modelo y lo verifica. Si no pasa, devuelve la plantilla. Nunca muestra uno sin verificar."""
    inicio = time.time()
    salida = llamar(instrucciones_redactor(), json.dumps(datos, ensure_ascii=False))
    uso = salida if isinstance(salida, dict) else {"texto": salida}
    mensaje = extraer_mensaje(uso.get("texto", ""))
    problemas = verificar_mensaje(mensaje, datos) if mensaje else ["la respuesta no es un JSON con 'mensaje'"]
    meta = {"segundos": uso.get("segundos", round(time.time() - inicio, 2)), "tokens_entrada": uso.get("tokens_entrada"),
            "tokens_salida": uso.get("tokens_salida"), "problemas": problemas, "mensaje_ia": mensaje,
            "usado": "plantilla" if problemas else "ia"}
    return (mensaje_plantilla(datos) if problemas else mensaje), meta
