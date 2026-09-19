"""
Script de depuración de tablas heredadas y creación del esquema relacional del Sistema Analítico en SQL Server.
Configurable vía variables de entorno (SQL_SERVER_HOST, SQL_SERVER_DB, etc.).
"""

import os
import sys
import logging
import urllib.parse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Garantizar resolución de rutas del proyecto
directorioActual = os.path.dirname(os.path.abspath(__file__))
directorioRaiz = os.path.abspath(os.path.join(directorioActual, "..", "..", ".."))
if directorioRaiz not in sys.path:
    sys.path.insert(0, directorioRaiz)

from sistemaAnalitica.modulos.seguridad.modelos import (
    BaseModelo, RolModelo, PermisoModelo, UsuarioModelo,
    PantallaModelo, RolPantallaModelo, RolVistaModelo,
    CuboModelo, VistaModelo
)
from sistemaAnalitica.modulos.seguridad.baseDatos import sembrarDatosIniciales

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("MigradorSqlServer")

# Configuración de conexión parametrizable
SERVIDOR_SQL = os.getenv("SQL_SERVER_HOST", "").strip()
BASE_DATOS_SQL = os.getenv("SQL_SERVER_DB", "").strip()
USUARIO_SQL = os.getenv("SQL_SERVER_USER", "").strip()
PASSWORD_SQL = os.getenv("SQL_SERVER_PASS", "").strip()
DRIVER_ODBC = os.getenv("SQL_SERVER_DRIVER", "ODBC Driver 17 for SQL Server")

CADENA_CONEXION_SQLSERVER = ""
if SERVIDOR_SQL and BASE_DATOS_SQL:
    paramsConn = urllib.parse.quote_plus(
        f"DRIVER={{{DRIVER_ODBC}}};"
        f"SERVER={SERVIDOR_SQL};"
        f"DATABASE={BASE_DATOS_SQL};"
        f"UID={USUARIO_SQL};"
        f"PWD={PASSWORD_SQL};"
        f"TrustServerCertificate=yes;"
    )
    CADENA_CONEXION_SQLSERVER = f"mssql+pyodbc:///?odbc_connect={paramsConn}"


def depurarTablasExistentes(engine) -> None:
    """
    Elimina de forma segura todas las restricciones de clave foránea y tablas existentes en TESTDB.
    """
    logger.info("Iniciando depuración de tablas existentes en TESTDB...")
    with engine.connect() as conexion:
        # 1. Obtener y eliminar todas las Foreign Keys
        consultaFks = text("""
            SELECT 
                fk.name AS nombreFk,
                OBJECT_SCHEMA_NAME(fk.parent_object_id) AS esquemaTabla,
                OBJECT_NAME(fk.parent_object_id) AS nombreTabla
            FROM sys.foreign_keys fk
        """)
        fks = conexion.execute(consultaFks).fetchall()
        logger.info(f"Se encontraron {len(fks)} restricciones de clave foránea para eliminar.")
        for fk in fks:
            sqlDropFk = f"ALTER TABLE [{fk.esquemaTabla}].[{fk.nombreTabla}] DROP CONSTRAINT [{fk.nombreFk}]"
            conexion.execute(text(sqlDropFk))

        # 2. Obtener y eliminar todas las tablas base
        consultaTablas = text("""
            SELECT TABLE_SCHEMA, TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_TYPE = 'BASE TABLE'
        """)
        tablas = conexion.execute(consultaTablas).fetchall()
        logger.info(f"Se encontraron {len(tablas)} tablas existentes para eliminar.")
        for t in tablas:
            logger.info(f"Eliminando tabla: [{t.TABLE_SCHEMA}].[{t.TABLE_NAME}]...")
            conexion.execute(text(f"DROP TABLE [{t.TABLE_SCHEMA}].[{t.TABLE_NAME}]"))

        conexion.commit()
    logger.info("Depuración completada. La base de datos TESTDB está completamente limpia.")


def crearEsquemaRelacional(engine) -> None:
    """
    Crea las tablas requeridas por el Sistema Analítico usando SQLAlchemy BaseModelo.
    """
    logger.info("Creando tablas del Sistema Analítico...")
    BaseModelo.metadata.create_all(bind=engine)
    logger.info("Tablas creadas exitosamente mediante SQLAlchemy metadata.")


def migrarDatosDesdeSqlite(engineSqlServer) -> None:
    """
    Migra cubos y vistas existentes en SQLite a SQL Server para preservar el estado operativo.
    """
    rutaSqlite = os.path.join(directorioRaiz, "sistemaAnalitica", "almacenamiento", "controlAnalitica.db")
    if not os.path.exists(rutaSqlite):
        logger.info("No se encontró base SQLite previa. Omitiendo migración de datos.")
        return

    logger.info("Sincronizando vistas y cubos desde SQLite local...")
    motorSqlite = create_engine(f"sqlite:///{rutaSqlite}")
    SesionSqlite = sessionmaker(bind=motorSqlite)
    SesionSqlServer = sessionmaker(bind=engineSqlServer)

    with SesionSqlite() as sSqlite, SesionSqlServer() as sSql:
        # Migrar Cubos
        cubosSqlite = sSqlite.query(CuboModelo).all()
        idCuboMap = {}
        for c in cubosSqlite:
            cuboExistente = sSql.query(CuboModelo).filter_by(nombreCubo=c.nombreCubo).first()
            if not cuboExistente:
                nuevoCubo = CuboModelo(
                    nombreCubo=c.nombreCubo,
                    archivoParquet=c.archivoParquet,
                    tipoOrigen=c.tipoOrigen,
                    configuracionOrigenJson=c.configuracionOrigenJson,
                    estadoHabilitado=c.estadoHabilitado,
                    fechaUltimaCarga=c.fechaUltimaCarga,
                    metadatosColumnasJson=c.metadatosColumnasJson,
                    fechaCreacion=c.fechaCreacion
                )
                sSql.add(nuevoCubo)
                sSql.flush()
                idCuboMap[c.idCubo] = nuevoCubo.idCubo
            else:
                idCuboMap[c.idCubo] = cuboExistente.idCubo

        # Migrar Vistas
        vistasSqlite = sSqlite.query(VistaModelo).all()
        for v in vistasSqlite:
            vistaExistente = sSql.query(VistaModelo).filter_by(codigoVista=v.codigoVista).first()
            if not vistaExistente:
                nuevaVista = VistaModelo(
                    codigoVista=v.codigoVista,
                    nombreVista=v.nombreVista,
                    descripcion=v.descripcion,
                    tipoIngesta=v.tipoIngesta,
                    rutaArchivoParquet=v.rutaArchivoParquet,
                    contratoEsquemaJson=v.contratoEsquemaJson,
                    configuracionJson=v.configuracionJson,
                    consultaSql=v.consultaSql,
                    idCubo=idCuboMap.get(v.idCubo),
                    creadoPorUsuarioId=1,  # Asignado al admin
                    estadoHabilitado=v.estadoHabilitado,
                    fechaUltimaEjecucion=v.fechaUltimaEjecucion,
                    activo=v.activo,
                    fechaCreacion=v.fechaCreacion,
                    fechaModificacion=v.fechaModificacion
                )
                sSql.add(nuevaVista)
                sSql.flush()

                # Asignar a rol Administrador por defecto
                rolAdmin = sSql.query(RolModelo).filter_by(nombreRol="Administrador").first()
                if rolAdmin and nuevaVista not in rolAdmin.vistas:
                    rolAdmin.vistas.append(nuevaVista)

        sSql.commit()
    logger.info("Migración y sincronización de cubos y vistas completada.")


def ejecutarMigracionCompleta() -> None:
    """
    Orquesta todo el proceso de migración, depuración y sembrado.
    """
    logger.info(f"Conectando a SQL Server: {SERVIDOR_SQL} / {BASE_DATOS_SQL}...")
    engine = create_engine(CADENA_CONEXION_SQLSERVER, echo=False, pool_pre_ping=True)

    # 1. Depurar tablas heredadas
    depurarTablasExistentes(engine)

    # 2. Crear nuevo esquema
    crearEsquemaRelacional(engine)

    # 3. Sembrar datos iniciales institucionales (Roles, Permisos, Pantallas, Usuario admin)
    logger.info("Sembrando datos institucionales...")
    FabricaSesionesSql = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with FabricaSesionesSql() as sesion:
        sembrarDatosIniciales(sesion)
        sesion.commit()
    logger.info("Datos institucionales sembrados exitosamente.")

    # 4. Migrar cubos y vistas existentes para preservar operatividad
    migrarDatosDesdeSqlite(engine)

    # 5. Resumen final de verificación
    with engine.connect() as conexion:
        tablasFinales = conexion.execute(text("""
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """)).fetchall()

        logger.info(f"============================================================")
        logger.info(f"MIGRACIÓN COMPLETADA. Tablas creadas en {BASE_DATOS_SQL}: {len(tablasFinales)}")
        for t in tablasFinales:
            conteo = conexion.execute(text(f"SELECT COUNT(*) FROM [{t.TABLE_NAME}]")).fetchone()[0]
            logger.info(f" - {t.TABLE_NAME}: {conteo} registros")
        logger.info(f"============================================================")


if __name__ == "__main__":
    ejecutarMigracionCompleta()
