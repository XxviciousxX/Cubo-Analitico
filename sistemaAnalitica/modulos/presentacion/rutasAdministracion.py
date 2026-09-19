"""
Módulo de Presentación: Rutas de Administración de Cubos y Vistas.
Re-exporta el enrutador de FastAPI para la gestión de ciclo de vida.
"""

from sistemaAnalitica.app.routers.administracion import router

__all__ = ["router"]
