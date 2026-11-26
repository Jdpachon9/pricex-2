"""Prueba de las reglas: con la interpretación correcta, ¿eligen lo que la clave dice?

No usa IA. Si esta prueba falla, el error está en las reglas o en los datos, no en el modelo.
Uso: python3 -m unittest discover -s pruebas
"""
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from pricex.catalogo import CatalogoSimulado, armar_consulta  # noqa: E402
from pricex.reglas import decidir  # noqa: E402

CATALOGO = CatalogoSimulado(RAIZ / "datos" / "catalogo_simulado.json")
CLAVE = json.loads((RAIZ / "datos" / "clave_respuestas.json").read_text(encoding="utf-8"))["pedidos"]


class PruebaReglas(unittest.TestCase):
    def test_cada_pedido_da_la_respuesta_esperada(self):
        for n, esperado in CLAVE.items():
            if esperado["accion"] != "recomendar":
                continue
            with self.subTest(pedido=n):
                pedido = esperado["interpretacion"]
                resultados = CATALOGO.buscar(armar_consulta(pedido))
                decision = decidir(pedido, resultados)
                self.assertEqual(decision["situacion"], esperado["situacion"])
                self.assertEqual([o["id"] for o in decision["opciones"]], esperado["top3"])
                encontrados = {p["id"] for p in resultados}
                motivos = {d["id"]: d["motivo"] for d in decision["descartes"]}
                for id_pub, motivo in esperado["descartes_esperados"].items():
                    self.assertIn(id_pub, encontrados, f"la búsqueda no encontró {id_pub}")
                    self.assertEqual(motivos.get(id_pub), motivo, id_pub)

    def test_las_publicaciones_con_instrucciones_quedan_fuera(self):
        sospechosas = [p for p in CATALOGO.publicaciones if "asistente" in p["textos_libres"].lower()
                       or "nota para la ia" in p["textos_libres"].lower()]
        self.assertEqual(len(sospechosas), 3)
        for pub in sospechosas:
            motivo = decidir({"producto": pub["producto"]}, [pub])["descartes"][0]["motivo"]
            self.assertEqual(motivo, "texto_sospechoso", pub["id"])


if __name__ == "__main__":
    unittest.main()
