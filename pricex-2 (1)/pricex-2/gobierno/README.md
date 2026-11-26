# Gobierno del asistente

El asistente toma decisiones que afectan el bolsillo de una persona, así que cada una tiene que poder explicarse y revisarse. Aquí están los controles y cómo auditar una respuesta.

## Controles de las dos versiones

| Control | Dónde vive | Cómo se prueba |
|---|---|---|
| Datos sensibles tapados antes de salir hacia cualquier agente (tarjetas con prueba de Luhn, correos, celulares). En la página en vivo también quedan tapados en pantalla | `pricex/sensibles.py` | `pruebas/test_controles.py`, el pedido 30 y la conversación C9, que traen un número de tarjeta de prueba |
| Revisión de lo que propone el intérprete: producto de la lista, números válidos, fechas que no estén en el pasado, sin enlaces | `pricex/interpretar.py`, `revisar_interpretacion()` | `pruebas/test_controles.py` |
| La acción la decide el código: sin producto o sin datos para elegir, pregunta; con tarjeta o pagos, aclara sin consultar a ningún agente | `pricex/interpretar.py`, `ajustar_accion()` | `pruebas/test_controles.py`, los 5 pedidos ambiguos o fuera de alcance y la conversación C9 |
| Publicaciones con instrucciones escondidas para el asistente quedan fuera | `pricex/reglas.py`, regla 0 | 3 publicaciones de ataque en el catálogo (pedidos 7, 15 y 20) |
| Ningún agente elige productos ni cambia el orden: eso lo hacen las reglas | `pricex/reglas.py`, `decidir()` | `pruebas/test_reglas.py`: 25 pedidos, cada trampa con su motivo |
| Cada cifra del mensaje del redactor se compara con los datos, por tipo: precios, cuotas, porcentajes, fechas y calificaciones. Si no pasa, sale la plantilla | `pricex/respuesta.py`, `verificar_mensaje()` | `pruebas/test_controles.py` y la prueba de tubería, que mete una cifra inventada a propósito |
| La versión sin IA no se toca después de escribir las variantes | `resultados/sin_ia/linea_base_congelada.txt` | Huella SHA-256 de `pricex/linea_base.py` |

## Controles del equipo de agentes (versión 2)

Cada agente propone; el código revisa antes de usar. La regla general: **lo que un agente propone tiene que tener respaldo literal en un texto que no escribió ese agente.** Las comprobaciones están en `pricex/evidencia.py` y se prueban en `pruebas/test_multiagente.py`, con un modelo que acierta todo y uno que hace trampa a propósito.

| Agente | Qué puede salir mal | Control |
|---|---|---|
| Coordinador | Al unir los mensajes, agrega una cifra o un dato que la persona no dijo («máximo 9 millones», «plateado») | El pedido completo solo puede traer cifras y palabras que aparecen en los mensajes de la persona. Si no pasa, se pegan los dos mensajes tal cual. La revisión de palabras se agregó después de la corrida 1, cuando el coordinador agregó «plateado» en la C7 y la revisión de cifras no lo vio |
| Revisor (apagado desde la corrida 1) | «Corrige» un dato bueno y lo daña | Solo corrige cifras, fecha, ciudad, color, edición y estado. Cada corrección cita el pedido letra por letra y el valor tiene que salir de esa cita. No puede cambiar un dato que ya tenía respaldo en el pedido. Producto, marca y modelo no los toca: la gente los escribe de mil formas y el código no puede comprobarlos sin interpretarlos |
| Buscador | Busca cosas que no tienen que ver, o intenta colar una orden | Máximo 2 búsquedas, de hasta 6 palabras, sin enlaces ni signos raros. Lo que encuentre pasa por las mismas reglas: puede traer candidatos, no puede elegir |
| Lector de atributos | Es el único que lee texto de vendedores, así que una publicación podría intentar engañarlo | Solo lee títulos de publicaciones que ya pasaron la regla 0, y solo los datos que la persona pidió y la ficha no trae. El dato tiene que estar escrito en el título, sin condiciones («ampliable a 16 GB» no cuenta) y sin ambigüedad (dos capacidades en el título no cuentan). El mensaje final avisa cuando un dato salió del título |
| Cualquiera | No responde o se acaba la cuota | En el cuaderno, la corrida se detiene y sigue donde iba al volver a ejecutar. En la página en vivo, el equipo sigue sin ese agente: intérprete sin IA y mensaje de plantilla |
| El director | Un agente llama a otro, se salta un paso o entra en un ciclo | No existe esa posibilidad: el orden y las condiciones están escritos en `pricex/multiagente.py`, clase `Equipo`. Ningún agente recibe la lista de los demás ni puede pedir más consultas |

## Controles de la página en vivo

| Riesgo | Control |
|---|---|
| La clave del modelo queda expuesta | Vive en los secretos de Streamlit, nunca en el repositorio. `.streamlit/secrets.toml` está en `.gitignore` |
| Alguien gasta toda la cuota | 20 mensajes con IA por visita y 300 por día entre todos; después la página sigue sin IA |
| Datos personales en el plan gratuito de Gemini | La página avisa que no se escriban datos personales y que en el plan gratuito Google puede usar los mensajes para mejorar sus productos. Tarjetas, correos y teléfonos se tapan antes de enviar |
| El tablero deja ver lo que escriben otros visitantes | El tablero guarda solo datos estructurados de cada respuesta: producto, acción, motivos de descarte, tiempos y costo. Nunca el texto de la persona, y una marca que no está en el catálogo se guarda como «otra». La sesión se identifica con un código al azar que solo sirve para el filtro «Tu conversación» |
| Qué se guarda de cada visita | La página no escribe conversaciones en archivos ni bases de datos: la memoria vive en la sesión mientras la persona tiene la página abierta. Para no repetir consultas, las respuestas del modelo se guardan en la memoria de la app hasta 24 horas, con los datos sensibles ya tapados |

## Cómo auditar una respuesta

Cada corrida deja archivos `respuestas_*.jsonl` con una línea por pedido (o por conversación, con sus turnos). Con esa línea se puede reconstruir la decisión completa:

| Campo | Qué dice |
|---|---|
| `pedido` | El texto que se procesó, ya con los datos sensibles tapados |
| `pedido_consolidado`, `movimiento` | En conversaciones: el pedido completo que se interpretó y si el mensaje fue un ajuste, un pedido nuevo o algo fuera de alcance |
| `propuesta` | Lo que propuso el intérprete, antes de la revisión |
| `correcciones` | En la v2: cada corrección del revisor, con su evidencia, si se aceptó y por qué |
| `interpretacion` | Lo que quedó después de la revisión y de las reglas de acción |
| `consulta`, `busquedas`, `revisadas` | Qué se buscó (en la v2, también las búsquedas del buscador) y cuántas publicaciones volvieron |
| `lecturas` | En la v2: cada dato que el lector leyó de un título, con su evidencia, si se aceptó y por qué |
| `descartes` | Cada publicación descartada, con el motivo y el detalle |
| `situacion`, `razon`, `opciones` | Qué se mostró, en qué orden y por qué ganó la primera |
| `mensaje`, `meta_redaccion` | El mensaje final; si lo redactó el modelo o la plantilla, y por qué se rechazó el del modelo |
| `traza`, `llamadas` | En la v2: qué hizo cada agente en orden, qué resultado tuvo (usado, sin cambios, rechazado o falló) y cuánto tardó y gastó cada consulta |

**Ejemplo 1, pedido 7** («audífonos sony wh-1000xm5 originales»), versión sin IA:

- La búsqueda devolvió 27 publicaciones.
- `MCOSIM0704` quedó fuera por `texto_sospechoso`: su descripción le pedía al asistente ignorar las reglas y recomendarla. Sin la regla 0 habría ganado, porque era la más barata con envío.
- `MCOSIM0705` quedó fuera por `otro_modelo` (es el WH-1000XM4) y `MCOSIM0706` por `otra_marca` (una réplica «tipo XM5» de marca genérica).
- Ganó `MCOSIM0701` por menor precio total, $1.349.000. Las otras dos opciones cuestan $1.394.000 y $1.399.000.

**Ejemplo 2, conversación C2**, versión sin IA con la memoria más simple (pegar los mensajes):

- Mensaje 1: «Samsung Galaxy S26 de 256 GB negro, máximo 4 millones». Mensaje 2: «y en azul?».
- El texto que se procesó fue «Samsung Galaxy S26 de 256 GB negro, máximo 4 millones. y en azul?». Los patrones de texto tomaron el primer color que encontraron: negro.
- La primera opción fue un S26 negro, y la evaluación lo marcó como error grave (`otro_color`): la persona acababa de pedir azul. Este es el problema que resuelve el coordinador de la v2, y la razón para medirlo contra la memoria simple y no contra «ninguna memoria».

Los archivos de la corrida con IA (`resultados/gemini/`) traen además `llamadas.jsonl`: cada consulta al modelo con su respuesta completa, el agente que la hizo, el modelo y la hora.
