"""PriceX 2.0 en vivo: la página para conversar con el equipo de agentes sobre el catálogo simulado.

Dos pestañas: Asistente (la conversación) y Tablero (lo que pasa en la página, que se actualiza con cada mensaje).
Se publica gratis en Streamlit Community Cloud (ver despliegue/STREAMLIT.md). La clave de Gemini va en los secretos
de la app, nunca en el código. Sin clave, o si se acaba la cuota del día, la página sigue funcionando sin IA.
Para probarla en tu computador: pip install -r requirements.txt && streamlit run app.py
"""
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from pricex import tablero_vista as vista
from pricex.agente import Asistente
from pricex.catalogo import CatalogoSimulado
from pricex.hoja import conectar as conectar_hoja
from pricex.config import FECHA_HOY
from pricex.multiagente import Conversacion, Equipo, atender_uniendo
from pricex.reglas import MOTIVOS
from pricex.respuesta import FRASES_MOTIVO, nombre_publicacion, texto_calificacion, texto_vendedor
from pricex.sensibles import tapar_datos_sensibles
from pricex.tablero import (comparar_corridas, corridas_de, lectura_corridas, COLUMNAS_CSV, RegistroDeUso, a_csv, evento_de, eventos_de_pruebas, filtrar, lecturas,
                            marcas_del_catalogo, nombre_producto, porcentaje, resumen, usd)
from pricex.texto import fecha_larga, pesos

RAIZ = Path(__file__).resolve().parent
MAX_CARACTERES = 300          # por mensaje
MAX_MENSAJES_SESION = 20      # con IA, por visitante
MAX_MENSAJES_DIA = 300        # con IA, entre todos los visitantes (se puede cambiar en los secretos)
EJEMPLOS = [
    "Samsung Galaxy S26 de 256 GB negro, máximo 4 millones",
    "tele de 55 pulgadas que no pase de 2 palos",
    "freidora de aire de 5 litros que me llegue antes del viernes a Ibagué",
    "un celular bueno y barato",
]
FUENTES = ["Todos los visitantes", "Tu conversación", "Pruebas grabadas"]
NOMBRE_VERSION = {"sin IA": "Sin IA", "v1": "V1: un agente", "v2": "V2: equipo"}

st.set_page_config(page_title="PriceX 2.0 · asistente de compras (demo)", page_icon="🛒", layout="centered")


def md(texto):
    """Texto para st.markdown: el signo $ se escapa, porque dos precios en una línea se leerían como fórmula."""
    return str(texto).replace("$", "\\$")


# ---------------------------------------------------------------- recursos compartidos
@st.cache_resource
def cargar_catalogo():
    return CatalogoSimulado(RAIZ / "datos" / "catalogo_simulado.json")


@st.cache_resource
def marcas_conocidas():
    return marcas_del_catalogo(cargar_catalogo())


@st.cache_resource
def registro_de_uso():
    """Los registros de todos los visitantes. Con los secretos HOJA_DE_USO_URL y HOJA_DE_USO_CUENTA quedan en una hoja
    de Google Sheets y sobreviven cuando la app se duerme; sin ellos, en memoria y en un archivo temporal."""
    ruta = os.environ.get("PRICEX_REGISTRO") or str(Path(tempfile.gettempdir()) / "pricex_eventos.jsonl")
    url, cuenta = secreto("HOJA_DE_USO_URL"), secreto("HOJA_DE_USO_CUENTA")
    if not (url and cuenta):
        return RegistroDeUso(ruta)
    try:
        return RegistroDeUso(ruta, hoja=conectar_hoja(url, cuenta))
    except Exception as error:  # una hoja mal configurada no tumba la página
        registro = RegistroDeUso(ruta)
        registro.problema = (f"No se pudo conectar la hoja de Google Sheets ({type(error).__name__}). Revisa los "
                             "secretos y que la hoja esté compartida con la cuenta de servicio.")
        return registro


@st.cache_resource
def datos_de_pruebas():
    return eventos_de_pruebas(RAIZ, marcas_conocidas())


@st.cache_resource
def uso_del_dia():
    """Contador compartido entre todos los visitantes. Se reinicia cada día y cuando la app se reinicia."""
    return {"dia": None, "mensajes": 0, "cuota_agotada": None}


def secreto(nombre, defecto=None):
    try:
        return st.secrets.get(nombre, defecto)
    except Exception:  # sin archivo de secretos
        return defecto


def hoy_real():
    return datetime.now(timezone.utc).date().isoformat()


@st.cache_resource
def cliente_gemini(clave):
    from google import genai
    return genai.Client(api_key=clave)


@st.cache_data(ttl=24 * 3600, max_entries=3000, show_spinner=False)
def consultar_gemini(_cliente, modelo, instrucciones, mensaje):
    """Una consulta al modelo. Las consultas repetidas (por ejemplo, los mensajes de ejemplo) salen de la caché.
    El guion bajo de _cliente hace que el cliente (y su clave) no forme parte de la llave de la caché."""
    from google.genai import types
    inicio = time.time()
    respuesta = _cliente.models.generate_content(
        model=modelo, contents=mensaje,
        config=types.GenerateContentConfig(system_instruction=instrucciones, response_mime_type="application/json"))
    uso = getattr(respuesta, "usage_metadata", None)
    return {"texto": respuesta.text or "", "segundos": round(time.time() - inicio, 2),
            "tokens_entrada": getattr(uso, "prompt_token_count", None),
            "tokens_salida": (getattr(uso, "candidates_token_count", None) or 0) + (getattr(uso, "thoughts_token_count", None) or 0)}


def crear_llamar(clave, modelo, uso):
    def llamar(instrucciones, mensaje):
        if uso["cuota_agotada"] == hoy_real():
            raise RuntimeError("se acabó la cuota de IA de hoy")
        try:
            return consultar_gemini(cliente_gemini(clave), modelo, instrucciones, mensaje)
        except Exception as error:
            if "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error):
                uso["cuota_agotada"] = hoy_real()
            raise
    return llamar


# ---------------------------------------------------------------- estado de la sesión
estado = st.session_state
if "conversacion" not in estado:
    estado.conversacion = Conversacion()
    estado.historial = []
    estado.mensajes_ia = 0
    estado.sesion_id = uuid.uuid4().hex[:12]  # anónimo: solo sirve para filtrar «Tu conversación»

catalogo = cargar_catalogo()
registro = registro_de_uso()
uso = uso_del_dia()
if uso["dia"] != hoy_real():
    uso.update(dia=hoy_real(), mensajes=0, cuota_agotada=None)
CLAVE = secreto("GEMINI_API_KEY") or secreto("GOOGLE_API_KEY")
MODELO = secreto("MODELO", "gemini-3.5-flash-lite")
LIMITE_DIA = int(secreto("MAX_MENSAJES_DIA", MAX_MENSAJES_DIA))


def modo_disponible():
    """('IA', None) si el equipo de agentes puede atender; ('sin IA', motivo) si no."""
    if not CLAVE:
        return "sin IA", "Esta copia de la página no tiene clave del modelo, así que funciona sin IA."
    if uso["cuota_agotada"] == hoy_real():
        return "sin IA", "Se acabó la cuota gratuita de IA de hoy. La página sigue funcionando sin IA."
    if uso["mensajes"] >= LIMITE_DIA:
        return "sin IA", "Se alcanzó el límite de mensajes con IA de hoy. La página sigue funcionando sin IA."
    if estado.mensajes_ia >= MAX_MENSAJES_SESION:
        return "sin IA", f"Ya usaste los {MAX_MENSAJES_SESION} mensajes con IA de esta visita. Sigue sin IA."
    return "IA", None


def atender(texto):
    modo, _ = modo_disponible()
    if modo == "IA":
        uso["mensajes"] += 1
        estado.mensajes_ia += 1
        equipo = Equipo(catalogo, crear_llamar(CLAVE, MODELO, uso), tolerar_errores=True)
        respuesta = equipo.atender(texto, estado.conversacion)
    else:
        respuesta = atender_uniendo(Asistente(catalogo), estado.conversacion, texto)
    # El tablero guarda solo datos estructurados de la respuesta, nunca el texto que escribió la persona
    registro.agregar(evento_de(respuesta, sesion=estado.sesion_id, marcas=marcas_conocidas()))
    return respuesta


# ---------------------------------------------------------------- cómo se muestra una respuesta
def mostrar_opciones(respuesta):
    decision = respuesta.get("decision") or {}
    for o in decision.get("opciones", []):
        with st.container(border=True):
            st.markdown(md(f"**{o['puesto']}. {nombre_publicacion(o)}**"))
            envio = "envío gratis" if not o.get("costo_envio") else f"{pesos(o['costo_envio'])} de envío incluido"
            llega = f"llega el {fecha_larga(o['llega'])}" if o.get("llega") else "sin fecha de entrega"
            st.markdown(md(f"{pesos(o['total'])} con {envio} · {llega}"))
            detalles = [texto_vendedor(o), texto_calificacion(o)]
            if o.get("cuotas"):
                detalles.append(f"{o['cuotas']} cuotas sin interés")
            if o.get("leido_del_titulo"):
                detalles.append("un dato sale del título de la publicación")
            st.caption(md(" · ".join(detalles) + f" · publicación simulada {o['id']}"))


def mostrar_detalles(respuesta, ver_traza):
    decision = respuesta.get("decision") or {}
    if respuesta.get("pedido_consolidado") and respuesta["pedido_consolidado"] != respuesta["pedido_tapado"]:
        st.caption(md(f"Pedido completo: «{respuesta['pedido_consolidado']}»"))
    if decision.get("descartes"):
        conteo = decision["conteo_descartes"]
        with st.expander(f"Por qué quedaron fuera {len(decision['descartes'])} de {decision['revisadas']} publicaciones"):
            for motivo in MOTIVOS:
                if motivo in conteo:
                    st.markdown(f"- {conteo[motivo]} {FRASES_MOTIVO[motivo][0 if conteo[motivo] == 1 else 1]}")
            for d in decision["descartes"][:12]:
                st.caption(md(f"{nombre_publicacion(d['pub'])}: {d['detalle']}"))
    if ver_traza and respuesta.get("traza"):
        with st.expander("Qué hizo cada agente"):
            for p in respuesta["traza"]:
                quien = p["quien"] + (" (IA)" if p["ia"] else " (código)")
                st.markdown(md(f"**{quien}** · {p['que']} · *{p['resultado']}*"))
                if p["detalle"]:
                    st.caption(md(p["detalle"]))
            segundos = sum(c.get("segundos") or 0 for c in respuesta.get("llamadas", []))
            st.caption(f"{len(respuesta.get('llamadas', []))} consultas al modelo · {segundos:.1f} s de modelo")


def mostrar(mensaje, ver_traza):
    with st.chat_message(mensaje["rol"]):
        if mensaje["rol"] == "user":
            st.markdown(md(mensaje["texto"]))
            return
        r = mensaje["respuesta"]
        st.markdown(md(r["mensaje"]))
        mostrar_opciones(r)
        mostrar_detalles(r, ver_traza)
        if r["modo"] == "multiagente" and r.get("llamadas"):
            st.caption("Atendió: el equipo de agentes con IA")
        elif r["modo"] == "multiagente":
            st.caption("Atendió: la versión sin IA, porque el modelo no respondió")
        else:
            st.caption("Atendió: la versión sin IA")


# ---------------------------------------------------------------- el tablero
def html(contenido):
    st.markdown(contenido, unsafe_allow_html=True)


def filas_para_tabla(eventos):
    """Los registros como filas planas para ver en una tabla: el gemelo accesible de cada gráfica."""
    filas = []
    for e in eventos:
        fila = {c: e.get(c) for c in COLUMNAS_CSV}
        fila["producto"] = nombre_producto(e["producto"]) if e["producto"] else None
        fila["descartes"] = sum(e["descartes"].values())
        filas.append(fila)
    return filas


def mostrar_tablero():
    html(vista.ESTILO)
    st.caption("Se actualiza con cada mensaje que se escribe en la página. Guarda solo datos estructurados "
               "(producto, acción, motivos, tiempos y costo), nunca el texto que escribes.")
    if registro.guarda_en_hoja:
        st.caption("Los mensajes de los visitantes quedan guardados en una hoja de Google Sheets.")
    elif registro.problema:
        st.caption(registro.problema)
    else:
        st.caption("Los mensajes de los visitantes se guardan mientras la página esté despierta.")
    izquierda, derecha = st.columns([3, 2])
    fuente = izquierda.radio("Datos", FUENTES, horizontal=True, key="tablero_fuente")
    if fuente == "Todos los visitantes":
        eventos = registro.eventos()
    elif fuente == "Tu conversación":
        eventos = filtrar(registro.eventos(), sesion=estado.sesion_id)
    else:
        pruebas = datos_de_pruebas()
        versiones = [v for v in NOMBRE_VERSION if any(e["version"] == v for e in pruebas)]
        version = izquierda.radio("Versión", versiones, format_func=NOMBRE_VERSION.get, horizontal=True,
                                  key="tablero_version")
        corridas = corridas_de(filtrar(pruebas, version=version))
        corrida = corridas[-1] if corridas else None
        if len(corridas) > 1:
            corrida = izquierda.radio("Corrida", list(reversed(corridas)), horizontal=True, key="tablero_corrida",
                                      format_func=lambda c: f"Corrida {c}" + (" (la actual)" if c == corridas[-1] else ""))
        eventos = filtrar(pruebas, version=version, corrida=corrida)
        if len(versiones) == 1:
            izquierda.caption("Las versiones con IA aparecen cuando se agreguen los resultados del cuaderno de Colab.")
        filas_corridas = comparar_corridas(pruebas)
        if len({f["corrida"] for f in filas_corridas if f["corrida"]}) > 1:
            html(vista.seccion("¿Qué cambió entre corridas?", lectura_corridas(filas_corridas)))
            html(vista.tabla_corridas(filas_corridas))
    presentes = sorted({e["producto"] for e in eventos if e["producto"]}, key=nombre_producto)
    eleccion = derecha.selectbox("Producto", ["Todos"] + presentes, key="tablero_producto",
                                 format_func=lambda p: p if p == "Todos" else vista.mayuscula(nombre_producto(p)))
    if eleccion != "Todos":
        eventos = filtrar(eventos, producto=eleccion)

    r = resumen(eventos)
    frases = dict(lecturas(r))
    if not r["mensajes"]:
        st.info(frases["Todavía no hay datos"])
        return
    if "Ojo con la muestra" in frases:
        st.info(frases["Ojo con la muestra"])
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Mensajes", f"{r['mensajes']:,}".replace(",", "."),
              help="Mensajes atendidos con este filtro. Cada turno de una conversación cuenta como uno.")
    k2.metric("Con opciones que cumplen todo", f"{porcentaje(r['con_opciones'], r['mensajes'])} %",
              help="Mensajes que terminaron con al menos una opción que cumple todo lo pedido.")
    k3.metric("Preguntó o aclaró", f"{porcentaje(r['preguntar_o_aclarar'], r['mensajes'])} %",
              help="Mensajes en los que faltaba información o se pidió algo que el asistente no hace.")
    k4.metric("Costo por mensaje", usd(r["costo_promedio_usd"]) if r["costo_promedio_usd"] else "Sin IA",
              help="Promedio de los mensajes atendidos con IA, con los precios de Gemini 3.5 Flash-Lite.")

    if r["calidad"] and r["calidad"]["recomendables"]:
        html(vista.seccion("¿Qué tan bien elige?", frases.get("¿Qué tan bien elige?")))
        html(vista.calidad(r["calidad"]))
    a, b = st.columns(2)
    with a:
        html(vista.seccion("¿Dónde se pierde el pedido?", frases.get("¿Dónde se pierde el pedido?")))
        html(vista.embudo(r["embudo"]))
    with b:
        html(vista.seccion("¿Por qué no sirven las publicaciones?", frases.get("¿Por qué no sirven las publicaciones?")))
        html(vista.motivos(r["motivos"], r["descartadas"]))
    a, b = st.columns(2)
    with a:
        html(vista.seccion("¿Qué piden?", frases.get("¿Qué piden?")))
        html(vista.productos(r["productos"]))
    with b:
        html(vista.seccion("¿Qué no encuentran?", frases.get("¿Qué no encuentran?")))
        html(vista.demanda(r["demanda_sin_atender"]))
    html(vista.seccion("¿Qué hizo el equipo de agentes?", frases.get("¿Qué hizo el equipo de agentes?")))
    html(vista.agentes(r["agentes"]))
    html(vista.seccion("¿Cuánto cuesta y cuánto vale?", frases.get("¿Cuánto cuesta y cuánto vale?")))
    with st.expander("Ver los datos en una tabla y descargarlos"):
        st.dataframe(filas_para_tabla(eventos), hide_index=True)
        st.download_button("Descargar CSV (para Excel o Power BI)", a_csv(eventos), file_name="pricex_tablero.csv",
                           mime="text/csv")


# ---------------------------------------------------------------- la página
st.title("PriceX 2.0")
st.markdown("Escribe en una frase lo que quieres comprar. Un equipo de agentes de IA entiende tu pedido, unas reglas "
            "fijas eligen las 3 mejores opciones y tú decides.")
st.caption(f"Proyecto de portafolio. Catálogo simulado del {fecha_larga(FECHA_HOY)} de {FECHA_HOY.year}: precios, "
           "vendedores y entregas son inventados. No está afiliado a Mercado Libre. No escribas datos personales: los "
           "números de tarjeta, correos y teléfonos se tapan antes de llegar al modelo, y en el plan gratuito Google "
           "puede usar los mensajes para mejorar sus productos.")

with st.sidebar:
    st.subheader("Prueba con")
    for i, ejemplo in enumerate(EJEMPLOS):
        if st.button(ejemplo, key=f"ejemplo_{i}"):  # un ejemplo empieza una conversación nueva
            estado.conversacion = Conversacion()
            estado.historial = []
            estado.pendiente = ejemplo
    st.caption("Después de la respuesta, prueba cambiar algo: «¿y en azul?», «mejor de 128», «que llegue mañana».")
    ver_traza = st.toggle("Mostrar qué hizo cada agente", value=True)
    if st.button("Empezar una conversación nueva"):
        estado.conversacion = Conversacion()
        estado.historial = []
    modo, motivo = modo_disponible()
    st.divider()
    if modo == "IA":
        st.caption(f"Con IA: te quedan {MAX_MENSAJES_SESION - estado.mensajes_ia} mensajes en esta visita.")
    else:
        st.caption(motivo)
    if secreto("REPO_URL"):
        st.markdown(f"[Código y evaluación en GitHub]({secreto('REPO_URL')})")

pestana_asistente, pestana_tablero = st.tabs(["Asistente", "Tablero"])
texto = st.chat_input("Ej.: audífonos sony wh-1000xm5 que lleguen mañana a Bogotá", max_chars=MAX_CARACTERES)
texto = texto or estado.pop("pendiente", None)

with pestana_asistente:
    for mensaje in estado.historial:
        mostrar(mensaje, ver_traza)
    if texto:
        texto = texto.strip()[:MAX_CARACTERES]
        usuario = {"rol": "user", "texto": tapar_datos_sensibles(texto)[0]}  # en pantalla también queda tapado
        estado.historial.append(usuario)
        mostrar(usuario, ver_traza)
        with st.spinner("El equipo está revisando el catálogo…"):
            respuesta = atender(texto)
        asistente = {"rol": "assistant", "respuesta": respuesta}
        estado.historial.append(asistente)
        mostrar(asistente, ver_traza)

with pestana_tablero:  # va después de atender el mensaje, para que el tablero ya lo incluya
    mostrar_tablero()

with st.sidebar:
    vivos = registro.eventos()
    if vivos:
        con_opciones = sum(e["situacion"] == "recomendar" for e in vivos)
        st.caption(f"En la página: {len(vivos)} mensajes, {porcentaje(con_opciones, len(vivos))} % con opciones que "
                   "cumplen todo. Míralo en la pestaña Tablero.")
