"""
Punto de entrada principal de la aplicación Streamlit para el Sistema Analítico.
Coordina la inicialización de la persistencia, la sesión y el ciclo de vida de presentación.
"""

import sys
import os
import streamlit as st

# Asegurar que el directorio raíz del proyecto esté en sys.path
directorioActual = os.path.dirname(os.path.abspath(__file__))
directorioRaiz = os.path.abspath(os.path.join(directorioActual, ".."))
if directorioRaiz not in sys.path:
    sys.path.insert(0, directorioRaiz)

# Configuración inicial de página (debe ser la primera llamada de Streamlit)
st.set_page_config(
    page_title="Sistema Analítico | Cubos de Autoservicio",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

from sistemaAnalitica.modulos.seguridad.baseDatos import inicializarBaseDatos
from sistemaAnalitica.modulos.autenticacion.gestorAutenticacion import GestorAutenticacion
from sistemaAnalitica.modulos.presentacion.estilos import (
    inyectarEstilosGlobales, COLOR_PRIMARIO, COLOR_SECUNDARIO
)
from sistemaAnalitica.modulos.presentacion.loginVista import renderizarFormularioLogin
from sistemaAnalitica.modulos.presentacion.ingestaVista import renderizarVistaIngesta
from sistemaAnalitica.modulos.presentacion.exploradorVistas import renderizarExploradorVistas


def main() -> None:
    """
    Función principal que orquesta la ejecución del sistema.
    """
    # 1. Inicialización de base de datos relacional y datos base
    if "baseDatosInicializada" not in st.session_state:
        inicializarBaseDatos()
        st.session_state["baseDatosInicializada"] = True

    # 2. Inicialización del gestor de autenticación
    if "gestorAutenticacion" not in st.session_state:
        st.session_state["gestorAutenticacion"] = GestorAutenticacion()

    gestor = st.session_state["gestorAutenticacion"]

    # 3. Verificación de sesión de usuario
    if not st.session_state.get("autenticado", False):
        renderizarFormularioLogin(gestor)
        return

    # 4. Renderizado de interfaz para usuario autenticado
    inyectarEstilosGlobales()
    usuario = st.session_state.get("usuarioActual", {})

    # Barra superior con datos de sesión
    colTitulo, colInfoUsuario, colAccion = st.columns([3, 2, 1])

    with colTitulo:
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 10px;">
                <span class="material-symbols-outlined" style="font-size: 2.2rem; color: {COLOR_PRIMARIO};">insights</span>
                <div>
                    <h2 style="margin: 0; font-size: 1.5rem; line-height: 1.2;">Sistema de Inteligencia Analítica</h2>
                    <span style="font-size: 0.82rem; color: #727783;">Cubos de Autoservicio y Análisis Multidimensional</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with colInfoUsuario:
        st.markdown(
            f"""
            <div style="text-align: right; padding-right: 15px;">
                <div style="font-weight: 700; font-size: 0.95rem; color: {COLOR_PRIMARIO};">
                    👤 {usuario.get('nombreCompleto', 'Usuario')}
                </div>
                <div style="font-size: 0.8rem; color: #414751;">
                    Rol: <span style="font-weight: 600; color: {COLOR_SECUNDARIO};">{usuario.get('nombreRol', 'N/A')}</span> 
                    | Origen: <span style="font-mono; font-size: 0.75rem;">{usuario.get('origenAutenticacion', 'LOCAL')}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with colAccion:
        if st.button("Cerrar Sesión", use_container_width=True, key="btnCerrarSesion"):
            st.session_state["autenticado"] = False
            st.session_state["usuarioActual"] = None
            st.rerun()

    # Barra de navegación modular interna
    permisosUsuario = usuario.get("permisos", [])
    tienePermisoIngesta = "INGESTA_DATOS" in permisosUsuario or usuario.get("nombreRol") == "Administrador"
    tienePermisoExploracion = "EXPLORACION_CUBOS" in permisosUsuario or usuario.get("nombreRol") in ["Administrador", "Analista", "Operador"]

    opcionesMenu = []
    if tienePermisoExploracion:
        opcionesMenu.append("📊 Explorador de Cubos y Reportes")
    if tienePermisoIngesta:
        opcionesMenu.append("📥 Ingesta y Modelado OBT")
    opcionesMenu.append("🏠 Panel General")

    seccionSeleccionada = st.radio(
        "Navegación del Sistema:",
        options=opcionesMenu,
        horizontal=True,
        label_visibility="collapsed"
    )

    st.markdown("---")

    if seccionSeleccionada == "📊 Explorador de Cubos y Reportes":
        renderizarExploradorVistas(usuario)
        return

    if seccionSeleccionada == "📥 Ingesta y Modelado OBT":
        renderizarVistaIngesta()
        return

    # Contenedor del panel principal
    st.markdown(
        f"""
        <div class="glass-card" style="margin-top: 1rem;">
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <h3 style="margin: 0; color: {COLOR_PRIMARIO};">Panel de Control General</h3>
                    <p style="color: #414751; margin: 0.3rem 0 0 0; font-size: 0.92rem;">
                        Bienvenido al portal analítico. Cubos de autoservicio, reportes gráficos con Plotly y DuckDB activos.
                    </p>
                </div>
                <div style="background: #e8f5e9; color: {COLOR_SECUNDARIO}; padding: 0.4rem 0.8rem; border-radius: 20px; font-weight: 700; font-size: 0.8rem;">
                    ✓ Módulo 1, 2 y 4 Activos y Operativos
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Métricas y estado modular
    m1, m2, m3, m4 = st.columns(4)

    with m1:
        st.metric(
            label="Módulo 1: Autenticación",
            value="Activo",
            delta="Strategy: Local, AD, SOAP"
        )

    with m2:
        st.metric(
            label="Módulo 2: Ingesta",
            value="Completado",
            delta="Calamine, SQL y Parquet"
        )

    with m3:
        st.metric(
            label="Módulo 4: Visualización",
            value="Activo y Operativo",
            delta="Torta, Barras y Drill-down"
        )

    with m4:
        st.metric(
            label="Módulo 3: Gobernanza",
            value="Siguiente Fase",
            delta="Matriz Excepciones y RLS"
        )

    # Detalle de la sesión activa y permisos
    with st.expander("🔍 Auditoría de Sesión Activa y Permisos Asignados", expanded=False):
        colDet1, colDet2 = st.columns(2)
        with colDet1:
            st.write("**Datos del Usuario Autenticado:**")
            st.json({
                "idUsuario": usuario.get("idUsuario"),
                "nombreUsuario": usuario.get("nombreUsuario"),
                "nombreCompleto": usuario.get("nombreCompleto"),
                "correoElectronico": usuario.get("correoElectronico"),
                "idRol": usuario.get("idRol"),
                "nombreRol": usuario.get("nombreRol"),
                "origenAutenticacion": usuario.get("origenAutenticacion")
            })
        with colDet2:
            st.write("**Permisos Granulares Activos:**")
            st.write(usuario.get("permisos", []))


if __name__ == "__main__":
    main()
