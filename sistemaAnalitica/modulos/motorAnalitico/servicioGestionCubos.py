"""
Servicio de Gestión y Gobernanza del Ciclo de Vida de Cubos y Vistas Analíticas.
Controla el ciclo de vida de los cubos Parquet OBT, refresco de datos según origen,
y validación de impacto semántico garantizando la integridad de vistas activas.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import duckdb
import pandas as pd
from sqlalchemy import text, create_engine

from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import (
    CuboModelo, VistaModelo, UsuarioModelo, ConexionBaseDatosModelo, ConfiguracionVistaEsquema,
    LogAuditoriaEliminacionModelo, ExcepcionUsuarioModelo, FiltroSeguridadFilaModelo
)
from sistemaAnalitica.modulos.ingesta.calamineLector import CalamineLectorExcel
from sistemaAnalitica.modulos.ingesta.validadorContratos import ValidadorContratos
from sistemaAnalitica.modulos.ingesta.generadorOBT import GeneradorOBT
from sistemaAnalitica.modulos.ingesta.gestorSqlEnVivo import GestorSqlEnVivo
from sistemaAnalitica.modulos.ingesta.generadorCuboCompuesto import GeneradorCuboCompuesto
from sistemaAnalitica.modulos.motorAnalitico.servicioPersistenciaCubos import ServicioPersistenciaCubos


class ServicioGestionCubos:
    """
    Servicio encargado de la gobernanza de cubos y vistas, auditoría y control de impacto.
    """

    @classmethod
    def normalizarRutaSql(cls, rutaArchivo: str) -> str:
        """
        Normaliza rutas para DuckDB en sistemas Windows.
        """
        return os.path.abspath(rutaArchivo).replace("\\", "/")

    @classmethod
    def conmutarEstadoCubo(cls, idCubo: int, nuevoEstado: bool) -> Dict[str, Any]:
        """
        Activa o desactiva un cubo analítico OBT.
        Si se desactiva, las consultas dirigidas a vistas dependientes serán rechazadas.
        """
        with obtenerSesion() as sesion:
            cubo = sesion.query(CuboModelo).filter_by(idCubo=idCubo).first()
            if not cubo:
                return {"exito": False, "error": f"Cubo con ID {idCubo} no encontrado."}

            cubo.estadoHabilitado = nuevoEstado
            sesion.commit()

            estadoTexto = "habilitado" if nuevoEstado else "deshabilitado"
            return {
                "exito": True,
                "idCubo": cubo.idCubo,
                "nombreCubo": cubo.nombreCubo,
                "estadoHabilitado": cubo.estadoHabilitado,
                "mensaje": f"El cubo '{cubo.nombreCubo}' ha sido {estadoTexto} exitosamente."
            }

    @classmethod
    def conmutarEstadoVista(cls, idVista: int, nuevoEstado: bool) -> Dict[str, Any]:
        """
        Activa o desactiva granularmente una vista analítica.
        """
        with obtenerSesion() as sesion:
            vista = sesion.query(VistaModelo).filter_by(idVista=idVista).first()
            if not vista:
                return {"exito": False, "error": f"Vista con ID {idVista} no encontrada."}

            vista.estadoHabilitado = nuevoEstado
            vista.fechaModificacion = datetime.utcnow()
            sesion.commit()

            estadoTexto = "habilitada" if nuevoEstado else "deshabilitada"
            return {
                "exito": True,
                "idVista": vista.idVista,
                "codigoVista": vista.codigoVista,
                "nombreVista": vista.nombreVista,
                "estadoHabilitado": vista.estadoHabilitado,
                "mensaje": f"La vista '{vista.nombreVista}' ha sido {estadoTexto} exitosamente."
            }

    @classmethod
    def validarImpactoColumnas(cls, idCubo: int, nuevasColumnas: List[str]) -> Dict[str, Any]:
        """
        Inspecciona todas las vistas activas asociadas al cubo para asegurar que ninguna
        dependa de columnas que vayan a ser eliminadas del esquema.
        """
        conjuntoNuevasColumnas = {col.lower() for col in nuevasColumnas}

        with obtenerSesion() as sesion:
            cubo = sesion.query(CuboModelo).filter_by(idCubo=idCubo).first()
            if not cubo:
                return {"permitido": False, "error": f"Cubo con ID {idCubo} no encontrado.", "vistasAfectadas": []}

            vistasActivas = sesion.query(VistaModelo).filter_by(
                idCubo=idCubo,
                estadoHabilitado=True,
                activo=True
            ).all()

            vistasAfectadas = []
            columnasEnConflictoGlobal = set()

            for v in vistasActivas:
                columnasRequeridasVista = set()

                # 1. Extraer columnas desde configuracionJson
                if v.configuracionJson:
                    try:
                        cfg = json.loads(v.configuracionJson)
                        grano = cfg.get("granoPermitido", {})
                        for dim in grano.get("dimensionesVisibles", []):
                            columnasRequeridasVista.add(dim)
                        for met in grano.get("metricas", []):
                            if isinstance(met, dict) and "columna" in met:
                                columnasRequeridasVista.add(met["columna"])
                            elif isinstance(met, str):
                                columnasRequeridasVista.add(met)

                        cfgVisual = cfg.get("configuracionVisual", {})
                        if cfgVisual.get("dimensionPredeterminada"):
                            columnasRequeridasVista.add(cfgVisual["dimensionPredeterminada"])
                        if cfgVisual.get("metricaPredeterminada"):
                            columnasRequeridasVista.add(cfgVisual["metricaPredeterminada"])

                        for j in grano.get("jerarquiaDrilldownPermitida", []):
                            columnasRequeridasVista.add(j)

                        # Filtros configurados
                        for f in grano.get("filtros", []) or cfg.get("filtros", []):
                            if isinstance(f, dict) and "columna" in f:
                                columnasRequeridasVista.add(f["columna"])
                    except Exception:
                        pass

                # 2. Si no hay configuracionJson pero sí contratoEsquemaJson
                if not columnasRequeridasVista and v.contratoEsquemaJson:
                    try:
                        contrato = json.loads(v.contratoEsquemaJson)
                        for col in contrato.get("columnas", []):
                            if col.get("clasificacionSemantica") != "Identificador/Descarte":
                                colNombre = col.get("nombreColumna") or col.get("nombreFinal")
                                if colNombre:
                                    columnasRequeridasVista.add(colNombre)
                    except Exception:
                        pass

                # Verificar si alguna columna requerida falta en nuevasColumnas
                columnasFaltantes = [
                    col for col in columnasRequeridasVista
                    if col.lower() not in conjuntoNuevasColumnas
                ]

                if columnasFaltantes:
                    columnasEnConflictoGlobal.update(columnasFaltantes)
                    vistasAfectadas.append({
                        "idVista": v.idVista,
                        "codigoVista": v.codigoVista,
                        "nombreVista": v.nombreVista,
                        "columnasFaltantes": columnasFaltantes
                    })

            if vistasAfectadas:
                return {
                    "permitido": False,
                    "mensaje": (
                        f"Operación bloqueada: Hay {len(vistasAfectadas)} vista(s) activa(s) que "
                        f"dependen de columnas a eliminar o deshabilitar: {', '.join(sorted(columnasEnConflictoGlobal))}."
                    ),
                    "vistasAfectadas": vistasAfectadas,
                    "columnasEnConflicto": sorted(list(columnasEnConflictoGlobal))
                }

            return {
                "permitido": True,
                "mensaje": "Validación de impacto exitosa: No existen vistas activas en conflicto.",
                "vistasAfectadas": [],
                "columnasEnConflicto": []
            }

    @classmethod
    def analizarExcelParaActualizacion(
        cls,
        idCubo: int,
        archivoBytes: bytes
    ) -> Dict[str, Any]:
        """
        Inspecciona el libro Excel subido para actualización de un cubo.
        Detecta si todas las hojas son idénticas en columnas (unificación automática)
        o si existen hojas dimensionales diferentes que requieren establecer relaciones en estrella.
        """
        if not archivoBytes:
            return {"exito": False, "error": "No se recibió archivo Excel para analizar."}

        analisis = CalamineLectorExcel.analizarLibroCompleto(archivoBytes)
        if not analisis.get("exito"):
            return analisis

        with obtenerSesion() as sesion:
            cubo = sesion.query(CuboModelo).filter_by(idCubo=idCubo).first()
            if not cubo:
                return {"exito": False, "error": f"Cubo {idCubo} no encontrado."}

            contratoExistente = {}
            if cubo.configuracionOrigenJson:
                try:
                    contratoExistente = json.loads(cubo.configuracionOrigenJson)
                except Exception:
                    pass

            trazabilidad = contratoExistente.get("trazabilidadOrigenes", {})
            relacionesPrevias = trazabilidad.get("relacionesEstrella", [])

            # Validar preventivamente columnas del Excel entrante contra vistas analíticas activas
            colsExcel = [c["nombre"] for c in analisis.get("columnasHechos", [])]
            for dim in analisis.get("hojasDimensionales", []):
                for c in dim.get("columnas", []):
                    colsExcel.append(c["nombre"])

            if colsExcel:
                impacto = cls.validarImpactoColumnas(idCubo, colsExcel)
                if not impacto["permitido"]:
                    return {
                        "exito": False,
                        "bloqueoPorVistas": True,
                        "error": impacto["mensaje"],
                        "vistasAfectadas": impacto["vistasAfectadas"],
                        "columnasEnConflicto": impacto["columnasEnConflicto"]
                    }

            if analisis["esHomogeneo"]:
                return {
                    "exito": True,
                    "requiereRelacion": False,
                    "esHomogeneo": True,
                    "totalHojas": analisis["totalHojas"],
                    "hojasIdenticas": analisis["hojasIdenticas"],
                    "mensaje": f"Se detectaron {analisis['totalHojas']} hoja(s) con estructura idéntica. Se unificarán automáticamente en el cubo."
                }

            return {
                "exito": True,
                "requiereRelacion": True,
                "esHomogeneo": False,
                "totalHojas": analisis["totalHojas"],
                "hojasIdenticas": analisis["hojasIdenticas"],
                "totalHojasIdenticas": len(analisis["hojasIdenticas"]),
                "hojasDimensionales": analisis["hojasDimensionales"],
                "totalHojasDimensionales": len(analisis["hojasDimensionales"]),
                "llavesCandidatas": analisis["llavesCandidatas"],
                "relacionesPrevias": relacionesPrevias,
                "mensaje": f"Se detectaron {len(analisis['hojasIdenticas'])} hojas de hechos y {len(analisis['hojasDimensionales'])} hojas dimensionales diferentes. Por favor confirma o define la relación entre ellas."
            }

    @classmethod
    def actualizarDatosCubo(
        cls,
        idCubo: int,
        nuevoArchivoExcel: Optional[bytes] = None,
        relacionesJson: Optional[str] = None,
        hojasUnificarJson: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta el refresco de datos del cubo según su origen (Excel, SQL, Data Lake, Compuesto),
        reescribiendo atómicamente el archivo Parquet con compresión ZSTD y actualizando timestamps.
        Si el archivo Excel posee múltiples hojas idénticas las unifica automáticamente;
        si posee hojas distintas, aplica o solicita el modelado de relaciones en estrella.
        """
        with obtenerSesion() as sesion:
            cubo = sesion.query(CuboModelo).filter_by(idCubo=idCubo).first()
            if not cubo:
                return {"exito": False, "error": f"Cubo con ID {idCubo} no encontrado."}

            tipoOrigen = (cubo.tipoOrigen or "").upper()
            if "PROCESO_MASIVO" in tipoOrigen or "DATA_LAKE" in tipoOrigen or "LAKE" in tipoOrigen:
                return {
                    "exito": False,
                    "error": "Los cubos y vistas de origen Data Lake / Proceso Masivo son alimentados por ETLs externas masivas y no admiten recarga manual desde la interfaz."
                }

            rutaParquet = os.path.abspath(cubo.archivoParquet)
            os.makedirs(os.path.dirname(rutaParquet), exist_ok=True)

            # 1. ORIGEN EXCEL
            if "EXCEL" in tipoOrigen:
                if not nuevoArchivoExcel:
                    return {
                        "exito": False,
                        "error": "Para refrescar un cubo de origen Excel debes adjuntar el nuevo archivo .xlsx."
                    }

                # Analizar estructura del libro Excel entrante
                analisis = CalamineLectorExcel.analizarLibroCompleto(nuevoArchivoExcel)
                if not analisis.get("exito"):
                    return {"exito": False, "error": f"No se pudo analizar el libro Excel: {analisis.get('error')}"}

                # Parsear contrato existente
                contratoExistente = {}
                if cubo.configuracionOrigenJson:
                    try:
                        contratoExistente = json.loads(cubo.configuracionOrigenJson)
                    except Exception:
                        pass

                trazabilidad = contratoExistente.get("trazabilidadOrigenes", {})

                # Determinar hojas a unificar
                hojasAUnificar = []
                if hojasUnificarJson:
                    try:
                        hojasAUnificar = json.loads(hojasUnificarJson)
                    except Exception:
                        hojasAUnificar = []
                if not hojasAUnificar:
                    hojasAUnificar = analisis.get("hojasIdenticas", [])

                # Determinar relaciones
                relaciones = []
                if relacionesJson:
                    try:
                        relaciones = json.loads(relacionesJson)
                    except Exception:
                        relaciones = []
                if not relaciones and trazabilidad:
                    relaciones = trazabilidad.get("relacionesEstrella", [])

                # Escenario A: Hojas idénticas o no requiere relaciones (es homogéneo)
                if analisis["esHomogeneo"] or not analisis.get("hojasDimensionales"):
                    dfConsolidado = CalamineLectorExcel.unificarHojasIdenticas(
                        nuevoArchivoExcel,
                        hojasAUnificar,
                        columnaTrazadora="hoja_origen"
                    )

                    # Validar impacto contra vistas activas antes de sobrescribir el Parquet
                    impacto = cls.validarImpactoColumnas(idCubo, list(dfConsolidado.columns))
                    if not impacto["permitido"]:
                        return {
                            "exito": False,
                            "error": impacto["mensaje"],
                            "bloqueoPorVistas": True,
                            "vistasAfectadas": impacto["vistasAfectadas"],
                            "columnasEnConflicto": impacto["columnasEnConflicto"]
                        }

                    conexion = duckdb.connect()
                    try:
                        conexion.register("df_temporal_recarga", dfConsolidado)
                        rutaSql = cls.normalizarRutaSql(rutaParquet)
                        if os.path.exists(rutaParquet):
                            os.remove(rutaParquet)
                        conexion.execute(f"COPY df_temporal_recarga TO '{rutaSql}' (FORMAT PARQUET, COMPRESSION ZSTD)")
                        filasActuales = int(conexion.execute(f"SELECT COUNT(*) FROM read_parquet('{rutaSql}')").fetchone()[0])
                    finally:
                        conexion.close()

                    cubo.fechaUltimaCarga = datetime.utcnow()
                    for v in cubo.vistas:
                        v.fechaUltimaEjecucion = cubo.fechaUltimaCarga
                    ServicioPersistenciaCubos.persistirBinarioEnCubo(cubo, rutaParquet)
                    sesion.commit()

                    return {
                        "exito": True,
                        "mensaje": f"Datos del cubo '{cubo.nombreCubo}' refrescados exitosamente. Se unificaron {len(hojasAUnificar)} hoja(s).",
                        "totalFilas": filasActuales,
                        "fechaUltimaCarga": cubo.fechaUltimaCarga.strftime("%Y-%m-%d %H:%M:%S")
                    }

                # Escenario B: Hojas dimensionales presentes
                if relaciones:
                    dfHechos = CalamineLectorExcel.unificarHojasIdenticas(
                        nuevoArchivoExcel,
                        hojasAUnificar,
                        columnaTrazadora="hoja_origen"
                    )
                    mapaDimensiones = {}
                    for rel in relaciones:
                        nomDim = rel.get("nombreDimension") or rel.get("hojaDimension")
                        if nomDim and nomDim not in mapaDimensiones:
                            mapaDimensiones[nomDim] = CalamineLectorExcel.convertirHojaADataFrame(nuevoArchivoExcel, nomDim)

                    # Validar impacto contra vistas activas antes de generar esquema estrella
                    colsDisponibles = list(dfHechos.columns)
                    for dimDf in mapaDimensiones.values():
                        colsDisponibles.extend(list(dimDf.columns))
                    impacto = cls.validarImpactoColumnas(idCubo, colsDisponibles)
                    if not impacto["permitido"]:
                        return {
                            "exito": False,
                            "error": impacto["mensaje"],
                            "bloqueoPorVistas": True,
                            "vistasAfectadas": impacto["vistasAfectadas"],
                            "columnasEnConflicto": impacto["columnasEnConflicto"]
                        }

                    resGen = GeneradorCuboCompuesto.generarParquetEsquemaEstrella(
                        dfHechos=dfHechos,
                        mapaDimensiones=mapaDimensiones,
                        relaciones=relaciones,
                        columnasMapeadas=None,
                        rutaDestinoParquet=rutaParquet
                    )

                    # Actualizar trazabilidad en contrato
                    trazabilidad["hojasUnificadas"] = hojasAUnificar
                    trazabilidad["relacionesEstrella"] = relaciones
                    contratoExistente["trazabilidadOrigenes"] = trazabilidad
                    cubo.configuracionOrigenJson = json.dumps(contratoExistente)
                    cubo.fechaUltimaCarga = datetime.utcnow()
                    for v in cubo.vistas:
                        v.fechaUltimaEjecucion = cubo.fechaUltimaCarga
                    ServicioPersistenciaCubos.persistirBinarioEnCubo(cubo, rutaParquet)
                    sesion.commit()

                    return {
                        "exito": True,
                        "mensaje": f"Datos del cubo en estrella '{cubo.nombreCubo}' refrescados exitosamente ({resGen['totalFilasGeneradas']:,} filas).",
                        "totalFilas": resGen["totalFilasGeneradas"],
                        "fechaUltimaCarga": cubo.fechaUltimaCarga.strftime("%Y-%m-%d %H:%M:%S")
                    }
                else:
                    # Se detectaron hojas distintas pero no hay relaciones configuradas ni enviadas
                    return {
                        "exito": False,
                        "requiereRelacion": True,
                        "error": "El nuevo archivo Excel contiene hojas con estructuras distintas. Es necesario configurar la relación entre las hojas.",
                        "analisis": {
                            "hojasIdenticas": hojasAUnificar,
                            "hojasDimensionales": analisis.get("hojasDimensionales", []),
                            "llavesCandidatas": analisis.get("llavesCandidatas", {})
                        }
                    }

            # 2. ORIGEN SQL / SQL_EN_VIVO
            elif "SQL" in tipoOrigen:
                consultaSql = None
                idConexion = None

                if cubo.configuracionOrigenJson:
                    try:
                        cfg = json.loads(cubo.configuracionOrigenJson)
                        consultaSql = cfg.get("consultaSql")
                        idConexion = cfg.get("idConexion")
                    except Exception:
                        pass

                # Si no está en cubo, buscar en su primera vista asociada
                if not consultaSql and cubo.vistas:
                    for v in cubo.vistas:
                        if v.consultaSql:
                            consultaSql = v.consultaSql
                            idConexion = v.idConexion or idConexion
                            break

                if not consultaSql or not idConexion:
                    return {
                        "exito": False,
                        "error": "No se encontró la consulta SQL ni la conexión asignada a este cubo."
                    }

                conexionDb = sesion.query(ConexionBaseDatosModelo).filter_by(idConexion=idConexion).first()
                if not conexionDb:
                    return {"exito": False, "error": f"Conexión de base de datos ID {idConexion} no encontrada."}

                try:
                    motorOrigen = create_engine(conexionDb.cadenaConexion.strip())
                    if GestorSqlEnVivo.esStoredProcedure(consultaSql):
                        dfResultado = GestorSqlEnVivo.ejecutarStoredProcedure(motorOrigen, consultaSql)
                    else:
                        dfResultado = pd.read_sql(text(consultaSql.strip().rstrip(";")), motorOrigen)
                except Exception as errSql:
                    return {
                        "exito": False,
                        "error": f"Fallo al ejecutar consulta SQL en origen: {str(errSql)}"
                    }

                # Coerción preventiva de columnas Decimal a float64 para evitar desbordamiento de escala fija en DuckDB (DECIMAL out of range)
                from decimal import Decimal
                for col in dfResultado.columns:
                    if dfResultado[col].dtype == object:
                        serieLimpia = dfResultado[col].dropna()
                        if not serieLimpia.empty and any(isinstance(v, Decimal) for v in serieLimpia.iloc[:25]):
                            dfResultado[col] = pd.to_numeric(dfResultado[col], errors="coerce")

                # Validar impacto contra vistas activas antes de sobrescribir el Parquet
                impacto = cls.validarImpactoColumnas(idCubo, list(dfResultado.columns))
                if not impacto["permitido"]:
                    return {
                        "exito": False,
                        "error": impacto["mensaje"],
                        "bloqueoPorVistas": True,
                        "vistasAfectadas": impacto["vistasAfectadas"],
                        "columnasEnConflicto": impacto["columnasEnConflicto"]
                    }

                conexionDuck = duckdb.connect()
                try:
                    conexionDuck.register("df_temporal_sql", dfResultado)
                    rutaSql = cls.normalizarRutaSql(rutaParquet)
                    if os.path.exists(rutaParquet):
                        os.remove(rutaParquet)
                    conexionDuck.execute(f"COPY df_temporal_sql TO '{rutaSql}' (FORMAT PARQUET, COMPRESSION ZSTD)")
                    filasActuales = int(conexionDuck.execute(f"SELECT COUNT(*) FROM read_parquet('{rutaSql}')").fetchone()[0])
                except Exception as errDuck:
                    return {
                        "exito": False,
                        "error": f"Fallo al materializar Parquet con DuckDB: {str(errDuck)}"
                    }
                finally:
                    conexionDuck.close()

                cubo.fechaUltimaCarga = datetime.utcnow()
                for v in cubo.vistas:
                    v.fechaUltimaEjecucion = cubo.fechaUltimaCarga
                ServicioPersistenciaCubos.persistirBinarioEnCubo(cubo, rutaParquet)
                sesion.commit()

                return {
                    "exito": True,
                    "mensaje": f"Datos del cubo '{cubo.nombreCubo}' refrescados exitosamente desde motor SQL.",
                    "totalFilas": filasActuales,
                    "fechaUltimaCarga": cubo.fechaUltimaCarga.strftime("%Y-%m-%d %H:%M:%S")
                }

            # 3. ORIGEN COMPUESTO
            elif "COMPUESTO" in tipoOrigen:
                if not cubo.configuracionOrigenJson:
                    return {"exito": False, "error": "No se encontraron metadatos de unión para el cubo compuesto."}

                cfg = json.loads(cubo.configuracionOrigenJson)
                trazabilidad = cfg.get("trazabilidadOrigenes", {})
                origenA = trazabilidad.get("origenA", {})
                origenB = trazabilidad.get("origenB", {})
                tipoJoin = trazabilidad.get("tipoJoin", "LEFT")

                rutaA = origenA.get("ruta")
                rutaB = origenB.get("ruta")
                claveA = origenA.get("clave")
                claveB = origenB.get("clave")
                columnas = cfg.get("columnas", [])

                if not rutaA or not rutaB or not os.path.exists(rutaA) or not os.path.exists(rutaB):
                    return {"exito": False, "error": "Una o ambas fuentes Parquet originales no están accesibles."}

                columnasMapeadas = []
                for col in columnas:
                    columnasMapeadas.append({
                        "nombreOriginal": col.get("nombreOriginal") or col.get("nombreColumna"),
                        "origen": col.get("origenColumna", "A"),
                        "nombreFinal": col.get("nombreColumna") or col.get("nombreFinal"),
                        "clasificacionSemantica": col.get("clasificacionSemantica", "Categorica/Dimension")
                    })

                resultado = GeneradorCuboCompuesto.generarParquetCompuesto(
                    rutaOrigenA=rutaA,
                    rutaOrigenB=rutaB,
                    claveOrigenA=claveA,
                    claveOrigenB=claveB,
                    tipoJoin=tipoJoin,
                    columnasMapeadas=columnasMapeadas,
                    rutaDestinoParquet=rutaParquet
                )

                cubo.fechaUltimaCarga = datetime.utcnow()
                for v in cubo.vistas:
                    v.fechaUltimaEjecucion = cubo.fechaUltimaCarga
                ServicioPersistenciaCubos.persistirBinarioEnCubo(cubo, rutaParquet)
                sesion.commit()

                return {
                    "exito": True,
                    "mensaje": f"Cubo compuesto '{cubo.nombreCubo}' regenerado exitosamente.",
                    "totalFilas": resultado.get("totalFilasGeneradas", 0),
                    "fechaUltimaCarga": cubo.fechaUltimaCarga.strftime("%Y-%m-%d %H:%M:%S")
                }

            # 4. ORIGEN PROCESO_MASIVO / DATA_LAKE
            else:
                if not os.path.exists(rutaParquet):
                    return {"exito": False, "error": f"El archivo Parquet en {rutaParquet} no existe en disco."}

                conexionDuck = duckdb.connect()
                try:
                    filasActuales = int(conexionDuck.execute(
                        f"SELECT COUNT(*) FROM read_parquet('{cls.normalizarRutaSql(rutaParquet)}')"
                    ).fetchone()[0])
                finally:
                    conexionDuck.close()

                cubo.fechaUltimaCarga = datetime.utcnow()
                for v in cubo.vistas:
                    v.fechaUltimaEjecucion = cubo.fechaUltimaCarga
                sesion.commit()

                return {
                    "exito": True,
                    "mensaje": f"Metadatos del cubo Data Lake '{cubo.nombreCubo}' verificados y sincronizados.",
                    "totalFilas": filasActuales,
                    "fechaUltimaCarga": cubo.fechaUltimaCarga.strftime("%Y-%m-%d %H:%M:%S")
                }

    @classmethod
    def actualizarEsquemaCubo(cls, idCubo: int, nuevoMapeoColumnas: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aplica la modificación del perfil semántico y la evolución física del archivo Parquet
        únicamente tras superar la validación de impacto sin vistas activas en conflicto.
        Las nuevas columnas añadidas se inicializan físicamente con valor NULL.
        """
        if not nuevoMapeoColumnas:
            return {"exito": False, "error": "El esquema del cubo debe contener al menos una columna."}

        # Validar impacto contra vistas activas
        nuevasColumnasNombres = list(nuevoMapeoColumnas.keys())
        impacto = cls.validarImpactoColumnas(idCubo, nuevasColumnasNombres)
        if not impacto["permitido"]:
            return {
                "exito": False,
                "error": impacto["mensaje"],
                "vistasAfectadas": impacto["vistasAfectadas"],
                "columnasEnConflicto": impacto["columnasEnConflicto"]
            }

        with obtenerSesion() as sesion:
            cubo = sesion.query(CuboModelo).filter_by(idCubo=idCubo).first()
            if not cubo:
                return {"exito": False, "error": f"Cubo con ID {idCubo} no encontrado."}

            rutaParquet = os.path.abspath(cubo.archivoParquet) if cubo.archivoParquet else None
            
            # Evolución física del Parquet si existe o generación de vacío si no existe
            if rutaParquet:
                os.makedirs(os.path.dirname(rutaParquet), exist_ok=True)
                con = duckdb.connect()
                try:
                    rutaSql = cls.normalizarRutaSql(rutaParquet)
                    if os.path.exists(rutaParquet):
                        # Inspeccionar columnas existentes en Parquet
                        columnasExistentesInfo = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{rutaSql}') LIMIT 1").fetchall()
                        columnasExistentesLower = {c[0].lower(): c[0] for c in columnasExistentesInfo}
                        
                        colsToAdd = [colNom for colNom in nuevoMapeoColumnas.keys() if colNom.lower() not in columnasExistentesLower]
                        colsToRemove = [origNom for origLower, origNom in columnasExistentesLower.items() if origLower not in {c.lower() for c in nuevoMapeoColumnas.keys()}]
                        
                        if colsToAdd or colsToRemove:
                            con.execute(f"CREATE TABLE _temp_evolucion AS SELECT * FROM read_parquet('{rutaSql}')")
                            for colNom in colsToAdd:
                                colData = nuevoMapeoColumnas[colNom]
                                tipoSql = colData.get("tipoDato") or colData.get("tipo") or "VARCHAR"
                                con.execute(f'ALTER TABLE _temp_evolucion ADD COLUMN "{colNom}" {tipoSql}')
                            for colNom in colsToRemove:
                                con.execute(f'ALTER TABLE _temp_evolucion DROP COLUMN "{colNom}"')
                            
                            rutaTemp = rutaParquet + ".tmp"
                            rutaTempSql = cls.normalizarRutaSql(rutaTemp)
                            con.execute(f"COPY _temp_evolucion TO '{rutaTempSql}' (FORMAT PARQUET, COMPRESSION ZSTD)")
                            con.close()
                            con = None
                            os.replace(rutaTemp, rutaParquet)
                    else:
                        # Crear parquet vacío con las columnas definidas
                        defs = []
                        for colNom, colData in nuevoMapeoColumnas.items():
                            tipoSql = colData.get("tipoDato") or colData.get("tipo") or "VARCHAR"
                            defs.append(f'"{colNom}" {tipoSql}')
                        con.execute(f"CREATE TABLE _temp_vacia ({', '.join(defs)});")
                        con.execute(f"COPY _temp_vacia TO '{rutaSql}' (FORMAT PARQUET, COMPRESSION ZSTD)")
                        con.close()
                        con = None
                except Exception as e:
                    if con:
                        con.close()
                    return {"exito": False, "error": f"Error al actualizar físicamente el archivo Parquet: {str(e)}"}

            cubo.metadatosColumnasJson = json.dumps(nuevoMapeoColumnas)
            sesion.commit()

            return {
                "exito": True,
                "mensaje": f"Estructura del cubo '{cubo.nombreCubo}' actualizada exitosamente. Las columnas añadidas se han inicializado en NULL.",
                "totalColumnas": len(nuevoMapeoColumnas)
            }

    @classmethod
    def actualizarConsultaSqlCubo(
        cls,
        idCubo: int,
        nuevaConsultaSql: str,
        nuevoIdConexion: Optional[int] = None,
        removerLimiteMuestra: bool = True,
        ejecutarRefresco: bool = False
    ) -> Dict[str, Any]:
        """
        Actualiza la sentencia SQL asignada a un cubo y a sus vistas asociadas,
        con opción de saneamiento automático de TOP/LIMIT y refresco inmediato.
        """
        from sistemaAnalitica.modulos.ingesta.gestorSqlEnVivo import GestorSqlEnVivo

        if not nuevaConsultaSql or not nuevaConsultaSql.strip():
            return {"exito": False, "error": "La consulta SQL no puede estar vacía."}

        sqlFinal = GestorSqlEnVivo.limpiarClausulaLimite(nuevaConsultaSql) if removerLimiteMuestra else nuevaConsultaSql.strip()
        nombreCubo = ""

        with obtenerSesion() as sesion:
            cubo = sesion.query(CuboModelo).filter_by(idCubo=idCubo).first()
            if not cubo:
                return {"exito": False, "error": f"Cubo con ID {idCubo} no encontrado."}

            nombreCubo = cubo.nombreCubo

            # Actualizar configuracionOrigenJson del Cubo
            cfg = {}
            if cubo.configuracionOrigenJson:
                try:
                    cfg = json.loads(cubo.configuracionOrigenJson)
                except Exception:
                    cfg = {}

            # Validar preventivamente que la nueva consulta SQL proyecte todas las columnas requeridas por vistas activas
            idConnVal = nuevoIdConexion
            if idConnVal is None:
                idConnVal = cfg.get("idConexion")
            if idConnVal is None and cubo.vistas:
                for v in cubo.vistas:
                    if v.idConexion:
                        idConnVal = v.idConexion
                        break

            if idConnVal:
                connModel = sesion.query(ConexionBaseDatosModelo).filter_by(idConexion=idConnVal).first()
                if connModel and connModel.cadenaConexion:
                    try:
                        dfMuestra, errMuestra = GestorSqlEnVivo.ejecutarMuestraSql(connModel.cadenaConexion.strip(), sqlFinal, limite=1)
                        if dfMuestra is not None and len(dfMuestra.columns) > 0:
                            impacto = cls.validarImpactoColumnas(idCubo, list(dfMuestra.columns))
                            if not impacto["permitido"]:
                                return {
                                    "exito": False,
                                    "bloqueoPorVistas": True,
                                    "error": impacto["mensaje"],
                                    "vistasAfectadas": impacto["vistasAfectadas"],
                                    "columnasEnConflicto": impacto["columnasEnConflicto"]
                                }
                        elif errMuestra:
                            return {
                                "exito": False,
                                "error": f"Error al validar la consulta SQL en origen: {errMuestra}"
                            }
                    except Exception as exSqlVal:
                        return {
                            "exito": False,
                            "error": f"Error al ejecutar validación de la nueva consulta SQL: {str(exSqlVal)}"
                        }

            cfg["consultaSql"] = sqlFinal
            if nuevoIdConexion is not None:
                cfg["idConexion"] = nuevoIdConexion
            cubo.configuracionOrigenJson = json.dumps(cfg)

            # Actualizar vistas dependientes del cubo
            for v in cubo.vistas:
                v.consultaSql = sqlFinal
                if nuevoIdConexion is not None:
                    v.idConexion = nuevoIdConexion
                v.fechaModificacion = datetime.utcnow()

            sesion.commit()

        # Si se solicitó refresco inmediato, ejecutarlo ahora
        resRefresco = None
        if ejecutarRefresco:
            resRefresco = cls.actualizarDatosCubo(idCubo)
            if not resRefresco.get("exito"):
                return {
                    "exito": False,
                    "idCubo": idCubo,
                    "error": resRefresco.get("error", "Error desconocido al refrescar datos del cubo."),
                    "consultaSql": sqlFinal
                }

        return {
            "exito": True,
            "idCubo": idCubo,
            "consultaSql": sqlFinal,
            "mensaje": f"Consulta SQL del cubo '{nombreCubo}' actualizada exitosamente." + (f" Refresco: {resRefresco.get('mensaje', '')}" if resRefresco else ""),
            "refresco": resRefresco
        }

    @classmethod
    def listarCubosConMetadatos(cls) -> List[Dict[str, Any]]:
        """
        Devuelve el catálogo de cubos con su estado, fecha de última carga, conteo de vistas y columnas.
        """
        with obtenerSesion() as sesion:
            cubos = sesion.query(CuboModelo).order_by(CuboModelo.fechaCreacion.desc()).all()
            resultado = []

            for c in cubos:
                totalVistas = len(c.vistas)
                vistasActivas = len([v for v in c.vistas if v.estadoHabilitado and v.activo])

                # Extraer consulta SQL y conexión asociada si existe
                consultaSqlCubo = ""
                idConexionCubo = None
                nombreConexionCubo = ""
                if c.configuracionOrigenJson:
                    try:
                        cfg = json.loads(c.configuracionOrigenJson)
                        consultaSqlCubo = cfg.get("consultaSql", "")
                        idConexionCubo = cfg.get("idConexion")
                    except Exception:
                        pass
                if not consultaSqlCubo and c.vistas:
                    for v in c.vistas:
                        if v.consultaSql:
                            consultaSqlCubo = v.consultaSql
                            idConexionCubo = v.idConexion or idConexionCubo
                            break

                if idConexionCubo:
                    conObj = sesion.query(ConexionBaseDatosModelo).filter_by(idConexion=idConexionCubo).first()
                    if conObj:
                        nombreConexionCubo = conObj.nombreConexion

                columnas = []
                # Intentar leer desde metadatosColumnasJson
                if c.metadatosColumnasJson:
                    try:
                        meta = json.loads(c.metadatosColumnasJson)
                        if isinstance(meta, dict) and "columnas" in meta:
                            for col in meta["columnas"]:
                                columnas.append({
                                    "nombre": col.get("nombreColumna") or col.get("nombreFinal") or col.get("nombreOriginal"),
                                    "tipo": col.get("tipoDatoEsperado") or col.get("tipoDato") or "VARCHAR",
                                    "clasificacion": col.get("clasificacionSemantica", "Categorica/Dimension")
                                })
                        elif isinstance(meta, dict):
                            for colNom, colData in meta.items():
                                if isinstance(colData, dict):
                                    columnas.append({
                                        "nombre": colNom,
                                        "tipo": colData.get("tipoDato", "VARCHAR"),
                                        "clasificacion": colData.get("clasificacionSemantica", "Categorica/Dimension")
                                    })
                                else:
                                    columnas.append({
                                        "nombre": colNom,
                                        "tipo": "VARCHAR",
                                        "clasificacion": str(colData)
                                    })
                    except Exception:
                        pass

                # Si no hay columnas en JSON, asegurar Parquet en disco e inspeccionar con DuckDB
                if not columnas and c.archivoParquet:
                    ServicioPersistenciaCubos.asegurarParquetEnDisco(c, sesion)
                    if os.path.exists(c.archivoParquet):
                        try:
                            con = duckdb.connect()
                            rutaSql = cls.normalizarRutaSql(c.archivoParquet)
                            desc = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{rutaSql}') LIMIT 1").fetchall()
                            con.close()
                            for row in desc:
                                nombre = row[0]
                                tipo = str(row[1]).upper()
                                esNum = any(t in tipo for t in ["INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC"])
                                clasif = "MetricaSumable" if esNum else "Categorica/Dimension"
                                columnas.append({
                                    "nombre": nombre,
                                    "tipo": tipo,
                                    "clasificacion": clasif
                                })
                        except Exception:
                            pass

                resultado.append({
                    "idCubo": c.idCubo,
                    "nombreCubo": c.nombreCubo,
                    "archivoParquet": c.archivoParquet,
                    "nombreArchivo": os.path.basename(c.archivoParquet) if c.archivoParquet else "",
                    "tipoOrigen": c.tipoOrigen,
                    "estadoHabilitado": c.estadoHabilitado,
                    "fechaUltimaCarga": c.fechaUltimaCarga.strftime("%Y-%m-%d %H:%M:%S") if c.fechaUltimaCarga else "-",
                    "totalVistas": totalVistas,
                    "vistasActivas": vistasActivas,
                    "columnas": columnas,
                    "consultaSql": consultaSqlCubo,
                    "idConexion": idConexionCubo,
                    "nombreConexion": nombreConexionCubo
                })

            return resultado

    @classmethod
    def listarVistasConAuditoria(cls) -> List[Dict[str, Any]]:
        """
        Devuelve el catálogo de vistas analíticas con trazabilidad de autoría, estado y datos del cubo.
        """
        with obtenerSesion() as sesion:
            vistas = sesion.query(VistaModelo).filter_by(activo=True).order_by(VistaModelo.fechaCreacion.desc()).all()
            resultado = []

            for v in vistas:
                nombreUsuarioCreador = "Sistema"
                if v.creador:
                    nombreUsuarioCreador = v.creador.nombreUsuario
                elif v.creadoPorUsuarioId:
                    u = sesion.query(UsuarioModelo).filter_by(idUsuario=v.creadoPorUsuarioId).first()
                    if u:
                        nombreUsuarioCreador = u.nombreUsuario

                nombreCubo = "-"
                estadoCubo = False
                fechaUltimaCargaCubo = "-"

                if v.cubo:
                    nombreCubo = v.cubo.nombreCubo
                    estadoCubo = v.cubo.estadoHabilitado
                    fechaUltimaCargaCubo = v.cubo.fechaUltimaCarga.strftime("%Y-%m-%d %H:%M:%S") if v.cubo.fechaUltimaCarga else "-"
                elif v.idCubo:
                    cuboObj = sesion.query(CuboModelo).filter_by(idCubo=v.idCubo).first()
                    if cuboObj:
                        nombreCubo = cuboObj.nombreCubo
                        estadoCubo = cuboObj.estadoHabilitado
                        fechaUltimaCargaCubo = cuboObj.fechaUltimaCarga.strftime("%Y-%m-%d %H:%M:%S") if cuboObj.fechaUltimaCarga else "-"

                resultado.append({
                    "idVista": v.idVista,
                    "codigoVista": v.codigoVista,
                    "nombreVista": v.nombreVista,
                    "descripcion": v.descripcion or "",
                    "estadoHabilitado": v.estadoHabilitado,
                    "nombreCubo": nombreCubo,
                    "idCubo": v.idCubo,
                    "estadoCubo": estadoCubo,
                    "creadoPor": nombreUsuarioCreador,
                    "fechaCreacion": v.fechaCreacion.strftime("%Y-%m-%d %H:%M:%S") if v.fechaCreacion else "-",
                    "fechaUltimaCargaCubo": fechaUltimaCargaCubo,
                    "puedeExplorar": bool(v.estadoHabilitado and estadoCubo)
                })

            return resultado

    @classmethod
    def eliminarCubo(cls, idCubo: int, usuario: dict, direccionIp: Optional[str] = None) -> Dict[str, Any]:
        """
        Elimina un cubo analítico OBT validando que no posea vistas asignadas.
        Registra la auditoría en logs_auditoria_eliminacion.
        """
        with obtenerSesion() as sesion:
            cubo = sesion.query(CuboModelo).filter_by(idCubo=idCubo).first()
            if not cubo:
                return {"exito": False, "error": f"Cubo con ID {idCubo} no encontrado."}

            vistasAsignadas = sesion.query(VistaModelo).filter_by(idCubo=idCubo, activo=True).all()
            if vistasAsignadas:
                nombresVistas = [v.nombreVista for v in vistasAsignadas]
                return {
                    "exito": False,
                    "error": f"No se puede eliminar el cubo '{cubo.nombreCubo}' porque tiene {len(vistasAsignadas)} vista(s) asignada(s): {', '.join(nombresVistas)}. Debe eliminar primero sus vistas asociadas.",
                    "bloqueado": True,
                    "totalVistas": len(vistasAsignadas),
                    "vistas": nombresVistas
                }

            nombreCubo = cubo.nombreCubo
            archivoParquet = cubo.archivoParquet
            detalles = {
                "nombreCubo": nombreCubo,
                "archivoParquet": archivoParquet,
                "tipoOrigen": cubo.tipoOrigen,
                "fechaCreacion": cubo.fechaCreacion.isoformat() if cubo.fechaCreacion else None
            }

            # Registrar log de auditoría permanente
            logAuditoria = LogAuditoriaEliminacionModelo(
                fechaHora=datetime.utcnow(),
                idUsuario=usuario.get("idUsuario") or usuario.get("id_usuario"),
                nombreUsuario=usuario.get("nombreUsuario", "sistema"),
                nombreCompleto=usuario.get("nombreCompleto", "Administrador"),
                tipoObjeto="CUBO",
                idObjeto=idCubo,
                identificadorObjeto=nombreCubo,
                nombreObjeto=nombreCubo,
                detallesJson=json.dumps(detalles, ensure_ascii=False),
                direccionIp=direccionIp or "127.0.0.1"
            )
            sesion.add(logAuditoria)

            # Eliminar archivo Parquet físico si existe
            if archivoParquet and os.path.exists(archivoParquet):
                try:
                    os.remove(archivoParquet)
                except Exception as errArch:
                    print(f"Aviso: no se pudo remover archivo físico {archivoParquet}: {errArch}")

            sesion.delete(cubo)
            sesion.commit()

            return {
                "exito": True,
                "idCubo": idCubo,
                "nombreCubo": nombreCubo,
                "mensaje": f"Cubo '{nombreCubo}' eliminado exitosamente con registro en auditoría."
            }

    @classmethod
    def eliminarVista(cls, idVista: int, usuario: dict, direccionIp: Optional[str] = None) -> Dict[str, Any]:
        """
        Elimina una vista analítica y desvincula sus roles y excepciones.
        Registra la auditoría en logs_auditoria_eliminacion.
        """
        with obtenerSesion() as sesion:
            vista = sesion.query(VistaModelo).filter_by(idVista=idVista).first()
            if not vista:
                return {"exito": False, "error": f"Vista con ID {idVista} no encontrada."}

            nombreVista = vista.nombreVista
            codigoVista = vista.codigoVista
            detalles = {
                "idVista": idVista,
                "codigoVista": codigoVista,
                "nombreVista": nombreVista,
                "tipoIngesta": vista.tipoIngesta,
                "idCubo": vista.idCubo,
                "fechaCreacion": vista.fechaCreacion.isoformat() if vista.fechaCreacion else None
            }

            # Limpiar asociaciones dependientes
            vista.roles.clear()
            sesion.query(ExcepcionUsuarioModelo).filter_by(idVista=idVista).delete()
            sesion.query(FiltroSeguridadFilaModelo).filter_by(idVista=idVista).delete()

            # Registrar log de auditoría permanente
            logAuditoria = LogAuditoriaEliminacionModelo(
                fechaHora=datetime.utcnow(),
                idUsuario=usuario.get("idUsuario") or usuario.get("id_usuario"),
                nombreUsuario=usuario.get("nombreUsuario", "sistema"),
                nombreCompleto=usuario.get("nombreCompleto", "Administrador"),
                tipoObjeto="VISTA",
                idObjeto=idVista,
                identificadorObjeto=codigoVista,
                nombreObjeto=nombreVista,
                detallesJson=json.dumps(detalles, ensure_ascii=False),
                direccionIp=direccionIp or "127.0.0.1"
            )
            sesion.add(logAuditoria)

            sesion.delete(vista)
            sesion.commit()

            return {
                "exito": True,
                "idVista": idVista,
                "codigoVista": codigoVista,
                "nombreVista": nombreVista,
                "mensaje": f"Vista '{nombreVista}' ({codigoVista}) eliminada exitosamente con registro en auditoría."
            }

    @classmethod
    def consultarAuditoriaEliminaciones(cls, limite: int = 100) -> List[Dict[str, Any]]:
        """
        Consulta los registros de auditoría de eliminación ordenados cronológicamente.
        """
        with obtenerSesion() as sesion:
            logs = sesion.query(LogAuditoriaEliminacionModelo).order_by(
                LogAuditoriaEliminacionModelo.fechaHora.desc()
            ).limit(limite).all()

            resultado = []
            for l in logs:
                detalles = {}
                if l.detallesJson:
                    try:
                        detalles = json.loads(l.detallesJson)
                    except Exception:
                        detalles = {"raw": l.detallesJson}
                resultado.append({
                    "id": l.id,
                    "fechaHora": l.fechaHora.strftime("%Y-%m-%d %H:%M:%S") if l.fechaHora else "-",
                    "idUsuario": l.idUsuario,
                    "nombreUsuario": l.nombreUsuario,
                    "nombreCompleto": l.nombreCompleto or l.nombreUsuario,
                    "tipoObjeto": l.tipoObjeto,
                    "idObjeto": l.idObjeto,
                    "identificadorObjeto": l.identificadorObjeto,
                    "nombreObjeto": l.nombreObjeto,
                    "detalles": detalles,
                    "direccionIp": l.direccionIp
                })
            return resultado
