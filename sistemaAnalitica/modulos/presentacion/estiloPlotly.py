"""
Módulo de Estilos y Plantillas Corporativas para Plotly.
Configura paleta cromática sobria, tipografía corporativa y soporte para fondo transparente 'glass-card'.
"""

import plotly.graph_objects as go
import plotly.io as pio

# Paleta cromática corporativa (uniformizada con tokens de diseño)
COLORES_CORPORATIVOS = [
    "#004482",  # Azul institucional profundo
    "#006e20",  # Verde bosque esmeralda
    "#005cab",  # Azul royal vivo
    "#0284c7",  # Celeste analítico
    "#d97706",  # Ámbar alerta
    "#dc2626",  # Rojo acento
    "#475569",  # Pizarra neutro
    "#64748b"   # Gris titanio
]

PLANTILLA_NOMBRE = "corporativo_sistema"


def registrarPlantillaCorporativa():
    """
    Registra en plotly.io una plantilla con fuentes, colores y layouts corporativos.
    """
    plantilla = go.layout.Template()

    # Configuración de ejes, colores y tipografía
    plantilla.layout = go.Layout(
        font=dict(
            family="Hanken Grotesk, Inter, system-ui, -apple-system, sans-serif",
            size=12,
            color="#334155"
        ),
        colorway=COLORES_CORPORATIVOS,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=30, t=50, b=40, pad=4),
        hoverlabel=dict(
            bgcolor="#ffffff",
            font_size=12,
            font_family="Inter, sans-serif",
            bordercolor="#e2e8f0"
        ),
        xaxis=dict(
            gridcolor="rgba(226, 232, 240, 0.6)",
            linecolor="#cbd5e1",
            zerolinecolor="#cbd5e1",
            tickfont=dict(size=11, color="#64748b"),
            title=dict(font=dict(size=12, color="#1e293b"))
        ),
        yaxis=dict(
            gridcolor="rgba(226, 232, 240, 0.6)",
            linecolor="#cbd5e1",
            zerolinecolor="#cbd5e1",
            tickfont=dict(size=11, color="#64748b"),
            title=dict(font=dict(size=12, color="#1e293b"))
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11, color="#475569")
        )
    )

    pio.templates[PLANTILLA_NOMBRE] = plantilla
    pio.templates.default = PLANTILLA_NOMBRE


# Registrar automáticamente al importar
registrarPlantillaCorporativa()


def aplicarEstiloFigura(figura: go.Figure, titulo: str = "", altura: int = 420) -> go.Figure:
    """
    Aplica el tema corporativo estandarizado a una figura Plotly existente.
    """
    figura.update_layout(
        template=PLANTILLA_NOMBRE,
        title=dict(
            text=f"<b>{titulo}</b>" if titulo else "",
            font=dict(size=15, color="#0f172a"),
            x=0.01,
            y=0.96
        ),
        height=altura,
        autosize=True
    )
    return figura
