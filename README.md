# Cubix - Sistema de Inteligencia Analítica y Cubos OLAP Multidimensionales

<p align="center">
  <img src="sistemaAnalitica/app/static/img/logo.svg" alt="Cubix Logo" width="150" height="150">
</p>

<p align="center">
  <b>Plataforma empresarial de inteligencia de datos, modelado One Big Table (OBT) y análisis multidimensional en tiempo real.</b><br>
  Construida con <b>FastAPI</b>, <b>DuckDB Vectorizado</b>, <b>Apache Parquet (ZSTD)</b>, <b>Calamine (Rust)</b> y <b>Supabase PostgreSQL</b>.<br>
  <i>Desplegada en producción en <b>Render</b> con persistencia y catálogo relacional en <b>Supabase</b>.</i>
</p>

---

## 🌐 Acceso al DEMO en Vivo (Render)

La plataforma se encuentra completamente desplegada, operativa y accesible en internet para pruebas inmediatas en la nube:

* 🔗 **URL de la Aplicación en Producción:** [https://cuboanalitico.onrender.com](https://cuboanalitico.onrender.com) *(o la URL de tu Web Service activo en Render)*
* 🟢 **Estado del Servicio:** En línea (24/7 con SSL/HTTPS automático).
* 💻 **Compatibilidad:** Accesible desde cualquier navegador web moderno (Chrome, Edge, Firefox, Safari) sin requerir instalación previa.

### 👥 Usuarios y Contraseñas de Prueba para el DEMO

Para evaluar los diferentes niveles de acceso, perfiles de seguridad (**RBAC**) y funcionalidades del sistema, utiliza las siguientes credenciales preconfiguradas:

| Usuario | Contraseña | Rol Asignado | Pantallas Habilitadas | ¿Qué puedes evaluar en el DEMO? |
| :--- | :--- | :--- | :--- | :--- |
| **`admin`** | `admin` | **Administrador** | **Acceso Total (8 pantallas):** Inicio, Ingesta OBT, Explorador OLAP, Gobernanza y Roles, Configuración de Vistas, Gestión de Cubos, Gestión de Vistas y Depuración de Objetos. | Gestión integral de usuarios, asignación de pantallas, control de permisos, ingesta de archivos y administración del catálogo. |
| **`analista`** | `analista` | **Analista de Datos** | **Acceso Analítico (7 pantallas):** Inicio, Ingesta OBT, Explorador OLAP, Configuración de Vistas, Gestión de Cubos, Gestión de Vistas y Depuración. | Carga masiva de datos, creación de cubos multidimensionales, configuración de gráficos y exploración analítica con métricas calculadas. |
| **`operador`** | `operador` | **Operador** | **Acceso Operativo (2 pantallas):** Inicio y Explorador OLAP. | Consulta de tableros ejecutivos, interacción con filtros dinámicos y exportación directa de reportes a Excel con un clic. |

---

## 📋 Tabla de Contenidos

1. [a. Descripción General del Proyecto](#a-descripción-general-del-proyecto)
2. [b. Stack Tecnológico Utilizado](#b-stack-tecnológico-utilizado)
3. [c. Instalación y Ejecución Local y en la Nube](#c-instalación-y-ejecución)
   - [3.1 Levantamiento Local Rápido (Zero-Config / SQLite Automático)](#31-levantamiento-local-rápido-zero-config--sqlite-automático)
   - [3.2 Conexión a Supabase PostgreSQL](#32-conexión-a-supabase-postgresql)
   - [3.3 Despliegue en Render](#33-despliegue-en-producción-render--supabase)
4. [d. Estructura del Proyecto](#d-estructura-del-proyecto)
5. [e. Funcionalidades Principales](#e-funcionalidades-principales)
6. [f. Modelo Relacional de Cubos y Consultas SQL de Prueba (5,000 Registros)](#f-modelo-relacional-de-cubos-y-consultas-sql-de-prueba-5000-registros)
7. [g. Dataset de Prueba en Git (`datosPrueba/`)](#g-dataset-de-prueba-en-git-datosprueba)
8. [Especificación de Variables de Entorno](#-especificación-de-variables-de-entorno)
9. [Catálogo de Endpoints API](#-catálogo-de-endpoints-api)

---

## a. Descripción General del Proyecto

**Cubix** es una plataforma de analítica de autoservicio empresarial diseñada para superar las limitaciones de rendimiento, memoria y costos de las herramientas tradicionales de Business Intelligence y las hojas de cálculo convencionales.

### Problema que Resuelve
En entornos corporativos, el análisis de grandes volúmenes de datos suele enfrentar dos barreras críticas:
1. **Lentitud y colapso en hojas de cálculo:** Archivos de Excel con cientos de miles de registros saturan la memoria RAM, ralentizan los equipos y provocan bloqueos en cálculos complejos o cruces relacionales (`BUSCARV` / `XLOOKUP`).
2. **Altos costos y complejidad de plataformas BI tradicionales:** Las soluciones convencionales requieren licencias elevadas por usuario, servidores dedicados costosos y procesos ETL rígidos.

### La Solución Cubix
Cubix desacopla completamente el almacenamiento transaccional de la capa de consulta analítica mediante el modelado **One Big Table (OBT)** y motores en memoria de ultra alto rendimiento:
* **Ingesta instantánea:** Extrae libros de cálculo masivos en fracciones de segundo utilizando bindings nativos de Rust (`python-calamine`).
* **Almacenamiento columnar de alta compresión:** Materializa los datos limpios en formato **Apache Parquet** comprimido con **ZSTD**, reduciendo drásticamente el espacio en disco y acelerando lecturas.
* **Consultas OLAP vectorizadas:** Emplea **DuckDB** para procesar agregaciones multidimensionales (`SUM`, `AVG`, `MAX`, `MIN`, `COUNT DISTINCT`) en tiempo real directamente sobre los archivos Parquet, sin necesidad de cargar DataFrames completos en la RAM.
* **Gobernanza y Seguridad:** Control de acceso basado en roles (**RBAC**), matriz de excepciones y seguridad a nivel de fila (**Row-Level Security - RLS**) gestionada sobre **Supabase PostgreSQL**.

```text
  +-------------------------------------------------------------------------+
  |                             FUENTES DE DATOS                            |
  |  - Libros Excel (.xlsx) [Rust Calamine - Miles de filas en < 1 seg]     |
  |  - Motores SQL en Vivo (PostgreSQL, Supabase, SQL Server con Throttling)|
  |  - Data Lake Externo (Ingesta Masiva Directa a Parquet)                 |
  +------------------------------------+------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |                           INGESTA Y MODELADO OBT                        |
  |  - Detección automática de hojas con estructura idéntica (UNION ALL)    |
  |  - Cruces Relacionales Multi-Key (JOINs) y Diagrama de Estrella         |
  |  - Detección preventiva de explosión de filas (Fan-Out Risk Analysis)   |
  |  - Tipado estricto y perfilado semántico de contratos de datos          |
  +------------------------------------+------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |                    ALMACENAMIENTO COLUMNAR DATA LAKE                    |
  |  - Archivos Apache Parquet comprimidos con ZSTD nivel analítico         |
  |  - Almacenamiento local optimizado o Cloud Storage                      |
  +------------------------------------+------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |                   MOTOR ANALÍTICO DUCKDB VECTORIZADO                    |
  |  - Agregaciones OLAP multidimensionales en memoria sub-segundo          |
  |  - Ejecución paralela sobre hilos sin bloqueo de GIL                    |
  |  - Filtros dinámicos, segmentación y Drill-Down jerárquico              |
  +------------------------------------+------------------------------------+
                                       |
                                       v
  +-------------------------------------------------------------------------+
  |                      GOBERNANZA Y PRESENTACIÓN WEB                      |
  |  - Catálogo de Metadatos y Seguridad en Supabase PostgreSQL             |
  |  - FastAPI (Backend Asíncrono) + Tailwind CSS + Plotly Interactivo      |
  |  - Seguridad basada en Roles (RBAC), Permisos de Vista y Row-Level Sec. |
  +-------------------------------------------------------------------------+
```

---

## b. Stack Tecnológico Utilizado

| Componente / Capa | Tecnología | Justificación y Rol en el Sistema |
| :--- | :--- | :--- |
| **Backend & Servidor Web** | **FastAPI** (Python 3.11+) | Framework web asíncrono de alto rendimiento (ASGI), organizado en routers modulares para autenticación, ingesta, administración y OLAP. |
| **Servidor ASGI** | **Uvicorn** | Servidor web ASGI para producción, ligero y con soporte para recarga en caliente y manejo concurrente. |
| **Motor Analítico OLAP** | **DuckDB** | Motor columnar vectorizado embebido que ejecuta consultas SQL complejas directamente sobre archivos Parquet sin saturar la memoria RAM. |
| **Almacenamiento Columnar** | **Apache Parquet (PyArrow + ZSTD)** | Formato abierto de almacenamiento columnar optimizado para analítica, con compresión Zstandard de alto ratio. |
| **Extracción de Datos Excel** | **python-calamine (Rust)** | Bindings nativos de Rust que permiten leer libros de Excel (.xlsx/.xlsb) a velocidades hasta 10x superiores a librerías Python tradicionales. |
| **Base de Datos & Catálogo** | **Supabase (PostgreSQL 15)** | Persistencia relacional en la nube para el catálogo de cubos, usuarios, roles, vistas analíticas, excepciones y logs de auditoría. |
| **ORM & Mapeo Relacional** | **SQLAlchemy 2.0** | Abstracción de datos para gestionar modelos relacionales tanto en Supabase PostgreSQL como en SQLite local. |
| **Frontend & UI** | **Jinja2 + Tailwind CSS** | Vistas web renderizadas del lado del servidor con diseño responsivo, estética corporativa profesional y componentes interactivos. |
| **Visualización de Datos** | **Plotly.js / Plotly Python** | Generación de gráficos analíticos interactivos dinámicos (barras, líneas, dispersión) renderizados en el explorador. |
| **Seguridad Criptográfica** | **PBKDF2-HMAC-SHA256** | Algoritmo de derivación de claves con salt dinámico de 16 bytes y 100,000 iteraciones para almacenamiento seguro de credenciales. |
| **Integración IA (Opcional)** | **Model Context Protocol (MCP)** | Servidor MCP integrado (`servidorMcpSql.py`) para conexión y análisis contextual mediante agentes inteligentes. |
| **Plataforma de Hosting** | **Render** | Despliegue de la aplicación web como Web Service con conexión HTTPS automática y escalabilidad gestionada. |

---

## c. Instalación y Ejecución

### 3.1 Levantamiento Local Rápido (Zero-Config / SQLite Automático)

> [!TIP]
> **Zero-Config:** No es obligatorio configurar ningún archivo `.env` para probar el sistema en tu computadora. El sistema detecta automáticamente la ausencia de variables de entorno y utiliza una base de datos local SQLite (`controlAnalitica.db`), inicializando y sembrando todas las tablas y usuarios de prueba al arrancar.

1. **Clonar el repositorio y entrar en la carpeta del proyecto:**
   ```bash
   git clone https://github.com/TU_USUARIO/TU_REPOSITORIO.git
   cd export
   ```

2. **Crear y activar el entorno virtual:**
   ```bash
   # En Windows:
   python -m venv .venv
   .\.venv\Scripts\activate

   # En Linux / macOS:
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Poblar las tablas relacionales de prueba (5,000 registros cada una):**
   ```bash
   python baseDatos/crearTablasRelacionadas.py --motor sqlite
   ```

5. **Iniciar el servidor:**
   * **En Windows con 1 clic:** Doble clic en `iniciarSistema.bat`.
   * **Por terminal:**
     ```bash
     uvicorn sistemaAnalitica.app.servidor:app --host 0.0.0.0 --port 8000 --reload
     ```
   * Abre tu navegador en `http://localhost:8000` e inicia sesión con `admin` / `admin`.

---

### 3.2 Conexión a Supabase PostgreSQL

Si deseas ejecutar localmente pero conectado a la base de datos central en Supabase:

1. Copia la plantilla de entorno:
   ```bash
   copy .env.example .env   # En Windows
   cp .env.example .env     # En Linux / Mac
   ```
2. Edita el archivo `.env` e ingresa tu cadena de conexión:
   ```env
   DATABASE_URL=postgresql://postgres.TU_REF:TU_PASSWORD@aws-0-us-west-2.pooler.supabase.com:5432/postgres
   ENTORNO=desarrollo
   SECRET_KEY=clave_secreta_super_segura
   ```
3. Si deseas regenerar o poblar las 3 tablas relacionales en Supabase:
   ```bash
   python baseDatos/crearTablasRelacionadas.py --motor postgres
   ```

---

### 3.3 Despliegue en Producción (Render + Supabase)

El proyecto está optimizado para ejecutarse nativamente en **Render**:

1. En el panel de Render, crea un **Web Service** conectado a tu repositorio de GitHub.
2. Configura los parámetros de ejecución:
   * **Runtime:** `Python 3`
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `uvicorn sistemaAnalitica.app.servidor:app --host 0.0.0.0 --port $PORT`
3. Agrega las variables de entorno en Render:
   * `DATABASE_URL`: Cadena de conexión provista por Supabase (Connection Pooling puerto 5432 o 6543).
   * `ENTORNO`: `produccion`
   * `SECRET_KEY`: Cadena criptográfica aleatoria para la firma de sesiones.

---

## d. Estructura del Proyecto

```text
export/
├── .env.example                 # Plantilla de variables de entorno (sin credenciales)
├── .gitignore                   # Reglas estrictas de exclusión (incluye datosPrueba/)
├── .dockerignore                # Exclusiones para imágenes Docker
├── Dockerfile                   # Contenedor listo para producción en la nube
├── README.md                    # Documentación técnica maestra del proyecto
├── STARTGUIDE.md                # Especificaciones internas de bajo nivel
├── requirements.txt             # Dependencias del ecosistema Python
├── iniciarSistema.bat           # Script de inicio en 1 clic para Windows
│
├── baseDatos/                   # Scripts de gestión relacional y sembrado
│   ├── crearTablasRelacionadas.py # Generador de dim_clientes, dim_productos y fact_ventas (5,000 c/u)
│   ├── recrearBaseDatos.py      # Purga y regeneración limpia del esquema en Supabase / SQLite
│   ├── generarDatosPrueba.py    # Generador complementario de tickets help desk y ventas Excel
│   ├── limpiarCatalogo.py       # Mantenimiento y depuración de registros huérfanos
│   ├── verificarTodo.py         # Diagnóstico integral de conectividad e integridad
│   └── esquemas/                # DDL SQL de referencia (PostgreSQL, SQLite, SQL Server)
│
├── datosPrueba/                 # Datasets de prueba incluidos en Git
│   ├── README.md                # Guía de uso del dataset para evaluadores del DEMO
│   └── ventas_10000.xlsx        # 10,000 registros para pruebas de ingesta ultrarrápida
│
└── sistemaAnalitica/            # Código fuente principal de la plataforma
    ├── almacenamiento/          # Almacenamiento local del Data Lake
    │   ├── controlAnalitica.db  # Base relacional SQLite local (auto-generada)
    │   └── parquets/            # Archivos .parquet generados dinámicamente
    │
    ├── app/                     # Capa web y controladores FastAPI
    │   ├── servidor.py          # Punto de entrada FastAPI y middlewares de sesión
    │   ├── dependencias.py      # Middleware de autenticación y RBAC
    │   ├── routers/             # Endpoints (autenticación, explorador, ingesta, admin)
    │   ├── static/              # Recursos estáticos (Tailwind CSS, JS, iconos SVG)
    │   └── templates/           # Vistas Jinja2 renderizadas con Tailwind CSS
    │
    └── modulos/                 # Lógica de dominio y motores analíticos
        ├── ingesta/             # Lector Calamine Rust, generador OBT, SQL en vivo
        ├── motorAnalitico/      # Motor DuckDB OLAP, agregaciones y exportador
        ├── seguridad/           # Modelos SQLAlchemy, sesiones de BD y RBAC
        ├── autenticacion/       # Estrategias de login (Local PBKDF2, LDAP, SOAP)
        └── mcp/                 # Servidor Model Context Protocol para IA
```

---

## e. Funcionalidades Principales

Cubix ofrece un flujo integral de datos desde la captura hasta la toma de decisiones analíticas:

### 1. Ingesta Inteligente y Modelado One Big Table (OBT)
* **Extracción Masiva Instantánea con Rust:** Lectura de archivos `.xlsx` mediante `python-calamine`, procesando miles de filas en sub-segundos sin sobrecarga de memoria.
* **Detección y Unificación Automática de Hojas:** Detección de hojas con esquemas idénticos para aplicar `UNION ALL` automático con trazabilidad de `hoja_origen`.
* **Cruce Relacional Multi-Hoja (Diagrama en Estrella):** Enlace de tablas de hechos con múltiples dimensiones satélites mediante llaves compuestas (`LEFT`, `INNER`, `OUTER`).
* **Prevención de Riesgo Fan-Out:** Análisis predictivo de cardinalidad antes de materializar el cubo, alertando si un cruce multiplicará artificialmente el volumen de filas.
* **Consultas SQL en Vivo con Throttling:** Conexión a motores relacionales externos con muestreo automático (`LIMIT 10`) y ventana de refresco controlado de 5 minutos para proteger bases operacionales contra sobrecargas.

### 2. Motor Analítico OLAP Vectorizado (DuckDB + Parquet)
* **Consultas Vectorizadas en Memoria:** Ejecución de consultas analíticas multidimensionales directamente sobre los archivos Parquet en sub-segundos, aprovechando paralelismo a nivel de hilos sin cuellos de botella del GIL de Python.
* **Métricas Sumables y No Sumables:** Soporte para agregaciones aditivas (`SUM`) y no aditivas (`AVG`, `MAX`, `MIN`, `COUNT DISTINCT`), además de columnas calculadas.
* **Filtros Dinámicos y Drill-Down:** Capacidad de segmentar por cualquier dimensión en tiempo real, ordenar dinámicamente y paginar grandes volúmenes de resultados.

### 3. Gobernanza, Seguridad y Control de Acceso Granular
* **Control de Acceso Basado en Roles (RBAC):** Tres perfiles institucionales diferenciados (`Administrador`, `Analista`, `Operador`) que determinan los módulos y pantallas visibles.
* **Matriz de Excepciones Usuario-Vista:** Mecanismo formal de concesión o revocación de acceso a vistas específicas independiente del rol:
  $$\text{AccesoEfectivo} = (\text{AccesoPorRol} \land \neg \text{ExcepcionRevocada}) \lor \text{ExcepcionConcedida}$$
* **Seguridad a Nivel de Fila (Row-Level Security - RLS):** Inyección transparente de filtros SQL automáticos según la identidad del usuario (ejemplo: un operador solo visualiza datos correspondientes a su sucursal o región).
* **Auditoría de Operaciones:** Registro detallado en base de datos de eventos del sistema y eliminaciones de objetos.

### 4. Exploración Visual y Exportación
* **Tableros Interactivos con Plotly:** Gráficos dinámicos interactivos sincronizados con la consulta del cubo.
* **Exportación de Reportes:** Descarga directa de resultados filtrados en formato **Excel (.xlsx)** estructurado y en **CSV**.

---

## f. Modelo Relacional de Cubos y Consultas SQL de Prueba (5,000 Registros)

En la base de datos (Supabase PostgreSQL y SQLite local) se encuentran creadas y pobladas **tres tablas relacionales organizadas en Diagrama de Estrella (Star Schema)** con exactamente **5,000 registros en cada tabla**, generadas mediante el script `baseDatos/crearTablasRelacionadas.py`:

```mermaid
erDiagram
    dim_clientes ||--o{ fact_ventas : "id_cliente (1:N)"
    dim_productos ||--o{ fact_ventas : "id_producto (1:N)"

    dim_clientes {
        int id_cliente PK
        string codigo_cliente
        string nombre_cliente
        string segmento
        string ciudad
        string pais
        string canal_adquisicion
        int antiguedad_anios
    }

    dim_productos {
        int id_producto PK
        string codigo_sku
        string nombre_producto
        string categoria
        string subcategoria
        float costo_unitario
        float precio_venta_base
        string estado
    }

    fact_ventas {
        int id_venta PK
        string numero_orden
        int id_cliente FK
        int id_producto FK
        timestamp fecha_venta
        string sucursal
        string metodo_pago
        int cantidad
        float precio_unitario
        float descuento_porcentaje
        float monto_total
        float costo_total
        float margen_bruto
    }
```

### 🔍 Consultas SQL (SELECT) de Prueba Listas para Ejecutar

Puedes ejecutar estas consultas directamente en el **SQL Editor de Supabase**, en tu cliente relacional favorito (DBeaver, pgAdmin) o en el módulo de **SQL en Vivo** de Cubix:

#### Consulta 1: Resumen Operativo de Ventas y Márgenes por Sucursal y Medio de Pago
Calcula el total facturado, margen bruto total y margen promedio agrupado por sucursal física:
```sql
SELECT 
    sucursal,
    metodo_pago,
    COUNT(*) AS total_transacciones,
    SUM(cantidad) AS unidades_vendidas,
    ROUND(CAST(SUM(monto_total) AS NUMERIC), 2) AS facturacion_total,
    ROUND(CAST(SUM(margen_bruto) AS NUMERIC), 2) AS ganancia_bruta_total,
    ROUND(CAST(AVG(margen_bruto) AS NUMERIC), 2) AS margen_promedio_por_orden
FROM fact_ventas
GROUP BY sucursal, metodo_pago
ORDER BY facturacion_total DESC;
```

#### Consulta 2: Cruzada Multidimensional en Estrella (Ventas + Clientes + Productos)
Une las tres tablas para analizar la rentabilidad cruzando el **segmento de cliente** con la **categoría de producto**:
```sql
SELECT 
    c.segmento AS segmento_cliente,
    p.categoria AS categoria_producto,
    COUNT(v.id_venta) AS ordenes_realizadas,
    SUM(v.cantidad) AS volumen_unidades,
    ROUND(CAST(SUM(v.monto_total) AS NUMERIC), 2) AS ingresos_totales,
    ROUND(CAST(SUM(v.costo_total) AS NUMERIC), 2) AS costo_mercancia,
    ROUND(CAST(SUM(v.margen_bruto) AS NUMERIC), 2) AS utilidad_neta,
    ROUND(CAST((SUM(v.margen_bruto) / NULLIF(SUM(v.monto_total), 0)) * 100 AS NUMERIC), 2) AS pct_rentabilidad
FROM fact_ventas v
INNER JOIN dim_clientes c ON v.id_cliente = c.id_cliente
INNER JOIN dim_productos p ON v.id_producto = p.id_producto
GROUP BY c.segmento, p.categoria
ORDER BY ingresos_totales DESC;
```

#### Consulta 3: Top 10 Clientes por Volumen de Facturación y Cobertura Geográfica
Identifica a los clientes con mayor valor comercial acumulado y su ubicación:
```sql
SELECT 
    c.codigo_cliente,
    c.nombre_cliente,
    c.segmento,
    c.ciudad,
    c.pais,
    COUNT(v.id_venta) AS total_pedidos,
    ROUND(CAST(SUM(v.monto_total) AS NUMERIC), 2) AS monto_acumulado_comprado
FROM fact_ventas v
INNER JOIN dim_clientes c ON v.id_cliente = c.id_cliente
GROUP BY c.codigo_cliente, c.nombre_cliente, c.segmento, c.ciudad, c.pais
ORDER BY monto_acumulado_comprado DESC
LIMIT 10;
```

#### Consulta 4: Rendimiento por Categoría y Subcategoría de Producto
Permite identificar las líneas de producto con mayor penetración de clientes únicos y mayor volumen transaccionado:
```sql
SELECT 
    p.categoria,
    p.subcategoria,
    COUNT(DISTINCT v.id_cliente) AS clientes_unicos_compradores,
    COUNT(v.id_venta) AS numero_ventas,
    SUM(v.cantidad) AS total_unidades_comercializadas,
    ROUND(CAST(SUM(v.monto_total) AS NUMERIC), 2) AS facturacion_total,
    ROUND(CAST(AVG(v.descuento_porcentaje) AS NUMERIC), 2) AS descuento_promedio_otorgado
FROM fact_ventas v
INNER JOIN dim_productos p ON v.id_producto = p.id_producto
GROUP BY p.categoria, p.subcategoria
ORDER BY facturacion_total DESC;
```

---

## g. Dataset de Prueba en Git (`datosPrueba/`)

Para facilitar la evaluación de la ingesta de archivos en el **DEMO en Render** o en local, el repositorio incluye en la carpeta [`datosPrueba/`](file:///c:/Users/MAURICIO/Documents/Antigravity/CuboAnalitico/export/datosPrueba) el dataset:

* 📄 **Archivo:** `datosPrueba/ventas_10000.xlsx`
* 📊 **Volumen:** 10,000 registros transaccionales reales.
* 📋 **Columnas:** `numero_venta`, `fecha_venta`, `sucursal`, `vendedor`, `producto`, `categoria`, `precio_unitario`, `cantidad`, `monto_total`.

### ¿Cómo probarlo en el DEMO de Render?
1. Descarga el archivo [`ventas_10000.xlsx`](datosPrueba/ventas_10000.xlsx) desde este repositorio a tu computadora.
2. Ingresa al [DEMO en Render](https://cuboanalitico.onrender.com) con el usuario `admin` o `analista`.
3. Dirígete a **Ingesta de Datos** (`/ingesta`).
4. Arrastra o selecciona `ventas_10000.xlsx`. El motor Calamine (Rust) procesará las 10,000 filas en menos de 2 segundos generando un archivo Parquet optimizado.
5. Pasa al **Explorador Analítico** (`/explorador`) para filtrar dinámicamente y generar gráficos instantáneos.

---

## 🔐 Especificación de Variables de Entorno

| Variable | Tipo | Requerida | Valor por Defecto | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `DATABASE_URL` | String | No (usa SQLite por defecto) | `sqlite:///sistemaAnalitica/...` | Cadena de conexión SQLAlchemy a Supabase PostgreSQL o SQLite local. |
| `PORT` | Integer | No | `8000` (Local) / `$PORT` (Render) | Puerto TCP de escucha del servidor web. |
| `HOST` | String | No | `0.0.0.0` | Dirección IP de enlace de la aplicación. |
| `ENTORNO` | String | No | `desarrollo` (Local) / `produccion` | Entorno de ejecución (`desarrollo` / `produccion`). |
| `SECRET_KEY` | String | No | *(Autogenerada)* | Clave para firma criptográfica de cookies de sesión segura. |

---

## 📡 Catálogo de Endpoints API

### Autenticación y Control de Sesión
* `GET /login`: Vista web del formulario de inicio de sesión.
* `POST /login`: Procesamiento de credenciales y generación de cookie segura de sesión.
* `GET /logout`: Revocación de sesión activa y redirección.

### Ingesta y Modelado de Datos
* `GET /ingesta`: Panel de control interactivo de ingesta de datos.
* `POST /api/ingesta/excel/analizar-libro-completo`: Análisis multivariable de hojas con Calamine (Rust).
* `POST /api/ingesta/procesar-excel`: Materialización del dataset a archivo Parquet OBT con compresión ZSTD.
* `POST /api/sql/probar`: Prueba de conectividad relacional con muestreo seguro (`LIMIT 10`).
* `POST /api/sql/procesar-cubo`: Extracción por lotes desde motor SQL hacia el Data Lake Parquet.
* `POST /api/ingesta/crear-cubo-compuesto`: Construcción de cubos multidimensionales mediante JOINs y validación Fan-Out.

### Motor Analítico OLAP
* `GET /explorador`: Interfaz visual de exploración y análisis multidimensional.
* `POST /api/olap/consultar`: Ejecución de consultas analíticas vectorizadas en tiempo real con DuckDB.
* `POST /api/olap/exportar`: Exportación de consultas a formatos XLSX y CSV.

### Seguridad, Vistas y Gobernanza
* `GET /seguridad`: Matriz RBAC, gestión de usuarios, roles y excepciones.
* `GET /administracion/cubos`: Catálogo y mantenimiento de archivos físicos Parquet.
* `GET /administracion/vistas`: Diseñador y asignador de vistas analíticas.

---

<p align="center">
  <b>Cubix</b> — Plataforma de Inteligencia Analítica Corporativa
</p>
