"""Guardar el uso de la página en vivo en una hoja de Google Sheets, para que no se pierda cuando la app se duerme.

Streamlit Community Cloud apaga la página después de un rato sin visitas, y con ella se borra lo que estaba en
memoria. Con una hoja conectada, cada mensaje queda como una fila con las mismas columnas del CSV del tablero, y al
despertar la página vuelve a leerla. La hoja se puede abrir directo en Power BI o en Excel.

Solo guarda datos estructurados (producto, acción, motivos, tiempos y costo), nunca el texto que escribe la persona.

Se configura con dos secretos de Streamlit (los pasos están en despliegue/STREAMLIT.md):
- HOJA_DE_USO_URL: el enlace de la hoja.
- HOJA_DE_USO_CUENTA: el contenido del archivo JSON de la cuenta de servicio de Google Cloud.
"""
import json

from .tablero import columnas, evento_de_fila, fila_de


def _celda(valor):
    return "" if valor is None else valor


class HojaDeUso:
    """Una hoja de cálculo como registro: lee todas las filas al empezar y agrega una fila por mensaje.

    'hoja' es una pestaña de gspread (o un objeto falso con los mismos dos métodos, en las pruebas)."""

    def __init__(self, hoja):
        self.hoja = hoja
        try:  # los números sin formato: así la configuración regional de la hoja no cambia los decimales
            valores = hoja.get_all_values(value_render_option="UNFORMATTED_VALUE")
        except TypeError:
            valores = hoja.get_all_values()
        if not valores or not any(valores[0]):
            self.encabezado = columnas()
            hoja.append_row(self.encabezado, value_input_option="RAW")
            self._filas = []
        else:
            self.encabezado = [str(c) for c in valores[0]]
            self._filas = valores[1:]

    def leer(self):
        return [evento_de_fila(dict(zip(self.encabezado, fila))) for fila in self._filas if any(fila)]

    def agregar(self, evento):
        datos = dict(zip(columnas(), fila_de(evento)))
        self.hoja.append_row([_celda(datos.get(c)) for c in self.encabezado], value_input_option="RAW")


def conectar(url, cuenta):
    """Abre la primera pestaña de la hoja con la cuenta de servicio. 'cuenta' es el JSON como texto o como tabla."""
    import gspread  # solo hace falta en la página publicada con la hoja configurada

    datos = json.loads(cuenta) if isinstance(cuenta, str) else dict(cuenta)
    cliente = gspread.service_account_from_dict(datos)
    return HojaDeUso(cliente.open_by_url(url).sheet1)
