"""
Vista de autenticación de usuarios con estética corporativa y selector de estrategias.
Implementa el formulario de acceso y atajos de demostración rápida por rol.
"""

import streamlit as st
from sistemaAnalitica.modulos.autenticacion.gestorAutenticacion import GestorAutenticacion
from sistemaAnalitica.modulos.presentacion.estilos import (
    inyectarEstilosGlobales, COLOR_PRIMARIO, COLOR_TEXTO_SECUNDARIO
)


def renderizarFormularioLogin(gestorAutenticacion: GestorAutenticacion) -> None:
    """
    Despliega la pantalla de inicio de sesión con soporte para múltiples estrategias
    y pre-llenado rápido para roles de prueba.
    """
    inyectarEstilosGlobales()

    # Inicialización de estado para prellenado de credenciales
    if "campoUsuario" not in st.session_state:
        st.session_state["campoUsuario"] = "admin"
    if "campoClave" not in st.session_state:
        st.session_state["campoClave"] = "admin"
    if "mensajeErrorLogin" not in st.session_state:
        st.session_state["mensajeErrorLogin"] = None

    columnaIzquierda, columnaCentral, columnaDerecha = st.columns([1, 1.8, 1])

    with columnaCentral:
        # Encabezado corporativo institucional
        st.markdown(
            f"""
            <div style="text-align: center; margin-top: 1.5rem; margin-bottom: 1rem;">
                <div style="font-size: 3.5rem; color: {COLOR_PRIMARIO}; line-height: 1;">
                    <span class="material-symbols-outlined" style="font-size: 4rem;">insights</span>
                </div>
                <h1 style="font-size: 2.2rem; margin: 0.2rem 0; letter-spacing: -0.5px;">Sistema Analítico</h1>
                <p style="color: {COLOR_TEXTO_SECUNDARIO}; font-size: 0.95rem; margin-top: 0.2rem;">
                    Inteligencia Analítica y Cubos de Autoservicio OLAP
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown('<div class="glass-card">', unsafe_allow_html=True)

        # 1. Selector de Estrategia de Autenticación
        listaEstrategias = gestorAutenticacion.listarEstrategias()
        mapaClaves = {item["nombre"]: item["clave"] for item in listaEstrategias}
        nombresEstrategias = list(mapaClaves.keys())

        estrategiaSeleccionada = st.selectbox(
            "Método de Autenticación:",
            options=nombresEstrategias,
            index=0,
            help="Selecciona el mecanismo de validación de identidad corporativo."
        )
        claveEstrategiaElegida = mapaClaves[estrategiaSeleccionada]
        gestorAutenticacion.asignarEstrategia(claveEstrategiaElegida)

        # 2. Selector Rápido de Roles Demo
        st.markdown(
            """
            <div style="margin-top: 0.8rem; margin-bottom: 0.8rem; padding: 0.6rem; background: #f3f3f6; border-radius: 8px; border: 1px solid #c1c6d3;">
                <p style="font-size: 0.75rem; font-weight: 700; color: #414751; text-transform: uppercase; margin: 0 0 0.4rem 0;">
                    Seleccionar Rol de Demostración (clic para rellenar):
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

        colRol1, colRol2, colRol3 = st.columns(3)
        with colRol1:
            if st.button("🛡️ Admin", key="btnAdmin", use_container_width=True, help="admin / admin"):
                st.session_state["campoUsuario"] = "admin"
                st.session_state["campoClave"] = "admin"
                st.session_state["mensajeErrorLogin"] = None
                st.rerun()

        with colRol2:
            if st.button("📊 Analista", key="btnAnalista", use_container_width=True, help="analista / analista123"):
                st.session_state["campoUsuario"] = "analista"
                st.session_state["campoClave"] = "analista123"
                st.session_state["mensajeErrorLogin"] = None
                st.rerun()

        with colRol3:
            if st.button("⚙️ Operador", key="btnOperador", use_container_width=True, help="operador / operador123"):
                st.session_state["campoUsuario"] = "operador"
                st.session_state["campoClave"] = "operador123"
                st.session_state["mensajeErrorLogin"] = None
                st.rerun()

        # 3. Formulario de Acceso
        with st.form("formularioAcceso", clear_on_submit=False):
            usuarioEntrada = st.text_input(
                "Usuario",
                value=st.session_state["campoUsuario"],
                placeholder="Ingresa tu usuario institucional"
            )
            claveEntrada = st.text_input(
                "Contraseña",
                value=st.session_state["campoClave"],
                type="password",
                placeholder="••••••••"
            )

            botonAcceder = st.form_submit_button("Acceder al Sistema", use_container_width=True)

            if botonAcceder:
                if not usuarioEntrada or not claveEntrada:
                    st.session_state["mensajeErrorLogin"] = "Por favor ingresa tu usuario y contraseña."
                else:
                    perfilUsuario = gestorAutenticacion.autenticarUsuario(usuarioEntrada, claveEntrada)
                    if perfilUsuario:
                        st.session_state["autenticado"] = True
                        st.session_state["usuarioActual"] = perfilUsuario
                        st.session_state["mensajeErrorLogin"] = None
                        st.rerun()
                    else:
                        st.session_state["mensajeErrorLogin"] = (
                            f"Credenciales no válidas para {usuarioEntrada} "
                            f"usando {estrategiaSeleccionada}."
                        )

        # Despliegue de error si existe
        if st.session_state.get("mensajeErrorLogin"):
            st.markdown(
                f"""
                <div class="alerta-error">
                    <span class="material-symbols-outlined" style="font-size: 1.2rem;">error</span>
                    <span>{st.session_state["mensajeErrorLogin"]}</span>
                </div>
                """,
                unsafe_allow_html=True
            )

        st.markdown('</div>', unsafe_allow_html=True)
