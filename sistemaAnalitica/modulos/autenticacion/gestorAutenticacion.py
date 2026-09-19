"""
Gestor de autenticación que coordina las estrategias bajo el patrón Strategy.
"""

from typing import Dict, Optional, Any, List
from sistemaAnalitica.modulos.autenticacion.estrategias import (
    EstrategiaAutenticacionBase,
    AutenticadorLocal,
    AutenticadorActiveDirectory,
    AutenticadorSoap
)


class GestorAutenticacion:
    """
    Contexto del patrón Strategy que expone operaciones de autenticación unificadas.
    """

    def __init__(self, claveEstrategiaInicial: str = "LOCAL"):
        self.estrategiasDisponibles: Dict[str, EstrategiaAutenticacionBase] = {
            "LOCAL": AutenticadorLocal(),
            "ACTIVE_DIRECTORY": AutenticadorActiveDirectory(),
            "SOAP": AutenticadorSoap()
        }
        self.claveEstrategiaActual = claveEstrategiaInicial
        self.estrategiaActual: EstrategiaAutenticacionBase = self.estrategiasDisponibles[claveEstrategiaInicial]

    def listarEstrategias(self) -> List[Dict[str, str]]:
        """
        Retorna la lista de estrategias configuradas y su nombre descriptivo.
        """
        return [
            {"clave": clave, "nombre": estrategia.obtenerNombreEstrategia()}
            for clave, estrategia in self.estrategiasDisponibles.items()
        ]

    def asignarEstrategia(self, claveEstrategia: str) -> bool:
        """
        Modifica la estrategia activa en tiempo de ejecución.
        """
        if claveEstrategia in self.estrategiasDisponibles:
            self.claveEstrategiaActual = claveEstrategia
            self.estrategiaActual = self.estrategiasDisponibles[claveEstrategia]
            return True
        return False

    def autenticarUsuario(self, nombreUsuario: str, clave: str) -> Optional[Dict[str, Any]]:
        """
        Ejecuta la autenticación utilizando la estrategia seleccionada actualmente.
        """
        return self.estrategiaActual.autenticar(nombreUsuario, clave)

    def obtenerNombreEstrategiaActual(self) -> str:
        """
        Devuelve el nombre amigable de la estrategia en uso.
        """
        return self.estrategiaActual.obtenerNombreEstrategia()
