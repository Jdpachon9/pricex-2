"""Corre el asistente SIN IA (línea base) sobre los pedidos, las variantes y las conversaciones, y guarda los
resultados en resultados/sin_ia/.

Es la corrida que se puede hacer sin clave de ningún servicio. En las conversaciones usa la memoria más simple:
pega el pedido anterior y el mensaje nuevo. Las corridas con IA (v1 y v2) están en agente/pricex2_agente.ipynb.
Uso: python3 scripts/correr_sin_ia.py
"""
import csv
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from pricex.agente import Asistente, compactar  # noqa: E402
from pricex.catalogo import CatalogoSimulado  # noqa: E402
from pricex.evaluar import evaluar_conversacion, evaluar_respuesta, precision_por_campo, resumen  # noqa: E402
from pricex.multiagente import Conversacion, atender_uniendo  # noqa: E402

SALIDA = RAIZ / "resultados" / "sin_ia"
CONJUNTOS = {"pedidos": "pedidos.csv", "variantes": "variantes.csv"}


def leer(nombre):
    with open(RAIZ / "datos" / nombre, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def escribir_csv(ruta, filas):
    with open(ruta, "w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(filas[0]))
        escritor.writeheader()
        escritor.writerows(filas)


def imprimir(conjunto, r, filas):
    print(f"\n{conjunto}: acción {r.get('acciones_ok_en_todos_los_turnos', r['accion_correcta'])}/{r['pedidos']} · "
          f"interpretación perfecta {r['interpretacion_perfecta']}/{r['recomendables']} · top 1 "
          f"{r['top1']}/{r['recomendables']} · top 3 {r['top3']}/{r['recomendables']} · graves {r['graves']} · "
          f"recomendó sin deber {r['recomendo_sin_deber']}/{r['debian_preguntar_o_aclarar']}")
    for f in filas:
        if not (f["accion_ok"] and f["interpretacion_ok"] and f["top1"] in (True, None)) or f.get("acciones_ok") is False:
            print(f"   #{f['n']:>3} acción {f['accion']:<10} campos mal: {f['campos_fallados'] or '-':<30} "
                  f"top1 {f['top1']} grave {f['grave']} {f['motivo_grave']}")


def main():
    catalogo = CatalogoSimulado(RAIZ / "datos" / "catalogo_simulado.json")
    clave = json.loads((RAIZ / "datos" / "clave_respuestas.json").read_text(encoding="utf-8"))["pedidos"]
    asistente = Asistente(catalogo)
    SALIDA.mkdir(parents=True, exist_ok=True)
    informe = {"modo": "sin IA", "congelado_el": catalogo.congelado_el}
    for conjunto, archivo in CONJUNTOS.items():
        if not (RAIZ / "datos" / archivo).exists():
            continue
        respuestas, filas = {}, []
        for pedido in leer(archivo):
            n = int(pedido["n"])
            respuesta = asistente.atender(pedido["texto"])
            respuestas[n] = respuesta
            filas.append(evaluar_respuesta(n, respuesta, clave[str(n)], catalogo))
        with open(SALIDA / f"respuestas_{conjunto}.jsonl", "w", encoding="utf-8") as f:
            for n, r in respuestas.items():
                f.write(json.dumps({"n": n, **compactar(r)}, ensure_ascii=False) + "\n")
        escribir_csv(SALIDA / f"evaluacion_{conjunto}.csv", filas)
        informe[conjunto] = {"resumen": resumen(filas), "precision_por_campo": precision_por_campo(filas, respuestas, clave)}
        imprimir(conjunto, informe[conjunto]["resumen"], filas)

    conversaciones = json.loads((RAIZ / "datos" / "conversaciones.json").read_text(encoding="utf-8"))["conversaciones"]
    respuestas, filas = {}, []
    for c in conversaciones:
        conversacion = Conversacion()
        respuestas[c["id"]] = [atender_uniendo(asistente, conversacion, t["texto"]) for t in c["turnos"]]
        filas.append(evaluar_conversacion(c, respuestas[c["id"]]))
    with open(SALIDA / "respuestas_conversaciones.jsonl", "w", encoding="utf-8") as f:
        for id_conv, rs in respuestas.items():
            f.write(json.dumps({"n": id_conv, "turnos": [compactar(r) for r in rs]}, ensure_ascii=False) + "\n")
    escribir_csv(SALIDA / "evaluacion_conversaciones.csv", filas)
    informe["conversaciones"] = {"resumen": resumen(filas)}
    imprimir("conversaciones", informe["conversaciones"]["resumen"], filas)
    (SALIDA / "resumen.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
