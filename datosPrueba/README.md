# Carpeta de Datasets de Prueba | Cubix

Esta carpeta contiene archivos de datos de prueba diseñados para evaluar y demostrar las capacidades del sistema **Cubix (Sistema de Inteligencia Analítica y Cubos OLAP)**.

---

## 📁 Archivos Disponibles

### 1. `ventas_10000.xlsx`
* **Descripción:** Libro de Excel con **10,000 registros transaccionales** simulados de ventas comerciales.
* **Columnas incluidas:**
  - `numero_venta`: Identificador único de orden (ej. `VTA-000001`).
  - `fecha_venta`: Marca temporal de la transacción (año 2025).
  - `sucursal`: Nombre de la sucursal emisora (7 sucursales distintas).
  - `vendedor`: Nombre del agente comercial (10 vendedores).
  - `producto`: Nombre del producto transaccionado (15 artículos de tecnología, oficina y mobiliario).
  - `categoria`: Clasificación del producto (`Electrónica`, `Accesorios`, `Audio`, `Oficina`, etc.).
  - `precio_unitario`: Precio de venta unitario.
  - `cantidad`: Unidades comercializadas.
  - `monto_total`: Monto total de la venta (`precio_unitario * cantidad`).

---

## 🚀 ¿Cómo usar este archivo en el DEMO en Vivo?

Cualquier persona que acceda al DEMO en Render puede probar el motor de ingesta ultrarrápida:

1. Descarga el archivo `ventas_10000.xlsx` desde este repositorio en GitHub a tu computadora.
2. Inicia sesión en el DEMO con las credenciales de prueba (`admin` / `admin` o `analista` / `analista`).
3. Ve al menú lateral **Ingesta de Datos** (`/ingesta`).
4. En el panel **Ingesta desde Excel**, selecciona y sube el archivo `ventas_10000.xlsx`.
5. Observa cómo el motor basado en Rust (**Calamine**) procesa las 10,000 filas en menos de 2 segundos y las convierte a formato columnar **Apache Parquet (ZSTD)**.
6. Ve al **Explorador Analítico** (`/explorador`) para consultar agregaciones instantáneas, generar gráficos y exportar a Excel.
