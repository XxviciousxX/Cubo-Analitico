"""
Script de verificación end-to-end para la persistencia híbrida de cubos Parquet en Supabase.
Simula el reinicio de contenedor efímero de Render eliminando el archivo local
y verificando la auto-restauración y consulta OLAP sin pérdida de datos.
"""

import os
import sys
import tempfile
import duckdb
import pandas as pd
from datetime import datetime

# Asegurar encoding UTF-8 en consola
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Asegurar path
directorioActual = os.path.dirname(os.path.abspath(__file__))
directorioExport = os.path.abspath(os.path.join(directorioActual, ".."))
if directorioExport not in sys.path:
    sys.path.insert(0, directorioExport)

from sistemaAnalitica.modulos.seguridad.baseDatos import obtenerSesion, inicializarBaseDatos
from sistemaAnalitica.modulos.seguridad.modelos import CuboModelo, VistaModelo
from sistemaAnalitica.modulos.motorAnalitico.servicioPersistenciaCubos import ServicioPersistenciaCubos
from sistemaAnalitica.modulos.motorAnalitico import ServicioCapaSemantica


def ejecutarPruebaPersistencia():
    print("=" * 70)
    print("INICIANDO PRUEBA DE PERSISTENCIA HIBRIDA (SUPABASE BYTEA + PARQUET LOCAL)")
    print("=" * 70)

    # 1. Asegurar esquema en Supabase
    inicializarBaseDatos()

    directorioParquets = ServicioPersistenciaCubos.obtenerDirectorioParquets()
    nombreArchivoTest = "cubo_test_persistencia_render.parquet"
    rutaParquetTest = os.path.join(directorioParquets, nombreArchivoTest)
    codigoVistaTest = "vista_test_persistencia"

    # 2. Generar DataFrame sintético y exportar a Parquet ZSTD
    dfPrueba = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "categoria": ["Electronica", "Hogar", "Electronica", "Moda", "Hogar"],
        "monto": [150.50, 45.00, 320.00, 89.90, 12.50]
    })

    conDuck = duckdb.connect()
    try:
        conDuck.register("df_test", dfPrueba)
        rutaSql = rutaParquetTest.replace("\\", "/")
        conDuck.execute(f"COPY df_test TO '{rutaSql}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    finally:
        conDuck.close()

    assert os.path.exists(rutaParquetTest), "El parquet de prueba no se creó en disco."
    tamanoOriginal = os.path.getsize(rutaParquetTest)
    print(f"[OK] 1. Archivo Parquet creado en disco: {rutaParquetTest} ({tamanoOriginal} bytes)")

    # 3. Registrar CuboModelo en Supabase y persistir binario
    with obtenerSesion() as sesion:
        # Purgar previo si existiera
        previo = sesion.query(CuboModelo).filter_by(nombreCubo="Cubo Test Persistencia").first()
        if previo:
            sesion.delete(previo)
            sesion.commit()

        cubo = CuboModelo(
            nombreCubo="Cubo Test Persistencia",
            archivoParquet=rutaParquetTest,
            tipoOrigen="EXCEL",
            estadoHabilitado=True,
            fechaUltimaCarga=datetime.utcnow(),
            metadatosColumnasJson='[{"nombreColumna": "categoria", "tipoDato": "VARCHAR", "clasificacionSemantica": "Categorica/Dimension"}, {"nombreColumna": "monto", "tipoDato": "DOUBLE", "clasificacionSemantica": "MetricaSumable"}]'
        )
        sesion.add(cubo)
        sesion.flush()

        exitoPersistencia = ServicioPersistenciaCubos.persistirBinarioEnCubo(cubo, rutaParquetTest)
        assert exitoPersistencia, "Fallo al serializar y asignar binario al cubo."
        assert cubo.archivoBinario is not None and len(cubo.archivoBinario) == tamanoOriginal

        sesion.commit()
        idCuboCreado = cubo.idCubo

    print(f"[OK] 2. Cubo persistido en Supabase PostgreSQL. ID: {idCuboCreado}, Binario en BD: {tamanoOriginal} bytes.")

    # 4. Crear VistaModelo asociada
    with obtenerSesion() as sesion:
        prevVista = sesion.query(VistaModelo).filter_by(codigoVista=codigoVistaTest).first()
        if prevVista:
            sesion.delete(prevVista)
            sesion.commit()

        vista = VistaModelo(
            codigoVista=codigoVistaTest,
            nombreVista="Vista Test Persistencia",
            descripcion="Vista para prueba de persistencia",
            tipoIngesta="EXCEL",
            idCubo=idCuboCreado,
            rutaArchivoParquet=rutaParquetTest,
            activo=True,
            estadoHabilitado=True
        )
        sesion.add(vista)
        sesion.commit()

    print(f"[OK] 3. Vista analitica '{codigoVistaTest}' creada y vinculada al cubo.")

    # 5. SIMULAR REINICIO DE CONTENEDOR EN RENDER (Destrucción de disco local)
    print("\n--- SIMULANDO REINICIO DE CONTENEDOR RENDER (Destruccion de archivo local) ---")
    if os.path.exists(rutaParquetTest):
        os.remove(rutaParquetTest)

    assert not os.path.exists(rutaParquetTest), "Error: el archivo no se pudo eliminar para la simulacion."
    print(f"[SIMULACION] Archivo eliminado de disco: {os.path.exists(rutaParquetTest)} (Disco limpio como en container nuevo)")

    # 6. Probar auto-restauración mediante ServicioPersistenciaCubos.asegurarParquetPorRuta
    print("\n--- PROBANDO AUTO-RESTAURACION BAJO DEMANDA ---")
    rutaRestaurada = ServicioPersistenciaCubos.asegurarParquetPorRuta(rutaParquetTest)
    assert rutaRestaurada and os.path.exists(rutaRestaurada), "Fallo en asegurarParquetPorRuta."
    assert os.path.getsize(rutaRestaurada) == tamanoOriginal, "El tamano restaurado no coincide con el original."
    print(f"[OK] 4. Archivo auto-restaurado en disco exitosamente: {rutaRestaurada} ({os.path.getsize(rutaRestaurada)} bytes)")

    # 7. Volver a borrar y probar consulta OLAP en frío
    print("\n--- SIMULANDO SEGUNDA DESTRUCCION Y CONSULTA OLAP EN FRIO ---")
    os.remove(rutaParquetTest)
    assert not os.path.exists(rutaParquetTest)

    resultadoOlap = ServicioCapaSemantica.validarYEjecutarConsultaSegura(
        codigoVista=codigoVistaTest,
        dimensionSolicitada="categoria",
        metricaSolicitada="monto"
    )

    assert resultadoOlap.get("exito") is True, f"Error en consulta OLAP: {resultadoOlap}"
    assert os.path.exists(rutaParquetTest), "El archivo debio restaurarse automaticamente durante la consulta."
    filas = resultadoOlap.get("filas", [])
    print(f"[OK] 5. Consulta OLAP ejecutada exitosamente en frio. Total categorias agrupadas: {len(filas)}")
    for f in filas:
        print(f"   - {f.get('categoria')}: Total {f.get('monto_Suma')} (Promedio: {f.get('monto_Promedio')})")

    # 8. Probar sincronización global de arranque (startup)
    print("\n--- SIMULANDO EVENTO STARTUP DE FASTAPI ---")
    os.remove(rutaParquetTest)
    assert not os.path.exists(rutaParquetTest)

    totalRestaurados = ServicioPersistenciaCubos.sincronizarTodosLosCubos()
    assert totalRestaurados >= 1, "sincronizarTodosLosCubos debio restaurar al menos 1 cubo."
    assert os.path.exists(rutaParquetTest), "El archivo debio ser restaurado en startup."
    print(f"[OK] 6. Evento startup ejecutado. Cubos restaurados en lote: {totalRestaurados}")

    # 9. Limpieza de datos de prueba en Supabase
    print("\n--- LIMPIEZA DE DATOS DE PRUEBA ---")
    with obtenerSesion() as sesion:
        v = sesion.query(VistaModelo).filter_by(codigoVista=codigoVistaTest).first()
        if v:
            sesion.delete(v)
        c = sesion.query(CuboModelo).filter_by(idCubo=idCuboCreado).first()
        if c:
            sesion.delete(c)
        sesion.commit()

    if os.path.exists(rutaParquetTest):
        os.remove(rutaParquetTest)

    print("[OK] 7. Entorno de prueba limpiado correctamente en Supabase y disco.")
    print("\n" + "=" * 70)
    print("TODAS LAS PRUEBAS DE PERSISTENCIA HIBRIDA PASARON SATISFACTORIAMENTE (100%)")
    print("=" * 70)


if __name__ == "__main__":
    ejecutarPruebaPersistencia()
