"""
Router de FastAPI para los módulos de Administración de Cubos y Administración de Vistas.
Provee interfaces web y endpoints REST para la gobernanza del ciclo de vida y auditoría.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Depends, Body, Path, UploadFile, File, Form, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel
from sistemaAnalitica.app.dependencias import requerirUsuarioAutenticado, requerirPermisoPantalla
from sistemaAnalitica.modulos.motorAnalitico.servicioGestionCubos import ServicioGestionCubos
from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import CuboModelo, VistaModelo, ConexionBaseDatosModelo, RolModelo

router = APIRouter(tags=["Administración"])
templates = Jinja2Templates(directory="sistemaAnalitica/app/templates")


# ==============================================================================
# VISTAS HTML DE ADMINISTRACIÓN
# ==============================================================================

@router.get("/administracion/cubos", response_class=HTMLResponse)
async def mostrarAdministracionCubos(
    request: Request,
    user: dict = Depends(requerirPermisoPantalla("ADMINISTRACION_CUBOS"))
):
    """
    Despliega la pantalla de gestión del ciclo de vida de los cubos Parquet OBT.
    """
    cubos = ServicioGestionCubos.listarCubosConMetadatos()
    with obtenerSesion() as sesion:
        conexiones = sesion.query(ConexionBaseDatosModelo).filter_by(activo=True).all()
        listaConexiones = [
            {"idConexion": c.idConexion, "nombreConexion": c.nombreConexion, "motorBaseDatos": c.motorBaseDatos}
            for c in conexiones
        ]

    return templates.TemplateResponse(
        request=request,
        name="administracionCubos.html",
        context={
            "user": user,
            "ruta_activa": "administracion_cubos",
            "cubos": cubos,
            "conexiones": listaConexiones
        }
    )


@router.get("/administracion/vistas", response_class=HTMLResponse)
async def mostrarAdministracionVistas(
    request: Request,
    user: dict = Depends(requerirPermisoPantalla("ADMINISTRACION_VISTAS"))
):
    """
    Despliega la pantalla de auditoría y gestión de vistas analíticas.
    """
    vistas = ServicioGestionCubos.listarVistasConAuditoria()
    with obtenerSesion() as sesion:
        cubos = sesion.query(CuboModelo).filter(CuboModelo.estadoHabilitado == True).order_by(CuboModelo.nombreCubo).all()
        listaCubos = [
            {"idCubo": c.idCubo, "nombreCubo": c.nombreCubo, "tipoOrigen": c.tipoOrigen, "archivoParquet": c.archivoParquet}
            for c in cubos
        ]
        roles = sesion.query(RolModelo).filter(RolModelo.activo == True).order_by(RolModelo.nombreRol).all()
        listaRoles = [
            {"idRol": r.idRol, "nombreRol": r.nombreRol}
            for r in roles
        ]

    return templates.TemplateResponse(
        request=request,
        name="administracionVistas.html",
        context={
            "user": user,
            "ruta_activa": "administracion_vistas",
            "vistas": vistas,
            "cubos": listaCubos,
            "roles": listaRoles
        }
    )


# ==============================================================================
# ENDPOINTS REST: GESTIÓN DE CUBOS
# ==============================================================================

@router.post("/api/cubos/{idCubo}/estado")
async def conmutarEstadoCubo(
    idCubo: int = Path(..., description="ID numérico del cubo"),
    datos: Optional[Dict[str, Any]] = Body(None),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Activa o desactiva un cubo analítico OBT.
    """
    nuevoEstado = None
    if datos and "estadoHabilitado" in datos:
        nuevoEstado = bool(datos["estadoHabilitado"])
    else:
        with obtenerSesion() as sesion:
            cubo = sesion.query(CuboModelo).filter_by(idCubo=idCubo).first()
            if not cubo:
                return JSONResponse({"exito": False, "error": "Cubo no encontrado."}, status_code=404)
            nuevoEstado = not cubo.estadoHabilitado

    resultado = ServicioGestionCubos.conmutarEstadoCubo(idCubo, nuevoEstado)
    if not resultado["exito"]:
        return JSONResponse(resultado, status_code=404)
    return JSONResponse(resultado)


@router.post("/api/cubos/{idCubo}/analizar-excel-actualizacion")
async def analizarExcelActualizacion(
    idCubo: int = Path(..., description="ID numérico del cubo"),
    archivoExcel: UploadFile = File(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Pre-analiza el libro Excel para actualización. Detecta si contiene hojas idénticas
    para unificación automática o si contiene hojas dimensionales que requieren
    confirmar/definir relaciones en estrella.
    """
    try:
        contenido = await archivoExcel.read()
        resultado = ServicioGestionCubos.analizarExcelParaActualizacion(idCubo, contenido)
        return JSONResponse(resultado)
    except Exception as e:
        return JSONResponse({"exito": False, "error": f"Fallo al pre-analizar Excel: {str(e)}"}, status_code=500)


@router.post("/api/cubos/{idCubo}/actualizar-datos")
async def actualizarDatosCubo(
    idCubo: int = Path(..., description="ID numérico del cubo"),
    archivoExcel: Optional[UploadFile] = File(None),
    relacionesJson: Optional[str] = Form(None),
    hojasUnificarJson: Optional[str] = Form(None),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Ejecuta el refresco de información según el tipo de origen del cubo.
    Admite UploadFile si el origen es Excel, unificando hojas idénticas
    o aplicando relaciones en estrella entre hojas.
    """
    contenidoBytes = None
    if archivoExcel:
        contenidoBytes = await archivoExcel.read()

    resultado = ServicioGestionCubos.actualizarDatosCubo(
        idCubo,
        nuevoArchivoExcel=contenidoBytes,
        relacionesJson=relacionesJson,
        hojasUnificarJson=hojasUnificarJson
    )
    if not resultado["exito"]:
        return JSONResponse(resultado, status_code=400)
    return JSONResponse(resultado)


@router.post("/api/cubos/{idCubo}/validar-esquema")
async def validarEsquemaCubo(
    idCubo: int = Path(..., description="ID numérico del cubo"),
    payload: Dict[str, Any] = Body(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Valida el impacto de modificar o eliminar columnas contra las vistas activas dependientes.
    """
    nuevasColumnas = payload.get("nuevasColumnas", [])
    resultado = ServicioGestionCubos.validarImpactoColumnas(idCubo, nuevasColumnas)
    return JSONResponse(resultado)


@router.put("/api/cubos/{idCubo}/columnas")
async def actualizarColumnasCubo(
    idCubo: int = Path(..., description="ID numérico del cubo"),
    payload: Dict[str, Any] = Body(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Persiste la actualización del esquema semántico del cubo si no existen vistas en conflicto.
    """
    mapeoColumnas = payload.get("mapeoColumnas", {})
    resultado = ServicioGestionCubos.actualizarEsquemaCubo(idCubo, mapeoColumnas)
    if not resultado["exito"]:
        return JSONResponse(resultado, status_code=409)
    return JSONResponse(resultado)


@router.post("/api/cubos/parsear-ddl")
async def apiParsearDdlCubo(
    payload: Dict[str, Any] = Body(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Parsea una definición DDL SQL para poblar o añadir columnas en la modificación de estructura.
    """
    from sistemaAnalitica.app.routers.ingesta import parsearDdlSql
    ddl = payload.get("ddl", "")
    res = parsearDdlSql(ddl)
    if not res.get("exito"):
        return JSONResponse(res, status_code=400)
    return JSONResponse(res)


@router.get("/api/cubos/{idCubo}/sql")
async def obtenerSqlCubo(
    idCubo: int = Path(..., description="ID numérico del cubo"),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Retorna la consulta SQL configurada y la conexión de base de datos asociada a un cubo.
    """
    import json
    with obtenerSesion() as sesion:
        cubo = sesion.query(CuboModelo).filter_by(idCubo=idCubo).first()
        if not cubo:
            return JSONResponse({"exito": False, "error": "Cubo no encontrado."}, status_code=404)

        consultaSql = ""
        idConexion = None
        if cubo.configuracionOrigenJson:
            try:
                cfg = json.loads(cubo.configuracionOrigenJson)
                consultaSql = cfg.get("consultaSql", "")
                idConexion = cfg.get("idConexion")
            except Exception:
                pass

        if not consultaSql and cubo.vistas:
            for v in cubo.vistas:
                if v.consultaSql:
                    consultaSql = v.consultaSql
                    idConexion = v.idConexion or idConexion
                    break

        conexiones = sesion.query(ConexionBaseDatosModelo).filter_by(activo=True).all()
        listaConexiones = [
            {"idConexion": c.idConexion, "nombreConexion": c.nombreConexion, "motorBaseDatos": c.motorBaseDatos}
            for c in conexiones
        ]

        return JSONResponse({
            "exito": True,
            "idCubo": cubo.idCubo,
            "nombreCubo": cubo.nombreCubo,
            "consultaSql": consultaSql,
            "idConexion": idConexion,
            "conexionesDisponibles": listaConexiones
        })


@router.put("/api/cubos/{idCubo}/sql")
async def modificarSqlCubo(
    idCubo: int = Path(..., description="ID numérico del cubo"),
    payload: Dict[str, Any] = Body(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Modifica la sentencia SQL y/o conexión asignada a un cubo OBT, con opción de refresco inmediato.
    """
    nuevaConsulta = payload.get("consultaSql", "").strip()
    nuevoIdConexion = payload.get("idConexion")
    removerLimite = bool(payload.get("removerLimiteMuestra", True))
    ejecutarRefresco = bool(payload.get("ejecutarRefresco", False))

    if not nuevaConsulta:
        return JSONResponse({"exito": False, "error": "Debe especificar una consulta SQL válida."}, status_code=400)

    resultado = ServicioGestionCubos.actualizarConsultaSqlCubo(
        idCubo=idCubo,
        nuevaConsultaSql=nuevaConsulta,
        nuevoIdConexion=int(nuevoIdConexion) if nuevoIdConexion else None,
        removerLimiteMuestra=removerLimite,
        ejecutarRefresco=ejecutarRefresco
    )

    if not resultado["exito"]:
        return JSONResponse(resultado, status_code=400)
    return JSONResponse(resultado)



# ==============================================================================
# ENDPOINTS REST: GESTIÓN DE VISTAS
# ==============================================================================

@router.post("/api/vistas/{idVista}/estado")
async def conmutarEstadoVista(
    idVista: int = Path(..., description="ID numérico de la vista"),
    datos: Optional[Dict[str, Any]] = Body(None),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Activa o desactiva granularmente una vista analítica.
    """
    nuevoEstado = None
    if datos and "estadoHabilitado" in datos:
        nuevoEstado = bool(datos["estadoHabilitado"])
    else:
        with obtenerSesion() as sesion:
            vista = sesion.query(VistaModelo).filter_by(idVista=idVista).first()
            if not vista:
                return JSONResponse({"exito": False, "error": "Vista no encontrada."}, status_code=404)
            nuevoEstado = not vista.estadoHabilitado

    resultado = ServicioGestionCubos.conmutarEstadoVista(idVista, nuevoEstado)
    if not resultado["exito"]:
        return JSONResponse(resultado, status_code=404)
    return JSONResponse(resultado)


class SolicitudCrearVista(BaseModel):
    nombreVista: str
    codigoVista: str
    idCubo: int
    descripcion: Optional[str] = None
    roles: Optional[List[int]] = None


@router.post("/api/vistas/crear")
async def crearNuevaVista(
    solicitud: SolicitudCrearVista = Body(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Crea una nueva Vista Analítica vinculada a un Cubo existente en el Data Lake.
    Inicializa el contrato semántico y la configuración visual por defecto.
    """
    import json, os, duckdb
    from sistemaAnalitica.app.routers.ingesta import sanitizarCodigoVista, sanitizarNombreVista
    
    nombreFinal = sanitizarNombreVista(solicitud.nombreVista)
    codigoFinal = sanitizarCodigoVista(solicitud.codigoVista or nombreFinal)
    
    with obtenerSesion() as sesion:
        cubo = sesion.query(CuboModelo).filter_by(idCubo=solicitud.idCubo).first()
        if not cubo:
            return JSONResponse({"exito": False, "error": "El Cubo seleccionado no existe."}, status_code=404)
        
        # Verificar unicidad del código de la vista
        vistaExistente = sesion.query(VistaModelo).filter_by(codigoVista=codigoFinal).first()
        if vistaExistente:
            return JSONResponse({"exito": False, "error": f"Ya existe una vista con el código '{codigoFinal}'."}, status_code=400)
        
        # Extraer columnas del cubo o del archivo parquet
        columnasContrato = []
        if cubo.metadatosColumnasJson:
            try:
                parsed = json.loads(cubo.metadatosColumnasJson)
                if isinstance(parsed, dict) and "columnas" in parsed:
                    columnasContrato = parsed["columnas"]
                elif isinstance(parsed, list):
                    columnasContrato = parsed
            except Exception:
                pass
        
        if not columnasContrato and cubo.archivoParquet and os.path.exists(cubo.archivoParquet):
            try:
                con = duckdb.connect()
                rutaSql = cubo.archivoParquet.replace("\\", "/")
                esquema = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{rutaSql}') LIMIT 1").fetchall()
                for c in esquema:
                    nombreCol = c[0]
                    tipoCol = str(c[1]).upper()
                    esNum = any(t in tipoCol for t in ["INT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "BIGINT"])
                    columnasContrato.append({
                        "nombreColumna": nombreCol,
                        "tipoDatoEsperado": "decimal" if esNum else "texto",
                        "clasificacionSemantica": "MetricaSumable" if esNum else "Categorica/Dimension",
                        "esObligatoria": True
                    })
                con.close()
            except Exception:
                pass
        
        # Normalizar columnasContrato para asegurar que cada elemento sea un diccionario
        columnasNormalizadas = []
        for c in columnasContrato:
            if isinstance(c, str):
                columnasNormalizadas.append({
                    "nombreColumna": c,
                    "tipoDatoEsperado": "texto",
                    "clasificacionSemantica": "Categorica/Dimension",
                    "esObligatoria": True
                })
            elif isinstance(c, dict):
                nom = c.get("nombreColumna", c.get("nombre", ""))
                tipo = c.get("tipoDatoEsperado", c.get("tipo", "texto"))
                clasif = c.get("clasificacionSemantica", c.get("clasificacion", "Categorica/Dimension"))
                columnasNormalizadas.append({
                    "nombreColumna": nom,
                    "tipoDatoEsperado": tipo,
                    "clasificacionSemantica": clasif,
                    "esObligatoria": c.get("esObligatoria", True)
                })
        columnasContrato = columnasNormalizadas

        # Generar contrato semántico
        contratoEsquema = {
            "idModelo": codigoFinal,
            "nombreVista": nombreFinal,
            "tipoIngesta": cubo.tipoOrigen,
            "columnas": columnasContrato
        }
        
        # Extraer dimensiones y métricas iniciales
        metricas = [
            c["nombreColumna"] for c in columnasContrato 
            if "Metrica" in c.get("clasificacionSemantica", "")
            or any(t in str(c.get("tipoDatoEsperado", "")).upper() for t in ["DECIMAL", "NUMERIC", "FLOAT"])
        ]
        dimensiones = [
            c["nombreColumna"] for c in columnasContrato 
            if c["nombreColumna"] not in metricas
        ]
        if not dimensiones and columnasContrato:
            dimensiones = [c["nombreColumna"] for c in columnasContrato]
        
        configuracionInicial = {
            "idVista": 0,
            "codigoVista": codigoFinal,
            "nombreVista": nombreFinal,
            "archivoParquet": cubo.archivoParquet,
            "granoPermitido": {
                "dimensionesVisibles": dimensiones,
                "metricas": [{"columna": m, "operacion": "SUM", "alias": m, "etiqueta": m} for m in metricas],
                "jerarquiaDrilldownPermitida": dimensiones,
                "permitirDrilldown": True
            },
            "politicaGobernanza": {
                "bloquearNivelDetalle": False,
                "columnasExcluidas": [],
                "permitirExportarDetalle": True,
                "tipoExportacionPermitida": "TOTAL"
            },
            "configuracionVisual": {
                "graficosPermitidos": ["BARRA", "LINEA", "TABLA", "DONA"],
                "graficoPredeterminado": "BARRA",
                "dimensionPredeterminada": dimensiones[0] if dimensiones else None,
                "metricaPredeterminada": metricas[0] if metricas else None,
                "paletaColores": ["#004482", "#006e20", "#005cab", "#0284c7", "#d97706", "#dc2626"]
            },
            "filtrosCubo": []
        }
        
        idUsuario = user.get("idUsuario") or user.get("id_usuario")
        nuevaVista = VistaModelo(
            codigoVista=codigoFinal,
            nombreVista=nombreFinal,
            descripcion=solicitud.descripcion,
            tipoIngesta=cubo.tipoOrigen or "EXCEL",
            rutaArchivoParquet=cubo.archivoParquet,
            contratoEsquemaJson=json.dumps(contratoEsquema, ensure_ascii=False),
            configuracionJson=json.dumps(configuracionInicial, ensure_ascii=False),
            idCubo=cubo.idCubo,
            creadoPorUsuarioId=idUsuario,
            estadoHabilitado=True,
            activo=True
        )
        sesion.add(nuevaVista)
        sesion.flush()
        
        configuracionInicial["idVista"] = nuevaVista.idVista
        nuevaVista.configuracionJson = json.dumps(configuracionInicial, ensure_ascii=False)
        
        if solicitud.roles and len(solicitud.roles) > 0:
            rolesAAsignar = sesion.query(RolModelo).filter(RolModelo.idRol.in_(solicitud.roles)).all()
            nuevaVista.roles = rolesAAsignar
        else:
            todosRoles = sesion.query(RolModelo).filter_by(activo=True).all()
            nuevaVista.roles = todosRoles
        
        idVistaGenerado = nuevaVista.idVista
        sesion.commit()
        
        return JSONResponse({
            "exito": True,
            "idVista": idVistaGenerado,
            "codigoVista": codigoFinal,
            "nombreVista": nombreFinal,
            "mensaje": f"Vista '{nombreFinal}' creada exitosamente vinculada al Cubo '{cubo.nombreCubo}'."
        })


# ==============================================================================
# ENDPOINTS REST: AUDITORÍA Y LOGS DEL SISTEMA
# ==============================================================================

@router.get("/api/sistema/logs")
async def consultarLogsSistema(
    limite: int = 50,
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Retorna los registros de auditoría y errores del sistema almacenados en logs_sistema en SQL Server.
    """
    from sistemaAnalitica.modulos.seguridad.gestorLogs import GestorLogsSistema
    registros = GestorLogsSistema.consultarLogsRecientes(limite=limite)
    return JSONResponse({
        "exito": True,
        "total": len(registros),
        "logs": registros
    })


# ==============================================================================
# MÓDULO DE DEPURACIÓN Y ELIMINACIÓN DE CUBOS Y VISTAS
# ==============================================================================

class SolicitudEliminacionLote(BaseModel):
    tipo: str  # 'cubos' o 'vistas'
    ids: List[int]


@router.get("/administracion/eliminacion", response_class=HTMLResponse)
async def mostrarEliminacionObjetos(
    request: Request,
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Despliega la interfaz de depuración, selección y eliminación de cubos y vistas con auditoría.
    """
    pantallasPermitidas = [p.get("codigoPantalla") for p in user.get("pantallasPermitidas", [])]
    esAdmin = user.get("nombreRol") == "Administrador"
    if not esAdmin and "ELIMINACION_OBJETOS" not in pantallasPermitidas and "ADMINISTRACION_CUBOS" not in pantallasPermitidas:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "codigo_estado": 403,
                "titulo_error": "Acceso Restringido",
                "mensaje_error": "No tienes privilegios para acceder al módulo de depuración y eliminación de objetos."
            },
            status_code=403
        )

    with obtenerSesion() as sesion:
        cubos = sesion.query(CuboModelo).order_by(CuboModelo.fechaCreacion.desc()).all()
        listaCubos = []
        for c in cubos:
            vistasAsoc = sesion.query(VistaModelo).filter_by(idCubo=c.idCubo, activo=True).all()
            nombresVistas = [v.nombreVista for v in vistasAsoc]
            listaCubos.append({
                "idCubo": c.idCubo,
                "nombreCubo": c.nombreCubo,
                "tipoOrigen": c.tipoOrigen,
                "archivoParquet": c.archivoParquet,
                "estadoHabilitado": c.estadoHabilitado,
                "fechaCreacion": c.fechaCreacion.strftime("%Y-%m-%d %H:%M") if c.fechaCreacion else "-",
                "totalVistasAsignadas": len(vistasAsoc),
                "nombresVistasAsignadas": nombresVistas,
                "puedeEliminar": len(vistasAsoc) == 0
            })

        vistas = sesion.query(VistaModelo).filter_by(activo=True).order_by(VistaModelo.fechaCreacion.desc()).all()
        listaVistas = []
        for v in vistas:
            nomCubo = v.cubo.nombreCubo if v.cubo else "-"
            listaVistas.append({
                "idVista": v.idVista,
                "codigoVista": v.codigoVista,
                "nombreVista": v.nombreVista,
                "tipoIngesta": v.tipoIngesta,
                "idCubo": v.idCubo,
                "nombreCubo": nomCubo,
                "estadoHabilitado": v.estadoHabilitado,
                "fechaCreacion": v.fechaCreacion.strftime("%Y-%m-%d %H:%M") if v.fechaCreacion else "-"
            })

    auditoriaReciente = ServicioGestionCubos.consultarAuditoriaEliminaciones(limite=100)

    return templates.TemplateResponse(
        request=request,
        name="eliminacionObjetos.html",
        context={
            "user": user,
            "ruta_activa": "eliminacion_objetos",
            "cubos": listaCubos,
            "vistas": listaVistas,
            "auditoria": auditoriaReciente
        }
    )


@router.delete("/api/administracion/cubos/{idCubo}")
async def apiEliminarCubo(
    idCubo: int = Path(...),
    request: Request = None,
    user: dict = Depends(requerirUsuarioAutenticado)
):
    ip = request.client.host if request and request.client else "127.0.0.1"
    resultado = ServicioGestionCubos.eliminarCubo(idCubo, user, direccionIp=ip)
    statusCode = 200 if resultado.get("exito") else 400
    return JSONResponse(resultado, status_code=statusCode)


@router.delete("/api/administracion/vistas/{idVista}")
async def apiEliminarVista(
    idVista: int = Path(...),
    request: Request = None,
    user: dict = Depends(requerirUsuarioAutenticado)
):
    ip = request.client.host if request and request.client else "127.0.0.1"
    resultado = ServicioGestionCubos.eliminarVista(idVista, user, direccionIp=ip)
    statusCode = 200 if resultado.get("exito") else 400
    return JSONResponse(resultado, status_code=statusCode)


@router.post("/api/administracion/eliminacion/lote")
async def apiEliminarLote(
    solicitud: SolicitudEliminacionLote,
    request: Request = None,
    user: dict = Depends(requerirUsuarioAutenticado)
):
    ip = request.client.host if request and request.client else "127.0.0.1"
    eliminados = []
    fallidos = []

    if solicitud.tipo.lower() in ("cubos", "cubo"):
        for idCubo in solicitud.ids:
            res = ServicioGestionCubos.eliminarCubo(idCubo, user, direccionIp=ip)
            if res.get("exito"):
                eliminados.append(res.get("nombreCubo", str(idCubo)))
            else:
                fallidos.append({"id": idCubo, "error": res.get("error")})
    elif solicitud.tipo.lower() in ("vistas", "vista"):
        for idVista in solicitud.ids:
            res = ServicioGestionCubos.eliminarVista(idVista, user, direccionIp=ip)
            if res.get("exito"):
                eliminados.append(res.get("nombreVista", str(idVista)))
            else:
                fallidos.append({"id": idVista, "error": res.get("error")})
    else:
        return JSONResponse({"exito": False, "error": "Tipo de objeto no reconocido."}, status_code=400)

    exitoGeneral = len(eliminados) > 0 or len(fallidos) == 0
    return JSONResponse({
        "exito": exitoGeneral,
        "totalEliminados": len(eliminados),
        "totalFallidos": len(fallidos),
        "eliminados": eliminados,
        "fallidos": fallidos,
        "mensaje": f"Se eliminaron {len(eliminados)} objeto(s). {f'Hubo {len(fallidos)} elemento(s) no eliminados.' if fallidos else ''}"
    })


@router.get("/api/administracion/eliminacion/auditoria")
async def apiConsultarAuditoria(
    limite: int = 100,
    user: dict = Depends(requerirUsuarioAutenticado)
):
    logs = ServicioGestionCubos.consultarAuditoriaEliminaciones(limite=limite)
    return JSONResponse({"exito": True, "total": len(logs), "auditoria": logs})

