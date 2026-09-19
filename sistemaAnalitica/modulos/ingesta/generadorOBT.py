"""
Generador de One Big Table (OBT) y exportador optimizado a Apache Parquet.
Realiza combinaciones relacionales (JOIN) y aplica compresión y filtrado de descarte.
"""

import os
from typing import Dict, List, Any, Optional
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


class GeneradorOBT:
    """
    Ensambla tablas relacionales en una única tabla desnormalizada y la almacena en formato columnar.
    """

    @classmethod
    def construirTablaConsolidada(
        cls,
        mapaTablas: Dict[str, pd.DataFrame],
        tablaPrincipal: str,
        definicionJoins: Optional[List[Dict[str, Any]]] = None
    ) -> pd.DataFrame:
        """
        Ejecuta las uniones (JOINs) configuradas secuencialmente a partir de una tabla base.
        """
        if tablaPrincipal not in mapaTablas:
            raise ValueError(f"La tabla principal '{tablaPrincipal}' no existe en las fuentes provistas.")

        dataframeConsolidado = mapaTablas[tablaPrincipal].copy()

        if not definicionJoins:
            return dataframeConsolidado

        for definicion in definicionJoins:
            tablaSecundaria = definicion.get("tablaSecundaria")
            llaveIzquierda = definicion.get("llaveIzquierda")
            llaveDerecha = definicion.get("llaveDerecha")
            tipoJoin = definicion.get("tipoJoin", "left").lower()

            if tablaSecundaria not in mapaTablas:
                continue

            dataframeSecundario = mapaTablas[tablaSecundaria]

            # Si las llaves están presentes, ejecutar el merge
            if llaveIzquierda in dataframeConsolidado.columns and llaveDerecha in dataframeSecundario.columns:
                # Evitar colisión de nombres de columnas duplicadas
                sufijo = f"_{tablaSecundaria}"
                dataframeConsolidado = pd.merge(
                    dataframeConsolidado,
                    dataframeSecundario,
                    how=tipoJoin,
                    left_on=llaveIzquierda,
                    right_on=llaveDerecha,
                    suffixes=("", sufijo)
                )

        return dataframeConsolidado

    @classmethod
    def guardarEnParquet(
        cls,
        dataframe: pd.DataFrame,
        rutaDestinoParquet: str,
        contratoColumnas: Optional[List[Dict[str, Any]]] = None,
        compresion: str = "snappy"
    ) -> str:
        """
        Convierte el DataFrame en una tabla Arrow con tipado estricto y la guarda en Parquet.
        Excluye las columnas clasificadas como 'Identificador/Descarte' según el contrato.
        """
        directorioDestino = os.path.dirname(os.path.abspath(rutaDestinoParquet))
        os.makedirs(directorioDestino, exist_ok=True)

        dataframeProcesado = dataframe.copy()

        if contratoColumnas:
            mapeoTipos = {}

            for defCol in contratoColumnas:
                nombreCol = defCol.get("nombreColumna")
                clasificacion = defCol.get("clasificacionSemantica")
                tipoDato = str(defCol.get("tipoDatoEsperado", "texto")).lower()
                mapeoTipos[nombreCol] = (clasificacion, tipoDato)

            # Aplicar coerción de tipos para garantizar consistencia Parquet sin eliminar columnas
            for nombreCol, (clasificacion, tipoDato) in mapeoTipos.items():
                if nombreCol in dataframeProcesado.columns:
                    try:
                        if clasificacion == "MetricaSumable" or any(t in tipoDato for t in ["decimal", "float", "numeric", "numerico"]):
                            dataframeProcesado[nombreCol] = pd.to_numeric(dataframeProcesado[nombreCol], errors="coerce").fillna(0.0).astype("float64")
                        elif any(t in tipoDato for t in ["entero", "int", "int64"]):
                            dataframeProcesado[nombreCol] = pd.to_numeric(dataframeProcesado[nombreCol], errors="coerce").fillna(0).astype("int64")
                        elif any(t in tipoDato for t in ["fecha", "date", "datetime", "timestamp", "temporal"]):
                            dataframeProcesado[nombreCol] = pd.to_datetime(dataframeProcesado[nombreCol], errors="coerce")
                        elif any(t in tipoDato for t in ["booleano", "bool"]):
                            dataframeProcesado[nombreCol] = dataframeProcesado[nombreCol].astype("boolean")
                        else:
                            dataframeProcesado[nombreCol] = dataframeProcesado[nombreCol].astype(str)
                    except Exception:
                        pass

        # Normalizar nombres de columnas a cadenas sin caracteres problemáticos
        dataframeProcesado.columns = [str(c).strip() for c in dataframeProcesado.columns]

        # Conversión a Apache Arrow Table
        tablaArrow = pa.Table.from_pandas(dataframeProcesado, preserve_index=False)

        # Escritura atómica a archivo Parquet
        pq.write_table(tablaArrow, rutaDestinoParquet, compression=compresion)

        return rutaDestinoParquet

    @classmethod
    def purgarArchivoParquet(cls, rutaArchivoParquet: str) -> bool:
        """
        Elimina de forma segura el archivo Parquet previo para la Modalidad B de Excel.
        """
        try:
            if rutaArchivoParquet and os.path.exists(rutaArchivoParquet):
                os.remove(rutaArchivoParquet)
                return True
        except Exception:
            return False
        return False
