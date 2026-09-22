"""
Gestor de conexión, sesiones y sembrado inicial de la base de datos relacional.
Soporta PostgreSQL (Supabase), SQL Server y SQLite local.
"""

import os
import hashlib
import binascii
import urllib.parse
import logging
from datetime import datetime
from contextlib import contextmanager
from typing import Generator, Optional
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
directorioActual = os.path.dirname(os.path.abspath(__file__))
directorioRaiz = os.path.abspath(os.path.join(directorioActual, "..", ".."))
directorioProyecto = os.path.abspath(os.path.join(directorioRaiz, ".."))
rutaEnv = os.path.join(directorioProyecto, ".env")
if os.path.exists(rutaEnv):
    load_dotenv(rutaEnv)
else:
    load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from sistemaAnalitica.modulos.seguridad.modelos import (
    BaseModelo, RolModelo, PermisoModelo, UsuarioModelo,
    PantallaModelo, RolPantallaModelo, RolVistaModelo, VistaModelo, CuboModelo,
    LogAuditoriaEliminacionModelo
)

loggerBaseDatos = logging.getLogger("BaseDatosControl")

# Determinación de ruta absoluta de persistencia local
directorioAlmacenamiento = os.path.join(directorioRaiz, "almacenamiento")
os.makedirs(directorioAlmacenamiento, exist_ok=True)

rutaBaseDatosSqlite = os.path.join(directorioAlmacenamiento, "controlAnalitica.db")
cadenaConexionPorDefecto = f"sqlite:///{rutaBaseDatosSqlite}"

# Configuración SQL Server parametrizable vía variables de entorno
SERVIDOR_SQL_RAW = os.getenv("SQL_SERVER_HOST", "").strip()
if SERVIDOR_SQL_RAW and not SERVIDOR_SQL_RAW.lower().startswith("tcp:") and "," not in SERVIDOR_SQL_RAW:
    SERVIDOR_SQL = f"tcp:{SERVIDOR_SQL_RAW},1433"
else:
    SERVIDOR_SQL = SERVIDOR_SQL_RAW

BASE_DATOS_SQL = os.getenv("SQL_SERVER_DB", "").strip()
USUARIO_SQL = os.getenv("SQL_SERVER_USER", "").strip()
PASSWORD_SQL = os.getenv("SQL_SERVER_PASS", "").strip()
DRIVER_ODBC = os.getenv("SQL_SERVER_DRIVER", "ODBC Driver 17 for SQL Server")

cadenaSqlServer = ""
if SERVIDOR_SQL and BASE_DATOS_SQL:
    paramsConn = urllib.parse.quote_plus(
        f"DRIVER={{{DRIVER_ODBC}}};"
        f"SERVER={SERVIDOR_SQL};"
        f"DATABASE={BASE_DATOS_SQL};"
        f"UID={USUARIO_SQL};"
        f"PWD={PASSWORD_SQL};"
        f"TrustServerCertificate=yes;"
        f"LoginTimeout=5;"
    )
    cadenaSqlServer = f"mssql+pyodbc:///?odbc_connect={paramsConn}"

cadenaConexionConfigurada = os.getenv("DATABASE_URL") or os.getenv("CADENA_CONEXION_CONTROL") or cadenaSqlServer or cadenaConexionPorDefecto

# Normalizar prefijo de PostgreSQL si es necesario
if cadenaConexionConfigurada.startswith("postgres://"):
    cadenaConexionConfigurada = cadenaConexionConfigurada.replace("postgres://", "postgresql+psycopg2://", 1)
elif cadenaConexionConfigurada.startswith("postgresql://") and not cadenaConexionConfigurada.startswith("postgresql+"):
    cadenaConexionConfigurada = cadenaConexionConfigurada.replace("postgresql://", "postgresql+psycopg2://", 1)

if "postgres" in cadenaConexionConfigurada:
    motorActivo = "POSTGRESQL"
elif "mssql" in cadenaConexionConfigurada:
    motorActivo = "SQLSERVER"
else:
    motorActivo = "SQLITE"

try:
    parametrosConexion = {}
    if motorActivo == "SQLITE":
        parametrosConexion["connect_args"] = {"check_same_thread": False}
    elif motorActivo == "POSTGRESQL":
        parametrosConexion["pool_pre_ping"] = True
        parametrosConexion["pool_recycle"] = 300

    motorBaseDatos = create_engine(
        cadenaConexionConfigurada,
        echo=False,
        **parametrosConexion
    )
    # Validar conexión inmediata con un ping rápido
    with motorBaseDatos.connect() as conexionPrueba:
        pass
except Exception as errorConexion:
    loggerBaseDatos.warning(f"No fue posible conectar a {cadenaConexionConfigurada}: {errorConexion}. Usando SQLite local.")
    motorBaseDatos = create_engine(
        cadenaConexionPorDefecto,
        echo=False,
        connect_args={"check_same_thread": False}
    )
    motorActivo = "SQLITE"

FabricaSesiones = sessionmaker(bind=motorBaseDatos, autocommit=False, autoflush=False, expire_on_commit=False)


def migrarEsquemaPersistenciaCubos():
    """
    Garantiza que la columna archivo_binario exista en la tabla cubos sin alterar datos existentes.
    Compatible con PostgreSQL, SQLite y SQL Server.
    """
    try:
        with motorBaseDatos.begin() as con:
            if motorActivo == "POSTGRESQL":
                con.execute(text("ALTER TABLE cubos ADD COLUMN IF NOT EXISTS archivo_binario BYTEA;"))
            elif motorActivo == "SQLITE":
                try:
                    infoCols = [r[1] for r in con.execute(text("PRAGMA table_info(cubos);")).fetchall()]
                    if infoCols and "archivo_binario" not in infoCols:
                        con.execute(text("ALTER TABLE cubos ADD COLUMN archivo_binario BLOB;"))
                except Exception:
                    pass
            elif motorActivo == "SQLSERVER":
                con.execute(text("""
                    IF NOT EXISTS (
                        SELECT * FROM sys.columns 
                        WHERE object_id = OBJECT_ID('cubos') AND name = 'archivo_binario'
                    )
                    ALTER TABLE cubos ADD archivo_binario VARBINARY(MAX) NULL;
                """))
        loggerBaseDatos.info("Esquema de persistencia de cubos verificado exitosamente.")
    except Exception as err:
        loggerBaseDatos.warning(f"Aviso al verificar columna archivo_binario: {err}")


# Ejecutar migración preventiva de esquema al cargar el módulo
migrarEsquemaPersistenciaCubos()


def obtenerInfoMotorActivo() -> dict:
    """
    Retorna información diagnóstica sobre el motor de base de datos relacional en uso.
    """
    if motorActivo == "POSTGRESQL":
        urlParsed = urllib.parse.urlparse(cadenaConexionConfigurada)
        return {
            "motor": "POSTGRESQL (Supabase)",
            "servidor": urlParsed.hostname or "Supabase",
            "baseDatos": (urlParsed.path or "").lstrip("/") or "postgres",
            "usuario": urlParsed.username or "postgres"
        }
    elif motorActivo == "SQLSERVER":
        return {
            "motor": "SQLSERVER",
            "servidor": SERVIDOR_SQL,
            "baseDatos": BASE_DATOS_SQL,
            "usuario": USUARIO_SQL
        }
    return {
        "motor": "SQLITE",
        "servidor": "Local",
        "baseDatos": rutaBaseDatosSqlite,
        "usuario": "N/A"
    }



@contextmanager
def obtenerSesion() -> Generator[Session, None, None]:
    """
    Administrador de contexto que provee una sesión de base de datos segura con rollback automático.
    """
    sesion = FabricaSesiones()
    try:
        yield sesion
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()


def generarHashContrasena(clavePlana: str) -> str:
    """
    Genera un hash seguro PBKDF2-HMAC-SHA256 con salt embebido.
    """
    sal = os.urandom(16)
    hashBytes = hashlib.pbkdf2_hmac("sha256", clavePlana.encode("utf-8"), sal, 100000)
    return binascii.hexlify(sal).decode("utf-8") + "$" + binascii.hexlify(hashBytes).decode("utf-8")


def verificarContrasena(clavePlana: str, hashAlmacenado: str) -> bool:
    """
    Valida si la contraseña plana coincide con el hash PBKDF2 almacenado.
    """
    try:
        partes = hashAlmacenado.split("$")
        if len(partes) != 2:
            return False
        sal = binascii.unhexlify(partes[0].encode("utf-8"))
        hashEsperado = partes[1]
        hashCalculado = hashlib.pbkdf2_hmac("sha256", clavePlana.encode("utf-8"), sal, 100000)
        return binascii.hexlify(hashCalculado).decode("utf-8") == hashEsperado
    except Exception:
        return False


def sembrarDatosIniciales(sesion: Session) -> None:
    """
    Crea los roles, permisos y el usuario inicial admin/admin si la base de datos está vacía.
    """
    # 1. Sembrado de Roles (exactamente 3 roles de negocio)
    rolesIniciales = [
        {"nombreRol": "Administrador", "descripcion": "Control total del sistema, seguridad, cubos e ingesta"},
        {"nombreRol": "Analista de Datos", "descripcion": "Acceso a construcción, modelado y exploración de cubos"},
        {"nombreRol": "Operador", "descripcion": "Acceso restringido a consulta de reportes y tableros operacionales"}
    ]

    mapaRoles = {}
    for datosRol in rolesIniciales:
        rolExistente = sesion.query(RolModelo).filter_by(nombreRol=datosRol["nombreRol"]).first()
        if not rolExistente:
            rolNuevo = RolModelo(
                nombreRol=datosRol["nombreRol"],
                descripcion=datosRol["descripcion"],
                activo=True
            )
            sesion.add(rolNuevo)
            sesion.flush()
            mapaRoles[datosRol["nombreRol"]] = rolNuevo
        else:
            mapaRoles[datosRol["nombreRol"]] = rolExistente

    # 2. Sembrado de Permisos
    permisosIniciales = [
        {"codigoPermiso": "ACCESO_SISTEMA", "nombrePermiso": "Ingreso a la plataforma", "descripcion": "Permite iniciar sesión"},
        {"codigoPermiso": "ADMIN_SEGURIDAD", "nombrePermiso": "Gestión de seguridad", "descripcion": "Administración de usuarios y roles"},
        {"codigoPermiso": "INGESTA_DATOS", "nombrePermiso": "Gestión de ingesta", "descripcion": "Carga de Excel, SQL y Data Lake"},
        {"codigoPermiso": "EXPLORACION_CUBOS", "nombrePermiso": "Exploración analítica", "descripcion": "Drill-down y consulta de vistas"},
        {"codigoPermiso": "EXPORTAR_DATOS", "nombrePermiso": "Exportación de datos", "descripcion": "Descarga de reportes en Excel/CSV"}
    ]

    objetosPermisos = []
    for datosPermiso in permisosIniciales:
        permisoExistente = sesion.query(PermisoModelo).filter_by(codigoPermiso=datosPermiso["codigoPermiso"]).first()
        if not permisoExistente:
            permisoNuevo = PermisoModelo(
                codigoPermiso=datosPermiso["codigoPermiso"],
                nombrePermiso=datosPermiso["nombrePermiso"],
                descripcion=datosPermiso["descripcion"]
            )
            sesion.add(permisoNuevo)
            sesion.flush()
            objetosPermisos.append(permisoNuevo)
        else:
            objetosPermisos.append(permisoExistente)

    # Asignar permisos por rol
    mapaPermisos = {p.codigoPermiso: p for p in objetosPermisos}

    rolAdmin = mapaRoles.get("Administrador")
    if rolAdmin and not rolAdmin.permisos:
        rolAdmin.permisos = objetosPermisos

    rolAnalista = mapaRoles.get("Analista de Datos")
    if rolAnalista and not rolAnalista.permisos:
        rolAnalista.permisos = [
            mapaPermisos["ACCESO_SISTEMA"],
            mapaPermisos["INGESTA_DATOS"],
            mapaPermisos["EXPLORACION_CUBOS"],
            mapaPermisos["EXPORTAR_DATOS"]
        ]

    rolOperador = mapaRoles.get("Operador")
    if rolOperador and not rolOperador.permisos:
        rolOperador.permisos = [
            mapaPermisos["ACCESO_SISTEMA"],
            mapaPermisos["EXPLORACION_CUBOS"]
        ]

    # 3. Sembrado de los 3 Usuarios Iniciales Requeridos
    usuariosIniciales = [
        {
            "nombreUsuario": "admin",
            "clave": "admin",
            "nombreCompleto": "Administrador del Sistema",
            "correoElectronico": "admin@cubix.local",
            "rol": rolAdmin
        },
        {
            "nombreUsuario": "analista",
            "clave": "analista",
            "nombreCompleto": "Analista de Datos",
            "correoElectronico": "analista@cubix.local",
            "rol": rolAnalista
        },
        {
            "nombreUsuario": "operador",
            "clave": "operador",
            "nombreCompleto": "Operador de Datos",
            "correoElectronico": "operador@cubix.local",
            "rol": rolOperador
        }
    ]

    for datosU in usuariosIniciales:
        uExistente = sesion.query(UsuarioModelo).filter_by(nombreUsuario=datosU["nombreUsuario"]).first()
        if not uExistente and datosU["rol"]:
            nuevoU = UsuarioModelo(
                nombreUsuario=datosU["nombreUsuario"],
                nombreCompleto=datosU["nombreCompleto"],
                correoElectronico=datosU["correoElectronico"],
                claveHash=generarHashContrasena(datosU["clave"]),
                idRol=datosU["rol"].idRol,
                activo=True,
                origenAutenticacion="LOCAL"
            )
            sesion.add(nuevoU)
            sesion.flush()
        elif uExistente and datosU["rol"]:
            # Asegurar idRol y contraseña actualizada
            uExistente.idRol = datosU["rol"].idRol
            uExistente.claveHash = generarHashContrasena(datosU["clave"])
            uExistente.activo = True

    # 4. Sembrado de Pantallas del Sistema
    pantallasIniciales = [
        {
            "codigoPantalla": "INICIO",
            "nombrePantalla": "Panel Principal",
            "rutaPantalla": "/",
            "icono": "dashboard",
            "descripcion": "Indicadores globales y catálogo de cubos analíticos",
            "orden": 1
        },
        {
            "codigoPantalla": "INGESTA",
            "nombrePantalla": "Ingesta y Modelado OBT",
            "rutaPantalla": "/ingesta",
            "icono": "upload_file",
            "descripcion": "Carga de libros Excel Calamine, SQL en vivo y Data Lake",
            "orden": 2
        },
        {
            "codigoPantalla": "EXPLORADOR",
            "nombrePantalla": "Explorador y Reportes",
            "rutaPantalla": "/explorador",
            "icono": "pie_chart",
            "descripcion": "Tableros OLAP, gráficos interactivos, KPIs y drill-down",
            "orden": 3
        },
        {
            "codigoPantalla": "SEGURIDAD",
            "nombrePantalla": "Gobernanza y Roles",
            "rutaPantalla": "/seguridad",
            "icono": "shield_person",
            "descripcion": "Matriz de accesos, pantallas, vistas y excepciones por usuario",
            "orden": 4
        },
        {
            "codigoPantalla": "CONFIGURACION_VISTAS",
            "nombrePantalla": "Configuración de Vistas",
            "rutaPantalla": "/configuracion-vistas",
            "icono": "settings_suggest",
            "descripcion": "Reglas visuales Plotly, sugerencias semánticas y gobernanza de granularidad",
            "orden": 5
        },
        {
            "codigoPantalla": "ADMINISTRACION_CUBOS",
            "nombrePantalla": "Gestión de Cubos",
            "rutaPantalla": "/administracion/cubos",
            "icono": "dataset",
            "descripcion": "Ciclo de vida de cubos OBT, refresco de datos y edición de columnas",
            "orden": 6
        },
        {
            "codigoPantalla": "ADMINISTRACION_VISTAS",
            "nombrePantalla": "Gestión de Vistas",
            "rutaPantalla": "/administracion/vistas",
            "icono": "visibility",
            "descripcion": "Auditoría de vistas, autoría, estado y enlace a cubos",
            "orden": 7
        },
        {
            "codigoPantalla": "ELIMINACION_OBJETOS",
            "nombrePantalla": "Depuración de Objetos",
            "rutaPantalla": "/administracion/eliminacion",
            "icono": "delete_sweep",
            "descripcion": "Eliminación controlada y auditada de cubos y vistas",
            "orden": 8
        }
    ]

    mapaPantallas = {}
    for datosP in pantallasIniciales:
        pantallaExistente = sesion.query(PantallaModelo).filter_by(codigoPantalla=datosP["codigoPantalla"]).first()
        if not pantallaExistente:
            nuevaPantalla = PantallaModelo(
                codigoPantalla=datosP["codigoPantalla"],
                nombrePantalla=datosP["nombrePantalla"],
                rutaPantalla=datosP["rutaPantalla"],
                icono=datosP["icono"],
                descripcion=datosP["descripcion"],
                orden=datosP["orden"],
                activo=True
            )
            sesion.add(nuevaPantalla)
            sesion.flush()
            mapaPantallas[datosP["codigoPantalla"]] = nuevaPantalla
        else:
            mapaPantallas[datosP["codigoPantalla"]] = pantallaExistente

    # Asignar pantallas por defecto a los 3 roles
    todasLasPantallas = list(mapaPantallas.values())
    if rolAdmin:
        rolAdmin.pantallas = todasLasPantallas

    if rolAnalista:
        rolAnalista.pantallas = [
            mapaPantallas["INICIO"],
            mapaPantallas["INGESTA"],
            mapaPantallas["EXPLORADOR"],
            mapaPantallas["CONFIGURACION_VISTAS"],
            mapaPantallas["ADMINISTRACION_CUBOS"],
            mapaPantallas["ADMINISTRACION_VISTAS"],
            mapaPantallas["ELIMINACION_OBJETOS"]
        ]

    if rolOperador:
        rolOperador.pantallas = [
            mapaPantallas["INICIO"],
            mapaPantallas["EXPLORADOR"]
        ]

    # Asignar vistas existentes por defecto a Administrador y Analista de Datos
    todasLasVistas = sesion.query(VistaModelo).filter_by(activo=True).all()
    if todasLasVistas:
        if rolAdmin:
            rolAdmin.vistas = todasLasVistas
        if rolAnalista:
            rolAnalista.vistas = todasLasVistas
        if rolOperador and not rolOperador.vistas:
            rolOperador.vistas = [todasLasVistas[0]]

    # 7. Sincronización automática de CuboModelo para vistas existentes
    usuarioAdmin = sesion.query(UsuarioModelo).filter_by(nombreUsuario="admin").first()
    idAdmin = usuarioAdmin.idUsuario if usuarioAdmin else 1

    for v in todasLasVistas:
        if v.estadoHabilitado is None:
            v.estadoHabilitado = True
        if v.creadoPorUsuarioId is None:
            v.creadoPorUsuarioId = idAdmin
        if v.idCubo is None and v.rutaArchivoParquet:
            cuboExistente = sesion.query(CuboModelo).filter_by(archivoParquet=v.rutaArchivoParquet).first()
            if not cuboExistente:
                tipo = "SQL_EN_VIVO" if v.tipoIngesta == "SqlEnVivo" else (
                    "EXCEL" if "Excel" in (v.tipoIngesta or "") else (
                        "COMPUESTO" if v.tipoIngesta == "CuboCompuesto" else "PROCESO_MASIVO"
                    )
                )
                cuboNuevo = CuboModelo(
                    nombreCubo=f"cubo_{v.codigoVista}",
                    archivoParquet=v.rutaArchivoParquet,
                    tipoOrigen=tipo,
                    configuracionOrigenJson=v.contratoEsquemaJson,
                    estadoHabilitado=True,
                    fechaUltimaCarga=v.fechaUltimaEjecucion or datetime.utcnow(),
                    metadatosColumnasJson=v.contratoEsquemaJson
                )
                sesion.add(cuboNuevo)
                sesion.flush()
                v.idCubo = cuboNuevo.idCubo
            else:
                v.idCubo = cuboExistente.idCubo

    # 8. Registro del cubo de Siniestros si existe en almacenamiento/parquets
    rutaSiniestros = os.path.join(directorioAlmacenamiento, "parquets", "cuboSiniestrosGeneral.parquet")
    if os.path.exists(rutaSiniestros):
        codigo = "cuboSiniestrosGeneral"
        vistaExistente = sesion.query(VistaModelo).filter_by(codigoVista=codigo).first()
        rutaCompleta = os.path.abspath(rutaSiniestros)
        cubo = sesion.query(CuboModelo).filter(
            (CuboModelo.archivoParquet == rutaCompleta) | (CuboModelo.nombreCubo == f"cubo_{codigo}")
        ).first()
        if not cubo:
            cubo = CuboModelo(
                nombreCubo=f"cubo_{codigo}",
                archivoParquet=rutaCompleta,
                tipoOrigen="SQL_EN_VIVO",
                estadoHabilitado=True,
                fechaUltimaCarga=datetime.utcnow()
            )
            sesion.add(cubo)
            sesion.flush()
        else:
            cubo.archivoParquet = rutaCompleta

        if not vistaExistente:
            vistaNueva = VistaModelo(
                codigoVista=codigo,
                nombreVista="Siniestros Generales",
                descripcion="Cubo analítico de Siniestros Generales",
                tipoIngesta="SqlEnVivo",
                rutaArchivoParquet=rutaCompleta,
                fechaUltimaEjecucion=datetime.utcnow(),
                activo=True,
                idCubo=cubo.idCubo,
                creadoPorUsuarioId=idAdmin,
                estadoHabilitado=True
            )
            sesion.add(vistaNueva)
            sesion.flush()
            vistaExistente = vistaNueva
        else:
            vistaExistente.nombreVista = "Siniestros Generales"
            vistaExistente.descripcion = "Cubo analítico de Siniestros Generales"
            vistaExistente.rutaArchivoParquet = rutaCompleta
            vistaExistente.idCubo = cubo.idCubo

        if rolAdmin and vistaExistente not in rolAdmin.vistas:
            rolAdmin.vistas.append(vistaExistente)
        if rolAnalista and vistaExistente not in rolAnalista.vistas:
            rolAnalista.vistas.append(vistaExistente)

    sesion.commit()


def inicializarBaseDatos() -> None:
    """
    Crea las tablas en la base de datos si no existen, aplica migraciones automáticas y ejecuta el sembrado inicial.
    """
    BaseModelo.metadata.create_all(bind=motorBaseDatos)

    # Migraciones preventivas seguras para SQLite en esquemas existentes
    columnasNuevas = [
        "ALTER TABLE vistas ADD COLUMN configuracion_json TEXT;",
        "ALTER TABLE vistas ADD COLUMN id_cubo INTEGER;",
        "ALTER TABLE vistas ADD COLUMN creado_por_usuario_id INTEGER;",
        "ALTER TABLE vistas ADD COLUMN estado_habilitado BOOLEAN DEFAULT 1;",
        "ALTER TABLE vistas ADD COLUMN fecha_modificacion DATETIME;"
    ]
    from sqlalchemy import text
    with motorBaseDatos.connect() as con:
        for alterSql in columnasNuevas:
            try:
                con.execute(text(alterSql))
                con.commit()
            except Exception:
                # La columna ya existe o la base relacional no requiere esta migración
                pass

    with obtenerSesion() as sesion:
        sembrarDatosIniciales(sesion)
