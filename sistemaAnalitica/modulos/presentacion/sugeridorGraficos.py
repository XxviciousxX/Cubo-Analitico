"""
Módulo de Sugerencia Semántica de Gráficos Plotly.
Evalúa compatibilidad de dimensiones y métricas analizando cardinalidad y tipos de datos en DuckDB.
"""

import duckdb
from typing import Dict, Any, List, Optional
import os


class SugeridorGraficos:
    """
    Motor semántico que inspecciona metadatos y cardinalidades de datasets Parquet
    en DuckDB para sugerir visualizaciones analíticas óptimas y descartar incompatibles.
    """

    TIPOS_GRAFICOS_DISPONIBLES = [
        {"id": "pie", "nombre": "Gráfico Circular", "icono": "pie_chart"},
        {"id": "bar", "nombre": "Gráfico de Barras", "icono": "bar_chart"},
        {"id": "line", "nombre": "Gráfico de Líneas", "icono": "show_chart"},
        {"id": "area", "nombre": "Gráfico de Área", "icono": "area_chart"},
        {"id": "treemap", "nombre": "Mapa de Árbol (Treemap)", "icono": "grid_view"},
        {"id": "scatter", "nombre": "Dispersión (Scatter)", "icono": "scatter_plot"}
    ]

    @classmethod
    def evaluarCompatibilidadGraficos(
        cls,
        rutaParquet: str,
        dimensionPrincipal: Optional[str] = None,
        metricaPrincipal: Optional[str] = None,
        dimensionesAdicionales: Optional[List[str]] = None,
        metricaSecundaria: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evalúa y categoriza qué gráficos son recomendados, tolerados o descartados.

        Reglas semánticas:
        - Pie: Cardinalidad de dimensión principal <= 7. Si > 7, descartado por sobrecarga visual.
        - Bar: Ideal para dimensiones categóricas o cardinalidad moderada (<= 60).
        - Line / Area: Exige dimensión de naturaleza temporal o secuencial (DATE, TIMESTAMP, o nombres tipo fecha/anio/mes).
        - Treemap: Diseñado para jerarquías (dimensión principal + al menos 1 dimensión adicional).
        - Scatter: Requiere 2 métricas continuas (metricaPrincipal + metricaSecundaria).
        """
        if not os.path.exists(rutaParquet):
            return {
                "recomendados": [],
                "descartados": [{"tipo": "todos", "motivo": f"Archivo Parquet no encontrado en {rutaParquet}"}],
                "cardinalidades": {},
                "escalaTemporal": False
            }

        rutaSql = rutaParquet.replace("\\", "/")
        cardinalidades: Dict[str, int] = {}
        tiposColumnas: Dict[str, str] = {}
        escalaTemporal = False

        conexion = duckdb.connect()
        try:
            # Inspeccionar tipos de datos del parquet
            esquema = conexion.execute(f"DESCRIBE SELECT * FROM read_parquet('{rutaSql}') LIMIT 1").fetchall()
            for col in esquema:
                colNombre = col[0]
                colTipo = str(col[1]).upper()
                tiposColumnas[colNombre] = colTipo

            # Si hay dimensión principal, calcular cardinalidad exacta
            if dimensionPrincipal and dimensionPrincipal in tiposColumnas:
                resCard = conexion.execute(
                    f'SELECT COUNT(DISTINCT "{dimensionPrincipal}") FROM read_parquet(\'{rutaSql}\')'
                ).fetchone()
                cardinalidades[dimensionPrincipal] = int(resCard[0]) if resCard else 0

                tipoDim = tiposColumnas[dimensionPrincipal]
                nombreLower = dimensionPrincipal.lower()
                escalaTemporal = any(t in tipoDim for t in ["DATE", "TIME", "TIMESTAMP"]) or any(
                    palabra in nombreLower for palabra in ["fecha", "date", "año", "anio", "mes", "periodo", "dia"]
                )

            # Cardinalidad para dimensiones adicionales
            if dimensionesAdicionales:
                for dimExtra in dimensionesAdicionales:
                    if dimExtra in tiposColumnas:
                        resCardExtra = conexion.execute(
                            f'SELECT COUNT(DISTINCT "{dimExtra}") FROM read_parquet(\'{rutaSql}\')'
                        ).fetchone()
                        cardinalidades[dimExtra] = int(resCardExtra[0]) if resCardExtra else 0

        except Exception as errorDuckdb:
            return {
                "recomendados": [],
                "descartados": [{"tipo": "general", "motivo": f"Error evaluando dataset: {str(errorDuckdb)}"}],
                "cardinalidades": {},
                "escalaTemporal": False
            }
        finally:
            conexion.close()

        recomendados = []
        descartados = []

        cardinalidadDim = cardinalidades.get(dimensionPrincipal, 0) if dimensionPrincipal else 0

        # 1. Regla PIE
        if not dimensionPrincipal or not metricaPrincipal:
            descartados.append({
                "tipo": "pie",
                "nombre": "Gráfico Circular (Torta)",
                "motivo": "Requiere seleccionar al menos una dimensión y una métrica."
            })
        elif cardinalidadDim <= 7:
            recomendados.append({
                "tipo": "pie",
                "nombre": "Gráfico Circular (Torta)",
                "puntuacion": 95 if cardinalidadDim <= 5 else 80,
                "motivo": f"Cardinalidad óptima ({cardinalidadDim} elementos únicos, ≤ 7). Permite lectura limpia de proporciones."
            })
        else:
            descartados.append({
                "tipo": "pie",
                "nombre": "Gráfico Circular (Torta)",
                "motivo": f"Cardinalidad alta ({cardinalidadDim} elementos únicos > 7). Provoca saturación visual e ilegibilidad."
            })

        # 2. Regla BAR
        if not dimensionPrincipal or not metricaPrincipal:
            descartados.append({
                "tipo": "bar",
                "nombre": "Gráfico de Barras",
                "motivo": "Requiere una dimensión y una métrica numérica."
            })
        elif cardinalidadDim <= 60:
            recomendados.append({
                "tipo": "bar",
                "nombre": "Gráfico de Barras",
                "puntuacion": 90,
                "motivo": f"Excelente para comparar valores entre las {cardinalidadDim} categorías observadas."
            })
        else:
            recomendados.append({
                "tipo": "bar",
                "nombre": "Gráfico de Barras",
                "puntuacion": 65,
                "motivo": f"Admite las {cardinalidadDim} categorías pero se recomienda limitar o filtrar los primeros N resultados."
            })

        # 3. Regla LINE / AREA
        if not dimensionPrincipal or not metricaPrincipal:
            descartados.append({
                "tipo": "line",
                "nombre": "Gráfico de Líneas",
                "motivo": "Requiere una dimensión y una métrica."
            })
            descartados.append({
                "tipo": "area",
                "nombre": "Gráfico de Área",
                "motivo": "Requiere una dimensión y una métrica."
            })
        elif escalaTemporal:
            recomendados.append({
                "tipo": "line",
                "nombre": "Gráfico de Líneas",
                "puntuacion": 98,
                "motivo": f"Dimensión temporal detectada ('{dimensionPrincipal}'). Óptimo para series de tiempo y tendencias continuas."
            })
            recomendados.append({
                "tipo": "area",
                "nombre": "Gráfico de Área",
                "puntuacion": 90,
                "motivo": "Ideal para evidenciar volumen acumulado a lo largo del tiempo."
            })
        else:
            descartados.append({
                "tipo": "line",
                "nombre": "Gráfico de Líneas",
                "motivo": f"La dimensión '{dimensionPrincipal}' no es de naturaleza cronológica o secuencial."
            })
            descartados.append({
                "tipo": "area",
                "nombre": "Gráfico de Área",
                "motivo": f"El gráfico de área requiere un eje temporal para no distorsionar comparaciones categóricas."
            })

        # 4. Regla TREEMAP
        cantDims = (1 if dimensionPrincipal else 0) + (len(dimensionesAdicionales) if dimensionesAdicionales else 0)
        if cantDims >= 2 and metricaPrincipal:
            recomendados.append({
                "tipo": "treemap",
                "nombre": "Mapa de Árbol (Treemap)",
                "puntuacion": 92,
                "motivo": f"Estructura jerárquica detectada con {cantDims} niveles dimensionales para desglose anidado."
            })
        else:
            descartados.append({
                "tipo": "treemap",
                "nombre": "Mapa de Árbol (Treemap)",
                "motivo": "Requiere al menos 2 dimensiones anidadas (jerarquía de desglose) y 1 métrica numérica."
            })

        # 5. Regla SCATTER
        if metricaPrincipal and metricaSecundaria and metricaPrincipal != metricaSecundaria:
            recomendados.append({
                "tipo": "scatter",
                "nombre": "Dispersión (Scatter)",
                "puntuacion": 85,
                "motivo": f"Permite evaluar correlación entre métricas '{metricaPrincipal}' y '{metricaSecundaria}' agrupadas por '{dimensionPrincipal}'."
            })
        else:
            descartados.append({
                "tipo": "scatter",
                "nombre": "Dispersión (Scatter)",
                "motivo": "Requiere 2 métricas numéricas distintas (X e Y) para análisis de correlación."
            })

        # Ordenar recomendados por puntuación descendente
        recomendados.sort(key=lambda x: x.get("puntuacion", 0), reverse=True)

        return {
            "recomendados": recomendados,
            "descartados": descartados,
            "cardinalidades": cardinalidades,
            "escalaTemporal": escalaTemporal,
            "sugeridoPrincipal": recomendados[0]["tipo"] if recomendados else "bar"
        }
