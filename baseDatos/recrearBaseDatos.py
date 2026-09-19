"""
Script Utilitario de Recreación y Sembrado de Base de Datos para Cubix.
Permite a cualquier desarrollador o agente inicializar el esquema relacional
completo y los datos maestros (roles, permisos, pantallas, usuarios del sistema
y registro de cubos Parquet) en Supabase (PostgreSQL), SQLite local o SQL Server.

Uso:
    python baseDatos/recrearBaseDatos.py [--motor postgres|sqlite|sqlserver] [--forzar]
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from dotenv import load_dotenv

# Garantizar resolución de rutas
directorioActual = os.path.dirname(os.path.abspath(__file__))
directorioProyecto = os.path.abspath(os.path.join(directorioActual, ".."))
if directorioProyecto not in sys.path:
    sys.path.insert(0, directorioProyecto)

rutaEnv = os.path.join(directorioProyecto, ".env")
if os.path.exists(rutaEnv):
    load_dotenv(rutaEnv)
else:
    load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RecrearBaseDatos")


def recrearBaseDatos(motor: str = "postgres", forzar: bool = False) -> None:
    directorioAlmacenamiento = os.path.join(directorioProyecto, "sistemaAnalitica", "almacenamiento")
    os.makedirs(directorioAlmacenamiento, exist_ok=True)
    directorioParquets = os.path.join(directorioAlmacenamiento, "parquets")
    os.makedirs(directorioParquets, exist_ok=True)

    rutaSqlite = os.path.join(directorioAlmacenamiento, "controlAnalitica.db")

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from sistemaAnalitica.modulos.seguridad.modelos import (
        BaseModelo, RolModelo, PermisoModelo, UsuarioModelo,
        PantallaModelo, CuboModelo, VistaModelo
    )
    from sistemaAnalitica.modulos.seguridad.baseDatos import (
        sembrarDatosIniciales, motorBaseDatos
    )

    motorLower = motor.lower()

    if motorLower in ["postgres", "postgresql", "supabase"]:
        cadenaConexion = os.getenv("DATABASE_URL", "").strip()
        if not cadenaConexion:
            logger.error("Para usar PostgreSQL/Supabase asegúrese de que DATABASE_URL esté definida en .env.")
            sys.exit(1)

        # Normalizar prefijo para SQLAlchemy y psycopg2
        if cadenaConexion.startswith("postgres://"):
            cadenaConexion = cadenaConexion.replace("postgres://", "postgresql+psycopg2://", 1)
        elif cadenaConexion.startswith("postgresql://") and not cadenaConexion.startswith("postgresql+"):
            cadenaConexion = cadenaConexion.replace("postgresql://", "postgresql+psycopg2://", 1)

        logger.info("Conectando a base de datos PostgreSQL (Supabase)...")
        engine = create_engine(cadenaConexion, echo=False, pool_pre_ping=True, pool_recycle=300)

        # Validar conexión
        with engine.connect() as con:
            pass
        logger.info("Conexión a PostgreSQL establecida con éxito.")

        if forzar:
            logger.warning("Limpiando todas las tablas preexistentes en el esquema 'public'...")
            with engine.connect() as con:
                scriptPurga = """
                DO $$ 
                DECLARE 
                    r RECORD;
                BEGIN
                    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                        EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END $$;
                """
                con.execute(text(scriptPurga))
                con.commit()
            logger.info("Todas las tablas previas en el esquema 'public' fueron eliminadas exitosamente.")

    elif motorLower == "sqlite":
        if forzar and os.path.exists(rutaSqlite):
            logger.warning(f"Limpiando base de datos SQLite previa: {rutaSqlite}")
            try:
                os.remove(rutaSqlite)
            except PermissionError:
                logger.info("El archivo SQLite tiene un lock temporal. Procediendo a recrear sobreescribiendo tablas existentes.")
        engine = create_engine(f"sqlite:///{rutaSqlite}", echo=False, connect_args={"check_same_thread": False})
        logger.info(f"Usando motor SQLite: {rutaSqlite}")

    elif motorLower == "sqlserver":
        import urllib.parse
        host = os.getenv("SQL_SERVER_HOST", "").strip()
        db = os.getenv("SQL_SERVER_DB", "").strip()
        user = os.getenv("SQL_SERVER_USER", "").strip()
        pwd = os.getenv("SQL_SERVER_PASS", "").strip()
        driver = os.getenv("SQL_SERVER_DRIVER", "ODBC Driver 17 for SQL Server")

        if not host or not db:
            logger.error("Para usar SQL Server configure las variables SQL_SERVER_HOST y SQL_SERVER_DB en .env.")
            sys.exit(1)

        paramsConn = urllib.parse.quote_plus(
            f"DRIVER={{{driver}}};"
            f"SERVER={host};"
            f"DATABASE={db};"
            f"UID={user};"
            f"PWD={pwd};"
            f"TrustServerCertificate=yes;"
            f"LoginTimeout=10;"
        )
        cadenaConexion = f"mssql+pyodbc:///?odbc_connect={paramsConn}"
        engine = create_engine(cadenaConexion, echo=False, pool_pre_ping=True)
        logger.info(f"Conectando a SQL Server en {host}/{db}...")
    else:
        logger.error(f"Motor no soportado: {motor}. Utilice 'postgres', 'sqlite' o 'sqlserver'.")
        sys.exit(1)

    # 1. Crear Esquema
    logger.info("Creando tablas relacionales en la base de datos...")
    BaseModelo.metadata.create_all(bind=engine)
    logger.info("Esquema relacional creado exitosamente.")

    # 2. Sembrar Datos Maestros
    Fabrica = sessionmaker(bind=engine)
    with Fabrica() as sesion:
        logger.info("Sembrando roles, permisos, pantallas y usuarios (admin, analista, operador)...")
        sembrarDatosIniciales(sesion)

        # 3. Registrar Cubos Parquet existentes
        if os.path.exists(directorioParquets):
            archivosParquet = [f for f in os.listdir(directorioParquets) if f.endswith(".parquet")]
            logger.info(f"Escaneando parquets en {directorioParquets}: {len(archivosParquet)} encontrados.")

            admin = sesion.query(UsuarioModelo).filter_by(nombreUsuario="admin").first()
            idAdmin = admin.idUsuario if admin else 1

            for arch in archivosParquet:
                rutaAbs = os.path.abspath(os.path.join(directorioParquets, arch))
                nombreBase = os.path.splitext(arch)[0]
                cuboExistente = sesion.query(CuboModelo).filter(
                    (CuboModelo.archivoParquet == rutaAbs) | (CuboModelo.nombreCubo == f"cubo_{nombreBase}")
                ).first()
                if not cuboExistente:
                    cuboNuevo = CuboModelo(
                        nombreCubo=f"cubo_{nombreBase}",
                        archivoParquet=rutaAbs,
                        tipoOrigen="PROCESO_MASIVO",
                        estadoHabilitado=True,
                        fechaUltimaCarga=datetime.utcnow()
                    )
                    sesion.add(cuboNuevo)
                    sesion.flush()
                    cuboActual = cuboNuevo
                    logger.info(f"Registrado cubo: cubo_{nombreBase} -> {arch}")
                else:
                    cuboExistente.archivoParquet = rutaAbs
                    cuboActual = cuboExistente

                vistaExistente = sesion.query(VistaModelo).filter_by(codigoVista=nombreBase).first()
                if not vistaExistente:
                    vistaNueva = VistaModelo(
                        codigoVista=nombreBase,
                        nombreVista=nombreBase.replace("_", " ").title(),
                        descripcion=f"Vista analítica basada en {arch}",
                        tipoIngesta="ProcesoMasivo",
                        rutaArchivoParquet=rutaAbs,
                        fechaUltimaEjecucion=datetime.utcnow(),
                        activo=True,
                        idCubo=cuboActual.idCubo,
                        creadoPorUsuarioId=idAdmin,
                        estadoHabilitado=True
                    )
                    sesion.add(vistaNueva)
                    sesion.flush()
                    logger.info(f"Registrada vista: {nombreBase}")
                    rolAdmin = sesion.query(RolModelo).filter_by(nombreRol="Administrador").first()
                    rolAnalista = sesion.query(RolModelo).filter_by(nombreRol="Analista de Datos").first()
                    if rolAdmin and vistaNueva not in rolAdmin.vistas:
                        rolAdmin.vistas.append(vistaNueva)
                    if rolAnalista and vistaNueva not in rolAnalista.vistas:
                        rolAnalista.vistas.append(vistaNueva)
                else:
                    vistaExistente.rutaArchivoParquet = rutaAbs
                    vistaExistente.idCubo = cuboActual.idCubo

            sesion.commit()

    logger.info("====================================================================")
    logger.info("  RECREACION Y SEMBRADO COMPLETADOS CON EXITO")
    logger.info("  Roles creados: Administrador, Analista de Datos, Operador")
    logger.info("  Usuarios y Credenciales:")
    logger.info("    1. Administrador: admin    |  Clave: admin")
    logger.info("    2. Analista:      analista |  Clave: analista")
    logger.info("    3. Operador:      operador |  Clave: operador")
    logger.info("====================================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recrear y sembrar base de datos para Cubix.")
    parser.add_argument("--motor", choices=["postgres", "supabase", "sqlite", "sqlserver"], default="postgres", help="Motor relacional (default: postgres)")
    parser.add_argument("--forzar", action="store_true", help="Forzar purga y recreación limpia de esquemas")
    args = parser.parse_args()

    recrearBaseDatos(motor=args.motor, forzar=args.forzar)

