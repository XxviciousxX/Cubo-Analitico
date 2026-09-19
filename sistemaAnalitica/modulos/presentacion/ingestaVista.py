"""
Vista interactiva para la ingesta de datos, perfilado de metadatos y generación de cubos Parquet.
Soporta Flujo 1 (Excel Calamine Modalidades A y B), Flujo 2 (SQL en vivo con Throttling) y Flujo 3 (Data Lake).
"""

import os
import io
import json
from datetime import datetime
from typing import Dict, Any, List
import streamlit as st
import pandas as pd

from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import VistaModelo, ConexionBaseDatosModelo
from sistemaAnalitica.modulos.ingesta.calamineLector import CalamineLectorExcel
from sistemaAnalitica.modulos.ingesta.validadorContratos import ValidadorContratos, ResultadoValidacion
from sistemaAnalitica.modulos.ingesta.generadorOBT import GeneradorOBT
from sistemaAnalitica.modulos.ingesta.gestorSqlEnVivo import GestorSqlEnVivo
from sistemaAnalitica.modulos.motorAnalitico.servicioDuckDb import ServicioDuckDb
from sistemaAnalitica.modulos.presentacion.estilos import (
    COLOR_PRIMARIO, COLOR_SECUNDARIO, COLOR_ERROR
)


def generarExcelEjemploVentas() -> bytes:
    """
    Crea en memoria un archivo Excel de demostración con múltiples hojas para pruebas rápidas.
    """
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as escritor:
        dfVentas = pd.DataFrame({
            "idVenta": [1001, 1002, 1003, 1004, 1005, 1006],
            "idSucursal": [10, 20, 10, 30, 20, 10],
            "fecha": pd.date_range("2026-02-01", periods=6, freq="D").astype(str),
            "montoVenta": [450000.0, 890000.5, 320000.0, 1200000.0, 670000.0, 510000.0],
            "costoTotal": [310000.0, 580000.0, 210000.0, 800000.0, 420000.0, 330000.0],
            "margenPct": [0.31, 0.35, 0.34, 0.33, 0.37, 0.35],
            "auditoriaFila": ["OK", "OK", "VERIFICADO", "OK", "OK", "VERIFICADO"]
        })
        dfVentas.to_excel(escritor, sheet_name="Ventas", index=False)

        dfSucursales = pd.DataFrame({
            "idSucursal": [10, 20, 30],
            "nombreSucursal": ["Casa Matriz", "Sucursal Providencia", "Sucursal Concepción"],
            "region": ["Metropolitana", "Metropolitana", "Biobío"],
            "gerenteZona": ["Ana Torres", "Carlos Ruiz", "Elena Díaz"]
        })
        dfSucursales.to_excel(escritor, sheet_name="Sucursales", index=False)

    buffer.seek(0)
    return buffer.getvalue()


def renderizarVistaIngesta() -> None:
    """
    Punto de entrada para el módulo visual de gestión de ingesta y perfilado de cubos.
    """
    st.markdown(
        f"""
        <div style="margin-bottom: 1.2rem;">
            <h2 style="margin: 0; color: {COLOR_PRIMARIO}; font-size: 1.8rem;">
                Módulo de Ingesta, Perfilado y Modelado de Datos
            </h2>
            <p style="color: #414751; font-size: 0.95rem; margin-top: 0.2rem;">
                Configuración de orígenes de datos, contratos de esquema y generación de One Big Table (OBT) en Parquet.
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    pestanaExcel, pestanaSql, pestanaDataLake, pestanaCatalogo = st.tabs([
        "📥 Flujo 1: Carga por Excel (Calamine)",
        "⚡ Flujo 2: SQL en Vivo (Throttling 5m)",
        "🏛️ Flujo 3: Procesos Masivos (Data Lake)",
        "📋 Catálogo de Vistas y Cubos"
    ])

    with pestanaExcel:
        renderizarFlujoExcel()

    with pestanaSql:
        renderizarFlujoSqlEnVivo()

    with pestanaDataLake:
        renderizarFlujoDataLake()

    with pestanaCatalogo:
        renderizarCatalogoVistas()


def renderizarFlujoExcel() -> None:
    """
    Implementa el flujo interactivo de carga por archivo Excel con Calamine, JOINs y validación.
    """
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("Configurador de Ingesta Excel Multitabla")
    st.caption("Lectura acelerada con Calamine, uniones relacionales (JOIN) y persistencia OBT Parquet.")

    colSubida, colDemo = st.columns([3, 1])
    with colSubida:
        archivoSubido = st.file_uploader(
            "Selecciona un libro Excel (.xlsx)",
            type=["xlsx"],
            help="Sube un archivo de muestra para inferir el esquema y relaciones."
        )

    with colDemo:
        st.write("&nbsp;")
        if st.button("Usar Libro Demo", key="btnCargarDemoExcel", use_container_width=True):
            st.session_state["contenidoBytesExcel"] = generarExcelEjemploVentas()
            st.session_state["nombreArchivoExcel"] = "LibroDemo_Ventas.xlsx"
            st.success("Libro demo cargado exitosamente.")

    if archivoSubido:
        st.session_state["contenidoBytesExcel"] = archivoSubido.read()
        st.session_state["nombreArchivoExcel"] = archivoSubido.name

    bytesLibro = st.session_state.get("contenidoBytesExcel")
    if not bytesLibro:
        st.info("Por favor sube un archivo Excel o presiona 'Usar Libro Demo' para comenzar.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    # 1. Extracción de hojas con Calamine
    hojasDisponibles = CalamineLectorExcel.obtenerHojasLibro(bytesLibro)
    st.markdown(f"**Hojas detectadas en el libro:** `{', '.join(hojasDisponibles)}`")

    colConfig1, colConfig2, colConfig3 = st.columns([2, 2, 2])
    with colConfig1:
        codigoVista = st.text_input(
            "Código de la Vista / Cubo:",
            value="cuboVentasMensuales",
            help="Identificador único para el archivo Parquet y base de control."
        )
    with colConfig2:
        nombreVista = st.text_input(
            "Nombre descriptivo:",
            value="Cubo de Ventas y Rendimiento por Sucursal"
        )
    with colConfig3:
        modalidadOperativa = st.selectbox(
            "Modalidad Operativa:",
            options=["ExcelModalidadA", "ExcelModalidadB"],
            format_func=lambda m: (
                "Modalidad A: Histórico Acumulado (Lectura directa)"
                if m == "ExcelModalidadA"
                else "Modalidad B: Carga Obligatoria en Sesión (Purga y valida)"
            )
        )

    # 2. Selección de Hoja Principal y Configuración de JOINs
    st.markdown("---")
    st.markdown("#### 🔗 Modelo Relacional y Uniones entre Hojas (JOIN)")

    colHojaBase, colAgregarJoin = st.columns([2, 4])
    with colHojaBase:
        hojaPrincipal = st.selectbox(
            "Hoja Principal (Hechos / Transacciones):",
            options=hojasDisponibles,
            index=0
        )

    # Cargar DataFrames de muestra para inspeccionar columnas
    mapaDataframesCompletos = {}
    mapaColumnasPorHoja = {}
    for hoja in hojasDisponibles:
        dfHoja = CalamineLectorExcel.convertirHojaADataFrame(bytesLibro, hoja)
        mapaDataframesCompletos[hoja] = dfHoja
        mapaColumnasPorHoja[hoja] = list(dfHoja.columns)

    hojasSecundarias = [h for h in hojasDisponibles if h != hojaPrincipal]
    definicionJoins = []

    if hojasSecundarias:
        st.write("Configuración de relaciones con hojas secundarias (Dimensiones):")
        for idx, hojaSec in enumerate(hojasSecundarias):
            colJoin1, colJoin2, colJoin3, colJoin4 = st.columns(4)
            with colJoin1:
                st.markdown(f"**{hojaPrincipal}**")
                llaveIzquierda = st.selectbox(
                    f"Columna en {hojaPrincipal}:",
                    options=mapaColumnasPorHoja[hojaPrincipal],
                    key=f"llaveIzq_{idx}"
                )
            with colJoin2:
                tipoJoin = st.selectbox(
                    "Tipo de Unión:",
                    options=["left", "inner", "outer"],
                    index=0,
                    key=f"tipoJoin_{idx}"
                )
            with colJoin3:
                st.markdown(f"**{hojaSec}**")
                llaveDerecha = st.selectbox(
                    f"Columna en {hojaSec}:",
                    options=mapaColumnasPorHoja[hojaSec],
                    key=f"llaveDer_{idx}"
                )
            with colJoin4:
                aplicarRelacion = st.checkbox(
                    f"Unir {hojaSec}",
                    value=True,
                    key=f"chkJoin_{idx}"
                )

            if aplicarRelacion:
                definicionJoins.append({
                    "tablaSecundaria": hojaSec,
                    "llaveIzquierda": llaveIzquierda,
                    "llaveDerecha": llaveDerecha,
                    "tipoJoin": tipoJoin
                })

    # Construir tabla consolidada en memoria
    dataframeConsolidado = GeneradorOBT.construirTablaConsolidada(
        mapaDataframesCompletos,
        hojaPrincipal,
        definicionJoins
    )

    st.markdown("---")
    st.markdown("#### ⚙️ Clasificación Semántica y Contrato de Columnas")
    st.caption("Define el rol analítico de cada columna en el One Big Table (OBT).")

    perfilInicial = CalamineLectorExcel.perfiladorTiposColumna(dataframeConsolidado)
    configuracionColumnas = []

    columnasOpciones = [
        "Categorica/Dimension",
        "MetricaSumable",
        "MetricaNoSumable",
        "Identificador/Descarte"
    ]

    for colNombre in dataframeConsolidado.columns:
        sugerencia = perfilInicial.get(str(colNombre), {}).get("clasificacionSugerida", "Categorica/Dimension")
        tipoPrimitivo = perfilInicial.get(str(colNombre), {}).get("tipoDatoPrimitivo", "texto")

        c1, c2, c3, c4 = st.columns([2, 3, 2, 1])
        with c1:
            st.markdown(f"**`{colNombre}`** (`{tipoPrimitivo}`)")
        with c2:
            indiceDefecto = columnasOpciones.index(sugerencia) if sugerencia in columnasOpciones else 0
            clasificacionElegida = st.selectbox(
                f"Rol para {colNombre}",
                options=columnasOpciones,
                index=indiceDefecto,
                key=f"sem_{colNombre}",
                label_visibility="collapsed"
            )
        with c3:
            tipoEsperado = st.selectbox(
                f"Tipo para {colNombre}",
                options=["texto", "decimal", "entero", "fecha", "booleano"],
                index=["texto", "decimal", "entero", "fecha", "booleano"].index(
                    tipoPrimitivo if tipoPrimitivo in ["texto", "decimal", "entero", "fecha", "booleano"] else "texto"
                ),
                key=f"tipo_{colNombre}",
                label_visibility="collapsed"
            )
        with c4:
            esObligatoria = st.checkbox("Requerida", value=True, key=f"req_{colNombre}")

        configuracionColumnas.append({
            "nombreColumna": colNombre,
            "tipoDatoEsperado": tipoEsperado,
            "clasificacionSemantica": clasificacionElegida,
            "esObligatoria": esObligatoria
        })

    # Previsualización tabular del OBT
    st.markdown("---")
    st.write(f"**Vista Previa de la Tabla Consolidada OBT ({len(dataframeConsolidado)} filas):**")
    st.dataframe(dataframeConsolidado.head(5), use_container_width=True)

    # 3. Guardado, Contrato y Generación de Parquet
    if st.button("💾 Guardar Contrato y Generar Cubo Parquet OBT", key="btnGuardarExcelParquet", use_container_width=True):
        contratoConstruido = ValidadorContratos.construirContratoJson(
            idModelo=codigoVista,
            nombreVista=nombreVista,
            tipoIngesta=modalidadOperativa,
            mapeoColumnas=configuracionColumnas,
            definicionJoins=definicionJoins
        )

        # Validación del contrato
        resultadoValidacion = ValidadorContratos.validarEsquema(dataframeConsolidado, contratoConstruido)
        if not resultadoValidacion.esValido:
            st.error("Error en validación de contrato:")
            for err in resultadoValidacion.errores:
                st.write(f"- ❌ {err}")
            st.markdown('</div>', unsafe_allow_html=True)
            return

        # Generar Parquet
        directorioAlmacenamiento = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
        ))
        rutaParquet = os.path.join(directorioAlmacenamiento, f"{codigoVista}.parquet")

        # Si es Modalidad B o actualización, purgar previo
        GeneradorOBT.purgarArchivoParquet(rutaParquet)
        GeneradorOBT.guardarEnParquet(dataframeConsolidado, rutaParquet, contratoColumnas=configuracionColumnas)

        # Persistir o actualizar en base de datos de control
        with obtenerSesion() as sesion:
            vistaBd = sesion.query(VistaModelo).filter_by(codigoVista=codigoVista).first()
            if not vistaBd:
                vistaBd = VistaModelo(
                    codigoVista=codigoVista,
                    nombreVista=nombreVista,
                    descripcion=f"Cubo generado vía Excel ({modalidadOperativa})",
                    tipoIngesta=modalidadOperativa,
                    rutaArchivoParquet=rutaParquet,
                    contratoEsquemaJson=json.dumps(contratoConstruido),
                    fechaUltimaEjecucion=datetime.utcnow(),
                    activo=True
                )
                sesion.add(vistaBd)
            else:
                vistaBd.nombreVista = nombreVista
                vistaBd.tipoIngesta = modalidadOperativa
                vistaBd.rutaArchivoParquet = rutaParquet
                vistaBd.contratoEsquemaJson = json.dumps(contratoConstruido)
                vistaBd.fechaUltimaEjecucion = datetime.utcnow()

            sesion.commit()

        st.success(
            f"✅ ¡Cubo '{codigoVista}' generado exitosamente! "
            f"Archivo Parquet almacenado en `{rutaParquet}`."
        )

    st.markdown('</div>', unsafe_allow_html=True)


def renderizarFlujoSqlEnVivo() -> None:
    """
    Implementa el flujo de consulta en línea SQL / SP con catálogo de conexiones y Throttling de 5 min.
    """
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("Consultas en Línea / SQL en Vivo")
    st.caption("Conexión directa a motores relacionales con control de sobrecarga (Throttling de 5 minutos).")

    conexionesDisponibles = GestorSqlEnVivo.listarConexiones()

    # Formulario para registrar o seleccionar conexión
    colSelCon, colNuevaCon = st.columns([3, 2])
    with colSelCon:
        opcionesConexiones = {c["nombreConexion"]: c for c in conexionesDisponibles}
        nombres = list(opcionesConexiones.keys())

        if nombres:
            conexionSeleccionadaNombre = st.selectbox(
                "Seleccionar Conexión a Base de Datos:",
                options=nombres
            )
            conexionSeleccionada = opcionesConexiones[conexionSeleccionadaNombre]
            cadenaConexionActiva = conexionSeleccionada["cadenaConexion"]
            idConexionActiva = conexionSeleccionada["idConexion"]
        else:
            conexionSeleccionada = None
            cadenaConexionActiva = ""
            idConexionActiva = None
            st.info("No hay conexiones registradas. Puedes agregar una a la derecha.")

    with colNuevaCon:
        with st.expander("➕ Registrar Nueva Conexión", expanded=(not bool(nombres))):
            nombreNueva = st.text_input("Nombre de la Conexión:", value="BaseTransaccional")
            motorNuevo = st.selectbox("Motor:", options=["SQLServer", "SQLite", "PostgreSQL"])
            cadenaNueva = st.text_input(
                "Cadena de Conexión (SQLAlchemy):",
                value="sqlite:///sistemaAnalitica/almacenamiento/controlAnalitica.db",
                help="Ej: mssql+pyodbc://user:pass@servidor/bd?driver=ODBC+Driver+17+for+SQL+Server"
            )
            descNueva = st.text_input("Descripción:", value="Conexión de pruebas")

            colTest, colGuardar = st.columns(2)
            with colTest:
                if st.button("Probar Conexión", key="btnTestConexion"):
                    valido, msg = GestorSqlEnVivo.probarConexion(cadenaNueva)
                    if valido:
                        st.success("Conexión exitosa.")
                    else:
                        st.error(msg)
            with colGuardar:
                if st.button("Guardar Conexión", key="btnGuardarConexion"):
                    GestorSqlEnVivo.registrarConexion(nombreNueva, motorNuevo, cadenaNueva, descNueva)
                    st.success(f"Conexión '{nombreNueva}' guardada.")
                    st.rerun()

    if not cadenaConexionActiva:
        st.markdown('</div>', unsafe_allow_html=True)
        return

    st.markdown("---")
    colSql1, colSql2 = st.columns([3, 2])
    with colSql1:
        codigoVistaSql = st.text_input("Código de la Vista SQL:", value="vistaUsuariosSistema")
        nombreVistaSql = st.text_input("Nombre de la Vista:", value="Métricas de Usuarios Registrados")
        consultaSqlEntrada = st.text_area(
            "Sentencia SQL o Invocación de Stored Procedure:",
            value="SELECT id_usuario, nombre_usuario, nombre_completo, activo, fecha_creacion FROM usuarios",
            height=100
        )
    with colSql2:
        st.write("&nbsp;")
        st.write("&nbsp;")
        st.info("ℹ️ Al probar la consulta, el sistema inyecta `LIMIT 10` o `TOP 10` para inferir cabeceras sin saturar el servidor.")
        if st.button("🔍 Probar Consulta y Extraer Muestra", key="btnProbarSql", use_container_width=True):
            dfMuestra, error = GestorSqlEnVivo.ejecutarMuestraSql(cadenaConexionActiva, consultaSqlEntrada, limiteMuestra=5)
            if error:
                st.error(error)
            else:
                st.session_state["muestraSqlDataframe"] = dfMuestra
                st.success(f"Muestra extraída correctamente ({len(dfMuestra)} filas).")

    dfMuestraSql = st.session_state.get("muestraSqlDataframe")
    if dfMuestraSql is not None:
        st.markdown("---")
        st.write("**Previsualización de Muestra SQL:**")
        st.dataframe(dfMuestraSql, use_container_width=True)

        colGuardarSql, colEspacio = st.columns([2, 3])
        with colGuardarSql:
            if st.button("💾 Registrar Vista SQL en Catálogo", key="btnGuardarVistaSql", use_container_width=True):
                with obtenerSesion() as sesion:
                    vistaExistente = sesion.query(VistaModelo).filter_by(codigoVista=codigoVistaSql).first()
                    if not vistaExistente:
                        vistaExistente = VistaModelo(
                            codigoVista=codigoVistaSql,
                            nombreVista=nombreVistaSql,
                            tipoIngesta="SqlEnVivo",
                            idConexion=idConexionActiva,
                            consultaSql=consultaSqlEntrada,
                            fechaUltimaEjecucion=None,
                            activo=True
                        )
                        sesion.add(vistaExistente)
                    else:
                        vistaExistente.nombreVista = nombreVistaSql
                        vistaExistente.idConexion = idConexionActiva
                        vistaExistente.consultaSql = consultaSqlEntrada

                    sesion.commit()
                st.success(f"Vista SQL '{codigoVistaSql}' registrada en el catálogo.")

    # Sección de Control de Sobrecarga (Throttling) para vistas SQL registradas
    st.markdown("---")
    st.markdown("#### ⏱️ Ejecución y Control de Sobrecarga (Throttling de 5 minutos)")

    with obtenerSesion() as sesion:
        vistasSqlRegistradas = sesion.query(VistaModelo).filter_by(tipoIngesta="SqlEnVivo", activo=True).all()
        opcionesVistasSql = {v.nombreVista: v.idVista for v in vistasSqlRegistradas}

    if not opcionesVistasSql:
        st.caption("Registra una vista SQL para habilitar la materialización con control de sobrecarga.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    vistaElegidaNombre = st.selectbox(
        "Seleccionar Vista SQL para Actualizar:",
        options=list(opcionesVistasSql.keys())
    )
    idVistaElegida = opcionesVistasSql[vistaElegidaNombre]

    puedeEjecutar, segsRestantes, mensajeThrottling = GestorSqlEnVivo.verificarThrottling(idVistaElegida)

    colBotonThrottling, colEstadoThrottling = st.columns([2, 3])
    with colBotonThrottling:
        if puedeEjecutar:
            if st.button("🚀 Actualizar Datos (Ejecutar y Guardar Parquet)", key="btnRefrescoSql"):
                directorioAlmacenamiento = os.path.abspath(os.path.join(
                    os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
                ))
                with obtenerSesion() as sesion:
                    vistaObj = sesion.query(VistaModelo).filter_by(idVista=idVistaElegida).first()
                    rutaParquetSql = os.path.join(directorioAlmacenamiento, f"{vistaObj.codigoVista}.parquet")

                exito, msg, _ = GestorSqlEnVivo.ejecutarYMaterializarParquet(idVistaElegida, rutaParquetSql)
                if exito:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        else:
            st.button("🔒 Actualizar Datos (Bloqueado)", disabled=True, use_container_width=True)

    with colEstadoThrottling:
        if not puedeEjecutar:
            minutos = segsRestantes // 60
            segundos = segsRestantes % 60
            st.warning(
                f"⏳ **Protección de sobrecarga activa.** Próximo refresco disponible en: "
                f"**{minutos:02d}:{segundos:02d}**"
            )
        else:
            st.success("✅ Listo para ejecutar refresco bajo demanda.")

    st.markdown('</div>', unsafe_allow_html=True)


def renderizarFlujoDataLake() -> None:
    """
    Implementa el flujo de Procesos Masivos / Data Lake (Inferencia WHERE 1=0 y sólo lectura).
    """
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("Procesos Masivos / Data Lake Parquet")
    st.caption("Vistas analíticas de solo lectura sobre archivos Parquet depositados en el lago de datos.")

    directorioParquets = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
    ))
    os.makedirs(directorioParquets, exist_ok=True)
    archivosParquet = [f for f in os.listdir(directorioParquets) if f.endswith(".parquet")]

    if not archivosParquet:
        st.info("No se han detectado archivos Parquet en el almacenamiento. Genera uno mediante el Flujo 1 o 2.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    colParquetSel, colParquetInfo = st.columns([2, 3])
    with colParquetSel:
        archivoElegido = st.selectbox("Seleccionar Archivo Parquet:", options=archivosParquet)
        codigoSugerido = os.path.splitext(archivoElegido)[0]
        nombreCubo = st.text_input("Nombre del Cubo:", value=f"Data Lake - {codigoSugerido}")

        if st.button("Registrar como Vista Data Lake de Solo Lectura", key="btnRegistrarDataLake"):
            rutaCompleta = os.path.join(directorioParquets, archivoElegido)
            with obtenerSesion() as sesion:
                vistaExistente = sesion.query(VistaModelo).filter_by(codigoVista=codigoSugerido).first()
                if not vistaExistente:
                    vistaExistente = VistaModelo(
                        codigoVista=codigoSugerido,
                        nombreVista=nombreCubo,
                        descripcion="Cubo Data Lake de solo lectura",
                        tipoIngesta="ProcesoMasivo",
                        rutaArchivoParquet=rutaCompleta,
                        activo=True
                    )
                    sesion.add(vistaExistente)
                else:
                    vistaExistente.tipoIngesta = "ProcesoMasivo"
                    vistaExistente.rutaArchivoParquet = rutaCompleta
                sesion.commit()
            st.success(f"Cubo '{codigoSugerido}' registrado en el catálogo.")

    with colParquetInfo:
        rutaSeleccionada = os.path.join(directorioParquets, archivoElegido)
        try:
            resumen = ServicioDuckDb.obtenerResumenCubo(rutaSeleccionada)
            st.write(f"**Total de Filas (DuckDB):** `{resumen['totalFilas']:,}`")
            st.write("**Esquema de Columnas:**")
            dfCols = pd.DataFrame(resumen["columnas"])
            st.dataframe(dfCols, use_container_width=True, height=180)
        except Exception as errDuck:
            st.error(f"Error inspeccionando Parquet: {str(errDuck)}")

    st.markdown('</div>', unsafe_allow_html=True)


def renderizarCatalogoVistas() -> None:
    """
    Despliega la lista de todas las vistas y cubos analíticos configurados en la base de datos de control.
    """
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("Catálogo Centralizado de Vistas y Cubos")

    with obtenerSesion() as sesion:
        vistas = sesion.query(VistaModelo).all()
        if not vistas:
            st.info("Aún no hay vistas analíticas registradas.")
            st.markdown('</div>', unsafe_allow_html=True)
            return

        datosVistas = []
        for v in vistas:
            existeParquet = os.path.exists(v.rutaArchivoParquet) if v.rutaArchivoParquet else False
            datosVistas.append({
                "ID": v.idVista,
                "Código": v.codigoVista,
                "Nombre": v.nombreVista,
                "Tipo Ingesta": v.tipoIngesta,
                "Parquet Disponible": "Sí" if existeParquet else "No",
                "Última Ejecución": v.fechaUltimaEjecucion.strftime("%Y-%m-%d %H:%M:%S") if v.fechaUltimaEjecucion else "Nunca",
                "Estado": "Activo" if v.activo else "Inactivo"
            })

    dfVistas = pd.DataFrame(datosVistas)
    st.dataframe(dfVistas, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
