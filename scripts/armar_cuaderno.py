"""Arma agente/pricex2_agente.ipynb a partir de las celdas de abajo.

El cuaderno corre las tres versiones en una sola pasada (sin IA, v1 con un agente y v2 con el equipo de agentes)
sobre los pedidos, las variantes y las conversaciones, y las compara.
Uso: python3 scripts/armar_cuaderno.py
"""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

CELDAS = []


def md(texto):
    CELDAS.append(("markdown", texto.strip("\n")))


def code(texto):
    CELDAS.append(("code", texto.strip("\n")))


md('''
# PriceX 2.0: del asistente con IA al equipo de agentes

**Cuaderno de evaluación · Catálogo simulado con la forma de la API de Mercado Libre · Proyecto de portafolio, no afiliado a Mercado Libre**

Le escribes en una frase lo que quieres comprar y el asistente te muestra las 3 mejores opciones, con el porqué. La compra la haces tú. Este cuaderno corre **tres versiones** del asistente con los mismos datos y las compara:

| Versión | Quién entiende el pedido | Quién elige |
|---|---|---|
| **Sin IA** | Patrones de texto escritos a mano (la línea base) | Las reglas |
| **V1: un agente** | Un modelo de IA (Gemini) interpreta y otro paso del mismo modelo redacta | Las reglas |
| **V2: equipo de agentes** | Seis agentes con tareas fijas: coordinador, intérprete, revisor, buscador, lector de atributos y redactor | Las reglas |

En las tres versiones **la IA entiende, las reglas eligen y la persona decide.** Ningún agente elige productos ni cambia el orden de las opciones.

**Cómo usarlo:** ejecuta las celdas en orden con `Shift + Enter`, o todas a la vez con *Entorno de ejecución > Ejecutar todas*. La primera vez, Google te pedirá permiso para conectar tu Drive.

**Palabras que vas a ver**

- **Modelo de IA:** el programa que entiende y escribe texto. Aquí se usa Gemini, de Google.
- **Agente:** un modelo de IA con una sola tarea y sus propias instrucciones. Por ejemplo, el *revisor* solo revisa lo que entendió el *intérprete*.
- **Equipo multiagente:** varios agentes que se reparten el trabajo. Aquí el orden lo pone el código (el «director»): cada agente trabaja solo cuando le toca y el código revisa lo que propone antes de usarlo.
- **Evidencia:** el pedazo exacto del texto que respalda lo que propone un agente. Si el agente dice «presupuesto: 2 millones», la evidencia es «2 palos». El código comprueba que esa evidencia esté, letra por letra, en el pedido.
- **Traza:** la lista de lo que hizo cada agente en una respuesta: qué propuso, si se usó y por qué.
- **Clave de API:** una contraseña que identifica tu cuenta ante el servicio del modelo. Nunca se escribe dentro del código.
- **JSON:** un formato de texto ordenado para intercambiar datos: `{"producto": "televisor", "pulgadas": 55}`.
- **Token:** un pedazo de palabra. Los modelos cobran por tokens leídos (entrada) y escritos (salida).
''')

md('''
## 1. Preparar el entorno

Esta celda carga las librerías, conecta tu Google Drive y busca la carpeta `pricex-2`. El código del asistente vive en la carpeta `pricex` del proyecto; el cuaderno lo usa y muestra cada paso. Todo lo que produce se guarda en `resultados/gemini`.
''')

code('''
import hashlib, json, os, statistics, subprocess, sys, time, zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    import google.colab  # solo existe dentro de Google Colab
    EN_COLAB = True
except ImportError:
    EN_COLAB = False

if EN_COLAB:
    from google.colab import drive
    drive.mount("/content/drive")


def buscar_proyecto():
    """Encuentra la carpeta del proyecto: la que tiene datos/catalogo_simulado.json."""
    marca = Path("datos") / "catalogo_simulado.json"
    if EN_COLAB:
        base = Path("/content/drive/MyDrive")
        candidatos = [c for c in [base / "pricex-2", base / "pricex-2" / "pricex-2"] if (c / marca).exists()]
        if not candidatos:  # búsqueda más amplia, por si la carpeta quedó dentro de otra
            for patron in ["*/datos/catalogo_simulado.json", "*/*/datos/catalogo_simulado.json",
                           "*/*/*/datos/catalogo_simulado.json"]:
                candidatos += [archivo.parent.parent for archivo in base.glob(patron)]
    else:
        candidatos = [c for c in [Path.cwd(), Path.cwd().parent] if (c / marca).exists()]
    candidatos.sort(key=lambda c: (not c.name.startswith("pricex"), len(str(c))))
    return candidatos[0] if candidatos else None


CARPETA = buscar_proyecto()
if CARPETA is None:
    raise FileNotFoundError(
        "No encontré la carpeta del proyecto. Sube la carpeta pricex-2 a tu Google Drive, dentro de "
        "'Mi unidad', y vuelve a ejecutar esta celda.")
sys.path.insert(0, str(CARPETA))
SALIDA = CARPETA / "resultados" / "gemini"
SALIDA.mkdir(parents=True, exist_ok=True)

from pricex.agente import Asistente, compactar
from pricex.catalogo import CatalogoSimulado
from pricex.config import FECHA_HOY
from pricex.evaluar import (CAMPOS_EVALUADOS, clave_para, evaluar_conversacion, evaluar_respuesta,
                            precision_por_campo, resumen)
from pricex.interpretar import instrucciones_interprete
from pricex.multiagente import (Conversacion, Equipo, agente_de, atender_uniendo, instrucciones_buscador,
                                instrucciones_coordinador, instrucciones_lector, instrucciones_revisor)
from pricex.respuesta import instrucciones_redactor, nombre_publicacion
from pricex.sensibles import tapar_datos_sensibles

print("Proyecto encontrado en:", CARPETA)
''')

md('''
## 2. Configuración

Normalmente no hay que cambiar nada.

- `PROVEEDOR`: `"gemini"` usa tu clave gratuita de Google AI Studio (recomendado). `"colab"` usa los modelos que Colab ofrece sin clave; sirve si la clave te da problemas.
- `MODELO`: el mismo del agente de quejas. Si no está disponible con tu clave, la sección 6 elige otro Flash-Lite y te avisa.
- `PAUSA_SEGUNDOS`: espera entre consultas, para no pasar el límite por minuto del plan gratuito.
- `VERSION_CONSULTAS`: si cambias alguna instrucción de un agente, súbelo a `2` para que todo se vuelva a consultar.
- `REDACTAR_CON_IA`: el redactor escribe los mensajes de los pedidos y de las conversaciones. En las variantes solo se mide la interpretación, para ahorrar consultas.
- Los precios son los de la página de precios de la API de Gemini en noviembre de 2026, en dólares por millón de tokens. Solo sirven para estimar el costo; con la clave gratuita no se paga nada.
''')

code('''
PROVEEDOR = "gemini"              # "gemini" o "colab"
MODELO = "gemini-3.5-flash-lite"
MODELO_COLAB = None               # solo para PROVEEDOR = "colab"; None usa el que Colab trae por defecto
PAUSA_SEGUNDOS = 4
VERSION_CONSULTAS = 1
REDACTAR_CON_IA = True
REDACTAR_VARIANTES = False
PRECIO_ENTRADA_USD = 0.30         # por millón de tokens de entrada
PRECIO_SALIDA_USD = 2.50          # por millón de tokens de salida (incluye los de "pensar")

print(f"El «hoy» de la simulación es {FECHA_HOY:%d/%m/%Y}: el día en que se congeló el catálogo.")
''')

md('''
## 3. Cargar los datos

Todo es simulado (lo producen `datos/generar_datos.py` y `datos/generar_conversaciones.py`):

- `catalogo_simulado.json`: 205 publicaciones con la forma de una búsqueda en la API de Mercado Libre. Precios, vendedores, calificaciones y entregas son inventados.
- `pedidos.csv`: los 30 pedidos de prueba: 10 de modelo exacto, 10 por presupuesto o características, 5 con trampa, 3 ambiguos y 2 fuera de alcance.
- `variantes.csv`: los mismos 30 pedidos dichos de otra forma. Se escribieron después de congelar la versión sin IA, para medirla con frases que no vio.
- `conversaciones.json`: 10 conversaciones de dos mensajes («Samsung S26 de 256 negro» y luego «¿y en azul?»). Prueban la memoria: lo que la versión 1 no tiene.
- `clave_respuestas.json`: la interpretación correcta y la respuesta esperada de cada pedido. **El asistente nunca la ve**; solo se usa para medirlo.
''')

code('''
catalogo = CatalogoSimulado(CARPETA / "datos" / "catalogo_simulado.json")
pedidos = pd.read_csv(CARPETA / "datos" / "pedidos.csv", encoding="utf-8-sig")
variantes = pd.read_csv(CARPETA / "datos" / "variantes.csv", encoding="utf-8-sig")
clave = json.loads((CARPETA / "datos" / "clave_respuestas.json").read_text(encoding="utf-8"))["pedidos"]
conversaciones = json.loads((CARPETA / "datos" / "conversaciones.json").read_text(encoding="utf-8"))["conversaciones"]

print(f"{len(catalogo.publicaciones)} publicaciones, congeladas el {catalogo.congelado_el}")
print(f"{len(pedidos)} pedidos, {len(variantes)} variantes y {len(conversaciones)} conversaciones")
display(pedidos.tipo.value_counts().rename("pedidos").to_frame())
display(pd.DataFrame([{"conversación": c["id"], "qué prueba": c["que_prueba"],
                       "mensaje 1": c["turnos"][0]["texto"], "mensaje 2": c["turnos"][1]["texto"]}
                      for c in conversaciones]))
''')

md('''
## 4. Tapar los datos sensibles

Para buscar un producto no hace falta saber la tarjeta, el correo ni el teléfono de nadie. Por eso se cambian por etiquetas como `[TARJETA]` antes de que el pedido salga hacia cualquier agente.

- **Tarjetas:** se reconocen con la *prueba de Luhn*, la fórmula con la que los números de tarjeta reales detectan errores de digitación. Así no se tapan precios ni referencias.
- El pedido 30 y la conversación C9 traen `4111 1111 1111 1111`, un número de prueba muy conocido que no es una tarjeta real.
''')

code('''
antes = pedidos.set_index("n").texto[30]
despues, tapados = tapar_datos_sensibles(antes)
print("Antes:  ", antes)
print("Después:", despues)
print("Tapado: ", tapados)

todos = list(pedidos.texto) + list(variantes.texto) + [t["texto"] for c in conversaciones for t in c["turnos"]]
con_datos = sum(bool(tapar_datos_sensibles(t)[1]) for t in todos)
print(f"\\nDe {len(todos)} textos, {con_datos} traían datos sensibles y quedaron tapados.")
''')

md('''
## 5. El equipo: qué hace cada agente y qué revisa el código

| Agente | Cuándo trabaja | Qué propone | Qué revisa el código antes de usarlo |
|---|---|---|---|
| **Coordinador** | Cuando ya hay un pedido en curso | El pedido completo en una frase («S26 de 256 azul, máximo 4 millones») | Que no traiga cifras que la persona no escribió. Si falla, se pegan los dos mensajes |
| **Intérprete** | Siempre (es el de la versión 1) | Los datos del pedido en JSON | Producto de la lista, cifras válidas, fecha futura y reglas de acción |
| **Revisor** | Cuando se va a recomendar | Correcciones a cifras, fecha, ciudad, color, edición o estado | Que cada corrección cite el pedido letra por letra y que no cambie un dato que ya tenía respaldo |
| **Buscador** | Si quedaron menos de 3 opciones y la búsqueda trajo poco | Hasta 2 búsquedas nuevas | Formato: palabras cortas, sin enlaces. Después las reglas revisan cada publicación |
| **Lector de atributos** | Si una publicación quedó fuera solo porque su ficha no trae un dato pedido | El dato, leído del título | Que esté escrito en el título, sin condiciones («ampliable a») y sin ambigüedad |
| **Redactor** | Cuando hay opciones para mostrar (es el de la versión 1) | El mensaje para la persona | Cada cifra contra los datos. Si falla, sale la plantilla |

Dos detalles importantes:

- **El director es código.** El orden de los pasos y cuándo trabaja cada agente están escritos en `pricex/multiagente.py`. Un agente no puede llamar a otro ni saltarse un paso.
- **Solo el lector ve texto de vendedores,** y solo títulos de publicaciones que ya pasaron el filtro de instrucciones escondidas. Lo que devuelve tiene que estar escrito en ese título: una orden escondida no puede convertirse en un dato.

Estas son las instrucciones de cada agente. Las del intérprete y el redactor son las mismas de la versión 1.
''')

code('''
for nombre, texto in [("COORDINADOR", instrucciones_coordinador()), ("INTÉRPRETE", instrucciones_interprete()),
                      ("REVISOR", instrucciones_revisor()), ("BUSCADOR", instrucciones_buscador()),
                      ("LECTOR DE ATRIBUTOS", instrucciones_lector()), ("REDACTOR", instrucciones_redactor())]:
    print("=" * 30, nombre, "=" * 30)
    print(texto, "\\n")
''')

md('''
## 6. Conectar el modelo

Con `PROVEEDOR = "gemini"` necesitas una clave gratuita. Si ya la creaste para el agente de quejas, sirve la misma:

1. Entra a [aistudio.google.com](https://aistudio.google.com) con tu cuenta de Google y acepta las condiciones.
2. Haz clic en **Get API key** y luego en **Create API key**. Copia la clave.
3. En este cuaderno, en la barra de la izquierda, haz clic en el ícono de la llave (**Secretos**).
4. Haz clic en **Agregar nuevo secreto**. En *Nombre* escribe `GEMINI_API_KEY`, en *Valor* pega la clave y activa *Acceso al cuaderno*.

La clave queda guardada en tu cuenta de Colab, no en el cuaderno: por eso no se publica cuando subas el proyecto a GitHub.

**Cada respuesta del modelo se guarda** en `resultados/gemini/llamadas.jsonl`. Si se corta la conexión o se acaba la cuota del día, vuelve a ejecutar: lo que ya se consultó no se vuelve a pedir. En total son unas 200 consultas. El plan gratuito tiene un límite de consultas por día que puedes ver en AI Studio, en la página de límites (*rate limit*); si se acaba, sigue al día siguiente.

La celda termina con una consulta de prueba. Si responde `listo`, la conexión funciona.
''')

code('''
# CONEXIÓN CON EL MODELO
if PROVEEDOR == "gemini":
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "google-genai"], check=True)
        from google import genai
        from google.genai import types

    NOMBRES_CLAVE = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
    clave_api = next((os.environ[n] for n in NOMBRES_CLAVE if os.environ.get(n)), None)
    avisos_clave = []
    if EN_COLAB and not clave_api:
        from google.colab import userdata
        for nombre in NOMBRES_CLAVE:
            try:
                clave_api = userdata.get(nombre)
            except Exception as error:
                avisos_clave.append(f"{nombre}: {type(error).__name__}")
            if clave_api:
                break
    if not clave_api:
        raise RuntimeError(
            "Falta la clave. Créala en aistudio.google.com y guárdala en Secretos (ícono de la llave, a la "
            "izquierda) con el nombre GEMINI_API_KEY y el acceso al cuaderno activado. Luego repite esta celda. "
            + ("Detalle: " + "; ".join(avisos_clave) if avisos_clave else ""))
    cliente = genai.Client(api_key=clave_api)
    try:
        disponibles = sorted(m.name.replace("models/", "") for m in cliente.models.list())
        flash = [n for n in disponibles if n.startswith("gemini") and "flash" in n]
        print("Modelos Gemini Flash disponibles con tu clave:", ", ".join(flash))
        if MODELO not in disponibles:
            descartar = ("preview", "exp", "image", "tts", "audio", "live", "transcribe", "translate")
            estables = [n for n in flash if not any(p in n for p in descartar)]
            candidatos = [n for n in estables if "lite" in n] or estables
            if candidatos:
                print(f"\\nAtención: '{MODELO}' no está disponible con tu clave. Uso '{candidatos[-1]}'.")
                MODELO = candidatos[-1]
            else:
                print(f"\\nAtención: '{MODELO}' no aparece en la lista. Cambia MODELO en la sección 2 por uno de esos.")
    except Exception as error:
        print("No pude listar los modelos:", error)
elif PROVEEDOR == "colab":
    from google.colab import ai
    print("Modelos que ofrece Colab:", ai.list_models())
else:
    raise ValueError('PROVEEDOR debe ser "gemini" o "colab".')


ERRORES_SIN_REINTENTO = {
    400: "Google rechazó la consulta. Si el detalle dice API_KEY_INVALID, la clave quedó mal copiada: "
         "créala de nuevo y actualiza el secreto.",
    401: "La clave no es válida. Créala de nuevo en aistudio.google.com y actualiza el secreto.",
    403: "La clave no tiene permiso para usar este modelo. Revisa la clave o cambia MODELO en la sección 2.",
    404: "El modelo no existe o no está disponible para tu clave. Cambia MODELO en la sección 2 "
         "por uno de la lista que imprimió esta celda.",
}


def llamar_modelo(instrucciones, mensaje, intentos=4):
    """Una consulta al modelo, con reintentos. Devuelve el texto y los tokens que usó."""
    espera = 30
    for intento in range(1, intentos + 1):
        try:
            if PROVEEDOR == "gemini":
                # Sin "temperature": los modelos Gemini recientes la ignoran y los futuros la rechazarán.
                respuesta = cliente.models.generate_content(
                    model=MODELO,
                    contents=mensaje,
                    config=types.GenerateContentConfig(system_instruction=instrucciones,
                                                       response_mime_type="application/json"),
                )
                uso = getattr(respuesta, "usage_metadata", None)
                salida = (getattr(uso, "candidates_token_count", None) or 0) + (getattr(uso, "thoughts_token_count", None) or 0)
                return {"texto": respuesta.text or "", "tokens_entrada": getattr(uso, "prompt_token_count", None),
                        "tokens_salida": salida or None}
            prompt = instrucciones + "\\n\\n" + mensaje
            texto = ai.generate_text(prompt, model_name=MODELO_COLAB) if MODELO_COLAB else ai.generate_text(prompt)
            return {"texto": texto, "tokens_entrada": None, "tokens_salida": None}
        except Exception as error:
            detalle = str(error)
            codigo = getattr(error, "code", None)
            if codigo in ERRORES_SIN_REINTENTO:
                raise RuntimeError(ERRORES_SIN_REINTENTO[codigo] + " Detalle técnico: " + detalle[:300]) from error
            limite_diario = "PerDay" in detalle or "per day" in detalle.lower()
            if limite_diario or intento == intentos:
                raise RuntimeError(
                    "El modelo no respondió. "
                    + ("Se acabó la cuota gratuita de hoy para este modelo. " if limite_diario else "")
                    + "El avance quedó guardado: vuelve a ejecutar la celda más tarde y seguirá donde iba. "
                    + "Detalle técnico: " + detalle[:300]) from error
            print(f"   Error del servicio (intento {intento} de {intentos}). Espero {espera} segundos y repito.")
            time.sleep(espera)
            espera *= 2


LLAMADAS = SALIDA / "llamadas.jsonl"
GUARDADAS = {}
if LLAMADAS.exists():
    for linea in LLAMADAS.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            registro = json.loads(linea)
            GUARDADAS[registro["clave"]] = registro


def llamar(instrucciones, mensaje):
    """Consulta el modelo, o devuelve la respuesta guardada si esa misma consulta ya se hizo."""
    modelo = MODELO if PROVEEDOR == "gemini" else (MODELO_COLAB or "colab")
    huella = hashlib.sha256("\\n".join([modelo, str(VERSION_CONSULTAS), instrucciones, mensaje]).encode()).hexdigest()
    if huella in GUARDADAS:
        return GUARDADAS[huella]
    inicio = time.time()
    salida = llamar_modelo(instrucciones, mensaje)
    registro = {"clave": huella, **salida, "segundos": round(time.time() - inicio, 2), "modelo": modelo,
                "version_consultas": VERSION_CONSULTAS, "fecha_hora": datetime.now().isoformat(timespec="seconds"),
                "agente": agente_de(instrucciones)}
    with open(LLAMADAS, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\\n")
    GUARDADAS[huella] = registro
    time.sleep(PAUSA_SEGUNDOS)
    return registro


print(f"Respuestas ya guardadas: {len(GUARDADAS)}")
prueba = llamar_modelo("Responde solo con JSON.", 'Devuelve exactamente este objeto: {"estado": "listo"}')
print("Respuesta de prueba:", prueba["texto"].strip()[:200])
''')

md('''
## 7. Versión 1: un agente atiende los 30 pedidos

Cada pedido pasa por el recorrido de la versión 1: se tapan los datos sensibles, el modelo interpreta, el código revisa esa interpretación, las reglas buscan y eligen, y el modelo redacta el mensaje. Aquí también corre la versión sin IA, que no consulta ningún modelo.

Son unas 55 consultas, de 5 a 8 minutos.
''')

code('''
asistente_v1 = Asistente(catalogo, llamar=llamar, redactar_con_ia=REDACTAR_CON_IA)
asistente_v1_variantes = Asistente(catalogo, llamar=llamar, redactar_con_ia=REDACTAR_VARIANTES)
asistente_sin_ia = Asistente(catalogo)
respuestas = {}


def atender_todos(asistente, tabla, avisar=False):
    resultado = {}
    for fila in tabla.itertuples():
        resultado[int(fila.n)] = asistente.atender(fila.texto)
        if avisar:
            r = resultado[int(fila.n)]
            print(f"  #{fila.n:>2} {r['accion']:<10} {fila.texto[:70]}")
    return resultado


print("Versión 1, los 30 pedidos:")
respuestas[("v1", "pedidos")] = atender_todos(asistente_v1, pedidos, avisar=True)
respuestas[("sin IA", "pedidos")] = atender_todos(asistente_sin_ia, pedidos)

vista = []
for n, r in respuestas[("v1", "pedidos")].items():
    i = r["interpretacion"]
    vista.append({"n": n, "pedido": r["pedido"][:45], "acción": r["accion"], "producto": i["producto"],
                  "marca": i["marca"], "modelo": i["modelo"], "presupuesto": i["presupuesto_max"],
                  "llegar a más tardar": i["fecha_limite"],
                  "mensaje": (r.get("meta_redaccion") or {}).get("usado", "-")})
display(pd.DataFrame(vista))
''')

md('''
## 8. Así deciden las reglas (en las tres versiones)

Este es el corazón del asistente y no usa IA. Para cada publicación que devuelve la búsqueda, las reglas preguntan en orden:

| N° | Regla | Si no cumple |
|---|---|---|
| 0 | ¿Trae instrucciones escondidas para el asistente? | Fuera, y se reporta |
| 1 | ¿Es el producto, la marca, el modelo, la capacidad y el color que se pidió? El color solo cuenta si se pidió | Fuera |
| 2 | ¿Está en el estado pedido? Si no dicen nada, nuevo | Fuera |
| 3 | ¿El vendedor tiene buena reputación y al menos 50 ventas? | Fuera |
| 4 | Si se pidió una fecha, ¿llega a tiempo a la ciudad? | Fuera |
| 5 | ¿Cabe en el presupuesto, con el envío? | Fuera. Si nada cabe, se muestra la más cercana y se avisa |

Entre las que quedan:

- **Si se pidió un modelo exacto,** gana el menor precio total (precio más envío). Si otra cuesta menos de 3 % más y es tienda oficial o llega antes, gana esa.
- **Si el pedido es abierto** («un portátil con 16 de RAM»), primero la calificación de los compradores (solo cuenta con 30 opiniones o más). Una diferencia de 0,2 estrellas o menos cuenta como empate, y entre las empatadas gana el menor precio total.
- Las cuotas sin interés no cambian el precio: solo se mencionan.

Ejemplo completo con el pedido 1, en la versión 1:
''')

code('''
r = respuestas[("v1", "pedidos")][1]
print("Pedido:", r["pedido"])
print("Lo que entendió el modelo:", {k: v for k, v in r["interpretacion"].items() if v not in (None, "")})
if r["decision"]:
    d = r["decision"]
    print(f"Búsqueda: «{r['consulta']}» → {d['revisadas']} publicaciones; {d['validas']} cumplen todo.\\n")
    display(pd.DataFrame([{"publicación": x["id"], "título": x["titulo"][:55], "motivo": x["motivo"],
                           "detalle": x["detalle"]} for x in d["descartes"]]).head(15))
    display(pd.DataFrame([{"puesto": o["puesto"], "opción": nombre_publicacion(o), "precio total": o["total"],
                           "llega": o["llega"], "tienda oficial": o["tienda_oficial"]} for o in d["opciones"]]))
print("\\nMensaje para la persona:\\n" + r["mensaje"])
''')

md('''
## 9. Versión 2: el equipo atiende los mismos 30 pedidos

El intérprete y el redactor son los de la versión 1. Cuando el equipo les hace exactamente la misma consulta, se reutiliza la respuesta guardada: así, **la diferencia entre v1 y v2 sale solo de los agentes nuevos** y no del azar del modelo.

Aquí se ve la traza de dos pedidos: el 9, donde una publicación no trae la capacidad en su ficha pero sí en el título, y el 27, donde ninguna opción cumple todo.

Son unas 30 consultas nuevas.
''')

code('''
equipo = Equipo(catalogo, llamar=llamar, redactar_con_ia=REDACTAR_CON_IA)
equipo_variantes = Equipo(catalogo, llamar=llamar, redactar_con_ia=REDACTAR_VARIANTES)


def atender_equipo(equipo, tabla, avisar=False):
    resultado = {}
    for fila in tabla.itertuples():
        resultado[int(fila.n)] = r = equipo.atender(fila.texto)
        if avisar:
            agentes = ", ".join(sorted({c["agente"] for c in r["llamadas"]}))
            print(f"  #{fila.n:>2} {r['accion']:<10} {fila.texto[:55]:<55} · {agentes}")
    return resultado


def mostrar_traza(r):
    print(f"Pedido: {r['pedido_tapado']}")
    if r.get("pedido_consolidado") and r["pedido_consolidado"] != r["pedido_tapado"]:
        print(f"Pedido completo: {r['pedido_consolidado']}")
    display(pd.DataFrame([{"quién": p["quien"], "¿IA?": "sí" if p["ia"] else "no", "qué hizo": p["que"],
                           "resultado": p["resultado"], "detalle": p["detalle"]} for p in r["traza"]]))
    print("Mensaje:", r["mensaje"], "\\n")


print("Versión 2, los 30 pedidos:")
respuestas[("v2", "pedidos")] = atender_equipo(equipo, pedidos, avisar=True)
for n in (9, 27):
    mostrar_traza(respuestas[("v2", "pedidos")][n])
''')

md('''
## 10. Las mismas necesidades, dichas de otra forma

La versión sin IA se escribió mirando los 30 pedidos, así que con ellos acierta casi todo: es un examen que ya conocía. Para medir de verdad, cada pedido tiene una **variante**: la misma necesidad con otras palabras («la play 5 slim», «pantalla de 27», «de 150 mil para abajo»). Las variantes se escribieron después de congelar la versión sin IA; su huella está en `resultados/sin_ia/linea_base_congelada.txt`.

Aquí solo se mide la interpretación (los mensajes salen de la plantilla): unas 60 consultas entre v1 y v2.
''')

code('''
print("Versión 1, las 30 variantes:")
respuestas[("v1", "variantes")] = atender_todos(asistente_v1_variantes, variantes, avisar=True)
print("\\nVersión 2, las 30 variantes:")
respuestas[("v2", "variantes")] = atender_equipo(equipo_variantes, variantes, avisar=True)
respuestas[("sin IA", "variantes")] = atender_todos(asistente_sin_ia, variantes)
''')

md('''
## 11. Conversaciones: la memoria

En una conversación real, el segundo mensaje casi nunca trae todo: «¿y en azul?», «mejor de 256», «que llegue mañana». Para que la comparación sea justa, la versión sin IA y la v1 reciben la memoria más simple que existe: **el pedido anterior y el mensaje nuevo, pegados.** La v2 tiene al coordinador, que escribe el pedido completo con el cambio. Si el coordinador propone algo que no pasa la revisión, la v2 también pega los textos.

Se mide la acción de cada turno y, en el último, lo mismo que en un pedido: si entendió, si la mejor opción quedó de primera y si hubo error grave. La mejor opción esperada se calculó con las reglas sobre **todo el catálogo**, como si la búsqueda fuera perfecta.

Unas 60 consultas.
''')

code('''
def conversar(atender, conversacion_esperada):
    conversacion = Conversacion()
    return [atender(conversacion, t["texto"]) for t in conversacion_esperada["turnos"]]


VERSIONES_CONVERSACION = {
    "sin IA": lambda conv, texto: atender_uniendo(asistente_sin_ia, conv, texto),
    "v1": lambda conv, texto: atender_uniendo(asistente_v1, conv, texto),
    "v2": lambda conv, texto: equipo.atender(texto, conv),
}
for version, atender in VERSIONES_CONVERSACION.items():
    respuestas[(version, "conversaciones")] = {c["id"]: conversar(atender, c) for c in conversaciones}
    print(f"{version}: listo")

for id_conv in ("C2", "C1"):
    print(f"\\n===== Conversación {id_conv}, segundo mensaje, versión 2 =====")
    mostrar_traza(respuestas[("v2", "conversaciones")][id_conv][-1])
''')

md('''
## 12. Las tres versiones, frente a frente

Cada respuesta se compara con la clave en tres niveles:

1. **Qué hizo:** recomendar, preguntar o aclarar.
2. **Qué entendió:** campo por campo (producto, marca, modelo, capacidad, presupuesto, fecha, ciudad…).
3. **Qué recomendó:** si la mejor opción quedó de primera, si quedó entre las 3 que se muestran y si la primera opción incumple algo de lo pedido. Esto último es el **error grave**: recomendar un 50 pulgadas a quien pidió 55, o un celular nuevo a quien pidió reacondicionado.

En el pedido 9 la respuesta esperada cambia entre versiones: la v2 puede leer en el título una capacidad que la ficha no trae, y con ese dato la mejor opción es otra (está en la clave como `"v2"`).
''')

code('''
VERSIONES = ["sin IA", "v1", "v2"]
CONJUNTOS = ["pedidos", "variantes", "conversaciones"]
FILAS, RESUMENES = {}, {}
for (version, conjunto), rs in respuestas.items():
    if conjunto == "conversaciones":
        FILAS[(version, conjunto)] = [evaluar_conversacion(c, rs[c["id"]]) for c in conversaciones]
    else:
        FILAS[(version, conjunto)] = [evaluar_respuesta(n, r, clave_para(clave[str(n)], version), catalogo)
                                      for n, r in rs.items()]
    RESUMENES[(version, conjunto)] = resumen(FILAS[(version, conjunto)])

METRICAS = [
    ("Hizo lo que debía (recomendar, preguntar o aclarar)", "accion_correcta", "pedidos"),
    ("Entendió el pedido sin ningún error", "interpretacion_perfecta", "recomendables"),
    ("Campos bien entendidos (%)", "campos_correctos_pct", None),
    ("Mejor opción en el primer puesto", "top1", "recomendables"),
    ("Mejor opción entre las 3 mostradas", "top3", "recomendables"),
    ("Errores graves: la primera opción incumple lo pedido", "graves", None),
    ("Recomendó cuando debía preguntar o aclarar", "recomendo_sin_deber", "debian_preguntar_o_aclarar"),
    ("Tarjetas que llegaron al modelo", "tarjetas_expuestas", None),
]
METRICAS_CONVERSACION = [("Acción correcta en los dos mensajes", "acciones_ok_en_todos_los_turnos", "pedidos")] + METRICAS[1:]


def celda(r, clave_metrica, total):
    return f"{r[clave_metrica]} de {r[total]}" if total else r[clave_metrica]


TABLAS = {}
for conjunto in CONJUNTOS:
    metricas = METRICAS_CONVERSACION if conjunto == "conversaciones" else METRICAS
    TABLAS[conjunto] = pd.DataFrame({nombre: {v: celda(RESUMENES[(v, conjunto)], k, t) for v in VERSIONES}
                                     for nombre, k, t in metricas}).T
    print(f"\\n{conjunto.upper()}")
    display(TABLAS[conjunto])

por_campo = pd.DataFrame({f"{v}, {c}": precision_por_campo(FILAS[(v, c)], respuestas[(v, c)], clave)
                          for c in ("pedidos", "variantes") for v in VERSIONES})
print("\\nCampos bien entendidos, en % de los 25 pedidos para recomendar:")
display(por_campo)
''')

md('''
## 13. Qué hizo cada agente

Cuántas veces trabajó cada agente y qué pasó con lo que propuso: **usado** (pasó la revisión y cambió algo), **sin cambios** (revisó y no hizo falta cambiar), **rechazado** (el código no lo aceptó) o **falló** (no respondió). Abajo, el detalle de cada corrección y cada lectura aceptada.
''')

code('''
todas_v2 = (list(respuestas[("v2", "pedidos")].values()) + list(respuestas[("v2", "variantes")].values())
            + [r for rs in respuestas[("v2", "conversaciones")].values() for r in rs])
actividad = {}
for r in todas_v2:
    for c in r["llamadas"]:
        actividad.setdefault(c["agente"], {"consultas": 0, "usado": 0, "sin cambios": 0, "rechazado": 0, "falló": 0})
        actividad[c["agente"]]["consultas"] += 1
    for p in r["traza"]:
        if p["ia"]:
            actividad.setdefault(p["quien"], {"consultas": 0, "usado": 0, "sin cambios": 0, "rechazado": 0, "falló": 0})
            actividad[p["quien"]][p["resultado"]] = actividad[p["quien"]].get(p["resultado"], 0) + 1
ORDEN_AGENTES = ["Coordinador", "Intérprete", "Revisor", "Buscador", "Lector de atributos", "Redactor"]
display(pd.DataFrame(actividad).T.reindex([a for a in ORDEN_AGENTES if a in actividad]).fillna(0).astype(int))

print("Correcciones del revisor que el código aceptó:")
for r in todas_v2:
    for c in r["correcciones"]:
        if c["aceptada"]:
            print(f"  «{r['pedido_consolidado'][:60]}» · {c['campo']}: {c['antes']} → {c['valor']} («{c['evidencia']}»)")
print("\\nLecturas del lector que el código aceptó:")
for r in todas_v2:
    for x in r["lecturas"]:
        if x["aceptada"]:
            print(f"  {x['id']} · {x['campo']} = {x['valor']} («{x['evidencia']}»)")
print("\\nBúsquedas extra del buscador:")
for r in todas_v2:
    if len(r["busquedas"]) > 1:
        print(f"  «{r['pedido_consolidado'][:60]}» · {r['busquedas'][1:]}")
''')

md('''
## 14. Dónde se equivocó

Una métrica sola no dice qué arreglar. Aquí están los casos en que la v2 falló en algo y los casos en que v1 y v2 dieron una primera opción distinta.
''')

code('''
COLUMNAS = ["n", "accion_esperada", "accion", "campos_fallados", "situacion", "top1", "grave", "motivo_grave"]
for conjunto in CONJUNTOS:
    malas = [f for f in FILAS[("v2", conjunto)]
             if not (f["accion_ok"] and f["interpretacion_ok"]) or f["top1"] is False or f["grave"]
             or f.get("acciones_ok") is False]
    print(f"\\nV2, {conjunto}: {len(malas)} con algún error")
    if malas:
        display(pd.DataFrame(malas)[COLUMNAS + (["acciones", "pedido_final"] if conjunto == "conversaciones" else [])])

print("\\nPedidos y variantes donde v1 y v2 eligieron distinta primera opción:")
for conjunto in ("pedidos", "variantes"):
    for n, r2 in respuestas[("v2", conjunto)].items():
        r1 = respuestas[("v1", conjunto)][n]
        p1 = (r1.get("decision") or {}).get("opciones", [{}])[:1]
        p2 = (r2.get("decision") or {}).get("opciones", [{}])[:1]
        id1, id2 = (p1[0].get("id") if p1 else None), (p2[0].get("id") if p2 else None)
        if id1 != id2:
            print(f"  {conjunto} #{n}: v1 {id1} · v2 {id2} · {r2['pedido_tapado'][:60]}")

rechazados = [f for f in FILAS[("v2", "pedidos")] if f["problemas_redaccion"]]
print(f"\\nMensajes del redactor que la verificación rechazó en la v2 (salió la plantilla): {len(rechazados)}")
for f in rechazados:
    r = respuestas[("v2", "pedidos")][f["n"]]
    print(f"  #{f['n']}: {f['problemas_redaccion']}\\n     Lo que escribió: {r['meta_redaccion']['mensaje_ia']}")
''')

md('''
## 15. Tiempo y costo

El tiempo es lo que tardó el modelo en responder, sumando las consultas de cada respuesta y sin las pausas entre consultas. Las consultas que se reutilizaron cuentan con el tiempo que tardaron la primera vez. El costo se calcula con los tokens que reporta Gemini y los precios de la sección 2. Con la clave gratuita no se paga nada; el número sirve para el caso de negocio.
''')

code('''
costos = []
for version in ("v1", "v2"):
    for conjunto in ("pedidos", "conversaciones"):
        filas = FILAS[(version, conjunto)]
        r = RESUMENES[(version, conjunto)]
        tiempos = [f["segundos_total"] for f in filas if f["segundos_total"]]
        costo = (r["tokens_entrada"] * PRECIO_ENTRADA_USD + r["tokens_salida"] * PRECIO_SALIDA_USD) / 1_000_000
        costos.append({"versión": version, "conjunto": conjunto,
                       "segundos (mediana)": round(statistics.median(tiempos), 1) if tiempos else None,
                       "segundos (máximo)": round(max(tiempos), 1) if tiempos else None,
                       "tokens de entrada": r["tokens_entrada"], "tokens de salida": r["tokens_salida"],
                       "US$ por 1.000": round(1000 * costo / len(filas), 2) if r["tokens_entrada"] else None})
display(pd.DataFrame(costos))
print("En conversaciones, cada fila es una conversación completa (dos mensajes).")
''')

md('''
## 16. Prueba tu propia conversación

Cambia los mensajes de la lista y ejecuta la celda. El catálogo es el simulado: hay celulares, portátiles, televisores, audífonos, electrodomésticos y más, pero no todo lo que existe. Las fechas cuentan desde el «hoy» de la simulación.
''')

code('''
MI_CONVERSACION = [
    "quiero un samsung s26 de 256 que me llegue antes del viernes",
    "mejor en azul, y que llegue a Ibagué",
]

mi_conversacion = Conversacion()
for texto in MI_CONVERSACION:
    r = equipo.atender(texto, mi_conversacion)
    print(f"\\nTú: {texto}")
    if r.get("pedido_consolidado") and r["pedido_consolidado"] != r["pedido_tapado"]:
        print(f"   (pedido completo: {r['pedido_consolidado']})")
    print("PriceX:", r["mensaje"])
    for o in (r["decision"] or {}).get("opciones", []):
        print(f"   {o['puesto']}. {nombre_publicacion(o)} · ${o['total']:,}".replace(",", ".") + f" · {o['enlace']}")
    print("   Agentes que trabajaron:", ", ".join(dict.fromkeys(p["quien"] for p in r["traza"])))
''')

md('''
## 17. Guardar, resumir y empacar

La primera celda guarda todo en `resultados/gemini`. La segunda imprime las tablas listas para pegar en el README. La tercera empaca la carpeta en `resultados_gemini.zip` y lo descarga. Ese archivo no trae tu clave: solo las respuestas del modelo y la evaluación.
''')

code('''
for (version, conjunto), rs in respuestas.items():
    if version == "sin IA":
        continue  # la sin IA ya tiene su carpeta: resultados/sin_ia
    with open(SALIDA / f"respuestas_{version}_{conjunto}.jsonl", "w", encoding="utf-8") as f:
        for n, r in rs.items():
            if conjunto == "conversaciones":
                f.write(json.dumps({"n": n, "turnos": [compactar(x) for x in r]}, ensure_ascii=False) + "\\n")
            else:
                f.write(json.dumps({"n": n, **compactar(r)}, ensure_ascii=False) + "\\n")
    pd.DataFrame(FILAS[(version, conjunto)]).to_csv(SALIDA / f"evaluacion_{version}_{conjunto}.csv", index=False,
                                                   encoding="utf-8-sig")
for conjunto, tabla in TABLAS.items():
    tabla.to_csv(SALIDA / f"comparacion_{conjunto}.csv", encoding="utf-8-sig")
informe = {"modelo": MODELO if PROVEEDOR == "gemini" else (MODELO_COLAB or "colab"),
           "version_consultas": VERSION_CONSULTAS, "fecha_corrida": datetime.now().isoformat(timespec="seconds"),
           "resumenes": {f"{v}, {c}": RESUMENES[(v, c)] for v in VERSIONES for c in CONJUNTOS},
           "precision_por_campo": por_campo.to_dict(), "actividad_agentes": actividad, "costos": costos}
(SALIDA / "resumen.json").write_text(json.dumps(informe, ensure_ascii=False, indent=1), encoding="utf-8")
print("Guardado en", SALIDA)
''')

code('''
for conjunto in CONJUNTOS:
    metricas = METRICAS_CONVERSACION if conjunto == "conversaciones" else METRICAS
    print(f"\\n**{conjunto.capitalize()}**\\n")
    print("| Métrica | Sin IA | V1: un agente | V2: equipo |")
    print("|---|---|---|---|")
    for nombre, k, t in metricas:
        print(f"| {nombre} | " + " | ".join(str(celda(RESUMENES[(v, conjunto)], k, t)) for v in VERSIONES) + " |")
print(f"\\nModelo: {informe['modelo']} · corrida del {informe['fecha_corrida'][:10]}")
''')

code('''
ARCHIVO_ZIP = CARPETA / "resultados_gemini.zip"
with zipfile.ZipFile(ARCHIVO_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for archivo in sorted(SALIDA.iterdir()):
        z.write(archivo, f"resultados/gemini/{archivo.name}")
print("Listo:", ARCHIVO_ZIP, f"({ARCHIVO_ZIP.stat().st_size // 1024} KB)")
if EN_COLAB:
    from google.colab import files
    files.download(str(ARCHIVO_ZIP))
''')


def main():
    cuaderno = {
        "cells": [{"cell_type": tipo, "metadata": {}, "source": texto.splitlines(keepends=True),
                   **({"outputs": [], "execution_count": None} if tipo == "code" else {})}
                  for tipo, texto in CELDAS],
        "metadata": {"colab": {"provenance": []},
                     "kernelspec": {"display_name": "Python 3", "name": "python3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 0,
    }
    destino = RAIZ / "agente" / "pricex2_agente.ipynb"
    destino.write_text(json.dumps(cuaderno, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{destino.relative_to(RAIZ)}: {len(CELDAS)} celdas")


if __name__ == "__main__":
    main()
