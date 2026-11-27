"""Cómo se ve el tablero: HTML simple, sin JavaScript. Las barras son filas con su ancho en porcentaje.

Lo usa la página en vivo (app.py) con st.markdown(..., unsafe_allow_html=True). El texto hereda el color del tema
de Streamlit y los grises son transparentes, así que se lee en modo claro y en modo oscuro. Colores de la paleta de
referencia de visualización: azul para una sola serie, una escala ordenada de azules para el embudo, y para el
resultado de los agentes azul (usado), gris (sin cambios), naranja (rechazado) y rojo de alerta (falló).
Todo texto pasa por html.escape.
"""
from html import escape as _escape

from .reglas import MOTIVOS
from .respuesta import FRASES_MOTIVO
from .tablero import AGENTES, NOMBRE_VERSION_CORTO, RESULTADOS, SITUACIONES, nombre_producto, usd
from .texto import decimal, pesos

AZUL = "#8d1bf4"  # morado de la identidad original de PriceX (se deja el nombre para no tocar el resto)
GRIS = "rgba(128,128,128,.45)"  # «Otros»: lo que se junta al final no compite con las barras con nombre
EMBUDO = ["#d2b4fb", "#b07cf8", "#8d1bf4", "#6512b8"]  # escala ordenada: más oscuro, más cerca del resultado
# Probada con el validador de daltonismo: morado, naranja y vino se distinguen; «sin cambios» va en gris.
COLOR_RESULTADO = {"usado": "#8d1bf4", "sin cambios": "rgba(128,128,128,.45)", "rechazado": "#f47230",
                   "falló": "#a11a2b"}

ESTILO = """<style>
.px{font-size:15px;line-height:1.45}
.px h4{font-size:17px;font-weight:600;margin:6px 0 2px;padding:0}
.px .px-lectura{margin:0 0 12px;max-width:68ch}
.px .px-fila{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3px 12px;align-items:baseline;margin:0 0 9px}
.px .px-cifra{font-variant-numeric:tabular-nums;font-weight:600;white-space:nowrap}
.px .px-cifra small{font-weight:400;opacity:.7;margin-left:6px}
.px .px-pista{grid-column:1/-1;height:10px;border-radius:0 4px 4px 0;background:rgba(128,128,128,.14)}
.px .px-barra{height:100%;border-radius:0 4px 4px 0;min-width:2px}
.px .px-tenue{opacity:.72;font-size:13px}
.px .px-seg{grid-column:1/-1;display:flex;gap:2px;height:8px}
.px .px-seg span{display:block;height:100%;border-radius:999px;min-width:3px}
.px .px-leyenda{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;opacity:.85;margin:2px 0 12px}
.px .px-leyenda i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.px table{border-collapse:collapse;width:100%;font-size:14px}
.px .px-scroll{overflow-x:auto}
.px th,.px td{text-align:left;padding:6px 8px;border-bottom:1px solid rgba(128,128,128,.25);vertical-align:top}
.px th{font-weight:600;opacity:.8}
.px th.n{text-align:right}
.px td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
</style>"""


PLURAL_RESULTADO = {"usado": ("usada", "usadas"), "sin cambios": ("sin cambios", "sin cambios"),
                    "rechazado": ("rechazada", "rechazadas"), "falló": ("falló", "fallaron")}


def escape(texto):
    """Escapa el HTML y también el signo $, que Streamlit podría leer como el inicio de una fórmula."""
    return _escape(str(texto)).replace("$", "&#36;")


def mayuscula(texto):
    """Primera letra en mayúscula sin tocar el resto: «disco SSD» -> «Disco SSD»."""
    return texto[:1].upper() + texto[1:]


def bloque(contenido):
    return f'<div class="px">{contenido}</div>'


def seccion(pregunta, lectura=None):
    """La pregunta de negocio como título y su lectura en una frase, antes de la gráfica."""
    html = f"<h4>{escape(pregunta)}</h4>"
    if lectura:
        html += f'<p class="px-lectura">{escape(lectura)}</p>'
    return bloque(html)


def fila_barra(etiqueta, valor, maximo, color=AZUL, nota=None, titulo=None):
    ancho = 0 if not maximo else max(0.0, min(100.0, 100 * valor / maximo))
    nota_html = f"<small>{escape(nota)}</small>" if nota else ""
    titulo_html = f' title="{escape(titulo)}"' if titulo else ""
    return (f'<div class="px-fila"{titulo_html}><span>{escape(etiqueta)}</span>'
            f'<span class="px-cifra">{escape(f"{valor:,}".replace(",", "."))}{nota_html}</span>'
            f'<div class="px-pista"><div class="px-barra" style="width:{ancho:.1f}%;background:{color}"></div></div></div>')


def embudo(etapas):
    """Cada etapa como barra contra la primera; la nota dice qué parte de los mensajes llegó hasta ahí."""
    if not etapas or not etapas[0][1]:
        return bloque('<p class="px-tenue">Sin mensajes todavía.</p>')
    primero = etapas[0][1]
    filas = [fila_barra(nombre, valor, primero, EMBUDO[min(i, len(EMBUDO) - 1)],
                        nota=None if i == 0 else f"{round(100 * valor / primero)} %",
                        titulo=f"{nombre}: {valor} de {primero}")
             for i, (nombre, valor) in enumerate(etapas)]
    return bloque("".join(filas))


def barras(filas, maximo_filas=7, total=None, nombre_otros="Otros"):
    """Barras ordenadas de mayor a menor, un solo color. Lo que no cabe se junta en «Otros»."""
    if not filas:
        return bloque('<p class="px-tenue">Nada que mostrar con este filtro.</p>')
    visibles, otros = filas, None
    if len(filas) > maximo_filas:
        juntas = filas[maximo_filas - 1:]
        visibles, otros = filas[:maximo_filas - 1], (f"{nombre_otros} ({len(juntas)})", sum(v for _, v in juntas))
    maximo = max(v for _, v in visibles + ([otros] if otros else []))
    total = total or sum(v for _, v in filas)
    html = "".join(fila_barra(n, v, maximo, nota=f"{round(100 * v / total)} %" if total else None,
                              titulo=f"{n}: {v} de {total}") for n, v in visibles)
    if otros:
        juntas = ", ".join(n for n, _ in filas[maximo_filas - 1:])
        html += fila_barra(otros[0], otros[1], maximo, color=GRIS, nota=f"{round(100 * otros[1] / total)} %",
                           titulo=f"Juntas: {juntas}")
    return bloque(html)


def motivos(motivos_contados, total):
    filas = [(mayuscula(FRASES_MOTIVO[m][1]), n) for m, n in motivos_contados if m in MOTIVOS]
    return barras(filas, total=total)


def productos(productos_contados):
    return barras([(mayuscula(nombre_producto(p)), n) for p, n in productos_contados], maximo_filas=8)


def agentes(filas):
    """Una fila por agente: cuántas veces trabajó y una barra delgada con lo que pasó con lo que propuso."""
    if not filas:
        return bloque('<p class="px-tenue">En estos datos no trabajó ningún agente de IA: los atendió la versión '
                      'sin IA.</p>')
    leyenda = "".join(f'<span><i style="background:{COLOR_RESULTADO[r]}"></i>{escape(mayuscula(r))}</span>'
                      for r in RESULTADOS)
    html = [f'<div class="px-leyenda">{leyenda}</div>']
    for agente in AGENTES:
        cuenta = dict(filas).get(agente)
        if not cuenta:
            continue
        veces = sum(cuenta.values())
        partes = "".join(f'<span title="{escape(r)}: {cuenta[r]}" style="flex:{cuenta[r]};background:{COLOR_RESULTADO[r]}">'
                         f'</span>' for r in RESULTADOS if cuenta.get(r))
        detalle = " · ".join(f"{cuenta[r]} {PLURAL_RESULTADO[r][0 if cuenta[r] == 1 else 1]}"
                             for r in RESULTADOS if cuenta.get(r))
        html.append(f'<div class="px-fila" title="{escape(agente)}: trabajó {veces} veces"><span>{escape(agente)}</span>'
                    f'<span class="px-cifra">{escape(detalle)}</span><div class="px-seg">{partes}</div></div>')
    return bloque("".join(html))


def demanda(filas, maximo_filas=8):
    if not filas:
        return bloque('<p class="px-tenue">Todos los pedidos con datos para buscar encontraron opciones.</p>')
    cuerpo = "".join(
        f"<tr><td>{escape(mayuscula(nombre_producto(f['producto'])))}</td><td>{escape(SITUACIONES[f['situacion']])}</td>"
        f"<td class='n'>{f['pedidos']}</td>"
        f"<td class='n'>{escape(pesos(f['brecha_mediana'])) if f['brecha_mediana'] else '—'}</td></tr>"
        for f in filas[:maximo_filas])
    return bloque("<table><tr><th>Producto</th><th>Qué pasó</th><th class='n'>Pedidos</th>"
                  f"<th class='n'>Le faltó</th></tr>{cuerpo}</table>")


def calidad(c):
    """Los aciertos contra la respuesta correcta, cada uno sobre su total, y los errores graves dichos en palabras."""
    filas = [fila_barra("Mejor opción en el primer puesto", c["top1"], c["recomendables"], nota=f"de {c['recomendables']}"),
             fila_barra("Entendió el pedido sin errores", c["entendio"], c["recomendables"],
                        nota=f"de {c['recomendables']}"),
             fila_barra("Hizo lo que debía: recomendar, preguntar o aclarar", c["acciones_ok"], c["casos"],
                        nota=f"de {c['casos']}")]
    if c["graves"]:
        grave = (f"{c['graves']} error{'es' if c['graves'] != 1 else ''} grave{'s' if c['graves'] != 1 else ''}: "
                 "la primera opción incumplía lo pedido.")
    else:
        grave = "Ningún error grave: la primera opción nunca incumplió lo pedido."
    return bloque("".join(filas) + f'<p class="px-tenue">{escape(grave)}</p>')


def tabla_corridas(filas):
    """El antes y el después de cada versión: aciertos, errores graves, costo y tiempo del modelo."""
    cuerpo = ""
    for f in filas:
        corrida = "Línea base" if f["corrida"] is None else f"Corrida {f['corrida']}"
        costo = usd(f["costo_usd"]) if f["costo_usd"] else "Sin IA"
        segundos = f"{decimal(f['segundos'], 1)} s" if f["segundos"] else "—"
        cuerpo += (f"<tr><td>{escape(NOMBRE_VERSION_CORTO.get(f['version'], f['version']))}</td><td>{escape(corrida)}</td>"
                   f"<td class='n'>{f['top1']} de {f['recomendables']}</td><td class='n'>{f['graves']}</td>"
                   f"<td class='n'>{escape(costo)}</td><td class='n'>{escape(segundos)}</td></tr>")
    return bloque("<div class='px-scroll'><table><tr><th>Versión</th><th>Corrida</th>"
                  "<th class='n'>Mejor opción primero</th><th class='n'>Errores graves</th>"
                  f"<th class='n'>Costo por mensaje</th><th class='n'>Tiempo del modelo</th></tr>{cuerpo}</table></div>")

