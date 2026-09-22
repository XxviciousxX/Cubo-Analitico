"""
Submódulo de Motor Analítico OLAP.
Maneja operaciones sobre DuckDB, compresión Parquet y generación de One Big Table (OBT).
"""

import os
import io
import json
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd

from sistemaAnalitica.modulos.motorAnalitico.servicioDuckDb import ServicioDuckDb
from sistemaAnalitica.modulos.motorAnalitico.servicioGestionCubos import ServicioGestionCubos
from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import (
    VistaModelo, FiltroSeguridadFilaModelo, ConfiguracionVistaEsquema, FiltroVistaEsquema
)


class ErrorSeguridadGobernanza(Exception):
    """
    Excepción lanzada cuando una consulta viola las reglas de grano máximo cerrado o lista blanca.
    """
    pass


class ServicioCapaSemantica:
    """
    Capa de abstracción analítica y gobernanza que garantiza la ejecución segura de agregaciones
    impidiendo el acceso a datos atómicos transaccionales o columnas fuera de la lista blanca.
    """

    @classmethod
    def _construirClausulaFiltro(cls, filtro: Any) -> Optional[str]:
        """
        Construye una expresión WHERE para DuckDB a partir de una regla de FiltroVistaEsquema.
        """
        if isinstance(filtro, dict):
            activo = filtro.get("activo", True)
            col = str(filtro.get("columna", "")).replace('"', '').strip()
            op = str(filtro.get("operador", "=")).strip().upper()
            val = filtro.get("valor")
        else:
            activo = getattr(filtro, "activo", True)
            col = str(getattr(filtro, "columna", "")).replace('"', '').strip()
            op = str(getattr(filtro, "operador", "=")).strip().upper()
            val = getattr(filtro, "valor", None)

        if not activo or not col:
            return None

        if op in ["IS NULL", "IS NOT NULL"]:
            return f'"{col}" {op}'

        if op in ["IN", "NOT IN"]:
            if isinstance(val, str):
                items = [x.strip() for x in val.split(",") if x.strip()]
            elif isinstance(val, list):
                items = [str(x).strip() for x in val if str(x).strip()]
            else:
                items = [str(val).strip()] if val is not None else []
            if not items:
                return None
            escaped = ", ".join([f"'{x.replace(chr(39), chr(39)+chr(39))}'" for x in items])
            return f'"{col}" {op} ({escaped})'

        if op in ["LIKE", "NOT LIKE"]:
            val_str = str(val or "").replace("'", "''")
            if not val_str.startswith("%") and not val_str.endswith("%"):
                val_str = f"%{val_str}%"
            return f'"{col}" {op} \'{val_str}\''

        # Operadores estándar: =, !=, <>, >, <, >=, <=
        if val is None:
            return None
        val_str = str(val).replace("'", "''")
        return f'"{col}" {op} \'{val_str}\''

    @classmethod
    def obtenerConfiguracionVista(cls, codigoVista: str) -> Optional[ConfiguracionVistaEsquema]:
        """
        Recupera y deserializa el contrato de configuración de una vista analítica.
        """
        with obtenerSesion() as sesion:
            vista = sesion.query(VistaModelo).filter_by(codigoVista=codigoVista, activo=True).first()
            if not vista or not vista.configuracionJson:
                return None

            try:
                datosJson = json.loads(vista.configuracionJson)
                return ConfiguracionVistaEsquema(**datosJson)
            except Exception:
                return None

    @classmethod
    def validarYEjecutarConsultaSegura(
        cls,
        codigoVista: str,
        dimensionSolicitada: Optional[str],
        metricaSolicitada: Optional[str],
        dimensionSecundaria: Optional[str] = None,
        filtrosWhere: Optional[List[str]] = None,
        idUsuario: Optional[int] = None,
        columnaOrden: Optional[str] = None,
        ordenAscendente: bool = False,
        limiteFilas: int = 500
    ) -> Dict[str, Any]:
        """
        Valida que las dimensiones y métricas pertenezcan a la lista blanca del grano permitido
        e inyecta Row-Level Security (RLS) antes de ejecutar el SQL en DuckDB.
        """
        with obtenerSesion() as sesion:
            vista = sesion.query(VistaModelo).filter_by(codigoVista=codigoVista, activo=True).first()
            if not vista:
                raise FileNotFoundError(f"Vista '{codigoVista}' no encontrada en el sistema.")

            from .servicioPersistenciaCubos import ServicioPersistenciaCubos
            rutaParquet = ServicioPersistenciaCubos.asegurarParquetVista(vista, sesion) or vista.rutaArchivoParquet
            if not rutaParquet or not os.path.exists(rutaParquet):
                raise FileNotFoundError(f"Archivo Parquet o vista '{codigoVista}' no disponible.")

            # Verificación del ciclo de vida de la vista y del cubo subyacente
            if not vista.estadoHabilitado:
                raise ErrorSeguridadGobernanza(f"La vista analítica '{vista.nombreVista}' se encuentra deshabilitada.")

            if vista.cubo and not vista.cubo.estadoHabilitado:
                raise ErrorSeguridadGobernanza("El cubo subyacente se encuentra inactivo")

            # Obtener configuración si existe
            configuracion = None
            if vista.configuracionJson:
                try:
                    configuracion = ConfiguracionVistaEsquema(**json.loads(vista.configuracionJson))
                except Exception:
                    configuracion = None

            # 1. Validación de Lista Blanca (Whitelist) de Grano si la vista está configurada
            if configuracion:
                grano = configuracion.granoPermitido
                gobernanza = configuracion.politicaGobernanza

                # Validar dimensión principal
                if dimensionSolicitada:
                    if dimensionSolicitada not in grano.dimensionesVisibles:
                        raise ErrorSeguridadGobernanza(
                            f"Acceso denegado: La dimensión '{dimensionSolicitada}' no está autorizada en la capa semántica de la vista."
                        )

                # Validar dimensión secundaria
                if dimensionSecundaria:
                    if dimensionSecundaria not in grano.dimensionesVisibles:
                        raise ErrorSeguridadGobernanza(
                            f"Acceso denegado: La dimensión secundaria '{dimensionSecundaria}' no está autorizada en la capa semántica de la vista."
                        )

                # Validar métrica
                columnasMetricasAutorizadas = [m.columna for m in grano.metricas]
                if metricaSolicitada:
                    if metricaSolicitada not in columnasMetricasAutorizadas:
                        raise ErrorSeguridadGobernanza(
                            f"Acceso denegado: La métrica '{metricaSolicitada}' no pertenece al grano permitido de la vista."
                        )

                # Validar columnas excluidas
                columnasAValidar = [c for c in [dimensionSolicitada, dimensionSecundaria, metricaSolicitada] if c]
                for col in columnasAValidar:
                    if col in gobernanza.columnasExcluidas:
                        raise ErrorSeguridadGobernanza(
                            f"Acceso restringido: Se intentó acceder a una columna clasificada como confidencial o excluida: {col}"
                        )

            # 2. Inyección de Filtros de Negocio del Cubo preconfigurados en la Vista
            filtrosCompuestos = list(filtrosWhere) if filtrosWhere else []
            if configuracion and getattr(configuracion, "filtrosCubo", None):
                for f in configuracion.filtrosCubo:
                    clausula = cls._construirClausulaFiltro(f)
                    if clausula:
                        filtrosCompuestos.append(clausula)

            # 3. Inyección de Row-Level Security (RLS)
            if idUsuario:
                reglasRls = sesion.query(FiltroSeguridadFilaModelo).filter_by(
                    idUsuario=idUsuario,
                    idVista=vista.idVista,
                    activo=True
                ).all()

                for regla in reglasRls:
                    col = regla.columnaFiltro
                    op = regla.operadorFiltro
                    val = regla.valorFiltro.replace("'", "''")
                    filtrosCompuestos.append(f'"{col}" {op} \'{val}\'')

        # 3. Determinar operación de agregación (por defecto SUM)
        operacionMetrica = "SUM"
        if configuracion and metricaSolicitada:
            for m in configuracion.granoPermitido.metricas:
                if m.columna == metricaSolicitada:
                    operacionMetrica = m.operacion.upper()
                    break

        # 4. Construcción de consulta SQL vectorizada en DuckDB
        dimensionesAgrupadas = []
        if dimensionSolicitada:
            dimensionesAgrupadas.append(dimensionSolicitada)
        if dimensionSecundaria and dimensionSecundaria != dimensionSolicitada:
            dimensionesAgrupadas.append(dimensionSecundaria)

        metricasSum = [metricaSolicitada] if operacionMetrica == "SUM" and metricaSolicitada else None
        metricasAvg = [metricaSolicitada] if operacionMetrica == "AVG" and metricaSolicitada else None

        # Si hay dimensión secundaria, ordenar por dimensión principal por defecto
        ordenPorDefecto = None
        if dimensionSecundaria and dimensionSolicitada:
            ordenPorDefecto = dimensionSolicitada
        elif metricasSum:
            ordenPorDefecto = f"{metricaSolicitada}_Total"
        elif metricasAvg:
            ordenPorDefecto = f"{metricaSolicitada}_Promedio"

        dfResultado = ServicioDuckDb.ejecutarConsultaOlap(
            rutaArchivoParquet=rutaParquet,
            dimensiones=dimensionesAgrupadas if dimensionesAgrupadas else None,
            metricasSumables=metricasSum,
            metricasPromedio=metricasAvg,
            filtrosWhere=filtrosCompuestos if filtrosCompuestos else None,
            columnaOrden=columnaOrden or ordenPorDefecto,
            ordenAscendente=ordenAscendente if columnaOrden else (True if dimensionSecundaria else False),
            limiteFilas=limiteFilas
        )

        # 5. Cálculo de KPIs agregados globales
        dfKpis = ServicioDuckDb.ejecutarConsultaOlap(
            rutaArchivoParquet=rutaParquet,
            metricasSumables=[metricaSolicitada] if metricaSolicitada else None,
            metricasPromedio=[metricaSolicitada] if metricaSolicitada else None,
            filtrosWhere=filtrosCompuestos if filtrosCompuestos else None
        )

        kpis = {"totalFilas": len(dfResultado), "suma": 0.0, "promedio": 0.0}
        if not dfKpis.empty and metricaSolicitada:
            colTotal = f"{metricaSolicitada}_Total"
            colProm = f"{metricaSolicitada}_Promedio"
            if colTotal in dfKpis.columns and dfKpis[colTotal].iloc[0] is not None:
                kpis["suma"] = float(dfKpis[colTotal].iloc[0] or 0.0)
            if colProm in dfKpis.columns and dfKpis[colProm].iloc[0] is not None:
                kpis["promedio"] = float(dfKpis[colProm].iloc[0] or 0.0)

        return {
            "exito": True,
            "filas": json.loads(dfResultado.to_json(orient="records", date_format="iso")),
            "kpis": kpis,
            "columnas": list(dfResultado.columns)
        }

    @classmethod
    def generarCsvResumenBlindado(
        cls,
        codigoVista: str,
        filtrosWhere: Optional[List[str]] = None,
        idUsuario: Optional[int] = None
    ) -> str:
        """
        Genera el CSV aplicando obligatoriamente el GROUP BY del grano permitido
        garantizando que ninguna fila transaccional atómica ni columna excluida sea expuesta.
        """
        from .servicioExportacionOlap import ServicioExportacionOlap
        contenidoCsv, _, _ = ServicioExportacionOlap.generarCsvBlindado(codigoVista=codigoVista, idUsuario=idUsuario)
        return contenidoCsv

    @classmethod
    def generarExcelResumenBlindado(
        cls,
        codigoVista: str,
        idUsuario: Optional[int] = None
    ) -> Tuple[str, str, int]:
        """
        Genera el Excel (.xlsx) particionado a 700k filas por hoja con autofiltro y tipos coherentes.
        """
        from .servicioExportacionOlap import ServicioExportacionOlap
        return ServicioExportacionOlap.generarExcelBlindado(codigoVista=codigoVista, idUsuario=idUsuario)

