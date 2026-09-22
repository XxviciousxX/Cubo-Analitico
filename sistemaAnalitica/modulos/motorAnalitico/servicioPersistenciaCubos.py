"""
Servicio de Persistencia Híbrida y Auto-Restauración de Cubos Parquet.
Permite almacenar los archivos binarios de los cubos (.parquet ZSTD) en la base de datos relacional
(Supabase PostgreSQL como BYTEA / SQLite como BLOB) y auto-restaurarlos en disco local
de alta velocidad de forma transparente al iniciar el servidor o bajo demanda.
"""

import os
import logging
from typing import Optional, List
from sqlalchemy.orm import Session

from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion
from sistemaAnalitica.modulos.seguridad.modelos import CuboModelo, VistaModelo

loggerPersistencia = logging.getLogger("sistemaAnalitica.persistenciaCubos")


class ServicioPersistenciaCubos:
    """
    Gestiona la sincronización bidireccional entre los archivos físicos Parquet en el disco
    del contenedor efímero y su respaldo binario en la base de datos relacional persistente.
    """

    @classmethod
    def obtenerDirectorioParquets(cls) -> str:
        """
        Retorna la ruta absoluta del directorio local de parquets asegurando su existencia.
        """
        directorio = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "almacenamiento", "parquets"
        ))
        os.makedirs(directorio, exist_ok=True)
        return directorio

    @classmethod
    def persistirBinarioEnCubo(cls, cubo: CuboModelo, rutaParquet: Optional[str] = None) -> bool:
        """
        Lee el archivo Parquet físico del disco y carga su contenido binario en cubo.archivoBinario.
        """
        ruta = rutaParquet or cubo.archivoParquet
        if not ruta or not os.path.exists(ruta):
            loggerPersistencia.warning(f"No se encontró archivo físico para persistir binario: {ruta}")
            return False

        try:
            with open(ruta, "rb") as archivoFisico:
                cubo.archivoBinario = archivoFisico.read()
            loggerPersistencia.info(f"Binario Parquet cargado exitosamente en Cubo '{cubo.nombreCubo}' ({len(cubo.archivoBinario)} bytes).")
            return True
        except Exception as err:
            loggerPersistencia.error(f"Error al leer binario Parquet desde {ruta}: {err}")
            return False

    @classmethod
    def asegurarParquetEnDisco(cls, cubo: CuboModelo, sesion: Optional[Session] = None) -> str:
        """
        Garantiza que el archivo Parquet físico exista en el disco local del contenedor.
        Si Render se reinició o el contenedor despertó y el archivo no está en disco,
        lo restaura instantáneamente a partir de cubo.archivoBinario.
        """
        directorioParquets = cls.obtenerDirectorioParquets()
        nombreArchivo = os.path.basename(cubo.archivoParquet) if cubo.archivoParquet else f"cubo_{cubo.idCubo}.parquet"
        rutaLocal = os.path.join(directorioParquets, nombreArchivo)

        # Si el archivo ya existe y tiene tamaño válido, no requiere restauración
        if os.path.exists(rutaLocal) and os.path.getsize(rutaLocal) > 0:
            return rutaLocal

        # Si no tiene binario en memoria, intentar cargarlo desde la base de datos
        binario = cubo.archivoBinario
        if not binario and sesion and cubo.idCubo:
            cuboBd = sesion.query(CuboModelo).filter_by(idCubo=cubo.idCubo).first()
            if cuboBd and cuboBd.archivoBinario:
                binario = cuboBd.archivoBinario
                cubo.archivoBinario = binario

        if binario and len(binario) > 0:
            try:
                with open(rutaLocal, "wb") as archivoDestino:
                    archivoDestino.write(binario)
                loggerPersistencia.info(f"Cubo '{cubo.nombreCubo}' auto-restaurado en disco local: {rutaLocal} ({len(binario)} bytes).")
                # Sincronizar ruta en el modelo si difiere
                cubo.archivoParquet = rutaLocal
            except Exception as err:
                loggerPersistencia.error(f"Fallo al escribir binario Parquet en disco {rutaLocal}: {err}")
        else:
            loggerPersistencia.warning(f"Cubo '{cubo.nombreCubo}' no tiene archivo físico ni binario registrado en BD.")

        return rutaLocal

    @classmethod
    def asegurarParquetVista(cls, vista: VistaModelo, sesion: Optional[Session] = None) -> Optional[str]:
        """
        Asegura que el archivo Parquet referenciado por una Vista exista en disco antes de consultar.
        """
        # Si la vista tiene relación con su cubo directo
        if vista.cubo:
            return cls.asegurarParquetEnDisco(vista.cubo, sesion=sesion)

        # Si la vista tiene ruta directa
        if vista.rutaArchivoParquet:
            directorioParquets = cls.obtenerDirectorioParquets()
            nombreArchivo = os.path.basename(vista.rutaArchivoParquet)
            rutaLocal = os.path.join(directorioParquets, nombreArchivo)

            if os.path.exists(rutaLocal) and os.path.getsize(rutaLocal) > 0:
                return rutaLocal

            # Buscar el cubo asociado por nombre de archivo en la sesión
            def restaurarConSesion(s: Session):
                cubo = s.query(CuboModelo).filter(
                    (CuboModelo.archivoParquet.like(f"%{nombreArchivo}")) |
                    (CuboModelo.nombreCubo == vista.codigoVista) |
                    (CuboModelo.nombreCubo == vista.nombreVista)
                ).first()
                if cubo:
                    return cls.asegurarParquetEnDisco(cubo, sesion=s)
                return None

            if sesion:
                return restaurarConSesion(sesion)
            else:
                with obtenerSesion() as nuevaSesion:
                    return restaurarConSesion(nuevaSesion)

        return None

    @classmethod
    def asegurarParquetPorRuta(cls, rutaParquet: str, sesion: Optional[Session] = None) -> Optional[str]:
        """
        Asegura que el archivo parquet exista en disco local; si no existe o tiene tamaño 0,
        lo busca en CuboModelo por nombre de archivo o ruta y lo reconstruye en disco.
        """
        if not rutaParquet:
            return None
        if os.path.exists(rutaParquet) and os.path.getsize(rutaParquet) > 0:
            return rutaParquet

        nombreArchivo = os.path.basename(rutaParquet)

        def restaurar(s: Session):
            cubo = s.query(CuboModelo).filter(
                (CuboModelo.archivoParquet == rutaParquet) |
                (CuboModelo.archivoParquet.like(f"%{nombreArchivo}"))
            ).first()
            if cubo:
                return cls.asegurarParquetEnDisco(cubo, sesion=s)
            return None

        if sesion:
            return restaurar(sesion)
        else:
            with obtenerSesion() as s:
                return restaurar(s)

    @classmethod
    def sincronizarTodosLosCubos(cls) -> int:
        """
        Escanea todos los cubos habilitados en la base de datos relacional y
        restaura en lote en el disco local cualquier archivo Parquet que falte.
        Ideal para ejecutarse durante el evento startup de FastAPI.
        """
        directorioParquets = cls.obtenerDirectorioParquets()
        restaurados = 0

        try:
            with obtenerSesion() as sesion:
                cubos = sesion.query(CuboModelo).filter_by(estadoHabilitado=True).all()
                for c in cubos:
                    nombreArchivo = os.path.basename(c.archivoParquet) if c.archivoParquet else f"cubo_{c.idCubo}.parquet"
                    rutaEsperada = os.path.join(directorioParquets, nombreArchivo)

                    if not os.path.exists(rutaEsperada) or os.path.getsize(rutaEsperada) == 0:
                        if c.archivoBinario and len(c.archivoBinario) > 0:
                            try:
                                with open(rutaEsperada, "wb") as f:
                                    f.write(c.archivoBinario)
                                c.archivoParquet = rutaEsperada
                                restaurados += 1
                                loggerPersistencia.info(f"[Startup Sync] Cubo '{c.nombreCubo}' restaurado ({len(c.archivoBinario)} bytes).")
                            except Exception as errEscritura:
                                loggerPersistencia.error(f"[Startup Sync] Error al restaurar {rutaEsperada}: {errEscritura}")
                        else:
                            loggerPersistencia.warning(f"[Startup Sync] Cubo '{c.nombreCubo}' no tiene binario en BD para restaurar.")
                    else:
                        # Si ya existe en disco pero no tiene binario en BD, respaldarlo en BD de forma retroactiva
                        if not c.archivoBinario or len(c.archivoBinario) == 0:
                            cls.persistirBinarioEnCubo(c, rutaEsperada)

                sesion.commit()
            loggerPersistencia.info(f"Sincronización de cubos completada. Total restaurados en disco: {restaurados}.")
            return restaurados
        except Exception as errSync:
            loggerPersistencia.error(f"Error durante la sincronización global de cubos: {errSync}")
            return 0
