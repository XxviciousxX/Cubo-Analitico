"""
Router para la Configuración de Vistas Analíticas, Reglas de Visualización Plotly y Gobernanza de Granularidad.
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Body
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
import os
import json

from fastapi import APIRouter, Request, Depends, HTTPException, Body
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
import os
import json

from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import VistaModelo, ConfiguracionVistaEsquema
from sistemaAnalitica.app.dependencias import (
    requerirUsuarioAutenticado,
    requerirPermisoPantalla
)
from sistemaAnalitica.modulos.presentacion.sugeridorGraficos import SugeridorGraficos
import duckdb
from fastapi.templating import Jinja2Templates

plantillas = Jinja2Templates(directory="sistemaAnalitica/app/templates")

enrutador = APIRouter(prefix="", tags=["Configuración de Vistas"])


@enrutador.get("/configuracion-vistas", response_class=HTMLResponse)
async def vistaConfigurador(
    peticion: Request,
    idVista: Optional[int] = None,
    usuarioActual=Depends(requerirPermisoPantalla("CONFIGURACION_VISTAS"))
):
    """
    Renderiza la interfaz visual del configurador de vistas analíticas.
    """
    with obtenerSesion() as db:
        vistasDisponibles = db.query(VistaModelo).filter(VistaModelo.activo == True).order_by(VistaModelo.nombreVista).all()
        
        vistaSeleccionada = None
        columnasParquet = []
        cardinalidades = {}
        configuracionActual = None

        if idVista:
            vistaSeleccionada = db.query(VistaModelo).filter(VistaModelo.idVista == idVista).first()
        if vistaSeleccionada and vistaSeleccionada.rutaArchivoParquet and os.path.exists(vistaSeleccionada.rutaArchivoParquet):
            rutaSql = vistaSeleccionada.rutaArchivoParquet.replace("\\", "/")
            try:
                con = duckdb.connect()
                esquema = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{rutaSql}') LIMIT 1").fetchall()
                for c in esquema:
                    columnasParquet.append({
                        "nombre": c[0],
                        "tipo": str(c[1]).upper(),
                        "esNumerico": any(t in str(c[1]).upper() for t in ["INT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "BIGINT"]),
                        "esTemporal": any(t in str(c[1]).upper() for t in ["DATE", "TIME", "TIMESTAMP"])
                    })
                con.close()
            except Exception as e:
                print(f"Error inspeccionando Parquet: {e}")

            if vistaSeleccionada.configuracionJson:
                try:
                    configuracionActual = json.loads(vistaSeleccionada.configuracionJson)
                except Exception:
                    configuracionActual = None

    return plantillas.TemplateResponse(
        request=peticion,
        name="configuradorVista.html",
        context={
            "user": usuarioActual,
            "vistasDisponibles": vistasDisponibles,
            "vistaSeleccionada": vistaSeleccionada,
            "columnasParquet": columnasParquet,
            "configuracionActual": configuracionActual,
            "graficosCatalogo": SugeridorGraficos.TIPOS_GRAFICOS_DISPONIBLES,
            "ruta_activa": "configuracion_vistas"
        }
    )


@enrutador.post("/api/vistas/analizar-compatibilidad")
async def analizarCompatibilidad(
    datos: Dict[str, Any] = Body(...),
    usuarioActual=Depends(requerirPermisoPantalla("CONFIGURACION_VISTAS"))
):
    """
    Inspecciona en DuckDB la compatibilidad de visualizaciones según cardinalidad y tipo.
    """
    idVista = datos.get("idVista")
    dimensionPrincipal = datos.get("dimensionPrincipal")
    metricaPrincipal = datos.get("metricaPrincipal")
    dimensionesAdicionales = datos.get("dimensionesAdicionales", [])
    metricaSecundaria = datos.get("metricaSecundaria")

    with obtenerSesion() as db:
        vista = db.query(VistaModelo).filter(VistaModelo.idVista == idVista).first()
        if not vista:
            raise HTTPException(status_code=404, detail="Vista no encontrada")

        if not vista.rutaArchivoParquet or not os.path.exists(vista.rutaArchivoParquet):
            raise HTTPException(status_code=400, detail=f"Archivo Parquet no disponible en {vista.rutaArchivoParquet}")

        rutaParquet = vista.rutaArchivoParquet

    analisis = SugeridorGraficos.evaluarCompatibilidadGraficos(
        rutaParquet=rutaParquet,
        dimensionPrincipal=dimensionPrincipal,
        metricaPrincipal=metricaPrincipal,
        dimensionesAdicionales=dimensionesAdicionales,
        metricaSecundaria=metricaSecundaria
    )

    return JSONResponse(content={"exito": True, "analisis": analisis})


from sistemaAnalitica.modulos.seguridad.gestorLogs import GestorLogsSistema

@enrutador.post("/api/vistas/guardar-configuracion")
async def guardarConfiguracionVista(
    configuracion: ConfiguracionVistaEsquema = Body(...),
    usuarioActual=Depends(requerirPermisoPantalla("CONFIGURACION_VISTAS"))
):
    """
    Valida y almacena las reglas visuales y de gobernanza de la vista en JSON.
    """
    try:
        with obtenerSesion() as db:
            vista = db.query(VistaModelo).filter(VistaModelo.idVista == configuracion.idVista).first()
            if not vista:
                GestorLogsSistema.registrarError(
                    capa="CONFIGURACION_VISTAS",
                    metodo="guardarConfiguracionVista",
                    error=f"Vista con id {configuracion.idVista} no encontrada."
                )
                raise HTTPException(status_code=404, detail="Vista no encontrada")

            # Serializar esquema validado a JSON
            dictConfiguracion = configuracion.model_dump()
            vista.configuracionJson = json.dumps(dictConfiguracion, ensure_ascii=False)
            nombreVista = vista.nombreVista

        return JSONResponse(content={
            "exito": True,
            "mensaje": f"Configuración visual y gobernanza de '{nombreVista}' guardadas exitosamente."
        })
    except HTTPException:
        raise
    except Exception as ex:
        GestorLogsSistema.registrarError(
            capa="CONFIGURACION_VISTAS",
            metodo="guardarConfiguracionVista",
            error=f"Fallo al guardar configuración: {str(ex)}"
        )
        return JSONResponse(status_code=500, content={"exito": False, "error": f"Error interno: {str(ex)}"})

