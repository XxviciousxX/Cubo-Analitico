"""
Lector de archivos Excel a alta velocidad utilizando python-calamine (bindings Rust).
Permite listar hojas, extraer muestras de datos y convertir tablas completas a DataFrames.
"""

import io
import json
from typing import List, Dict, Any, Union, Optional
import pandas as pd
from python_calamine import load_workbook


class CalamineLectorExcel:
    """
    Componente para la inspección y carga eficiente de libros de cálculo Excel.
    """

    @staticmethod
    def _normalizarEntrada(fuenteArchivo: Union[str, bytes, io.BytesIO]) -> Any:
        """
        Normaliza la entrada de archivo para compatibilidad con python-calamine y pandas.
        """
        if isinstance(fuenteArchivo, bytes):
            return io.BytesIO(fuenteArchivo)
        return fuenteArchivo

    @classmethod
    def obtenerHojasLibro(cls, fuenteArchivo: Union[str, bytes, io.BytesIO]) -> List[str]:
        """
        Extrae la lista de nombres de hojas disponibles en el libro Excel de forma instantánea.
        """
        fuenteNormalizada = cls._normalizarEntrada(fuenteArchivo)
        if isinstance(fuenteNormalizada, io.BytesIO):
            fuenteNormalizada.seek(0)
            libro = load_workbook(fuenteNormalizada)
            return list(libro.sheet_names)
        else:
            libro = load_workbook(fuenteNormalizada)
            return list(libro.sheet_names)

    @classmethod
    def extraerMuestraHoja(
        cls,
        fuenteArchivo: Union[str, bytes, io.BytesIO],
        nombreHoja: str,
        limiteFilas: int = 10
    ) -> Dict[str, Any]:
        """
        Carga únicamente las primeras N filas de una hoja para previsualización y perfilado de esquema.
        """
        fuenteNormalizada = cls._normalizarEntrada(fuenteArchivo)
        if isinstance(fuenteNormalizada, io.BytesIO):
            fuenteNormalizada.seek(0)

        dataframeMuestra = pd.read_excel(
            fuenteNormalizada,
            sheet_name=nombreHoja,
            engine="calamine",
            nrows=limiteFilas
        )

        # Serialización segura con to_json para convertir Timestamps, fechas, NaN y NaT a formato JSON estándar
        filasMuestraJson = json.loads(dataframeMuestra.to_json(orient="records", date_format="iso"))

        perfilColumnas = cls.perfiladorTiposColumna(dataframeMuestra)

        return {
            "nombreHoja": nombreHoja,
            "totalColumnas": len(dataframeMuestra.columns),
            "columnas": list(dataframeMuestra.columns.astype(str)),
            "perfilColumnas": perfilColumnas,
            "filasMuestra": filasMuestraJson
        }

    @classmethod
    def convertirHojaADataFrame(
        cls,
        fuenteArchivo: Union[str, bytes, io.BytesIO],
        nombreHoja: str
    ) -> pd.DataFrame:
        """
        Lee el contenido completo de una hoja de cálculo mediante el motor calamine.
        """
        fuenteNormalizada = cls._normalizarEntrada(fuenteArchivo)
        if isinstance(fuenteNormalizada, io.BytesIO):
            fuenteNormalizada.seek(0)

        dataframeCompleto = pd.read_excel(
            fuenteNormalizada,
            sheet_name=nombreHoja,
            engine="calamine"
        )
        return dataframeCompleto

    @staticmethod
    def perfiladorTiposColumna(dataframe: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """
        Infiere tipos de datos primitivos y una clasificación semántica recomendada para cada columna.
        """
        perfil = {}
        for nombreColumna in dataframe.columns:
            serie = dataframe[nombreColumna].dropna()
            tipoDatoInferido = "texto"
            clasificacionSugerida = "Categorica/Dimension"

            if pd.api.types.is_numeric_dtype(serie):
                if pd.api.types.is_integer_dtype(serie):
                    # Si parece un ID (por nombre o valores secuenciales únicos)
                    nombreColMin = str(nombreColumna).lower()
                    if "id" in nombreColMin or "cod" in nombreColMin or "folio" in nombreColMin:
                        tipoDatoInferido = "entero"
                        clasificacionSugerida = "Identificador/Descarte"
                    else:
                        tipoDatoInferido = "entero"
                        clasificacionSugerida = "MetricaSumable"
                else:
                    tipoDatoInferido = "decimal"
                    # Métricas con porcentaje o tasa suelen ser promedios o no sumables
                    nombreColMin = str(nombreColumna).lower()
                    if "porc" in nombreColMin or "pct" in nombreColMin or "tasa" in nombreColMin or "margen" in nombreColMin:
                        clasificacionSugerida = "MetricaNoSumable"
                    else:
                        clasificacionSugerida = "MetricaSumable"

            elif pd.api.types.is_datetime64_any_dtype(serie):
                tipoDatoInferido = "fecha"
                clasificacionSugerida = "Categorica/Dimension"
            elif pd.api.types.is_bool_dtype(serie):
                tipoDatoInferido = "booleano"
                clasificacionSugerida = "Categorica/Dimension"
            else:
                # Comprobar si parece fecha en texto
                tipoDatoInferido = "texto"
                nombreColMin = str(nombreColumna).lower()
                if "id" in nombreColMin or "cod" in nombreColMin:
                    clasificacionSugerida = "Identificador/Descarte"
                else:
                    clasificacionSugerida = "Categorica/Dimension"

            perfil[str(nombreColumna)] = {
                "tipoDatoPrimitivo": tipoDatoInferido,
                "clasificacionSugerida": clasificacionSugerida,
                "conteoNoNulos": int(serie.count()),
                "valoresUnicos": int(serie.nunique()) if len(serie) > 0 else 0
            }

        return perfil

    @classmethod
    def analizarLibroCompleto(
        cls,
        fuenteArchivo: Union[str, bytes, io.BytesIO],
        limiteMuestra: int = 5
    ) -> Dict[str, Any]:
        """
        Inspecciona todas las hojas de un libro Excel, agrupa hojas con estructura de columnas
        idéntica para unificación automática (UNION ALL) y clasifica hojas distintas como
        dimensiones candidatas para un Diagrama de Estrella (Star Schema).
        """
        hojas = cls.obtenerHojasLibro(fuenteArchivo)
        if not hojas:
            return {"exito": False, "error": "El libro Excel no contiene hojas legibles."}

        detalleHojas = {}
        gruposPorFirma = {}  # firma -> lista de nombres de hojas
        columnasPorFirma = {}

        for h in hojas:
            try:
                muestra = cls.extraerMuestraHoja(fuenteArchivo, h, limiteFilas=limiteMuestra)
                cols = muestra["columnas"]
                colsInfo = []
                for c in cols:
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
                    "filasMuestra": muestra["filasMuestra"],
                    "perfilColumnas": muestra["perfilColumnas"]
                }

                # Firma normalizada basada en nombres de columnas ordenados en minúsculas
                firma = tuple(sorted([str(c).strip().lower() for c in cols]))
                if firma not in gruposPorFirma:
                    gruposPorFirma[firma] = []
                    columnasPorFirma[firma] = colsInfo
                gruposPorFirma[firma].append(h)
            except Exception as e:
                detalleHojas[h] = {
                    "totalColumnas": 0,
                    "columnas": [],
                    "filasMuestra": [],
                    "error": str(e)
                }

        # Identificar el grupo principal (el más numeroso de hojas idénticas)
        # Si hay empate, priorizar el que aparezca primero en el libro
        firmasOrdenadas = sorted(
            gruposPorFirma.keys(),
            key=lambda f: len(gruposPorFirma[f]),
            reverse=True
        )

        firmaPrincipal = firmasOrdenadas[0] if firmasOrdenadas else ()
        hojasIdenticas = gruposPorFirma.get(firmaPrincipal, [])
        columnasHechos = columnasPorFirma.get(firmaPrincipal, [])

        # Todas las demás hojas con estructura distinta son candidatas a dimensiones
        hojasDimensionales = []
        for f in firmasOrdenadas[1:]:
            for nomHoja in gruposPorFirma[f]:
                hojasDimensionales.append({
                    "nombreHoja": nomHoja,
                    "totalColumnas": detalleHojas[nomHoja]["totalColumnas"],
                    "columnas": detalleHojas[nomHoja]["columnas"],
                    "filasMuestra": detalleHojas[nomHoja]["filasMuestra"]
                })

        # Detección inteligente de llaves candidatas (FK/PK) entre la tabla de hechos y las dimensiones
        nombresHechosMin = {str(c["nombre"]).strip().lower(): c["nombre"] for c in columnasHechos}
        llavesCandidatas = {}

        for dim in hojasDimensionales:
            nomDim = dim["nombreHoja"]
            coincidencias = []
            for colD in dim["columnas"]:
                colDMin = str(colD["nombre"]).strip().lower()
                if colDMin in nombresHechosMin:
                    coincidencias.append({
                        "claveHechos": nombresHechosMin[colDMin],
                        "claveDimension": colD["nombre"],
                        "esExacto": True
                    })
                elif any(pat in colDMin for pat in ["id_", "cod_", "num_", "nro_"]):
                    # Búsqueda por subcadena
                    for colHMin, colHOrig in nombresHechosMin.items():
                        if colDMin in colHMin or colHMin in colDMin:
                            coincidencias.append({
                                "claveHechos": colHOrig,
                                "claveDimension": colD["nombre"],
                                "esExacto": False
                            })
            llavesCandidatas[nomDim] = coincidencias

        return {
            "exito": True,
            "totalHojas": len(hojas),
            "todasLasHojas": hojas,
            "hojasIdenticas": hojasIdenticas,
            "totalHojasIdenticas": len(hojasIdenticas),
            "columnasHechos": columnasHechos,
            "hojasDimensionales": hojasDimensionales,
            "totalHojasDimensionales": len(hojasDimensionales),
            "llavesCandidatas": llavesCandidatas,
            "detalleHojas": detalleHojas,
            "esHomogeneo": len(hojasDimensionales) == 0
        }

    @classmethod
    def unificarHojasIdenticas(
        cls,
        fuenteArchivo: Union[str, bytes, io.BytesIO],
        listaHojas: List[str],
        columnaTrazadora: Optional[str] = "hoja_origen"
    ) -> pd.DataFrame:
        """
        Carga mediante Calamine y unifica verticalmente (UNION ALL) múltiples hojas
        que poseen idéntica estructura de columnas, inyectando la columna trazadora de origen.
        """
        if not listaHojas:
            raise ValueError("La lista de hojas a unificar no puede estar vacía.")

        dataframes = []
        for hoja in listaHojas:
            df = cls.convertirHojaADataFrame(fuenteArchivo, hoja)
            if columnaTrazadora:
                df[columnaTrazadora] = str(hoja)
            dataframes.append(df)

        if len(dataframes) == 1:
            return dataframes[0]

        dfConsolidado = pd.concat(dataframes, ignore_index=True)
        return dfConsolidado

