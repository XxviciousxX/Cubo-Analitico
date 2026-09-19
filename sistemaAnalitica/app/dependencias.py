"""
Dependencias de seguridad y gestión de sesiones para FastAPI.
Maneja autenticación por cookies firmadas y redirecciones automáticas a /login.
"""

import os
import json
import time
import hmac
import hashlib
import base64
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse

CLAVE_SECRETA_SESION = os.getenv("CLAVE_SECRETA_SESION", "clave-secreta-corporativa-sistema-analitica-2026")
NOMBRE_COOKIE_SESION = "sesion_analitica_token"
TIEMPO_INACTIVIDAD_SEGUNDOS = int(os.getenv("TIEMPO_INACTIVIDAD_SEGUNDOS", "1200"))  # 20 minutos (1200 segundos)


def serializarSesionUsuario(datosUsuario: Dict[str, Any]) -> str:
    """
    Serializa y firma criptográficamente los datos de sesión en un token base64 seguro,
    asegurando el registro del timestamp de último acceso para control de inactividad.
    """
    if "ultimo_acceso" not in datosUsuario:
        datosUsuario["ultimo_acceso"] = int(time.time())
    contenidoJson = json.dumps(datosUsuario, separators=(",", ":"))
    firma = hmac.new(
        CLAVE_SECRETA_SESION.encode("utf-8"),
        contenidoJson.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    carga = f"{firma}:{contenidoJson}"
    return base64.urlsafe_b64encode(carga.encode("utf-8")).decode("utf-8")


def deserializarSesionUsuario(tokenCookie: str) -> Optional[Dict[str, Any]]:
    """
    Verifica la firma y extrae el diccionario de usuario de la cookie.
    Valida que no haya superado el umbral de inactividad permitido (20 minutos).
    """
    try:
        decodificado = base64.urlsafe_b64decode(tokenCookie.encode("utf-8")).decode("utf-8")
        partes = decodificado.split(":", 1)
        if len(partes) != 2:
            return None

        firmaEsperada, contenidoJson = partes
        firmaCalculada = hmac.new(
            CLAVE_SECRETA_SESION.encode("utf-8"),
            contenidoJson.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(firmaEsperada, firmaCalculada):
            datos = json.loads(contenidoJson)
            ultimoAcceso = datos.get("ultimo_acceso")
            if ultimoAcceso is not None:
                ahora = int(time.time())
                if ahora - ultimoAcceso > TIEMPO_INACTIVIDAD_SEGUNDOS:
                    # Sesión expirada por inactividad (> 20 minutos)
                    return None
            return datos
    except Exception:
        return None
    return None


def obtenerUsuarioActual(request: Request) -> Optional[Dict[str, Any]]:
    """
    Recupera el usuario actual desde la cookie de sesión o retorna None si no existe o expiró por inactividad.
    """
    token = request.cookies.get(NOMBRE_COOKIE_SESION)
    if not token:
        return None
    return deserializarSesionUsuario(token)


from sistemaAnalitica.modulos.seguridad import ServicioAutorizacion


def requerirUsuarioAutenticado(request: Request) -> Dict[str, Any]:
    """
    Dependencia estricta para vistas HTML y API. Si el usuario no tiene sesión válida,
    lanza una excepción controlada para redirigir a /login o error 401 si es API.
    Adjunta en el diccionario del usuario la lista de pantallas autorizadas.
    """
    usuario = obtenerUsuarioActual(request)
    if not usuario:
        if "api" in request.url.path:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sesión no válida o expirada por inactividad."
            )
        tokenPrevio = request.cookies.get(NOMBRE_COOKIE_SESION)
        ubicacionLogin = "/login?inactividad=1" if tokenPrevio else "/login"
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": ubicacionLogin}
        )

    # Inyectar dinámicamente las pantallas permitidas según rol y excepciones
    idUsuario = usuario.get("idUsuario")
    if idUsuario:
        usuario["pantallasPermitidas"] = ServicioAutorizacion.obtenerPantallasPermitidasUsuario(idUsuario)
    else:
        usuario["pantallasPermitidas"] = []

    return usuario


def requerirPermisoPantalla(codigoPantalla: str):
    """
    Genera un validador de dependencia FastAPI que asegura que el usuario tenga
    acceso efectivo a la pantalla solicitada, lanzando HTTP 403 en caso denegado.
    """
    def _verificador(request: Request) -> Dict[str, Any]:
        usuario = requerirUsuarioAutenticado(request)
        idUsuario = usuario.get("idUsuario")
        if not idUsuario or not ServicioAutorizacion.verificarAccesoPantalla(idUsuario, codigoPantalla):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso Restringido: Tu perfil o excepciones no te permiten ingresar a la pantalla '{codigoPantalla}'."
            )
        return usuario
    return _verificador

