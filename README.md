# Cubix - Sistema de Inteligencia Analítica y Cubos OLAP Multidimensionales

<p align="center">
  <img src="sistemaAnalitica/app/static/img/logo.svg" alt="Cubix Logo" width="160" height="160">
</p>

<p align="center">
  <b>Plataforma empresarial de inteligencia de datos, modelado One Big Table (OBT) y análisis multidimensional en tiempo real.</b><br>
  Construida sobre <b>FastAPI</b>, <b>DuckDB Vectorizado</b>, <b>Apache Parquet (ZSTD)</b>, <b>Calamine (Rust)</b> y <b>Supabase PostgreSQL</b>.
</p>

---

## 📋 Tabla de Contenidos

1. [Visión General de la Arquitectura](#-visión-general-de-la-arquitectura)
2. [Módulos Principales del Sistema](#-módulos-principales-del-sistema)
3. [Estructura del Proyecto](#-estructura-del-proyecto)
4. [Roles y Control de Acceso (RBAC)](#-roles-y-control-de-acceso-rbac)
5. [Guía de Puesta en Marcha Local](#-guía-de-puesta-en-marcha-local)
6. [Guía de Contenerización y Despliegue en Vertex AI / Cloud Run](#-guía-de-contenerización-y-despliegue-en-vertex-ai--cloud-run)
7. [Instrucciones para Subir el Proyecto a Git](#-instrucciones-para-subir-el-proyecto-a-git)
8. [Especificación de Variables de Entorno](#-especificación-de-variables-de-entorno)
9. [Catálogo de Endpoints API](#-catálogo-de-endpoints-api)

---

## 🏛️ Visión General de la Arquitectura

Cubix desacopla el almacenamiento transaccional tradicional de la capa de consulta analítica mediante un enfoque **One Big Table (OBT)** asistido por motores en memoria de ultra alto rendimiento:

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
  |  - Almacenamiento local optimizado o Cloud Storage (GCS / S3)           |
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

## ⚙️ Módulos Principales del Sistema

### 1. Ingesta y Modelado de Datos (`sistemaAnalitica/modulos/ingesta`)
- **Calamine (Rust):** Extracción instantánea de libros Excel sin sobrecarga de memoria de COM/Python.
- **Unificación de Hojas Idénticas:** Identifica automáticamente hojas distribuidas (ej. meses de un año) y realiza `UNION ALL` agregando la columna de auditoría `hoja_origen`.
- **Diagrama de Estrella y Cruce Multi-Hoja:** Permite correlacionar tablas de hechos con dimensiones satélites mediante llaves compuestas.
- **Consultas SQL con Throttling:** Conector a motores relacionales con prevención de sobrecarga mediante ventana de refresco controlado de 5 minutos.
- **Data Lake Masivo:** Diseñador de contratos de esquema Parquet vacío para ingestas directas por procesos ETL externos.

### 2. Motor Analítico OLAP (`sistemaAnalitica/modulos/motorAnalitico`)
- Lectura de archivos Parquet directamente desde DuckDB sin necesidad de cargar DataFrames completos en memoria.
- Métricas sumables (`SUM`), no sumables (`AVG`, `MAX`, `MIN`, `COUNT DISTINCT`) y campos calculados.
- Filtros por dimensión, ordenamiento dinámico y paginación columnar.
- Generación de gráficos interactivos Plotly y exportación directa a Excel con formato.

### 3. Gobernanza, Auditoría y Seguridad (`sistemaAnalitica/modulos/seguridad`)
- Catálogo relacional administrado por SQLAlchemy sobre **Supabase PostgreSQL**.
- Tablas de control: `usuarios`, `roles`, `pantallas`, `permisos`, `cubos`, `vistas`, `roles_vistas`, `excepciones_usuario` y `conexiones_bases_datos`.
- Trazabilidad y auditoría de eliminaciones (`logs_auditoria_eliminacion`).

---

## 📁 Estructura del Proyecto

```text
export/
├── .env.example                 # Plantilla de variables de entorno (sin credenciales)
├── .gitignore                   # Reglas estrictas de exclusión para Git
├── .dockerignore                # Exclusiones para compilación de imágenes Docker
├── Dockerfile                   # Contenedor optimizado para Cloud Run / Vertex AI
├── README.md                    # Documentación técnica maestra del proyecto
├── STARTGUIDE.md                # Guía de especificaciones de bajo nivel para agentes
├── requirements.txt             # Dependencias de Python estándar para pip/Docker
├── iniciarSistema.bat           # Script de inicio en 1 clic para entornos Windows
│
├── baseDatos/                   # Scripts de gestión relacional y datos de prueba
│   ├── recrearBaseDatos.py      # Purga y regeneración limpia del esquema en Supabase
│   ├── generarDatosPrueba.py    # Generador del dataset de ventas y tabla ingesta_test
│   ├── verificarTodo.py         # Script de verificación integral del estado del sistema
│   └── esquemas/                # Esquemas DDL SQL de referencia
│
├── datosPrueba/                 # Datasets de prueba locales
│   └── ventas_10000.xlsx        # 10,000 registros de ventas para pruebas de ingesta Excel
│
└── sistemaAnalitica/            # Código fuente principal de la aplicación
    ├── almacenamiento/          # Almacenamiento local del Data Lake
    │   └── parquets/            # Archivos .parquet materializados (ignorado en Git)
    ├── app/                     # Capa web y controladores FastAPI
    │   ├── servidor.py          # Punto de entrada de la aplicación FastAPI
    │   ├── dependencias.py      # Middleware de autenticación y verificación de roles
    │   ├── routers/             # Endpoints (autenticacion, explorador, ingesta, admin)
    │   ├── static/              # Recursos estáticos (CSS, JS, iconos, logos SVG/PNG)
    │   └── templates/           # Vistas Jinja2 renderizadas con Tailwind CSS
    └── modulos/                 # Lógica de dominio y motores
        ├── ingesta/             # Lector Calamine, generador OBT, gestor SQL en vivo
        ├── motorAnalitico/      # Motor DuckDB OLAP, perfilador y transformador
        └── seguridad/           # Modelos SQLAlchemy, sesiones de BD y RBAC
```

---

## 👥 Roles y Control de Acceso (RBAC)

El sistema cuenta con 3 perfiles de usuario predeterminados configurados en la base de datos de Supabase PostgreSQL:

| Usuario | Contraseña | Rol Asignado | Pantallas y Privilegios Habilitados |
| :--- | :--- | :--- | :--- |
| **`admin`** | `admin` | **Administrador** | **Acceso Total:** Inicio, Ingesta, Explorador OLAP, Seguridad, Configuración de Vistas, Gestión de Cubos, Gestión de Vistas, Depuración de Objetos. |
| **`analista`** | `analista` | **Analista de Datos** | **Acceso Analítico:** Inicio, Ingesta, Explorador OLAP, Configuración de Vistas, Gestión de Cubos, Gestión de Vistas, Depuración de Objetos. |
| **`operador`** | `operador` | **Operador** | **Acceso Operativo:** Inicio, Explorador OLAP (consulta de tableros y exportación de reportes asignados). |

---

## 🚀 Guía de Puesta en Marcha Local

### Prerrequisitos
- Python 3.11 o superior.
- Conexión a Internet para conectar a Supabase PostgreSQL (o SQLite local).

### Pasos de Instalación
1. **Crear y activar el entorno virtual:**
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   # Linux / Mac:
   source .venv/bin/activate
   ```

2. **Instalar dependencias del proyecto:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configurar variables de entorno:**
   ```bash
   # Windows:
   copy .env.example .env
   # Linux / Mac:
   cp .env.example .env
   ```
   Edite el archivo `.env` e ingrese su cadena `DATABASE_URL` (o use la conexión provista por defecto).

4. **Inicializar y poblar la Base de Datos:**
   ```bash
   python baseDatos/recrearBaseDatos.py --motor postgres --forzar
   python baseDatos/generarDatosPrueba.py
   ```

5. **Iniciar el Servidor Web:**
   - **En Windows:** Doble clic en `iniciarSistema.bat`.
   - **Por comando:**
     ```bash
     uvicorn sistemaAnalitica.app.servidor:app --host 0.0.0.0 --port 8000 --reload
     ```

6. **Ingreso al Sistema:**
   - Abrir el navegador en `http://localhost:8000`.
   - Iniciar sesión con `admin` / `admin`.

---

## ☁️ Guía de Contenerización y Despliegue en Vertex AI / Cloud Run

Cubix está completamente dockerizado y cumple con las especificaciones de Google Cloud:
- Exposición dinámica del puerto mediante la variable de entorno `$PORT`.
- Base ligera `python:3.11-slim` con drivers relacionales compilados.
- Usuario no privilegiado `appuser` para cumplimiento de seguridad en contenedores.

### 1. Construcción y Prueba Local de la Imagen Docker
```bash
# Construir la imagen
docker build -t cubix-analytics:latest .

# Ejecutar el contenedor localmente
docker run -p 8080:8080 --env-file .env cubix-analytics:latest
```
Acceda a `http://localhost:8080`.

### 2. Despliegue en Google Cloud (Artifact Registry + Cloud Run)
Google Cloud Run es el entorno ideal para hospedar la aplicación web y los endpoints analíticos de Cubix, con escalado a cero y soporte HTTPS automático.

```bash
# 1. Autenticar con Google Cloud
gcloud auth login
gcloud config set project TU_PROJECT_ID

# 2. Habilitar APIs necesarias
gcloud services enable artifactregistry.googleapis.com run.googleapis.com

# 3. Crear repositorio en Artifact Registry
gcloud artifacts repositories create cubix-repo \
    --repository-format=docker \
    --location=us-central1 \
    --description="Repositorio Docker para Cubix"

# 4. Compilar y subir la imagen
gcloud builds submit --tag us-central1-docker.pkg.dev/TU_PROJECT_ID/cubix-repo/cubix-app:latest

# 5. Desplegar en Cloud Run inyectando DATABASE_URL de forma segura
gcloud run deploy cubix-service \
    --image us-central1-docker.pkg.dev/TU_PROJECT_ID/cubix-repo/cubix-app:latest \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --set-env-vars DATABASE_URL="postgresql://postgres.flposnfuyrkenlhiguaq:Zaq12wsxcv%2B%2B123789456@aws-0-us-west-2.pooler.supabase.com:5432/postgres" \
    --memory 2Gi \
    --cpu 2
```

### 3. Despliegue en Google Cloud Vertex AI (Custom Container)
Para utilizar Cubix como endpoint analítico o de inferencia sobre modelos en Vertex AI:

1. **Registrar el Modelo / Contenedor en Vertex AI:**
   ```bash
   gcloud ai models upload \
       --region=us-central1 \
       --display-name="cubix-analytical-engine" \
       --container-image-uri="us-central1-docker.pkg.dev/TU_PROJECT_ID/cubix-repo/cubix-app:latest" \
       --container-ports=8080 \
       --container-health-route="/login" \
       --container-predict-route="/api/olap/consultar"
   ```

2. **Crear Endpoint en Vertex AI y Desplegar:**
   ```bash
   # Crear el endpoint
   gcloud ai endpoints create \
       --region=us-central1 \
       --display-name="cubix-endpoint"

   # Desplegar el modelo contenedor en el endpoint
   gcloud ai endpoints deploy-model ENDPOINT_ID \
       --region=us-central1 \
       --model=MODEL_ID \
       --display-name="cubix-deployment" \
       --machine-type="n1-standard-4" \
       --traffic-split=0=100
   ```

---

## 📦 Instrucciones para Subir el Proyecto a Git

> [!IMPORTANT]
> **Directorio Raíz para Git:**  
> La carpeta que contiene todos los archivos del proyecto listos para ser subidos a tu repositorio de GitHub, GitLab o Bitbucket es:  
> **`c:\Users\MAURICIO\Documents\Antigravity\CuboAnalitico\export`**

### Pasos en la Terminal de tu Máquina:

1. **Abrir la terminal en la carpeta `export`:**
   ```bash
   cd "c:\Users\MAURICIO\Documents\Antigravity\CuboAnalitico\export"
   ```

2. **Inicializar el repositorio Git local:**
   ```bash
   git init
   ```

3. **Verificar que el `.gitignore` proteja los secretos:**
   ```bash
   git status
   ```
   *Verifique que ni el archivo `.env` ni la carpeta `.venv` aparezcan en la lista de archivos sin seguimiento.*

4. **Añadir todos los archivos y realizar el commit inicial:**
   ```bash
   git add .
   git commit -m "feat: publicacion inicial del sistema analitico Cubix"
   ```

5. **Vincular con tu repositorio remoto y subir el código:**
   ```bash
   # Cambiar a la rama principal
   git branch -M main

   # Vincular con la URL de tu repositorio (reemplazar con tu URL de GitHub)
   git remote add origin https://github.com/TU_USUARIO/TU_REPOSITORIO.git

   # Subir los cambios
   git push -u origin main
   ```

---

## 🔐 Especificación de Variables de Entorno

| Variable | Tipo | Requerida | Valor por Defecto | Descripción |
| :--- | :--- | :--- | :--- | :--- |
| `DATABASE_URL` | String | **Sí** (en prod) | `sqlite:///sistemaAnalitica/...` | URL de conexión SQLAlchemy a PostgreSQL / Supabase o SQLite. |
| `PORT` | Integer | No | `8080` (Docker) / `8000` | Puerto TCP donde escucha el servidor web. |
| `HOST` | String | No | `0.0.0.0` | Dirección IP de enlace de la aplicación. |
| `ENTORNO` | String | No | `produccion` | Define el modo de ejecución (`desarrollo` / `produccion`). |
| `SECRET_KEY` | String | No | *(Generada dinámicamente)* | Llave criptográfica para la firma de cookies de sesión segura. |

---

## 📡 Catálogo de Endpoints API

### Autenticación y Sesión
- `GET /login`: Formulario de inicio de sesión con Tailwind CSS.
- `POST /login`: Validación de credenciales locales contra Supabase (PBKDF2-HMAC-SHA256).
- `GET /logout`: Cierre de sesión y revocación de cookie de seguridad.

### Ingesta y Modelado de Cubos
- `GET /ingesta`: Panel de control interactivo de ingesta de datos.
- `POST /api/ingesta/excel/analizar-libro-completo`: Análisis multivariable de hojas con Calamine (Rust).
- `POST /api/ingesta/procesar-excel`: Materialización a Parquet OBT con compresión ZSTD.
- `POST /api/sql/probar`: Extracción de muestra segura (TOP 10) con validación de conectividad.
- `POST /api/sql/procesar-cubo`: Extracción por lotes desde SQL relacional hacia Parquet.
- `POST /api/ingesta/crear-cubo-compuesto`: Enlace de múltiples cubos mediante JOINs relacionales y diagnóstico Fan-Out.

### Motor Analítico OLAP
- `GET /explorador`: Interfaz visual de exploración analítica multidimensional.
- `POST /api/olap/consultar`: Ejecución de consultas analíticas vectorizadas en sub-segundos sobre DuckDB.
- `POST /api/olap/exportar`: Exportación del cubo procesado a formatos XLSX / CSV.

### Administración y Gobernanza
- `GET /seguridad`: Matriz RBAC, gestión de usuarios, roles y asignación de pantallas.
- `GET /administracion/cubos`: Catálogo y mantenimiento de archivos físicos Parquet.
- `GET /administracion/vistas`: Diseñador de vistas analíticas asociadas a cubos.

---

<p align="center">
  <b>Cubix</b> — Plataforma de Inteligencia Analítica Corporativa
</p>
