"""Arma demo/datos_demo.json con las respuestas grabadas de cada corrida: sin IA y, si existen, v1 y v2 con IA.

La demo no inventa nada: muestra lo que el asistente respondió en las corridas, enriquecido con los datos del
catálogo simulado (precio, envío, vendedor). Uso: python3 scripts/armar_demo.py
"""
import csv
import json
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from pricex.catalogo import CatalogoSimulado  # noqa: E402
from pricex.config import FECHA_HOY, PRODUCTOS  # noqa: E402
from pricex.evaluar import clave_para  # noqa: E402
from pricex.reglas import MOTIVOS, texto_valor  # noqa: E402
from pricex.respuesta import FRASES_MOTIVO, nombre_publicacion, texto_calificacion  # noqa: E402
from pricex.texto import fecha_larga  # noqa: E402

CAMPOS = [("producto", "Producto"), ("marca", "Marca"), ("modelo", "Modelo"), ("almacenamiento_gb", "Capacidad"),
          ("ram_gb", "RAM"), ("pulgadas", "Tamaño"), ("litros", "Litros"), ("kilos", "Kilos"),
          ("potencia_w", "Potencia"), ("color", "Color"), ("edicion", "Edición"), ("condicion", "Estado"),
          ("presupuesto_max", "Presupuesto"), ("fecha_limite", "Llegar a más tardar"), ("ciudad", "Ciudad")]
CORRIDAS = [("sin IA", RAIZ / "resultados" / "sin_ia", ""), ("v1", RAIZ / "resultados" / "gemini", "v1_"),
            ("v2", RAIZ / "resultados" / "gemini", "v2_")]


def leer_csv(ruta):
    with open(ruta, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def valor_entendido(campo, valor):
    if campo == "producto":
        return PRODUCTOS[valor][1]
    if campo == "presupuesto_max":
        return "$" + f"{valor:,}".replace(",", ".")
    if campo == "fecha_limite":
        return fecha_larga(valor)
    if campo in ("almacenamiento_gb", "ram_gb", "pulgadas", "litros", "kilos", "potencia_w"):
        return texto_valor(campo, valor)
    return str(valor)


def opcion(o, catalogo):
    pub = catalogo.por_id[o["id"]]
    llega = date.fromisoformat(o["llega"]) if o.get("llega") else None
    return {
        "puesto": o["puesto"], "id": o["id"], "nombre": o.get("nombre") or nombre_publicacion(pub), "total": o["total"],
        "precio": pub["precio"], "envio": pub["costo_envio"], "llega": fecha_larga(llega) if llega else None,
        "dias": (llega - FECHA_HOY).days if llega else None, "oficial": pub["tienda_oficial"],
        "vendedor": "Tienda oficial" if pub["tienda_oficial"] else pub["vendedor"], "reputacion": pub["reputacion"],
        "ventas": pub["ventas"], "cuotas": pub["cuotas"], "calificacion": texto_calificacion(pub),
        "condicion": pub["condicion"], "leido_del_titulo": o.get("leido_del_titulo"),
    }


def respuesta(r, catalogo):
    """Lo que muestra la demo de una respuesta: lo que entendió, el colador, las opciones y el mensaje."""
    conteo = {}
    for d in r["descartes"]:
        conteo[d["motivo"]] = conteo.get(d["motivo"], 0) + 1
    return {
        "pedido": r["pedido"], "pedido_completo": r.get("pedido_consolidado"), "accion": r["accion"],
        "situacion": r["situacion"], "razon": r["razon"],
        "entendi": [[nombre, valor_entendido(c, r["interpretacion"][c])] for c, nombre in CAMPOS
                    if r["interpretacion"].get(c) not in (None, "")],
        "revisadas": r["revisadas"], "validas": r.get("validas"),
        "colador": [[m, conteo[m], FRASES_MOTIVO[m][0 if conteo[m] == 1 else 1]] for m in MOTIVOS if m in conteo],
        "opciones": [opcion(o, catalogo) for o in r["opciones"]],
        "descartes": [{"id": d["id"], "nombre": nombre_publicacion(catalogo.por_id[d["id"]]), "motivo": d["motivo"],
                       "detalle": d["detalle"]} for d in r["descartes"]],
        "mensaje": r["mensaje"],
        "traza": r.get("traza"),
        "consultas": len(r["llamadas"]) if "llamadas" in r else None,
    }


def esperado_y_acierto(esperado, e, catalogo):
    ganador = esperado.get("ganador")
    return ({"accion": esperado["accion"], "situacion": esperado.get("situacion"), "ganador": ganador,
             "ganador_nombre": nombre_publicacion(catalogo.por_id[ganador]) if ganador else None},
            {"accion": e.get("acciones_ok", e["accion_ok"]) == "True", "top1": e["top1"] == "True",
             "grave": e["grave"] == "True", "motivo_grave": e["motivo_grave"], "campos_fallados": e["campos_fallados"]})


def registros(modo, carpeta, prefijo, catalogo, clave, textos, conversaciones):
    salida = []
    for conjunto in ("pedidos", "variantes", "conversaciones"):
        archivo = carpeta / f"respuestas_{prefijo}{conjunto}.jsonl"
        if not archivo.exists():
            continue
        evaluacion = {f["n"]: f for f in leer_csv(carpeta / f"evaluacion_{prefijo}{conjunto}.csv")}
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            r = json.loads(linea)
            n, e = r["n"], evaluacion[str(r["n"])]
            if conjunto == "conversaciones":
                c = conversaciones[n]
                final = c["turnos"][-1]
                esperado, acierto = esperado_y_acierto(final, e, catalogo)
                salida.append({"modo": modo, "conjunto": conjunto, "n": n, "que_prueba": c["que_prueba"],
                               "acciones_esperadas": [t["accion"] for t in c["turnos"]],
                               "turnos": [respuesta(t, catalogo) for t in r["turnos"]],
                               "esperado": esperado, "acierto": acierto})
                continue
            esperado, acierto = esperado_y_acierto(clave_para(clave[str(n)], modo), e, catalogo)
            salida.append({"modo": modo, "conjunto": conjunto, "n": n, **respuesta(r, catalogo),
                           "pedido": textos[conjunto][n]["texto"], "tipo": textos["pedidos"][n]["tipo"],
                           "trampa": textos["pedidos"][n]["trampa"],
                           "que_cambia": textos[conjunto][n].get("que_cambia", ""),
                           "esperado": esperado, "acierto": acierto})
    return salida


def main():
    catalogo = CatalogoSimulado(RAIZ / "datos" / "catalogo_simulado.json")
    clave = json.loads((RAIZ / "datos" / "clave_respuestas.json").read_text(encoding="utf-8"))["pedidos"]
    textos = {c: {int(f["n"]): f for f in leer_csv(RAIZ / "datos" / f"{c}.csv")} for c in ("pedidos", "variantes")}
    conversaciones = {c["id"]: c for c in
                      json.loads((RAIZ / "datos" / "conversaciones.json").read_text(encoding="utf-8"))["conversaciones"]}
    datos = {"congelado_el": catalogo.congelado_el, "resumenes": {}, "respuestas": []}
    for modo, carpeta, prefijo in CORRIDAS:
        datos["respuestas"] += registros(modo, carpeta, prefijo, catalogo, clave, textos, conversaciones)
        resumen = carpeta / "resumen.json"
        if not resumen.exists():
            continue
        informe = json.loads(resumen.read_text(encoding="utf-8"))
        if modo == "sin IA":
            datos["resumenes"]["sin IA"] = {c: informe[c]["resumen"] for c in ("pedidos", "variantes", "conversaciones")
                                            if c in informe}
        elif "resumenes" in informe:
            datos["resumenes"][modo] = {c: informe["resumenes"][f"{modo}, {c}"]
                                        for c in ("pedidos", "variantes", "conversaciones")
                                        if f"{modo}, {c}" in informe["resumenes"]}
            datos["modelo"] = informe.get("modelo")
    destino = RAIZ / "demo" / "datos_demo.json"
    destino.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    modos = sorted({r["modo"] for r in datos["respuestas"]})
    print(f"{destino.relative_to(RAIZ)}: {len(datos['respuestas'])} respuestas ({', '.join(modos)}), "
          f"{destino.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
