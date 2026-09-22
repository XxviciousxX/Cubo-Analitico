# -*- coding: utf-8 -*-
"""
Servicio especializado para la exportación analítica masiva (CSV y Excel)
de datos puros agregados según el contrato semántico y grano permitido de la vista.
"""

import os
import re
import io
import json
import math
import tempfile
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple

import duckdb
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.cell import WriteOnlyCell

from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import (
    VistaModelo, ConfiguracionVistaEsquema, FiltroSeguridadFilaModelo
)


class ErrorLimiteExportacion(Exception):
    """Excepción lanzada cuando el volumen de filas a exportar excede el umbral permitido."""
    pass


class ServicioExportacionOlap:
    """
    Gestiona la extracción vectorizada y generación de reportes en streaming
    para grandes volúmenes de datos con particionamiento y políticas de grano cerrado.
    """

    LIMITE_MAXIMO_FILAS = 3_000_000  # 3 millones de filas
    FILAS_POR_HOJA_EXCEL = 700_000   # 700k filas por hoja de cálculo

    @classmethod
    def sanitizarNombreArchivo(cls, nombre: str) -> str:
        """
        Limpia un nombre para que sea seguro como archivo del sistema operativo.
        """
        nombreLimpio = re.sub(r'[\\/*?:"<>| ]+', '_', str(nombre).strip())
        nombreLimpio = re.sub(r'_+', '_', nombreLimpio).strip('_')
        return nombreLimpio or "exportacion"

    @classmethod
    def construirConsultaSqlVista(
        cls,
        vista: VistaModelo,
        idUsuario: Optional[int] = None
    ) -> Tuple[str, str, List[str], List[Dict[str, str]]]:
        """
        Construye la consulta SQL DuckDB sobre el grano permitido de la vista:
        Retorna (sqlConteo, sqlDatos, listaDimensiones, listaMetricasInfo).
        """
        from sistemaAnalitica.modulos.motorAnalitico.servicioPersistenciaCubos import ServicioPersistenciaCubos
        rutaParquet = ServicioPersistenciaCubos.asegurarParquetVista(vista) or vista.rutaArchivoParquet
        if not rutaParquet or not os.path.exists(rutaParquet):
            raise FileNotFoundError(f"El archivo Parquet de la vista '{vista.codigoVista}' no existe.")

        rutaSql = rutaParquet.replace("\\", "/")

        configuracion = None
        if vista.configuracionJson:
            try:
                configuracion = ConfiguracionVistaEsquema(**json.loads(vista.configuracionJson))
            except Exception:
                configuracion = None

        dimensiones: List[str] = []
        metricasInfo: List[Dict[str, str]] = []

        if configuracion and configuracion.granoPermitido:
            dimensiones = list(configuracion.granoPermitido.dimensionesVisibles)
            for m in configuracion.granoPermitido.metricas:
                metricasInfo.append({
                    "columna": m.columna,
                    "operacion": (m.operacion or "SUM").upper(),
                    "alias": m.alias or f"{m.columna}_{m.operacion or 'SUM'}"
                })

        # Fallback en caso de no tener grano configurado
        if not dimensiones and not metricasInfo:
            con = duckdb.connect()
            esquema = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{rutaSql}') LIMIT 1").fetchall()
            con.close()
            for c in esquema:
                nom = c[0]
                t = str(c[1]).upper()
                if any(num in t for num in ["INT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT"]):
                    metricasInfo.append({"columna": nom, "operacion": "SUM", "alias": nom})
                else:
                    dimensiones.append(nom)

        # Construcción de cláusulas de filtros (Filtros de Negocio + RLS)
        filtrosCompuestos: List[str] = []

        # 1. Filtros de negocio de la vista (filtrosCubo)
        if configuracion and getattr(configuracion, "filtrosCubo", None):
            for f in configuracion.filtrosCubo:
                if not getattr(f, "activo", True):
                    continue
                col = str(f.columna).replace('"', '""')
                op = str(f.operador).upper().strip()
                val = str(f.valor or "").strip()
                tipo = str(getattr(f, "tipoDato", "VARCHAR")).upper()
                esNumero = any(t in tipo for t in ["INT", "DECIMAL", "NUMERIC", "FLOAT"])

                if op in ("IS NULL", "IS NOT NULL"):
                    filtrosCompuestos.append(f'"{col}" {op}')
                elif op in ("IN", "NOT IN"):
                    elementos = [e.strip() for e in val.split(",") if e.strip()]
                    if elementos:
                        if esNumero:
                            nums = [str(float(e)) if "." in e else str(int(e)) for e in elementos if e.replace(".", "", 1).isdigit()]
                            if nums:
                                filtrosCompuestos.append(f'"{col}" {op} ({", ".join(nums)})')
                        else:
                            strs = [f"'{e.replace(chr(39), chr(39)+chr(39))}'" for e in elementos]
                            filtrosCompuestos.append(f'"{col}" {op} ({", ".join(strs)})')
                elif op in ("LIKE", "NOT LIKE"):
                    valSql = val.replace("'", "''")
                    filtrosCompuestos.append(f'CAST("{col}" AS VARCHAR) {op} \'{valSql}\'')
                elif op in ("=", "!=", ">", "<", ">=", "<="):
                    if esNumero:
                        try:
                            valNum = float(val) if "." in val else int(val)
                            filtrosCompuestos.append(f'"{col}" {op} {valNum}')
                        except ValueError:
                            filtrosCompuestos.append(f'"{col}" {op} \'{val.replace(chr(39), chr(39)+chr(39))}\'')
                    else:
                        filtrosCompuestos.append(f'"{col}" {op} \'{val.replace(chr(39), chr(39)+chr(39))}\'')

        # 2. Inyección de RLS por usuario
        if idUsuario:
            with obtenerSesion() as sesionDb:
                reglasRls = sesionDb.query(FiltroSeguridadFilaModelo).filter_by(
                    idUsuario=idUsuario,
                    idVista=vista.idVista,
                    activo=True
                ).all()
                for regla in reglasRls:
                    col = regla.columnaFiltro.replace('"', '""')
                    op = regla.operadorFiltro.strip()
                    val = regla.valorFiltro.replace("'", "''")
                    filtrosCompuestos.append(f'"{col}" {op} \'{val}\'')

        clausulaWhere = f"WHERE {' AND '.join(filtrosCompuestos)}" if filtrosCompuestos else ""

        # Construcción de proyecciones
        proyecciones: List[str] = []
        for dim in dimensiones:
            dimEsc = dim.replace('"', '""')
            proyecciones.append(f'"{dimEsc}"')

        for met in metricasInfo:
            colEsc = met["columna"].replace('"', '""')
            aliasEsc = met["alias"].replace('"', '""')
            op = met["operacion"]
            proyecciones.append(f'{op}("{colEsc}") AS "{aliasEsc}"')

        if not proyecciones:
            proyecciones = ["*"]

        cadenaSelect = ", ".join(proyecciones)
        
        # Agrupamiento obligatorio por dimensiones de grano
        if dimensiones and metricasInfo:
            dimsGroupBy = ", ".join([f'"{d.replace(chr(34), chr(34)+chr(34))}"' for d in dimensiones])
            clausulaGroupBy = f"GROUP BY {dimsGroupBy}"
            clausulaOrderBy = f"ORDER BY {dimsGroupBy}"
        elif dimensiones and not metricasInfo:
            dimsGroupBy = ", ".join([f'"{d.replace(chr(34), chr(34)+chr(34))}"' for d in dimensiones])
            clausulaGroupBy = f"GROUP BY {dimsGroupBy}"
            clausulaOrderBy = f"ORDER BY {dimsGroupBy}"
        else:
            clausulaGroupBy = ""
            clausulaOrderBy = ""

        sqlBase = f"""
            SELECT {cadenaSelect}
            FROM read_parquet('{rutaSql}')
            {clausulaWhere}
            {clausulaGroupBy}
        """

        sqlConteo = f"SELECT COUNT(*) FROM ({sqlBase}) AS subconsulta_conteo"
        sqlDatos = f"{sqlBase} {clausulaOrderBy}"

        return sqlConteo, sqlDatos, dimensiones, metricasInfo

    @classmethod
    def verificarVolumenExportacion(
        cls,
        codigoVista: str,
        idUsuario: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Calcula previamente el total de filas que generará la vista pura
        y verifica si cumple con el límite de 3 millones de filas.
        """
        with obtenerSesion() as sesion:
            vista = sesion.query(VistaModelo).filter_by(codigoVista=codigoVista, activo=True).first()
            if not vista:
                return {
                    "exito": False,
                    "error": f"La vista analítica '{codigoVista}' no fue encontrada o está inactiva."
                }

            try:
                sqlConteo, _, dimensiones, metricasInfo = cls.construirConsultaSqlVista(vista, idUsuario)
            except Exception as e:
                return {"exito": False, "error": str(e)}

        try:
            con = duckdb.connect()
            totalFilas = con.execute(sqlConteo).fetchone()[0]
            con.close()
        except Exception as e:
            return {"exito": False, "error": f"Error al calcular conteo DuckDB: {str(e)}"}

        permiteDescarga = totalFilas <= cls.LIMITE_MAXIMO_FILAS
        particionesRequeridas = max(1, math.ceil(totalFilas / cls.FILAS_POR_HOJA_EXCEL)) if totalFilas > 0 else 1

        mensaje = None
        if not permiteDescarga:
            mensaje = (
                f"No se puede descargar la información del cubo. El resultado contiene "
                f"{totalFilas:,} filas, superando el límite máximo permitido de {cls.LIMITE_MAXIMO_FILAS:,} filas. "
                f"Por favor añade filtros a la vista para reducir el tamaño del reporte."
            )

        fechaActual = datetime.now().strftime("%d%m%Y")
        nombreBase = cls.sanitizarNombreArchivo(vista.nombreVista)
        nombreArchivoExcel = f"{nombreBase}_{fechaActual}.xlsx"
        nombreArchivoCsv = f"{nombreBase}_{fechaActual}.csv"

        return {
            "exito": True,
            "totalFilas": totalFilas,
            "permiteDescarga": permiteDescarga,
            "limiteMaximo": cls.LIMITE_MAXIMO_FILAS,
            "particionesRequeridas": particionesRequeridas,
            "dimensiones": dimensiones,
            "metricas": [m["alias"] for m in metricasInfo],
            "nombreArchivoExcel": nombreArchivoExcel,
            "nombreArchivoCsv": nombreArchivoCsv,
            "error": mensaje
        }

    @classmethod
    def generarExcelBlindado(
        cls,
        codigoVista: str,
        idUsuario: Optional[int] = None,
        tamanoLote: int = 50_000
    ) -> Tuple[str, str, int]:
        """
        Genera un archivo Excel (.xlsx) en modo streaming write-only:
        - Particionado en hojas de 700,000 filas ('Parte 1', 'Parte 2'...)
        - Fila 1: Título de la vista
        - Fila 2: Encabezados de columnas con AutoFilter activo
        - Filas 3+: Datos tipados estrictamente (numérico, fecha, booleano, texto)
        - Límite máximo: 3,000,000 de filas
        Retorna (rutaArchivoTemporal, nombreDescarga, totalFilasExportadas).
        """
        with obtenerSesion() as sesion:
            vista = sesion.query(VistaModelo).filter_by(codigoVista=codigoVista, activo=True).first()
            if not vista:
                raise ValueError(f"Vista '{codigoVista}' no encontrada.")

            sqlConteo, sqlDatos, dimensiones, metricasInfo = cls.construirConsultaSqlVista(vista, idUsuario)
            nombreVista = vista.nombreVista

        con = duckdb.connect()
        totalFilas = con.execute(sqlConteo).fetchone()[0]

        if totalFilas > cls.LIMITE_MAXIMO_FILAS:
            con.close()
            raise ErrorLimiteExportacion(
                f"No se puede descargar la información del cubo. El resultado contiene {totalFilas:,} filas, "
                f"superando el límite máximo permitido de {cls.LIMITE_MAXIMO_FILAS:,} filas."
            )

        # Crear archivo temporal en disco para no saturar memoria RAM
        tempFile = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        rutaTemp = tempFile.name
        tempFile.close()

        wb = openpyxl.Workbook(write_only=True)

        cursor = con.cursor()
        cursor.execute(sqlDatos)
        nombresColumnas = [desc[0] for desc in cursor.description]
        numColumnas = len(nombresColumnas)

        # Muestrear el primer lote para determinar anchos óptimos de columnas
        primerLote = cursor.fetchmany(tamanoLote) if totalFilas > 0 else []

        anchosColumnas: Dict[int, float] = {}
        for idx, nomCol in enumerate(nombresColumnas):
            lenCabecera = len(str(nomCol))
            maxLenDato = 0
            if primerLote:
                for fila in primerLote:
                    val = fila[idx]
                    if val is not None:
                        valLen = len(str(val))
                        if valLen > maxLenDato:
                            maxLenDato = valLen
            anchoOptimo = max(lenCabecera + 5, maxLenDato + 4, 14)
            anchosColumnas[idx] = float(min(anchoOptimo, 60))

        # Estilos corporativos predefinidos
        fillBanner = PatternFill(start_color='004482', end_color='004482', fill_type='solid')
        fontTitulo = Font(name='Segoe UI', size=16, bold=True, color='FFFFFF')
        alignTitulo = Alignment(horizontal='left', vertical='center', indent=1)

        fontEncabezado = Font(name='Segoe UI', size=11, bold=True, color='002D57')
        fillEncabezado = PatternFill(start_color='E8F0FE', end_color='E8F0FE', fill_type='solid')
        alignEncabezado = Alignment(horizontal='center', vertical='center', wrap_text=True)

        filaActualHoja = 0
        numeroParte = 1
        hojaActual = None

        def crearNuevaHoja(parteNum: int):
            ws = wb.create_sheet(title=f"Parte {parteNum}")
            # Alturas de fila (deben configurarse antes de escribir las celdas en write_only)
            ws.row_dimensions[1].height = 40
            ws.row_dimensions[2].height = 26

            # Ancho de columnas según longitud del nombre del dato y valores
            for idxCol in range(1, numColumnas + 1):
                letra = get_column_letter(idxCol)
                ws.column_dimensions[letra].width = anchosColumnas.get(idxCol - 1, 15.0)

            # Fila 1: Título vistoso y estilizado de la vista en franja azul corporativa
            cTitulo = WriteOnlyCell(ws, value=str(nombreVista).upper())
            cTitulo.font = fontTitulo
            cTitulo.fill = fillBanner
            cTitulo.alignment = alignTitulo

            fila1 = [cTitulo]
            for _ in range(max(0, numColumnas - 1)):
                cVacia = WriteOnlyCell(ws, value="")
                cVacia.fill = fillBanner
                fila1.append(cVacia)
            ws.append(fila1)

            # Fila 2: Encabezados de columnas estilizados
            fila2 = []
            for nomCol in nombresColumnas:
                cEnc = WriteOnlyCell(ws, value=str(nomCol))
                cEnc.font = fontEncabezado
                cEnc.fill = fillEncabezado
                cEnc.alignment = alignEncabezado
                fila2.append(cEnc)
            ws.append(fila2)

            return ws

        if totalFilas == 0:
            hojaActual = crearNuevaHoja(1)
            letraFin = get_column_letter(max(1, numColumnas))
            hojaActual.auto_filter.ref = f"A2:{letraFin}2"
        else:
            # Iterador que une el primerLote con los lotes subsiguientes
            def generadorFilas():
                for f in primerLote:
                    yield f
                while True:
                    subLote = cursor.fetchmany(tamanoLote)
                    if not subLote:
                        break
                    for f in subLote:
                        yield f

            for fila in generadorFilas():
                if hojaActual is None or filaActualHoja >= cls.FILAS_POR_HOJA_EXCEL:
                    if hojaActual is not None:
                        # Activar filtro en la hoja que acaba de terminar
                        filaFin = filaActualHoja + 2
                        letraFin = get_column_letter(numColumnas)
                        hojaActual.auto_filter.ref = f"A2:{letraFin}{filaFin}"
                        numeroParte += 1

                    hojaActual = crearNuevaHoja(numeroParte)
                    filaActualHoja = 0

                # Convertir valores a tipos nativos de Excel
                filaFormateada = []
                for val in fila:
                    if val is None:
                        filaFormateada.append("")
                    elif isinstance(val, (int, float, bool)):
                        filaFormateada.append(val)
                    elif isinstance(val, (datetime, date)):
                        filaFormateada.append(val.isoformat() if hasattr(val, 'isoformat') else str(val))
                    else:
                        filaFormateada.append(str(val))

                hojaActual.append(filaFormateada)
                filaActualHoja += 1

            # Activar filtro en la última hoja
            if hojaActual is not None:
                filaFin = max(2, filaActualHoja + 2)
                letraFin = get_column_letter(numColumnas)
                hojaActual.auto_filter.ref = f"A2:{letraFin}{filaFin}"

        cursor.close()
        con.close()

        # Guardar en streaming al archivo temporal
        wb.save(rutaTemp)

        fechaActual = datetime.now().strftime("%d%m%Y")
        nombreLimpio = cls.sanitizarNombreArchivo(nombreVista)
        nombreDescarga = f"{nombreLimpio}_{fechaActual}.xlsx"

        return rutaTemp, nombreDescarga, totalFilas

    @classmethod
    def generarCsvBlindado(
        cls,
        codigoVista: str,
        idUsuario: Optional[int] = None
    ) -> Tuple[str, str, int]:
        """
        Genera un archivo CSV con codificación UTF-8 con BOM (\ufeff)
        para apertura nativa impecable en Excel sin problemas de tildes o caracteres latinos.
        Retorna (contenidoCsvString, nombreDescarga, totalFilas).
        """
        with obtenerSesion() as sesion:
            vista = sesion.query(VistaModelo).filter_by(codigoVista=codigoVista, activo=True).first()
            if not vista:
                raise ValueError(f"Vista '{codigoVista}' no encontrada.")

            sqlConteo, sqlDatos, _, _ = cls.construirConsultaSqlVista(vista, idUsuario)
            nombreVista = vista.nombreVista

        con = duckdb.connect()
        totalFilas = con.execute(sqlConteo).fetchone()[0]

        if totalFilas > cls.LIMITE_MAXIMO_FILAS:
            con.close()
            raise ErrorLimiteExportacion(
                f"No se puede descargar la información del cubo. El resultado contiene {totalFilas:,} filas, "
                f"superando el límite máximo permitido de {cls.LIMITE_MAXIMO_FILAS:,} filas."
            )

        df = con.execute(sqlDatos).df()
        con.close()

        buffer = io.StringIO()
        # Inyectar BOM para compatibilidad inmediata con Excel en Windows
        buffer.write("\ufeff")
        df.to_csv(buffer, index=False, encoding="utf-8")
        contenidoCsv = buffer.getvalue()

        fechaActual = datetime.now().strftime("%d%m%Y")
        nombreLimpio = cls.sanitizarNombreArchivo(nombreVista)
        nombreDescarga = f"{nombreLimpio}_{fechaActual}.csv"

        return contenidoCsv, nombreDescarga, totalFilas
