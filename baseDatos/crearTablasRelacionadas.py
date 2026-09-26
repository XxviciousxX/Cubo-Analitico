"""
Script optimizado para crear y poblar tres tablas relacionales en la base de datos (Supabase PostgreSQL o SQLite):
1. dim_clientes: 5,000 registros de clientes con datos demográficos y de segmentación.
2. dim_productos: 5,000 registros de catálogo con categorías, costos y precios sugeridos.
3. fact_ventas: 5,000 transacciones de ventas vinculadas por llaves foráneas a clientes y productos.

Diseñadas para modelado analítico OLAP en estrella (Star Schema) y consultas cruzadas.
Utiliza inserciones multi-row en lotes para máxima velocidad en red.
"""

import os
import sys
import random
import argparse
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import create_engine, text

# Localizar directorio raíz
DIR_ACTUAL = os.path.dirname(os.path.abspath(__file__))
DIR_RAIZ = os.path.abspath(os.path.join(DIR_ACTUAL, ".."))
if DIR_RAIZ not in sys.path:
    sys.path.insert(0, DIR_RAIZ)

from sistemaAnalitica.modulos.seguridad.baseDatos import (
    motorBaseDatos,
    motorActivo,
    cadenaConexionConfigurada,
    rutaBaseDatosSqlite
)

def obtenerMotorConexion(forzarMotor=None):
    if forzarMotor == "sqlite":
        print(f"-> Forzando motor SQLITE local: sqlite:///{rutaBaseDatosSqlite}", flush=True)
        return create_engine(f"sqlite:///{rutaBaseDatosSqlite}", echo=False), "SQLITE"
    elif forzarMotor == "postgres":
        url = os.getenv("DATABASE_URL", cadenaConexionConfigurada)
        print(f"-> Forzando motor POSTGRESQL (Supabase)", flush=True)
        return create_engine(url, echo=False), "POSTGRESQL"
    else:
        print(f"-> Usando motor configurado actualmente: {motorActivo}", flush=True)
        return motorBaseDatos, motorActivo

def crearEsquemaTablas(engine, tipoMotor):
    print(f"\n[1/4] Creando estructura DDL para motor {tipoMotor}...", flush=True)
    with engine.begin() as con:
        if tipoMotor == "POSTGRESQL":
            con.execute(text("DROP TABLE IF EXISTS fact_ventas CASCADE;"))
            con.execute(text("DROP TABLE IF EXISTS dim_clientes CASCADE;"))
            con.execute(text("DROP TABLE IF EXISTS dim_productos CASCADE;"))

            con.execute(text("""
                CREATE TABLE dim_clientes (
                    id_cliente SERIAL PRIMARY KEY,
                    codigo_cliente VARCHAR(20) NOT NULL UNIQUE,
                    nombre_cliente VARCHAR(150) NOT NULL,
                    segmento VARCHAR(50) NOT NULL,
                    ciudad VARCHAR(100) NOT NULL,
                    pais VARCHAR(50) NOT NULL,
                    canal_adquisicion VARCHAR(50) NOT NULL,
                    antiguedad_anios INTEGER NOT NULL
                );
            """))

            con.execute(text("""
                CREATE TABLE dim_productos (
                    id_producto SERIAL PRIMARY KEY,
                    codigo_sku VARCHAR(30) NOT NULL UNIQUE,
                    nombre_producto VARCHAR(150) NOT NULL,
                    categoria VARCHAR(100) NOT NULL,
                    subcategoria VARCHAR(100) NOT NULL,
                    costo_unitario NUMERIC(10, 2) NOT NULL,
                    precio_venta_base NUMERIC(10, 2) NOT NULL,
                    estado VARCHAR(20) NOT NULL
                );
            """))

            con.execute(text("""
                CREATE TABLE fact_ventas (
                    id_venta SERIAL PRIMARY KEY,
                    numero_orden VARCHAR(50) NOT NULL UNIQUE,
                    id_cliente INTEGER NOT NULL REFERENCES dim_clientes(id_cliente),
                    id_producto INTEGER NOT NULL REFERENCES dim_productos(id_producto),
                    fecha_venta TIMESTAMP NOT NULL,
                    sucursal VARCHAR(100) NOT NULL,
                    metodo_pago VARCHAR(50) NOT NULL,
                    cantidad INTEGER NOT NULL,
                    precio_unitario NUMERIC(10, 2) NOT NULL,
                    descuento_porcentaje NUMERIC(5, 2) NOT NULL,
                    monto_total NUMERIC(12, 2) NOT NULL,
                    costo_total NUMERIC(12, 2) NOT NULL,
                    margen_bruto NUMERIC(12, 2) NOT NULL
                );
            """))
        else: # SQLITE
            con.execute(text("DROP TABLE IF EXISTS fact_ventas;"))
            con.execute(text("DROP TABLE IF EXISTS dim_clientes;"))
            con.execute(text("DROP TABLE IF EXISTS dim_productos;"))

            con.execute(text("""
                CREATE TABLE dim_clientes (
                    id_cliente INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo_cliente TEXT NOT NULL UNIQUE,
                    nombre_cliente TEXT NOT NULL,
                    segmento TEXT NOT NULL,
                    ciudad TEXT NOT NULL,
                    pais TEXT NOT NULL,
                    canal_adquisicion TEXT NOT NULL,
                    antiguedad_anios INTEGER NOT NULL
                );
            """))

            con.execute(text("""
                CREATE TABLE dim_productos (
                    id_producto INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo_sku TEXT NOT NULL UNIQUE,
                    nombre_producto TEXT NOT NULL,
                    categoria TEXT NOT NULL,
                    subcategoria TEXT NOT NULL,
                    costo_unitario REAL NOT NULL,
                    precio_venta_base REAL NOT NULL,
                    estado TEXT NOT NULL
                );
            """))

            con.execute(text("""
                CREATE TABLE fact_ventas (
                    id_venta INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_orden TEXT NOT NULL UNIQUE,
                    id_cliente INTEGER NOT NULL,
                    id_producto INTEGER NOT NULL,
                    fecha_venta TIMESTAMP NOT NULL,
                    sucursal TEXT NOT NULL,
                    metodo_pago TEXT NOT NULL,
                    cantidad INTEGER NOT NULL,
                    precio_unitario REAL NOT NULL,
                    descuento_porcentaje REAL NOT NULL,
                    monto_total REAL NOT NULL,
                    costo_total REAL NOT NULL,
                    margen_bruto REAL NOT NULL,
                    FOREIGN KEY(id_cliente) REFERENCES dim_clientes(id_cliente),
                    FOREIGN KEY(id_producto) REFERENCES dim_productos(id_producto)
                );
            """))
    print("[OK] Tablas creadas con éxito.", flush=True)

def generarYInsertarDatos(engine, cantidad=5000):
    random.seed(42)

    # 1. GENERAR CLIENTES
    print(f"\n[2/4] Generando e insertando {cantidad} registros en dim_clientes...", flush=True)
    nombres = ["Juan", "María", "Carlos", "Ana", "Luis", "Lucía", "Jorge", "Sofía", "Pedro", "Valeria",
               "Fernando", "Camila", "Diego", "Paula", "Andrés", "Daniela", "Mateo", "Valentina", "Gabriel", "Elena"]
    apellidos = ["Pérez", "González", "Rodríguez", "Martínez", "López", "Gómez", "Fernández", "Díaz", "Morales", "Castro",
                 "Vargas", "Torres", "Castillo", "Soto", "Navarro", "Paredes", "Ríos", "Mendoza", "Guzmán", "Herrera"]
    segmentos = ["Corporativo Enterprise", "PyME", "Consumo Masivo", "Gobierno e Institucional", "Profesional Independiente"]
    ciudades = [
        ("Santiago", "Chile"), ("Buenos Aires", "Argentina"), ("Bogotá", "Colombia"),
        ("Lima", "Perú"), ("Ciudad de México", "México"), ("Medellín", "Colombia"),
        ("Montevideo", "Uruguay"), ("Guadalajara", "México"), ("Córdoba", "Argentina"), ("Valparaíso", "Chile")
    ]
    canales = ["Ventas Directas", "Campaña Digital / Inbound", "Referido Corporativo", "Partner Estratégico", "Portal Web"]

    clientes = []
    for i in range(1, cantidad + 1):
        nom = f"{random.choice(nombres)} {random.choice(apellidos)} {random.choice(apellidos)}"
        ciudad, pais = random.choice(ciudades)
        clientes.append({
            "codigo_cliente": f"CLI-{i:05d}",
            "nombre_cliente": nom,
            "segmento": random.choice(segmentos),
            "ciudad": ciudad,
            "pais": pais,
            "canal_adquisicion": random.choice(canales),
            "antiguedad_anios": random.randint(1, 15)
        })

    dfClientes = pd.DataFrame(clientes)
    dfClientes.to_sql("dim_clientes", con=engine, if_exists="append", index=False, chunksize=1000, method="multi")
    print("[OK] 5,000 registros insertados en dim_clientes.", flush=True)

    # 2. GENERAR PRODUCTOS
    print(f"\n[3/4] Generando e insertando {cantidad} registros en dim_productos...", flush=True)
    categoriasBase = [
        ("Tecnología y Cómputo", ["Laptops Corporativas", "Monitores UltraWide", "Workstations", "Tablets Profesionales", "Servidores Mini"]),
        ("Accesorios y Periféricos", ["Teclados Mecánicos", "Mouses Ergonómicos", "Auriculares con Cancelación", "Docks USB-C", "Webcams 4K"]),
        ("Mobiliario Ergonómico", ["Sillas Ergonómicas", "Escritorios Regulables", "Soportes Articulados", "Cajoneras Móviles"]),
        ("Redes y Conectividad", ["Switches Administrables", "Routers Wi-Fi 6", "Puntos de Acceso", "Firewalls Perimetrales"]),
        ("Software y Licenciamiento", ["Licencia ERP Anual", "Suite de Ciberseguridad", "Plataforma Cloud BI", "Bases de Datos Enterprise"]),
        ("Almacenamiento y Backup", ["Discos SSD NVMe 2TB", "Sistemas NAS 4 Bahías", "Memorias RAM DDR5 64GB", "Unidades Externas Rugged"]),
        ("Oficina y Papelería Pro", ["Destructoras de Papel", "Impresoras Multifuncionales", "Escaners de Alta Velocidad", "Plastificadoras Térmicas"]),
        ("Energía y Protección", ["UPS Online 3kVA", "Reguladores de Voltaje", "Baterías de Respaldo", "Sistemas PDU"])
    ]
    estados = ["Activo", "Activo", "Activo", "Lanzamiento", "Descontinuado"]

    productos = []
    for i in range(1, cantidad + 1):
        catNom, subcats = random.choice(categoriasBase)
        subcatNom = random.choice(subcats)
        sku = f"SKU-{i:05d}"
        nombreProd = f"{subcatNom} Mod. {random.choice(['Alpha', 'Pro', 'Ultra', 'Elite', 'Prime', 'Edge'])} #{random.randint(100, 999)}"
        costo = round(random.uniform(15.0, 1500.0), 2)
        margen = random.uniform(1.30, 1.80)
        precioBase = round(costo * margen, 2)

        productos.append({
            "codigo_sku": sku,
            "nombre_producto": nombreProd,
            "categoria": catNom,
            "subcategoria": subcatNom,
            "costo_unitario": costo,
            "precio_venta_base": precioBase,
            "estado": random.choice(estados)
        })

    dfProductos = pd.DataFrame(productos)
    dfProductos.to_sql("dim_productos", con=engine, if_exists="append", index=False, chunksize=1000, method="multi")
    print("[OK] 5,000 registros insertados en dim_productos.", flush=True)

    # 3. GENERAR TRANSACCIONES EN FACT_VENTAS
    print(f"\n[4/4] Generando e insertando {cantidad} transacciones en fact_ventas...", flush=True)
    sucursales = [
        "Sucursal Central Corporativa", "Sucursal Financiera Norte", "Sucursal Tecnológica Sur",
        "Sucursal Plaza Este", "Sucursal Centro Histórico", "Sucursal Mall Las Condes",
        "Sucursal E-Commerce Directo", "Sucursal Zona Franca"
    ]
    metodosPago = ["Transferencia Bancaria B2B", "Tarjeta de Crédito Corporativa", "Orden de Compra 30 Días", "Pago en Línea", "Crédito Documentario"]
    
    fechaInicio = datetime(2024, 1, 1)
    diasRango = 730

    ventas = []
    for i in range(1, cantidad + 1):
        idCliente = random.randint(1, cantidad)
        idProducto = random.randint(1, cantidad)
        prodRef = productos[idProducto - 1]
        costoUnit = prodRef["costo_unitario"]
        precioBase = prodRef["precio_venta_base"]

        precioReal = round(precioBase * random.uniform(0.95, 1.05), 2)
        descuentoPct = round(random.choice([0.0, 0.0, 5.0, 10.0, 15.0, 20.0]), 2)
        cantidadUnid = random.choices([1, 2, 3, 4, 5, 8, 12, 20], weights=[50, 20, 12, 8, 5, 3, 1, 1])[0]

        montoBruto = round(precioReal * cantidadUnid, 2)
        montoTotal = round(montoBruto * (1 - descuentoPct / 100.0), 2)
        costoTotal = round(costoUnit * cantidadUnid, 2)
        margenBruto = round(montoTotal - costoTotal, 2)

        fechaTransaccion = fechaInicio + timedelta(
            days=random.randint(0, diasRango),
            hours=random.randint(8, 20),
            minutes=random.randint(0, 59)
        )

        ventas.append({
            "numero_orden": f"ORD-{i:05d}",
            "id_cliente": idCliente,
            "id_producto": idProducto,
            "fecha_venta": fechaTransaccion,
            "sucursal": random.choice(sucursales),
            "metodo_pago": random.choice(metodosPago),
            "cantidad": cantidadUnid,
            "precio_unitario": precioReal,
            "descuento_porcentaje": descuentoPct,
            "monto_total": montoTotal,
            "costo_total": costoTotal,
            "margen_bruto": margenBruto
        })

    dfVentas = pd.DataFrame(ventas)
    dfVentas.to_sql("fact_ventas", con=engine, if_exists="append", index=False, chunksize=1000, method="multi")
    print("[OK] 5,000 registros insertados en fact_ventas.", flush=True)

def verificarResultados(engine):
    print("\n================ VERIFICACION DE INTEGRIDAD ================", flush=True)
    with engine.connect() as con:
        cntClientes = con.execute(text("SELECT COUNT(*) FROM dim_clientes;")).scalar()
        cntProductos = con.execute(text("SELECT COUNT(*) FROM dim_productos;")).scalar()
        cntVentas = con.execute(text("SELECT COUNT(*) FROM fact_ventas;")).scalar()
        
        print(f"- Registros en dim_clientes : {cntClientes:,}", flush=True)
        print(f"- Registros en dim_productos: {cntProductos:,}", flush=True)
        print(f"- Registros en fact_ventas  : {cntVentas:,}", flush=True)

        resJoin = con.execute(text("""
            SELECT 
                c.segmento, 
                p.categoria, 
                COUNT(*) AS ordenes, 
                ROUND(CAST(SUM(v.monto_total) AS NUMERIC), 2) AS total_facturado
            FROM fact_ventas v
            JOIN dim_clientes c ON v.id_cliente = c.id_cliente
            JOIN dim_productos p ON v.id_producto = p.id_producto
            GROUP BY c.segmento, p.categoria
            ORDER BY total_facturado DESC
            LIMIT 3;
        """)).fetchall()

        print("\nPrueba de JOIN en estrella ejecutada correctamente:", flush=True)
        for fila in resJoin:
            print(f"  * Segmento: {fila[0]} | Categoria: {fila[1]} | Ordenes: {fila[2]} | Total: ${fila[3]:,.2f}", flush=True)
    print("============================================================\n", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Poblar tablas relacionales dim_clientes, dim_productos y fact_ventas.")
    parser.add_argument("--motor", choices=["postgres", "sqlite"], help="Fuerza el motor de destino (postgres o sqlite).")
    args = parser.parse_args()

    engine, motor = obtenerMotorConexion(args.motor)
    crearEsquemaTablas(engine, motor)
    generarYInsertarDatos(engine, cantidad=5000)
    verificarResultados(engine)
