"""El tablero: convierte cada respuesta en un registro sin texto personal y resume lo que pasa en la página.

Responde cinco preguntas de negocio, cada una con su lectura en una frase:
1. ¿Dónde se pierde el pedido?            (embudo)
2. ¿Por qué no sirven las publicaciones?  (motivos de descarte: ruido del buscador y calidad del catálogo)
3. ¿Qué piden y qué no encuentran?        (demanda y demanda sin atender)
4. ¿Qué hizo el equipo de agentes?        (propuestas usadas, sin cambios y rechazadas por el código)
5. ¿Cuánto cuesta y cuánto vale?          (costo por pedido frente a la comisión de una venta)

En las pruebas grabadas, que tienen respuesta correcta, responde además:
6. ¿Qué tan bien elige?                   (aciertos y errores graves contra la clave, por versión y corrida)

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
    """Los registros de la página en vivo. Con una hoja de Google Sheets conectada (hoja.py), cada mensaje queda
    guardado ahí y sobrevive cuando la app se duerme; sin hoja, quedan en memoria y en un archivo mientras la app
    esté despierta."""

    def __init__(self, ruta=None, maximo=20_000, hoja=None):
        self.ruta = Path(ruta) if ruta else None
        self.maximo = maximo
        self.hoja = hoja
        self.problema = None
        self._eventos = []
        self._candado = threading.Lock()
        if self.hoja is not None:
            try:
                self._eventos = list(self.hoja.leer())[-maximo:]
            except Exception as error:  # la página sigue: sin hoja, como antes
                self._fallo_la_hoja("leer", error)
        if self.hoja is None and self.ruta and self.ruta.exists():
            for linea in self.ruta.read_text(encoding="utf-8").splitlines()[-maximo:]:
                try:
                    self._eventos.append(json.loads(linea))
                except ValueError:
                    continue

    def _fallo_la_hoja(self, que, error):
        self.problema = f"No se pudo {que} la hoja de Google Sheets ({type(error).__name__}): los datos quedan solo " \
                        "mientras la página esté despierta."
        self.hoja = None

    @property
    def guarda_en_hoja(self):
        return self.hoja is not None

    def agregar(self, evento):
        with self._candado:
            self._eventos.append(evento)
            del self._eventos[:-self.maximo]
            if self.hoja is not None:
                try:
                    self.hoja.agregar(evento)
                except Exception as error:
                    self._fallo_la_hoja("escribir en", error)
            if self.ruta:
                try:
                    with open(self.ruta, "a", encoding="utf-8") as f:
                        f.write(json.dumps(evento, ensure_ascii=False) + "\n")
                except OSError:
                    self.ruta = None  # sin disco para escribir: sigue en memoria

    def eventos(self):
        with self._candado:
            return list(self._eventos)


def _veredicto(fila):
    """La fila de evaluación de un caso, en datos: True, False o None cuando no aplica."""
    def dato(clave):
        valor = (fila or {}).get(clave)
        return {"True": True, "False": False}.get(valor)
    return {"accion_ok": dato("acciones_ok") if dato("acciones_ok") is not None else dato("accion_ok"),
            "top1": dato("top1"), "grave": dato("grave"), "entendio": dato("interpretacion_ok")}


def _evaluaciones(archivo):
    if not archivo.exists():
        return {}
    with open(archivo, encoding="utf-8-sig") as f:
        return {fila["n"]: fila for fila in csv.DictReader(f)}


# Dónde está cada corrida grabada. La sin IA es una sola (no usa modelo); la corrida 1 quedó archivada en su carpeta.
FUENTES_PRUEBAS = [("sin IA", None, ("resultados", "sin_ia"), ""),
                   ("v1", 1, ("resultados", "gemini", "corrida_1"), "v1_"), ("v2", 1, ("resultados", "gemini", "corrida_1"), "v2_"),
                   ("v1", 2, ("resultados", "gemini"), "v1_"), ("v2", 2, ("resultados", "gemini"), "v2_")]


def eventos_de_pruebas(raiz, marcas=None):
    """Los registros de las corridas grabadas, con el veredicto de cada caso contra la clave de respuestas.

    En una conversación, el veredicto va en el último turno, que es donde se mide."""
    raiz = Path(raiz)
    eventos = []
    for version, corrida, partes, prefijo in FUENTES_PRUEBAS:
        carpeta = raiz.joinpath(*partes)
        for conjunto in ("pedidos", "variantes", "conversaciones"):
            archivo = carpeta / f"respuestas_{prefijo}{conjunto}.jsonl"
            if not archivo.exists():
                continue
            evaluaciones = _evaluaciones(carpeta / f"evaluacion_{prefijo}{conjunto}.csv")
            for linea in archivo.read_text(encoding="utf-8").splitlines():
                r = json.loads(linea)
                turnos = r["turnos"] if conjunto == "conversaciones" else [r]
                for i, turno in enumerate(turnos, start=1):
                    sesion = f"{conjunto}-{r['n']}" if corrida is None else f"corrida{corrida}-{conjunto}-{r['n']}"
                    evento = evento_de(turno, sesion=sesion, origen="prueba", version=version, marcas=marcas)
                    evento.update(momento=None, corrida=corrida, conjunto=conjunto)
                    ultimo = i == len(turnos)
                    evento.update(_veredicto(evaluaciones.get(str(r["n"])) if ultimo else None))
                    eventos.append(evento)
    return eventos


def corridas_de(eventos):
    return sorted({e.get("corrida") for e in eventos if e.get("corrida")})


def filtrar(eventos, producto=None, sesion=None, version=None, corrida=None):
    """La versión sin IA no tiene corrida: es la misma línea base para las dos, así que el filtro de corrida la deja."""
    return [e for e in eventos if (producto is None or e["producto"] == producto)
            and (sesion is None or e["sesion"] == sesion) and (version is None or e["version"] == version)
            and (corrida is None or e.get("corrida") in (None, corrida))]


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
    evaluados = [e for e in eventos if e.get("accion_ok") is not None]
    recomendables = [e for e in evaluados if e.get("top1") is not None]
    calidad = None
    if evaluados:
        calidad = {"casos": len(evaluados), "acciones_ok": sum(bool(e["accion_ok"]) for e in evaluados),
                   "recomendables": len(recomendables), "top1": sum(bool(e["top1"]) for e in recomendables),
                   "entendio": sum(bool(e.get("entendio")) for e in recomendables),
                   "graves": sum(bool(e.get("grave")) for e in recomendables)}
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
        "calidad": calidad,
    }


NOMBRE_VERSION_CORTO = {"sin IA": "Sin IA", "v1": "V1: un agente", "v2": "V2: equipo"}


def comparar_corridas(eventos):
    """Una fila por versión y corrida: aciertos, errores graves, costo y tiempo. Es el antes y el después."""
    filas = []
    for version, corrida, *_ in FUENTES_PRUEBAS:
        grupo = [e for e in eventos if e["version"] == version and e.get("corrida") == corrida]
        if not grupo:
            continue
        r = resumen(grupo)
        c = r["calidad"] or {}
        filas.append({"version": version, "corrida": corrida, "recomendables": c.get("recomendables", 0),
                      "top1": c.get("top1", 0), "graves": c.get("graves", 0), "costo_usd": r["costo_promedio_usd"],
                      "segundos": r["segundos_mediana"]})
    return filas


def lectura_corridas(filas):
    """La frase del antes y el después: qué pasó con cada versión con IA de la corrida 1 a la 2."""
    por = {(f["version"], f["corrida"]): f for f in filas}
    partes = []
    for version in ("v1", "v2"):
        antes, despues = por.get((version, 1)), por.get((version, 2))
        if not (antes and despues):
            continue
        texto = (f"la {version} pasó de {antes['top1']} a {despues['top1']} aciertos de {despues['recomendables']}")
        if antes["costo_usd"] and despues["costo_usd"]:
            cambio = round(100 * (despues["costo_usd"] - antes["costo_usd"]) / antes["costo_usd"])
            texto += (f" y su costo por mensaje {'bajó' if cambio < 0 else 'subió'} {abs(cambio)} %"
                      if cambio else " con el mismo costo por mensaje")
        partes.append(texto)
    if not partes:
        return None
    return ("De la corrida 1 a la 2 (después de corregir la regla de modelos, frenar las palabras nuevas del "
            "coordinador, cambiar el buscador a marcas y apagar el revisor), " + "; ".join(partes) + ".")


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
    c = r.get("calidad")
    if c and c["recomendables"]:
        frases.append(("¿Qué tan bien elige?",
                       f"Contra la respuesta correcta, la mejor opción quedó primera en {c['top1']} de "
                       f"{c['recomendables']} pedidos ({porcentaje(c['top1'], c['recomendables'])} %) y entendió sin "
                       f"errores {c['entendio']} de {c['recomendables']}. Errores graves, es decir, una primera opción "
                       f"que incumple lo pedido: {c['graves']}. Hizo lo que debía (recomendar, preguntar o aclarar) en "
                       f"{c['acciones_ok']} de {c['casos']} casos."))
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
        revisor = dict(r["agentes"]).get("Revisor")  # apagado por defecto desde la corrida 1
        frase = (f"Los agentes trabajaron {propuestas} veces y el código rechazó {totales['rechazado']} de sus "
                 "propuestas")
        if revisor:
            frase += f". El revisor cambió algo en {revisor.get('usado', 0)} de {sum(revisor.values())} pedidos"
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
COLUMNAS_CSV = ["momento", "origen", "version", "corrida", "conjunto", "accion_ok", "top1", "grave", "entendio",
                "sesion", "turno", "movimiento", "accion", "situacion", "razon",
                "producto", "marca", "presupuesto", "total_primera", "brecha", "revisadas", "validas",
                "leido_del_titulo", "busquedas_extra", "consultas", "tokens_entrada", "tokens_salida",
                "segundos_modelo", "costo_usd"]


def columna_agente(agente, resultado):
    return f"{normalizar(agente).replace(' ', '_')}_{normalizar(resultado).replace(' ', '_')}"


def columnas():
    """Las columnas del CSV y de la hoja de Google Sheets: los datos del mensaje, un motivo de descarte por columna
    y una columna por agente y resultado."""
    return (COLUMNAS_CSV + [f"descartes_{m}" for m in MOTIVOS]
            + [columna_agente(a, r) for a in AGENTES for r in RESULTADOS])


def fila_de(evento):
    """Los valores de un registro, en el orden de columnas()."""
    return ([evento.get(c) for c in COLUMNAS_CSV] + [evento["descartes"].get(m, 0) for m in MOTIVOS]
            + [evento["agentes"].get(a, {}).get(r, 0) for a in AGENTES for r in RESULTADOS])


# Cómo volver a leer una fila (de la hoja o del CSV) como registro: cada columna con su tipo
ENTEROS = {"corrida", "turno", "presupuesto", "total_primera", "brecha"}
CONTEOS = {"revisadas", "validas", "busquedas_extra", "consultas", "tokens_entrada", "tokens_salida"}
DECIMALES = {"segundos_modelo", "costo_usd"}
SI_NO = {"accion_ok", "top1", "grave", "entendio"}


def _numero(valor):
    return float(str(valor).replace(",", ".")) if not isinstance(valor, (int, float)) else valor


def evento_de_fila(fila):
    """El registro que guardó fila_de(), a partir de un diccionario columna -> valor. Lo vacío vuelve como None."""
    evento = {}
    for c in COLUMNAS_CSV:
        v = fila.get(c)
        vacio = v in ("", None)
        if c in CONTEOS:
            evento[c] = 0 if vacio else int(_numero(v))
        elif c in DECIMALES:
            evento[c] = 0.0 if vacio else float(_numero(v))
        elif c in ENTEROS:
            evento[c] = None if vacio else int(_numero(v))
        elif c == "leido_del_titulo":
            evento[c] = False if vacio else (v if isinstance(v, bool) else str(v).strip().upper() == "TRUE")
        elif c in SI_NO:
            evento[c] = None if vacio else (v if isinstance(v, bool) else str(v).strip().upper() == "TRUE")
        else:
            evento[c] = None if vacio else str(v)
    evento["descartes"] = {m: int(_numero(fila[f"descartes_{m}"])) for m in MOTIVOS
                           if fila.get(f"descartes_{m}") not in ("", None) and int(_numero(fila[f"descartes_{m}"]))}
    evento["agentes"] = {}
    for a in AGENTES:
        for r in RESULTADOS:
            v = fila.get(columna_agente(a, r))
            if v not in ("", None) and int(_numero(v)):
                evento["agentes"].setdefault(a, {})[r] = int(_numero(v))
    return evento


def a_csv(eventos):
    """Un CSV con una fila por mensaje, listo para Excel o Power BI. Los descartes y los agentes van en columnas."""
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(columnas())
    for e in eventos:
        escritor.writerow(fila_de(e))
    return salida.getvalue()
