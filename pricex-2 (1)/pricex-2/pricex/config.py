"""Parámetros del asistente. Todo lo que es una decisión de producto vive aquí, con nombre propio."""
from datetime import date

# El "hoy" de la simulación: el día en que se congeló el catálogo
FECHA_HOY = date(2026, 11, 22)
CIUDAD_POR_DEFECTO = "Bogotá"

# Criterio de la mejor opción
DIFERENCIA_EMPATE_PRECIO = 0.03       # en un modelo exacto, menos del 3 % de diferencia cuenta como empate
DIFERENCIA_EMPATE_CALIFICACION = 0.2  # en un pedido abierto, 0,2 estrellas o menos cuentan como empate
MIN_OPINIONES = 30                    # una calificación con menos opiniones no se tiene en cuenta
MIN_VENTAS_VENDEDOR = 50
REPUTACION_NO_CONFIABLE = {"1_red", "2_orange"}
OPCIONES_A_MOSTRAR = 3
MAX_RESULTADOS_BUSQUEDA = 40

# Productos que la persona puede pedir: dominio de la API, nombre para mostrar y palabras de búsqueda
PRODUCTOS = {
    "celular": ("MCO-CELLPHONES", "celular", ["celular"]),
    "portatil": ("MCO-NOTEBOOKS", "portátil", ["portatil"]),
    "freidora_de_aire": ("MCO-AIR_FRYERS", "freidora de aire", ["freidora"]),
    "televisor": ("MCO-TELEVISIONS", "televisor", ["televisor", "tv"]),
    "audifonos": ("MCO-HEADPHONES", "audífonos", ["audifonos"]),
    "consola": ("MCO-GAME_CONSOLES", "consola", ["consola"]),
    "tablet": ("MCO-TABLETS", "tablet", ["tablet"]),
    "lector_libros": ("MCO-EBOOK_READERS", "lector de libros", ["lector", "libros"]),
    "nevera": ("MCO-REFRIGERATORS", "nevera", ["nevera"]),
    "lavadora": ("MCO-WASHING_MACHINES", "lavadora", ["lavadora"]),
    "silla_oficina": ("MCO-OFFICE_CHAIRS", "silla de oficina", ["silla"]),
    "taladro": ("MCO-DRILLS", "taladro", ["taladro"]),
    "cafetera": ("MCO-COFFEE_MAKERS", "cafetera", ["cafetera"]),
    "disco_ssd": ("MCO-SOLID_STATE_DRIVES", "disco SSD", ["ssd", "disco"]),
    "memoria_microsd": ("MCO-MEMORY_CARDS", "memoria microSD", ["memoria", "micro", "microsd"]),
    "cargador": ("MCO-CELLPHONE_CHARGERS", "cargador", ["cargador"]),
    "monitor": ("MCO-MONITORS", "monitor", ["monitor"]),
    "pulsera_inteligente": ("MCO-SMARTBANDS", "pulsera inteligente", ["pulsera", "band"]),
    "control": ("MCO-GAMEPADS", "control", ["control"]),
}
DOMINIO_A_PRODUCTO = {dominio: clave for clave, (dominio, _, _) in PRODUCTOS.items()}

CIUDADES = ["Bogotá", "Medellín", "Cali", "Barranquilla", "Cartagena", "Bucaramanga", "Ibagué", "Pereira",
            "Manizales", "Neiva", "Villavicencio", "Cúcuta", "Santa Marta", "Pasto", "Armenia", "Tunja"]

# Versión 2 (equipo de agentes): cuándo trabaja el Buscador y cuánto puede buscar
MIN_RESULTADOS_DEL_PRODUCTO = 10  # el Buscador trabaja si la búsqueda trajo menos de esto del producto pedido...
MAX_BUSQUEDAS_EXTRA = 2           # ...y quedaron menos de OPCIONES_A_MOSTRAR opciones. Máximo 2 búsquedas más
MAX_PUBLICACIONES_LECTOR = 10     # el Lector lee como máximo 10 títulos por pedido
USAR_REVISOR = False              # apagado tras la corrida 1 con Gemini: 64 consultas y ningún cambio

# Caso de negocio y costos (para el tablero). Precios de Gemini 3.5 Flash-Lite en noviembre de 2026, en dólares
# por millón de tokens; dólar a la TRM de mediados de noviembre; comisión y compra promedio son supuestos.
PRECIO_ENTRADA_USD = 0.30
PRECIO_SALIDA_USD = 2.50
DOLAR_EN_PESOS = 3300
COMISION_AFILIADO = 0.04
COMPRA_PROMEDIO = 1_000_000

# Atributos que se pueden exigir: cómo se comparan
ATRIBUTOS_EXACTOS = ["almacenamiento_gb", "pulgadas", "edicion"]   # tiene que ser igual
ATRIBUTOS_MINIMOS = ["ram_gb", "litros", "kilos", "potencia_w"]     # igual o más
