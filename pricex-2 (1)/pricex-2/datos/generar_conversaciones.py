"""Genera datos/conversaciones.json: 10 conversaciones de dos mensajes para medir la memoria del equipo.

Cada turno trae la acción esperada (recomendar, preguntar o aclarar). El último turno trae además la interpretación
correcta del pedido completo, y la mejor opción esperada se calcula con las reglas sobre TODO el catálogo, como si
la búsqueda fuera perfecta. Así se mide también si la búsqueda llegó a la mejor opción que existe.

Como en los pedidos, el asistente nunca ve lo esperado: solo sirve para medirlo.
Uso: python3 datos/generar_conversaciones.py
"""
import json
import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARPETA.parent))

from pricex.config import FECHA_HOY  # noqa: E402
from pricex.catalogo import CatalogoSimulado  # noqa: E402
from pricex.evidencia import LEIBLES, valores  # noqa: E402
from pricex.interpretar import vacia  # noqa: E402
from pricex.reglas import decidir  # noqa: E402

R, P, A = "recomendar", "preguntar", "aclarar"
CONVERSACIONES = [
    ("C1", "Responder con el presupuesto la pregunta del asistente. Ojo: ningún título dice «celular»",
     [("un celular bueno y barato", P, {"producto": "celular"}),
      ("hasta 1 millón", R, {"producto": "celular", "presupuesto_max": 1000000})]),
    ("C2", "Cambiar solo el color y conservar todo lo demás",
     [("Samsung Galaxy S26 de 256 GB negro, máximo 4 millones", R,
       {"producto": "celular", "marca": "Samsung", "modelo": "Galaxy S26", "almacenamiento_gb": 256, "color": "negro",
        "presupuesto_max": 4000000}),
      ("y en azul?", R, {"producto": "celular", "marca": "Samsung", "modelo": "Galaxy S26", "almacenamiento_gb": 256,
                         "color": "azul", "presupuesto_max": 4000000})]),
    ("C3", "Un pedido ambiguo que se aclara en el segundo mensaje",
     [("algo bonito para regalarle a mi mamá", P, {}),
      ("una freidora de aire, que no pase de 300 mil", R, {"producto": "freidora_de_aire", "presupuesto_max": 300000})]),
    ("C4", "Dar tamaño y presupuesto después de una pregunta",
     [("quiero cambiar el televisor", P, {"producto": "televisor"}),
      ("de 55 pulgadas, máximo 2 millones", R, {"producto": "televisor", "pulgadas": 55, "presupuesto_max": 2000000})]),
    ("C5", "Cambiar la capacidad",
     [("iPhone 16 de 128", R, {"producto": "celular", "marca": "Apple", "modelo": "iPhone 16", "almacenamiento_gb": 128}),
      ("mejor de 256", R, {"producto": "celular", "marca": "Apple", "modelo": "iPhone 16", "almacenamiento_gb": 256})]),
    ("C6", "Agregar la marca a un pedido abierto",
     [("portátil con 16 de RAM, máximo 2,5 millones", R, {"producto": "portatil", "ram_gb": 16, "presupuesto_max": 2500000}),
      ("que sea Lenovo", R, {"producto": "portatil", "marca": "Lenovo", "ram_gb": 16, "presupuesto_max": 2500000})]),
    ("C7", "Agregar fecha y ciudad de entrega",
     [("audífonos sony wh-1000xm5", R, {"producto": "audifonos", "marca": "Sony", "modelo": "WH-1000XM5"}),
      ("que lleguen mañana a Bogotá", R, {"producto": "audifonos", "marca": "Sony", "modelo": "WH-1000XM5",
                                          "fecha_limite": "2026-11-23", "ciudad": "Bogotá"})]),
    ("C8", "Empezar con algo fuera de alcance y luego hacer un pedido",
     [("¿está más barato en otra tienda?", A, {"motivo_aclaracion": "otra_tienda"}),
      ("bueno, entonces busca una nevera de mínimo 300 litros hasta 2,5 millones", R,
       {"producto": "nevera", "litros": 300, "presupuesto_max": 2500000})]),
    ("C9", "Pedir a mitad de conversación que el asistente pague con una tarjeta (número de prueba, no real)",
     [("Xiaomi Redmi Note 14 de 256", R, {"producto": "celular", "marca": "Xiaomi", "modelo": "Redmi Note 14",
                                          "almacenamiento_gb": 256}),
      ("cómpralo tú con mi tarjeta 4111 1111 1111 1111", A, {"motivo_aclaracion": "pagos"})]),
    ("C10", "Saludar primero y pedir después",
     [("hola", P, {}),
      ("busco una cafetera Nespresso", R, {"producto": "cafetera", "marca": "Nespresso"})]),
]


def interpretacion(accion, campos):
    i = vacia()
    i.update(accion=accion, condicion="nuevo" if accion == R else None)
    i.update(campos)
    i.pop("pregunta")
    return i


def lector_perfecto(publicaciones, pedido):
    """Completa con el título los datos pedidos que la ficha no trae, solo si el título dice un único valor."""
    completas = []
    for p in publicaciones:
        p = dict(p)
        for campo in LEIBLES:
            if pedido.get(campo) not in (None, "") and p.get(campo) in (None, ""):
                en_titulo = valores(campo, p["titulo"])
                if len(en_titulo) == 1:
                    p[campo] = en_titulo.pop()
        completas.append(p)
    return completas


def main():
    catalogo = CatalogoSimulado(CARPETA / "catalogo_simulado.json")
    salida = []
    for id_conv, que_prueba, turnos in CONVERSACIONES:
        filas = []
        for k, (texto, accion, campos) in enumerate(turnos, start=1):
            fila = {"turno": k, "texto": texto, "accion": accion, "interpretacion": interpretacion(accion, campos)}
            if k == len(turnos) and accion == R:
                decision = decidir(fila["interpretacion"], lector_perfecto(catalogo.publicaciones, fila["interpretacion"]),
                                   FECHA_HOY)
                top3 = [o["id"] for o in decision["opciones"]]
                fila.update(situacion=decision["situacion"], ganador=top3[0] if top3 else None, top3=top3,
                            validas_en_catalogo=decision["validas"])
            filas.append(fila)
        salida.append({"id": id_conv, "que_prueba": que_prueba, "turnos": filas})
        final = filas[-1]
        print(f"{id_conv}: {' → '.join(t['accion'] for t in filas)}"
              + (f" · gana {final['ganador']} ({final['validas_en_catalogo']} cumplen en todo el catálogo)"
                 if final.get("ganador") else ""))
    nota = ("Conversaciones de prueba de PriceX 2.0 (simuladas). La mejor opción esperada sale de aplicar las reglas a "
            "todo el catálogo simulado, como si la búsqueda fuera perfecta. El asistente nunca ve este archivo.")
    (CARPETA / "conversaciones.json").write_text(
        json.dumps({"congelado_el": catalogo.congelado_el, "nota": nota, "conversaciones": salida},
                   ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
