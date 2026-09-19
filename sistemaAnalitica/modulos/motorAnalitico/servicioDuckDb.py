"""
Servicio del motor analítico OLAP embebido basado en DuckDB.
Ejecuta consultas analíticas de alto desempeño directamente contra archivos Apache Parquet.
"""

from typing import List, Dict, Any, Optional
import os
import json
import duckdb
import pandas as pd


class ServicioDuckDb:
    """
    Motor de consultas OLAP vectorizadas sobre archivos Parquet sin recarga completa en RAM.
    """

    @staticmethod
    def obtenerConexion() -> duckdb.DuckDBPyConnection:
        """
        Retorna una conexión en memoria a DuckDB configurada para analítica multihilo.
        """
        conexion = duckdb.connect(database=":memory:")
        conexion.execute("PRAGMA threads=4;")
        return conexion

    @classmethod
    def obtenerResumenCubo(cls, rutaArchivoParquet: str) -> Dict[str, Any]:
        """
        Inspecciona el archivo Parquet y calcula estadísticas descriptivas básicas y esquema.
        """
        if not os.path.exists(rutaArchivoParquet):
            raise FileNotFoundError(f"Archivo Parquet no encontrado: {rutaArchivoParquet}")

        # Normalizar barras para SQL de DuckDB en Windows
        rutaSql = rutaArchivoParquet.replace("\\", "/")

        with cls.obtenerConexion() as conexion:
            # 1. Total de registros
            totalFilas = conexion.execute(
                f"SELECT COUNT(*) FROM read_parquet('{rutaSql}')"
            ).fetchone()[0]

            # 2. Descripción de columnas y tipos de datos en DuckDB
            infoColumnas = conexion.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{rutaSql}')"
            ).fetchall()

            listaColumnas = [
                {
                    "nombreColumna": fila[0],
                    "tipoDato": fila[1],
                    "esNulo": fila[2]
                }
                for fila in infoColumnas
            ]

            # 3. Muestra de las primeras 5 filas
            muestra = conexion.execute(
                f"SELECT * FROM read_parquet('{rutaSql}') LIMIT 5"
            ).fetchdf()

            return {
                "rutaParquet": rutaArchivoParquet,
                "totalFilas": totalFilas,
                "columnas": listaColumnas,
                "muestraPrimerasFilas": json.loads(muestra.to_json(orient="records", date_format="iso"))
            }

    @classmethod
    def ejecutarConsultaOlap(
        cls,
        rutaArchivoParquet: str,
        dimensiones: Optional[List[str]] = None,
        metricasSumables: Optional[List[str]] = None,
        metricasPromedio: Optional[List[str]] = None,
        filtrosWhere: Optional[List[str]] = None,
        columnaOrden: Optional[str] = None,
        ordenAscendente: bool = False,
        limiteFilas: int = 1000
    ) -> pd.DataFrame:
        """
        Construye y ejecuta dinámicamente una consulta analítica de agregación multidimensional.
        """
        if not os.path.exists(rutaArchivoParquet):
            raise FileNotFoundError(f"Archivo Parquet no encontrado: {rutaArchivoParquet}")

        rutaSql = rutaArchivoParquet.replace("\\", "/")

        clausulaSelect = []
        clausulaGroupBy = []

        # Agregar dimensiones
        if dimensiones:
            for dim in dimensiones:
                clausulaSelect.append(f'"{dim}"')
                clausulaGroupBy.append(f'"{dim}"')

        # Agregar métricas sumables
        if metricasSumables:
            for met in metricasSumables:
                clausulaSelect.append(f'SUM(CAST("{met}" AS DOUBLE)) AS "{met}_Total"')

        # Agregar métricas no sumables / promedio
        if metricasPromedio:
            for met in metricasPromedio:
                clausulaSelect.append(f'AVG(CAST("{met}" AS DOUBLE)) AS "{met}_Promedio"')

        # Si no se pidieron dimensiones ni métricas, traer muestra plana
        if not clausulaSelect:
            clausulaSelect = ["*"]

        sql = f"SELECT {', '.join(clausulaSelect)} FROM read_parquet('{rutaSql}')"

        if filtrosWhere:
            sql += f" WHERE {' AND '.join(filtrosWhere)}"

        if clausulaGroupBy:
            sql += f" GROUP BY {', '.join(clausulaGroupBy)}"

        if columnaOrden:
            direccion = "ASC" if ordenAscendente else "DESC"
            sql += f' ORDER BY "{columnaOrden}" {direccion}'

        if limiteFilas > 0:
            sql += f" LIMIT {limiteFilas}"

        with cls.obtenerConexion() as conexion:
            return conexion.execute(sql).fetchdf()

    @classmethod
    def ejecutarSqlLibre(cls, consultaSql: str) -> pd.DataFrame:
        """
        Permite la ejecución directa de una consulta SQL en DuckDB.
        """
        with cls.obtenerConexion() as conexion:
            return conexion.execute(consultaSql).fetchdf()
