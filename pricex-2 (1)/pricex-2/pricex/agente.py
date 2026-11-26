"""El asistente completo: del pedido de la persona a la respuesta, en cuatro pasos.

1. Tapar datos sensibles (tarjetas, correos, teléfonos).
2. Interpretar el pedido: con IA o con patrones de texto (línea base). El código revisa la interpretación.
3. Buscar y aplicar las reglas: qué queda fuera y en qué orden se muestran las que sirven.
4. Redactar la respuesta: plantilla, o IA con verificación de cifras.

La compra la hace la persona desde el enlace. El asistente no paga ni guarda datos de pago.
"""
import time

from .catalogo import armar_consulta
from .config import CIUDAD_POR_DEFECTO, FECHA_HOY
from .interpretar import ajustar_accion, interpretar_con_ia
from .linea_base import interpretar_sin_ia
from .reglas import decidir
from .respuesta import ACLARACIONES, datos_para_explicar, explicar_con_ia, mensaje_plantilla, pregunta_plantilla
from .sensibles import tapar_datos_sensibles


class Asistente:
    def __init__(self, catalogo, llamar=None, redactar_con_ia=False, hoy=FECHA_HOY,
                 ciudad_por_defecto=CIUDAD_POR_DEFECTO):
        """'llamar' es la función que habla con el modelo de IA. Sin ella, el asistente funciona sin IA."""
        self.catalogo = catalogo
        self.llamar = llamar
        self.redactar_con_ia = bool(redactar_con_ia and llamar)
        self.hoy = hoy
        self.ciudad_por_defecto = ciudad_por_defecto

    @property
    def modo(self):
        return "con IA" if self.llamar else "sin IA"

    def atender(self, texto):
        inicio = time.time()
        texto_tapado, tapados = tapar_datos_sensibles(texto)
        if self.llamar:
            propuesta, meta_interpretacion = interpretar_con_ia(texto_tapado, self.llamar, self.hoy)
        else:
            propuesta, meta_interpretacion = interpretar_sin_ia(texto_tapado, self.hoy), {"segundos": 0.0, "problemas": []}
        interpretacion = ajustar_accion(propuesta, tapados)
        respuesta = {"pedido": texto, "pedido_tapado": texto_tapado, "tapados": tapados, "modo": self.modo,
                     "propuesta": propuesta, "interpretacion": interpretacion,
                     "meta_interpretacion": meta_interpretacion, "accion": interpretacion["accion"], "consulta": None,
                     "decision": None, "datos": None, "mensaje": None, "meta_redaccion": None}
        if interpretacion["accion"] == "recomendar":
            consulta = armar_consulta(interpretacion)
            decision = decidir(interpretacion, self.catalogo.buscar(consulta), self.hoy, self.ciudad_por_defecto)
            datos = datos_para_explicar(texto_tapado, interpretacion, decision, self.hoy)
            if self.redactar_con_ia:
                mensaje, meta_redaccion = explicar_con_ia(datos, self.llamar)
            else:
                mensaje, meta_redaccion = mensaje_plantilla(datos), {"usado": "plantilla", "problemas": []}
            respuesta.update(consulta=consulta, decision=decision, datos=datos, mensaje=mensaje,
                             meta_redaccion=meta_redaccion)
        elif interpretacion["accion"] == "preguntar":
            respuesta["mensaje"] = interpretacion.get("pregunta") or pregunta_plantilla(interpretacion)
        else:
            respuesta["mensaje"] = ACLARACIONES[interpretacion.get("motivo_aclaracion") or "otro"]
        respuesta["segundos_total"] = round(time.time() - inicio, 3)
        return respuesta


def compactar(respuesta):
    """Versión liviana de la respuesta para guardarla en el registro (una línea por pedido)."""
    from .respuesta import nombre_publicacion

    decision = respuesta.get("decision") or {}
    compacta = {
        "pedido": respuesta["pedido_tapado"], "tapados": respuesta["tapados"], "modo": respuesta["modo"],
        "propuesta": respuesta["propuesta"], "interpretacion": respuesta["interpretacion"],
        "meta_interpretacion": respuesta["meta_interpretacion"], "accion": respuesta["accion"],
        "consulta": respuesta.get("consulta"), "situacion": decision.get("situacion"), "razon": decision.get("razon"),
        "revisadas": decision.get("revisadas"), "validas": decision.get("validas"),
        "opciones": [{"puesto": o["puesto"], "id": o["id"], "nombre": nombre_publicacion(o), "total": o["total"],
                      "llega": o.get("llega"), "enlace": o.get("enlace"),
                      **({"leido_del_titulo": o["leido_del_titulo"]} if o.get("leido_del_titulo") else {})}
                     for o in decision.get("opciones", [])],
        "descartes": [{"id": d["id"], "motivo": d["motivo"], "detalle": d["detalle"]}
                      for d in decision.get("descartes", [])],
        "mensaje": respuesta["mensaje"], "meta_redaccion": respuesta.get("meta_redaccion"),
        "segundos_total": respuesta.get("segundos_total"),
    }
    # Lo que agrega la versión 2: la memoria de la conversación y la traza de cada agente
    for campo in ("turno", "pedido_consolidado", "movimiento", "busquedas", "correcciones", "lecturas", "traza",
                  "llamadas"):
        if campo in respuesta:
            compacta[campo] = respuesta[campo]
    return compacta
