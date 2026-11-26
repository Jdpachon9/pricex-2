"""Pruebas del tablero: el registro no guarda texto personal, las cuentas cuadran y las lecturas se arman bien.

Uso: python3 -m unittest discover -s pruebas
"""
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "pruebas"))

from modelo_falso import ModeloColaborador  # noqa: E402
from pricex.catalogo import CatalogoSimulado  # noqa: E402
from pricex.multiagente import Conversacion, Equipo  # noqa: E402
from pricex.tablero import (RegistroDeUso, a_csv, evento_de, eventos_de_pruebas, filtrar, lecturas,  # noqa: E402
                            marcas_del_catalogo, resumen)

CATALOGO = CatalogoSimulado(RAIZ / "datos" / "catalogo_simulado.json")
MARCAS = marcas_del_catalogo(CATALOGO)
PRUEBAS = eventos_de_pruebas(RAIZ, MARCAS)


class Registro(unittest.TestCase):
    def test_no_guarda_el_texto_de_la_persona(self):
        r = Equipo(CATALOGO, ModeloColaborador()).atender("tele de 55 pulgadas que no pase de 2 palos")
        evento = evento_de(r, sesion="s", marcas=MARCAS)
        self.assertNotIn("tele de 55", str(evento))
        self.assertEqual((evento["producto"], evento["version"], evento["presupuesto"]), ("televisor", "v2", 2000000))
        self.assertEqual(evento["revisadas"], evento["validas"] + sum(evento["descartes"].values()))
        self.assertGreater(evento["costo_usd"], 0)

    def test_una_marca_que_no_esta_en_el_catalogo_se_guarda_como_otra(self):
        respuesta = {"accion": "recomendar", "modo": "sin IA",
                     "interpretacion": {"producto": "celular", "marca": "Mi tía Rosa"}}
        self.assertEqual(evento_de(respuesta, marcas=MARCAS)["marca"], "otra")

    def test_sobrevive_en_el_archivo_mientras_la_app_esta_despierta(self):
        ruta = Path(tempfile.mkdtemp()) / "eventos.jsonl"
        registro = RegistroDeUso(ruta)
        for evento in PRUEBAS[:5]:
            registro.agregar(evento)
        self.assertEqual(len(RegistroDeUso(ruta).eventos()), 5)


class Resumen(unittest.TestCase):
    def test_las_cuentas_cuadran_con_la_corrida_sin_ia(self):
        eventos = filtrar(PRUEBAS, version="sin IA")
        r = resumen(eventos)
        self.assertEqual(r["mensajes"], 80)  # 30 pedidos, 30 variantes y 20 turnos de conversación
        etapas = [n for _, n in r["embudo"]]
        self.assertEqual(etapas, sorted(etapas, reverse=True))
        self.assertEqual(r["revisadas"], r["validas"] + r["descartadas"])
        self.assertEqual(r["motivos"][0][0], "otro_producto")

    def test_el_filtro_de_producto(self):
        self.assertEqual(len(filtrar(PRUEBAS, producto="celular", version="sin IA")), 18)

    def test_lecturas_sin_datos_y_con_pocos_datos(self):
        self.assertEqual(lecturas(resumen([]))[0][0], "Todavía no hay datos")
        titulos = [t for t, _ in lecturas(resumen(PRUEBAS[:4]))]
        self.assertEqual(titulos[0], "Ojo con la muestra")

    def test_lecturas_de_un_equipo_con_ia(self):
        equipo, conversacion = Equipo(CATALOGO, ModeloColaborador()), Conversacion()
        eventos = [evento_de(equipo.atender(t, conversacion), marcas=MARCAS)
                   for t in ["Samsung Galaxy S26 de 256 GB negro, máximo 4 millones", "y en azul?"]]
        frases = dict(lecturas(resumen(eventos)))
        self.assertIn("¿Qué hizo el equipo de agentes?", frases)
        self.assertIn("una venta paga", frases["¿Cuánto cuesta y cuánto vale?"])

    def test_el_csv_trae_una_fila_por_mensaje_y_sin_texto(self):
        texto = a_csv(PRUEBAS[:10])
        filas = texto.strip().splitlines()
        self.assertEqual(len(filas), 11)
        self.assertTrue(filas[0].startswith("momento,origen,version"))
        self.assertNotIn("Samsung Galaxy S26 de 256 GB negro", texto)


if __name__ == "__main__":
    unittest.main()
