"""
Módulo de Exploración de Cubos, Reportes Gráficos y Drill-Down Interactivo.
Permite visualizar la información de los cubos analíticos en gráficos de torta/dona,
barras, líneas, tarjetas KPI y navegación jerárquica de lo macro a lo micro.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import VistaModelo
from sistemaAnalitica.modulos.motorAnalitico.servicioDuckDb import ServicioDuckDb
from sistemaAnalitica.modulos.ingesta.gestorSqlEnVivo import GestorSqlEnVivo
from sistemaAnalitica.modulos.ingesta.generadorOBT import GeneradorOBT
from sistemaAnalitica.modulos.ingesta.calamineLector import CalamineLectorExcel
from sistemaAnalitica.modulos.ingesta.validadorContratos import ValidadorContratos
from sistemaAnalitica.modulos.presentacion.estilos import (
    COLOR_PRIMARIO, COLOR_PRIMARIO_CONTENEDOR, COLOR_SECUNDARIO,
    COLOR_FONDO, COLOR_SUPERFICIE, COLOR_BORDE, COLOR_TEXTO_PRINCIPAL
)

# Paleta armónica corporativa basada en las directrices de Knowledge Base
PALETA_GRAFICOS = [
    "#004482",  # Azul corporativo primario
    "#006e20",  # Verde esmeralda secundario
    "#005cab",  # Azul contenedor
    "#204475",  # Azul terciario
    "#3a5c8e",  # Azul medio
    "#6dde73",  # Verde claro
    "#a6c8ff",  # Azul pastel
    "#e8f5e9",  # Verde fondo sutil
    "#c1c6d3"   # Neutro contorno
]


def renderizarExploradorVistas(usuarioActual: Dict[str, Any]) -> None:
    """
    Punto de entrada para la visualización y análisis interactivo de cubos analíticos.
    """
    st.markdown(
        f"""
        <div style="margin-bottom: 1.2rem;">
            <h2 style="margin: 0; color: {COLOR_PRIMARIO}; font-size: 1.8rem;">
                Explorador de Cubos y Reportes Analíticos
            </h2>
            <p style="color: #414751; font-size: 0.95rem; margin-top: 0.2rem;">
                Visualización interactiva, análisis de distribución (torta), comparativas y navegación drill-down de alto rendimiento.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 1. Obtener catálogo de vistas activas disponibles
    with obtenerSesion() as sesion:
        vistasDisponibles = sesion.query(VistaModelo).filter_by(activo=True).all()
        listaVistas = [
            {
                "idVista": v.idVista,
                "codigoVista": v.codigoVista,
                "nombreVista": v.nombreVista,
                "tipoIngesta": v.tipoIngesta,
                "rutaArchivoParquet": v.rutaArchivoParquet,
                "contratoEsquemaJson": v.contratoEsquemaJson,
                "fechaUltimaEjecucion": v.fechaUltimaEjecucion
            }
            for v in vistasDisponibles
        ]

    if not listaVistas:
        st.warning("No hay cubos ni vistas analíticas registradas en el catálogo. Por favor crea uno en la pestaña de Ingesta.")
        return

    # Selector de Cubo
    opcionesVistas = {f"{v['nombreVista']} ({v['codigoVista']})": v for v in listaVistas}
    nombresOpciones = list(opcionesVistas.keys())

    colSel, colEspacio = st.columns([3, 1])
    with colSel:
        nombreSeleccionado = st.selectbox(
            "Seleccionar Cubo Analítico:",
            options=nombresOpciones,
            index=0
        )

    vistaSeleccionada = opcionesVistas[nombreSeleccionado]
    rutaParquet = vistaSeleccionada["rutaArchivoParquet"]

    # Validación de existencia del archivo Parquet
    if not rutaParquet or not os.path.exists(rutaParquet):
        st.error(f"El archivo Parquet del cubo `{vistaSeleccionada['codigoVista']}` no fue encontrado en `{rutaParquet}`.")
        return

    # 2. Manejo de modalidades operativas específicas
    tipoIngesta = vistaSeleccionada["tipoIngesta"]
    if tipoIngesta == "ExcelModalidadB":
        renderizarControlModalidadB(vistaSeleccionada)
    elif tipoIngesta == "SqlEnVivo":
        renderizarControlSqlEnVivo(vistaSeleccionada)

    # 3. Inspección del Cubo con DuckDB
    try:
        resumenCubo = ServicioDuckDb.obtenerResumenCubo(rutaParquet)
    except Exception as errorDuck:
        st.error(f"Error accediendo a los datos con DuckDB: {str(errorDuck)}")
        return

    # Identificar Dimensiones y Métricas
    columnasInfo = resumenCubo["columnas"]
    todasColumnas = [c["nombreColumna"] for c in columnasInfo]

    # Clasificación por tipos de DuckDB y contrato
    dimensionesCandidatas = []
    metricasSumables = []
    metricasPromedio = []

    contratoJson = None
    if vistaSeleccionada.get("contratoEsquemaJson"):
        try:
            contratoJson = json.loads(vistaSeleccionada["contratoEsquemaJson"])
        except Exception:
            contratoJson = None

    if contratoJson and "columnas" in contratoJson:
        for c in contratoJson["columnas"]:
            nom = c.get("nombreColumna")
            clasif = c.get("clasificacionSemantica")
            if nom in todasColumnas:
                if clasif == "Categorica/Dimension":
                    dimensionesCandidatas.append(nom)
                elif clasif == "MetricaSumable":
                    metricasSumables.append(nom)
                elif clasif == "MetricaNoSumable":
                    metricasPromedio.append(nom)
    else:
        # Inferencia por tipo de datos
        for c in columnasInfo:
            tipo = c["tipoDato"].upper()
            nom = c["nombreColumna"]
            if "INT" in tipo or "DOUBLE" in tipo or "FLOAT" in tipo or "DECIMAL" in tipo:
                metricasSumables.append(nom)
            else:
                dimensionesCandidatas.append(nom)

    # Fallback si no hay métricas sumables
    if not metricasSumables and not metricasPromedio:
        metricasSumables = [c["nombreColumna"] for c in columnasInfo if "INT" in c["tipoDato"].upper()]

    # 4. Inicializar estado de Drill-Down y filtros en sesión
    claveEstadoFiltros = f"filtrosDrillDown_{vistaSeleccionada['codigoVista']}"
    if claveEstadoFiltros not in st.session_state:
        st.session_state[claveEstadoFiltros] = []

    # 5. Tarjetas KPI Superiores
    renderizarTarjetasKpi(rutaParquet, resumenCubo["totalFilas"], metricasSumables, metricasPromedio)

    # 6. Panel de Navegación y Filtros Drill-Down
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown("#### 🧭 Navegación Jerárquica y Drill-Down")

    filtrosActivos = st.session_state[claveEstadoFiltros]

    colMigas, colBotonReset = st.columns([4, 1])
    with colMigas:
        if not filtrosActivos:
            st.markdown("📍 **Nivel de Navegación:** `Inicio (Visión General Macro)`")
        else:
            migasTexto = "📍 **Nivel de Navegación:** `Inicio`"
            for f in filtrosActivos:
                migasTexto += f" ➔ `{f['dimension']}: {f['valor']}`"
            st.markdown(migasTexto)

    with colBotonReset:
        if st.button("🔄 Restablecer a Macro", use_container_width=True, help="Limpia todos los filtros de profundización"):
            st.session_state[claveEstadoFiltros] = []
            st.rerun()

    # Construir cláusula WHERE acumulada de filtros drill-down
    listaClausulasWhere = []
    for f in filtrosActivos:
        valEscapado = str(f["valor"]).replace("'", "''")
        listaClausulasWhere.append(f'"{f["dimension"]}" = \'{valEscapado}\'')

    # Configuración de dimensiones y métricas para visualizaciones
    colDim, colMet, colTipoGrafico = st.columns(3)

    # Filtrar dimensiones disponibles (excluyendo las que ya están fijas en el drill-down)
    dimensionesFiltroAplicadas = [f["dimension"] for f in filtrosActivos]
    dimensionesRestantes = [d for d in dimensionesCandidatas if d not in dimensionesFiltroAplicadas]
    if not dimensionesRestantes:
        dimensionesRestantes = dimensionesCandidatas

    with colDim:
        dimensionPrimaria = st.selectbox(
            "Dimensión Principal de Análisis:",
            options=dimensionesRestantes,
            index=0 if dimensionesRestantes else None,
            help="Atributo para agrupar los datos en los gráficos."
        )

    with colMet:
        opcionesMetricas = metricasSumables + metricasPromedio
        metricaPrimaria = st.selectbox(
            "Métrica a Evaluar:",
            options=opcionesMetricas,
            index=0 if opcionesMetricas else None
        )

    with colTipoGrafico:
        tipoGrafico = st.selectbox(
            "Tipo de Gráfico Principal:",
            options=["Gráfico de Torta / Donut", "Gráfico de Barras", "Líneas de Tendencia", "Tabla Detallada"]
        )

    st.markdown("---")

    # 7. Ejecutar Consulta Agregada en DuckDB con filtros aplicados
    esMetricaSumable = metricaPrimaria in metricasSumables
    listaSumables = [metricaPrimaria] if esMetricaSumable else []
    listaPromedio = [metricaPrimaria] if not esMetricaSumable else []

    columnaMetricaCalculada = f"{metricaPrimaria}_Total" if esMetricaSumable else f"{metricaPrimaria}_Promedio"

    try:
        dataframeAgregado = ServicioDuckDb.ejecutarConsultaOlap(
            rutaArchivoParquet=rutaParquet,
            dimensiones=[dimensionPrimaria] if dimensionPrimaria else None,
            metricasSumables=listaSumables,
            metricasPromedio=listaPromedio,
            filtrosWhere=listaClausulasWhere if listaClausulasWhere else None,
            columnaOrden=columnaMetricaCalculada,
            ordenAscendente=False,
            limiteFilas=500
        )
    except Exception as errConsulta:
        st.error(f"Error calculando agregación OLAP: {str(errConsulta)}")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    if dataframeAgregado.empty:
        st.info("No se encontraron registros que coincidan con los filtros seleccionados.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    # 8. Renderizado del Gráfico Seleccionado y Gráficos Complementarios
    if tipoGrafico == "Gráfico de Torta / Donut":
        renderizarGraficoTortaDona(dataframeAgregado, dimensionPrimaria, columnaMetricaCalculada, metricaPrimaria)
    elif tipoGrafico == "Gráfico de Barras":
        renderizarGraficoBarras(dataframeAgregado, dimensionPrimaria, columnaMetricaCalculada, metricaPrimaria)
    elif tipoGrafico == "Líneas de Tendencia":
        renderizarGraficoLineas(dataframeAgregado, dimensionPrimaria, columnaMetricaCalculada, metricaPrimaria)
    else:
        renderizarTablaAnalitica(dataframeAgregado, dimensionPrimaria, columnaMetricaCalculada)

    # 9. Selector Interactivo para Profundizar (Drill-Down)
    st.markdown("---")
    st.markdown("#### 🔍 Profundizar en un Segmento Específico (Drill-Down)")

    colSelVal, colBotonProfundizar = st.columns([3, 1])
    with colSelVal:
        valoresDisponibles = dataframeAgregado[dimensionPrimaria].dropna().astype(str).tolist()
        valorSeleccionado = st.selectbox(
            f"Selecciona un valor de '{dimensionPrimaria}' para profundizar:",
            options=valoresDisponibles
        )

    with colBotonProfundizar:
        st.write("&nbsp;")
        if st.button("🔽 Profundizar", use_container_width=True, key="btnProfundizar"):
            st.session_state[claveEstadoFiltros].append({
                "dimension": dimensionPrimaria,
                "valor": valorSeleccionado
            })
            st.rerun()

    # 10. Despliegue simultáneo de Torta y Barras para Análisis Integral
    st.markdown("---")
    st.markdown("#### 📊 Distribución y Comparativa Simultánea")
    colTorta, colBarras = st.columns(2)

    with colTorta:
        st.caption(f"Distribución porcentual de {metricaPrimaria} por {dimensionPrimaria}")
        figTorta = px.pie(
            dataframeAgregado,
            names=dimensionPrimaria,
            values=columnaMetricaCalculada,
            hole=0.45,
            color_discrete_sequence=PALETA_GRAFICOS
        )
        figTorta.update_traces(textposition='inside', textinfo='percent+label')
        figTorta.update_layout(
            margin=dict(t=20, b=20, l=10, r=10),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
        )
        st.plotly_chart(figTorta, use_container_width=True)

    with colBarras:
        st.caption(f"Comparativa cuantitativa de {metricaPrimaria}")
        figBarras = px.bar(
            dataframeAgregado,
            x=dimensionPrimaria,
            y=columnaMetricaCalculada,
            text=columnaMetricaCalculada,
            color_discrete_sequence=[COLOR_PRIMARIO]
        )
        figBarras.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
        figBarras.update_layout(
            margin=dict(t=20, b=20, l=10, r=10),
            xaxis_title=dimensionPrimaria,
            yaxis_title=metricaPrimaria,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(figBarras, use_container_width=True)

    # 11. Tabla de datos agregados con opción de exportación CSV
    st.markdown("---")
    st.markdown("#### 📋 Matriz de Datos Agregados")
    st.dataframe(dataframeAgregado, use_container_width=True)

    csvDatos = dataframeAgregado.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Descargar Reporte en CSV",
        data=csvDatos,
        file_name=f"reporte_{vistaSeleccionada['codigoVista']}_{dimensionPrimaria}.csv",
        mime="text/csv",
        key="btnDescargarCsv"
    )

    st.markdown('</div>', unsafe_allow_html=True)


def renderizarTarjetasKpi(
    rutaParquet: str,
    totalFilas: int,
    metricasSumables: List[str],
    metricasPromedio: List[str]
) -> None:
    """
    Despliega indicadores de alto impacto visual con valores globales calculados en DuckDB.
    """
    colKpi1, colKpi2, colKpi3, colKpi4 = st.columns(4)

    with colKpi1:
        st.metric(
            label="Total Registros en Cubo",
            value=f"{totalFilas:,}"
        )

    # Calcular suma de primera métrica
    with colKpi2:
        if metricasSumables:
            primeraMetrica = metricasSumables[0]
            try:
                dfSuma = ServicioDuckDb.ejecutarConsultaOlap(
                    rutaArchivoParquet=rutaParquet,
                    metricasSumables=[primeraMetrica]
                )
                valorTotal = float(dfSuma[f"{primeraMetrica}_Total"].iloc[0])
                st.metric(
                    label=f"Suma Total ({primeraMetrica})",
                    value=f"${valorTotal:,.0f}" if valorTotal > 1000 else f"{valorTotal:,.2f}"
                )
            except Exception:
                st.metric(label=f"Métrica: {primeraMetrica}", value="N/A")
        else:
            st.metric(label="Métrica Sumable", value="Sin métricas")

    # Segunda métrica sumable si existe
    with colKpi3:
        if len(metricasSumables) > 1:
            segundaMetrica = metricasSumables[1]
            try:
                dfSuma2 = ServicioDuckDb.ejecutarConsultaOlap(
                    rutaArchivoParquet=rutaParquet,
                    metricasSumables=[segundaMetrica]
                )
                valorTotal2 = float(dfSuma2[f"{segundaMetrica}_Total"].iloc[0])
                st.metric(
                    label=f"Suma Total ({segundaMetrica})",
                    value=f"${valorTotal2:,.0f}" if valorTotal2 > 1000 else f"{valorTotal2:,.2f}"
                )
            except Exception:
                st.metric(label=f"Métrica: {segundaMetrica}", value="N/A")
        elif metricasPromedio:
            metProm = metricasPromedio[0]
            try:
                dfProm = ServicioDuckDb.ejecutarConsultaOlap(
                    rutaArchivoParquet=rutaParquet,
                    metricasPromedio=[metProm]
                )
                valProm = float(dfProm[f"{metProm}_Promedio"].iloc[0])
                st.metric(label=f"Promedio ({metProm})", value=f"{valProm:.2%}" if valProm < 1.0 else f"{valProm:,.2f}")
            except Exception:
                st.metric(label=f"Promedio: {metProm}", value="N/A")
        else:
            st.metric(label="Métrica 2", value="N/A")

    # Métrica promedio o ratio
    with colKpi4:
        if metricasPromedio:
            metProm = metricasPromedio[0]
            try:
                dfProm = ServicioDuckDb.ejecutarConsultaOlap(
                    rutaArchivoParquet=rutaParquet,
                    metricasPromedio=[metProm]
                )
                valProm = float(dfProm[f"{metProm}_Promedio"].iloc[0])
                st.metric(label=f"Índice / Margen Promedio", value=f"{valProm:.1%}" if valProm < 1.0 else f"{valProm:,.2f}")
            except Exception:
                st.metric(label="Ratio Analítico", value="N/A")
        else:
            st.metric(label="Estado del Cubo", value="En Línea (DuckDB)")


def renderizarGraficoTortaDona(
    df: pd.DataFrame,
    dimension: str,
    columnaMetrica: str,
    etiquetaMetrica: str
) -> None:
    """
    Construye un gráfico interactivo tipo dona con estilo corporativo.
    """
    st.markdown(f"#### 🍩 Gráfico de Torta / Dona: {etiquetaMetrica} por {dimension}")
    fig = px.pie(
        df,
        names=dimension,
        values=columnaMetrica,
        hole=0.50,
        color_discrete_sequence=PALETA_GRAFICOS
    )
    fig.update_traces(
        textposition='inside',
        textinfo='percent+label',
        hoverinfo='label+percent+value',
        marker=dict(line=dict(color='#ffffff', width=2))
    )
    fig.update_layout(
        margin=dict(t=30, b=30, l=20, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    st.plotly_chart(fig, use_container_width=True)


def renderizarGraficoBarras(
    df: pd.DataFrame,
    dimension: str,
    columnaMetrica: str,
    etiquetaMetrica: str
) -> None:
    """
    Construye un gráfico de barras estilizado con la paleta de Knowledge Base.
    """
    st.markdown(f"#### 📊 Gráfico de Barras: Comparativa de {etiquetaMetrica}")
    fig = px.bar(
        df,
        x=dimension,
        y=columnaMetrica,
        text=columnaMetrica,
        color_discrete_sequence=[COLOR_PRIMARIO]
    )
    fig.update_traces(
        texttemplate='%{text:,.0f}',
        textposition='outside',
        marker=dict(line=dict(color=COLOR_PRIMARIO_CONTENEDOR, width=1))
    )
    fig.update_layout(
        margin=dict(t=30, b=30, l=20, r=20),
        xaxis_title=dimension,
        yaxis_title=etiquetaMetrica,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    st.plotly_chart(fig, use_container_width=True)


def renderizarGraficoLineas(
    df: pd.DataFrame,
    dimension: str,
    columnaMetrica: str,
    etiquetaMetrica: str
) -> None:
    """
    Construye un gráfico de líneas para evolución temporal.
    """
    st.markdown(f"#### 📈 Tendencia y Evolución: {etiquetaMetrica}")
    fig = px.line(
        df,
        x=dimension,
        y=columnaMetrica,
        markers=True,
        color_discrete_sequence=[COLOR_PRIMARIO]
    )
    fig.update_traces(
        line=dict(width=3),
        marker=dict(size=8, color=COLOR_SECUNDARIO)
    )
    fig.update_layout(
        margin=dict(t=30, b=30, l=20, r=20),
        xaxis_title=dimension,
        yaxis_title=etiquetaMetrica,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    st.plotly_chart(fig, use_container_width=True)


def renderizarTablaAnalitica(
    df: pd.DataFrame,
    dimension: str,
    columnaMetrica: str
) -> None:
    """
    Despliega tabla agregada formateada.
    """
    st.markdown(f"#### 📋 Tabla Resumen Agregada")
    st.dataframe(df, use_container_width=True)


def renderizarControlModalidadB(vista: Dict[str, Any]) -> None:
    """
    Para vistas Excel Modalidad B: requiere carga obligatoria y valida contrato.
    """
    with st.expander("📥 Actualización de Datos (Modalidad B - Archivo Requerido)", expanded=False):
        st.info("Esta vista requiere subir el archivo Excel actualizado para purgar y refrescar los datos.")
        nuevoArchivo = st.file_uploader(
            "Cargar Excel actualizado (.xlsx):",
            type=["xlsx"],
            key=f"uploaderModB_{vista['codigoVista']}"
        )
        if nuevoArchivo:
            if st.button("Validar Contrato y Actualizar Vista", key=f"btnProcModB_{vista['codigoVista']}"):
                bytesArchivo = nuevoArchivo.read()
                # Leer hoja
                hojas = CalamineLectorExcel.obtenerHojasLibro(bytesArchivo)
                dfNuevo = CalamineLectorExcel.convertirHojaADataFrame(bytesArchivo, hojas[0])

                if vista.get("contratoEsquemaJson"):
                    contrato = json.loads(vista["contratoEsquemaJson"])
                    validacion = ValidadorContratos.validarEsquema(dfNuevo, contrato)
                    if not validacion.esValido:
                        st.error("Error en validación de contrato:")
                        for err in validacion.errores:
                            st.write(f"- ❌ {err}")
                        return

                # Purgar y reescribir Parquet
                GeneradorOBT.purgarArchivoParquet(vista["rutaArchivoParquet"])
                GeneradorOBT.guardarEnParquet(dfNuevo, vista["rutaArchivoParquet"])
                st.success("Datos actualizados correctamente.")
                st.rerun()


def renderizarControlSqlEnVivo(vista: Dict[str, Any]) -> None:
    """
    Para vistas SQL en Vivo: botón con Throttling de 5 minutos.
    """
    puedeEjecutar, segsRestantes, msg = GestorSqlEnVivo.verificarThrottling(vista["idVista"])

    with st.container():
        colBtn, colInfo = st.columns([2, 4])
        with colBtn:
            if puedeEjecutar:
                if st.button("🚀 Actualizar Datos en Vivo", key=f"btnRefrescoSql_{vista['idVista']}"):
                    exito, mensaje, _ = GestorSqlEnVivo.ejecutarYMaterializarParquet(
                        vista["idVista"],
                        vista["rutaArchivoParquet"]
                    )
                    if exito:
                        st.success(mensaje)
                        st.rerun()
                    else:
                        st.error(mensaje)
            else:
                st.button("🔒 Actualizar Datos (Bloqueado)", disabled=True, key=f"btnLockSql_{vista['idVista']}")

        with colInfo:
            if not puedeEjecutar:
                minutos = segsRestantes // 60
                segundos = segsRestantes % 60
                st.warning(f"⏳ Throttling activo. Próxima actualización en: **{minutos:02d}:{segundos:02d}**")
            else:
                st.caption("Conexión activa. Listo para ejecutar actualización bajo demanda.")
