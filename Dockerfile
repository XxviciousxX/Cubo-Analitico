# ==============================================================================
# Dockerfile - Cubix (Sistema de Inteligencia Analitica y Cubos OLAP)
# Compatible con Google Cloud Run y Google Cloud Vertex AI
# ==============================================================================

FROM python:3.11-slim

# Metadatos del Contenedor
LABEL maintainer="Cubix Analytics Team"
LABEL description="Contenedor de producción para Cubix - Motor OLAP sobre Parquet y FastAPI"

# Variables de Entorno de Python y Contenedor
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080 \
    HOST=0.0.0.0

WORKDIR /app

# Instalar dependencias del sistema operativo para compilacion nativa y drivers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    unixodbc-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente de la aplicación
COPY . .

# Asegurar la existencia de directorios de almacenamiento en tiempo de ejecucion
RUN mkdir -p sistemaAnalitica/almacenamiento/parquets \
    && mkdir -p sistemaAnalitica/almacenamiento/parquets_backup

# Crear usuario sin privilegios para ejecucion segura
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Exponer el puerto configurado (Google Cloud inyecta la variable $PORT)
EXPOSE 8080

# Comando de arranque con Uvicorn enlazado dinamicamente al puerto
CMD exec uvicorn sistemaAnalitica.app.servidor:app --host 0.0.0.0 --port ${PORT:-8080} --workers 2
