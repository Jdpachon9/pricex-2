"""Utilidades de texto: normalizar palabras y escribir pesos, decimales y fechas como en Colombia."""
import re
import unicodedata
from datetime import date

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def normalizar(texto):
    """Minúsculas, sin tildes y con un solo espacio entre palabras: 'Ibagué ' -> 'ibague'."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.lower().split())


def palabras(texto):
    """Lista de palabras sin signos: 'WH-1000XM5 (Negro)' -> ['wh', '1000xm5', 'negro']."""
    return re.sub(r"[^a-z0-9]+", " ", normalizar(texto)).split()


def pesos(valor):
    """3849000 -> '$3.849.000'."""
    return "$" + f"{int(round(valor)):,}".replace(",", ".")


def decimal(valor, decimales=1):
    """4.8 -> '4,8'."""
    return f"{valor:.{decimales}f}".replace(".", ",")


def fecha_larga(dia):
    """date(2026, 11, 24) -> 'martes 24 de noviembre'."""
    if isinstance(dia, str):
        dia = date.fromisoformat(dia)
    return f"{DIAS[dia.weekday()]} {dia.day} de {MESES[dia.month - 1]}"
