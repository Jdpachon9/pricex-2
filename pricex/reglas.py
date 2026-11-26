"""Las reglas que eligen la mejor opción.

La IA solo interpreta el pedido. Qué publicación queda fuera y en qué orden se muestran las que sirven lo deciden
estas reglas: son fijas, se pueden auditar y dan siempre el mismo resultado con los mismos datos.
"""
import re
from collections import Counter
from datetime import timedelta

from .config import (ATRIBUTOS_EXACTOS, ATRIBUTOS_MINIMOS, CIUDAD_POR_DEFECTO, DIFERENCIA_EMPATE_CALIFICACION,
                     DIFERENCIA_EMPATE_PRECIO, FECHA_HOY, MIN_OPINIONES, MIN_VENTAS_VENDEDOR,
                     OPCIONES_A_MOSTRAR, PRODUCTOS, REPUTACION_NO_CONFIABLE)
from .texto import fecha_larga, normalizar, pesos

# Motivos de descarte, en el orden en que se revisan. El presupuesto va de último: si nada cabe en él,
# se muestran las opciones que solo fallaron por precio.
MOTIVOS = {
    "texto_sospechoso": "traían instrucciones escondidas para el asistente",
    "otro_producto": "eran otro producto o un accesorio",
    "otra_marca": "eran de otra marca",
    "otro_modelo": "eran otro modelo",
    "otra_especificacion": "tenían otra capacidad, tamaño o edición",
    "otro_color": "eran de otro color",
    "sin_dato": "no confirmaban un dato que pediste",
    "otro_estado": "no estaban en el estado que pediste",
    "vendedor_no_confiable": "eran de vendedores con mala reputación o con pocas ventas",
    "llega_tarde": "no llegaban a tiempo",
    "sobre_presupuesto": "pasaban de tu presupuesto",
}
SOSPECHOSO = re.compile(
    r"(ignora|olvida|omite)\w*\s+(tus|las|todas|sus|esas|estas)\s+(reglas|instrucciones|indicaciones)"
    r"|nota para (el|la) (asistente|ia|inteligencia artificial|modelo|bot)"
    r"|si eres (una|un) (ia|asistente|bot|modelo|inteligencia artificial)"
    r"|(asistente|ia|bot|chatbot)( de compras)?\s*:\s*(ignora|recomienda|di|responde|pon|elige|menciona)"
    r"|system prompt|prompt del sistema"
)
ALIAS_MARCA = {"black decker": "black+decker", "black and decker": "black+decker", "black & decker": "black+decker",
               "wd": "western digital", "dolce gusto": "nescafe dolce gusto", "playstation": "sony"}
ALIAS_COLOR = {"negra": "negro", "blanca": "blanco", "roja": "rojo", "morada": "morado", "rosada": "rosado",
               "rosa": "rosado", "plata": "plateado", "lila": "morado", "purpura": "morado"}
ALIAS_EDICION = {"fisica": "disco", "con disco": "disco", "estandar": "disco", "lector de discos": "disco"}
NOMBRE_ATRIBUTO = {"almacenamiento_gb": "la capacidad", "ram_gb": "la memoria RAM", "pulgadas": "el tamaño",
                   "litros": "la capacidad en litros", "kilos": "la capacidad en kilos", "potencia_w": "la potencia",
                   "edicion": "la edición", "color": "el color"}
NOMBRE_ESTADO = {"nuevo": "nuevo", "usado": "usado", "reacondicionado": "reacondicionado"}
NIVELES = {"1_red": "vendedor con reputación roja", "2_orange": "vendedor con reputación naranja"}


def canon_marca(texto):
    t = normalizar(texto).replace(" + ", "+")
    return ALIAS_MARCA.get(t, t)


def canon_modelo(texto):
    """Forma comparable de un modelo: 'Galaxy S26+' -> 's26+', 'PS5 Slim' -> 'playstation5slim'."""
    t = normalizar(texto).replace("plus", "+")
    t = re.sub(r"\b(samsung|apple|sony|xiaomi|amazon|lenovo|galaxy)\b", " ", t)
    t = re.sub(r"\bps ?5\b", "playstation 5", t)
    return re.sub(r"[^a-z0-9+]", "", t)


def canon_color(texto):
    t = normalizar(texto)
    return ALIAS_COLOR.get(t, t)


def canon_edicion(texto):
    t = normalizar(texto)
    return ALIAS_EDICION.get(t, t)


def texto_valor(campo, valor):
    """Cómo se le dice un valor a la persona: 1000 GB -> '1 TB', 5 litros -> '5 litros'."""
    if campo == "almacenamiento_gb":
        return f"{valor // 1000} TB" if valor >= 1000 and valor % 1000 == 0 else f"{valor} GB"
    unidades = {"ram_gb": "GB de RAM", "pulgadas": "pulgadas", "litros": "litros", "kilos": "kg", "potencia_w": "W"}
    if campo in unidades:
        cifra = f"{valor:g}".replace(".", ",") if isinstance(valor, float) else str(valor)
        return f"{cifra} {unidades[campo]}"
    return str(valor)


def dias_entrega(pub, ciudad):
    dias = pub.get("entrega_dias") or {}
    return dias.get(ciudad, dias.get("otras"))


def revisar(pub, pedido, ciudad, hoy=FECHA_HOY):
    """Revisa una publicación contra el pedido. Devuelve (None, '') si sirve, o (motivo, detalle) si no."""
    if SOSPECHOSO.search(normalizar(pub.get("textos_libres", ""))):
        return "texto_sospechoso", "la publicación trae instrucciones para el asistente"
    producto = pedido.get("producto")
    if producto and pub.get("dominio") != PRODUCTOS[producto][0]:
        return "otro_producto", "no es " + PRODUCTOS[producto][1]
    if pedido.get("marca") and canon_marca(pub.get("marca")) != canon_marca(pedido["marca"]):
        return "otra_marca", f"es de otra marca: {pub.get('marca') or 'sin marca'}"
    if pedido.get("modelo") and canon_modelo(pub.get("modelo")) != canon_modelo(pedido["modelo"]):
        return "otro_modelo", f"es otro modelo: {pub.get('modelo') or 'sin dato'}"
    for campo in ATRIBUTOS_EXACTOS + ATRIBUTOS_MINIMOS:
        pedido_valor = pedido.get(campo)
        if pedido_valor in (None, ""):
            continue
        valor = pub.get(campo)
        if valor is None:
            return "sin_dato", f"no dice {NOMBRE_ATRIBUTO[campo]}"
        if campo == "edicion":
            if canon_edicion(valor) != canon_edicion(pedido_valor):
                return "otra_especificacion", f"es la edición {valor}"
        elif campo in ATRIBUTOS_EXACTOS and valor != pedido_valor:
            return "otra_especificacion", f"tiene {texto_valor(campo, valor)} y pediste {texto_valor(campo, pedido_valor)}"
        elif campo in ATRIBUTOS_MINIMOS and valor < pedido_valor:
            return "otra_especificacion", f"tiene {texto_valor(campo, valor)} y pediste {texto_valor(campo, pedido_valor)}"
    if pedido.get("color"):
        if not pub.get("color"):
            return "sin_dato", "no dice el color"
        if canon_color(pub["color"]) != canon_color(pedido["color"]):
            return "otro_color", f"es de color {pub['color']}"
    estado = pedido.get("condicion") or "nuevo"
    if pub.get("condicion") != estado:
        return "otro_estado", f"es {NOMBRE_ESTADO.get(pub.get('condicion'), pub.get('condicion'))}"
    nivel = pub.get("reputacion")
    if nivel in REPUTACION_NO_CONFIABLE:
        return "vendedor_no_confiable", NIVELES[nivel]
    if not nivel or (pub.get("ventas") or 0) < MIN_VENTAS_VENDEDOR:
        return "vendedor_no_confiable", f"vendedor con solo {pub.get('ventas') or 0} ventas"
    if pedido.get("fecha_limite"):
        dias = dias_entrega(pub, ciudad)
        if dias is None:
            return "sin_dato", "no dice cuándo llega"
        llega = hoy + timedelta(days=dias)
        if llega.isoformat() > pedido["fecha_limite"]:
            return "llega_tarde", f"llega el {fecha_larga(llega)}"
    total = pub["precio"] + (pub.get("costo_envio") or 0)
    if pedido.get("presupuesto_max") and total > pedido["presupuesto_max"]:
        return "sobre_presupuesto", f"cuesta {pesos(total)} con envío"
    return None, ""


def con_totales(pub, ciudad, hoy):
    dias = dias_entrega(pub, ciudad)
    return {**pub, "total": pub["precio"] + (pub.get("costo_envio") or 0), "dias": dias,
            "llega": (hoy + timedelta(days=dias)).isoformat() if dias is not None else None}


def decimas(calificacion):
    return round(calificacion * 10)


def ordenar_modelo_exacto(validas):
    """Todas son el mismo producto: gana el menor precio total. Si otra cuesta menos de 3 % más y es tienda
    oficial o llega antes, gana esa."""
    por_total = sorted(validas, key=lambda o: (o["total"], o["id"]))
    mas_barata = por_total[0]
    empatadas = [o for o in por_total if o["total"] * 100 < mas_barata["total"] * round(100 * (1 + DIFERENCIA_EMPATE_PRECIO))]
    primera = min(empatadas, key=lambda o: (not o["tienda_oficial"], o["dias"] if o["dias"] is not None else 99,
                                            o["total"], o["id"]))
    if primera is mas_barata:
        razon = "menor_precio"
    elif primera["tienda_oficial"] and not mas_barata["tienda_oficial"]:
        razon = "tienda_oficial"
    else:
        razon = "llega_antes"
    return [primera] + [o for o in por_total if o is not primera], razon, mas_barata


def ordenar_pedido_abierto(validas):
    """Compiten productos distintos: primero la calificación (con 30 opiniones o más); 0,2 estrellas o menos
    cuentan como empate y entre las empatadas gana el menor precio total."""
    calificadas = [o for o in validas if o.get("calificacion") is not None and o["opiniones"] >= MIN_OPINIONES]
    if not calificadas:
        orden = sorted(validas, key=lambda o: (o["total"], o["id"]))
        return orden, "menor_precio_sin_calificaciones", None
    mejor = max(decimas(o["calificacion"]) for o in calificadas)
    limite = mejor - round(DIFERENCIA_EMPATE_CALIFICACION * 10)
    grupo = sorted([o for o in calificadas if decimas(o["calificacion"]) >= limite], key=lambda o: (o["total"], o["id"]))
    resto = sorted([o for o in validas if o not in grupo],
                   key=lambda o: (o not in calificadas, -decimas(o["calificacion"]) if o in calificadas else 0,
                                  o["total"], o["id"]))
    rango = (min(o["calificacion"] for o in grupo), max(o["calificacion"] for o in grupo))
    return grupo + resto, "mejor_calificada", rango


def decidir(pedido, resultados, hoy=FECHA_HOY, ciudad_por_defecto=CIUDAD_POR_DEFECTO):
    """Aplica las reglas a los resultados de la búsqueda y arma la respuesta: situación, opciones y descartes."""
    ciudad = pedido.get("ciudad") or ciudad_por_defecto
    validas, solo_por_precio, descartes = [], [], []
    for pub in resultados:
        motivo, detalle = revisar(pub, pedido, ciudad, hoy)
        if motivo is None:
            validas.append(con_totales(pub, ciudad, hoy))
        else:
            descartes.append({"id": pub["id"], "motivo": motivo, "detalle": detalle, "titulo": pub["titulo"], "pub": pub})
            if motivo == "sobre_presupuesto":
                solo_por_precio.append(con_totales(pub, ciudad, hoy))
    exacto = bool(pedido.get("modelo"))
    decision = {"ciudad": ciudad, "pedido_exacto": exacto, "revisadas": len(resultados), "descartes": descartes,
                "conteo_descartes": dict(Counter(d["motivo"] for d in descartes)), "razon": None,
                "mas_barata": None, "rango_calificacion": None}
    if validas:
        decision["situacion"] = "recomendar"
        if exacto:
            orden, razon, mas_barata = ordenar_modelo_exacto(validas)
            decision["mas_barata"] = mas_barata["id"]
        else:
            orden, razon, rango = ordenar_pedido_abierto(validas)
            decision["rango_calificacion"] = rango
        decision["razon"] = razon
    elif solo_por_precio:
        decision["situacion"] = "fuera_de_presupuesto"
        orden = sorted(solo_por_precio, key=lambda o: (o["total"], o["id"]))
        decision["razon"] = "mas_cercana_al_presupuesto"
    else:
        decision["situacion"] = "sin_resultados"
        orden = []
    decision["opciones"] = [{**o, "puesto": i} for i, o in enumerate(orden[:OPCIONES_A_MOSTRAR], start=1)]
    decision["validas"] = len(validas)
    return decision
