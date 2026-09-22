"""
Servicio de Unión Analítica y Muestreo para Cubos Compuestos y Data Lake Parquet.
Utiliza DuckDB vectorizado para calcular cardinalidades, prevenir fan-out y exportar en ZSTD.
"""

import os
import json
import duckdb
from typing import Dict, Any, List, Optional
import pandas as pd


class GeneradorCuboCompuesto:
    """
    Servicio encargado de inspeccionar archivos Parquet, perfilar claves de cruce
    y generar archivos Parquet compuestos (OBT) mediante consultas SQL vectorizadas.
    """

    @classmethod
    def normalizarRutaSql(cls, rutaArchivo: str) -> str:
        """
        Normaliza rutas en sistemas operativos Windows para evitar errores en DuckDB.
        """
        return os.path.abspath(rutaArchivo).replace("\\", "/")

    @classmethod
    def obtenerMetadatosOrigen(cls, rutaParquet: str) -> Dict[str, Any]:
        """
        Inspecciona el esquema, tipos de datos y total de registros de un archivo Parquet.
        """
        if not os.path.exists(rutaParquet) or os.path.getsize(rutaParquet) == 0:
            try:
                from sistemaAnalitica.modulos.motorAnalitico.servicioPersistenciaCubos import ServicioPersistenciaCubos
                ServicioPersistenciaCubos.asegurarParquetPorRuta(rutaParquet)
            except Exception:
                pass

        if not os.path.exists(rutaParquet):
            raise FileNotFoundError(f"Archivo Parquet no encontrado: {rutaParquet}")

        rutaSql = cls.normalizarRutaSql(rutaParquet)
        conexion = duckdb.connect()
        try:
            esquema = conexion.execute(f"DESCRIBE SELECT * FROM read_parquet('{rutaSql}') LIMIT 1").fetchall()
            totalFilas = int(conexion.execute(f"SELECT COUNT(*) FROM read_parquet('{rutaSql}')").fetchone()[0])

            columnas = []
            for col in esquema:
                colNombre = col[0]
                colTipo = str(col[1]).upper()
                esNumerico = any(t in colTipo for t in ["INT", "DOUBLE", "FLOAT", "DECIMAL", "HUGEINT", "BIGINT", "NUMERIC"])
                esTemporal = any(t in colTipo for t in ["DATE", "TIME", "TIMESTAMP"])

                # Clasificación sugerida por defecto
                if esNumerico:
                    clasificacion = "MetricaSumable"
                elif esTemporal:
                    clasificacion = "Categorica/Dimension"
                else:
                    clasificacion = "Categorica/Dimension"

                columnas.append({
                    "nombreColumna": colNombre,
                    "tipoDato": colTipo,
                    "esNumerico": esNumerico,
                    "esTemporal": esTemporal,
                    "clasificacionSugerida": clasificacion
                })

            return {
                "exito": True,
                "rutaParquet": rutaParquet,
                "totalFilas": totalFilas,
                "columnas": columnas
            }
        finally:
            conexion.close()

    @classmethod
    def obtenerMuestraDataLake(cls, rutaParquet: str, limite: int = 10) -> Dict[str, Any]:
        """
        Extrae una muestra de registros y metadatos de un archivo Parquet del Data Lake
        para permitir el perfilado semántico en la interfaz web de manera idéntica a Excel/SQL.
        """
        metadatos = cls.obtenerMetadatosOrigen(rutaParquet)
        rutaSql = cls.normalizarRutaSql(rutaParquet)

        conexion = duckdb.connect()
        try:
            dfMuestra = conexion.execute(f"SELECT * FROM read_parquet('{rutaSql}') LIMIT {limite}").fetchdf()
            filas = json.loads(dfMuestra.to_json(orient="records", date_format="iso"))
            return {
                "exito": True,
                "totalFilas": metadatos["totalFilas"],
                "columnas": metadatos["columnas"],
                "filasMuestra": filas
            }
        finally:
            conexion.close()

    @classmethod
    def _normalizarCondiciones(
        cls,
        condiciones: Optional[List[Dict[str, Any]]] = None,
        claveA: Optional[str] = None,
        claveB: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Normaliza las condiciones de cruce asegurando compatibilidad con modelos Pydantic o dicts.
        """
        resultado = []
        if condiciones:
            for c in condiciones:
                if hasattr(c, "claveOrigenA") and hasattr(c, "claveOrigenB"):
                    kA = c.claveOrigenA
                    kB = c.claveOrigenB
                elif isinstance(c, dict):
                    kA = c.get("claveOrigenA") or c.get("claveA")
                    kB = c.get("claveOrigenB") or c.get("claveB")
                else:
                    continue
                if kA and kB:
                    resultado.append({"claveOrigenA": str(kA).strip(), "claveOrigenB": str(kB).strip()})
        if not resultado and claveA and claveB:
            resultado.append({"claveOrigenA": str(claveA).strip(), "claveOrigenB": str(claveB).strip()})
        return resultado

    @classmethod
    def validarRiesgoDuplicacion(
        cls,
        rutaOrigenA: str,
        rutaOrigenB: str,
        claveA: Optional[str] = None,
        claveB: Optional[str] = None,
        condiciones: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Verifica la cardinalidad de las claves simples o compuestas y detecta
        preventivamente el riesgo de explosión de filas (fan-out) o duplicación de métricas aditivas.
        """
        if not os.path.exists(rutaOrigenA) or not os.path.exists(rutaOrigenB):
            return {
                "exito": False,
                "error": "Uno o ambos archivos Parquet no existen en el disco."
            }

        conds = cls._normalizarCondiciones(condiciones, claveA, claveB)
        if not conds:
            return {
                "exito": False,
                "error": "Debes especificar al menos una condición de unión (par de claves)."
            }

        rutaSqlA = cls.normalizarRutaSql(rutaOrigenA)
        rutaSqlB = cls.normalizarRutaSql(rutaOrigenB)

        conexion = duckdb.connect()
        try:
            columnasB = [c["claveOrigenB"] for c in conds]
            columnasB_sql = ', '.join([f'"{col}"' for col in columnasB])

            # Validar unicidad de la tupla de claves en tabla secundaria B
            resB = conexion.execute(
                f"""
                SELECT COUNT(*) AS total,
                       (SELECT COUNT(*) FROM (SELECT DISTINCT {columnasB_sql} FROM read_parquet('{rutaSqlB}'))) AS unicos
                FROM read_parquet('{rutaSqlB}')
                """
            ).fetchone()

            totalFilasB = int(resB[0]) if resB else 0
            valoresUnicosB = int(resB[1]) if resB else 0

            # Validar coincidencias compuestas entre A y B
            condicionesOn = " AND ".join([f'a."{c["claveOrigenA"]}" = b."{c["claveOrigenB"]}"' for c in conds])
            columnasA_sql = ', '.join([f'a."{c["claveOrigenA"]}"' for c in conds])

            resCoincidencias = conexion.execute(
                f"""
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT {columnasA_sql}
                    FROM read_parquet('{rutaSqlA}') a
                    INNER JOIN read_parquet('{rutaSqlB}') b ON {condicionesOn}
                )
                """
            ).fetchone()
            clavesCoincidentes = int(resCoincidencias[0]) if resCoincidencias else 0

            esClaveUnicaB = (valoresUnicosB == totalFilasB)
            porcentajeUnicidadB = (valoresUnicosB / totalFilasB * 100.0) if totalFilasB > 0 else 0.0

            riesgoFanOut = not esClaveUnicaB
            clavesB_texto = ", ".join([f"'{c}'" for c in columnasB])

            if riesgoFanOut:
                mensaje = (
                    f"ADVERTENCIA DE FAN-OUT: La combinación de claves ({clavesB_texto}) en la tabla B no es única "
                    f"({valoresUnicosB:,} combinaciones únicas de {totalFilasB:,} filas, {porcentajeUnicidadB:.1f}% unicidad). "
                    f"El cruce generará duplicación de registros y multiplicará métricas aditivas."
                )
                severidad = "PELIGRO"
            else:
                mensaje = (
                    f"CARDINALIDAD SEGURA: La combinación de claves ({clavesB_texto}) en la tabla B es 100% única "
                    f"({valoresUnicosB:,} combinaciones distintas en {totalFilasB:,} filas). "
                    f"Se encontraron {clavesCoincidentes:,} registros coincidentes con la tabla A."
                )
                severidad = "SEGURO"

            return {
                "exito": True,
                "totalFilasB": totalFilasB,
                "valoresUnicosB": valoresUnicosB,
                "porcentajeUnicidadB": round(porcentajeUnicidadB, 2),
                "clavesCoincidentes": clavesCoincidentes,
                "riesgoFanOut": riesgoFanOut,
                "severidad": severidad,
                "mensaje": mensaje
            }
        except Exception as errorEvaluacion:
            return {
                "exito": False,
                "error": f"Error validando cardinalidad con DuckDB: {str(errorEvaluacion)}"
            }
        finally:
            conexion.close()

    @classmethod
    def validarRiesgoDuplicacionDataFrames(
        cls,
        dfA: pd.DataFrame,
        dfB: pd.DataFrame,
        condiciones: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Valida cardinalidad y riesgo de fan-out entre dos DataFrames de pandas (p. ej. hojas de Excel).
        """
        conds = cls._normalizarCondiciones(condiciones)
        if not conds:
            return {"exito": False, "error": "Debes especificar al menos una condición de unión."}

        conexion = duckdb.connect()
        try:
            columnasB = [c["claveOrigenB"] for c in conds]
            columnasB_sql = ', '.join([f'"{col}"' for col in columnasB])

            resB = conexion.execute(
                f"""
                SELECT COUNT(*) AS total,
                       (SELECT COUNT(*) FROM (SELECT DISTINCT {columnasB_sql} FROM dfB)) AS unicos
                FROM dfB
                """
            ).fetchone()

            totalFilasB = int(resB[0]) if resB else 0
            valoresUnicosB = int(resB[1]) if resB else 0

            condicionesOn = " AND ".join([f'a."{c["claveOrigenA"]}" = b."{c["claveOrigenB"]}"' for c in conds])
            columnasA_sql = ', '.join([f'a."{c["claveOrigenA"]}"' for c in conds])

            resCoincidencias = conexion.execute(
                f"""
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT {columnasA_sql}
                    FROM dfA a
                    INNER JOIN dfB b ON {condicionesOn}
                )
                """
            ).fetchone()
            clavesCoincidentes = int(resCoincidencias[0]) if resCoincidencias else 0

            esClaveUnicaB = (valoresUnicosB == totalFilasB)
            porcentajeUnicidadB = (valoresUnicosB / totalFilasB * 100.0) if totalFilasB > 0 else 0.0
            riesgoFanOut = not esClaveUnicaB
            clavesB_texto = ", ".join([f"'{c}'" for c in columnasB])

            if riesgoFanOut:
                mensaje = (
                    f"ADVERTENCIA DE FAN-OUT: La combinación de claves ({clavesB_texto}) en la tabla B no es única "
                    f"({valoresUnicosB:,} combinaciones únicas de {totalFilasB:,} filas, {porcentajeUnicidadB:.1f}% unicidad). "
                    f"El cruce generará duplicación de registros y multiplicará métricas aditivas."
                )
                severidad = "PELIGRO"
            else:
                mensaje = (
                    f"CARDINALIDAD SEGURA: La combinación de claves ({clavesB_texto}) en la tabla B es 100% única "
                    f"({valoresUnicosB:,} combinaciones distintas en {totalFilasB:,} filas). "
                    f"Se encontraron {clavesCoincidentes:,} registros coincidentes con la tabla A."
                )
                severidad = "SEGURO"

            return {
                "exito": True,
                "totalFilasB": totalFilasB,
                "valoresUnicosB": valoresUnicosB,
                "porcentajeUnicidadB": round(porcentajeUnicidadB, 2),
                "clavesCoincidentes": clavesCoincidentes,
                "riesgoFanOut": riesgoFanOut,
                "severidad": severidad,
                "mensaje": mensaje
            }
        except Exception as ex:
            return {"exito": False, "error": f"Error validando cardinalidad: {str(ex)}"}
        finally:
            conexion.close()

    @classmethod
    def generarParquetCompuesto(
        cls,
        rutaOrigenA: str,
        rutaOrigenB: str,
        claveOrigenA: Optional[str] = None,
        claveOrigenB: Optional[str] = None,
        tipoJoin: str = "LEFT",
        columnasMapeadas: List[Dict[str, Any]] = None,
        rutaDestinoParquet: str = None,
        condiciones: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta el cruce relacional vectorizado en DuckDB con soporte para claves simples
        o compuestas (múltiples condiciones AND) y exporta hacia Parquet ZSTD.
        """
        if not os.path.exists(rutaOrigenA) or os.path.getsize(rutaOrigenA) == 0:
            try:
                from sistemaAnalitica.modulos.motorAnalitico.servicioPersistenciaCubos import ServicioPersistenciaCubos
                ServicioPersistenciaCubos.asegurarParquetPorRuta(rutaOrigenA)
            except Exception:
                pass

        if not os.path.exists(rutaOrigenB) or os.path.getsize(rutaOrigenB) == 0:
            try:
                from sistemaAnalitica.modulos.motorAnalitico.servicioPersistenciaCubos import ServicioPersistenciaCubos
                ServicioPersistenciaCubos.asegurarParquetPorRuta(rutaOrigenB)
            except Exception:
                pass

        if not os.path.exists(rutaOrigenA) or not os.path.exists(rutaOrigenB):
            raise FileNotFoundError("Una o ambas rutas de Parquet no existen.")

        conds = cls._normalizarCondiciones(condiciones, claveOrigenA, claveOrigenB)
        if not conds:
            raise ValueError("Debes especificar al menos una condición de unión.")

        os.makedirs(os.path.dirname(os.path.abspath(rutaDestinoParquet)), exist_ok=True)

        rutaSqlA = cls.normalizarRutaSql(rutaOrigenA)
        rutaSqlB = cls.normalizarRutaSql(rutaOrigenB)
        rutaSqlDestino = cls.normalizarRutaSql(rutaDestinoParquet)

        # Mapear tipo de JOIN
        tipoJoinSql = {
            "LEFT": "LEFT JOIN",
            "INNER": "INNER JOIN",
            "FULL": "FULL OUTER JOIN",
            "ALL": "FULL OUTER JOIN"
        }.get(str(tipoJoin).upper(), "LEFT JOIN")

        # Construir proyecciones SELECT excluyendo Descarte
        proyeccionesSelect = []
        nombresFinalesUsados = set()

        for col in (columnasMapeadas or []):
            clasif = col.get("clasificacionSemantica", "Categorica/Dimension")
            if clasif == "Identificador/Descarte" or not col.get("esObligatoria", True):
                continue

            origen = col.get("origen", "A").upper()
            nombreOriginal = col.get("nombreOriginal")
            nombreFinal = col.get("nombreFinal") or nombreOriginal

            # Resolver colisiones si el nombre ya fue usado
            if nombreFinal in nombresFinalesUsados:
                nombreFinal = f"{'origenA' if origen == 'A' else 'origenB'}_{nombreFinal}"

            nombresFinalesUsados.add(nombreFinal)
            aliasPrefijo = "a" if origen == "A" else "b"
            proyeccionesSelect.append(f'{aliasPrefijo}."{nombreOriginal}" AS "{nombreFinal}"')

        if not proyeccionesSelect:
            raise ValueError("Debes seleccionar al menos una columna para incluir en el cubo compuesto.")

        selectClausula = ",\n    ".join(proyeccionesSelect)
        condicionesOn = " AND ".join([f'a."{c["claveOrigenA"]}" = b."{c["claveOrigenB"]}"' for c in conds])

        sentenciaSql = f"""
        COPY (
            SELECT
                {selectClausula}
            FROM read_parquet('{rutaSqlA}') a
            {tipoJoinSql} read_parquet('{rutaSqlB}') b
                ON {condicionesOn}
        ) TO '{rutaSqlDestino}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """

        conexion = duckdb.connect()
        try:
            if os.path.exists(rutaDestinoParquet):
                os.remove(rutaDestinoParquet)

            conexion.execute(sentenciaSql)
            filasGeneradas = int(conexion.execute(f"SELECT COUNT(*) FROM read_parquet('{rutaSqlDestino}')").fetchone()[0])

            return {
                "exito": True,
                "rutaParquet": rutaDestinoParquet,
                "totalFilasGeneradas": filasGeneradas,
                "totalColumnas": len(proyeccionesSelect)
            }
        finally:
            conexion.close()

    @classmethod
    def generarParquetDesdeDataFramesCompuestos(
        cls,
        dfA: pd.DataFrame,
        dfB: pd.DataFrame,
        condiciones: List[Dict[str, Any]],
        tipoJoin: str,
        columnasMapeadas: List[Dict[str, Any]],
        rutaDestinoParquet: str
    ) -> Dict[str, Any]:
        """
        Ejecuta el cruce relacional vectorizado entre dos DataFrames de pandas (por ejemplo,
        provenientes de dos hojas distintas de un archivo Excel) utilizando DuckDB en memoria
        y exportando directamente a Parquet con compresión ZSTD.
        """
        conds = cls._normalizarCondiciones(condiciones)
        if not conds:
            raise ValueError("Debes especificar al menos una condición de unión.")

        os.makedirs(os.path.dirname(os.path.abspath(rutaDestinoParquet)), exist_ok=True)
        rutaSqlDestino = cls.normalizarRutaSql(rutaDestinoParquet)

        tipoJoinSql = {
            "LEFT": "LEFT JOIN",
            "INNER": "INNER JOIN",
            "FULL": "FULL OUTER JOIN",
            "ALL": "FULL OUTER JOIN"
        }.get(str(tipoJoin).upper(), "LEFT JOIN")

        # Construir proyecciones SELECT
        proyeccionesSelect = []
        nombresFinalesUsados = set()

        for col in (columnasMapeadas or []):
            clasif = col.get("clasificacionSemantica", "Categorica/Dimension")
            if clasif == "Identificador/Descarte" or not col.get("esObligatoria", True):
                continue

            origen = col.get("origen", "A").upper()
            nombreOriginal = col.get("nombreOriginal")
            nombreFinal = col.get("nombreFinal") or nombreOriginal

            if nombreFinal in nombresFinalesUsados:
                nombreFinal = f"{'origenA' if origen == 'A' else 'origenB'}_{nombreFinal}"

            nombresFinalesUsados.add(nombreFinal)
            aliasPrefijo = "a" if origen == "A" else "b"
            proyeccionesSelect.append(f'{aliasPrefijo}."{nombreOriginal}" AS "{nombreFinal}"')

        if not proyeccionesSelect:
            raise ValueError("Debes seleccionar al menos una columna para incluir en el cubo compuesto.")

        selectClausula = ",\n    ".join(proyeccionesSelect)
        condicionesOn = " AND ".join([f'a."{c["claveOrigenA"]}" = b."{c["claveOrigenB"]}"' for c in conds])

        sentenciaSql = f"""
        COPY (
            SELECT
                {selectClausula}
            FROM dfA a
            {tipoJoinSql} dfB b
                ON {condicionesOn}
        ) TO '{rutaSqlDestino}' (FORMAT PARQUET, COMPRESSION ZSTD);
        """

        conexion = duckdb.connect()
        try:
            if os.path.exists(rutaDestinoParquet):
                os.remove(rutaDestinoParquet)

            conexion.execute(sentenciaSql)
            filasGeneradas = int(conexion.execute(f"SELECT COUNT(*) FROM read_parquet('{rutaSqlDestino}')").fetchone()[0])

            return {
                "exito": True,
                "rutaParquet": rutaDestinoParquet,
                "totalFilasGeneradas": filasGeneradas,
                "totalColumnas": len(proyeccionesSelect)
            }
        finally:
            conexion.close()

    @classmethod
    def generarParquetEsquemaEstrella(
        cls,
        dfHechos: pd.DataFrame,
        mapaDimensiones: Dict[str, pd.DataFrame],
        relaciones: List[Dict[str, Any]],
        columnasMapeadas: Optional[List[Dict[str, Any]]],
        rutaDestinoParquet: str
    ) -> Dict[str, Any]:
        """
        Ejecuta la consolidación analítica en esquema de estrella (Star Schema) uniendo
        una tabla central de hechos (que puede ser la unificación de N hojas idénticas)
        con múltiples tablas dimensionales mediante DuckDB vectorizado y compresión ZSTD.
        """
        os.makedirs(os.path.dirname(os.path.abspath(rutaDestinoParquet)), exist_ok=True)
        rutaSqlDestino = cls.normalizarRutaSql(rutaDestinoParquet)

        conexion = duckdb.connect()
        try:
            conexion.register("tabla_hechos", dfHechos)

            # Si no hay dimensiones o relaciones, guardar directamente la tabla de hechos consolidada
            if not mapaDimensiones or not relaciones:
                if os.path.exists(rutaDestinoParquet):
                    os.remove(rutaDestinoParquet)
                conexion.execute(f"COPY tabla_hechos TO '{rutaSqlDestino}' (FORMAT PARQUET, COMPRESSION ZSTD);")
                filasGeneradas = int(conexion.execute(f"SELECT COUNT(*) FROM read_parquet('{rutaSqlDestino}')").fetchone()[0])
                totalCols = len(dfHechos.columns)
                return {
                    "exito": True,
                    "rutaParquet": rutaDestinoParquet,
                    "totalFilasGeneradas": filasGeneradas,
                    "totalColumnas": totalCols
                }

            # Registrar cada tabla dimensional con un alias seguro
            joinsSql = []
            mapaAliasDim = {}
            for idx, rel in enumerate(relaciones):
                nomDim = rel.get("nombreDimension") or rel.get("hojaDimension")
                if not nomDim or nomDim not in mapaDimensiones:
                    continue

                dfDim = mapaDimensiones[nomDim]
                aliasDim = f"dim_{idx}"
                mapaAliasDim[nomDim] = aliasDim
                conexion.register(aliasDim, dfDim)

                tipoJoin = str(rel.get("tipoJoin", "LEFT")).upper()
                tipoJoinSql = {
                    "LEFT": "LEFT JOIN",
                    "INNER": "INNER JOIN",
                    "FULL": "FULL OUTER JOIN"
                }.get(tipoJoin, "LEFT JOIN")

                conds = rel.get("condiciones", [])
                if not conds and rel.get("claveHechos") and rel.get("claveDimension"):
                    conds = [{"claveHechos": rel["claveHechos"], "claveDimension": rel["claveDimension"]}]

                if conds:
                    clausulaOn = " AND ".join([
                        f'h."{c["claveHechos"]}" = {aliasDim}."{c["claveDimension"]}"'
                        for c in conds
                    ])
                    joinsSql.append(f"{tipoJoinSql} {aliasDim} ON {clausulaOn}")

            # Construir proyecciones SELECT
            proyeccionesSelect = []
            nombresFinalesUsados = set()

            if columnasMapeadas:
                for col in columnasMapeadas:
                    clasif = col.get("clasificacionSemantica", "Categorica/Dimension")
                    if clasif == "Identificador/Descarte" or not col.get("esObligatoria", True):
                        continue

                    origen = str(col.get("origen", "HECHOS")).strip()
                    nombreOriginal = col.get("nombreOriginal")
                    nombreFinal = col.get("nombreFinal") or nombreOriginal

                    if nombreFinal in nombresFinalesUsados:
                        nombreFinal = f"{origen.lower()}_{nombreFinal}"

                    nombresFinalesUsados.add(nombreFinal)

                    if origen.upper() in ["HECHOS", "FACT", "A"]:
                        aliasPrefijo = "h"
                    else:
                        aliasPrefijo = mapaAliasDim.get(origen, "h")

                    proyeccionesSelect.append(f'{aliasPrefijo}."{nombreOriginal}" AS "{nombreFinal}"')
            else:
                # Si no se envió mapeo explícito, proyectar todas las de hechos + dimensiones sin colisión
                for colH in dfHechos.columns:
                    proyeccionesSelect.append(f'h."{colH}" AS "{colH}"')
                    nombresFinalesUsados.add(colH)

                for nomDim, aliasDim in mapaAliasDim.items():
                    dfDim = mapaDimensiones[nomDim]
                    for colD in dfDim.columns:
                        nomFinal = colD
                        if nomFinal in nombresFinalesUsados:
                            nomFinal = f"{nomDim}_{colD}"
                        nombresFinalesUsados.add(nomFinal)
                        proyeccionesSelect.append(f'{aliasDim}."{colD}" AS "{nomFinal}"')

            selectClausula = ",\n    ".join(proyeccionesSelect)
            joinsClausula = "\n".join(joinsSql)

            sentenciaSql = f"""
            COPY (
                SELECT
                    {selectClausula}
                FROM tabla_hechos h
                {joinsClausula}
            ) TO '{rutaSqlDestino}' (FORMAT PARQUET, COMPRESSION ZSTD);
            """

            if os.path.exists(rutaDestinoParquet):
                os.remove(rutaDestinoParquet)

            conexion.execute(sentenciaSql)
            filasGeneradas = int(conexion.execute(f"SELECT COUNT(*) FROM read_parquet('{rutaSqlDestino}')").fetchone()[0])

            return {
                "exito": True,
                "rutaParquet": rutaDestinoParquet,
                "totalFilasGeneradas": filasGeneradas,
                "totalColumnas": len(proyeccionesSelect)
            }
        finally:
            conexion.close()

