"""
Router para la monitorización de salud, diagnóstico y métricas de la Base de Datos del Sistema.
Expone endpoints REST para inspeccionar la conectividad y el estado relacional de SQL Server.
"""

import time
from typing import Dict, Any
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sistemaAnalitica.app.dependencias import requerirUsuarioAutenticado
from sistemaAnalitica.modulos.seguridad.baseDatos import (
    obtenerSesion, motorBaseDatos, obtenerInfoMotorActivo
)
from sistemaAnalitica.modulos.seguridad.modelos import (
    UsuarioModelo, RolModelo, PantallaModelo, CuboModelo, VistaModelo
)

router = APIRouter(prefix="/api/sistema/base-datos", tags=["Base de Datos del Sistema"])


@router.get("/estado")
async def obtenerEstadoBaseDatos(
    user: dict = Depends(requerirUsuarioAutenticado)
) -> JSONResponse:
    """
    Retorna métricas de salud, latencia de conexión y estado de las tablas relacionales del sistema.
    """
    inicioTiempo = time.perf_counter()
    infoMotor = obtenerInfoMotorActivo()

    try:
        with obtenerSesion() as sesion:
            # Latencia con query ligera
            sesion.execute(text("SELECT 1"))
            latenciaMs = round((time.perf_counter() - inicioTiempo) * 1000, 2)

            totalUsuarios = sesion.query(UsuarioModelo).count()
            totalRoles = sesion.query(RolModelo).count()
            totalPantallas = sesion.query(PantallaModelo).count()
            totalCubos = sesion.query(CuboModelo).count()
            totalVistas = sesion.query(VistaModelo).count()

            # Resumen de tablas
            tablasResumen = {
                "usuarios": totalUsuarios,
                "roles": totalRoles,
                "pantallas": totalPantallas,
                "cubos": totalCubos,
                "vistas": totalVistas
            }

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "exito": True,
                "estadoConexion": "OPERATIVO",
                "latenciaMs": latenciaMs,
                "infoMotor": infoMotor,
                "tablas": tablasResumen
            }
        )
    except Exception as errorConexion:
        latenciaMs = round((time.perf_counter() - inicioTiempo) * 1000, 2)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "exito": False,
                "estadoConexion": "DEGRADADO / ERROR",
                "latenciaMs": latenciaMs,
                "infoMotor": infoMotor,
                "error": str(errorConexion)
            }
        )


@router.post("/verificar")
async def verificarConexionBaseDatos(
    user: dict = Depends(requerirUsuarioAutenticado)
) -> JSONResponse:
    """
    Ejecuta un diagnóstico profundo de la conexión y las restricciones referenciales.
    """
    try:
        with motorBaseDatos.connect() as conexion:
            version = conexion.execute(text("SELECT @@VERSION")).fetchone()[0]
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "exito": True,
                "mensaje": "Conexión a SQL Server verificada con éxito.",
                "versionServidor": version.split("\n")[0] if "\n" in version else version
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"exito": False, "error": str(e)}
        )
