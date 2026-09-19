"""
Router de autenticación para FastAPI: login, validación multi-estrategia y logout.
"""

import time
from typing import Optional
from fastapi import APIRouter, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sistemaAnalitica.modulos.autenticacion.gestorAutenticacion import GestorAutenticacion
from sistemaAnalitica.app.dependencias import (
    serializarSesionUsuario, obtenerUsuarioActual, NOMBRE_COOKIE_SESION
)

router = APIRouter(tags=["Autenticación"])
templates = Jinja2Templates(directory="sistemaAnalitica/app/templates")
gestorAutenticacion = GestorAutenticacion()


@router.get("/login", response_class=HTMLResponse)
async def mostrarLogin(request: Request):
    """
    Despliega la pantalla de acceso o redirige a inicio si ya existe sesión válida.
    """
    usuarioExistente = obtenerUsuarioActual(request)
    if usuarioExistente:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    avisoInactividad = None
    if request.query_params.get("inactividad"):
        avisoInactividad = "Tu sesión ha expirado automáticamente tras 20 minutos de inactividad por motivos de seguridad. Por favor, ingresa tus credenciales nuevamente."

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None, "aviso": avisoInactividad}
    )


@router.post("/login")
async def procesarLogin(
    request: Request,
    usuario: str = Form(...),
    clave: str = Form(...),
    estrategia: str = Form("LOCAL")
):
    """
    Valida credenciales utilizando la estrategia seleccionada y emite cookie segura.
    """
    # Validación exclusiva por base de datos
    gestorAutenticacion.asignarEstrategia("LOCAL")
    perfilUsuario = gestorAutenticacion.autenticarUsuario(usuario.strip(), clave)

    if not perfilUsuario:
        errorMsg = f"Usuario o contraseña incorrectos para '{usuario}'."
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": errorMsg, "aviso": None},
            status_code=status.HTTP_401_UNAUTHORIZED
        )

    # Asegurar timestamp de último acceso y serializar sesión
    perfilUsuario["ultimo_acceso"] = int(time.time())
    tokenSesion = serializarSesionUsuario(perfilUsuario)
    respuesta = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    respuesta.set_cookie(
        key=NOMBRE_COOKIE_SESION,
        value=tokenSesion,
        httponly=True,
        max_age=86400,  # 24 horas
        samesite="lax"
    )
    return respuesta


@router.get("/logout")
async def cerrarSesion():
    """
    Purga la cookie de sesión y redirige a la pantalla de acceso.
    """
    respuesta = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    respuesta.delete_cookie(NOMBRE_COOKIE_SESION)
    return respuesta
