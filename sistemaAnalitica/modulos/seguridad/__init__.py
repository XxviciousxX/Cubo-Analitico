"""
Submódulo de Gobernanza y Seguridad.
Maneja roles, permisos de vistas, matriz de excepciones de usuario y seguridad por fila (RLS).
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import (
    UsuarioModelo, RolModelo, VistaModelo, PantallaModelo,
    ExcepcionUsuarioModelo, ExcepcionPantallaUsuarioModelo,
    RolVistaModelo, RolPantallaModelo, LogSistemaModelo
)
from sistemaAnalitica.modulos.seguridad.gestorLogs import GestorLogsSistema


class ServicioAutorizacion:
    """
    Gestiona el cálculo de permisos efectivos y transacciones de asignación.
    """

    @staticmethod
    def verificarAccesoPantalla(idUsuario: int, codigoPantalla: str, sesionExterna: Optional[Session] = None) -> bool:
        """
        Calcula si el usuario tiene acceso efectivo a una pantalla del sistema.
        """
        def _verificar(sesion: Session) -> bool:
            usuario = sesion.query(UsuarioModelo).filter_by(idUsuario=idUsuario, activo=True).first()
            if not usuario:
                return False

            if usuario.rol and usuario.rol.nombreRol == "Administrador":
                excepcionRevocada = sesion.query(ExcepcionPantallaUsuarioModelo).join(PantallaModelo).filter(
                    ExcepcionPantallaUsuarioModelo.idUsuario == idUsuario,
                    PantallaModelo.codigoPantalla == codigoPantalla,
                    ExcepcionPantallaUsuarioModelo.permitido == False
                ).first()
                if excepcionRevocada:
                    return False
                return True

            pantalla = sesion.query(PantallaModelo).filter_by(codigoPantalla=codigoPantalla, activo=True).first()
            if not pantalla:
                return False

            excepcion = sesion.query(ExcepcionPantallaUsuarioModelo).filter_by(
                idUsuario=idUsuario,
                idPantalla=pantalla.idPantalla
            ).first()

            if excepcion is not None:
                return excepcion.permitido

            if not usuario.rol:
                return False

            tieneRol = sesion.query(RolPantallaModelo).filter_by(
                idRol=usuario.idRol,
                idPantalla=pantalla.idPantalla
            ).first() is not None

            return tieneRol

        if sesionExterna:
            return _verificar(sesionExterna)
        with obtenerSesion() as s:
            return _verificar(s)

    @staticmethod
    def obtenerPantallasPermitidasUsuario(idUsuario: int) -> List[Dict[str, Any]]:
        """
        Devuelve el listado ordenado de pantallas a las que el usuario puede acceder.
        """
        pantallasPermitidas = []
        with obtenerSesion() as sesion:
            pantallas = sesion.query(PantallaModelo).filter_by(activo=True).order_by(PantallaModelo.orden).all()
            for p in pantallas:
                if ServicioAutorizacion.verificarAccesoPantalla(idUsuario, p.codigoPantalla, sesionExterna=sesion):
                    pantallasPermitidas.append({
                        "idPantalla": p.idPantalla,
                        "codigoPantalla": p.codigoPantalla,
                        "nombrePantalla": p.nombrePantalla,
                        "rutaPantalla": p.rutaPantalla,
                        "icono": p.icono,
                        "descripcion": p.descripcion,
                        "orden": p.orden
                    })
        return pantallasPermitidas

    @staticmethod
    def verificarAccesoVista(idUsuario: int, codigoVista: str, sesionExterna: Optional[Session] = None) -> bool:
        """
        Calcula si el usuario tiene acceso efectivo a un cubo analítico o vista.
        """
        def _verificar(sesion: Session) -> bool:
            usuario = sesion.query(UsuarioModelo).filter_by(idUsuario=idUsuario, activo=True).first()
            if not usuario:
                return False

            vista = sesion.query(VistaModelo).filter_by(codigoVista=codigoVista, activo=True).first()
            if not vista:
                return False

            # Validar ciclo de vida: si la vista o su cubo están deshabilitados, denegar acceso
            if not vista.estadoHabilitado:
                return False
            if vista.cubo and not vista.cubo.estadoHabilitado:
                return False

            if usuario.rol and usuario.rol.nombreRol == "Administrador":
                excepcionRevocada = sesion.query(ExcepcionUsuarioModelo).filter_by(
                    idUsuario=idUsuario,
                    idVista=vista.idVista,
                    permitido=False
                ).first()
                if excepcionRevocada:
                    return False
                return True

            excepcion = sesion.query(ExcepcionUsuarioModelo).filter_by(
                idUsuario=idUsuario,
                idVista=vista.idVista
            ).first()

            if excepcion is not None:
                return excepcion.permitido

            if not usuario.rol:
                return False

            tieneRol = sesion.query(RolVistaModelo).filter_by(
                idRol=usuario.idRol,
                idVista=vista.idVista
            ).first() is not None

            return tieneRol

        if sesionExterna:
            return _verificar(sesionExterna)
        with obtenerSesion() as s:
            return _verificar(s)

    @staticmethod
    def obtenerVistasPermitidasUsuario(idUsuario: int) -> List[VistaModelo]:
        """
        Devuelve las instancias de VistaModelo a las que el usuario tiene acceso efectivo.
        """
        vistasAutorizadas = []
        with obtenerSesion() as sesion:
            todasLasVistas = sesion.query(VistaModelo).filter_by(activo=True).all()
            for v in todasLasVistas:
                if ServicioAutorizacion.verificarAccesoVista(idUsuario, v.codigoVista, sesionExterna=sesion):
                    vistasAutorizadas.append(v)
        return vistasAutorizadas

    @staticmethod
    def asignarVistasARol(idRol: int, idsVistas: List[int]) -> None:
        """
        Actualiza en bloque las vistas asociadas a un rol institucional.
        """
        with obtenerSesion() as sesion:
            rol = sesion.query(RolModelo).filter_by(idRol=idRol).first()
            if not rol:
                raise ValueError(f"Rol con ID {idRol} no encontrado.")

            vistas = sesion.query(VistaModelo).filter(VistaModelo.idVista.in_(idsVistas)).all() if idsVistas else []
            rol.vistas = vistas
            sesion.commit()

    @staticmethod
    def asignarPantallasARol(idRol: int, idsPantallas: List[int]) -> None:
        """
        Actualiza en bloque las pantallas asociadas a un rol institucional.
        """
        with obtenerSesion() as sesion:
            rol = sesion.query(RolModelo).filter_by(idRol=idRol).first()
            if not rol:
                raise ValueError(f"Rol con ID {idRol} no encontrado.")

            pantallas = sesion.query(PantallaModelo).filter(PantallaModelo.idPantalla.in_(idsPantallas)).all() if idsPantallas else []
            rol.pantallas = pantallas
            sesion.commit()

    @staticmethod
    def registrarExcepcionVista(idUsuario: int, idVista: int, permitido: bool, motivo: Optional[str] = None) -> None:
        """
        Crea o actualiza una excepción de acceso a una vista para un usuario.
        """
        with obtenerSesion() as sesion:
            excepcion = sesion.query(ExcepcionUsuarioModelo).filter_by(
                idUsuario=idUsuario,
                idVista=idVista
            ).first()

            if not excepcion:
                excepcion = ExcepcionUsuarioModelo(
                    idUsuario=idUsuario,
                    idVista=idVista,
                    permitido=permitido,
                    motivo=motivo or ("Concesión explícita" if permitido else "Revocación explícita")
                )
                sesion.add(excepcion)
            else:
                excepcion.permitido = permitido
                if motivo:
                    excepcion.motivo = motivo
            sesion.commit()

    @staticmethod
    def eliminarExcepcionVista(idExcepcion: int) -> bool:
        """
        Elimina una regla de excepción de vista por su identificador.
        """
        with obtenerSesion() as sesion:
            exc = sesion.query(ExcepcionUsuarioModelo).filter_by(idExcepcion=idExcepcion).first()
            if exc:
                sesion.delete(exc)
                sesion.commit()
                return True
            return False

    @staticmethod
    def registrarExcepcionPantalla(idUsuario: int, idPantalla: int, permitido: bool, motivo: Optional[str] = None) -> None:
        """
        Crea o actualiza una excepción de acceso a una pantalla para un usuario.
        """
        with obtenerSesion() as sesion:
            excepcion = sesion.query(ExcepcionPantallaUsuarioModelo).filter_by(
                idUsuario=idUsuario,
                idPantalla=idPantalla
            ).first()

            if not excepcion:
                excepcion = ExcepcionPantallaUsuarioModelo(
                    idUsuario=idUsuario,
                    idPantalla=idPantalla,
                    permitido=permitido,
                    motivo=motivo or ("Concesión explícita de pantalla" if permitido else "Revocación explícita de pantalla")
                )
                sesion.add(excepcion)
            else:
                excepcion.permitido = permitido
                if motivo:
                    excepcion.motivo = motivo
            sesion.commit()

    @staticmethod
    def eliminarExcepcionPantalla(idExcepcion: int) -> bool:
        """
        Elimina una regla de excepción de pantalla por su identificador.
        """
        with obtenerSesion() as sesion:
            exc = sesion.query(ExcepcionPantallaUsuarioModelo).filter_by(idExcepcion=idExcepcion).first()
            if exc:
                sesion.delete(exc)
                sesion.commit()
                return True
            return False

