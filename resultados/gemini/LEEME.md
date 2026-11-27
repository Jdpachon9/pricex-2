# Corridas con IA (versión 1 y versión 2)

Resultados reales de `agente/pricex2_agente.ipynb`, ejecutado en Google Colab con Gemini 3.5 Flash-Lite. Nada de esta carpeta se simula.

| Corrida | Fecha | Dónde está | Qué cambió antes |
|---|---|---|---|
| 1 | 26 de noviembre de 2026 | `corrida_1/` | Es la primera medición del equipo de seis agentes |
| 2 | 26 de noviembre de 2026 | esta carpeta | Regla de modelos corregida, coordinador sin palabras nuevas, buscador con marcas y revisor apagado |

Archivos de cada corrida:

- `respuestas_v1_*.jsonl` y `respuestas_v2_*.jsonl`: el registro de cada pedido, variante y conversación. Los de la v2 traen la traza de cada agente.
- `evaluacion_v1_*.csv` y `evaluacion_v2_*.csv`: la comparación con la clave, caso por caso.
- `comparacion_pedidos.csv`, `comparacion_variantes.csv` y `comparacion_conversaciones.csv`: las tres versiones frente a frente.
- `resumen.json`: los resúmenes, la precisión por campo, lo que hizo cada agente y el costo.
- `llamadas.jsonl` (solo aquí): cada consulta al modelo de las dos corridas, con su respuesta completa. Es la memoria del cuaderno: lo que ya se consultó no se vuelve a pedir.

La página en vivo y su tablero leen las dos corridas desde aquí.
