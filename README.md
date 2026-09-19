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

## 📋 Tabla de Contenidos

1. [a. Descripción General del Proyecto](#a-descripción-general-del-proyecto)
2. [b. Stack Tecnológico Utilizado](#b-stack-tecnológico-utilizado)
3. [c. Instalación y Ejecución](#c-instalación-y-ejecución)
   - [3.1 Prerrequisitos y Configuración de Variables de Entorno](#31-prerrequisitos-y-configuración-de-variables-de-entorno)
   - [3.2 Ejecución en Entorno Local](#32-ejecución-en-entorno-local)
   - [3.3 Despliegue en Producción (Render + Supabase)](#33-despliegue-en-producción-render--supabase)
   - [3.4 Contenerización con Docker](#34-contenerización-con-docker)
4. [d. Estructura del Proyecto](#d-estructura-del-proyecto)
5. [e. Funcionalidades Principales](#e-funcionalidades-principales)
6. [f. Usuarios y Contraseñas de Prueba](#f-usuarios-y-contraseñas-de-prueba)
7. [Especificación de Variables de Entorno](#-especificación-de-variables-de-entorno)
8. [Catálogo de Endpoints API](#-catálogo-de-endpoints-api)

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

El sistema está construido combinando tecnologías modernas de alto desempeño, garantizando bajo consumo de recursos y alta escalabilidad:

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

### 3.1 Prerrequisitos y Configuración de Variables de Entorno

* **Python:** Versión 3.11 o superior instalada en el sistema.
* **Conexión a Base de Datos:** Cadena de conexión `DATABASE_URL` a Supabase PostgreSQL (o uso del motor local SQLite por defecto).

#### Configurar el archivo `.env`
1. Copie la plantilla base:
   ```bash
   # En Windows (CMD / PowerShell):
   copy .env.example .env

   # En Linux / macOS:
   cp .env.example .env
   ```
2. Configure su cadena de conexión en el archivo `.env`:
   ```env
   # Conexión a Supabase PostgreSQL (Producción / Remota):
   DATABASE_URL=postgresql://postgres.TU_REF:TU_PASSWORD@aws-0-us-west-2.pooler.supabase.com:5432/postgres

   # O conexión local SQLite (Desarrollo sin conexión externa):
   # DATABASE_URL=sqlite:///sistemaAnalitica/almacenamiento/controlAnalitica.db

   PORT=8000
   HOST=0.0.0.0
   ENTORNO=desarrollo
   SECRET_KEY=clave_secreta_para_firma_de_sesion_segura
   ```

---

### 3.2 Ejecución en Entorno Local

1. **Crear y activar el entorno virtual:**
   ```bash
   # Crear entorno virtual
   python -m venv .venv

   # Activar en Windows:
   .\.venv\Scripts\activate

   # Activar en Linux / macOS:
   source .venv/bin/activate
   ```

2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Inicializar y poblar la Base de Datos (Primer uso):**
   ```bash
   # Para Supabase PostgreSQL:
   python baseDatos/recrearBaseDatos.py --motor postgres --forzar
   python baseDatos/generarDatosPrueba.py

   # O para SQLite local:
   python baseDatos/recrearBaseDatos.py --motor sqlite --forzar
   ```

4. **Iniciar la aplicación:**
   * **En Windows con un clic:** Ejecutar el archivo `iniciarSistema.bat`.
   * **Mediante consola de comandos:**
     ```bash
     uvicorn sistemaAnalitica.app.servidor:app --host 0.0.0.0 --port 8000 --reload
     ```

5. **Acceder a la plataforma:**
   Abra su navegador web e ingrese a `http://localhost:8000`.

---

### 3.3 Despliegue en Producción (Render + Supabase)

El proyecto está configurado para ejecutarse de forma nativa en **Render**:

1. **Crear un nuevo Web Service en Render:**
   * Conecte su repositorio de GitHub a Render.
   * Seleccione el entorno de ejecución: **Python 3**.
   * **Root Directory:** `./` (o el directorio raíz donde reside el proyecto).
2. **Configuración de Comandos de Construcción y Arranque:**
   * **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
   * **Start Command:**
     ```bash
     uvicorn sistemaAnalitica.app.servidor:app --host 0.0.0.0 --port $PORT
     ```
3. **Variables de Entorno en el Dashboard de Render:**
   Agregue las siguientes claves en la sección *Environment Variables*:
   * `DATABASE_URL`: Cadena de conexión `postgresql://...` provista por Supabase (se recomienda usar el *Connection Pooling* en puerto 5432 o 6543).
   * `ENTORNO`: `produccion`
   * `SECRET_KEY`: Cadena aleatoria segura para el cifrado de sesiones.
   * `PYTHON_VERSION`: `3.11.9`

---

### 3.4 Contenerización con Docker

El repositorio incluye un `Dockerfile` optimizado y multi-stage listo para correr en cualquier nube:

```bash
# 1. Construir la imagen Docker
docker build -t cubix-analytics:latest .

# 2. Ejecutar el contenedor vinculando el archivo .env
docker run -d -p 8080:8080 --env-file .env --name cubix_app cubix-analytics:latest
```
Acceso: `http://localhost:8080`

---

## d. Estructura del Proyecto

La arquitectura del proyecto sigue una separación clara de responsabilidades:

```text
export/
├── .env.example                 # Plantilla de variables de entorno (sin credenciales sensibles)
├── .gitignore                   # Reglas estrictas de exclusión para Git (oculta .env, .venv, etc.)
├── .dockerignore                # Exclusiones para construcción óptima de imágenes Docker
├── Dockerfile                   # Especificación de contenedor Docker para producción
├── README.md                    # Documentación técnica completa y detallada del proyecto
├── STARTGUIDE.md                # Guía de especificaciones de bajo nivel para agentes y desarrollo
├── requirements.txt             # Dependencias Python fijadas para pip, Render y Docker
├── iniciarSistema.bat           # Script de inicio en 1 clic para entornos Windows
│
├── baseDatos/                   # Scripts de gestión relacional, esquemas y datos de prueba
│   ├── esquemas/                # Esquemas DDL SQL de referencia (PostgreSQL y SQLite)
│   │   ├── schema_sqlserver.sql
│   │   └── schema_sqlite.sql
│   ├── recrearBaseDatos.py      # Script de purga y regeneración limpia de tablas en Supabase / SQLite
│   ├── generarDatosPrueba.py    # Generador del dataset de ventas y tabla relacional de ingesta
│   ├── probarIngestaExcel.py    # Pruebas automatizadas del motor de ingesta de archivos
│   ├── limpiarCatalogo.py       # Utilidad para saneamiento de registros huérfanos del catálogo
│   └── verificarTodo.py         # Script de verificación integral del estado del sistema
│
├── datosPrueba/                 # Datasets de prueba locales
│   └── ventas_10000.xlsx        # Dataset con 10,000 registros para pruebas de ingesta y rendimiento
│
└── sistemaAnalitica/            # Código fuente principal de la plataforma
    ├── almacenamiento/          # Persistencia física de datos
    │   ├── controlAnalitica.db  # Base de datos SQLite local de control (fallback)
    │   └── parquets/            # Archivos .parquet generados por el Data Lake
    │
    ├── app/                     # Capa web y controladores FastAPI
    │   ├── servidor.py          # Punto de entrada de la aplicación FastAPI y middlewares
    │   ├── dependencias.py      # Middleware de autenticación, control de sesiones y RBAC
    │   ├── routers/             # Módulos de endpoints separados por dominio funcional
    │   │   ├── autenticacion.py # Gestión de login, logout y sesiones seguras
    │   │   ├── inicio.py        # Dashboard principal y resumen de métricas del sistema
    │   │   ├── ingesta.py       # Endpoints de subida, análisis Calamine y cruce OBT
    │   │   ├── explorador.py    # Endpoints de consulta OLAP vectorizada con DuckDB
    │   │   ├── seguridad.py     # Endpoints de administración de usuarios, roles y RLS
    │   │   ├── administracion.py# Mantenimiento de cubos, vistas y limpieza de metadatos
    │   │   ├── configuracionVistas.py # Diseñador de vistas analíticas asociadas
    │   │   └── baseDatosRouter.py     # Gestión de conexiones relacionales en vivo
    │   ├── static/              # Recursos estáticos web (Tailwind CSS, JS, imágenes, SVG)
    │   └── templates/           # Plantillas Jinja2 (HTML5 semántico, layouts, modales)
    │
    ├── modulos/                 # Lógica de dominio y motores analíticos
    │   ├── ingesta/             # Lector Calamine Rust, generador OBT, gestor SQL en vivo
    │   ├── motorAnalitico/      # Motor DuckDB OLAP, perfilador columnar y transformaciones
    │   ├── seguridad/           # Modelos SQLAlchemy, sesiones de BD, RBAC y auditoría
    │   ├── autenticacion/       # Estrategias de login (Local PBKDF2, LDAP, SOAP)
    │   ├── presentacion/        # Componentes de presentación, estilos y vistas
    │   └── mcp/                 # Servidor Model Context Protocol para asistentes inteligentes
    │
    └── documentacion/           # Especificaciones arquitectónicas internas
        ├── ARQUITECTURA.md      # Memoria técnica de diseño arquitectónico
        ├── CONTRATOS.md         # Especificación de contratos de datos y payloads
        └── BITACORA_APRENDIZAJE.md # Registro técnico de evolución del proyecto
```

---

## e. Funcionalidades Principales

Cubix ofrece un flujo integral de datos desde la captura hasta la toma de decisiones analíticas:

### 1. Ingesta Inteligente y Modelado One Big Table (OBT)
* **Extracción Masiva Instantánea con Rust:** Lectura de archivos `.xlsx` y `.xlsb` mediante `python-calamine`, procesando miles de registros por segundo con mínimo consumo de CPU y memoria.
* **Detección y Unificación Automática de Hojas:** Detección de hojas con estructuras equivalentes (por ejemplo, meses o trimestres) para aplicar `UNION ALL` automático, registrando la columna trazable `hoja_origen`.
* **Cruce Relacional Multi-Hoja (Diagrama en Estrella):** Interfaz para definir enlaces entre una hoja de hechos principal y múltiples hojas satélites de dimensiones mediante claves compuestas (`LEFT`, `INNER`, `OUTER`).
* **Prevención de Riesgo Fan-Out:** Análisis predictivo de cardinalidad antes de materializar el cubo, alertando al usuario si un cruce multiplicará artificialmente el volumen de filas.
* **Consultas SQL en Vivo con Throttling:** Conexión a motores externos (PostgreSQL, SQL Server, Supabase) con muestreo automático (`LIMIT 10`) y ventana de refresco controlado de 5 minutos para proteger bases operacionales contra sobrecargas.

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

## f. Usuarios y Contraseñas de Prueba

El sistema cuenta con tres cuentas de usuario predeterminadas registradas en la base de datos de Supabase PostgreSQL para evaluar los distintos niveles de permisos y seguridad:

| Usuario | Contraseña | Rol Asignado | Privilegios y Pantallas Habilitadas |
| :--- | :--- | :--- | :--- |
| **`admin`** | `admin` | **Administrador** | **Acceso Total:** Inicio, Ingesta de Datos, Explorador OLAP, Seguridad y RBAC, Configuración de Vistas, Mantenimiento de Cubos y Auditoría. |
| **`analista`** | `analista` | **Analista de Datos** | **Acceso Analítico:** Inicio, Ingesta de Datos, Explorador OLAP, Configuración de Vistas y Mantenimiento de Cubos. |
| **`operador`** | `operador` | **Operador** | **Acceso Operativo:** Inicio, Explorador OLAP (consulta de tableros asignados y exportación de reportes). |

> [!NOTE]
> Todas las contraseñas son validadas contra Supabase PostgreSQL utilizando derivación criptográfica **PBKDF2-HMAC-SHA256** con salt dinámico y 100,000 rondas de hashing.

---

## 🔐 Especificación de Variables de Entorno

| Variable | Tipo | Requerida | Valor por Defecto | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `DATABASE_URL` | String | **Sí** (en producción) | `sqlite:///sistemaAnalitica/...` | Cadena de conexión SQLAlchemy a Supabase PostgreSQL o SQLite local. |
| `PORT` | Integer | No | `8000` (Local) / `$PORT` (Render) | Puerto TCP de escucha del servidor web. |
| `HOST` | String | No | `0.0.0.0` | Dirección IP de enlace de la aplicación. |
| `ENTORNO` | String | No | `produccion` | Entorno de ejecución (`desarrollo` / `produccion`). |
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
