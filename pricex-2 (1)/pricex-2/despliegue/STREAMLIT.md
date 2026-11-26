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

La página tiene dos pestañas: *Asistente* y *Tablero*. El tablero se actualiza con cada mensaje y se puede filtrar por todos los visitantes, por tu conversación o por las pruebas grabadas. En las pruebas grabadas se elige la versión (sin IA, v1 o v2) y la corrida con Gemini (1 o 2), y aparecen dos preguntas más: *¿Qué tan bien elige?*, con los aciertos y errores graves contra la respuesta correcta, y *¿Qué cambió entre corridas?*, con el antes y el después de cada versión. Abajo tiene la tabla de datos y un botón para descargarlos en CSV.

Sin más configuración, los datos de los visitantes viven en la memoria de la app y se borran cuando se duerme o se reinicia. Para conservarlos, conecta una hoja de Google Sheets.

## Guardar el uso en Google Sheets

Con la hoja conectada, cada mensaje queda como una fila con las mismas columnas del CSV, y al despertar, la página la vuelve a leer. La hoja se abre directo en Power BI o en Excel. Solo guarda datos estructurados, nunca el texto que escriben las personas. Todo es gratis.

1. **Crea la hoja.** En [sheets.new](https://sheets.new) crea una hoja vacía, ponle de nombre «PriceX 2.0: uso» y copia su enlace.
2. **Crea un proyecto en Google Cloud.** En [console.cloud.google.com](https://console.cloud.google.com), arriba, elige *Seleccionar proyecto → Proyecto nuevo*, ponle `pricex-2` y créalo.
3. **Activa la API de Google Sheets.** Con ese proyecto elegido, ve a *APIs y servicios → Biblioteca*, busca «Google Sheets API» y haz clic en **Habilitar**.
4. **Crea la cuenta de servicio.** Es un usuario robot que va a escribir en la hoja. Ve a *APIs y servicios → Credenciales → Crear credenciales → Cuenta de servicio*, ponle `pricex-hoja`, haz clic en **Crear y continuar** y luego en **Listo** (no necesita roles).
5. **Descarga su llave.** Abre la cuenta de servicio que creaste, entra a la pestaña *Claves* y elige *Agregar clave → Crear clave nueva → JSON*. Se descarga un archivo `.json`. Trátalo como una contraseña: no lo subas a GitHub ni lo muestres en pantallazos.
6. **Comparte la hoja con el robot.** Abre el archivo `.json` con el Bloc de notas, copia el correo que aparece en `client_email` (termina en `iam.gserviceaccount.com`), y en la hoja haz clic en **Compartir**, pega ese correo y déjalo como **Editor**.
7. **Agrega dos secretos en Streamlit.** En la app, entra a *Settings → Secrets* y, debajo de lo que ya tienes, pega esto con tu enlace y todo el contenido del archivo `.json` entre las comillas triples:

   ```toml
   HOJA_DE_USO_URL = "https://docs.google.com/spreadsheets/d/.../edit"
   HOJA_DE_USO_CUENTA = '''
   { pega aquí todo el contenido del archivo .json, tal cual }
   '''
   ```

8. **Guarda y comprueba.** La app se reinicia sola. En la pestaña *Tablero* debe decir: «Los mensajes de los visitantes quedan guardados en una hoja de Google Sheets». Escribe un pedido y revisa que aparezca una fila nueva en la hoja.

Si algo queda mal configurado, la página sigue funcionando y el tablero dice qué falló.

## Bueno saber

- Si nadie la visita en unas horas, la página se duerme. El primer visitante la despierta con un clic y tarda alrededor de un minuto.
- Los contadores viven en la memoria de la app: se reinician cada día y cuando la app se reinicia.
- Para probarla en tu computador: `pip install -r requirements.txt`, copia `.streamlit/secrets.toml.ejemplo` como `.streamlit/secrets.toml` con tu clave, y ejecuta `streamlit run app.py`.
- Antes de publicar un cambio: `python3 pruebas/prueba_app_streamlit.py` corre la página con un Streamlit falso y revisa que la lógica no falle.
