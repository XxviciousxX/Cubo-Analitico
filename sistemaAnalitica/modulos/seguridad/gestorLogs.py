"""
Servicio centralizado de auditoría y registro de errores del sistema en base de datos.
Permite persistir incidentes con trazabilidad de capa, método y mensaje técnico.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
import traceback
import logging

from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import LogSistemaModelo

logger = logging.getLogger("GestorLogsSistema")


class GestorLogsSistema:
    """
    Servicio para el registro y consulta de errores del sistema en la tabla logs_sistema.
    """

    @classmethod
    def registrarError(cls, capa: str, metodo: str, error: str) -> Optional[int]:
        """
        Guarda un error en la tabla logs_sistema de SQL Server.
        Nunca propaga excepciones para no interrumpir el flujo principal de la aplicación.
        """
        try:
            with obtenerSesion() as sesion:
                nuevoLog = LogSistemaModelo(
                    fecha=datetime.utcnow(),
                    capa=str(capa).strip().upper()[:50],
                    metodo=str(metodo).strip()[:100],
                    error=str(error).strip()
                )
                sesion.add(nuevoLog)
                sesion.commit()
                sesion.refresh(nuevoLog)
                return nuevoLog.id
        except Exception as ex:
            logger.error(f"Fallo al registrar error en logs_sistema: {str(ex)}")
            return None

    @classmethod
    def consultarLogsRecientes(cls, limite: int = 50) -> List[Dict[str, Any]]:
        """
        Retorna los errores más recientes ordenados descendentemente por fecha.
        """
        try:
            with obtenerSesion() as sesion:
                registros = sesion.query(LogSistemaModelo).order_by(
                    LogSistemaModelo.fecha.desc()
                ).limit(limite).all()

                return [
                    {
                        "id": r.id,
                        "fecha": r.fecha.strftime("%Y-%m-%d %H:%M:%S") if r.fecha else None,
                        "capa": r.capa,
                        "metodo": r.metodo,
                        "error": r.error
                    }
                    for r in registros
                ]
        except Exception as ex:
            logger.error(f"Fallo al consultar logs_sistema: {str(ex)}")
            return []
