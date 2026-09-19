"""
Servidor MCP (Model Context Protocol) para la Base de Datos del Sistema Analítico.
Permite a los asistentes de IA inspeccionar de forma segura la gobernanza, estado de cubos,
vistas y métricas del catálogo relacional activo (SQL Server o SQLite).
"""

import os
import sys
import time
from typing import Dict, Any, List, Optional
from mcp.server.mcpserver import MCPServer
from sqlalchemy import text

# Asegurar importaciones del proyecto
directorioActual = os.path.dirname(os.path.abspath(__file__))
directorioRaiz = os.path.abspath(os.path.join(directorioActual, "..", "..", ".."))
if directorioRaiz not in sys.path:
    sys.path.insert(0, directorioRaiz)

from sistemaAnalitica.modulos.seguridad.baseDatos import (
    obtenerSesion, motorBaseDatos, obtenerInfoMotorActivo
)
from sistemaAnalitica.modulos.seguridad.modelos import (
    UsuarioModelo, RolModelo, PantallaModelo, CuboModelo, VistaModelo,
    ExcepcionUsuarioModelo, ExcepcionPantallaUsuarioModelo
)

mcp = MCPServer("cubo-sql-server")


@mcp.tool()
def verificar_conexion_sql() -> Dict[str, Any]:
    """
    Verifica la conectividad con la base de datos relacional activa (SQL Server o SQLite),
    mide la latencia de respuesta y obtiene la versión del motor de base de datos.
    """
    inicio = time.perf_counter()
    info = obtenerInfoMotorActivo()
    try:
        with motorBaseDatos.connect() as conn:
            version = conn.execute(text("SELECT @@VERSION")).fetchone()[0]
            latenciaMs = round((time.perf_counter() - inicio) * 1000, 2)
            return {
                "exito": True,
                "estado": "CONECTADO",
                "latenciaMs": latenciaMs,
                "infoMotor": info,
                "versionServidor": version.split("\n")[0] if "\n" in version else version
            }
    except Exception as e:
        latenciaMs = round((time.perf_counter() - inicio) * 1000, 2)
        return {
            "exito": False,
            "estado": "ERROR_CONEXION",
            "latenciaMs": latenciaMs,
            "infoMotor": info,
            "error": str(e)
        }


@mcp.tool()
def consultar_catalogo_sistema() -> Dict[str, Any]:
    """
    Obtiene un resumen consolidado del catálogo institucional:
    total de usuarios, roles, pantallas activas, cubos OBT y vistas analíticas registradas.
    """
    with obtenerSesion() as sesion:
        usuarios = sesion.query(UsuarioModelo).all()
        roles = sesion.query(RolModelo).all()
        pantallas = sesion.query(PantallaModelo).order_by(PantallaModelo.orden).all()
        cubos = sesion.query(CuboModelo).all()
        vistas = sesion.query(VistaModelo).all()

        return {
            "usuarios": [
                {
                    "idUsuario": u.idUsuario,
                    "nombreUsuario": u.nombreUsuario,
                    "nombreCompleto": u.nombreCompleto,
                    "correo": u.correoElectronico,
                    "rol": u.rol.nombreRol if u.rol else "Sin Rol",
                    "activo": u.activo
                }
                for u in usuarios
            ],
            "roles": [{"idRol": r.idRol, "nombreRol": r.nombreRol, "descripcion": r.descripcion} for r in roles],
            "pantallas": [{"codigo": p.codigoPantalla, "nombre": p.nombrePantalla, "ruta": p.rutaPantalla} for p in pantallas],
            "cubos": [{"idCubo": c.idCubo, "nombre": c.nombreCubo, "origen": c.tipoOrigen, "habilitado": c.estadoHabilitado} for c in cubos],
            "vistas": [{"idVista": v.idVista, "codigo": v.codigoVista, "nombre": v.nombreVista, "habilitada": v.estadoHabilitado} for v in vistas]
        }


@mcp.tool()
def consultar_metricas_cubos() -> List[Dict[str, Any]]:
    """
    Lista todos los cubos analíticos Parquet registrados en la base de datos de control,
    indicando el archivo en disco, tipología de origen, fecha de última carga y estado operativo.
    """
    with obtenerSesion() as sesion:
        cubos = sesion.query(CuboModelo).all()
        resultado = []
        for c in cubos:
            resultado.append({
                "idCubo": c.idCubo,
                "nombreCubo": c.nombreCubo,
                "archivoParquet": c.archivoParquet,
                "existeEnDisco": os.path.exists(c.archivoParquet) if c.archivoParquet else False,
                "tipoOrigen": c.tipoOrigen,
                "estadoHabilitado": c.estadoHabilitado,
                "fechaUltimaCarga": c.fechaUltimaCarga.isoformat() if c.fechaUltimaCarga else None,
                "vistasAsociadas": [v.codigoVista for v in c.vistas]
            })
        return resultado


@mcp.tool()
def auditar_excepciones_usuario(idUsuario: int) -> Dict[str, Any]:
    """
    Audita la matriz de excepciones concedidas (+) o revocadas (-) para un usuario específico,
    tanto a nivel de cubos/vistas analíticas como de pantallas del sistema.
    """
    with obtenerSesion() as sesion:
        usuario = sesion.query(UsuarioModelo).filter_by(idUsuario=idUsuario).first()
        if not usuario:
            return {"error": f"Usuario con ID {idUsuario} no encontrado."}

        excepcionesVistas = sesion.query(ExcepcionUsuarioModelo).filter_by(idUsuario=idUsuario).all()
        excepcionesPantallas = sesion.query(ExcepcionPantallaUsuarioModelo).filter_by(idUsuario=idUsuario).all()

        return {
            "usuario": usuario.nombreUsuario,
            "rol": usuario.rol.nombreRol if usuario.rol else "Sin Rol",
            "excepcionesVistas": [
                {
                    "vista": exc.vista.codigoVista if exc.vista else "N/A",
                    "permitido": exc.permitido,
                    "motivo": exc.motivo,
                    "fecha": exc.fechaCreacion.isoformat() if exc.fechaCreacion else None
                }
                for exc in excepcionesVistas
            ],
            "excepcionesPantallas": [
                {
                    "pantalla": exc.pantalla.codigoPantalla if exc.pantalla else "N/A",
                    "permitido": exc.permitido,
                    "motivo": exc.motivo,
                    "fecha": exc.fechaCreacion.isoformat() if exc.fechaCreacion else None
                }
                for exc in excepcionesPantallas
            ]
        }


@mcp.tool()
def ejecutar_consulta_segura_control(consultaSql: str, limite: int = 50) -> Dict[str, Any]:
    """
    Ejecuta una consulta SQL SELECT de sólo lectura sobre las tablas relacionales de control en SQL Server.
    Bloquea estrictamente sentencias de modificación (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE).
    """
    consultaLimpia = consultaSql.strip()
    palabrasProhibidas = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "EXEC", "EXECUTE", "CREATE"]
    primeraPalabra = consultaLimpia.split()[0].upper() if consultaLimpia else ""

    if primeraPalabra != "SELECT":
        return {"error": "Solo se permiten consultas de lectura que comiencen con SELECT."}

    for palabra in palabrasProhibidas:
        if f" {palabra} " in f" {consultaLimpia.upper()} ":
            return {"error": f"La sentencia contiene la palabra clave restringida '{palabra}'."}

    limiteEfectivo = min(max(1, limite), 100)

    try:
        with motorBaseDatos.connect() as conn:
            # Envolver con TOP / LIMIT si no lo tiene
            res = conn.execute(text(consultaLimpia))
            filas = [dict(row._mapping) for row in res.fetchmany(limiteEfectivo)]
            return {
                "exito": True,
                "totalFilas": len(filas),
                "filas": filas
            }
    except Exception as e:
        return {"exito": False, "error": str(e)}


def iniciarServidor() -> None:
    """
    Inicia el servidor MCP a través del transporte estándar Stdio.
    """
    mcp.run(transport="stdio")


if __name__ == "__main__":
    iniciarServidor()
