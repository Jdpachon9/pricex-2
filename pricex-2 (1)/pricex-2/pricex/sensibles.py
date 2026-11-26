"""Tapa los datos sensibles antes de que el pedido salga hacia el modelo de IA.

El asistente no necesita números de tarjeta, correos ni teléfonos para buscar un producto, así que no los recibe.
"""
import re

TARJETA = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
CELULAR = re.compile(r"(?<!\d)(?:\+?57[ -]?)?3\d{2}[ -]?\d{3}[ -]?\d{4}(?!\d)")


def pasa_luhn(cifras):
    """Prueba de Luhn: la que usan los números de tarjeta reales para detectar errores de digitación."""
    total = 0
    for i, c in enumerate(reversed(cifras)):
        d = int(c)
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def tapar_datos_sensibles(texto):
    """Devuelve el texto con [TARJETA], [CORREO] y [TELEFONO] en lugar de los datos, y la lista de lo que tapó."""
    tapados = []

    def tarjeta(m):
        cifras = re.sub(r"\D", "", m.group(0))
        if 13 <= len(cifras) <= 19 and pasa_luhn(cifras):
            tapados.append("tarjeta")
            return "[TARJETA]"
        return m.group(0)

    texto = TARJETA.sub(tarjeta, texto)
    texto, n = CORREO.subn("[CORREO]", texto)
    tapados += ["correo"] * n
    texto, n = CELULAR.subn("[TELEFONO]", texto)
    tapados += ["telefono"] * n
    return texto, tapados
