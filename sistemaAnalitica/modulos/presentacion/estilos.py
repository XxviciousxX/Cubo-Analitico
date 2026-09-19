"""
Definición de estilos corporativos y tokens de diseño visual.
Extraído de las directrices de diseño de Knowledge Base (Cubo de Autoservicio).
"""

import streamlit as st

# Tokens de colores institucionales
COLOR_PRIMARIO = "#004482"
COLOR_PRIMARIO_CONTENEDOR = "#005cab"
COLOR_SECUNDARIO = "#006e20"
COLOR_SECUNDARIO_CONTENEDOR = "#e8f5e9"
COLOR_FONDO = "#f9f9fc"
COLOR_SUPERFICIE = "#ffffff"
COLOR_SUPERFICIE_BAJA = "#f3f3f6"
COLOR_TEXTO_PRINCIPAL = "#1a1c1e"
COLOR_TEXTO_SECUNDARIO = "#414751"
COLOR_BORDE = "#c1c6d3"
COLOR_ERROR = "#ba1a1a"
COLOR_ERROR_CONTENEDOR = "#ffdad6"
COLOR_ERROR_TEXTO = "#93000a"


def inyectarEstilosGlobales() -> None:
    """
    Inyecta las hojas de estilo CSS en la aplicación Streamlit respetando
    la paleta corporativa y el diseño de Knowledge Base.
    """
    css = f"""
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet">

    <style>
        /* Tipografía y fondo principal con malla de gradiente */
        html, body, [class*="css"], .stApp {{
            font-family: 'Inter', sans-serif;
            color: {COLOR_TEXTO_PRINCIPAL};
            background-color: {COLOR_FONDO};
            background-image: 
                radial-gradient(at 0% 0%, rgba(0, 68, 130, 0.12) 0px, transparent 50%),
                radial-gradient(at 100% 0%, rgba(0, 110, 32, 0.10) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(0, 68, 130, 0.08) 0px, transparent 50%),
                radial-gradient(at 0% 100%, rgba(0, 110, 32, 0.06) 0px, transparent 50%);
            background-attachment: fixed;
        }}

        /* Títulos institucionales */
        h1, h2, h3, .font-display {{
            font-family: 'Hanken Grotesk', sans-serif !important;
            color: {COLOR_PRIMARIO} !important;
            font-weight: 700 !important;
        }}

        /* Botones principales con efecto resplandor corporativo (btn-glow) */
        div.stButton > button:first-child {{
            background: linear-gradient(135deg, {COLOR_PRIMARIO} 0%, {COLOR_PRIMARIO_CONTENEDOR} 100%) !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 0.6rem 1.4rem !important;
            font-family: 'Hanken Grotesk', sans-serif !important;
            font-weight: 700 !important;
            font-size: 0.95rem !important;
            box-shadow: 0 4px 15px rgba(0, 68, 130, 0.25) !important;
            transition: all 0.3s ease !important;
        }}

        div.stButton > button:first-child:hover {{
            box-shadow: 0 6px 20px rgba(0, 68, 130, 0.38) !important;
            transform: translateY(-1px) !important;
            background: linear-gradient(135deg, {COLOR_PRIMARIO_CONTENEDOR} 0%, {COLOR_PRIMARIO} 100%) !important;
        }}

        div.stButton > button:first-child:active {{
            transform: scale(0.98) !important;
        }}

        /* Botones secundarios */
        button[kind="secondary"] {{
            background: #ffffff !important;
            color: {COLOR_TEXTO_PRINCIPAL} !important;
            border: 1px solid {COLOR_BORDE} !important;
            border-radius: 8px !important;
            font-family: 'Inter', sans-serif !important;
            font-weight: 600 !important;
            box-shadow: none !important;
        }}

        button[kind="secondary"]:hover {{
            background: {COLOR_SUPERFICIE_BAJA} !important;
            border-color: {COLOR_PRIMARIO} !important;
            color: {COLOR_PRIMARIO} !important;
        }}

        /* Tarjeta de cristal (Glass Card) */
        .glass-card {{
            background: rgba(255, 255, 255, 0.88);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.5);
            border-radius: 14px;
            box-shadow: 0 8px 32px 0 rgba(0, 68, 130, 0.08);
            padding: 2rem;
            margin-bottom: 1.5rem;
        }}

        /* Cajas de texto e inputs */
        div[data-baseweb="input"] {{
            border-radius: 8px !important;
            border-color: {COLOR_BORDE} !important;
            background-color: #ffffff !important;
        }}

        div[data-baseweb="input"]:focus-within {{
            border-color: {COLOR_PRIMARIO} !important;
            box-shadow: 0 0 0 1px {COLOR_PRIMARIO} !important;
        }}

        /* Métricas y tarjetas de control */
        div[data-testid="stMetric"] {{
            background: #ffffff;
            border: 1px solid {COLOR_BORDE};
            border-radius: 10px;
            padding: 1rem;
            border-top: 4px solid {COLOR_PRIMARIO};
            box-shadow: 0px 4px 15px rgba(0, 0, 0, 0.03);
        }}

        /* Alertas de error corporativas */
        .alerta-error {{
            background-color: {COLOR_ERROR_CONTENEDOR};
            color: {COLOR_ERROR_TEXTO};
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-size: 0.88rem;
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 1rem;
            border: 1px solid #f2b8b5;
        }}

        /* Barra de navegación superior */
        .barra-superior {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #ffffff;
            padding: 0.75rem 1.5rem;
            border-radius: 12px;
            border: 1px solid {COLOR_BORDE};
            margin-bottom: 1.5rem;
            box-shadow: 0 2px 10px rgba(0, 68, 130, 0.05);
        }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
