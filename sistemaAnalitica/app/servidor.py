"""
Servidor web principal FastAPI para el Sistema Analítico y Cubos de Autoservicio.
Uniformizado con la arquitectura, estilos y manejo de errores de Knowledge Base.
"""

import os
import sys
import traceback
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

# Garantizar resolución de rutas
directorioActual = os.path.dirname(os.path.abspath(__file__))
directorioRaiz = os.path.abspath(os.path.join(directorioActual, "..", ".."))
if directorioRaiz not in sys.path:
    sys.path.insert(0, directorioRaiz)

from sistemaAnalitica.modulos.seguridad.baseDatos import inicializarBaseDatos
from sistemaAnalitica.modulos.seguridad.gestorLogs import GestorLogsSistema
from sistemaAnalitica.app.routers.autenticacion import router as routerAutenticacion
from sistemaAnalitica.app.routers.inicio import router as routerInicio
from sistemaAnalitica.app.routers.ingesta import router as routerIngesta
from sistemaAnalitica.app.routers.explorador import router as routerExplorador
from sistemaAnalitica.app.routers.seguridad import router as routerSeguridad
from sistemaAnalitica.app.routers.configuracionVistas import enrutador as routerConfiguracionVistas
from sistemaAnalitica.app.routers.administracion import router as routerAdministracion
from sistemaAnalitica.app.routers.baseDatosRouter import router as routerBaseDatos

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="Cubix | Inteligencia Analítica y Cubos OLAP",
    description="Plataforma analítica OLAP multipágina con DuckDB, Parquet y Tailwind CSS",
    version="2.0.0"
)

import time
from sistemaAnalitica.app.dependencias import (
    NOMBRE_COOKIE_SESION,
    deserializarSesionUsuario,
    serializarSesionUsuario
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def renovarSesionDeslizanteMiddleware(request: Request, call_next):
    """
    Middleware para ventana deslizante de sesión:
    Si el usuario tiene una sesión activa y han pasado más de 60 segundos
    desde su último acceso registrado, actualiza el timestamp en la cookie
    para evitar que expire mientras el usuario trabaja activamente.
    """
    tokenCookie = request.cookies.get(NOMBRE_COOKIE_SESION)
    nuevoToken = None

    if tokenCookie and request.url.path not in ["/logout", "/login"]:
        datosUsuario = deserializarSesionUsuario(tokenCookie)
        if datosUsuario:
            ahora = int(time.time())
            ultimoAcceso = datosUsuario.get("ultimo_acceso", 0)
            if ahora - ultimoAcceso >= 60:
                datosUsuario["ultimo_acceso"] = ahora
                nuevoToken = serializarSesionUsuario(datosUsuario)

    response = await call_next(request)

    if nuevoToken and request.url.path != "/logout":
        location = response.headers.get("Location", "")
        if "/login" not in location:
            response.set_cookie(
                key=NOMBRE_COOKIE_SESION,
                value=nuevoToken,
                httponly=True,
                max_age=86400,
                samesite="lax"
            )

    return response

# Montar directorio de recursos estáticos (logos, favicons, estilos)
directorioEstatico = os.path.join(directorioActual, "static")
os.makedirs(directorioEstatico, exist_ok=True)
app.mount("/static", StaticFiles(directory=directorioEstatico), name="static")

templates = Jinja2Templates(directory="sistemaAnalitica/app/templates")

# Registro de routers por módulo
app.include_router(routerAutenticacion)
app.include_router(routerInicio)
app.include_router(routerIngesta)
app.include_router(routerExplorador)
app.include_router(routerSeguridad)
app.include_router(routerConfiguracionVistas)
app.include_router(routerAdministracion)
app.include_router(routerBaseDatos)


from sistemaAnalitica.modulos.motorAnalitico.servicioPersistenciaCubos import ServicioPersistenciaCubos


@app.on_event("startup")
def inicializarAplicacion():
    """
    Inicializa la base de datos relacional, asegura migraciones de esquema
    y auto-restaura los cubos Parquet desde Supabase al disco local del contenedor.
    """
    inicializarBaseDatos()
    ServicioPersistenciaCubos.sincronizarTodosLosCubos()


# ----------------- MANEJADOR GLOBAL DE ERRORES Y PÁGINA DEDICADA -----------------

@app.exception_handler(StarletteHTTPException)
@app.exception_handler(HTTPException)
async def manejadorExcepcionesHttp(request: Request, exc: StarletteHTTPException):
    """
    Gestiona errores HTTP (404, 401, 403) renderizando la plantilla visual de error.
    """
    if "api" in request.url.path:
        return JSONResponse(status_code=exc.status_code, content={"detalle": exc.detail})

    titulos = {
        404: "Página o Recurso No Encontrado",
        403: "Acceso Restringido o Denegado",
        401: "Autenticación Requerida",
        500: "Error Interno del Servidor"
    }

    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "codigo_estado": exc.status_code,
            "titulo_error": titulos.get(exc.status_code, "Aviso del Sistema"),
            "mensaje_error": exc.detail if isinstance(exc.detail, str) else "Ha ocurrido un problema al procesar la solicitud.",
            "detalle_tecnico": None
        },
        status_code=exc.status_code
    )


@app.exception_handler(RequestValidationError)
async def manejadorValidacionPydantic(request: Request, exc: RequestValidationError):
    """
    Captura fallos de validación de esquemas Pydantic y los registra en la tabla logs_sistema.
    """
    errores = exc.errors()
    detalleStr = str(errores)
    try:
        GestorLogsSistema.registrarError(
            capa="FastAPI Validación",
            metodo=f"{request.method} {request.url.path}",
            error=f"Errores de esquema Pydantic: {detalleStr}"
        )
    except Exception:
        pass

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detalle": errores, "mensaje": "Parámetros de solicitud no válidos según el contrato de esquema."}
    )


@app.exception_handler(Exception)
async def manejadorExcepcionesGenerales(request: Request, exc: Exception):
    """
    Captura fallos inesperados y despliega la página de errores corporativa sin romper la interfaz.
    Registra automáticamente el error en la tabla logs_sistema de SQL Server.
    """
    tbStr = traceback.format_exc()
    try:
        GestorLogsSistema.registrarError(
            capa="FastAPI Servidor",
            metodo=f"{request.method} {request.url.path}",
            error=f"{type(exc).__name__}: {str(exc)}\n\n{tbStr}"
        )
    except Exception:
        pass

    if "api" in request.url.path:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detalle": "Error interno del servidor.", "error": str(exc)}
        )

    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "codigo_estado": 500,
            "titulo_error": "Error Inesperado del Sistema",
            "mensaje_error": "Se ha presentado una anomalía en el procesamiento. La traza fue registrada para auditoría.",
            "detalle_tecnico": f"{type(exc).__name__}: {str(exc)}\n\n{tbStr}"
        },
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
