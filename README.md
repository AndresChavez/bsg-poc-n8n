# Mil Oficios · Consultas

Interfaz sencilla: el operador escribe un mensaje, la API lo envía al agente de n8n y muestra su respuesta. Búsqueda de cliente, historial, detalle y políticas. No hay creación, matching ni respuestas de ejemplo.

La búsqueda identifica registros por teléfono o por tipo y número de documento. El historial utiliza el customerId obtenido; el detalle admite un service_request_code directo o una referencia inequívoca del historial. El acceso corresponde a un operador autorizado: buscar un registro no autentica la identidad de su titular.

## Ejecutar localmente

Python 3.12. Desde esta carpeta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-local.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
# Configurar N8N_WEBHOOK_URL, N8N_WEBHOOK_TOKEN y ACCESS_CODE en .env
.\.venv\Scripts\python.exe -m uvicorn app:app --env-file .env --host 127.0.0.1 --port 8000
```

Abrir http://localhost:8000. Introducir el código de acceso y una consulta. Los cuatro botones solo ayudan a redactar el mensaje; no contienen registros reales ni resultados pregrabados.

## Contrato 4.0

POST /api/triage:

```json
{"mensaje":"¿Qué condiciones aplican a las visitas técnicas?","session_id":"11111111-1111-4111-8111-111111111111","request_id":"22222222-2222-4222-8222-222222222222"}
```

La cabecera x-access-code contiene el código de la demo. La API valida ese código antes de llamar a n8n, reenvía el mismo cuerpo con x-api-key y espera:

```json
{"ok":true,"respuesta":"Respuesta textual del agente","meta":{"session_id":"11111111-1111-4111-8111-111111111111","request_id":"22222222-2222-4222-8222-222222222222","execution_id":"ID de ejecución de n8n"}}
```

No se reenvía al navegador el JSON crudo de clientes o servicios, ni la memoria, argumentos u observaciones de herramientas. La UI interpreta Markdown del agente con Marked y sanea el HTML con DOMPurify antes de insertarlo. Los mensajes del usuario y los errores se muestran como texto plano. Mantiene la conversación únicamente en memoria de la pestaña; sessionStorage guarda solo el UUID de sesión. Nueva conversación cambia ese UUID. Recargar puede conservar el contexto en n8n pero limpia el historial visible.

## Publicar

Esta carpeta es la raíz del proyecto en Vercel. Importar el repositorio y utilizar Framework Preset FastAPI y Root Directory ./; conservar los valores de compilación y salida predeterminados del framework. Python 3.12 queda indicado en .python-version y vercel.json configura un máximo de 120 segundos.

Antes de desplegar, configurar las tres variables privadas del entorno Production:

| Variable | Valor |
|---|---|
| N8N_WEBHOOK_URL | URL HTTPS de producción del webhook de n8n. |
| N8N_WEBHOOK_TOKEN | Secreto de la credencial Header Auth cuya cabecera es x-api-key. |
| ACCESS_CODE | Código de acceso para el operador de la demo. |

Volver a desplegar después de cambiar las variables. El archivo .env local no se publica ni se utiliza como configuración del despliegue. La clave del modelo y la autenticación a las APIs de Mil Oficios permanecen en n8n. .gitignore excluye los archivos privados de Git y .vercelignore excluye configuración local, entornos y pruebas del despliegue.

/api/health informa configuración, no garantiza que n8n o sus APIs estén respondiendo. La conexión real solo queda comprobada después de enviar una consulta y revisar su ejecución.

Para verificar el despliegue, abrir /api/health: configurado=true confirma que están presentes las tres variables. Después enviar una consulta sobre políticas desde la interfaz y comprobar su ejecución en n8n; esta consulta confirma el recorrido completo.

### Configuración de n8n

Los exports JSON se entregan por separado. El workflow principal debe tener un Webhook POST con ruta mil-oficios, Header Auth y respuesta mediante Respond to Webhook. El valor de su credencial x-api-key debe coincidir con N8N_WEBHOOK_TOKEN. Utilizar su Production URL y publicar la versión correspondiente.

Las herramientas del agente deben seleccionar los subworkflows correctos:

| Herramienta | Entradas |
|---|---|
| buscar_cliente | phone, documentType, documentNumber |
| consultar_historial_servicios | customerId y los mismos criterios phone o documentType + documentNumber |
| consultar_detalle_servicio | service_request_code |
| buscar_politicas | Consulta textual; contenido cargado en el nodo |

En cada subworkflow, conservar el trigger When Executed by Another Workflow y configurar la referencia al workflow de autenticación existente. Historial también debe apuntar al workflow Buscar Cliente en Revalidar cliente. Configurar las credenciales del modelo y publicar las versiones utilizadas por las herramientas.

La interfaz y el proxy de este repositorio se despliegan juntos; el agente, la memoria y las credenciales de las APIs permanecen en n8n.

Documentación oficial: [FastAPI en Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [exclusiones de despliegue](https://vercel.com/docs/deployments/vercel-ignore).

## Formato de las respuestas

Se admiten negritas, cursivas, listas, títulos, citas, código, tablas y enlaces HTTP/HTTPS o mailto. Se permite únicamente una lista limitada de etiquetas y atributos; se eliminan scripts, manejadores de eventos, imágenes, iframes, formularios y estilos enviados por el agente. Los enlaces se abren con noopener/noreferrer. Si faltan las librerías, se conserva el texto original. Las dependencias se sirven desde public/vendor/, con versiones, integridad y licencias incluidas; no se usa un CDN en ejecución.

Para repetir las 24 comprobaciones de Markdown y saneamiento, abrir tests/markdown.html en el navegador. La página solo usa datos ficticios y no consulta n8n.

## Pruebas de API

Con las dependencias instaladas:

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_api.py" -v
~~~

Son 12 pruebas locales con respuestas controladas. No leen .env ni llaman a n8n. Comprueban acceso, validación, correspondencia de sesión, reenvío, contrato y manejo de errores. Las pruebas locales no acreditan el comportamiento del agente real ni las cuatro pruebas públicas requeridas para la entrega.

## Datos de la demostración

La integración puede consultar APIs reales. Para la evaluación del curso utilizar datos sintéticos o anonimizados. No incorporar al repositorio credenciales, respuestas de clientes ni capturas con datos personales.
