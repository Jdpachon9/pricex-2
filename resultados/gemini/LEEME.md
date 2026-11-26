# Corridas con IA (versión 1 y versión 2)

Esta carpeta se llena al ejecutar `agente/pricex2_agente.ipynb` en Google Colab con una clave de Gemini:

- `llamadas.jsonl`: cada consulta al modelo, con el agente que la hizo y la respuesta completa.
- `respuestas_v1_*.jsonl` y `respuestas_v2_*.jsonl`: el registro de cada pedido, variante y conversación. Los de la v2 traen la traza de cada agente.
- `evaluacion_v1_*.csv` y `evaluacion_v2_*.csv`: la comparación con la clave, caso por caso.
- `comparacion_pedidos.csv`, `comparacion_variantes.csv` y `comparacion_conversaciones.csv`: las tablas de las tres versiones frente a frente.
- `resumen.json`: los resúmenes, la precisión por campo, lo que hizo cada agente y el costo.

Todavía no hay corrida: los resultados de esta carpeta no se simulan.
