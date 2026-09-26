"""
Script para:
1. Generar export/datosPrueba/ventas_10000.xlsx con 10,000 registros de ventas.
2. Crear y poblar la tabla ingesta_test en Supabase con 10,000 tickets de help desk.
"""
import os
import random
from datetime import datetime, timedelta
import pandas as pd
from sqlalchemy import create_engine, text

DIR_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_DATOS_PRUEBA = os.path.join(DIR_BASE, "datosPrueba")
os.makedirs(DIR_DATOS_PRUEBA, exist_ok=True)
ARCHIVO_EXCEL = os.path.join(DIR_DATOS_PRUEBA, "ventas_10000.xlsx")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres.flposnfuyrkenlhiguaq:Zaq12wsxcv%2B%2B123789456@aws-0-us-west-2.pooler.supabase.com:5432/postgres"
)

def generarExcelVentas():
    print(f"Generando {ARCHIVO_EXCEL}...")
    random.seed(42)
    sucursales = ["Sucursal Central", "Sucursal Norte", "Sucursal Sur", "Sucursal Este", "Sucursal Oeste", "Sucursal Aeropuerto", "Sucursal Mall Plaza"]
    vendedores = [
        "Carlos Mendoza", "Ana Gómez", "Luis Rodríguez", "María Pérez", "Jorge Fernández",
        "Lucía Morales", "Pedro Sánchez", "Valeria Díaz", "Fernando Castro", "Sofía Vargas"
    ]
    productos = [
        ("Laptop Gamer Pro", "Electrónica", 1250.00),
        ("Monitor UltraWide 34\"", "Electrónica", 450.00),
        ("Teclado Mecánico RGB", "Accesorios", 85.00),
        ("Mouse Inalámbrico Ergo", "Accesorios", 45.00),
        ("Auriculares Cancelación Ruido", "Audio", 130.00),
        ("Impresora Láser Multifuncional", "Oficina", 280.00),
        ("Silla Ergonómica Premium", "Muebles", 220.00),
        ("Escritorio Elevable Eléctrico", "Muebles", 390.00),
        ("Disco SSD NVMe 2TB", "Componentes", 160.00),
        ("Memoria RAM 32GB DDR5", "Componentes", 115.00),
        ("Tablet 11 Pulgadas", "Electrónica", 320.00),
        ("Smartphone 5G 256GB", "Telefonía", 650.00),
        ("Cargador Rápido GaN 65W", "Accesorios", 35.00),
        ("Webcam 4K con Micrófono", "Accesorios", 95.00),
        ("Servidor NAS 4 Bahías", "Redes y Servidores", 550.00)
    ]
    
    fechaInicio = datetime(2025, 1, 1)
    diasRango = 365
    
    registros = []
    for i in range(1, 10001):
        numVenta = f"VTA-{i:06d}"
        fecha = (fechaInicio + timedelta(days=random.randint(0, diasRango), hours=random.randint(8, 20), minutes=random.randint(0, 59))).strftime("%Y-%m-%d %H:%M:%S")
        sucursal = random.choice(sucursales)
        vendedor = random.choice(vendedores)
        prod, categoria, precioUnitario = random.choice(productos)
        
        precioFinal = round(precioUnitario * random.uniform(0.95, 1.05), 2)
        cantidad = random.choices([1, 2, 3, 4, 5, 10], weights=[60, 20, 10, 5, 3, 2])[0]
        montoTotal = round(precioFinal * cantidad, 2)
        
        registros.append({
            "numero_venta": numVenta,
            "fecha_venta": fecha,
            "sucursal": sucursal,
            "vendedor": vendedor,
            "producto": prod,
            "categoria": categoria,
            "precio_unitario": precioFinal,
            "cantidad": cantidad,
            "monto_total": montoTotal
        })
        
    df = pd.DataFrame(registros)
    df.to_excel(ARCHIVO_EXCEL, index=False, engine="openpyxl")
    print(f"Excel generado exitosamente con {len(df)} registros en {ARCHIVO_EXCEL}.")

def crearYPoblarIngestaTest():
    print("Conectando a Supabase para crear tabla ingesta_test...")
    engine = create_engine(DATABASE_URL)
    
    with engine.begin() as conexion:
        conexion.execute(text("""
            DROP TABLE IF EXISTS ingesta_test CASCADE;
            CREATE TABLE ingesta_test (
                id SERIAL PRIMARY KEY,
                numero_ticket VARCHAR(50) NOT NULL,
                usuario_solicitante VARCHAR(100) NOT NULL,
                area_solicitante VARCHAR(100) NOT NULL,
                tiempo_atencion_minutos INTEGER NOT NULL,
                fecha_atencion TIMESTAMP NOT NULL,
                area_atendio VARCHAR(100) NOT NULL,
                prioridad VARCHAR(20) NOT NULL,
                estado VARCHAR(20) NOT NULL,
                categoria_problema VARCHAR(100) NOT NULL
            );
        """))
    print("Tabla ingesta_test creada. Generando 10,000 tickets...")
    
    random.seed(99)
    usuarios = [
        "jperez", "mgonzalez", "lrodriguez", "cmartinez", "alopez", 
        "fgomez", "vfernandez", "dgarcia", "etorres", "sramirez",
        "mcastillo", "rherrera", "pnavarro", "kparedes", "jsoto"
    ]
    areasSolicitantes = [
        "Finanzas", "Contabilidad", "Recursos Humanos", "Operaciones",
        "Ventas", "Marketing", "Logística", "Legal", "Auditoría Interna"
    ]
    areasAtencion = [
        "Mesa de Ayuda Nivel 1", "Soporte Técnico Nivel 2", "Infraestructura y Redes",
        "Desarrollo y Sistemas", "Seguridad de la Información", "Base de Datos"
    ]
    prioridades = ["Baja", "Media", "Alta", "Crítica"]
    estados = ["Cerrado", "Resuelto", "En Proceso", "Pendiente Usuario"]
    categorias = [
        "Restablecimiento de Contraseña", "Fallo de Impresora", "Sin Conexión a Red / VPN",
        "Lentitud en Sistema ERP", "Acceso a Carpeta Compartida", "Error en Correo Electrónico",
        "Instalación de Software Aprobado", "Falla de Hardware (Monitor/PC)", "Solicitud Nuevo Equipo",
        "Permisos de Base de Datos"
    ]
    
    fechaInicio = datetime(2025, 1, 1)
    diasRango = 365
    
    tickets = []
    for i in range(1, 10001):
        numTicket = f"TCK-{i:06d}"
        usuario = random.choice(usuarios)
        areaSol = random.choice(areasSolicitantes)
        areaAtn = random.choice(areasAtencion)
        prio = random.choices(prioridades, weights=[30, 45, 20, 5])[0]
        estado = random.choices(estados, weights=[65, 25, 7, 3])[0]
        cat = random.choice(categorias)
        
        if prio == "Crítica":
            tiempoMin = random.randint(15, 120)
        elif prio == "Alta":
            tiempoMin = random.randint(30, 360)
        elif prio == "Media":
            tiempoMin = random.randint(60, 720)
        else:
            tiempoMin = random.randint(120, 1440)
            
        fechaAtencion = (fechaInicio + timedelta(days=random.randint(0, diasRango), hours=random.randint(7, 21), minutes=random.randint(0, 59)))
        
        tickets.append({
            "numero_ticket": numTicket,
            "usuario_solicitante": usuario,
            "area_solicitante": areaSol,
            "tiempo_atencion_minutos": tiempoMin,
            "fecha_atencion": fechaAtencion,
            "area_atendio": areaAtn,
            "prioridad": prio,
            "estado": estado,
            "categoria_problema": cat
        })
        
    dfTickets = pd.DataFrame(tickets)
    
    print("Insertando tickets en Supabase...")
    dfTickets.to_sql("ingesta_test", con=engine, if_exists="append", index=False, chunksize=2000, method="multi")
    
    with engine.connect() as conexion:
        total = conexion.execute(text("SELECT count(*) FROM ingesta_test;")).scalar()
        print(f"Total de registros insertados y confirmados en ingesta_test: {total}")

if __name__ == "__main__":
    generarExcelVentas()
    crearYPoblarIngestaTest()
