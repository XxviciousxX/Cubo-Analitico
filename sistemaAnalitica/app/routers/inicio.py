"""
Router del Panel Principal (Inicio) para FastAPI.
"""

import os
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from sistemaAnalitica.app.dependencias import requerirUsuarioAutenticado, requerirPermisoPantalla
from sistemaAnalitica.modulos.seguridad import ServicioAutorizacion

router = APIRouter(tags=["Inicio"])
templates = Jinja2Templates(directory="sistemaAnalitica/app/templates")


@router.get("/", response_class=HTMLResponse)
async def mostrarInicio(
    request: Request,
    pagina: int = Query(1, ge=1),
    user: dict = Depends(requerirPermisoPantalla("INICIO"))
):
    """
    Despliega el panel de control principal con listado paginado de vistas autorizadas.
    """
    idUsuario = user.get("idUsuario", 1)
    vistasAutorizadas = ServicioAutorizacion.obtenerVistasPermitidasUsuario(idUsuario)

    tamanoPagina = 10
    totalVistas = len(vistasAutorizadas)
    totalPaginas = max(1, (totalVistas + tamanoPagina - 1) // tamanoPagina)

    if pagina > totalPaginas:
        pagina = totalPaginas

    inicioIdx = (pagina - 1) * tamanoPagina
    finIdx = inicioIdx + tamanoPagina
    vistasPaginadas = vistasAutorizadas[inicioIdx:finIdx]

    return templates.TemplateResponse(
        request=request,
        name="inicio.html",
        context={
            "user": user,
            "vistas": vistasPaginadas,
            "total_vistas": totalVistas,
            "pagina_actual": pagina,
            "total_paginas": totalPaginas,
            "inicio_idx": inicioIdx + 1 if totalVistas > 0 else 0,
            "fin_idx": min(finIdx, totalVistas),
            "ruta_activa": "inicio"
        }
    )
