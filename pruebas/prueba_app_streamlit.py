"""Prueba de humo de la página en vivo (app.py) con un Streamlit FALSO y, en un caso, un Gemini FALSO.

Streamlit vuelve a ejecutar app.py de arriba abajo cada vez que la persona escribe o hace clic. Esta prueba imita
eso: corre app.py varias veces seguidas, con mensajes de prueba, y revisa lo que quedó en pantalla y en la sesión.
No prueba cómo se ve (eso hay que mirarlo en la página publicada), solo que la lógica no falle.
Las respuestas del Gemini falso NO son resultados.
Uso: python3 pruebas/prueba_app_streamlit.py
"""
import inspect
import os
import sys
import tempfile
import types as tipos
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "pruebas"))

from modelo_falso import ModeloColaborador  # noqa: E402


class Sesion(dict):
    def __getattr__(self, nombre):
        try:
            return self[nombre]
        except KeyError as error:
            raise AttributeError(nombre) from error

    def __setattr__(self, nombre, valor):
        self[nombre] = valor


class Secretos(dict):
    def get(self, nombre, defecto=None):
        if not self:
            raise FileNotFoundError("No secrets found")
        return super().get(nombre, defecto)


class StreamlitFalso(tipos.ModuleType):
    def __init__(self, secretos):
        super().__init__("streamlit")
        self.session_state, self.secrets = Sesion(), Secretos(secretos)
        self.pantalla, self.entrada, self.clics, self._memoria, self.elecciones = [], None, set(), {}, {}
        self.sidebar = Bloque(self, "barra lateral")

    def _anotar(self, tipo, texto=""):
        self.pantalla.append((tipo, str(texto)))

    def _cache(self, funcion=None, **_):
        def decorar(f):
            nombres = list(inspect.signature(f).parameters)

            def envuelta(*args):
                llave = (f.__name__,) + tuple(a for n, a in zip(nombres, args) if not n.startswith("_"))
                if llave not in self._memoria:
                    self._memoria[llave] = f(*args)
                return self._memoria[llave]
            return envuelta
        return decorar(funcion) if funcion else decorar

    cache_resource = cache_data = _cache

    def set_page_config(self, **_): pass
    def title(self, t): self._anotar("título", t)
    def subheader(self, t): self._anotar("subtítulo", t)
    def markdown(self, t, **_): self._anotar("texto", t)
    def caption(self, t, **_): self._anotar("nota", t)
    def info(self, t, **_): self._anotar("aviso", t)
    def divider(self): pass
    def chat_input(self, *_, **__): return self.entrada
    def button(self, etiqueta, key=None, **_): return (key or etiqueta) in self.clics
    def toggle(self, etiqueta, value=False, **_): return value
    def container(self, **_): return Bloque(self, "tarjeta")
    def expander(self, etiqueta, **_): return Bloque(self, "desplegable: " + etiqueta)
    def chat_message(self, rol, **_): return Bloque(self, "mensaje de " + rol)
    def image(self, imagen, **_): self._anotar("imagen", Path(str(imagen)).name)
    def spinner(self, texto): return Bloque(self, "esperando")
    def tabs(self, nombres): return [Bloque(self, "pestaña: " + n) for n in nombres]
    def columns(self, spec): return [Bloque(self, "columna") for _ in range(spec if isinstance(spec, int) else len(spec))]
    def metric(self, etiqueta, valor, **_): self._anotar("métrica", f"{etiqueta}: {valor}")
    def dataframe(self, datos, **_): self._anotar("tabla", len(datos))
    def download_button(self, etiqueta, datos, **_): self._anotar("descarga", datos.splitlines()[0][:40]); return False

    def radio(self, etiqueta, opciones, key=None, format_func=str, **_):
        elegida = self.elecciones.get(key, opciones[0])
        return elegida if elegida in opciones else opciones[0]

    def selectbox(self, etiqueta, opciones, key=None, format_func=str, **_):
        elegida = self.elecciones.get(key, opciones[0])
        return elegida if elegida in opciones else opciones[0]


class Bloque:
    def __init__(self, st, nombre):
        self.st, self.nombre = st, nombre

    def __enter__(self):
        self.st._anotar("bloque", self.nombre)
        return self

    def __exit__(self, *_):
        return False

    def __getattr__(self, nombre):
        return getattr(self.st, nombre)


def gemini_falso(modelo, falla=None):
    """Un paquete google.genai de mentira que responde con el ModeloColaborador (o falla, si se pide)."""
    class Config:
        def __init__(self, **kw):
            self.kw = kw

    class Respuesta:
        def __init__(self, salida):
            self.text = salida["texto"]
            self.usage_metadata = tipos.SimpleNamespace(prompt_token_count=900, candidates_token_count=60,
                                                        thoughts_token_count=0)

    class Modelos:
        def generate_content(self, model, contents, config):
            if falla:
                raise RuntimeError(falla)
            return Respuesta(modelo(config.kw["system_instruction"], contents))

    genai = tipos.ModuleType("google.genai")
    genai_types = tipos.ModuleType("google.genai.types")
    genai_types.GenerateContentConfig = Config
    genai.Client = lambda api_key: tipos.SimpleNamespace(models=Modelos())
    genai.types = genai_types
    google = tipos.ModuleType("google")
    google.genai = genai
    sys.modules.update({"google": google, "google.genai": genai, "google.genai.types": genai_types})


def correr_app(st, entrada=None, clics=(), elecciones=None):
    st.pantalla, st.entrada, st.clics = [], entrada, set(clics)
    st.elecciones.update(elecciones or {})
    sys.modules["streamlit"] = st
    codigo = (RAIZ / "app.py").read_text(encoding="utf-8")
    exec(compile(codigo, str(RAIZ / "app.py"), "exec"), {"__name__": "__main__", "__file__": str(RAIZ / "app.py")})
    return st


def ultima(st):
    return [m for m in st.session_state.historial if m["rol"] == "assistant"][-1]["respuesta"]


def metrica(st, nombre):
    return next((t.split(": ", 1)[1] for tipo, t in st.pantalla if tipo == "métrica" and t.startswith(nombre + ":")), None)


def revisar(condicion, descripcion):
    print(("bien  " if condicion else "MAL   ") + descripcion)
    if not condicion:
        raise SystemExit(1)


# Cada caso usa su propio archivo de registro, para que no se mezclen los visitantes de un caso con otro
CARPETA_REGISTROS = Path(tempfile.mkdtemp(prefix="pricex_registros_"))


def registro_nuevo():
    os.environ["PRICEX_REGISTRO"] = str(CARPETA_REGISTROS / f"eventos_{len(list(CARPETA_REGISTROS.iterdir()))}.jsonl")
    (CARPETA_REGISTROS / Path(os.environ["PRICEX_REGISTRO"]).name).touch()


# 1. Sin clave: la página funciona sin IA y recuerda el pedido pegando los textos
registro_nuevo()
st = StreamlitFalso({})
correr_app(st)
revisar(any("sin IA" in t for _, t in st.pantalla), "sin clave, la barra lateral avisa que funciona sin IA")
correr_app(st, "quiero cambiar el televisor")
correr_app(st, "de 55 pulgadas, máximo 2 millones")
r = ultima(st)
revisar(r["modo"] == "sin IA" and r["decision"]["opciones"][0]["id"] == "MCOSIM1501",
        "sin IA, el segundo mensaje completa el pedido y gana MCOSIM1501")
revisar(len(st.session_state.historial) == 4, "el historial tiene los 4 mensajes")
correr_app(st, clics={"ejemplo_1"})
revisar(ultima(st)["pedido"] == "tele de 55 pulgadas que no pase de 2 palos", "el botón de ejemplo envía su texto")
correr_app(st, "págalo con mi tarjeta 4111 1111 1111 1111")
pantalla = " ".join(t for _, t in st.pantalla)
revisar("4111" not in pantalla and ultima(st)["accion"] == "aclarar", "la tarjeta no queda en pantalla y aclara pagos")

# El tablero se mueve con cada mensaje
revisar(metrica(st, "Mensajes") == "4", "el tablero cuenta los 4 mensajes de los visitantes")
correr_app(st, "Xiaomi Smart Band 9")
revisar(metrica(st, "Mensajes") == "5", "con un mensaje más, el tablero pasa a 5 sin recargar nada")
revisar(any(tipo == "descarga" and t.startswith("momento,origen") for tipo, t in st.pantalla), "ofrece el CSV")
pantalla = " ".join(t for _, t in st.pantalla)
revisar("tele de 55" not in pantalla.split("pestaña: Tablero")[-1], "el tablero no muestra el texto de nadie")
correr_app(st, elecciones={"tablero_fuente": "Pruebas grabadas"})
revisar(metrica(st, "Mensajes") == "80", "con «Pruebas grabadas» muestra las 80 respuestas de la corrida sin IA")
correr_app(st, elecciones={"tablero_fuente": "Pruebas grabadas", "tablero_producto": "celular"})
revisar(metrica(st, "Mensajes") == "18", "el filtro de producto deja solo los 18 mensajes de celulares")
correr_app(st, elecciones={"tablero_fuente": "Pruebas grabadas", "tablero_version": "v2", "tablero_producto": "Todos"})
pantalla = " ".join(t for _, t in st.pantalla)
revisar(metrica(st, "Mensajes") == "80" and "59 de 59" in pantalla,
        "la v2 abre en la corrida actual, con sus 80 mensajes y la mejor opción primera en 59 de 59")
revisar("¿Qué cambió entre corridas?" in pantalla and "Corrida 1" in pantalla, "muestra el antes y el después")
correr_app(st, elecciones={"tablero_fuente": "Pruebas grabadas", "tablero_version": "v2", "tablero_corrida": 1,
                           "tablero_producto": "Todos"})
revisar("55 de 59" in " ".join(t for _, t in st.pantalla), "con la corrida 1 vuelven los 55 aciertos de entonces")

# 2. Con clave (Gemini falso): atiende el equipo de agentes y la conversación cambia el color
registro_nuevo()
gemini_falso(ModeloColaborador())
st = StreamlitFalso({"GEMINI_API_KEY": "clave-falsa"})
correr_app(st, "Samsung Galaxy S26 de 256 GB negro, máximo 4 millones")
correr_app(st, "y en azul?")
r = ultima(st)
revisar(r["modo"] == "multiagente" and r["decision"]["opciones"][0]["id"] == "MCOSIM0104",
        "con IA, el coordinador une los mensajes y gana el S26 azul (MCOSIM0104)")
revisar(any(t == "desplegable: Qué hizo cada agente" for _, t in st.pantalla), "se muestra la traza de los agentes")
revisar(st.session_state.mensajes_ia == 2, "cuenta los mensajes con IA de la visita")
correr_app(st, elecciones={"tablero_fuente": "Tu conversación"})
revisar(metrica(st, "Mensajes") == "2" and (metrica(st, "Costo por mensaje") or "").startswith("US$"),
        "«Tu conversación» muestra los 2 mensajes y el costo con IA")
pantalla = " ".join(t for _, t in st.pantalla)
revisar("Coordinador" in pantalla and "Intérprete" in pantalla, "el tablero muestra lo que hizo cada agente")

# 3. Se acaba la cuota: el equipo sigue sin los agentes que fallan y los mensajes siguientes van sin IA
registro_nuevo()
gemini_falso(ModeloColaborador(), falla="429 RESOURCE_EXHAUSTED: quota exceeded")
st = StreamlitFalso({"GEMINI_API_KEY": "clave-falsa"})
correr_app(st, "tele de 55 pulgadas que no pase de 2 palos")
r = ultima(st)
revisar(r["mensaje"] and r["decision"]["opciones"][0]["id"] == "MCOSIM1501",
        "si el modelo falla, la respuesta sale igual (intérprete sin IA y plantilla)")
correr_app(st, "Xiaomi Smart Band 9")
revisar(ultima(st)["modo"] == "sin IA", "después de la cuota agotada, atiende la versión sin IA")

# 4. Límite por visita
registro_nuevo()
gemini_falso(ModeloColaborador())
st = StreamlitFalso({"GEMINI_API_KEY": "clave-falsa"})
correr_app(st)
st.session_state.mensajes_ia = 20
correr_app(st, "Xiaomi Smart Band 9")
revisar(ultima(st)["modo"] == "sin IA", "al llegar a 20 mensajes con IA, sigue sin IA")
import shutil  # noqa: E402
shutil.rmtree(CARPETA_REGISTROS)
print("\nPrueba de la página: todo bien.")
