"""El tablero: convierte cada respuesta en un registro sin texto personal y resume lo que pasa en la página.

Responde cinco preguntas de negocio, cada una con su lectura en una frase:
1. ¿Dónde se pierde el pedido?            (embudo)
2. ¿Por qué no sirven las publicaciones?  (motivos de descarte: ruido del buscador y calidad del catálogo)
3. ¿Qué piden y qué no encuentran?        (demanda y demanda sin atender)
4. ¿Qué hizo el equipo de agentes?        (propuestas usadas, sin cambios y rechazadas por el código)
5. ¿Cuánto cuesta y cuánto vale?          (costo por pedido frente a la comisión de una venta)

Privacidad: el registro guarda solo datos estructurados (producto, acción, motivos, tiempos, costo). Nunca guarda
el texto que escribió la persona, y una marca que no está en el catálogo se guarda como «otra».
"""
import csv
import io
import json
import statistics
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .config import (COMISION_AFILIADO, COMPRA_PROMEDIO, DOLAR_EN_PESOS, PRECIO_ENTRADA_USD, PRECIO_SALIDA_USD,
                     PRODUCTOS)
from .reglas import MOTIVOS, canon_marca
from .respuesta import ARTICULO, FRASES_MOTIVO
from .texto import decimal, normalizar, pesos

AGENTES = ["Coordinador", "Intérprete", "Revisor", "Buscador", "Lector de atributos", "Redactor"]
RESULTADOS = ["usado", "sin cambios", "rechazado", "falló"]
SITUACIONES = {"recomendar": "con opciones que cumplen todo", "fuera_de_presupuesto": "nada cabe en el presupuesto",
               "sin_resultados": "no hay nada que cumpla"}
# Qué significa para el negocio cada motivo de descarte cuando es el principal
SENTIDO_MOTIVO = {
    "otro_producto": "la búsqueda trae accesorios y otros productos, un ruido que las reglas limpian",
    "otro_modelo": "aparecen modelos parecidos (Plus, Pro, la versión anterior) que confunden al comprador",
    "otra_marca": "aparecen marcas que no se pidieron, como réplicas o genéricos",
    "otra_especificacion": "la capacidad o el tamaño no coinciden aunque el nombre se parezca",
    "otro_color": "el modelo existe, pero no en el color pedido",
    "sin_dato": "hay fichas incompletas: publicaciones que podrían servir pero no confirman un dato",
    "otro_estado": "aparecen usados o reacondicionados cuando se pidió nuevo, o al revés",
    "vendedor_no_confiable": "hay vendedores con mala reputación o pocas ventas, un riesgo para el comprador",
    "llega_tarde": "la entrega no alcanza la fecha que pidió la persona",
    "sobre_presupuesto": "el precio total pasa lo que la persona quiere pagar",
    "texto_sospechoso": "hay publicaciones que intentan darle órdenes al asistente",
}


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def marcas_del_catalogo(catalogo):
    """Las marcas que existen en el catálogo, en su forma comparable. Solo esas se muestran en el tablero."""
    return {canon_marca(p.get("marca")) for p in catalogo.publicaciones if p.get("marca")}


# ---------------------------------------------------------------- un registro por respuesta
def evento_de(respuesta, sesion=None, origen="visitante", version=None, marcas=None):
    """Convierte una respuesta (completa o compacta) en un registro sin texto de la persona."""
    interpretacion = respuesta.get("interpretacion") or {}
    decision = respuesta.get("decision") or {}
    opciones = decision.get("opciones") if decision else respuesta.get("opciones")
    opciones = opciones or []
    situacion = decision.get("situacion") if decision else respuesta.get("situacion")
    revisadas = decision.get("revisadas") if decision else respuesta.get("revisadas")
    validas = decision.get("validas") if decision else respuesta.get("validas")
    if decision:
        descartes = Counter(decision.get("conteo_descartes") or {})
    else:
        descartes = Counter(d["motivo"] for d in respuesta.get("descartes") or [])
    producto = interpretacion.get("producto") if interpretacion.get("producto") in PRODUCTOS else None
    marca = canon_marca(interpretacion["marca"]) if interpretacion.get("marca") else None
    if marca and marcas is not None and marca not in marcas:
        marca = "otra"
    presupuesto = interpretacion.get("presupuesto_max")
    total = opciones[0]["total"] if opciones else None
    agentes = {}
    for paso in respuesta.get("traza") or []:
        if paso.get("ia") and paso.get("quien") in AGENTES:
            cuenta = agentes.setdefault(paso["quien"], Counter())
            cuenta[paso.get("resultado")] += 1
    llamadas = list(respuesta.get("llamadas") or [])
    if not llamadas and respuesta.get("modo") == "con IA":  # versión 1: interpretación y, si hubo, redacción
        redaccion = respuesta.get("meta_redaccion") or {}
        llamadas = [respuesta.get("meta_interpretacion") or {}] + ([redaccion] if "mensaje_ia" in redaccion else [])
    tokens_entrada = sum(c.get("tokens_entrada") or 0 for c in llamadas)
    tokens_salida = sum(c.get("tokens_salida") or 0 for c in llamadas)
    return {
        "momento": ahora(), "origen": origen, "sesion": sesion, "version": version or etiqueta_modo(respuesta),
        "turno": respuesta.get("turno"), "movimiento": respuesta.get("movimiento"),
        "accion": respuesta.get("accion"), "situacion": situacion, "razon": respuesta.get("razon") or decision.get("razon"),
        "producto": producto, "marca": marca, "presupuesto": presupuesto,
        "total_primera": total,
        "brecha": total - presupuesto if situacion == "fuera_de_presupuesto" and total and presupuesto else None,
        "revisadas": revisadas or 0, "validas": validas or 0, "descartes": dict(descartes),
        "leido_del_titulo": any(o.get("leido_del_titulo") for o in opciones),
        "busquedas_extra": max(0, len(respuesta.get("busquedas") or []) - 1),
        "agentes": {a: dict(c) for a, c in agentes.items()},
        "consultas": len(llamadas), "tokens_entrada": tokens_entrada, "tokens_salida": tokens_salida,
        "segundos_modelo": round(sum(c.get("segundos") or 0 for c in llamadas), 2),
        "costo_usd": round((tokens_entrada * PRECIO_ENTRADA_USD + tokens_salida * PRECIO_SALIDA_USD) / 1_000_000, 6),
    }


def etiqueta_modo(respuesta):
    return {"multiagente": "v2", "con IA": "v1", "sin IA": "sin IA"}.get(respuesta.get("modo"), respuesta.get("modo"))


class RegistroDeUso:
    """Los registros de la página en vivo: en memoria y, mientras la app esté despierta, en un archivo."""

    def __init__(self, ruta=None, maximo=20_000):
        self.ruta = Path(ruta) if ruta else None
        self.maximo = maximo
        self._eventos = []
        self._candado = threading.Lock()
        if self.ruta and self.ruta.exists():
            for linea in self.ruta.read_text(encoding="utf-8").splitlines()[-maximo:]:
                try:
                    self._eventos.append(json.loads(linea))
                except ValueError:
                    continue

    def agregar(self, evento):
        with self._candado:
            self._eventos.append(evento)
            del self._eventos[:-self.maximo]
            if self.ruta:
                try:
                    with open(self.ruta, "a", encoding="utf-8") as f:
                        f.write(json.dumps(evento, ensure_ascii=False) + "\n")
                except OSError:
                    self.ruta = None  # sin disco para escribir: sigue en memoria

    def eventos(self):
        with self._candado:
            return list(self._eventos)


def eventos_de_pruebas(raiz, marcas=None):
    """Los registros de las corridas grabadas: sin IA siempre; v1 y v2 cuando se haya corrido el cuaderno."""
    raiz = Path(raiz)
    fuentes = [("sin IA", raiz / "resultados" / "sin_ia", ""), ("v1", raiz / "resultados" / "gemini", "v1_"),
               ("v2", raiz / "resultados" / "gemini", "v2_")]
    eventos = []
    for version, carpeta, prefijo in fuentes:
        for conjunto in ("pedidos", "variantes", "conversaciones"):
            archivo = carpeta / f"respuestas_{prefijo}{conjunto}.jsonl"
            if not archivo.exists():
                continue
            for linea in archivo.read_text(encoding="utf-8").splitlines():
                r = json.loads(linea)
                for turno in (r["turnos"] if conjunto == "conversaciones" else [r]):
                    evento = evento_de(turno, sesion=f"{conjunto}-{r['n']}", origen="prueba", version=version,
                                       marcas=marcas)
                    evento["momento"] = None
                    eventos.append(evento)
    return eventos


def filtrar(eventos, producto=None, sesion=None, version=None):
    return [e for e in eventos if (producto is None or e["producto"] == producto)
            and (sesion is None or e["sesion"] == sesion) and (version is None or e["version"] == version)]


# ---------------------------------------------------------------- los resúmenes
def porcentaje(parte, total):
    return round(100 * parte / total) if total else 0


def mediana(valores):
    valores = [v for v in valores if v is not None]
    return statistics.median(valores) if valores else None


def resumen(eventos):
    """Todo lo que muestra el tablero, calculado de los registros. Las lecturas van aparte (lecturas())."""
    n = len(eventos)
    con_producto = [e for e in eventos if e["producto"]]
    buscados = [e for e in eventos if e["accion"] == "recomendar"]
    con_opciones = [e for e in buscados if e["situacion"] == "recomendar"]
    embudo = [("Mensajes que llegaron", n), ("Se entendió qué producto busca", len(con_producto)),
              ("Tenía datos para buscar", len(buscados)), ("Hubo opciones que cumplen todo", len(con_opciones))]
    descartes = Counter()
    for e in eventos:
        descartes.update(e["descartes"])
    motivos = [(m, descartes[m]) for m in sorted(descartes, key=lambda m: (-descartes[m], list(MOTIVOS).index(m)))]
    productos = Counter(e["producto"] for e in con_producto)
    sin_atender = {}
    for e in buscados:
        if e["situacion"] in ("sin_resultados", "fuera_de_presupuesto"):
            fila = sin_atender.setdefault((e["producto"], e["situacion"]), {"pedidos": 0, "brechas": []})
            fila["pedidos"] += 1
            if e["brecha"]:
                fila["brechas"].append(e["brecha"])
    demanda = sorted(({"producto": p, "situacion": s, "pedidos": f["pedidos"], "brecha_mediana": mediana(f["brechas"])}
                      for (p, s), f in sin_atender.items()), key=lambda f: (-f["pedidos"], f["producto"] or ""))
    agentes = {}
    for e in eventos:
        for agente, cuenta in e["agentes"].items():
            fila = agentes.setdefault(agente, Counter())
            fila.update(cuenta)
    con_ia = [e for e in eventos if e["consultas"]]
    costo = mediana_costo = None
    if con_ia:
        costo = sum(e["costo_usd"] for e in con_ia) / len(con_ia)
        mediana_costo = mediana([e["costo_usd"] for e in con_ia])
    return {
        "mensajes": n, "sesiones": len({e["sesion"] for e in eventos if e["sesion"]}),
        "con_opciones": len(con_opciones), "buscados": len(buscados),
        "preguntar_o_aclarar": sum(e["accion"] in ("preguntar", "aclarar") for e in eventos),
        "embudo": embudo, "motivos": motivos, "revisadas": sum(e["revisadas"] for e in eventos),
        "validas": sum(e["validas"] for e in eventos), "descartadas": sum(descartes.values()),
        "productos": productos.most_common(), "demanda_sin_atender": demanda,
        "presupuesto_mediano": mediana([e["presupuesto"] for e in buscados]),
        "agentes": [(a, dict(agentes[a])) for a in AGENTES if a in agentes],
        "con_ia": len(con_ia), "costo_promedio_usd": costo, "costo_mediano_usd": mediana_costo,
        "segundos_mediana": mediana([e["segundos_modelo"] for e in con_ia]),
        "consultas_por_mensaje": sum(e["consultas"] for e in con_ia) / len(con_ia) if con_ia else None,
        "titulos_leidos": sum(e["leido_del_titulo"] for e in eventos),
        "busquedas_extra": sum(e["busquedas_extra"] for e in eventos),
    }


def nombre_producto(clave):
    return PRODUCTOS[clave][1] if clave in PRODUCTOS else "sin producto"


def usd(valor):
    return "US$ " + (f"{valor:.4f}".replace(".", ",") if valor < 0.01 else decimal(valor, 2))


def lecturas(r):
    """Una frase por pregunta de negocio, calculada de los datos. Con pocos datos, lo dice."""
    frases = []
    n = r["mensajes"]
    if not n:
        return [("Todavía no hay datos", "Escribe un pedido en la pestaña Asistente y este tablero se actualiza con "
                                         "cada mensaje.")]
    if n < 10:
        frases.append(("Ojo con la muestra", f"Con {n} mensaje{'s' if n != 1 else ''} todavía es pronto para concluir: "
                                             "las lecturas se afinan con más uso."))
    etapas = r["embudo"]
    caidas = [(etapas[i][0], etapas[i - 1][1] - etapas[i][1]) for i in range(1, len(etapas))]
    etapa, caida = max(caidas, key=lambda c: c[1])
    frase = (f"De {n} mensajes, {r['con_opciones']} terminaron con opciones que cumplen todo "
             f"({porcentaje(r['con_opciones'], n)} %).")
    if caida:
        frase += " " + {
            "Se entendió qué producto busca": f"La mayor caída es al entender qué producto busca: {caida} mensajes sin "
                                              "un producto claro (saludos, pedidos fuera de alcance o frases que el "
                                              "asistente no entendió). Ahí pregunta o aclara.",
            "Tenía datos para buscar": f"La mayor caída es al tener datos para buscar: {caida} pedidos muy generales "
                                       "(«un celular bueno») o sin un dato clave. Ahí el asistente pregunta antes de "
                                       "recomendar.",
            "Hubo opciones que cumplen todo": f"La mayor caída es al final: {caida} pedidos sin opciones que cumplan "
                                              "todo, porque el catálogo no tenía lo pedido o no cabía en el "
                                              "presupuesto. Es demanda sin atender.",
        }[etapa]
    frases.append(("¿Dónde se pierde el pedido?", frase))
    if r["motivos"]:
        motivo, cuantas = r["motivos"][0]
        por_cada = r["descartadas"] / r["validas"] if r["validas"] else None
        frase = (f"Por cada publicación que sirve, la búsqueda trae {decimal(por_cada, 0) if por_cada >= 10 else decimal(por_cada)} "
                 "que no. " if por_cada else "Ninguna publicación sirvió. ")
        frase += (f"El motivo principal es que {FRASES_MOTIVO[motivo][1]} ({porcentaje(cuantas, r['descartadas'])} % "
                  f"de las descartadas). Quiere decir que {SENTIDO_MOTIVO[motivo]}.")
        frases.append(("¿Por qué no sirven las publicaciones?", frase))
    if r["productos"]:
        producto, veces = r["productos"][0]
        con_producto = sum(v for _, v in r["productos"])
        frase = (f"Lo más pedido es {ARTICULO.get(producto, 'el')} {nombre_producto(producto)}: {veces} de "
                 f"{con_producto} mensajes con un producto claro ({porcentaje(veces, con_producto)} %).")
        if r["presupuesto_mediano"]:
            frase += f" Quienes dicen cuánto quieren gastar ponen {pesos(r['presupuesto_mediano'])} en la mediana."
        frases.append(("¿Qué piden?", frase))
    if r["buscados"]:
        sin = sum(f["pedidos"] for f in r["demanda_sin_atender"])
        presupuesto = [f for f in r["demanda_sin_atender"] if f["situacion"] == "fuera_de_presupuesto"]
        por_presupuesto = sum(f["pedidos"] for f in presupuesto)
        if sin:
            frase = (f"De {r['buscados']} pedidos con datos para buscar, {sin} no encontraron nada que cumpliera: "
                     f"{por_presupuesto} por presupuesto y {sin - por_presupuesto} porque no había el producto, el "
                     "modelo o el color.")
            brechas = [f["brecha_mediana"] for f in presupuesto if f["brecha_mediana"]]
            if brechas:
                frase += f" A los que no les alcanzó, les faltaron {pesos(mediana(brechas))} en la mediana."
            principal = r["demanda_sin_atender"][0]
            frase += (f" Donde más pasa: {nombre_producto(principal['producto'])} ({principal['pedidos']} "
                      f"pedido{'s' if principal['pedidos'] != 1 else ''}).")
        else:
            frase = f"Los {r['buscados']} pedidos con datos para buscar encontraron opciones que cumplen todo."
        frases.append(("¿Qué no encuentran?", frase))
    if r["agentes"]:
        totales = Counter()
        for _, cuenta in r["agentes"]:
            totales.update(cuenta)
        propuestas = sum(totales.values())
        revisor = dict(r["agentes"]).get("Revisor", {})
        frase = (f"Los agentes trabajaron {propuestas} veces y el código rechazó {totales['rechazado']} de sus "
                 f"propuestas. El revisor cambió algo en {revisor.get('usado', 0)} de {sum(revisor.values())} pedidos")
        frase += (f"; el lector rescató {r['titulos_leidos']} publicaci{'ón' if r['titulos_leidos'] == 1 else 'ones'} "
                  "leyendo su título" if r["titulos_leidos"] else "")
        frase += f" y el buscador hizo {r['busquedas_extra']} búsquedas extra." if r["busquedas_extra"] else "."
        frases.append(("¿Qué hizo el equipo de agentes?", frase))
    if r["costo_promedio_usd"]:
        en_pesos = r["costo_promedio_usd"] * DOLAR_EN_PESOS
        comision = COMISION_AFILIADO * COMPRA_PROMEDIO
        frase = (f"Un mensaje con IA cuesta en promedio {usd(r['costo_promedio_usd'])} (unos {pesos(en_pesos)}). Con "
                 f"{round(100 * COMISION_AFILIADO)} % de comisión sobre una compra de {pesos(COMPRA_PROMEDIO)}, una venta "
                 f"paga {pesos(comision / en_pesos).replace('$', '')} mensajes.")
        frases.append(("¿Cuánto cuesta y cuánto vale?", frase))
    elif n:
        frases.append(("¿Cuánto cuesta y cuánto vale?", "Estos mensajes los atendió la versión sin IA: no hay costo "
                                                        "de modelo."))
    return frases


# ---------------------------------------------------------------- exportar para inteligencia de negocios
COLUMNAS_CSV = ["momento", "origen", "version", "sesion", "turno", "movimiento", "accion", "situacion", "razon",
                "producto", "marca", "presupuesto", "total_primera", "brecha", "revisadas", "validas",
                "leido_del_titulo", "busquedas_extra", "consultas", "tokens_entrada", "tokens_salida",
                "segundos_modelo", "costo_usd"]


def a_csv(eventos):
    """Un CSV con una fila por mensaje, listo para Excel o Power BI. Los descartes y los agentes van en columnas."""
    salida = io.StringIO()
    columnas = COLUMNAS_CSV + [f"descartes_{m}" for m in MOTIVOS] + [
        f"{normalizar(a).replace(' ', '_')}_{normalizar(r).replace(' ', '_')}" for a in AGENTES for r in RESULTADOS]
    escritor = csv.writer(salida)
    escritor.writerow(columnas)
    for e in eventos:
        fila = [e.get(c) for c in COLUMNAS_CSV] + [e["descartes"].get(m, 0) for m in MOTIVOS]
        fila += [e["agentes"].get(a, {}).get(r, 0) for a in AGENTES for r in RESULTADOS]
        escritor.writerow(fila)
    return salida.getvalue()
