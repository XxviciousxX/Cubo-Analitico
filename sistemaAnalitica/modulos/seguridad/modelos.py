"""
Modelos relacionales para la gobernanza, autenticación y control de accesos.
Utiliza SQLAlchemy 2.0 y sigue la convención de nomenclatura camelCase en atributos.
"""

from datetime import datetime
from typing import Optional, List, Any, Dict
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import declarative_base, relationship

BaseModelo = declarative_base()


class RolPermisoModelo(BaseModelo):
    """
    Tabla intermedia para la asociación de roles y permisos del sistema.
    """
    __tablename__ = "roles_permisos"

    idRol = Column("id_rol", Integer, ForeignKey("roles.id_rol"), primary_key=True)
    idPermiso = Column("id_permiso", Integer, ForeignKey("permisos.id_permiso"), primary_key=True)


class RolVistaModelo(BaseModelo):
    """
    Tabla intermedia para la asignación de vistas o cubos analíticos por rol institucional.
    """
    __tablename__ = "roles_vistas"

    idRol = Column("id_rol", Integer, ForeignKey("roles.id_rol"), primary_key=True)
    idVista = Column("id_vista", Integer, ForeignKey("vistas.id_vista"), primary_key=True)


class RolPantallaModelo(BaseModelo):
    """
    Tabla intermedia para la asignación de pantallas o módulos del sistema por rol institucional.
    """
    __tablename__ = "roles_pantallas"

    idRol = Column("id_rol", Integer, ForeignKey("roles.id_rol"), primary_key=True)
    idPantalla = Column("id_pantalla", Integer, ForeignKey("pantallas.id_pantalla"), primary_key=True)


class PantallaModelo(BaseModelo):
    """
    Representa una pantalla o módulo del sistema accesible mediante ruta URL.
    """
    __tablename__ = "pantallas"

    idPantalla = Column("id_pantalla", Integer, primary_key=True, autoincrement=True)
    codigoPantalla = Column("codigo_pantalla", String(50), unique=True, nullable=False)
    nombrePantalla = Column("nombre_pantalla", String(100), nullable=False)
    rutaPantalla = Column("ruta_pantalla", String(100), unique=True, nullable=False)
    icono = Column("icono", String(50), default="dashboard", nullable=False)
    descripcion = Column("descripcion", String(255), nullable=True)
    orden = Column("orden", Integer, default=0, nullable=False)
    activo = Column("activo", Boolean, default=True, nullable=False)

    roles = relationship("RolModelo", secondary="roles_pantallas", back_populates="pantallas")


class RolModelo(BaseModelo):
    """
    Representa un rol de usuario dentro de la jerarquía institucional.
    """
    __tablename__ = "roles"

    idRol = Column("id_rol", Integer, primary_key=True, autoincrement=True)
    nombreRol = Column("nombre_rol", String(50), unique=True, nullable=False)
    descripcion = Column("descripcion", String(255), nullable=True)
    activo = Column("activo", Boolean, default=True, nullable=False)
    fechaCreacion = Column("fecha_creacion", DateTime, default=datetime.utcnow, nullable=False)

    usuarios = relationship("UsuarioModelo", back_populates="rol")
    permisos = relationship("PermisoModelo", secondary="roles_permisos", back_populates="roles")
    vistas = relationship("VistaModelo", secondary="roles_vistas", back_populates="roles")
    pantallas = relationship("PantallaModelo", secondary="roles_pantallas", back_populates="roles")


class PermisoModelo(BaseModelo):
    """
    Define una acción o privilegio granular dentro de los módulos del sistema.
    """
    __tablename__ = "permisos"

    idPermiso = Column("id_permiso", Integer, primary_key=True, autoincrement=True)
    codigoPermiso = Column("codigo_permiso", String(50), unique=True, nullable=False)
    nombrePermiso = Column("nombre_permiso", String(100), nullable=False)
    descripcion = Column("descripcion", String(255), nullable=True)

    roles = relationship("RolModelo", secondary="roles_permisos", back_populates="permisos")


class UsuarioModelo(BaseModelo):
    """
    Entidad de usuario con credenciales locales o vinculación externa.
    """
    __tablename__ = "usuarios"

    idUsuario = Column("id_usuario", Integer, primary_key=True, autoincrement=True)
    nombreUsuario = Column("nombre_usuario", String(50), unique=True, nullable=False, index=True)
    nombreCompleto = Column("nombre_completo", String(150), nullable=False)
    correoElectronico = Column("correo_electronico", String(120), unique=True, nullable=False)
    claveHash = Column("clave_hash", String(255), nullable=False)
    idRol = Column("id_rol", Integer, ForeignKey("roles.id_rol"), nullable=False)
    activo = Column("activo", Boolean, default=True, nullable=False)
    origenAutenticacion = Column("origen_autenticacion", String(20), default="LOCAL", nullable=False)
    fechaCreacion = Column("fecha_creacion", DateTime, default=datetime.utcnow, nullable=False)
    fechaUltimoAcceso = Column("fecha_ultimo_acceso", DateTime, nullable=True)

    rol = relationship("RolModelo", back_populates="usuarios")
    excepciones = relationship("ExcepcionUsuarioModelo", back_populates="usuario")
    excepcionesPantalla = relationship("ExcepcionPantallaUsuarioModelo", back_populates="usuario")
    filtrosSeguridad = relationship("FiltroSeguridadFilaModelo", back_populates="usuario")


class ConexionBaseDatosModelo(BaseModelo):
    """
    Catálogo paramétrico de orígenes de datos relacionales para consultas SQL en vivo.
    """
    __tablename__ = "conexiones_bases_datos"

    idConexion = Column("id_conexion", Integer, primary_key=True, autoincrement=True)
    nombreConexion = Column("nombre_conexion", String(100), unique=True, nullable=False)
    motorBaseDatos = Column("motor_base_datos", String(50), nullable=False)  # SQLServer, PostgreSQL, etc.
    cadenaConexion = Column("cadena_conexion", Text, nullable=False)
    descripcion = Column("descripcion", String(255), nullable=True)
    activo = Column("activo", Boolean, default=True, nullable=False)
    fechaCreacion = Column("fecha_creacion", DateTime, default=datetime.utcnow, nullable=False)


class CuboModelo(BaseModelo):
    """
    Entidad representativa del archivo físico Parquet OBT y su ciclo de vida en el almacenamiento.
    """
    __tablename__ = "cubos"

    idCubo = Column("id_cubo", Integer, primary_key=True, autoincrement=True)
    nombreCubo = Column("nombre_cubo", String(150), unique=True, nullable=False)
    archivoParquet = Column("archivo_parquet", String(255), nullable=False)
    tipoOrigen = Column("tipo_origen", String(50), nullable=False)  # EXCEL, SQL_EN_VIVO, PROCESO_MASIVO, COMPUESTO
    configuracionOrigenJson = Column("configuracion_origen_json", Text, nullable=True)
    estadoHabilitado = Column("estado_habilitado", Boolean, default=True, nullable=False)
    fechaUltimaCarga = Column("fecha_ultima_carga", DateTime, default=datetime.utcnow, nullable=False)
    metadatosColumnasJson = Column("metadatos_columnas_json", Text, nullable=True)
    fechaCreacion = Column("fecha_creacion", DateTime, default=datetime.utcnow, nullable=False)

    vistas = relationship("VistaModelo", back_populates="cubo")


class VistaModelo(BaseModelo):
    """
    Definición y metadatos de las vistas analíticas o reportes configurados.
    """
    __tablename__ = "vistas"

    idVista = Column("id_vista", Integer, primary_key=True, autoincrement=True)
    codigoVista = Column("codigo_vista", String(150), unique=True, nullable=False)
    nombreVista = Column("nombre_vista", String(150), nullable=False)
    descripcion = Column("descripcion", String(255), nullable=True)
    tipoIngesta = Column("tipo_ingesta", String(30), nullable=False)  # ExcelModalidadA, ExcelModalidadB, SqlEnVivo, ProcesoMasivo, CuboCompuesto
    rutaArchivoParquet = Column("ruta_archivo_parquet", String(255), nullable=True)
    contratoEsquemaJson = Column("contrato_esquema_json", Text, nullable=True)
    configuracionJson = Column("configuracion_json", Text, nullable=True)
    consultaSql = Column("consulta_sql", Text, nullable=True)
    idConexion = Column("id_conexion", Integer, ForeignKey("conexiones_bases_datos.id_conexion"), nullable=True)
    idCubo = Column("id_cubo", Integer, ForeignKey("cubos.id_cubo"), nullable=True)
    creadoPorUsuarioId = Column("creado_por_usuario_id", Integer, ForeignKey("usuarios.id_usuario"), nullable=True)
    estadoHabilitado = Column("estado_habilitado", Boolean, default=True, nullable=False)
    fechaUltimaEjecucion = Column("fecha_ultima_ejecucion", DateTime, nullable=True)
    activo = Column("activo", Boolean, default=True, nullable=False)
    fechaCreacion = Column("fecha_creacion", DateTime, default=datetime.utcnow, nullable=False)
    fechaModificacion = Column("fecha_modificacion", DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    roles = relationship("RolModelo", secondary="roles_vistas", back_populates="vistas")
    cubo = relationship("CuboModelo", back_populates="vistas")
    creador = relationship("UsuarioModelo")


# ==============================================================================
# ESQUEMAS PYDANTIC DE CONTRATO PARA CONFIGURACIÓN DE VISTAS Y GOBERNANZA
# ==============================================================================
from pydantic import BaseModel, Field, model_validator

class MetricaGranoEsquema(BaseModel):
    """
    Especificación de una métrica cuantitativa con su agregación permitida.
    """
    columna: Optional[str] = None
    campo: Optional[str] = None
    operacion: Optional[str] = "SUM"
    agregacion: Optional[str] = "SUM"
    alias: Optional[str] = None
    etiqueta: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def normalizarMetrica(cls, data: Any):
        if isinstance(data, dict):
            col = data.get("columna") or data.get("campo") or ""
            op = data.get("operacion") or data.get("agregacion") or "SUM"
            ali = data.get("alias") or data.get("etiqueta") or f"{col} ({op})"
            return {
                "columna": col,
                "campo": col,
                "operacion": op,
                "agregacion": op,
                "alias": ali,
                "etiqueta": ali
            }
        return data


class GranoPermitidoEsquema(BaseModel):
    """
    Capa semántica que define las dimensiones y métricas visibles en la vista.
    """
    dimensionesVisibles: List[str]
    metricas: List[MetricaGranoEsquema]
    jerarquiaDrilldownPermitida: List[str] = Field(default_factory=list)
    permitirDrilldown: bool = True


class PoliticaGobernanzaEsquema(BaseModel):
    """
    Políticas de blindaje y restricciones para impedir acceso transaccional atómico.
    """
    bloquearNivelDetalle: bool = True
    columnasExcluidas: List[str] = Field(default_factory=list)
    permitirExportarDetalle: bool = False
    tipoExportacionPermitida: str = "SOLO_RESUMEN_AGREGADO"


class ConfiguracionVisualEsquema(BaseModel):
    """
    Reglas de visualización con Plotly y opciones interactivas permitidas.
    """
    graficoPredeterminado: str = "bar"
    graficosPermitidos: List[str] = Field(default_factory=lambda: ["bar", "pie", "line"])
    dimensionPredeterminada: Optional[str] = None
    metricaPredeterminada: Optional[str] = None
    paletaColores: List[str] = Field(default_factory=lambda: ["#004482", "#006e20", "#005cab", "#0284c7", "#d97706", "#dc2626"])
    tituloEjeX: Optional[str] = None
    tituloEjeY: Optional[str] = None


class FiltroVistaEsquema(BaseModel):
    """
    Filtro estático o de negocio a nivel de vista que condiciona los datos del cubo.
    Ejemplo: columna='segmento', operador='!=', valor='Corporativo'
    """
    columna: str
    operador: str = "="  # '=', '!=', '<>', '>', '<', '>=', '<=', 'IN', 'NOT IN', 'LIKE', 'NOT LIKE'
    valor: Any
    tipoDato: Optional[str] = "texto"
    activo: bool = True


class ConfiguracionVistaEsquema(BaseModel):
    """
    Contrato completo consolidado de configuración y gobernanza de la vista.
    """
    idVista: Optional[int] = None
    codigoVista: Optional[str] = None
    nombreVista: Optional[str] = None
    archivoParquet: Optional[str] = None
    granoPermitido: GranoPermitidoEsquema
    politicaGobernanza: PoliticaGobernanzaEsquema = Field(default_factory=PoliticaGobernanzaEsquema)
    configuracionVisual: ConfiguracionVisualEsquema = Field(default_factory=ConfiguracionVisualEsquema)
    filtrosCubo: List[FiltroVistaEsquema] = Field(default_factory=list)


class ExcepcionUsuarioModelo(BaseModelo):
    """
    Matriz de excepciones por usuario para conceder o revocar acceso a vistas específicas.
    """
    __tablename__ = "excepciones_usuario"

    idExcepcion = Column("id_excepcion", Integer, primary_key=True, autoincrement=True)
    idUsuario = Column("id_usuario", Integer, ForeignKey("usuarios.id_usuario"), nullable=False)
    idVista = Column("id_vista", Integer, ForeignKey("vistas.id_vista"), nullable=False)
    permitido = Column("permitido", Boolean, nullable=False)  # True = Concedido, False = Revocado
    motivo = Column("motivo", String(255), nullable=True)
    fechaCreacion = Column("fecha_creacion", DateTime, default=datetime.utcnow, nullable=False)

    usuario = relationship("UsuarioModelo", back_populates="excepciones")
    vista = relationship("VistaModelo")


class ExcepcionPantallaUsuarioModelo(BaseModelo):
    """
    Matriz de excepciones por usuario para conceder o revocar acceso a pantallas del sistema.
    """
    __tablename__ = "excepciones_pantallas_usuario"

    idExcepcion = Column("id_excepcion", Integer, primary_key=True, autoincrement=True)
    idUsuario = Column("id_usuario", Integer, ForeignKey("usuarios.id_usuario"), nullable=False)
    idPantalla = Column("id_pantalla", Integer, ForeignKey("pantallas.id_pantalla"), nullable=False)
    permitido = Column("permitido", Boolean, nullable=False)  # True = Concedido, False = Revocado
    motivo = Column("motivo", String(255), nullable=True)
    fechaCreacion = Column("fecha_creacion", DateTime, default=datetime.utcnow, nullable=False)

    usuario = relationship("UsuarioModelo", back_populates="excepcionesPantalla")
    pantalla = relationship("PantallaModelo")


class FiltroSeguridadFilaModelo(BaseModelo):
    """
    Reglas de Row-Level Security (RLS) asignadas por usuario o rol.
    """
    __tablename__ = "filtros_seguridad_fila"

    idFiltro = Column("id_filtro", Integer, primary_key=True, autoincrement=True)
    idUsuario = Column("id_usuario", Integer, ForeignKey("usuarios.id_usuario"), nullable=False)
    idVista = Column("id_vista", Integer, ForeignKey("vistas.id_vista"), nullable=False)
    columnaFiltro = Column("columna_filtro", String(50), nullable=False)
    operadorFiltro = Column("operador_filtro", String(10), default="=", nullable=False)
    valorFiltro = Column("valor_filtro", String(100), nullable=False)
    activo = Column("activo", Boolean, default=True, nullable=False)

    usuario = relationship("UsuarioModelo", back_populates="filtrosSeguridad")
    vista = relationship("VistaModelo")


class LogSistemaModelo(BaseModelo):
    """
    Registro centralizado de errores e incidentes del sistema para diagnóstico y auditoría.
    """
    __tablename__ = "logs_sistema"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    fecha = Column("fecha", DateTime, default=datetime.utcnow, nullable=False)
    capa = Column("capa", String(50), nullable=False)
    metodo = Column("metodo", String(100), nullable=False)
    error = Column("error", Text, nullable=False)


class LogAuditoriaEliminacionModelo(BaseModelo):
    """
    Registro de auditoría permanente para la eliminación de cubos OBT y vistas analíticas.
    Consigna fecha/hora exacta, usuario responsable, objeto afectado y metadatos.
    """
    __tablename__ = "logs_auditoria_eliminacion"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    fechaHora = Column("fecha_hora", DateTime, default=datetime.utcnow, nullable=False, index=True)
    idUsuario = Column("id_usuario", Integer, nullable=True)
    nombreUsuario = Column("nombre_usuario", String(100), nullable=False)
    nombreCompleto = Column("nombre_completo", String(150), nullable=True)
    tipoObjeto = Column("tipo_objeto", String(20), nullable=False)  # CUBO / VISTA
    idObjeto = Column("id_objeto", Integer, nullable=False)
    identificadorObjeto = Column("identificador_objeto", String(150), nullable=False)
    nombreObjeto = Column("nombre_objeto", String(150), nullable=False)
    detallesJson = Column("detalles_json", Text, nullable=True)
    direccionIp = Column("direccion_ip", String(50), nullable=True)
