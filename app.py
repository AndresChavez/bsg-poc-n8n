"""Mil Oficios · proxy del MVP (FastAPI en Vercel).

Esta función es lo único que ve el navegador. Cada vez que alguien pulsa «Enviar consulta» hace, en orden:

  1. Revisa el código de acceso obligatorio de la demo (ACCESS_CODE).
  2. Limita cuántas consultas seguidas puede hacer cada visitante.
  3. Valida el mensaje (entre 3 y 1000 caracteres).
  4. Llama al webhook de n8n con mensaje, session_id y request_id, y espera su respuesta.
  5. Normaliza la respuesta al contrato 4.0 (contrato.py): siempre la misma forma hacia el navegador.
  6. Deja en los registros solo lo mínimo (id, estado, tiempo). Nunca el contenido de los mensajes.

La URL del webhook y su token se leen en el servidor desde variables de entorno y no se envían al navegador.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import time
import uuid
from collections import defaultdict, deque
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from contrato import VERSION, ErrorContrato, normalizar_salida, respuesta_error, validar_peticion

# ----------------------------------------------------------------------------- EDITA AQUÍ
BACKEND = "n8n"                  # etiqueta que muestra la pantalla: n8n | make | langchain
RUTA = "C"                       # ruta del curso que implementa el backend: A | B | R | C | D
ENV_URL = "N8N_WEBHOOK_URL"      # variable de entorno de Vercel con la URL de PRODUCCIÓN del webhook
ENV_TOKEN = "N8N_WEBHOOK_TOKEN"  # secreto obligatorio de Header Auth del webhook
CABECERA_TOKEN = "x-api-key"     # encabezado en que viaja ese secreto: el mismo nombre que pusiste en n8n
MAX_POR_MINUTO = int(os.getenv("MAX_POR_MINUTO", "8"))   # consultas por minuto y por visitante
# -----------------------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("miloficios")
# Las líneas del proxy salen por stdout: en los registros de Vercel lo que sale por stderr se marca como «error».
if not any(getattr(h, "_nimbo", False) for h in log.handlers):
    _salida = logging.StreamHandler(sys.stdout)   # StreamHandler vacía el búfer en cada línea
    _salida._nimbo = True
    _salida.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_salida)
log.propagate = False
# httpx anota en INFO cada URL que llama, y la URL del webhook es un secreto: se silencia
# (httpx2 y httpcore2 son los nombres que usa el SDK de OpenAI en sus versiones nuevas).
for _nombre in ("httpx", "httpcore", "httpx2", "httpcore2"):
    logging.getLogger(_nombre).setLevel(logging.WARNING)

# Se desactiva la documentación automática de FastAPI: esta API es de uso interno de la pantalla.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


# ----------------------------------------------------------------------------- utilidades
def registrar(**campos: Any) -> None:
    """Una línea JSON por solicitud. Nunca incluyas aquí el mensaje del cliente ni la respuesta."""
    log.info(json.dumps(campos, ensure_ascii=False))


def responder(cuerpo: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(cuerpo, status_code=status, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def milisegundos(inicio: float) -> int:
    return int((time.perf_counter() - inicio) * 1000)


def ip_de(request: Request) -> str:
    """IP del visitante. En Vercel llega en x-real-ip / x-forwarded-for."""
    directa = request.headers.get("x-real-ip")
    if directa:
        return directa.strip()
    reenviada = request.headers.get("x-forwarded-for", "")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


# ----------------------------------------------------------------------------- 1. código de acceso
def revisar_acceso(request: Request) -> None:
    esperado = os.getenv("ACCESS_CODE", "").strip()
    if not esperado:
        raise ErrorContrato("sin_configurar", "Configura ACCESS_CODE para la demo con datos reales.", 503)
    recibido = request.headers.get("x-access-code", "").strip()
    if not hmac.compare_digest(recibido.encode(), esperado.encode()):
        raise ErrorContrato("acceso", "El código de acceso no es correcto.", 401, "falta o no coincide x-access-code")


# ----------------------------------------------------------------------------- 2. límite por visitante
# Es un límite «de mejor esfuerzo»: la memoria es de cada instancia de la función, y Vercel puede crear varias.
# Sirve para frenar errores (un bucle, un botón pulsado mil veces), no a un atacante decidido.
_visitas: dict[str, deque] = defaultdict(deque)


def limitar(visitante: str) -> None:
    ahora = time.monotonic()
    marcas = _visitas[visitante]
    while marcas and ahora - marcas[0] > 60:
        marcas.popleft()
    if len(marcas) >= MAX_POR_MINUTO:
        raise ErrorContrato("limite", "Hay demasiadas solicitudes seguidas. Espera un momento y vuelve a intentar.", 429,
                            f"máximo {MAX_POR_MINUTO} por minuto", True)
    marcas.append(ahora)
    if len(_visitas) > 2000:  # no dejar que el diccionario crezca sin límite
        for clave in [k for k, v in _visitas.items() if not v or ahora - v[-1] > 60]:
            del _visitas[clave]


# ----------------------------------------------------------------------------- 3. lectura del cuerpo
async def leer_json(request: Request) -> Any:
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > 16_000:
        raise ErrorContrato("validacion", "La solicitud es demasiado grande.", 413, "cuerpo mayor a 16 KB")
    crudo = await request.body()
    if len(crudo) > 16_000:
        raise ErrorContrato("validacion", "La solicitud es demasiado grande.", 413, "cuerpo mayor a 16 KB")
    try:
        return json.loads(crudo)
    except ValueError:
        raise ErrorContrato("validacion", "Escribe el mensaje del cliente.", 400, "el cuerpo no es JSON") from None


# ----------------------------------------------------------------------------- 4. backend: webhook de n8n
import httpx

TIMEOUT_S = float(os.getenv("BACKEND_TIMEOUT_S", "110"))   # menos que maxDuration (120 s) de vercel.json


def url_webhook() -> str:
    return os.getenv(ENV_URL, "").strip()


def configurado() -> bool:
    return bool(url_webhook() and os.getenv(ENV_TOKEN, "").strip() and os.getenv("ACCESS_CODE", "").strip())


def pista_del_backend(r: httpx.Response, cuerpo: Any) -> str:
    """Una frase corta del propio backend para el detalle del error (nunca HTML ni volcados largos)."""
    if isinstance(cuerpo, dict) and isinstance(cuerpo.get("message"), str):
        texto = cuerpo["message"]
    elif cuerpo is None and not r.text.lstrip().startswith("<"):
        texto = r.text
    else:
        return ""
    texto = " ".join(texto.split())[:100]
    return f" · {texto}" if texto else ""


def interpretar(r: httpx.Response) -> Any:
    """Traduce la respuesta HTTP del webhook a algo que normalizar_salida() entienda, o a un ErrorContrato."""
    try:
        cuerpo = r.json()
    except ValueError:
        cuerpo = None
    if r.status_code < 300:
        if cuerpo is None:
            texto = r.text.strip()[:60]
            pista = "el cuerpo no es JSON" if texto == "Accepted" else f"el cuerpo no es JSON: {texto!r}"
            raise ErrorContrato("respuesta_invalida", "El backend respondió, pero no con JSON.", 502, pista)
        return cuerpo
    if isinstance(cuerpo, dict) and cuerpo.get("ok") is False:
        return cuerpo  # el flujo informó su propio error con la forma del contrato: se respeta
    codigo = r.status_code
    pista = pista_del_backend(r, cuerpo)
    if codigo in (401, 403):
        raise ErrorContrato("backend_acceso", "El backend rechazó las credenciales del servicio.", 502, f"HTTP {codigo}{pista}")
    if codigo == 404:
        prueba = " · es la URL de PRUEBA: usa la de producción" if "webhook-test" in url_webhook() else ""
        raise ErrorContrato("backend_url", "No se encontró el webhook en la URL configurada.", 502, f"HTTP 404{prueba}{pista}")
    if codigo == 429:
        raise ErrorContrato("limite", "El backend recibió demasiadas solicitudes seguidas.", 429, f"HTTP 429{pista}", True)
    if codigo >= 500 and "timed out" in pista.lower():
        raise ErrorContrato("timeout", "El flujo tardó demasiado y la plataforma lo canceló.", 504, f"HTTP {codigo}{pista}", True)
    raise ErrorContrato("backend", "El backend no respondió correctamente.", 502, f"HTTP {codigo}{pista}", codigo >= 500)


async def llamar_backend(peticion: dict) -> Any:
    url = url_webhook()
    if not configurado():
        raise ErrorContrato("sin_configurar", f"Configura {ENV_URL}, {ENV_TOKEN} y ACCESS_CODE en el servidor.", 503,
                            f"define {ENV_URL} y vuelve a desplegar")
    if not url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        raise ErrorContrato("sin_configurar", f"{ENV_URL} debe empezar con https://", 503, "la URL no empieza con https://")
    cabeceras = {"Content-Type": "application/json", "Accept": "application/json"}
    token = os.getenv(ENV_TOKEN, "").strip()
    if token:
        cabeceras[CABECERA_TOKEN] = token
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUT_S, connect=10.0)) as cliente:
            respuesta = await cliente.post(url, json=peticion, headers=cabeceras)
    except httpx.TimeoutException:
        raise ErrorContrato("timeout", "El backend tardó demasiado en responder.", 504, f"sin respuesta en {int(TIMEOUT_S)} s", True) from None
    except httpx.HTTPError as e:
        raise ErrorContrato("backend", "No se pudo conectar con el backend.", 502, type(e).__name__, True) from None
    return interpretar(respuesta)


# ----------------------------------------------------------------------------- rutas
@app.get("/api/health")
async def salud() -> JSONResponse:
    """La pantalla pregunta aquí si hay backend y si pide código. No revela ningún secreto."""
    return responder({"ok": True, "version": VERSION, "backend": BACKEND, "ruta": RUTA,
                      "configurado": configurado(), "requiere_codigo": True})


@app.post("/api/triage")
async def triage(request: Request) -> JSONResponse:
    inicio = time.perf_counter()
    id_solicitud = uuid.uuid4().hex[:8]
    try:
        revisar_acceso(request)
        limitar(ip_de(request))
        peticion = validar_peticion(await leer_json(request))
        crudo = await llamar_backend(peticion)
        resultado = normalizar_salida(crudo, backend=BACKEND, ruta=RUTA)
        if any(resultado["meta"].get(k) != peticion[k] for k in ("session_id", "request_id")):
            raise ErrorContrato("respuesta_invalida", "La respuesta pertenece a otra sesión o mensaje.", 502)
        resultado["meta"]["latencia_ms"] = milisegundos(inicio)
        resultado["meta"]["id"] = id_solicitud
        registrar(id=id_solicitud, backend=BACKEND, ok=True, ms=resultado["meta"]["latencia_ms"])
        return responder(resultado)
    except ErrorContrato as e:
        registrar(id=id_solicitud, backend=BACKEND, ok=False, codigo=e.codigo, ms=milisegundos(inicio))
        return responder(respuesta_error(e, id_solicitud, BACKEND), e.status)
    except Exception as e:  # noqa: BLE001  nunca se le devuelve al navegador un traceback
        registrar(id=id_solicitud, backend=BACKEND, ok=False, codigo="backend", error=type(e).__name__, ms=milisegundos(inicio))
        error = ErrorContrato("backend", "Error inesperado en la función de Vercel.", 500, type(e).__name__)
        return responder(respuesta_error(error, id_solicitud, BACKEND), 500)


# En tu computador no hay CDN que sirva la carpeta public/, así que la servimos nosotros.
# En Vercel (variable VERCEL definida) esto no se ejecuta: public/ sale directo de la red de Vercel.
if not os.getenv("VERCEL"):
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    _public = Path(__file__).parent / "public"
    if _public.is_dir():
        app.mount("/", StaticFiles(directory=str(_public), html=True), name="public")
