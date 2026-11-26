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
from pricex.tablero import (RegistroDeUso, a_csv, comparar_corridas, evento_de, eventos_de_pruebas,  # noqa: E402
                            filtrar, lecturas, marcas_del_catalogo, resumen)

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


class Corridas(unittest.TestCase):
    """Las dos corridas reales con Gemini (resultados/gemini y resultados/gemini/corrida_1) y su calidad."""

    def test_lee_las_dos_corridas_y_la_linea_base(self):
        cuenta = {}
        for e in PRUEBAS:
            cuenta[(e["version"], e.get("corrida"))] = cuenta.get((e["version"], e.get("corrida")), 0) + 1
        self.assertEqual(cuenta, {("sin IA", None): 80, ("v1", 1): 80, ("v2", 1): 80, ("v1", 2): 80, ("v2", 2): 80})

    def test_la_calidad_cuadra_con_las_tablas_del_cuaderno(self):
        esperado = {("sin IA", None): (44, 6), ("v1", 1): (55, 0), ("v2", 1): (55, 0), ("v1", 2): (58, 0),
                    ("v2", 2): (59, 0)}  # 25 + 25 + 9 casos para recomendar
        for (version, corrida), (top1, graves) in esperado.items():
            c = resumen([e for e in PRUEBAS if e["version"] == version and e.get("corrida") == corrida])["calidad"]
            self.assertEqual((c["recomendables"], c["top1"], c["graves"]), (59, top1, graves), (version, corrida))

    def test_el_filtro_de_corrida_deja_la_linea_base(self):
        self.assertEqual(len(filtrar(PRUEBAS, corrida=1)), 240)  # sin IA + v1 y v2 de la corrida 1
        self.assertEqual(len(filtrar(PRUEBAS, version="v2", corrida=2)), 80)

    def test_el_antes_y_el_despues(self):
        filas = {(f["version"], f["corrida"]): f for f in comparar_corridas(PRUEBAS)}
        self.assertEqual((filas[("v2", 1)]["top1"], filas[("v2", 2)]["top1"]), (55, 59))
        self.assertLess(filas[("v2", 2)]["costo_usd"], filas[("v2", 1)]["costo_usd"])  # sin el revisor

    def test_el_csv_trae_la_corrida_y_el_veredicto(self):
        encabezado = a_csv(PRUEBAS[:1]).splitlines()[0].split(",")
        for columna in ("corrida", "conjunto", "accion_ok", "top1", "grave", "entendio"):
            self.assertIn(columna, encabezado)


class HojaFalsa:
    """Imita una pestaña de gspread: guarda las filas en memoria. No es Google Sheets: solo prueba el código."""

    def __init__(self, falla=False):
        self.filas, self.falla = [], falla

    def get_all_values(self, value_render_option=None):
        if self.falla:
            raise ConnectionError("sin red")
        return [list(f) for f in self.filas]

    def append_row(self, valores, value_input_option=None):
        if self.falla:
            raise ConnectionError("sin red")
        self.filas.append(list(valores))


class HojaDeGoogle(unittest.TestCase):
    def test_guarda_y_vuelve_a_leer_lo_mismo(self):
        from pricex.hoja import HojaDeUso
        falsa = HojaFalsa()
        eventos = filtrar(PRUEBAS, version="v2", corrida=2)
        registro = RegistroDeUso(hoja=HojaDeUso(falsa))
        for e in eventos:
            registro.agregar(e)
        self.assertEqual(len(falsa.filas), 81)  # el encabezado y una fila por mensaje
        self.assertNotIn(None, falsa.filas[1])  # las celdas vacías van como texto vacío
        leidos = RegistroDeUso(hoja=HojaDeUso(falsa)).eventos()  # la app se durmió y volvió a despertar
        antes, despues = resumen(eventos), resumen(leidos)
        for clave in ("mensajes", "con_opciones", "descartadas", "agentes", "calidad", "busquedas_extra"):
            self.assertEqual(antes[clave], despues[clave], clave)
        self.assertAlmostEqual(antes["costo_promedio_usd"], despues["costo_promedio_usd"])

    def test_si_la_hoja_falla_la_pagina_sigue(self):
        from pricex.hoja import HojaDeUso
        falsa = HojaFalsa()
        hoja = HojaDeUso(falsa)
        registro = RegistroDeUso(hoja=hoja)
        falsa.falla = True
        registro.agregar(PRUEBAS[0])
        self.assertEqual(len(registro.eventos()), 1)
        self.assertFalse(registro.guarda_en_hoja)
        self.assertIn("Google Sheets", registro.problema)


if __name__ == "__main__":
    unittest.main()
