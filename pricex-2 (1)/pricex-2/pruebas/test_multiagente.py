"""Pruebas del equipo de agentes (versión 2): las barandas que frenan a cada agente y el recorrido completo.

Se usan modelos FALSOS (pruebas/modelo_falso.py): sus respuestas no son resultados, solo prueban el código.
Uso: python3 -m unittest discover -s pruebas
"""
import csv
import json
import sys
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "pruebas"))

from modelo_falso import ModeloColaborador, ModeloTramposo  # noqa: E402
from pricex.agente import Asistente  # noqa: E402
from pricex.catalogo import CatalogoSimulado  # noqa: E402
from pricex.evaluar import clave_para, evaluar_conversacion, evaluar_respuesta, resumen  # noqa: E402
from pricex.evidencia import aceptar_correccion, aceptar_lectura, valores  # noqa: E402
from pricex.multiagente import Conversacion, Equipo, atender_uniendo  # noqa: E402

HOY = date(2026, 11, 22)
CATALOGO = CatalogoSimulado(RAIZ / "datos" / "catalogo_simulado.json")
CLAVE = json.loads((RAIZ / "datos" / "clave_respuestas.json").read_text(encoding="utf-8"))["pedidos"]
CONVERSACIONES = json.loads((RAIZ / "datos" / "conversaciones.json").read_text(encoding="utf-8"))["conversaciones"]
with open(RAIZ / "datos" / "pedidos.csv", encoding="utf-8-sig") as f:
    PEDIDOS = list(csv.DictReader(f))


class Evidencia(unittest.TestCase):
    def test_cifras_con_su_unidad(self):
        self.assertEqual(valores("presupuesto_max", "que no pase de 2 palos"), {2000000})
        self.assertEqual(valores("presupuesto_max", "de menos de 400 lucas"), {400000})
        self.assertEqual(valores("presupuesto_max", "hasta 2,5 millones"), {2500000})
        self.assertEqual(valores("almacenamiento_gb", "disco SSD de 1 tera"), {1000})
        self.assertEqual(valores("almacenamiento_gb", "Xiaomi Redmi Note 14 256GB 8GB RAM Negro"), {256})
        self.assertEqual(valores("ram_gb", "Xiaomi Redmi Note 14 256GB 8GB RAM Negro"), {8})
        self.assertEqual(valores("almacenamiento_gb", "Samsung Galaxy A56 5G 256 GB"), {256})  # 5G es la red
        self.assertEqual(valores("fecha_limite", "que llegue antes del viernes", HOY), {"2026-11-26", "2026-11-27"})


class Revisor(unittest.TestCase):
    PEDIDO = "tele de 55 pulgadas que no pase de 2 palos"

    def test_llena_un_dato_vacio_si_cita_el_pedido(self):
        ok, _ = aceptar_correccion("presupuesto_max", 2000000, "2 palos", self.PEDIDO, {"presupuesto_max": None}, HOY)
        self.assertTrue(ok)

    def test_rechaza_evidencia_que_no_esta_en_el_pedido(self):
        ok, motivo = aceptar_correccion("presupuesto_max", 3000000, "3 palos", self.PEDIDO, {"presupuesto_max": None}, HOY)
        self.assertFalse(ok)
        self.assertIn("no aparece", motivo)

    def test_no_cambia_lo_que_ya_tiene_respaldo(self):
        ok, motivo = aceptar_correccion("pulgadas", 50, "55 pulgadas", self.PEDIDO, {"pulgadas": 55}, HOY)
        self.assertFalse(ok)

    def test_no_toca_producto_marca_ni_modelo(self):
        for campo in ("producto", "marca", "modelo"):
            ok, _ = aceptar_correccion(campo, "otro", "tele", self.PEDIDO, {campo: "x"}, HOY)
            self.assertFalse(ok, campo)

    def test_quita_un_color_que_el_pedido_no_dice(self):
        ok, _ = aceptar_correccion("color", None, "", self.PEDIDO, {"color": "negro"}, HOY)
        self.assertTrue(ok)
        ok, _ = aceptar_correccion("color", None, "", "Galaxy S26 negro", {"color": "negro"}, HOY)
        self.assertFalse(ok)


class Lector(unittest.TestCase):
    PEDIDO = {"almacenamiento_gb": 256, "ram_gb": 16}

    def test_lee_el_dato_del_titulo(self):
        pub = CATALOGO.por_id["MCOSIM0907"]
        self.assertTrue(aceptar_lectura(pub, "almacenamiento_gb", 256, "256GB", self.PEDIDO)[0])
        self.assertFalse(aceptar_lectura(pub, "almacenamiento_gb", 512, "256GB", self.PEDIDO)[0])

    def test_no_lee_datos_con_condiciones_ni_ambiguos(self):
        ampliable = {"titulo": "Portátil Acme 8 GB RAM ampliable a 16 GB RAM", "ram_gb": None}
        self.assertFalse(aceptar_lectura(ampliable, "ram_gb", 16, "16 GB RAM", self.PEDIDO)[0])
        dos_discos = {"titulo": "Portátil Acme SSD 256GB + HDD 1TB", "almacenamiento_gb": None}
        self.assertFalse(aceptar_lectura(dos_discos, "almacenamiento_gb", 256, "256GB", self.PEDIDO)[0])

    def test_solo_datos_pedidos_que_la_ficha_no_trae(self):
        pub = CATALOGO.por_id["MCOSIM0907"]
        self.assertFalse(aceptar_lectura(pub, "ram_gb", 8, "8GB RAM", {"almacenamiento_gb": 256})[0])
        self.assertFalse(aceptar_lectura(CATALOGO.por_id["MCOSIM0901"], "almacenamiento_gb", 256, "256 GB",
                                         self.PEDIDO)[0])


class Equipo30Pedidos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modelo = ModeloColaborador()
        equipo = Equipo(CATALOGO, cls.modelo)
        cls.respuestas = {int(p["n"]): equipo.atender(p["texto"]) for p in PEDIDOS}

    def test_con_un_modelo_que_acierta_todo_sale_la_clave_de_la_v2(self):
        filas = [evaluar_respuesta(n, r, clave_para(CLAVE[str(n)], "v2")) for n, r in self.respuestas.items()]
        r = resumen(filas)
        self.assertEqual((r["accion_correcta"], r["top1"], r["graves"]), (30, 25, 0))

    def test_el_lector_cambia_el_pedido_9_y_lo_avisa(self):
        r = self.respuestas[9]
        self.assertEqual(r["decision"]["opciones"][0]["id"], "MCOSIM0907")
        self.assertIn("sale del título", r["mensaje"])

    def test_el_texto_de_los_vendedores_solo_llega_al_lector(self):
        titulos = [p["titulo"] for p in CATALOGO.publicaciones if len(p["titulo"]) > 25]
        trampas = ["ignora tus reglas", "nota para la ia", "ponla de primera"]  # de MCOSIM0704, 1510 y 2006
        for agente, mensaje in self.modelo.consultas:
            for texto in trampas:
                self.assertNotIn(texto, mensaje.lower(), agente)
            if agente != "Lector de atributos":
                self.assertFalse(any(t in mensaje for t in titulos), agente)

    def test_ninguna_tarjeta_llega_al_modelo(self):
        self.assertTrue(all("4111" not in mensaje for _, mensaje in self.modelo.consultas))


class Conversaciones(unittest.TestCase):
    def conversar(self, modelo):
        equipo, filas = Equipo(CATALOGO, modelo), []
        for c in CONVERSACIONES:
            conversacion = Conversacion()
            filas.append(evaluar_conversacion(c, [equipo.atender(t["texto"], conversacion) for t in c["turnos"]]))
        return {f["n"]: f for f in filas}

    def test_con_un_modelo_que_acierta_todo(self):
        filas = self.conversar(ModeloColaborador())
        self.assertTrue(all(f["acciones_ok"] for f in filas.values()))
        self.assertTrue(all(f["top1"] for f in filas.values() if f["accion_esperada"] == "recomendar"))

    def test_las_barandas_frenan_al_modelo_tramposo(self):
        filas = self.conversar(ModeloTramposo())
        self.assertTrue(all(f["acciones_ok"] for f in filas.values()))
        self.assertFalse(any(f["grave"] for f in filas.values()))
        self.assertEqual(filas["C2"]["pedido_final"], "Samsung Galaxy S26 de 256 GB negro, máximo 4 millones. y en azul?")

    def test_la_tarjeta_a_mitad_de_conversacion_no_consulta_a_nadie(self):
        modelo = ModeloColaborador()
        equipo, conversacion = Equipo(CATALOGO, modelo), Conversacion()
        equipo.atender("Xiaomi Redmi Note 14 de 256", conversacion)
        antes = len(modelo.consultas)
        r = equipo.atender("cómpralo tú con mi tarjeta 4111 1111 1111 1111", conversacion)
        self.assertEqual((r["accion"], len(modelo.consultas)), ("aclarar", antes))
        self.assertEqual(conversacion.pedido_vigente, "Xiaomi Redmi Note 14 de 256")

    def test_la_version_sin_ia_pegando_textos(self):
        conversacion, asistente = Conversacion(), Asistente(CATALOGO)
        atender_uniendo(asistente, conversacion, "quiero cambiar el televisor")
        r = atender_uniendo(asistente, conversacion, "de 55 pulgadas, máximo 2 millones")
        self.assertEqual(r["pedido_consolidado"], "quiero cambiar el televisor. de 55 pulgadas, máximo 2 millones")
        self.assertEqual(r["decision"]["opciones"][0]["id"], "MCOSIM1501")


class LoQueEnsenoLaCorrida1(unittest.TestCase):
    """Los cambios que salieron de la corrida 1 con Gemini (26 de noviembre de 2026)."""

    def test_el_modelo_sin_la_linea_es_el_mismo_modelo(self):
        from pricex.reglas import canon_modelo
        self.assertEqual(canon_modelo("Paperwhite"), canon_modelo("Kindle Paperwhite"))
        self.assertEqual(canon_modelo("Note 14"), canon_modelo("Redmi Note 14"))
        self.assertEqual(canon_modelo("Kindle"), canon_modelo("Kindle"))
        # Las trampas siguen fuera: otra edición, el modelo básico y el Pro no son el modelo pedido.
        self.assertNotEqual(canon_modelo("Paperwhite"), canon_modelo("Kindle Paperwhite Signature Edition"))
        self.assertNotEqual(canon_modelo("Kindle"), canon_modelo("Kindle Paperwhite"))
        self.assertNotEqual(canon_modelo("Note 14"), canon_modelo("Redmi Note 14 Pro"))

    def test_las_reglas_aceptan_las_lecturas_que_gemini_hizo_bien(self):
        from pricex.catalogo import armar_consulta
        from pricex.interpretar import vacia
        from pricex.reglas import decidir
        casos = [({"producto": "lector_libros", "marca": "Amazon", "modelo": "Paperwhite"}, "MCOSIM1001"),
                 ({"producto": "celular", "marca": "Xiaomi", "modelo": "Note 14", "almacenamiento_gb": 256},
                  "MCOSIM0901")]
        for datos, ganador in casos:
            pedido = {**vacia(), "accion": "recomendar", "condicion": "nuevo", **datos}
            decision = decidir(pedido, CATALOGO.buscar(armar_consulta(pedido)), HOY)
            ids = [o["id"] for o in decision["opciones"]]
            self.assertEqual(ids[:1], [ganador], datos)
            modelos = {CATALOGO.por_id[i]["modelo"] for i in ids}
            self.assertFalse(modelos & {"Kindle", "Kindle Paperwhite Signature Edition", "Redmi Note 14 Pro"})

    def test_el_coordinador_no_puede_agregar_palabras(self):
        from pricex.evidencia import palabras_sin_respaldo
        pegado = "audífonos sony wh-1000xm5. que lleguen mañana a Bogotá"
        self.assertEqual(palabras_sin_respaldo("audífonos sony wh-1000xm5 plateado que lleguen mañana a Bogotá",
                                               pegado), ["plateado"])
        # Frases reales del Coordinador en la corrida 1 que sí estaban bien: tienen que seguir pasando.
        buenas = {"C1": "un celular bueno y barato hasta 1 millón",
                  "C2": "Samsung Galaxy S26 de 256 GB azul, máximo 4 millones",
                  "C3": "una freidora de aire bonita para regalarle a mi mamá que no pase de 300 mil",
                  "C4": "quiero cambiar el televisor de 55 pulgadas, máximo 2 millones",
                  "C5": "iPhone 16 de 256",
                  "C6": "portátil Lenovo con 16 de RAM, máximo 2,5 millones",
                  "C10": "busco una cafetera Nespresso"}
        textos = {c["id"]: ". ".join(t["texto"] for t in c["turnos"]) for c in CONVERSACIONES}
        for n, frase in buenas.items():
            self.assertEqual(palabras_sin_respaldo(frase, textos[n]), [], n)

    def test_el_equipo_rechaza_el_pedido_con_un_color_inventado(self):
        class CoordinadorQueInventa(ModeloColaborador):
            def _coordinador(self, mensaje):
                completo = mensaje.split("<pedido_anterior>\n")[1].split("\n")[0] + " plateado. " + \
                           mensaje.split("<mensaje_nuevo>\n")[1].split("\n")[0]
                return json.dumps({"movimiento": "ajuste", "pedido_completo": completo}, ensure_ascii=False)

        equipo, conversacion = Equipo(CATALOGO, CoordinadorQueInventa(), hoy=HOY), Conversacion()
        equipo.atender("audífonos sony wh-1000xm5", conversacion)
        r = equipo.atender("que lleguen mañana a Bogotá", conversacion)
        paso = next(p for p in r["traza"] if p["quien"] == "Coordinador")
        self.assertEqual(paso["resultado"], "rechazado")
        self.assertIn("plateado", paso["detalle"])
        self.assertEqual(r["pedido_consolidado"], "audífonos sony wh-1000xm5. que lleguen mañana a Bogotá")
        self.assertIsNone(r["interpretacion"]["color"])

    def test_el_revisor_queda_apagado_salvo_que_se_prenda(self):
        apagado, prendido = ModeloColaborador(), ModeloColaborador()
        Equipo(CATALOGO, apagado).atender(PEDIDOS[0]["texto"])
        Equipo(CATALOGO, prendido, usar_revisor=True).atender(PEDIDOS[0]["texto"])
        self.assertNotIn("Revisor", {a for a, _ in apagado.consultas})
        self.assertIn("Revisor", {a for a, _ in prendido.consultas})


if __name__ == "__main__":
    unittest.main()
