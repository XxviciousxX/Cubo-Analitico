"""
Router de gobernanza, roles y usuarios para FastAPI.
Implementa gestión multipestaña:
1. Usuarios y Roles
2. Vistas por Rol
3. Pantallas por Rol
4. Excepciones de Vistas por Usuario
5. Excepciones de Pantallas por Usuario
"""

from typing import List, Optional
from fastapi import APIRouter, Request, Depends, Body, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from sistemaAnalitica.app.dependencias import requerirUsuarioAutenticado, requerirPermisoPantalla
from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import (
    UsuarioModelo, RolModelo, PermisoModelo, VistaModelo, PantallaModelo,
    ExcepcionUsuarioModelo, ExcepcionPantallaUsuarioModelo
)
from sistemaAnalitica.modulos.seguridad import ServicioAutorizacion

router = APIRouter(tags=["Seguridad"])
templates = Jinja2Templates(directory="sistemaAnalitica/app/templates")


from sqlalchemy.orm import joinedload

@router.get("/seguridad", response_class=HTMLResponse)
async def mostrarSeguridad(
    request: Request,
    user: dict = Depends(requerirPermisoPantalla("SEGURIDAD"))
):
    """
    Despliega la administración de gobernanza, roles, asignación de pantallas/vistas
    y matrices de excepciones por usuario.
    """
    with obtenerSesion() as sesion:
        usuarios = sesion.query(UsuarioModelo).options(joinedload(UsuarioModelo.rol)).all()
        roles = sesion.query(RolModelo).options(
            joinedload(RolModelo.usuarios),
            joinedload(RolModelo.vistas),
            joinedload(RolModelo.pantallas)
        ).filter_by(activo=True).all()
        permisos = sesion.query(PermisoModelo).all()
        vistas = sesion.query(VistaModelo).filter_by(activo=True).all()
        pantallas = sesion.query(PantallaModelo).filter_by(activo=True).order_by(PantallaModelo.orden).all()
        excepcionesVistas = sesion.query(ExcepcionUsuarioModelo).options(
            joinedload(ExcepcionUsuarioModelo.usuario).joinedload(UsuarioModelo.rol),
            joinedload(ExcepcionUsuarioModelo.vista)
        ).all()
        excepcionesPantallas = sesion.query(ExcepcionPantallaUsuarioModelo).options(
            joinedload(ExcepcionPantallaUsuarioModelo.usuario).joinedload(UsuarioModelo.rol),
            joinedload(ExcepcionPantallaUsuarioModelo.pantalla)
        ).all()

        # Construir matriz de vistas por rol: { idRol: [idVista, ...] }
        matrizVistasPorRol = {r.idRol: [v.idVista for v in r.vistas] for r in roles}
        matrizPantallasPorRol = {r.idRol: [p.idPantalla for p in r.pantallas] for r in roles}

    return templates.TemplateResponse(
        request=request,
        name="seguridad.html",
        context={
            "user": user,
            "usuarios": usuarios,
            "roles": roles,
            "permisos": permisos,
            "vistas": vistas,
            "pantallas": pantallas,
            "excepciones_vistas": excepcionesVistas,
            "excepciones_pantallas": excepcionesPantallas,
            "matriz_vistas_rol": matrizVistasPorRol,
            "matriz_pantallas_rol": matrizPantallasPorRol,
            "ruta_activa": "seguridad"
        }
    )


# ---------------- API REST DE GOBERNANZA Y ASIGNACIÓN ----------------

@router.post("/api/seguridad/roles/{idRol}/vistas")
async def actualizarVistasDeRol(
    idRol: int,
    user: dict = Depends(requerirPermisoPantalla("SEGURIDAD")),
    datos: dict = Body(...)
):
    """
    Asigna en bloque la lista de vistas/cubos accesibles para un rol.
    """
    idsVistas = datos.get("idsVistas", [])
    try:
        ServicioAutorizacion.asignarVistasARol(idRol, [int(i) for i in idsVistas])
        return JSONResponse({"exito": True, "mensaje": "Vistas del rol actualizadas con éxito."})
    except Exception as err:
        return JSONResponse({"exito": False, "error": str(err)}, status_code=400)


@router.post("/api/seguridad/roles/{idRol}/pantallas")
async def actualizarPantallasDeRol(
    idRol: int,
    user: dict = Depends(requerirPermisoPantalla("SEGURIDAD")),
    datos: dict = Body(...)
):
    """
    Asigna en bloque la lista de pantallas accesibles para un rol.
    """
    idsPantallas = datos.get("idsPantallas", [])
    try:
        ServicioAutorizacion.asignarPantallasARol(idRol, [int(i) for i in idsPantallas])
        return JSONResponse({"exito": True, "mensaje": "Pantallas del rol actualizadas con éxito."})
    except Exception as err:
        return JSONResponse({"exito": False, "error": str(err)}, status_code=400)


@router.post("/api/seguridad/usuarios/{idUsuario}/excepciones-vista")
async def guardarExcepcionVista(
    idUsuario: int,
    user: dict = Depends(requerirPermisoPantalla("SEGURIDAD")),
    datos: dict = Body(...)
):
    """
    Registra o actualiza una excepción de vista (concesión o revocación) para un usuario.
    """
    idVista = int(datos.get("idVista", 0))
    permitido = bool(datos.get("permitido", True))
    motivo = datos.get("motivo", "")

    try:
        ServicioAutorizacion.registrarExcepcionVista(idUsuario, idVista, permitido, motivo)
        return JSONResponse({"exito": True, "mensaje": "Excepción de vista registrada correctamente."})
    except Exception as err:
        return JSONResponse({"exito": False, "error": str(err)}, status_code=400)


@router.delete("/api/seguridad/excepciones-vista/{idExcepcion}")
async def eliminarExcepcionVista(
    idExcepcion: int,
    user: dict = Depends(requerirPermisoPantalla("SEGURIDAD"))
):
    """
    Elimina una regla de excepción de vista.
    """
    eliminado = ServicioAutorizacion.eliminarExcepcionVista(idExcepcion)
    if eliminado:
        return JSONResponse({"exito": True, "mensaje": "Excepción eliminada correctamente."})
    return JSONResponse({"exito": False, "error": "Excepción no encontrada."}, status_code=404)


@router.post("/api/seguridad/usuarios/{idUsuario}/excepciones-pantalla")
async def guardarExcepcionPantalla(
    idUsuario: int,
    user: dict = Depends(requerirPermisoPantalla("SEGURIDAD")),
    datos: dict = Body(...)
):
    """
    Registra o actualiza una excepción de pantalla (concesión o revocación) para un usuario.
    """
    idPantalla = int(datos.get("idPantalla", 0))
    permitido = bool(datos.get("permitido", True))
    motivo = datos.get("motivo", "")

    try:
        ServicioAutorizacion.registrarExcepcionPantalla(idUsuario, idPantalla, permitido, motivo)
        return JSONResponse({"exito": True, "mensaje": "Excepción de pantalla registrada correctamente."})
    except Exception as err:
        return JSONResponse({"exito": False, "error": str(err)}, status_code=400)


@router.delete("/api/seguridad/excepciones-pantalla/{idExcepcion}")
async def eliminarExcepcionPantalla(
    idExcepcion: int,
    user: dict = Depends(requerirPermisoPantalla("SEGURIDAD"))
):
    """
    Elimina una regla de excepción de pantalla.
    """
    eliminado = ServicioAutorizacion.eliminarExcepcionPantalla(idExcepcion)
    if eliminado:
        return JSONResponse({"exito": True, "mensaje": "Excepción eliminada correctamente."})
    return JSONResponse({"exito": False, "error": "Excepción no encontrada."}, status_code=404)

