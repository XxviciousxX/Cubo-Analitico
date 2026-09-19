"""
Esquemas Pydantic para el Submódulo de Ingesta, Cubo Compuesto y Muestreo de Data Lake.
"""

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field


class ColumnaMapeada(BaseModel):
    """
    Definición de una columna en el cubo compuesto, con su origen, alias y clasificación.
    """
    nombreOriginal: str
    origen: Literal["A", "B"]
    nombreFinal: str
    clasificacionSemantica: Literal[
        "Categorica/Dimension", "MetricaSumable", "MetricaNoSumable", "Identificador/Descarte"
    ] = "Categorica/Dimension"
    esObligatoria: bool = True


class CondicionJoin(BaseModel):
    """
    Par de columnas utilizadas para realizar el cruce relacional (JOIN) entre dos orígenes.
    """
    claveOrigenA: str
    claveOrigenB: str


class SolicitudInspeccionClaves(BaseModel):
    """
    Datos requeridos para evaluar compatibilidad y riesgo de fan-out entre claves de unión.
    """
    rutaOrigenA: str
    rutaOrigenB: str
    claveOrigenA: Optional[str] = None
    claveOrigenB: Optional[str] = None
    condiciones: Optional[List[CondicionJoin]] = None

    def obtenerCondiciones(self) -> List[CondicionJoin]:
        if self.condiciones and len(self.condiciones) > 0:
            return self.condiciones
        if self.claveOrigenA and self.claveOrigenB:
            return [CondicionJoin(claveOrigenA=self.claveOrigenA, claveOrigenB=self.claveOrigenB)]
        return []


class SolicitudCuboCompuesto(BaseModel):
    """
    Contrato completo para la generación física de un Cubo Compuesto vía DuckDB.
    """
    codigoNuevoCubo: str
    nombreNuevoCubo: str
    rutaOrigenA: str
    rutaOrigenB: str
    claveOrigenA: Optional[str] = None
    claveOrigenB: Optional[str] = None
    condiciones: Optional[List[CondicionJoin]] = None
    tipoJoin: Literal["LEFT", "INNER", "FULL"] = "LEFT"
    columnas: List[ColumnaMapeada]
    rolPorDefectoId: Optional[str] = "TODOS"
    descripcion: Optional[str] = None

    def obtenerCondiciones(self) -> List[CondicionJoin]:
        if self.condiciones and len(self.condiciones) > 0:
            return self.condiciones
        if self.claveOrigenA and self.claveOrigenB:
            return [CondicionJoin(claveOrigenA=self.claveOrigenA, claveOrigenB=self.claveOrigenB)]
        return []


class SolicitudMuestreoDataLake(BaseModel):
    """
    Solicitud para previsualizar filas y perfilar un archivo Parquet del Data Lake.
    """
    nombreArchivoParquet: str
    limiteFilas: int = 10


class SolicitudRegistroDataLake(BaseModel):
    """
    Contrato para formalizar el registro de un Parquet del Data Lake en el catálogo de vistas.
    """
    codigoVista: str
    nombreVista: str
    nombreArchivoParquet: str
    mapeoColumnas: List[Dict[str, Any]]
    rolPorDefectoId: Optional[str] = "TODOS"
    descripcion: Optional[str] = None
