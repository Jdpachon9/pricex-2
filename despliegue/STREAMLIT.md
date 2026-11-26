# Publicar la página en vivo (Streamlit Community Cloud)

La página `app.py` deja que cualquier persona con el enlace converse con el equipo de agentes sobre el catálogo simulado. Se publica gratis en Streamlit Community Cloud, que la toma directamente de tu repositorio de GitHub.

## Lo que necesitas

- El proyecto subido a GitHub como repositorio **público**, con `app.py`, `requirements.txt` y la carpeta `.streamlit` en la raíz.
- Tu clave de Gemini (la misma del cuaderno).

## Pasos

1. Entra a [share.streamlit.io](https://share.streamlit.io) con tu cuenta de GitHub y autoriza el acceso.
2. Arriba a la derecha, haz clic en **Create app** y luego en **Yup, I have an app**.
3. Llena los datos: el repositorio (`tu-usuario/pricex-2`), la rama (`main`) y el archivo principal (`app.py`). En **App URL** puedes escoger el nombre del enlace, por ejemplo `pricex-2`.
4. Haz clic en **Advanced settings**. Escoge Python 3.12 y, en **Secrets**, pega esto con tu clave real:

   ```toml
   GEMINI_API_KEY = "tu-clave"
   MODELO = "gemini-3.5-flash-lite"
   MAX_MENSAJES_DIA = 300
   REPO_URL = "https://github.com/tu-usuario/pricex-2"
   ```

5. Haz clic en **Deploy**. En unos minutos la página queda en `https://pricex-2.streamlit.app` (o el nombre que escogiste).

La clave queda guardada en Streamlit, no en el repositorio. Si algún día la cambias, actualízala en la configuración de la app (**Settings > Secrets**).

## Cómo se protege la clave y la cuota

| Riesgo | Qué hace la página |
|---|---|
| Alguien escribe sin parar | Máximo 20 mensajes con IA por visita y 300 por día entre todos (`MAX_MENSAJES_DIA`). Después sigue funcionando sin IA |
| Se acaba la cuota gratuita de Gemini | Al primer aviso de cuota agotada deja de consultar el modelo ese día y atiende la versión sin IA |
| El modelo no responde | Cada agente que falla se salta y la respuesta sale igual: intérprete sin IA y mensaje de plantilla |
| La misma pregunta muchas veces | Las consultas repetidas (por ejemplo, los botones de ejemplo) salen de una memoria temporal y no gastan cuota |
| Datos personales | Tarjetas, correos y teléfonos se tapan antes de llegar al modelo y también en pantalla. La página avisa que en el plan gratuito Google puede usar los mensajes para mejorar sus productos |

## El tablero

La página tiene dos pestañas: *Asistente* y *Tablero*. El tablero se actualiza con cada mensaje y se puede filtrar por todos los visitantes, por tu conversación o por las pruebas grabadas (sin IA y, cuando agregues `resultados/gemini`, v1 y v2). Abajo tiene la tabla de datos y un botón para descargarlos en CSV.

Los datos de los visitantes viven en la memoria de la app y en un archivo temporal: duran mientras la app está despierta y se borran cuando se duerme o se reinicia. Si quieres conservarlos, descarga el CSV antes. Guardarlos de forma permanente necesita una base de datos externa: queda como siguiente paso.

## Bueno saber

- Si nadie la visita en unas horas, la página se duerme. El primer visitante la despierta con un clic y tarda alrededor de un minuto.
- Los contadores viven en la memoria de la app: se reinician cada día y cuando la app se reinicia.
- Para probarla en tu computador: `pip install -r requirements.txt`, copia `.streamlit/secrets.toml.ejemplo` como `.streamlit/secrets.toml` con tu clave, y ejecuta `streamlit run app.py`.
- Antes de publicar un cambio: `python3 pruebas/prueba_app_streamlit.py` corre la página con un Streamlit falso y revisa que la lógica no falle.
