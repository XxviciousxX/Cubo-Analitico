"""
Gestor de consultas SQL en vivo y procesos masivos de Data Lake.
Incluye catálogo de conexiones y control de sobrecarga (Throttling de 5 minutos).
"""

from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Any, Optional
from decimal import Decimal
import re
import pandas as pd
from sqlalchemy import create_engine, text

from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import ConexionBaseDatosModelo, VistaModelo
from sistemaAnalitica.modulos.ingesta.generadorOBT import GeneradorOBT


class GestorSqlEnVivo:
    """
    Coordina la interacción con motores relacionales externos y la política de refresco controlado.
    """

    SEGUNDOS_BLOQUEO_THROTTLING = 300  # 5 minutos

    @staticmethod
    def esStoredProcedure(consultaSql: str) -> bool:
        """
        Determina si una sentencia SQL corresponde a la invocación de un Stored Procedure (EXEC / EXECUTE).
        """
        if not consultaSql:
            return False
        return bool(re.match(r'^\s*(?:exec|execute)\b', consultaSql.strip(), re.IGNORECASE))

    @classmethod
    def ejecutarStoredProcedure(cls, motor: Any, consultaSql: str) -> pd.DataFrame:
        """
        Ejecuta un Stored Procedure garantizando SET NOCOUNT ON y navegando entre conjuntos de resultados
        hasta obtener las columnas y filas reales generadas por el procedimiento.
        """
        sqlExec = consultaSql.strip()
        if not re.search(r'(?i)\bset\s+nocount\s+on\b', sqlExec):
            sqlExec = "SET NOCOUNT ON;\n" + sqlExec

        conexionCruda = motor.raw_connection()
        try:
            cursor = conexionCruda.cursor()
            try:
                cursor.execute("SET NOCOUNT ON;")
            except Exception:
                pass
            cursor.execute(sqlExec)
            # Avanzar si existen recordsets vacíos por sentencias DML o variables internas del SP
            while cursor.description is None:
                if not cursor.nextset():
                    break

            if cursor.description is not None:
                columnas = [desc[0] for desc in cursor.description]
                filas = cursor.fetchall()
                filasLimpias = [list(f) for f in filas]
                df = pd.DataFrame(filasLimpias, columns=columnas)
                # Coerción de columnas Decimal a float64 para prevenir desbordamiento de escala fija en DuckDB/Parquet
                for col in df.columns:
                    if df[col].dtype == object:
                        serieLimpia = df[col].dropna()
                        if not serieLimpia.empty and any(isinstance(v, Decimal) for v in serieLimpia.iloc[:25]):
                            df[col] = pd.to_numeric(df[col], errors="coerce")
                return df
            else:
                return pd.DataFrame()
        finally:
            try:
                conexionCruda.close()
            except Exception:
                pass

    @classmethod
    def limpiarClausulaLimite(cls, consultaSql: str) -> str:
        """
        Remueve de forma segura cláusulas de muestreo temporal como 'TOP <N>' o 'LIMIT <N>'
        para permitir que la consulta materialice el conjunto de datos analítico completo.
        Si la sentencia es un Stored Procedure (EXEC), se conserva intacta sin alterar sus parámetros.
        """
        if not consultaSql:
            return ""
        if cls.esStoredProcedure(consultaSql):
            return consultaSql.strip()

        sql = consultaSql.strip()
        # 1. Remover TOP <N> o TOP (<N>) después de SELECT o SELECT DISTINCT
        patronTop = r'(?i)\b(SELECT(?:\s+DISTINCT)?)\s+TOP\s*\(?\s*\d+\s*\)?\s*'
        sql = re.sub(patronTop, r'\1 ', sql)
        # 2. Remover LIMIT <N> al final de la consulta (con o sin punto y coma)
        patronLimit = r'(?i)\s+LIMIT\s+\d+\s*(;?)\s*$'
        sql = re.sub(patronLimit, r'\1', sql)
        return sql.strip()

    @classmethod
    def listarConexiones(cls) -> List[Dict[str, Any]]:
        """
        Devuelve el catálogo de conexiones configuradas en la base de control.
        """
        with obtenerSesion() as sesion:
            conexiones = sesion.query(ConexionBaseDatosModelo).filter_by(activo=True).all()
            return [
                {
                    "idConexion": c.idConexion,
                    "nombreConexion": c.nombreConexion,
                    "motorBaseDatos": c.motorBaseDatos,
                    "cadenaConexion": c.cadenaConexion,
                    "descripcion": c.descripcion
                }
                for c in conexiones
            ]

    @classmethod
    def registrarConexion(
        cls,
        nombreConexion: str,
        motorBaseDatos: str,
        cadenaConexion: str,
        descripcion: str = ""
    ) -> ConexionBaseDatosModelo:
        """
        Registra una nueva cadena de conexión en el catálogo relacional.
        """
        with obtenerSesion() as sesion:
            conexionExistente = sesion.query(ConexionBaseDatosModelo).filter_by(
                nombreConexion=nombreConexion.strip()
            ).first()

            if conexionExistente:
                conexionExistente.cadenaConexion = cadenaConexion.strip()
                conexionExistente.motorBaseDatos = motorBaseDatos.strip()
                conexionExistente.descripcion = descripcion.strip()
                conexionExistente.activo = True
                sesion.commit()
                return conexionExistente

            nuevaConexion = ConexionBaseDatosModelo(
                nombreConexion=nombreConexion.strip(),
                motorBaseDatos=motorBaseDatos.strip(),
                cadenaConexion=cadenaConexion.strip(),
                descripcion=descripcion.strip(),
                activo=True
            )
            sesion.add(nuevaConexion)
            sesion.commit()
            sesion.refresh(nuevaConexion)
            return nuevaConexion

    @classmethod
    def probarConexion(cls, cadenaConexion: str) -> Tuple[bool, str]:
        """
        Valida la conectividad contra el origen de datos relacional.
        """
        try:
            motorPrueba = create_engine(cadenaConexion.strip())
            with motorPrueba.connect() as conexion:
                conexion.execute(text("SELECT 1"))
            return True, "Conexión exitosa al motor de base de datos."
        except Exception as errorConexion:
            return False, f"Fallo al conectar: {str(errorConexion)}"

    @classmethod
    def ejecutarMuestraSql(
        cls,
        cadenaConexion: str,
        consultaSql: str,
        limiteMuestra: int = 10
    ) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Ejecuta una consulta agregando TOP o LIMIT para extraer cabeceras y muestra sin sobrecargar.
        Si la consulta es un Stored Procedure (EXEC), se ejecuta directamente en su totalidad sin TOP/LIMIT.
        """
        try:
            motor = create_engine(cadenaConexion.strip())
            consultaLimpia = consultaSql.strip().rstrip(";")

            # Si es un Stored Procedure, ejecutar directamente y tomar el conjunto de resultados completo
            if cls.esStoredProcedure(consultaLimpia):
                dataframeMuestra = cls.ejecutarStoredProcedure(motor, consultaLimpia)
                return dataframeMuestra, None

            # Si la consulta SELECT no tiene límite explícito, envolver en subconsulta limitada
            if "top " not in consultaLimpia.lower() and "limit " not in consultaLimpia.lower():
                consultaMuestra = f"SELECT * FROM ({consultaLimpia}) AS subconsulta_muestra LIMIT {limiteMuestra}"
            else:
                consultaMuestra = consultaLimpia

            try:
                dataframeMuestra = pd.read_sql(text(consultaMuestra), motor)
            except Exception:
                # Fallback para motores como SQL Server que no aceptan LIMIT
                consultaMuestraSqlServer = f"SELECT TOP {limiteMuestra} * FROM ({consultaLimpia}) AS subconsulta_muestra"
                dataframeMuestra = pd.read_sql(text(consultaMuestraSqlServer), motor)

            return dataframeMuestra, None
        except Exception as errorEjecucion:
            return None, f"Error ejecutando consulta de prueba: {str(errorEjecucion)}"

    @classmethod
    def inferirEsquemaMasivo(
        cls,
        cadenaConexion: str,
        consultaSql: str
    ) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """
        Flujo 3: Ejecuta la consulta con WHERE 1 = 0 para inferir el esquema a costo cero en producción.
        Para Stored Procedures, se ejecuta directamente.
        """
        try:
            motor = create_engine(cadenaConexion.strip())
            consultaLimpia = consultaSql.strip().rstrip(";")

            if cls.esStoredProcedure(consultaLimpia):
                return cls.ejecutarMuestraSql(cadenaConexion, consultaLimpia)

            consultaVacia = f"SELECT * FROM ({consultaLimpia}) AS esquema_vacio WHERE 1 = 0"

            dataframeVacio = pd.read_sql(text(consultaVacia), motor)
            return dataframeVacio, None
        except Exception as errorInferencia:
            # Si falla el WHERE 1=0, intentar con TOP 1
            return cls.ejecutarMuestraSql(cadenaConexion, consultaSql, limiteMuestra=1)

    @classmethod
    def verificarThrottling(cls, idVista: int) -> Tuple[bool, int, Optional[str]]:
        """
        Evalúa si la vista tiene permitido ejecutar 'Actualizar Datos'.
        Retorna (puedeEjecutar: bool, segundosRestantes: int, mensaje: Optional[str]).
        """
        with obtenerSesion() as sesion:
            vista = sesion.query(VistaModelo).filter_by(idVista=idVista).first()
            if not vista:
                return False, 0, "La vista analítica especificada no existe."

            if not vista.fechaUltimaEjecucion:
                return True, 0, None

            tiempoTranscurrido = datetime.utcnow() - vista.fechaUltimaEjecucion
            segundosPasados = int(tiempoTranscurrido.total_seconds())

            if segundosPasados < cls.SEGUNDOS_BLOQUEO_THROTTLING:
                segundosRestantes = cls.SEGUNDOS_BLOQUEO_THROTTLING - segundosPasados
                minutos = segundosRestantes // 60
                segundos = segundosRestantes % 60
                mensajeBloqueo = (
                    f"Protección de sobrecarga activa (Throttling de 5 min). "
                    f"Debes esperar {minutos:02d}:{segundos:02d} antes de refrescar nuevamente."
                )
                return False, segundosRestantes, mensajeBloqueo

            return True, 0, None

    @classmethod
    def ejecutarYMaterializarParquet(
        cls,
        idVista: int,
        rutaDestinoParquet: str
    ) -> Tuple[bool, str, int]:
        """
        Ejecuta la consulta completa de una vista SQL en vivo, valida el throttling,
        actualiza la marca temporal y materializa el resultado en Apache Parquet.
        """
        with obtenerSesion() as sesion:
            vista = sesion.query(VistaModelo).filter_by(idVista=idVista).first()
            if not vista:
                return False, "Vista no encontrada en catálogo.", 0

            # 1. Validar política de throttling
            puede, segundosRestantes, mensaje = cls.verificarThrottling(idVista)
            if not puede:
                return False, mensaje or "Bloqueo por throttling.", segundosRestantes

            if not vista.idConexion or not vista.consultaSql:
                return False, "La vista no tiene configurada una conexión o consulta SQL.", 0

            conexionObj = sesion.query(ConexionBaseDatosModelo).filter_by(idConexion=vista.idConexion).first()
            if not conexionObj:
                return False, "Conexión a base de datos huérfana o inexistente.", 0

            cadena = conexionObj.cadenaConexion
            sql = vista.consultaSql

        # 2. Ejecución completa
        try:
            motor = create_engine(cadena)
            if cls.esStoredProcedure(sql):
                dataframeCompleto = cls.ejecutarStoredProcedure(motor, sql)
            else:
                dataframeCompleto = pd.read_sql(text(sql), motor)

            # 3. Guardar en Parquet
            GeneradorOBT.guardarEnParquet(dataframeCompleto, rutaDestinoParquet)

            # 4. Actualizar fecha de última ejecución
            with obtenerSesion() as sesionActualizacion:
                vistaActualizada = sesionActualizacion.query(VistaModelo).filter_by(idVista=idVista).first()
                if vistaActualizada:
                    vistaActualizada.fechaUltimaEjecucion = datetime.utcnow()
                    vistaActualizada.rutaArchivoParquet = rutaDestinoParquet
                    sesionActualizacion.commit()

            return True, f"Datos actualizados y materializados ({len(dataframeCompleto)} filas).", 0

        except Exception as errorEjecucion:
            return False, f"Fallo al ejecutar y materializar: {str(errorEjecucion)}", 0
