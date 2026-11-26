"""Cómo se mide el asistente contra la clave de respuestas.

Cada respuesta se compara en tres niveles:
1. ¿Hizo lo que debía (recomendar, preguntar o aclarar)?
2. ¿Entendió el pedido? Campo por campo contra la interpretación correcta.
3. ¿Recomendó bien? La mejor opción esperada en el primer puesto (top 1) o entre las 3 mostradas (top 3), y si la
   primera opción que mostró incumple algo de lo pedido (error grave).

Las conversaciones se miden igual en su último mensaje, y además se revisa la acción de cada turno.
"""
import statistics
from datetime import date

from .config import CIUDAD_POR_DEFECTO, FECHA_HOY
from .reglas import canon_color, canon_marca, canon_modelo, revisar
from .sensibles import TARJETA, pasa_luhn
from .texto import normalizar

CAMPOS_EVALUADOS = ["accion", "producto", "marca", "modelo", "almacenamiento_gb", "ram_gb", "pulgadas", "litros",
                    "kilos", "potencia_w", "color", "edicion", "condicion", "presupuesto_max", "fecha_limite", "ciudad"]


def iguales(campo, valor, esperado, tolerancia=None):
    tolerancia = tolerancia or {}
    vacio_a, vacio_b = valor in (None, ""), esperado in (None, "")
    if vacio_a or vacio_b:
        return vacio_a and vacio_b
    if campo == "marca":
        return canon_marca(valor) == canon_marca(esperado)
    if campo == "modelo":
        return canon_modelo(valor) == canon_modelo(esperado)
    if campo == "color":
        return canon_color(valor) == canon_color(esperado)
    if campo == "fecha_limite":
        dias = abs((date.fromisoformat(valor) - date.fromisoformat(esperado)).days)
        return dias <= tolerancia.get(campo, 0)
    if campo == "litros":
        return abs(float(valor) - float(esperado)) < 0.01
    if campo in ("almacenamiento_gb", "ram_gb", "pulgadas", "kilos", "potencia_w", "presupuesto_max"):
        return int(valor) == int(esperado)
    return normalizar(valor) == normalizar(esperado)


def tarjeta_visible(texto):
    """¿Quedó algún número de tarjeta en el texto que va al modelo?"""
    for m in TARJETA.finditer(texto or ""):
        cifras = "".join(c for c in m.group(0) if c.isdigit())
        if 13 <= len(cifras) <= 19 and pasa_luhn(cifras):
            return True
    return False


def clave_para(esperado, version):
    """La respuesta esperada para una versión: la v2 lee títulos, así que en algún pedido espera otra cosa."""
    return {**esperado, **esperado[version]} if version in esperado else esperado


def tiempo_de_respuesta(respuesta):
    """Sin IA: el tiempo total. Con IA: lo que tardó el modelo en cada consulta (sin las pausas entre consultas)."""
    if respuesta.get("modo") == "sin IA":
        return respuesta.get("segundos_total")
    if "llamadas" in respuesta:
        return round(sum(c.get("segundos") or 0 for c in respuesta["llamadas"]), 2)
    return round((respuesta["meta_interpretacion"].get("segundos") or 0)
                 + ((respuesta.get("meta_redaccion") or {}).get("segundos") or 0), 2)


def tokens(respuesta, tipo):
    if "llamadas" in respuesta:
        return sum(c.get(tipo) or 0 for c in respuesta["llamadas"])
    return ((respuesta.get("meta_interpretacion") or {}).get(tipo) or 0) + ((respuesta.get("meta_redaccion") or {}).get(tipo) or 0)


def evaluar_respuesta(n, respuesta, esperado, catalogo=None, hoy=FECHA_HOY):
    accion_esperada = esperado["accion"]
    if accion_esperada == "recomendar":
        campos = CAMPOS_EVALUADOS
    elif accion_esperada == "preguntar":
        campos = ["accion", "producto"]
    else:
        campos = ["accion"]
    comparacion = {c: iguales(c, respuesta["interpretacion"].get(c), esperado["interpretacion"].get(c),
                              esperado.get("tolerancia")) for c in campos}
    fila = {"n": int(n), "accion_esperada": accion_esperada, "accion": respuesta["accion"],
            "accion_ok": respuesta["accion"] == accion_esperada,
            "interpretacion_ok": all(comparacion.values()),
            "campos_fallados": ", ".join(c for c, ok in comparacion.items() if not ok),
            "campos_evaluados": len(campos), "campos_ok": sum(comparacion.values()),
            "situacion_esperada": esperado.get("situacion"), "situacion": None, "ganador_esperado": esperado["ganador"],
            "mostradas": "", "top1": None, "top3": None, "grave": None, "motivo_grave": "",
            "recomendo_sin_deber": None, "no_recomendo": None,
            "tarjeta_detectada": "tarjeta" in respuesta["tapados"],
            "tarjeta_expuesta": tarjeta_visible(respuesta["pedido_tapado"]),
            "segundos_total": tiempo_de_respuesta(respuesta),
            "redaccion": (respuesta.get("meta_redaccion") or {}).get("usado"),
            "problemas_redaccion": "; ".join((respuesta.get("meta_redaccion") or {}).get("problemas") or []),
            "problemas_interpretacion": "; ".join(respuesta["meta_interpretacion"].get("problemas") or []),
            "consultas": len(respuesta["llamadas"]) if "llamadas" in respuesta else None,
            "tokens_entrada": tokens(respuesta, "tokens_entrada"),
            "tokens_salida": tokens(respuesta, "tokens_salida"),
            "mensaje": respuesta.get("mensaje")}
    decision = respuesta.get("decision")
    if accion_esperada != "recomendar":
        fila["recomendo_sin_deber"] = respuesta["accion"] == "recomendar"
        return fila
    fila["no_recomendo"] = decision is None
    if decision is None:
        fila.update(top1=False, top3=False, grave=False)
        return fila
    mostradas = [o["id"] for o in decision["opciones"]]
    fila.update(situacion=decision["situacion"], mostradas=" ".join(mostradas))
    misma_situacion = decision["situacion"] == esperado["situacion"]
    if esperado["situacion"] == "sin_resultados":
        fila["top1"] = fila["top3"] = misma_situacion
    else:
        fila["top1"] = misma_situacion and mostradas[:1] == [esperado["ganador"]]
        fila["top3"] = misma_situacion and esperado["ganador"] in mostradas
    fila["grave"] = False
    if mostradas:
        # La primera opción tal como la mostró el asistente: en la v2 puede traer un dato leído del título.
        ciudad = esperado["interpretacion"].get("ciudad") or CIUDAD_POR_DEFECTO
        motivo, detalle = revisar(decision["opciones"][0], esperado["interpretacion"], ciudad, hoy)
        aviso_correcto = (motivo == "sobre_presupuesto" and esperado["situacion"] == "fuera_de_presupuesto"
                          and decision["situacion"] == "fuera_de_presupuesto")
        if motivo and not aviso_correcto:
            fila.update(grave=True, motivo_grave=f"{motivo}: {detalle}")
    return fila


def evaluar_conversacion(esperada, respuestas, hoy=FECHA_HOY):
    """Una fila por conversación: la acción de cada turno y, en el último mensaje, lo mismo que en un pedido."""
    final = esperada["turnos"][-1]
    clave_final = {"accion": final["accion"], "situacion": final.get("situacion"), "tolerancia": {},
                   "interpretacion": final["interpretacion"], "ganador": final.get("ganador"),
                   "top3": final.get("top3", [])}
    fila = evaluar_respuesta(0, respuestas[-1], clave_final, None, hoy)
    acciones = [r["accion"] for r in respuestas]
    esperadas = [t["accion"] for t in esperada["turnos"]]
    fila.update(n=esperada["id"], acciones_esperadas=" → ".join(esperadas), acciones=" → ".join(acciones),
                acciones_ok=acciones == esperadas,
                segundos_total=round(sum(tiempo_de_respuesta(r) or 0 for r in respuestas), 2),
                tokens_entrada=sum(tokens(r, "tokens_entrada") for r in respuestas),
                tokens_salida=sum(tokens(r, "tokens_salida") for r in respuestas),
                consultas=sum(len(r.get("llamadas") or []) for r in respuestas) if "llamadas" in respuestas[-1] else None,
                pedido_final=respuestas[-1].get("pedido_consolidado") or respuestas[-1]["pedido_tapado"])
    return fila


def resumen(filas):
    recomendables = [f for f in filas if f["accion_esperada"] == "recomendar"]
    otras = [f for f in filas if f["accion_esperada"] != "recomendar"]
    tiempos = [f["segundos_total"] for f in filas if f["segundos_total"] is not None]
    extra = {"acciones_ok_en_todos_los_turnos": sum(f["acciones_ok"] for f in filas)} if filas and "acciones_ok" in filas[0] else {}
    return {
        **extra,
        "pedidos": len(filas),
        "accion_correcta": sum(f["accion_ok"] for f in filas),
        "recomendables": len(recomendables),
        "interpretacion_perfecta": sum(f["interpretacion_ok"] for f in recomendables),
        "campos_correctos_pct": round(100 * sum(f["campos_ok"] for f in recomendables)
                                      / max(1, sum(f["campos_evaluados"] for f in recomendables)), 1),
        "top1": sum(bool(f["top1"]) for f in recomendables),
        "top3": sum(bool(f["top3"]) for f in recomendables),
        "graves": sum(bool(f["grave"]) for f in recomendables),
        "no_recomendo_debiendo": sum(bool(f["no_recomendo"]) for f in recomendables),
        "debian_preguntar_o_aclarar": len(otras),
        "recomendo_sin_deber": sum(bool(f["recomendo_sin_deber"]) for f in otras),
        "tarjetas_detectadas": sum(bool(f["tarjeta_detectada"]) for f in filas),
        "tarjetas_expuestas": sum(bool(f["tarjeta_expuesta"]) for f in filas),
        "mensajes_redactados_por_ia": sum(f["redaccion"] == "ia" for f in recomendables),
        "mensajes_rechazados_por_verificacion": sum(bool(f["problemas_redaccion"]) for f in recomendables),
        "segundos_mediana": round(statistics.median(tiempos), 2) if tiempos else None,
        "segundos_maximo": round(max(tiempos), 2) if tiempos else None,
        "tokens_entrada": sum(f["tokens_entrada"] for f in filas),
        "tokens_salida": sum(f["tokens_salida"] for f in filas),
        "consultas": sum(f["consultas"] or 0 for f in filas) if filas and filas[0].get("consultas") is not None else None,
    }


def precision_por_campo(filas, respuestas, clave):
    """% de pedidos para recomendar en que cada campo quedó bien."""
    conteo = {c: [0, 0] for c in CAMPOS_EVALUADOS}
    for f in filas:
        if f["accion_esperada"] != "recomendar":
            continue
        esperado = clave[str(f["n"])]
        r = respuestas[f["n"]]
        for c in CAMPOS_EVALUADOS:
            conteo[c][1] += 1
            conteo[c][0] += iguales(c, r["interpretacion"].get(c), esperado["interpretacion"].get(c),
                                    esperado.get("tolerancia"))
    return {c: round(100 * ok / total, 1) for c, (ok, total) in conteo.items() if total}
