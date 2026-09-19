"""
Router del Explorador de Cubos, Gráficos Plotly y Drill-Down para FastAPI.
Integra la Capa Semántica, Blindaje de Granularidad y Exportación de Resumen Protegido.
"""

import os
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Depends, Body, Query, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from sistemaAnalitica.app.dependencias import requerirUsuarioAutenticado, requerirPermisoPantalla
from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import VistaModelo
from sistemaAnalitica.modulos.seguridad import ServicioAutorizacion
from sistemaAnalitica.modulos.motorAnalitico.servicioDuckDb import ServicioDuckDb
from sistemaAnalitica.modulos.motorAnalitico import ServicioCapaSemantica, ErrorSeguridadGobernanza

router = APIRouter(tags=["Explorador"])
templates = Jinja2Templates(directory="sistemaAnalitica/app/templates")


@router.get("/explorador", response_class=HTMLResponse)
async def mostrarExplorador(
    request: Request,
    codigo: Optional[str] = Query(None),
    user: dict = Depends(requerirPermisoPantalla("EXPLORADOR"))
):
    """
    Despliega el explorador visual interactivo de cubos y gráficos analíticos autorizados.
    """
    idUsuario = user.get("idUsuario", 1)
    vistas = ServicioAutorizacion.obtenerVistasPermitidasUsuario(idUsuario)
    if not vistas:
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "codigo_estado": 403,
                "titulo_error": "Sin Cubos Analíticos Autorizados",
                "mensaje_error": "No tienes vistas ni cubos analíticos asignados a tu rol o perfil. Contacta al Administrador.",
                "detalle_tecnico": None
            }
        )

    vistaActual = None
    if codigo:
        vistaActual = next((v for v in vistas if v.codigoVista == codigo), None)
        if not vistaActual:
            # Comprobar si la vista existe pero está deshabilitada o pertenece a un cubo inactivo
            with obtenerSesion() as sesionVerif:
                vistaEnDb = sesionVerif.query(VistaModelo).filter_by(codigoVista=codigo, activo=True).first()
                if vistaEnDb:
                    mensajeInactivo = "La vista analítica se encuentra deshabilitada o su cubo subyacente está inactivo."
                    if vistaEnDb.cubo and not vistaEnDb.cubo.estadoHabilitado:
                        mensajeInactivo = "El cubo subyacente se encuentra inactivo."
                    elif not vistaEnDb.estadoHabilitado:
                        mensajeInactivo = f"La vista '{vistaEnDb.nombreVista}' se encuentra deshabilitada."

                    return templates.TemplateResponse(
                        request=request,
                        name="error.html",
                        context={
                            "codigo_estado": 403,
                            "titulo_error": "Vista o Cubo Inactivo",
                            "mensaje_error": mensajeInactivo,
                            "detalle_tecnico": f"Vista solicitada: {codigo}"
                        },
                        status_code=403
                    )
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={
                    "codigo_estado": 404,
                    "titulo_error": "Vista no encontrada",
                    "mensaje_error": f"La vista '{codigo}' no existe o no tienes permisos asignados.",
                    "detalle_tecnico": None
                },
                status_code=404
            )

    if not vistaActual:
        vistaActual = vistas[0]

    rutaParquet = vistaActual.rutaArchivoParquet
    if not rutaParquet or not os.path.exists(rutaParquet):
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "codigo_estado": 404,
                "titulo_error": "Archivo Parquet no encontrado",
                "mensaje_error": f"El archivo Parquet para el cubo '{vistaActual.codigoVista}' no existe en el almacenamiento.",
                "detalle_tecnico": f"Ruta esperada: {rutaParquet}"
            }
        )

    resumen = ServicioDuckDb.obtenerResumenCubo(rutaParquet)
    columnasInfo = resumen["columnas"]

    # Revisar si la vista tiene configuración semántica guardada
    configuracionSemantica = ServicioCapaSemantica.obtenerConfiguracionVista(vistaActual.codigoVista)

    dimensiones = []
    metricas = []
    graficosPermitidos = ["pie", "bar", "line", "area", "treemap", "scatter"]
    graficoPredeterminado = "bar"
    dimDefecto = None
    metDefecto = None

    if configuracionSemantica:
        dimensiones = configuracionSemantica.granoPermitido.dimensionesVisibles
        metricas = [m.columna for m in configuracionSemantica.granoPermitido.metricas]
        graficosPermitidos = configuracionSemantica.configuracionVisual.graficosPermitidos
        graficoPredeterminado = configuracionSemantica.configuracionVisual.graficoPredeterminado
        dimDefecto = configuracionSemantica.configuracionVisual.dimensionPredeterminada
        metDefecto = configuracionSemantica.configuracionVisual.metricaPredeterminada

    if not dimensiones:
        for c in columnasInfo:
            nom = c["nombreColumna"]
            tipo = c["tipoDato"].upper()
            if not any(t in tipo for t in ["INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "BIGINT"]):
                dimensiones.append(nom)

    if not metricas:
        for c in columnasInfo:
            nom = c["nombreColumna"]
            tipo = c["tipoDato"].upper()
            if any(t in tipo for t in ["INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "BIGINT"]):
                metricas.append(nom)

    if not metricas and columnasInfo:
        metricas.append(columnasInfo[0]["nombreColumna"])
    if not dimensiones and columnasInfo:
        dimensiones.append(columnasInfo[0]["nombreColumna"])

    jerarquiaDrilldown = []
    if configuracionSemantica and configuracionSemantica.granoPermitido.jerarquiaDrilldownPermitida:
        jerarquiaDrilldown = configuracionSemantica.granoPermitido.jerarquiaDrilldownPermitida
    elif dimensiones:
        jerarquiaDrilldown = list(dimensiones)

    if not dimDefecto or dimDefecto not in dimensiones:
        dimDefecto = dimensiones[0] if dimensiones else "categoria"
    if not metDefecto or metDefecto not in metricas:
        metDefecto = metricas[0] if metricas else "valor"

    # KPIs iniciales seguros
    totalFilas = resumen["totalFilas"]
    kpiSuma = "$0"
    kpiPromedio = "0.00"

    try:
        resultadoInicial = ServicioCapaSemantica.validarYEjecutarConsultaSegura(
            codigoVista=vistaActual.codigoVista,
            dimensionSolicitada=dimDefecto,
            metricaSolicitada=metDefecto,
            idUsuario=idUsuario,
            limiteFilas=1
        )
        kpis = resultadoInicial.get("kpis", {})
        sumaVal = kpis.get("suma", 0.0)
        promVal = kpis.get("promedio", 0.0)
        kpiSuma = f"${sumaVal:,.0f}" if sumaVal > 1000 else f"{sumaVal:,.2f}"
        kpiPromedio = f"{promVal:,.2f}"
    except Exception:
        pass

    return templates.TemplateResponse(
        request=request,
        name="explorador.html",
        context={
            "user": user,
            "vistas": vistas,
            "vista_actual": vistaActual,
            "dimensiones": dimensiones,
            "metricas": metricas,
            "jerarquia_drilldown": jerarquiaDrilldown,
            "dimension_seleccionada": dimDefecto,
            "metrica_seleccionada": metDefecto,
            "graficos_permitidos": graficosPermitidos,
            "grafico_predeterminado": graficoPredeterminado,
            "total_filas": f"{totalFilas:,}",
            "kpi_suma_principal": kpiSuma,
            "kpi_promedio_principal": kpiPromedio,
            "ruta_activa": "explorador"
        }
    )


@router.post("/api/olap/consultar")
async def consultarOlap(
    user: dict = Depends(requerirUsuarioAutenticado),
    datos: dict = Body(...)
):
    """
    API JSON segura con validación semántica de grano y RLS.
    """
    codigoVista = datos.get("codigoVista")
    dimension = datos.get("dimension")
    dimensionSecundaria = datos.get("dimensionSecundaria") or None
    metrica = datos.get("metrica")
    filtros = datos.get("filtros", [])

    idUsuario = user.get("idUsuario", 1)
    if not ServicioAutorizacion.verificarAccesoVista(idUsuario, codigoVista):
        return JSONResponse({
            "exito": False,
            "error": f"Acceso denegado al cubo analítico '{codigoVista}'."
        }, status_code=403)

    # Construir filtros Where acumulados
    clausulasWhere = []
    for f in filtros:
        dimF = f.get("dimension")
        valF = str(f.get("valor", "")).replace("'", "''")
        clausulasWhere.append(f'"{dimF}" = \'{valF}\'')

    try:
        resultado = ServicioCapaSemantica.validarYEjecutarConsultaSegura(
            codigoVista=codigoVista,
            dimensionSolicitada=dimension,
            dimensionSecundaria=dimensionSecundaria,
            metricaSolicitada=metrica,
            filtrosWhere=clausulasWhere if clausulasWhere else None,
            idUsuario=idUsuario,
            limiteFilas=300
        )
        return JSONResponse(resultado)

    except ErrorSeguridadGobernanza as errSeguridad:
        return JSONResponse({"exito": False, "error": str(errSeguridad)}, status_code=403)
    except Exception as errorDuck:
        return JSONResponse({"exito": False, "error": str(errorDuck)}, status_code=500)


@router.get("/api/olap/exportar/pre-verificar")
async def preVerificarExportacion(
    codigoVista: str = Query(...),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Verifica el volumen de filas a exportar antes de iniciar la descarga pesada.
    """
    idUsuario = user.get("idUsuario", 1)
    if not ServicioAutorizacion.verificarAccesoVista(idUsuario, codigoVista):
        return JSONResponse({
            "exito": False,
            "error": f"Acceso denegado para consultar el cubo '{codigoVista}'."
        }, status_code=403)

    from sistemaAnalitica.modulos.motorAnalitico.servicioExportacionOlap import ServicioExportacionOlap
    resultado = ServicioExportacionOlap.verificarVolumenExportacion(codigoVista, idUsuario)
    return JSONResponse(resultado)


@router.get("/api/olap/exportar")
async def exportarResumenBlindado(
    codigoVista: str = Query(...),
    formato: str = Query("csv"),
    user: dict = Depends(requerirUsuarioAutenticado)
):
    """
    Descarga el dataset exclusivamente en su grano agregado puro permitido,
    ya sea en formato Excel (.xlsx) particionado a 700k filas o CSV con UTF-8 BOM.
    """
    idUsuario = user.get("idUsuario", 1)
    if not ServicioAutorizacion.verificarAccesoVista(idUsuario, codigoVista):
        return JSONResponse({
            "exito": False,
            "error": f"Acceso denegado para exportar el cubo '{codigoVista}'."
        }, status_code=403)

    from sistemaAnalitica.modulos.motorAnalitico.servicioExportacionOlap import (
        ServicioExportacionOlap, ErrorLimiteExportacion
    )
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    formatoNorm = str(formato).lower().strip()

    try:
        if formatoNorm in ("excel", "xlsx"):
            rutaTemp, nombreArchivo, totalFilas = ServicioExportacionOlap.generarExcelBlindado(
                codigoVista=codigoVista,
                idUsuario=idUsuario
            )
            return FileResponse(
                path=rutaTemp,
                filename=nombreArchivo,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                background=BackgroundTask(os.remove, rutaTemp)
            )
        else:
            contenidoCsv, nombreArchivo, totalFilas = ServicioExportacionOlap.generarCsvBlindado(
                codigoVista=codigoVista,
                idUsuario=idUsuario
            )
            return Response(
                content=contenidoCsv,
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename={nombreArchivo}"}
            )
    except ErrorLimiteExportacion as errLimite:
        return JSONResponse({"exito": False, "error": str(errLimite)}, status_code=400)
    except Exception as e:
        return JSONResponse({"exito": False, "error": f"Error al generar exportación: {str(e)}"}, status_code=500)
