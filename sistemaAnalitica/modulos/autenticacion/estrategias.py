"""
Estrategias de autenticación desacopladas bajo el patrón Strategy.
Implementa validación Local, Active Directory (LDAP3) y SOAP (Zeep).
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any
import logging

from sistemaAnalitica.modulos.seguridad.baseDatos import (
    obtenerSesion, verificarContrasena
)
from sistemaAnalitica.modulos.seguridad.modelos import UsuarioModelo, RolModelo

configuracionLogger = logging.getLogger("AutenticacionEstrategias")


class EstrategiaAutenticacionBase(ABC):
    """
    Interfaz base que define el contrato obligatorio para cualquier mecanismo de autenticación.
    """

    @abstractmethod
    def autenticar(self, nombreUsuario: str, clave: str) -> Optional[Dict[str, Any]]:
        """
        Valida las credenciales provistas y retorna el diccionario de perfil de usuario o None.
        """
        pass

    @abstractmethod
    def obtenerNombreEstrategia(self) -> str:
        """
        Retorna el identificador legible de la estrategia.
        """
        pass


class AutenticadorLocal(EstrategiaAutenticacionBase):
    """
    Estrategia de autenticación local contra la base de datos relacional del sistema.
    """

    def obtenerNombreEstrategia(self) -> str:
        return "Autenticación Local (Base de Datos)"

    def autenticar(self, nombreUsuario: str, clave: str) -> Optional[Dict[str, Any]]:
        if not nombreUsuario or not clave:
            return None

        with obtenerSesion() as sesion:
            usuario = sesion.query(UsuarioModelo).filter(
                UsuarioModelo.nombreUsuario.ilike(nombreUsuario.strip())
            ).first()

            if not usuario:
                return None

            if not usuario.activo:
                return None

            if not verificarContrasena(clave, usuario.claveHash):
                return None

            # Actualizar fecha de último acceso
            usuario.fechaUltimoAcceso = datetime.utcnow()
            sesion.commit()

            codigosPermisos = [p.codigoPermiso for p in usuario.rol.permisos] if usuario.rol else []

            return {
                "idUsuario": usuario.idUsuario,
                "nombreUsuario": usuario.nombreUsuario,
                "nombreCompleto": usuario.nombreCompleto,
                "correoElectronico": usuario.correoElectronico,
                "nombreRol": usuario.rol.nombreRol if usuario.rol else "Sin Rol",
                "idRol": usuario.idRol,
                "permisos": codigosPermisos,
                "origenAutenticacion": "LOCAL"
            }


class AutenticadorActiveDirectory(EstrategiaAutenticacionBase):
    """
    Estrategia de autenticación empresarial mediante Directorio Activo utilizando ldap3.
    """

    def __init__(
        self,
        servidorLdap: str = "ldap://directorio.corporativo.local",
        puerto: int = 389,
        usarSsl: bool = False,
        dominio: str = "EMPRESA",
        baseDn: str = "DC=empresa,DC=local",
        permitirSimulacionDesarrollo: bool = True
    ):
        self.servidorLdap = servidorLdap
        self.puerto = puerto
        self.usarSsl = usarSsl
        self.dominio = dominio
        self.baseDn = baseDn
        self.permitirSimulacionDesarrollo = permitirSimulacionDesarrollo

    def obtenerNombreEstrategia(self) -> str:
        return "Active Directory (LDAP)"

    def autenticar(self, nombreUsuario: str, clave: str) -> Optional[Dict[str, Any]]:
        if not nombreUsuario or not clave:
            return None

        usuarioCompletoLdap = f"{self.dominio}\\{nombreUsuario.strip()}"

        try:
            from ldap3 import Server, Connection, ALL, NTLM, SUBTREE
            servidor = Server(self.servidorLdap, port=self.puerto, use_ssl=self.usarSsl, get_info=ALL)
            conexion = Connection(
                servidor,
                user=usuarioCompletoLdap,
                password=clave,
                authentication=NTLM,
                auto_bind=True
            )

            if conexion.bound:
                # Búsqueda de atributos del usuario en AD
                filtroLdap = f"(&(objectClass=user)(sAMAccountName={nombreUsuario.strip()}))"
                atributosRequeridos = ["displayName", "mail", "memberOf"]
                conexion.search(
                    search_base=self.baseDn,
                    search_filter=filtroLdap,
                    search_scope=SUBTREE,
                    attributes=atributosRequeridos
                )

                nombreCompleto = nombreUsuario
                correo = f"{nombreUsuario}@{self.dominio.lower()}.com"

                if conexion.entries:
                    entrada = conexion.entries[0]
                    if hasattr(entrada, "displayName") and entrada.displayName.value:
                        nombreCompleto = str(entrada.displayName.value)
                    if hasattr(entrada, "mail") and entrada.mail.value:
                        correo = str(entrada.mail.value)

                conexion.unbind()

                # Sincronización o consulta en base de datos local para mapear roles
                return self._sincronizarUsuarioLocal(nombreUsuario, nombreCompleto, correo)

        except Exception as errorLdap:
            configuracionLogger.warning(f"Error conectando con servidor LDAP {self.servidorLdap}: {str(errorLdap)}")

            # Soporte de prueba / modo preparado para entornos donde aún no está disponible el AD real
            if self.permitirSimulacionDesarrollo and nombreUsuario.lower() == "ad_demo" and clave == "demo123":
                return self._sincronizarUsuarioLocal(
                    nombreUsuario="ad_demo",
                    nombreCompleto="Usuario Directorio Activo Demo",
                    correo=f"ad_demo@{self.dominio.lower()}.com"
                )

        return None

    def _sincronizarUsuarioLocal(self, nombreUsuario: str, nombreCompleto: str, correo: str) -> Dict[str, Any]:
        """
        Garantiza que exista un registro local con rol asignado para el usuario autenticado por AD.
        """
        with obtenerSesion() as sesion:
            usuarioLocal = sesion.query(UsuarioModelo).filter_by(nombreUsuario=nombreUsuario).first()
            if not usuarioLocal:
                rolAnalista = sesion.query(RolModelo).filter_by(nombreRol="Analista").first()
                idRolDefecto = rolAnalista.idRol if rolAnalista else 1

                usuarioLocal = UsuarioModelo(
                    nombreUsuario=nombreUsuario,
                    nombreCompleto=nombreCompleto,
                    correoElectronico=correo,
                    claveHash="PROVISTO_POR_LDAP",
                    idRol=idRolDefecto,
                    activo=True,
                    origenAutenticacion="ACTIVE_DIRECTORY"
                )
                sesion.add(usuarioLocal)
                sesion.flush()

            usuarioLocal.fechaUltimoAcceso = datetime.utcnow()
            sesion.commit()

            codigosPermisos = [p.codigoPermiso for p in usuarioLocal.rol.permisos] if usuarioLocal.rol else []

            return {
                "idUsuario": usuarioLocal.idUsuario,
                "nombreUsuario": usuarioLocal.nombreUsuario,
                "nombreCompleto": usuarioLocal.nombreCompleto,
                "correoElectronico": usuarioLocal.correoElectronico,
                "nombreRol": usuarioLocal.rol.nombreRol if usuarioLocal.rol else "Analista",
                "idRol": usuarioLocal.idRol,
                "permisos": codigosPermisos,
                "origenAutenticacion": "ACTIVE_DIRECTORY"
            }


class AutenticadorSoap(EstrategiaAutenticacionBase):
    """
    Estrategia de autenticación contra servicios legados SOAP XML utilizando Zeep.
    """

    def __init__(
        self,
        urlWsdl: str = "http://servicios.corporativo.local/SeguridadServicio.svc?wsdl",
        nombreOperacion: str = "ValidarCredenciales",
        tiempoEsperaSegundos: int = 10,
        permitirSimulacionDesarrollo: bool = True
    ):
        self.urlWsdl = urlWsdl
        self.nombreOperacion = nombreOperacion
        self.tiempoEsperaSegundos = tiempoEsperaSegundos
        self.permitirSimulacionDesarrollo = permitirSimulacionDesarrollo

    def obtenerNombreEstrategia(self) -> str:
        return "Servicio Web SOAP (Zeep)"

    def autenticar(self, nombreUsuario: str, clave: str) -> Optional[Dict[str, Any]]:
        if not nombreUsuario or not clave:
            return None

        try:
            from zeep import Client
            from zeep.transports import Transport
            import requests

            sesionHttp = requests.Session()
            transporte = Transport(session=sesionHttp, timeout=self.tiempoEsperaSegundos)
            clienteSoap = Client(wsdl=self.urlWsdl, transport=transporte)

            metodoServicio = getattr(clienteSoap.service, self.nombreOperacion)
            resultado = metodoServicio(
                usuario=nombreUsuario.strip(),
                contrasena=clave
            )

            if resultado and getattr(resultado, "EsValido", False):
                nombreCompleto = getattr(resultado, "NombreCompleto", nombreUsuario)
                correo = getattr(resultado, "Correo", f"{nombreUsuario}@soap.local")
                return self._sincronizarUsuarioSoap(nombreUsuario, nombreCompleto, correo)

        except Exception as errorSoap:
            configuracionLogger.warning(f"Error invocando servicio SOAP {self.urlWsdl}: {str(errorSoap)}")

            if self.permitirSimulacionDesarrollo and nombreUsuario.lower() == "soap_demo" and clave == "soap123":
                return self._sincronizarUsuarioSoap(
                    nombreUsuario="soap_demo",
                    nombreCompleto="Usuario Servicio SOAP Demo",
                    correo="soap_demo@soap.local"
                )

        return None

    def _sincronizarUsuarioSoap(self, nombreUsuario: str, nombreCompleto: str, correo: str) -> Dict[str, Any]:
        """
        Garantiza sincronización en la base de datos local para el usuario autenticado vía SOAP.
        """
        with obtenerSesion() as sesion:
            usuarioLocal = sesion.query(UsuarioModelo).filter_by(nombreUsuario=nombreUsuario).first()
            if not usuarioLocal:
                rolOperador = sesion.query(RolModelo).filter_by(nombreRol="Operador").first()
                idRolDefecto = rolOperador.idRol if rolOperador else 1

                usuarioLocal = UsuarioModelo(
                    nombreUsuario=nombreUsuario,
                    nombreCompleto=nombreCompleto,
                    correoElectronico=correo,
                    claveHash="PROVISTO_POR_SOAP",
                    idRol=idRolDefecto,
                    activo=True,
                    origenAutenticacion="SOAP"
                )
                sesion.add(usuarioLocal)
                sesion.flush()

            usuarioLocal.fechaUltimoAcceso = datetime.utcnow()
            sesion.commit()

            codigosPermisos = [p.codigoPermiso for p in usuarioLocal.rol.permisos] if usuarioLocal.rol else []

            return {
                "idUsuario": usuarioLocal.idUsuario,
                "nombreUsuario": usuarioLocal.nombreUsuario,
                "nombreCompleto": usuarioLocal.nombreCompleto,
                "correoElectronico": usuarioLocal.correoElectronico,
                "nombreRol": usuarioLocal.rol.nombreRol if usuarioLocal.rol else "Operador",
                "idRol": usuarioLocal.idRol,
                "permisos": codigosPermisos,
                "origenAutenticacion": "SOAP"
            }
