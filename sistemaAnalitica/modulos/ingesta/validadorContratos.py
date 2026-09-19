"""
Validador de contratos de datos y metadatos.
Garantiza que la estructura, columnas y tipos esperados coincidan antes de permitir la ingesta.
"""

from typing import List, Dict, Any
from dataclasses import dataclass, field
import pandas as pd


@dataclass
class ResultadoValidacion:
    """
    Estructura de respuesta que consolida el diagnóstico de validación de contrato.
    """
    esValido: bool
    errores: List[str] = field(default_factory=list)
    advertencias: List[str] = field(default_factory=list)
    totalFilas: int = 0
    totalColumnas: int = 0


class ValidadorContratos:
    """
    Auditor formal de compatibilidad de esquemas entre los datos entrantes y el contrato establecido.
    """

    @classmethod
    def validarEsquema(
        cls,
        dataframe: pd.DataFrame,
        contratoJson: Dict[str, Any]
    ) -> ResultadoValidacion:
        """
        Comprueba que el DataFrame cumpla estrictamente con la definición del contrato JSON.
        """
        resultado = ResultadoValidacion(
            esValido=True,
            totalFilas=len(dataframe),
            totalColumnas=len(dataframe.columns)
        )

        columnasContrato = contratoJson.get("columnas", [])
        columnasDataFrameNormalizadas = {str(col).strip().lower(): col for col in dataframe.columns}

        # 1. Validación de presencia de columnas
        for defColumna in columnasContrato:
            nombreEsperado = str(defColumna.get("nombreColumna", "")).strip()
            esObligatoria = defColumna.get("esObligatoria", True)
            clasificacion = defColumna.get("clasificacionSemantica", "Categorica/Dimension")

            # Si es descarte y no es obligatoria, podemos ignorar si no viene
            if clasificacion == "Identificador/Descarte" and not esObligatoria:
                continue

            nombreMinuscula = nombreEsperado.lower()
            if nombreMinuscula not in columnasDataFrameNormalizadas:
                if esObligatoria:
                    resultado.esValido = False
                    resultado.errores.append(
                        f"Columna obligatoria ausente: '{nombreEsperado}'. "
                        f"Se esperaba una columna clasificada como '{clasificacion}'."
                    )
                else:
                    resultado.advertencias.append(
                        f"Columna opcional no encontrada: '{nombreEsperado}'."
                    )
            else:
                # 2. Validación de consistencia de tipos
                columnaReal = columnasDataFrameNormalizadas[nombreMinuscula]
                tipoEsperado = defColumna.get("tipoDatoEsperado", "texto").lower()
                cls._validarCompatibilidadTipo(dataframe[columnaReal], tipoEsperado, nombreEsperado, resultado)

        # 3. Advertencia de columnas adicionales no definidas en el contrato
        nombresContratoNormalizados = {
            str(col.get("nombreColumna", "")).strip().lower()
            for col in columnasContrato
        }
        for colReal in dataframe.columns:
            if str(colReal).strip().lower() not in nombresContratoNormalizados:
                resultado.advertencias.append(
                    f"Columna adicional detectada fuera del contrato: '{colReal}'. Se procesará como dimensión auxiliar."
                )

        return resultado

    @staticmethod
    def _validarCompatibilidadTipo(
        serie: pd.Series,
        tipoEsperado: str,
        nombreColumna: str,
        resultado: ResultadoValidacion
    ) -> None:
        """
        Comprueba si una serie puede coercerse o ya es compatible con el tipo solicitado.
        """
        serieSinNulos = serie.dropna()
        if len(serieSinNulos) == 0:
            return

        if tipoEsperado in ["entero", "int", "integer"]:
            # Verificar si se puede convertir a numérico sin pérdidas
            convertidos = pd.to_numeric(serieSinNulos, errors="coerce")
            fallos = int(convertidos.isna().sum())
            if fallos > 0:
                porcentajeError = (fallos / len(serieSinNulos)) * 100
                if porcentajeError > 5.0:
                    resultado.esValido = False
                    resultado.errores.append(
                        f"Incompatibilidad de tipos en '{nombreColumna}': Se esperaba número entero, "
                        f"pero se encontraron {fallos} valores no numéricos ({porcentajeError:.1f}%)."
                    )
                else:
                    resultado.advertencias.append(
                        f"Valores no enteros en '{nombreColumna}': {fallos} filas contienen valores no numéricos."
                    )

        elif tipoEsperado in ["decimal", "float", "double", "metricasumable", "metricanosumable"]:
            convertidos = pd.to_numeric(serieSinNulos, errors="coerce")
            fallos = int(convertidos.isna().sum())
            if fallos > 0:
                porcentajeError = (fallos / len(serieSinNulos)) * 100
                if porcentajeError > 5.0:
                    resultado.esValido = False
                    resultado.errores.append(
                        f"Incompatibilidad de tipos en '{nombreColumna}': Se esperaba número decimal o métrica, "
                        f"pero se detectaron {fallos} valores no convertibles ({porcentajeError:.1f}%)."
                    )
                else:
                    resultado.advertencias.append(
                        f"Métrica '{nombreColumna}' contiene {fallos} filas con valores no numéricos que se imputarán a nulo."
                    )

        elif tipoEsperado in ["fecha", "date", "datetime"]:
            if not pd.api.types.is_datetime64_any_dtype(serieSinNulos):
                convertidos = pd.to_datetime(serieSinNulos, errors="coerce")
                fallos = int(convertidos.isna().sum())
                if fallos > (len(serieSinNulos) * 0.20):
                    resultado.esValido = False
                    resultado.errores.append(
                        f"Incompatibilidad de tipos en '{nombreColumna}': Se esperaba formato de fecha/tiempo, "
                        f"pero no fue posible parsear {fallos} registros."
                    )

    @classmethod
    def construirContratoJson(
        cls,
        idModelo: str,
        nombreVista: str,
        tipoIngesta: str,
        mapeoColumnas: List[Dict[str, Any]],
        definicionJoins: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Construye el diccionario formal del contrato JSON según la especificación técnica.
        """
        return {
            "idModelo": idModelo,
            "nombreVista": nombreVista,
            "tipoIngesta": tipoIngesta,
            "columnas": [
                {
                    "nombreColumna": col.get("nombreColumna"),
                    "tipoDatoEsperado": col.get("tipoDatoEsperado", "texto"),
                    "clasificacionSemantica": col.get("clasificacionSemantica", "Categorica/Dimension"),
                    "esObligatoria": col.get("esObligatoria", True)
                }
                for col in mapeoColumnas
            ],
            "definicionJoins": definicionJoins or []
        }
