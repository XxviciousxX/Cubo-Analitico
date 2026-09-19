"""
Router para la ingesta de datos, perfilado de metadatos y motor Parquet.
"""

import os
import json
import re
from datetime import datetime
from typing import Optional, List
import pandas as pd
from fastapi import APIRouter, Request, Depends, Body, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import duckdb

from sistemaAnalitica.app.dependencias import requerirUsuarioAutenticado, requerirPermisoPantalla
from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import VistaModelo, ConexionBaseDatosModelo, RolModelo, CuboModelo
from sistemaAnalitica.modulos.ingesta.calamineLector import CalamineLectorExcel
from sistemaAnalitica.modulos.ingesta.validadorContratos import ValidadorContratos
from sistemaAnalitica.modulos.ingesta.generadorOBT import GeneradorOBT
from sistemaAnalitica.modulos.ingesta.gestorSqlEnVivo import GestorSqlEnVivo
from sistemaAnalitica.modulos.ingesta.generadorCuboCompuesto import GeneradorCuboCompuesto
from sistemaAnalitica.modulos.ingesta.esquemas import (
    SolicitudCuboCompuesto,
    SolicitudInspeccionClaves,
    SolicitudMuestreoDataLake,
    SolicitudRegistroDataLake,
    CondicionJoin
)
from sistemaAnalitica.modulos.presentacion.ingestaVista import generarExcelEjemploVentas

router = APIRouter(tags=["Ingesta"])
templates = Jinja2Templates(directory="sistemaAnalitica/app/templates")


def sanitizarCodigoVista(codigo: str, maxLen: int = 140) -> str:
    """
    Sanitiza y acota el código del cubo/vista para evitar truncamientos en la BD
    y caracteres inválidos en el sistema de archivos.
    """
    limpio = re.sub(r'[^a-zA-Z0-9_]', '_', str(codigo).strip())
    limpio = re.sub(r'_+', '_', limpio).strip('_')
    return (limpio or 'cubo_datos')[:maxLen]


def sanitizarNombreVista(nombre: str, maxLen: int = 140) -> str:
    """
    Acota el nombre descriptivo de la vista para ajustarse al esquema relacional.
    """
    return str(nombre).strip()[:maxLen]


@router.get("/ingesta", response_class=HTMLResponse)
async def mostrarIngesta(
    request: Request,
    user: dict = Depends(requerirPermisoPantalla("INGESTA"))
):
    """
    Despliega la interfaz de ingesta multipestaña con Calamine, SQL y Data Lake.
    """
    directorioParquets = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
    ))
    os.makedirs(directorioParquets, exist_ok=True)
    parquetsExistentes = [f for f in os.listdir(directorioParquets) if f.endswith(".parquet")]

    with obtenerSesion() as sesion:
        roles = sesion.query(RolModelo).filter_by(activo=True).all()
        conexiones = sesion.query(ConexionBaseDatosModelo).filter_by(activo=True).all()

    return templates.TemplateResponse(
        request=request,
        name="ingesta.html",
        context={
            "user": user,
            "roles": roles,
            "conexiones": conexiones,
            "parquets_existentes": parquetsExistentes,
            "ruta_activa": "ingesta"
        }
    )


@router.post("/api/ingesta/analizar-excel")
async def analizarArchivoExcel(
    archivo: UploadFile = File(...),
    hoja: Optional[str] = Form(None),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Analiza un archivo Excel real (.xlsx) subido por el usuario mediante Calamine Rust.
    Extrae las hojas disponibles y perfila las columnas de la hoja seleccionada.
    """
    try:
        contenido = await archivo.read()
        hojas = CalamineLectorExcel.obtenerHojasLibro(contenido)
        if not hojas:
            return JSONResponse({"exito": False, "error": "El archivo Excel no contiene hojas válidas o legibles."}, status_code=400)

        hojaActiva = hoja if (hoja and hoja in hojas) else hojas[0]
        df = CalamineLectorExcel.convertirHojaADataFrame(contenido, hojaActiva)
        perfil = CalamineLectorExcel.perfiladorTiposColumna(df)

        columnas = [
            {
                "nombre": col,
                "tipo": perfil[col]["tipoDatoPrimitivo"],
                "clasificacion": perfil[col]["clasificacionSugerida"],
                "conteoNoNulos": perfil[col]["conteoNoNulos"],
                "valoresUnicos": perfil[col]["valoresUnicos"]
            }
            for col in df.columns
        ]

        return JSONResponse({
            "exito": True,
            "nombreArchivo": archivo.filename,
            "hojas": hojas,
            "hojaSeleccionada": hojaActiva,
            "totalFilas": len(df),
            "columnas": columnas
        })
    except Exception as e:
        return JSONResponse({"exito": False, "error": f"Error al analizar libro Excel: {str(e)}"}, status_code=500)


@router.post("/api/ingesta/procesar-excel")
async def procesarYGuardarExcel(
    archivo: UploadFile = File(...),
    nombreCubo: Optional[str] = Form(None),
    codigoCubo: Optional[str] = Form(None),
    codigoVista: Optional[str] = Form(None),
    nombreVista: Optional[str] = Form(None),
    modalidad: str = Form("ExcelModalidadA"),
    rolDefecto: Optional[str] = Form("TODOS"),
    hoja: Optional[str] = Form(None),
    nombreHoja: Optional[str] = Form(None),
    configuracionColumnasJson: Optional[str] = Form(None),
    configuracionColumnas: Optional[str] = Form(None),
    hojasUnificarJson: Optional[str] = Form(None),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Procesa el archivo Excel real subido por el usuario, valida y aplica los tipos de datos
    definidos por el usuario, materializa el archivo Apache Parquet con compresión ZSTD
    y registra exclusivamente el Cubo en el catálogo relacional (dbo.cubos), sin generar vista automática.
    """
    try:
        nombreFinalCubo = sanitizarNombreVista(nombreCubo or nombreVista or codigoVista or "Cubo Excel")
        slugCubo = sanitizarCodigoVista(codigoCubo or codigoVista or nombreFinalCubo)
        contenido = await archivo.read()

        # Determinar hojas disponibles
        hojasDisponibles = CalamineLectorExcel.obtenerHojasLibro(contenido)
        hojaSeleccionada = hoja or nombreHoja or (hojasDisponibles[0] if hojasDisponibles else "")

        hojasAUnificar = []
        if hojasUnificarJson:
            try:
                parsed = json.loads(hojasUnificarJson)
                if isinstance(parsed, list) and len(parsed) > 0:
                    hojasAUnificar = parsed
            except Exception:
                hojasAUnificar = []

        if len(hojasAUnificar) > 1:
            df = CalamineLectorExcel.unificarHojasIdenticas(contenido, hojasAUnificar, columnaTrazadora="hoja_origen")
        else:
            hojaFinal = hojasAUnificar[0] if len(hojasAUnificar) == 1 else hojaSeleccionada
            df = CalamineLectorExcel.convertirHojaADataFrame(contenido, hojaFinal)

        jsonConfig = configuracionColumnasJson or configuracionColumnas
        columnasConfiguradas = json.loads(jsonConfig) if jsonConfig else []

        if columnasConfiguradas:
            columnasContrato = [
                {
                    "nombreColumna": c.get("nombre", str(c)),
                    "tipoDatoEsperado": c.get("tipoDato") or c.get("tipo") or "VARCHAR",
                    "clasificacionSemantica": c.get("clasificacionSemantica") or c.get("clasificacion") or "Categorica/Dimension"
                }
                for c in columnasConfiguradas
            ]
        else:
            perfil = CalamineLectorExcel.perfiladorTiposColumna(df)
            columnasContrato = [
                {
                    "nombreColumna": col,
                    "tipoDatoEsperado": perfil[col]["tipoDatoPrimitivo"],
                    "clasificacionSemantica": perfil[col]["clasificacionSugerida"]
                }
                for col in df.columns
            ]

        if "hoja_origen" in df.columns and not any(c["nombreColumna"] == "hoja_origen" for c in columnasContrato):
            columnasContrato.append({
                "nombreColumna": "hoja_origen",
                "tipoDatoEsperado": "VARCHAR",
                "clasificacionSemantica": "Categorica/Dimension"
            })

        directorioParquets = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
        ))
        os.makedirs(directorioParquets, exist_ok=True)
        rutaParquet = os.path.join(directorioParquets, f"{slugCubo}.parquet")

        contrato = ValidadorContratos.construirContratoJson(
            idModelo=slugCubo,
            nombreVista=nombreFinalCubo,
            tipoIngesta=modalidad,
            mapeoColumnas=columnasContrato
        )
        if len(hojasAUnificar) > 1:
            contrato["hojasUnificadas"] = hojasAUnificar

        GeneradorOBT.purgarArchivoParquet(rutaParquet)
        GeneradorOBT.guardarEnParquet(df, rutaParquet, contratoColumnas=columnasContrato)

        with obtenerSesion() as sesion:
            cubo = sesion.query(CuboModelo).filter(
                (CuboModelo.archivoParquet == rutaParquet) | (CuboModelo.nombreCubo == nombreFinalCubo)
            ).first()
            if not cubo:
                cubo = CuboModelo(
                    nombreCubo=nombreFinalCubo,
                    archivoParquet=rutaParquet,
                    tipoOrigen="EXCEL",
                    configuracionOrigenJson=json.dumps(contrato),
                    estadoHabilitado=True,
                    fechaUltimaCarga=datetime.utcnow(),
                    metadatosColumnasJson=json.dumps(columnasContrato)
                )
                sesion.add(cubo)
                sesion.flush()
            else:
                cubo.nombreCubo = nombreFinalCubo
                cubo.archivoParquet = rutaParquet
                cubo.tipoOrigen = "EXCEL"
                cubo.fechaUltimaCarga = datetime.utcnow()
                cubo.configuracionOrigenJson = json.dumps(contrato)
                cubo.metadatosColumnasJson = json.dumps(columnasContrato)

            idCubo = cubo.idCubo
            nombreRegistrado = cubo.nombreCubo
            sesion.commit()

        return JSONResponse({
            "exito": True,
            "idCubo": idCubo,
            "nombreCubo": nombreRegistrado,
            "codigoCubo": slugCubo,
            "codigoVista": slugCubo,  # retrocompatibilidad
            "rutaParquet": rutaParquet,
            "totalFilas": len(df),
            "totalColumnas": len(columnasContrato),
            "columnas": columnasContrato,
            "mensaje": f"Cubo '{nombreRegistrado}' creado y materializado exitosamente en el Data Lake ({len(df)} registros)."
        })
    except Exception as e:
        return JSONResponse({"exito": False, "error": f"Error al procesar Excel: {str(e)}"}, status_code=500)


@router.post("/api/sql/probar")
async def probarConsultaSql(
    user: dict = Depends(requerirUsuarioAutenticado),
    datos: dict = Body(...)
):
    """
    Ejecuta muestra rápida TOP 10 de SQL.
    """
    cadena = datos.get("cadenaConexion", "")
    idConexion = datos.get("idConexion")
    if not cadena and idConexion:
        with obtenerSesion() as sesion:
            cObj = sesion.query(ConexionBaseDatosModelo).filter_by(idConexion=int(idConexion)).first()
            if cObj:
                cadena = cObj.cadenaConexion

    sql = datos.get("consultaSql", "")
    esSp = GestorSqlEnVivo.esStoredProcedure(sql)
    dfMuestra, err = GestorSqlEnVivo.ejecutarMuestraSql(cadena, sql, limiteMuestra=5)
    if err:
        return JSONResponse({"exito": False, "error": err})
    
    # Serialización segura con pandas to_json para convertir Timestamps, fechas y NaNs a formato ISO JSON
    filasJson = json.loads(dfMuestra.to_json(orient="records", date_format="iso"))
    return JSONResponse({
        "exito": True,
        "filas": filasJson,
        "columnas": list(dfMuestra.columns),
        "totalFilasMuestra": len(filasJson),
        "esStoredProcedure": esSp
    })


@router.post("/api/sql/procesar-cubo")
async def procesarYGuardarCuboSql(
    user: dict = Depends(requerirUsuarioAutenticado),
    datos: dict = Body(...)
):
    """
    Ejecuta la consulta SQL contra el origen de datos relacional, materializa
    el cubo columnar en Apache Parquet (ZSTD) y registra el cubo y vista en SQL Server.
    Soporta sentencias SELECT y Stored Procedures (EXEC).
    """
    cadena = datos.get("cadenaConexion", "").strip()
    codigoVista = datos.get("codigoVista", "").strip()
    nombreVista = datos.get("nombreVista", "").strip() or codigoVista
    sql = datos.get("consultaSql", "").strip()
    rolDefecto = datos.get("rolDefecto", "TODOS")
    removerLimiteMuestra = bool(datos.get("removerLimiteMuestra", True))

    if not cadena or not codigoVista or not sql:
        return JSONResponse({"exito": False, "error": "Faltan parámetros requeridos (cadena, código o consulta SQL)."}, status_code=400)

    # Saneamiento de muestreo: si se especificó TOP o LIMIT, removerlo para materialización completa (SPs no se alteran)
    sqlEjecucion = GestorSqlEnVivo.limpiarClausulaLimite(sql) if removerLimiteMuestra else sql
    esSp = GestorSqlEnVivo.esStoredProcedure(sql)

    try:
        from sqlalchemy import create_engine, text
        motor = create_engine(cadena)
        if esSp:
            df = GestorSqlEnVivo.ejecutarStoredProcedure(motor, sqlEjecucion)
        else:
            df = pd.read_sql(text(sqlEjecucion), motor)

        directorioParquets = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
        ))
        os.makedirs(directorioParquets, exist_ok=True)
        rutaParquet = os.path.join(directorioParquets, f"{codigoVista}.parquet")

        # Materializar Parquet con ZSTD
        GeneradorOBT.purgarArchivoParquet(rutaParquet)
        GeneradorOBT.guardarEnParquet(df, rutaParquet, compresion="zstd")

        # Perfilado automático de columnas
        perfil = CalamineLectorExcel.perfiladorTiposColumna(df)
        contratoColumnas = [
            {
                "nombreColumna": col,
                "tipoDatoEsperado": perfil[col]["tipoDatoPrimitivo"],
                "clasificacionSemantica": perfil[col]["clasificacionSugerida"]
            }
            for col in df.columns
        ]

        contrato = ValidadorContratos.construirContratoJson(
            idModelo=codigoVista,
            nombreVista=nombreVista,
            tipoIngesta="SqlEnVivo",
            mapeoColumnas=contratoColumnas
        )

        rolesAsignadosNombres = []
        with obtenerSesion() as sesion:
            conexionObj = sesion.query(ConexionBaseDatosModelo).filter_by(cadenaConexion=cadena, activo=True).first()
            idConexion = conexionObj.idConexion if conexionObj else None

            contrato["consultaSql"] = sqlEjecucion
            contrato["idConexion"] = idConexion

            nombreFinalCubo = sanitizarNombreVista(nombreVista or codigoVista or "Cubo SQL")
            slugCubo = sanitizarCodigoVista(codigoVista or nombreFinalCubo)

            cubo = sesion.query(CuboModelo).filter(
                (CuboModelo.archivoParquet == rutaParquet) | (CuboModelo.nombreCubo == nombreFinalCubo)
            ).first()
            if not cubo:
                cubo = CuboModelo(
                    nombreCubo=nombreFinalCubo,
                    archivoParquet=rutaParquet,
                    tipoOrigen="SQL",
                    configuracionOrigenJson=json.dumps(contrato),
                    estadoHabilitado=True,
                    fechaUltimaCarga=datetime.utcnow(),
                    metadatosColumnasJson=json.dumps(contratoColumnas)
                )
                sesion.add(cubo)
                sesion.flush()
            else:
                cubo.nombreCubo = nombreFinalCubo
                cubo.archivoParquet = rutaParquet
                cubo.fechaUltimaCarga = datetime.utcnow()
                cubo.configuracionOrigenJson = json.dumps(contrato)
                cubo.metadatosColumnasJson = json.dumps(contratoColumnas)

            idCubo = cubo.idCubo
            nombreRegistrado = cubo.nombreCubo
            sesion.commit()

        return JSONResponse({
            "exito": True,
            "idCubo": idCubo,
            "nombreCubo": nombreRegistrado,
            "codigoCubo": slugCubo,
            "codigoVista": slugCubo,
            "rutaParquet": rutaParquet,
            "totalFilas": len(df),
            "totalColumnas": len(contratoColumnas),
            "columnas": contratoColumnas,
            "mensaje": f"Cubo SQL '{nombreRegistrado}' materializado exitosamente en el Data Lake ({len(df)} registros)."
        })
    except Exception as e:
        return JSONResponse({"exito": False, "error": f"Fallo al procesar y materializar cubo SQL: {str(e)}"}, status_code=500)


# ==============================================================================
# ENDPOINTS: CUBOS COMPUESTOS (JOIN) Y MUESTREO DE DATA LAKE PARQUET
# ==============================================================================

@router.get("/api/ingesta/cubos-disponibles")
async def listarCubosDisponibles(user: dict = Depends(requerirUsuarioAutenticado)):
    """
    Devuelve la lista de cubos/vistas analíticas y archivos Parquet existentes con sus metadatos y origen.
    """
    directorioParquets = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
    ))
    os.makedirs(directorioParquets, exist_ok=True)

    cubos = []
    with obtenerSesion() as sesion:
        vistas = sesion.query(VistaModelo).filter_by(activo=True).all()
        mapaVistasPorRuta = {os.path.abspath(v.rutaArchivoParquet).lower(): v for v in vistas if v.rutaArchivoParquet}

        archivos = [f for f in os.listdir(directorioParquets) if f.endswith(".parquet")]
        for arch in archivos:
            rutaCompleta = os.path.abspath(os.path.join(directorioParquets, arch))
            vistaAsociada = mapaVistasPorRuta.get(rutaCompleta.lower())

            tipoOrigen = "DataLake"
            nombreVista = arch.replace(".parquet", "")
            codigoVista = arch.replace(".parquet", "")

            if vistaAsociada:
                tipoOrigen = vistaAsociada.tipoIngesta
                nombreVista = vistaAsociada.nombreVista
                codigoVista = vistaAsociada.codigoVista

            try:
                meta = GeneradorCuboCompuesto.obtenerMetadatosOrigen(rutaCompleta)
                totalFilas = meta["totalFilas"]
                cantColumnas = len(meta["columnas"])
            except Exception:
                totalFilas = 0
                cantColumnas = 0

            cubos.append({
                "nombreArchivo": arch,
                "rutaParquet": rutaCompleta,
                "codigoVista": codigoVista,
                "nombreVista": nombreVista,
                "tipoOrigen": tipoOrigen,
                "totalFilas": totalFilas,
                "cantColumnas": cantColumnas
            })

    return JSONResponse({"exito": True, "cubos": cubos})


@router.post("/api/ingesta/datalake/muestrear")
async def muestrearDataLake(
    solicitud: SolicitudMuestreoDataLake = Body(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Obtiene una muestra de N registros y metadatos de un archivo Parquet del Data Lake.
    """
    directorioParquets = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
    ))
    rutaParquet = os.path.join(directorioParquets, solicitud.nombreArchivoParquet)
    if not os.path.exists(rutaParquet):
        return JSONResponse({"exito": False, "error": f"El archivo '{solicitud.nombreArchivoParquet}' no existe en el Data Lake."}, status_code=404)

    try:
        resultado = GeneradorCuboCompuesto.obtenerMuestraDataLake(rutaParquet, limite=solicitud.limiteFilas)
        return JSONResponse(resultado)
    except Exception as e:
        return JSONResponse({"exito": False, "error": f"Error al muestrear Parquet: {str(e)}"}, status_code=500)


@router.post("/api/ingesta/datalake/registrar")
async def registrarDataLake(
    solicitud: SolicitudRegistroDataLake = Body(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Registra formalmente un Parquet del Data Lake como vista en VistaModelo con su contrato y rol asignado.
    """
    directorioParquets = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
    ))
    rutaParquet = os.path.join(directorioParquets, solicitud.nombreArchivoParquet)
    if not os.path.exists(rutaParquet):
        return JSONResponse({"exito": False, "error": f"El archivo Parquet no existe en {rutaParquet}."}, status_code=404)

    contrato = ValidadorContratos.construirContratoJson(
        idModelo=solicitud.codigoVista,
        nombreVista=solicitud.nombreVista,
        tipoIngesta="ProcesoMasivo",
        mapeoColumnas=solicitud.mapeoColumnas
    )

    nombreFinalCubo = sanitizarNombreVista(solicitud.nombreVista or solicitud.codigoVista or "Cubo Data Lake")
    with obtenerSesion() as sesion:
        cubo = sesion.query(CuboModelo).filter(
            (CuboModelo.archivoParquet == rutaParquet) | (CuboModelo.nombreCubo == nombreFinalCubo)
        ).first()
        if not cubo:
            cubo = CuboModelo(
                nombreCubo=nombreFinalCubo,
                archivoParquet=rutaParquet,
                tipoOrigen="PROCESO_MASIVO",
                configuracionOrigenJson=json.dumps(contrato),
                estadoHabilitado=True,
                fechaUltimaCarga=datetime.utcnow(),
                metadatosColumnasJson=json.dumps(solicitud.mapeoColumnas)
            )
            sesion.add(cubo)
            sesion.flush()
        else:
            cubo.nombreCubo = nombreFinalCubo
            cubo.archivoParquet = rutaParquet
            cubo.tipoOrigen = "PROCESO_MASIVO"
            cubo.fechaUltimaCarga = datetime.utcnow()
            cubo.configuracionOrigenJson = json.dumps(contrato)
            cubo.metadatosColumnasJson = json.dumps(solicitud.mapeoColumnas)

        idCubo = cubo.idCubo
        nombreRegistrado = cubo.nombreCubo
        sesion.commit()

    return JSONResponse({
        "exito": True,
        "idCubo": idCubo,
        "nombreCubo": nombreRegistrado,
        "codigoCubo": solicitud.codigoVista,
        "codigoVista": solicitud.codigoVista,
        "rutaParquet": rutaParquet,
        "mensaje": f"Cubo Data Lake '{nombreRegistrado}' registrado exitosamente en el catálogo relacional."
    })


def parsearDdlSql(ddlText: str) -> dict:
    """
    Interpreta una sentencia CREATE TABLE o definición de columnas DDL con DuckDB
    y retorna la estructura columnar tipificada y clasificada semánticamente.
    """
    texto = (ddlText or "").strip()
    if not texto:
        return {"exito": False, "error": "La sentencia DDL SQL no puede estar vacía."}

    if not re.search(r'^\s*CREATE\s+TABLE', texto, re.IGNORECASE):
        columnasRaw = texto.strip(';').strip()
        if not (columnasRaw.startswith('(') and columnasRaw.endswith(')')):
            columnasRaw = f"({columnasRaw})"
        ddlEjecutar = f"CREATE TABLE _tabla_temp_ddl {columnasRaw};"
        nombreTabla = "_tabla_temp_ddl"
    else:
        m = re.search(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_\.\"\'`]+)\s*\(', texto, re.IGNORECASE)
        if m:
            nombreTabla = m.group(1).replace('"', '').replace("'", "").replace("`", "")
            ddlEjecutar = texto
        else:
            return {"exito": False, "error": "No se pudo interpretar la sintaxis de CREATE TABLE."}

    con = duckdb.connect()
    try:
        con.execute(ddlEjecutar)
        columnasInfo = con.execute(f"DESCRIBE {nombreTabla};").fetchall()
        resultado = []
        for row in columnasInfo:
            colNom = str(row[0]).strip()
            colTipo = str(row[1]).upper()
            esTemporal = any(t in colTipo for t in ["DATE", "TIME", "TIMESTAMP"]) or any(
                p in colNom.lower() for p in ["fecha", "date", "anio", "mes", "dia", "periodo"]
            )
            esMetrica = any(t in colTipo for t in ["INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "HUGEINT", "BIGINT"]) and not (
                colNom.lower().startswith("id_") or colNom.lower().endswith("_id") or colNom.lower() == "id" or "codigo" in colNom.lower()
            )
            clasif = "Temporal" if esTemporal else ("MetricaSumable" if esMetrica else "Categorica/Dimension")
            resultado.append({
                "nombre": colNom,
                "tipo": colTipo,
                "clasificacion": clasif
            })
        return {
            "exito": True,
            "nombreTablaSugerido": nombreTabla if nombreTabla != "_tabla_temp_ddl" else "cubo_data_lake",
            "columnas": resultado
        }
    except Exception as e:
        return {"exito": False, "error": f"Error al interpretar sintaxis SQL DDL con DuckDB: {str(e)}"}
    finally:
        con.close()


@router.post("/api/ingesta/datalake/parsear-ddl")
async def apiParsearDdlDataLake(
    payload: dict = Body(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Interpreta una sentencia CREATE TABLE o definición de columnas DDL con DuckDB
    y retorna la estructura columnar tipificada y clasificada semánticamente.
    """
    ddl = payload.get("ddl", "")
    res = parsearDdlSql(ddl)
    if not res.get("exito"):
        return JSONResponse(res, status_code=400)
    return JSONResponse(res)


@router.post("/api/ingesta/datalake/crear-cubo-vacio")
async def apiCrearCuboVacioDataLake(
    payload: dict = Body(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Crea un Cubo OBT vacío de origen Data Lake (PROCESO_MASIVO), generando físicamente
    el archivo .parquet vacío con compresión ZSTD y registrándolo en el catálogo relacional
    para que pipelines o ETLs externas puedan depositar los datos masivos.
    """
    nombreCubo = sanitizarNombreVista(payload.get("nombreCubo", "Cubo Data Lake"))
    codigoCubo = sanitizarCodigoVista(payload.get("codigoCubo", nombreCubo))
    columnas = payload.get("columnas", [])

    if not columnas or not isinstance(columnas, list):
        return JSONResponse({"exito": False, "error": "Debes definir al menos una columna para el esquema del cubo."}, status_code=400)

    directorioParquets = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
    ))
    os.makedirs(directorioParquets, exist_ok=True)
    nombreArchivoParquet = f"{codigoCubo}.parquet"
    rutaParquet = os.path.join(directorioParquets, nombreArchivoParquet)
    rutaSql = rutaParquet.replace("\\", "/")

    # Construir mapeo y DDL DuckDB
    mapeoColumnas = {}
    defsColumnas = []
    for col in columnas:
        colNom = sanitizarCodigoVista(col.get("nombre", "columna"))
        colTipo = str(col.get("tipo", "VARCHAR")).strip().upper()
        colClasif = col.get("clasificacion", "Categorica/Dimension")
        
        mapeoColumnas[colNom] = {
            "tipoDato": colTipo,
            "clasificacionSemantica": colClasif
        }
        defsColumnas.append(f'"{colNom}" {colTipo}')

    ddlSql = f"CREATE TABLE _cubo_lake_init ({', '.join(defsColumnas)});"

    con = duckdb.connect()
    try:
        con.execute(ddlSql)
        con.execute(f"COPY _cubo_lake_init TO '{rutaSql}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    except Exception as e:
        return JSONResponse({"exito": False, "error": f"Fallo al generar archivo Parquet vacío: {str(e)}"}, status_code=500)
    finally:
        con.close()

    contrato = {
        "idModelo": codigoCubo,
        "nombreVista": nombreCubo,
        "tipoIngesta": "ProcesoMasivo",
        "descripcion": "Cubo vacío creado para alimentación por ETL masiva externa.",
        "columnas": [
            {
                "nombreColumna": k,
                "tipoDato": v["tipoDato"],
                "clasificacionSemantica": v["clasificacionSemantica"]
            }
            for k, v in mapeoColumnas.items()
        ]
    }

    with obtenerSesion() as sesion:
        cubo = sesion.query(CuboModelo).filter(
            (CuboModelo.archivoParquet == rutaParquet) | (CuboModelo.nombreCubo == nombreCubo)
        ).first()

        if not cubo:
            cubo = CuboModelo(
                nombreCubo=nombreCubo,
                archivoParquet=rutaParquet,
                tipoOrigen="PROCESO_MASIVO",
                configuracionOrigenJson=json.dumps(contrato),
                estadoHabilitado=True,
                fechaUltimaCarga=datetime.utcnow(),
                metadatosColumnasJson=json.dumps(mapeoColumnas)
            )
            sesion.add(cubo)
            sesion.flush()
        else:
            cubo.nombreCubo = nombreCubo
            cubo.archivoParquet = rutaParquet
            cubo.tipoOrigen = "PROCESO_MASIVO"
            cubo.fechaUltimaCarga = datetime.utcnow()
            cubo.configuracionOrigenJson = json.dumps(contrato)
            cubo.metadatosColumnasJson = json.dumps(mapeoColumnas)

        idCubo = cubo.idCubo
        nombreRegistrado = cubo.nombreCubo
        sesion.commit()

    return JSONResponse({
        "exito": True,
        "idCubo": idCubo,
        "nombreCubo": nombreRegistrado,
        "codigoCubo": codigoCubo,
        "archivoParquet": nombreArchivoParquet,
        "rutaAbsolutaParquet": rutaParquet,
        "totalColumnas": len(mapeoColumnas),
        "mensaje": f"Cubo Data Lake '{nombreRegistrado}' creado exitosamente con {len(mapeoColumnas)} columnas vacías, listo para ingesta por ETL externa."
    })


@router.post("/api/ingesta/inspeccionar-claves")
async def inspeccionarClavesCruce(
    solicitud: SolicitudInspeccionClaves = Body(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Inspecciona y calcula cardinalidad en DuckDB advirtiendo si la clave o combinación
    de claves de B produce fan-out (duplicación de métricas).
    """
    condicionesDict = [c.model_dump() for c in solicitud.obtenerCondiciones()]
    diagnostico = GeneradorCuboCompuesto.validarRiesgoDuplicacion(
        rutaOrigenA=solicitud.rutaOrigenA,
        rutaOrigenB=solicitud.rutaOrigenB,
        claveA=solicitud.claveOrigenA,
        claveB=solicitud.claveOrigenB,
        condiciones=condicionesDict
    )
    return JSONResponse(diagnostico)


@router.post("/api/ingesta/crear-cubo-compuesto")
async def crearCuboCompuesto(
    solicitud: SolicitudCuboCompuesto = Body(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Ejecuta el JOIN en DuckDB (soportando claves simples o compuestas), guarda el nuevo Parquet ZSTD
    y registra la vista en VistaModelo con trazabilidad completa.
    """
    directorioParquets = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
    ))
    os.makedirs(directorioParquets, exist_ok=True)
    rutaDestino = os.path.join(directorioParquets, f"{solicitud.codigoNuevoCubo}.parquet")

    # Identificar tipo de origen de cada fuente para trazabilidad
    tipoOrigenA = "Desconocido"
    tipoOrigenB = "Desconocido"

    with obtenerSesion() as sesion:
        vistas = sesion.query(VistaModelo).all()
        for v in vistas:
            if v.rutaArchivoParquet:
                if os.path.abspath(v.rutaArchivoParquet).lower() == os.path.abspath(solicitud.rutaOrigenA).lower():
                    tipoOrigenA = v.tipoIngesta
                if os.path.abspath(v.rutaArchivoParquet).lower() == os.path.abspath(solicitud.rutaOrigenB).lower():
                    tipoOrigenB = v.tipoIngesta

    condicionesObj = solicitud.obtenerCondiciones()
    condicionesDict = [c.model_dump() for c in condicionesObj]

    # Ejecutar cruce y guardado físico con DuckDB
    try:
        columnasDict = [col.model_dump() for col in solicitud.columnas]
        resultadoGeneracion = GeneradorCuboCompuesto.generarParquetCompuesto(
            rutaOrigenA=solicitud.rutaOrigenA,
            rutaOrigenB=solicitud.rutaOrigenB,
            tipoJoin=solicitud.tipoJoin,
            columnasMapeadas=columnasDict,
            rutaDestinoParquet=rutaDestino,
            condiciones=condicionesDict
        )
    except Exception as errorDuck:
        return JSONResponse({"exito": False, "error": f"Fallo al generar Parquet compuesto: {str(errorDuck)}"}, status_code=500)

    # Construir contrato semántico con trazabilidad de orígenes
    columnasContrato = [
        {
            "nombreColumna": col.nombreFinal,
            "tipoDatoEsperado": "texto" if "Categorica" in col.clasificacionSemantica else "decimal",
            "clasificacionSemantica": col.clasificacionSemantica,
            "origenColumna": col.origen,
            "nombreOriginal": col.nombreOriginal
        }
        for col in solicitud.columnas
        if col.clasificacionSemantica != "Identificador/Descarte"
    ]

    contrato = {
        "idModelo": solicitud.codigoNuevoCubo,
        "nombreVista": solicitud.nombreNuevoCubo,
        "tipoIngesta": "CuboCompuesto",
        "trazabilidadOrigenes": {
            "origenA": {"ruta": solicitud.rutaOrigenA, "tipo": tipoOrigenA},
            "origenB": {"ruta": solicitud.rutaOrigenB, "tipo": tipoOrigenB},
            "condicionesJoin": condicionesDict,
            "tipoJoin": solicitud.tipoJoin
        },
        "columnas": columnasContrato
    }

    nombreFinalCubo = sanitizarNombreVista(solicitud.nombreNuevoCubo or solicitud.codigoNuevoCubo or "Cubo Compuesto")
    slugCubo = sanitizarCodigoVista(solicitud.codigoNuevoCubo or nombreFinalCubo)
    with obtenerSesion() as sesion:
        cubo = sesion.query(CuboModelo).filter(
            (CuboModelo.archivoParquet == rutaDestino) | (CuboModelo.nombreCubo == nombreFinalCubo)
        ).first()
        if not cubo:
            cubo = CuboModelo(
                nombreCubo=nombreFinalCubo,
                archivoParquet=rutaDestino,
                tipoOrigen="COMPUESTO",
                configuracionOrigenJson=json.dumps(contrato),
                estadoHabilitado=True,
                fechaUltimaCarga=datetime.utcnow(),
                metadatosColumnasJson=json.dumps(columnasContrato)
            )
            sesion.add(cubo)
            sesion.flush()
        else:
            cubo.nombreCubo = nombreFinalCubo
            cubo.archivoParquet = rutaDestino
            cubo.tipoOrigen = "COMPUESTO"
            cubo.fechaUltimaCarga = datetime.utcnow()
            cubo.configuracionOrigenJson = json.dumps(contrato)
            cubo.metadatosColumnasJson = json.dumps(columnasContrato)

        idCubo = cubo.idCubo
        nombreRegistrado = cubo.nombreCubo
        sesion.commit()

    return JSONResponse({
        "exito": True,
        "idCubo": idCubo,
        "nombreCubo": nombreRegistrado,
        "codigoCubo": slugCubo,
        "codigoVista": slugCubo,
        "rutaParquet": rutaDestino,
        "totalFilas": resultadoGeneracion["totalFilasGeneradas"],
        "totalColumnas": len(columnasContrato),
        "columnas": columnasContrato,
        "mensaje": f"Cubo compuesto '{nombreRegistrado}' creado exitosamente en el Data Lake ({resultadoGeneracion['totalFilasGeneradas']:,} filas)."
    })


@router.post("/api/ingesta/excel/analizar-hojas")
async def analizarTodasLasHojasExcel(
    archivo: UploadFile = File(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Lee todas las hojas de un archivo Excel con Calamine Rust y perfila sus esquemas
    para permitir el modelado relacional multi-hoja con JOINs.
    """
    try:
        contenido = await archivo.read()
        hojas = CalamineLectorExcel.obtenerHojasLibro(contenido)
        if not hojas:
            return JSONResponse({"exito": False, "error": "El archivo Excel no contiene hojas válidas."}, status_code=400)

        detalleHojas = {}
        for h in hojas:
            try:
                muestra = CalamineLectorExcel.extraerMuestraHoja(contenido, h, limiteFilas=5)
                colsInfo = []
                for c in muestra["columnas"]:
                    perfilC = muestra["perfilColumnas"].get(c, {})
                    colsInfo.append({
                        "nombre": c,
                        "tipo": perfilC.get("tipoDatoPrimitivo", "texto"),
                        "clasificacion": perfilC.get("clasificacionSugerida", "Categorica/Dimension"),
                        "conteoNoNulos": perfilC.get("conteoNoNulos", 0),
                        "valoresUnicos": perfilC.get("valoresUnicos", 0)
                    })
                detalleHojas[h] = {
                    "totalColumnas": muestra["totalColumnas"],
                    "columnas": colsInfo,
                    "filasMuestra": muestra["filasMuestra"]
                }
            except Exception as exHoja:
                detalleHojas[h] = {
                    "totalColumnas": 0,
                    "columnas": [],
                    "error": str(exHoja)
                }

        return JSONResponse({
            "exito": True,
            "nombreArchivo": archivo.filename,
            "hojas": hojas,
            "detalleHojas": detalleHojas
        })
    except Exception as e:
        return JSONResponse({"exito": False, "error": f"Error al analizar hojas del Excel: {str(e)}"}, status_code=500)


@router.post("/api/ingesta/excel/inspeccionar-claves-multihoja")
async def inspeccionarClavesMultiHojaExcel(
    archivo: UploadFile = File(...),
    hojaA: str = Form(...),
    hojaB: str = Form(...),
    condicionesJson: str = Form(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Evalúa en DuckDB el riesgo de fan-out y la cardinalidad del cruce entre dos hojas del Excel.
    """
    try:
        contenido = await archivo.read()
        dfA = CalamineLectorExcel.convertirHojaADataFrame(contenido, hojaA)
        dfB = CalamineLectorExcel.convertirHojaADataFrame(contenido, hojaB)
        condiciones = json.loads(condicionesJson)

        diagnostico = GeneradorCuboCompuesto.validarRiesgoDuplicacionDataFrames(
            dfA=dfA,
            dfB=dfB,
            condiciones=condiciones
        )
        return JSONResponse(diagnostico)
    except Exception as e:
        return JSONResponse({"exito": False, "error": f"Error evaluando claves en Excel: {str(e)}"}, status_code=500)


@router.post("/api/ingesta/excel/procesar-multihoja")
async def procesarYGuardarExcelMultiHoja(
    archivo: UploadFile = File(...),
    nombreCubo: Optional[str] = Form(None),
    codigoCubo: Optional[str] = Form(None),
    codigoVista: Optional[str] = Form(None),
    nombreVista: Optional[str] = Form(None),
    hojaA: str = Form(...),
    hojaB: str = Form(...),
    tipoJoin: str = Form("LEFT"),
    condicionesJson: str = Form(...),
    configuracionColumnasJson: str = Form(...),
    rolDefecto: Optional[str] = Form("TODOS"),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Ejecuta el cruce relacional vectorizado entre dos hojas de un archivo Excel,
    materializa el archivo Apache Parquet con compresión ZSTD y registra el Cubo en el catálogo (dbo.cubos).
    """
    try:
        nombreFinalCubo = sanitizarNombreVista(nombreCubo or nombreVista or codigoVista or "Cubo Excel MultiHoja")
        slugCubo = sanitizarCodigoVista(codigoCubo or codigoVista or nombreFinalCubo)
        contenido = await archivo.read()
        dfA = CalamineLectorExcel.convertirHojaADataFrame(contenido, hojaA)
        dfB = CalamineLectorExcel.convertirHojaADataFrame(contenido, hojaB)
        condiciones = json.loads(condicionesJson)
        columnasConfiguradas = json.loads(configuracionColumnasJson)

        directorioParquets = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
        ))
        os.makedirs(directorioParquets, exist_ok=True)
        rutaParquet = os.path.join(directorioParquets, f"{slugCubo}.parquet")

        resultadoGeneracion = GeneradorCuboCompuesto.generarParquetDesdeDataFramesCompuestos(
            dfA=dfA,
            dfB=dfB,
            condiciones=condiciones,
            tipoJoin=tipoJoin,
            columnasMapeadas=columnasConfiguradas,
            rutaDestinoParquet=rutaParquet
        )

        columnasContrato = [
            {
                "nombreColumna": c["nombreFinal"],
                "tipoDatoEsperado": "texto" if "Categorica" in c.get("clasificacionSemantica", "") else "decimal",
                "clasificacionSemantica": c.get("clasificacionSemantica", "Categorica/Dimension"),
                "origenColumna": c.get("origen", "A"),
                "nombreOriginal": c.get("nombreOriginal", c["nombreFinal"])
            }
            for c in columnasConfiguradas
            if c.get("clasificacionSemantica") != "Identificador/Descarte" and c.get("esObligatoria", True)
        ]

        contrato = {
            "idModelo": slugCubo,
            "nombreVista": nombreFinalCubo,
            "tipoIngesta": "ExcelMultiHojaJOIN",
            "trazabilidadOrigenes": {
                "archivo": archivo.filename,
                "hojaA": hojaA,
                "hojaB": hojaB,
                "condicionesJoin": condiciones,
                "tipoJoin": tipoJoin
            },
            "columnas": columnasContrato
        }

        with obtenerSesion() as sesion:
            cubo = sesion.query(CuboModelo).filter(
                (CuboModelo.archivoParquet == rutaParquet) | (CuboModelo.nombreCubo == nombreFinalCubo)
            ).first()
            if not cubo:
                cubo = CuboModelo(
                    nombreCubo=nombreFinalCubo,
                    archivoParquet=rutaParquet,
                    tipoOrigen="EXCEL_MULTIHOJA",
                    configuracionOrigenJson=json.dumps(contrato),
                    estadoHabilitado=True,
                    fechaUltimaCarga=datetime.utcnow(),
                    metadatosColumnasJson=json.dumps(columnasContrato)
                )
                sesion.add(cubo)
                sesion.flush()
            else:
                cubo.nombreCubo = nombreFinalCubo
                cubo.archivoParquet = rutaParquet
                cubo.tipoOrigen = "EXCEL_MULTIHOJA"
                cubo.fechaUltimaCarga = datetime.utcnow()
                cubo.configuracionOrigenJson = json.dumps(contrato)
                cubo.metadatosColumnasJson = json.dumps(columnasContrato)

            idCubo = cubo.idCubo
            nombreRegistrado = cubo.nombreCubo
            sesion.commit()

        return JSONResponse({
            "exito": True,
            "mensaje": f"Cubo Multi-Hoja '{nombreVista}' generado exitosamente con {resultadoGeneracion['totalFilasGeneradas']:,} filas.",
            "codigoVista": codigoVista,
            "rutaParquet": rutaParquet,
            "totalFilas": resultadoGeneracion["totalFilasGeneradas"],
            "rolesAsignados": list(set(rolesAsignadosNombres))
        })
    except Exception as e:
        return JSONResponse({"exito": False, "error": f"Error al procesar cruce multi-hoja de Excel: {str(e)}"}, status_code=500)


@router.post("/api/ingesta/excel/analizar-libro-completo")
async def analizarLibroExcelCompleto(
    archivo: UploadFile = File(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Inspecciona todas las hojas del libro Excel, detectando automáticamente hojas
    idénticas en columnas (candidatas a UNION ALL consolidada) y hojas dimensionales
    dispares para modelado en Diagrama de Estrella.
    """
    try:
        contenido = await archivo.read()
        diagnostico = CalamineLectorExcel.analizarLibroCompleto(contenido)
        if not diagnostico.get("exito"):
            return JSONResponse(diagnostico, status_code=400)

        diagnostico["nombreArchivo"] = archivo.filename
        return JSONResponse(diagnostico)
    except Exception as e:
        return JSONResponse({"exito": False, "error": f"Fallo al analizar estructura del libro Excel: {str(e)}"}, status_code=500)


@router.post("/api/ingesta/excel/procesar-estrella")
async def procesarYGuardarExcelEstrella(
    archivo: UploadFile = File(...),
    nombreCubo: Optional[str] = Form(None),
    codigoCubo: Optional[str] = Form(None),
    codigoVista: Optional[str] = Form(None),
    nombreVista: Optional[str] = Form(None),
    modalidad: str = Form("ExcelModalidadA"),
    rolDefecto: Optional[str] = Form("TODOS"),
    hojasUnificarJson: str = Form("[]"),
    relacionesJson: str = Form("[]"),
    configuracionColumnasJson: Optional[str] = Form("[]"),
    hojaPrincipal: Optional[str] = Form(None),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Procesa un libro Excel unificando automáticamente N hojas idénticas en la tabla
    de hechos central y relacionando las hojas dimensionales dispares mediante
    un Diagrama de Estrella con DuckDB vectorizado y compresión ZSTD, registrando
    exclusivamente el Cubo en el catálogo (dbo.cubos).
    """
    try:
        nombreFinalCubo = sanitizarNombreVista(nombreCubo or nombreVista or codigoVista or "Cubo Excel Estrella")
        slugCubo = sanitizarCodigoVista(codigoCubo or codigoVista or nombreFinalCubo)
        contenido = await archivo.read()
        hojasAUnificar = json.loads(hojasUnificarJson) if hojasUnificarJson else []
        relaciones = json.loads(relacionesJson) if relacionesJson else []
        columnasConfiguradas = json.loads(configuracionColumnasJson) if configuracionColumnasJson else []

        # 1. Obtener la tabla de hechos (unificada o única)
        if len(hojasAUnificar) > 1:
            dfHechos = CalamineLectorExcel.unificarHojasIdenticas(contenido, hojasAUnificar, columnaTrazadora="hoja_origen")
        elif len(hojasAUnificar) == 1:
            dfHechos = CalamineLectorExcel.convertirHojaADataFrame(contenido, hojasAUnificar[0])
        elif hojaPrincipal:
            dfHechos = CalamineLectorExcel.convertirHojaADataFrame(contenido, hojaPrincipal)
        else:
            hojasLibro = CalamineLectorExcel.obtenerHojasLibro(contenido)
            dfHechos = CalamineLectorExcel.convertirHojaADataFrame(contenido, hojasLibro[0])

        # 2. Cargar DataFrames de dimensiones referenciadas
        mapaDimensiones = {}
        for rel in relaciones:
            nomDim = rel.get("nombreDimension") or rel.get("hojaDimension")
            if nomDim and nomDim not in mapaDimensiones:
                mapaDimensiones[nomDim] = CalamineLectorExcel.convertirHojaADataFrame(contenido, nomDim)

        directorioParquets = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
        ))
        os.makedirs(directorioParquets, exist_ok=True)
        rutaParquet = os.path.join(directorioParquets, f"{slugCubo}.parquet")

        # 3. Materializar Parquet con DuckDB
        resultadoGeneracion = GeneradorCuboCompuesto.generarParquetEsquemaEstrella(
            dfHechos=dfHechos,
            mapaDimensiones=mapaDimensiones,
            relaciones=relaciones,
            columnasMapeadas=columnasConfiguradas,
            rutaDestinoParquet=rutaParquet
        )

        # 4. Construir contrato semántico con trazabilidad
        if columnasConfiguradas:
            columnasContrato = [
                {
                    "nombreColumna": c.get("nombreFinal") or c.get("nombreOriginal") or c.get("nombre"),
                    "tipoDatoEsperado": "decimal" if "Metrica" in c.get("clasificacionSemantica", "") else "texto",
                    "clasificacionSemantica": c.get("clasificacionSemantica", "Categorica/Dimension"),
                    "origenColumna": c.get("origen", "HECHOS"),
                    "nombreOriginal": c.get("nombreOriginal") or c.get("nombre")
                }
                for c in columnasConfiguradas
                if c.get("clasificacionSemantica") != "Identificador/Descarte" and c.get("esObligatoria", True)
            ]
        else:
            # Perfilado automático si no se enviaron columnas explícitas
            meta = GeneradorCuboCompuesto.obtenerMetadatosOrigen(rutaParquet)
            columnasContrato = [
                {
                    "nombreColumna": c["nombreColumna"],
                    "tipoDatoEsperado": "decimal" if c["esNumerico"] else "texto",
                    "clasificacionSemantica": c["clasificacionSugerida"],
                    "origenColumna": "ESTRELLA",
                    "nombreOriginal": c["nombreColumna"]
                }
                for c in meta["columnas"]
            ]

        contrato = {
            "idModelo": slugCubo,
            "nombreVista": nombreFinalCubo,
            "tipoIngesta": "ExcelEstrella",
            "modalidad": modalidad,
            "trazabilidadOrigenes": {
                "archivo": archivo.filename,
                "hojasUnificadas": hojasAUnificar,
                "relacionesEstrella": relaciones,
                "dimensiones": list(mapaDimensiones.keys())
            },
            "columnas": columnasContrato
        }

        with obtenerSesion() as sesion:
            cubo = sesion.query(CuboModelo).filter(
                (CuboModelo.archivoParquet == rutaParquet) | (CuboModelo.nombreCubo == nombreFinalCubo)
            ).first()
            if not cubo:
                cubo = CuboModelo(
                    nombreCubo=nombreFinalCubo,
                    archivoParquet=rutaParquet,
                    tipoOrigen="EXCEL_ESTRELLA",
                    configuracionOrigenJson=json.dumps(contrato),
                    estadoHabilitado=True,
                    fechaUltimaCarga=datetime.utcnow(),
                    metadatosColumnasJson=json.dumps(columnasContrato)
                )
                sesion.add(cubo)
                sesion.flush()
            else:
                cubo.nombreCubo = nombreFinalCubo
                cubo.archivoParquet = rutaParquet
                cubo.fechaUltimaCarga = datetime.utcnow()
                cubo.tipoOrigen = "EXCEL_ESTRELLA"
                cubo.configuracionOrigenJson = json.dumps(contrato)
                cubo.metadatosColumnasJson = json.dumps(columnasContrato)

            idCubo = cubo.idCubo
            nombreRegistrado = cubo.nombreCubo
            sesion.commit()

        return JSONResponse({
            "exito": True,
            "idCubo": idCubo,
            "nombreCubo": nombreRegistrado,
            "codigoCubo": slugCubo,
            "codigoVista": slugCubo,
            "rutaParquet": rutaParquet,
            "totalFilas": resultadoGeneracion["totalFilasGeneradas"],
            "totalColumnas": resultadoGeneracion["totalColumnas"],
            "columnas": columnasContrato,
            "mensaje": f"Cubo en Estrella '{nombreRegistrado}' materializado exitosamente ({resultadoGeneracion['totalFilasGeneradas']} filas, {resultadoGeneracion['totalColumnas']} columnas)."
        })
    except Exception as e:
        return JSONResponse({"exito": False, "error": f"Error al procesar Diagrama de Estrella en Excel: {str(e)}"}, status_code=500)

