"""Pruebas de los controles: datos sensibles, revisión de la interpretación y verificación del mensaje.

Uso: python3 -m unittest discover -s pruebas
"""
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from pricex.catalogo import CatalogoSimulado, armar_consulta  # noqa: E402
from pricex.interpretar import ajustar_accion, extraer_json, revisar_interpretacion  # noqa: E402
from pricex.reglas import decidir  # noqa: E402
from pricex.respuesta import datos_para_explicar, verificar_mensaje  # noqa: E402
from pricex.sensibles import tapar_datos_sensibles  # noqa: E402

CATALOGO = CatalogoSimulado(RAIZ / "datos" / "catalogo_simulado.json")
PEDIDO = {"producto": "celular", "marca": "Samsung", "modelo": "Galaxy S26", "almacenamiento_gb": 256,
          "color": "negro", "condicion": "nuevo", "presupuesto_max": 4000000}


def datos_ejemplo():
    decision = decidir(PEDIDO, CATALOGO.buscar(armar_consulta(PEDIDO)))
    return datos_para_explicar("Samsung Galaxy S26 de 256 GB negro", PEDIDO, decision)


class DatosSensibles(unittest.TestCase):
    def test_tapa_tarjeta_correo_y_telefono(self):
        texto, tapados = tapar_datos_sensibles("págalo con 4111 1111 1111 1111, escríbeme a ana@correo.com o al 300 123 4567")
        self.assertNotIn("4111", texto)
        self.assertIn("[TARJETA]", texto)
        self.assertIn("[CORREO]", texto)
        self.assertIn("[TELEFONO]", texto)
        self.assertEqual(sorted(tapados), ["correo", "tarjeta", "telefono"])

    def test_no_tapa_precios_ni_numeros_que_no_son_tarjeta(self):
        texto, tapados = tapar_datos_sensibles("máximo $3.849.000, referencia 1234 5678 9012 3456")
        self.assertIn("3.849.000", texto)
        self.assertIn("1234 5678 9012 3456", texto)  # no pasa la prueba de Luhn
        self.assertEqual(tapados, [])


class RevisionDeLaInterpretacion(unittest.TestCase):
    def test_limpia_y_valida(self):
        dato = {"accion": "recomendar", "producto": "bicicleta", "modelo": "Galaxy S26 256GB negro",
                "presupuesto_max": "4000000", "fecha_limite": "2020-01-01"}
        r, problemas = revisar_interpretacion(dato)
        self.assertIsNone(r["producto"])
        self.assertEqual(r["modelo"], "Galaxy S26")
        self.assertEqual(r["presupuesto_max"], 4000000)
        self.assertIsNone(r["fecha_limite"])
        self.assertTrue(any("producto fuera de la lista" in p for p in problemas))
        self.assertTrue(any("pasado" in p for p in problemas))

    def test_acepta_el_producto_escrito_de_otra_forma(self):
        for escrito, clave in [("lector de libros", "lector_libros"), ("Freidora de aire", "freidora_de_aire"),
                               ("TV", "televisor"), ("memoria_microsd", "memoria_microsd")]:
            r, _ = revisar_interpretacion({"accion": "recomendar", "producto": escrito})
            self.assertEqual(r["producto"], clave, escrito)

    def test_las_reglas_de_accion_las_pone_el_codigo(self):
        r, _ = revisar_interpretacion({"accion": "recomendar", "producto": None})
        self.assertEqual(ajustar_accion(r)["accion"], "preguntar")
        r, _ = revisar_interpretacion({"accion": "recomendar", "producto": "celular"})
        self.assertEqual(ajustar_accion(r)["accion"], "preguntar")  # sin nada específico: hay que preguntar
        r, _ = revisar_interpretacion({"accion": "recomendar", "producto": "celular", "marca": "Samsung"})
        self.assertEqual(ajustar_accion(r, tapados=["tarjeta"])["accion"], "aclarar")

    def test_extrae_json_con_texto_alrededor(self):
        self.assertEqual(extraer_json('Claro: ```json\n{"accion": "preguntar"}\n```')["accion"], "preguntar")
        self.assertIsNone(extraer_json("no sé"))


class VerificacionDelMensaje(unittest.TestCase):
    def test_mensaje_con_cifras_exactas_pasa(self):
        datos = datos_ejemplo()
        primera = datos["opciones"][0]
        mensaje = (f"Te recomiendo el {primera['nombre']} por {primera['total']}, con envío gratis y "
                   f"{primera['cuotas']}. Llega el {primera['llega']}. Tú decides y compras desde el enlace.")
        self.assertEqual(verificar_mensaje(mensaje, datos), [])

    def test_cifra_inventada_o_redondeada_no_pasa(self):
        datos = datos_ejemplo()
        total = datos["opciones"][0]["total"]
        self.assertTrue(verificar_mensaje(f"Cuesta {total} y tiene 24 cuotas sin interés.", datos))
        self.assertTrue(verificar_mensaje(f"Cuesta {total}, unos 3,8 millones.", datos))

    def test_enlace_o_precio_equivocado_no_pasa(self):
        datos = datos_ejemplo()
        total = datos["opciones"][0]["total"]
        self.assertIn("trae un enlace", verificar_mensaje(f"Cómpralo en https://ejemplo.com por {total}", datos))
        segunda = datos["opciones"][1]["total"]
        self.assertIn("no menciona el precio de la opción elegida", verificar_mensaje(f"Compra el de {segunda}.", datos))

    def test_al_modelo_no_le_llega_texto_de_vendedores(self):
        datos = str(datos_ejemplo())
        for pub in CATALOGO.publicaciones:
            if pub["descripcion"]:
                self.assertNotIn(pub["descripcion"][:30], datos)
        self.assertNotIn("_SIM", datos)  # ni los apodos de los vendedores


if __name__ == "__main__":
    unittest.main()
