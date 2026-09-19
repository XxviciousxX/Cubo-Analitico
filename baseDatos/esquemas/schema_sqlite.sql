-- =============================================================================
-- ESQUEMA RELACIONAL DDL PARA SQLITE - CUBIX ANALYTICS
-- Motor de Control y Gobernanza de Cubos OLAP
-- =============================================================================

PRAGMA foreign_keys = ON;

-- Tabla: conexiones_bases_datos
CREATE TABLE conexiones_bases_datos (
	id_conexion INTEGER NOT NULL, 
	nombre_conexion VARCHAR(100) NOT NULL, 
	motor_base_datos VARCHAR(50) NOT NULL, 
	cadena_conexion TEXT NOT NULL, 
	descripcion VARCHAR(255), 
	activo BOOLEAN NOT NULL, 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id_conexion), 
	UNIQUE (nombre_conexion)
);

-- Tabla: cubos
CREATE TABLE cubos (
	id_cubo INTEGER NOT NULL, 
	nombre_cubo VARCHAR(150) NOT NULL, 
	archivo_parquet VARCHAR(255) NOT NULL, 
	tipo_origen VARCHAR(50) NOT NULL, 
	configuracion_origen_json TEXT, 
	estado_habilitado BOOLEAN NOT NULL, 
	fecha_ultima_carga DATETIME NOT NULL, 
	metadatos_columnas_json TEXT, 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id_cubo), 
	UNIQUE (nombre_cubo)
);

-- Tabla: logs_auditoria_eliminacion
CREATE TABLE logs_auditoria_eliminacion (
	id INTEGER NOT NULL, 
	fecha_hora DATETIME NOT NULL, 
	id_usuario INTEGER, 
	nombre_usuario VARCHAR(100) NOT NULL, 
	nombre_completo VARCHAR(150), 
	tipo_objeto VARCHAR(20) NOT NULL, 
	id_objeto INTEGER NOT NULL, 
	identificador_objeto VARCHAR(150) NOT NULL, 
	nombre_objeto VARCHAR(150) NOT NULL, 
	detalles_json TEXT, 
	direccion_ip VARCHAR(50), 
	PRIMARY KEY (id)
);

CREATE INDEX ix_logs_auditoria_eliminacion_fecha_hora ON logs_auditoria_eliminacion (fecha_hora);

-- Tabla: logs_sistema
CREATE TABLE logs_sistema (
	id INTEGER NOT NULL, 
	fecha DATETIME NOT NULL, 
	capa VARCHAR(50) NOT NULL, 
	metodo VARCHAR(100) NOT NULL, 
	error TEXT NOT NULL, 
	PRIMARY KEY (id)
);

-- Tabla: pantallas
CREATE TABLE pantallas (
	id_pantalla INTEGER NOT NULL, 
	codigo_pantalla VARCHAR(50) NOT NULL, 
	nombre_pantalla VARCHAR(100) NOT NULL, 
	ruta_pantalla VARCHAR(100) NOT NULL, 
	icono VARCHAR(50) NOT NULL, 
	descripcion VARCHAR(255), 
	orden INTEGER NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id_pantalla), 
	UNIQUE (codigo_pantalla), 
	UNIQUE (ruta_pantalla)
);

-- Tabla: permisos
CREATE TABLE permisos (
	id_permiso INTEGER NOT NULL, 
	codigo_permiso VARCHAR(50) NOT NULL, 
	nombre_permiso VARCHAR(100) NOT NULL, 
	descripcion VARCHAR(255), 
	PRIMARY KEY (id_permiso), 
	UNIQUE (codigo_permiso)
);

-- Tabla: roles
CREATE TABLE roles (
	id_rol INTEGER NOT NULL, 
	nombre_rol VARCHAR(50) NOT NULL, 
	descripcion VARCHAR(255), 
	activo BOOLEAN NOT NULL, 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id_rol), 
	UNIQUE (nombre_rol)
);

-- Tabla: roles_pantallas
CREATE TABLE roles_pantallas (
	id_rol INTEGER NOT NULL, 
	id_pantalla INTEGER NOT NULL, 
	PRIMARY KEY (id_rol, id_pantalla), 
	FOREIGN KEY(id_rol) REFERENCES roles (id_rol), 
	FOREIGN KEY(id_pantalla) REFERENCES pantallas (id_pantalla)
);

-- Tabla: roles_permisos
CREATE TABLE roles_permisos (
	id_rol INTEGER NOT NULL, 
	id_permiso INTEGER NOT NULL, 
	PRIMARY KEY (id_rol, id_permiso), 
	FOREIGN KEY(id_rol) REFERENCES roles (id_rol), 
	FOREIGN KEY(id_permiso) REFERENCES permisos (id_permiso)
);

-- Tabla: usuarios
CREATE TABLE usuarios (
	id_usuario INTEGER NOT NULL, 
	nombre_usuario VARCHAR(50) NOT NULL, 
	nombre_completo VARCHAR(150) NOT NULL, 
	correo_electronico VARCHAR(120) NOT NULL, 
	clave_hash VARCHAR(255) NOT NULL, 
	id_rol INTEGER NOT NULL, 
	activo BOOLEAN NOT NULL, 
	origen_autenticacion VARCHAR(20) NOT NULL, 
	fecha_creacion DATETIME NOT NULL, 
	fecha_ultimo_acceso DATETIME, 
	PRIMARY KEY (id_usuario), 
	UNIQUE (correo_electronico), 
	FOREIGN KEY(id_rol) REFERENCES roles (id_rol)
);

CREATE UNIQUE INDEX ix_usuarios_nombre_usuario ON usuarios (nombre_usuario);

-- Tabla: excepciones_pantallas_usuario
CREATE TABLE excepciones_pantallas_usuario (
	id_excepcion INTEGER NOT NULL, 
	id_usuario INTEGER NOT NULL, 
	id_pantalla INTEGER NOT NULL, 
	permitido BOOLEAN NOT NULL, 
	motivo VARCHAR(255), 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id_excepcion), 
	FOREIGN KEY(id_usuario) REFERENCES usuarios (id_usuario), 
	FOREIGN KEY(id_pantalla) REFERENCES pantallas (id_pantalla)
);

-- Tabla: vistas
CREATE TABLE vistas (
	id_vista INTEGER NOT NULL, 
	codigo_vista VARCHAR(150) NOT NULL, 
	nombre_vista VARCHAR(150) NOT NULL, 
	descripcion VARCHAR(255), 
	tipo_ingesta VARCHAR(30) NOT NULL, 
	ruta_archivo_parquet VARCHAR(255), 
	contrato_esquema_json TEXT, 
	configuracion_json TEXT, 
	consulta_sql TEXT, 
	id_conexion INTEGER, 
	id_cubo INTEGER, 
	creado_por_usuario_id INTEGER, 
	estado_habilitado BOOLEAN NOT NULL, 
	fecha_ultima_ejecucion DATETIME, 
	activo BOOLEAN NOT NULL, 
	fecha_creacion DATETIME NOT NULL, 
	fecha_modificacion DATETIME, 
	PRIMARY KEY (id_vista), 
	UNIQUE (codigo_vista), 
	FOREIGN KEY(id_conexion) REFERENCES conexiones_bases_datos (id_conexion), 
	FOREIGN KEY(id_cubo) REFERENCES cubos (id_cubo), 
	FOREIGN KEY(creado_por_usuario_id) REFERENCES usuarios (id_usuario)
);

-- Tabla: excepciones_usuario
CREATE TABLE excepciones_usuario (
	id_excepcion INTEGER NOT NULL, 
	id_usuario INTEGER NOT NULL, 
	id_vista INTEGER NOT NULL, 
	permitido BOOLEAN NOT NULL, 
	motivo VARCHAR(255), 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id_excepcion), 
	FOREIGN KEY(id_usuario) REFERENCES usuarios (id_usuario), 
	FOREIGN KEY(id_vista) REFERENCES vistas (id_vista)
);

-- Tabla: filtros_seguridad_fila
CREATE TABLE filtros_seguridad_fila (
	id_filtro INTEGER NOT NULL, 
	id_usuario INTEGER NOT NULL, 
	id_vista INTEGER NOT NULL, 
	columna_filtro VARCHAR(50) NOT NULL, 
	operador_filtro VARCHAR(10) NOT NULL, 
	valor_filtro VARCHAR(100) NOT NULL, 
	activo BOOLEAN NOT NULL, 
	PRIMARY KEY (id_filtro), 
	FOREIGN KEY(id_usuario) REFERENCES usuarios (id_usuario), 
	FOREIGN KEY(id_vista) REFERENCES vistas (id_vista)
);

-- Tabla: roles_vistas
CREATE TABLE roles_vistas (
	id_rol INTEGER NOT NULL, 
	id_vista INTEGER NOT NULL, 
	PRIMARY KEY (id_rol, id_vista), 
	FOREIGN KEY(id_rol) REFERENCES roles (id_rol), 
	FOREIGN KEY(id_vista) REFERENCES vistas (id_vista)
);

