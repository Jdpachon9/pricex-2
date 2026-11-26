"""Prueba de tubería: ejecuta el cuaderno completo con un cliente FALSO de Gemini, en una copia temporal.

Solo comprueba que el código corre de punta a punta (conexión, guardado, reanudación, las tres versiones, la
evaluación y el zip). Las salidas del cliente falso NO son resultados: la copia temporal se borra al final.
Uso: python3 pruebas/prueba_tuberia_cuaderno.py
"""
import json
import os
import shutil
import sys
import tempfile
import types as tipos
from pathlib import Path

ORIGEN = Path(__file__).resolve().parents[1]
TEMPORAL = Path(tempfile.mkdtemp(prefix="pricex_prueba_"))
PROYECTO = TEMPORAL / "pricex-2"
shutil.copytree(ORIGEN, PROYECTO, ignore=shutil.ignore_patterns("resultados_gemini.zip", "__pycache__"))
for archivo in (PROYECTO / "resultados" / "gemini").glob("*"):  # incluida la carpeta de la corrida 1
    shutil.rmtree(archivo) if archivo.is_dir() else archivo.unlink()
sys.path.insert(0, str(PROYECTO))
sys.path.insert(0, str(PROYECTO / "pruebas"))

from modelo_falso import ModeloColaborador  # noqa: E402

MODELO_FALSO = ModeloColaborador()
CONSULTAS = {"n": 0}


class Config:
    def __init__(self, **kw):
        self.kw = kw


class Uso:
    def __init__(self, entrada, salida):
        self.prompt_token_count, self.candidates_token_count, self.thoughts_token_count = entrada, salida, 0


class Respuesta:
    def __init__(self, salida):
        self.text = salida["texto"]
        self.usage_metadata = Uso(salida["tokens_entrada"], salida["tokens_salida"])


class Modelos:
    def list(self):
        return [tipos.SimpleNamespace(name="models/gemini-3.5-flash-lite")]

    def generate_content(self, model, contents, config):
        CONSULTAS["n"] += 1
        instrucciones = config.kw["system_instruction"]
        if instrucciones.startswith("Responde solo con JSON"):
            return Respuesta({"texto": '{"estado": "listo"}', "tokens_entrada": 10, "tokens_salida": 5})
        salida = MODELO_FALSO(instrucciones, contents)
        if instrucciones.startswith("Eres quien redacta") and "iPhone 16" in salida["texto"]:
            datos = json.loads(salida["texto"])  # un mensaje con una cifra inventada: la verificación debe frenarlo
            salida["texto"] = json.dumps({"mensaje": datos["mensaje"] + " Tiene 24 cuotas sin interés."}, ensure_ascii=False)
        return Respuesta(salida)


class Cliente:
    def __init__(self, api_key):
        self.models = Modelos()


genai = tipos.ModuleType("google.genai")
genai_types = tipos.ModuleType("google.genai.types")
genai_types.GenerateContentConfig = Config
genai.Client, genai.types = Cliente, genai_types
google = sys.modules.get("google") or tipos.ModuleType("google")
google.genai = genai
sys.modules.update({"google": google, "google.genai": genai, "google.genai.types": genai_types})
os.environ["GEMINI_API_KEY"] = "clave-falsa-de-prueba"
os.chdir(PROYECTO)

cuaderno = json.loads((PROYECTO / "agente" / "pricex2_agente.ipynb").read_text(encoding="utf-8"))
celdas = ["".join(c["source"]) for c in cuaderno["cells"] if c["cell_type"] == "code"]


def correr():
    espacio = {"display": lambda x: print(x.to_string() if hasattr(x, "to_string") else x), "__name__": "__main__"}
    for i, codigo in enumerate(celdas):
        exec(compile(codigo, f"celda_{i}", "exec"), espacio)
        if "PAUSA_SEGUNDOS = " in codigo:
            espacio["PAUSA_SEGUNDOS"] = 0
    return espacio


try:
    espacio = correr()
    primera_vuelta = CONSULTAS["n"]
    espacio = correr()  # segunda vuelta: todo debe salir de lo guardado
    print("\n==== PRUEBA DE TUBERÍA (cliente falso: nada de esto es un resultado) ====")
    print("consultas al cliente falso, primera vuelta:", primera_vuelta)
    print("consultas nuevas en la segunda vuelta (debe ser 1, la de prueba):", CONSULTAS["n"] - primera_vuelta)
    print("archivos:", sorted(p.name for p in (PROYECTO / "resultados" / "gemini").iterdir()))
    print("zip:", (PROYECTO / "resultados_gemini.zip").exists())
    for version in ("v1", "v2"):
        rechazados = [f["n"] for f in espacio["FILAS"][(version, "pedidos")] if f["problemas_redaccion"]]
        print(f"{version}: mensajes rechazados por la verificación (se esperan los del iPhone 16):", rechazados)
    print("agentes:", {a: v["consultas"] for a, v in espacio["actividad"].items()})
finally:
    if os.environ.get("PRICEX_CONSERVAR_COPIA"):  # solo para revisar a ojo la demo con datos falsos; nunca publicar
        print("copia temporal conservada en:", PROYECTO)
    else:
        shutil.rmtree(TEMPORAL)
        print("copia temporal borrada:", not TEMPORAL.exists())
