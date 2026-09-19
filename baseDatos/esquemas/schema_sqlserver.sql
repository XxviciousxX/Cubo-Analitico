-- =============================================================================
-- ESQUEMA RELACIONAL DDL PARA MICROSOFT SQL SERVER (T-SQL) - CUBIX
-- Motor de Control y Gobernanza de Cubos OLAP
-- =============================================================================

-- Tabla: conexiones_bases_datos
CREATE TABLE conexiones_bases_datos (
	id_conexion INTEGER NOT NULL IDENTITY, 
	nombre_conexion VARCHAR(100) NOT NULL, 
	motor_base_datos VARCHAR(50) NOT NULL, 
	cadena_conexion TEXT NOT NULL, 
	descripcion VARCHAR(255) NULL, 
	activo BIT NOT NULL, 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id_conexion), 
	UNIQUE (nombre_conexion)
);
GO

-- Tabla: cubos
CREATE TABLE cubos (
	id_cubo INTEGER NOT NULL IDENTITY, 
	nombre_cubo VARCHAR(150) NOT NULL, 
	archivo_parquet VARCHAR(255) NOT NULL, 
	tipo_origen VARCHAR(50) NOT NULL, 
	configuracion_origen_json TEXT NULL, 
	estado_habilitado BIT NOT NULL, 
	fecha_ultima_carga DATETIME NOT NULL, 
	metadatos_columnas_json TEXT NULL, 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id_cubo), 
	UNIQUE (nombre_cubo)
);
GO

-- Tabla: logs_auditoria_eliminacion
CREATE TABLE logs_auditoria_eliminacion (
	id INTEGER NOT NULL IDENTITY, 
	fecha_hora DATETIME NOT NULL, 
	id_usuario INTEGER NULL, 
	nombre_usuario VARCHAR(100) NOT NULL, 
	nombre_completo VARCHAR(150) NULL, 
	tipo_objeto VARCHAR(20) NOT NULL, 
	id_objeto INTEGER NOT NULL, 
	identificador_objeto VARCHAR(150) NOT NULL, 
	nombre_objeto VARCHAR(150) NOT NULL, 
	detalles_json TEXT NULL, 
	direccion_ip VARCHAR(50) NULL, 
	PRIMARY KEY (id)
);
GO

CREATE INDEX ix_logs_auditoria_eliminacion_fecha_hora ON logs_auditoria_eliminacion (fecha_hora);
GO

-- Tabla: logs_sistema
CREATE TABLE logs_sistema (
	id INTEGER NOT NULL IDENTITY, 
	fecha DATETIME NOT NULL, 
	capa VARCHAR(50) NOT NULL, 
	metodo VARCHAR(100) NOT NULL, 
	error TEXT NOT NULL, 
	PRIMARY KEY (id)
);
GO

-- Tabla: pantallas
CREATE TABLE pantallas (
	id_pantalla INTEGER NOT NULL IDENTITY, 
	codigo_pantalla VARCHAR(50) NOT NULL, 
	nombre_pantalla VARCHAR(100) NOT NULL, 
	ruta_pantalla VARCHAR(100) NOT NULL, 
	icono VARCHAR(50) NOT NULL, 
	descripcion VARCHAR(255) NULL, 
	orden INTEGER NOT NULL, 
	activo BIT NOT NULL, 
	PRIMARY KEY (id_pantalla), 
	UNIQUE (codigo_pantalla), 
	UNIQUE (ruta_pantalla)
);
GO

-- Tabla: permisos
CREATE TABLE permisos (
	id_permiso INTEGER NOT NULL IDENTITY, 
	codigo_permiso VARCHAR(50) NOT NULL, 
	nombre_permiso VARCHAR(100) NOT NULL, 
	descripcion VARCHAR(255) NULL, 
	PRIMARY KEY (id_permiso), 
	UNIQUE (codigo_permiso)
);
GO

-- Tabla: roles
CREATE TABLE roles (
	id_rol INTEGER NOT NULL IDENTITY, 
	nombre_rol VARCHAR(50) NOT NULL, 
	descripcion VARCHAR(255) NULL, 
	activo BIT NOT NULL, 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id_rol), 
	UNIQUE (nombre_rol)
);
GO

-- Tabla: roles_pantallas
CREATE TABLE roles_pantallas (
	id_rol INTEGER NOT NULL, 
	id_pantalla INTEGER NOT NULL, 
	PRIMARY KEY (id_rol, id_pantalla), 
	FOREIGN KEY(id_rol) REFERENCES roles (id_rol), 
	FOREIGN KEY(id_pantalla) REFERENCES pantallas (id_pantalla)
);
GO

-- Tabla: roles_permisos
CREATE TABLE roles_permisos (
	id_rol INTEGER NOT NULL, 
	id_permiso INTEGER NOT NULL, 
	PRIMARY KEY (id_rol, id_permiso), 
	FOREIGN KEY(id_rol) REFERENCES roles (id_rol), 
	FOREIGN KEY(id_permiso) REFERENCES permisos (id_permiso)
);
GO

-- Tabla: usuarios
CREATE TABLE usuarios (
	id_usuario INTEGER NOT NULL IDENTITY, 
	nombre_usuario VARCHAR(50) NOT NULL, 
	nombre_completo VARCHAR(150) NOT NULL, 
	correo_electronico VARCHAR(120) NOT NULL, 
	clave_hash VARCHAR(255) NOT NULL, 
	id_rol INTEGER NOT NULL, 
	activo BIT NOT NULL, 
	origen_autenticacion VARCHAR(20) NOT NULL, 
	fecha_creacion DATETIME NOT NULL, 
	fecha_ultimo_acceso DATETIME NULL, 
	PRIMARY KEY (id_usuario), 
	UNIQUE (correo_electronico), 
	FOREIGN KEY(id_rol) REFERENCES roles (id_rol)
);
GO

CREATE UNIQUE INDEX ix_usuarios_nombre_usuario ON usuarios (nombre_usuario);
GO

-- Tabla: excepciones_pantallas_usuario
CREATE TABLE excepciones_pantallas_usuario (
	id_excepcion INTEGER NOT NULL IDENTITY, 
	id_usuario INTEGER NOT NULL, 
	id_pantalla INTEGER NOT NULL, 
	permitido BIT NOT NULL, 
	motivo VARCHAR(255) NULL, 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id_excepcion), 
	FOREIGN KEY(id_usuario) REFERENCES usuarios (id_usuario), 
	FOREIGN KEY(id_pantalla) REFERENCES pantallas (id_pantalla)
);
GO

-- Tabla: vistas
CREATE TABLE vistas (
	id_vista INTEGER NOT NULL IDENTITY, 
	codigo_vista VARCHAR(150) NOT NULL, 
	nombre_vista VARCHAR(150) NOT NULL, 
	descripcion VARCHAR(255) NULL, 
	tipo_ingesta VARCHAR(30) NOT NULL, 
	ruta_archivo_parquet VARCHAR(255) NULL, 
	contrato_esquema_json TEXT NULL, 
	configuracion_json TEXT NULL, 
	consulta_sql TEXT NULL, 
	id_conexion INTEGER NULL, 
	id_cubo INTEGER NULL, 
	creado_por_usuario_id INTEGER NULL, 
	estado_habilitado BIT NOT NULL, 
	fecha_ultima_ejecucion DATETIME NULL, 
	activo BIT NOT NULL, 
	fecha_creacion DATETIME NOT NULL, 
	fecha_modificacion DATETIME NULL, 
	PRIMARY KEY (id_vista), 
	UNIQUE (codigo_vista), 
	FOREIGN KEY(id_conexion) REFERENCES conexiones_bases_datos (id_conexion), 
	FOREIGN KEY(id_cubo) REFERENCES cubos (id_cubo), 
	FOREIGN KEY(creado_por_usuario_id) REFERENCES usuarios (id_usuario)
);
GO

-- Tabla: excepciones_usuario
CREATE TABLE excepciones_usuario (
	id_excepcion INTEGER NOT NULL IDENTITY, 
	id_usuario INTEGER NOT NULL, 
	id_vista INTEGER NOT NULL, 
	permitido BIT NOT NULL, 
	motivo VARCHAR(255) NULL, 
	fecha_creacion DATETIME NOT NULL, 
	PRIMARY KEY (id_excepcion), 
	FOREIGN KEY(id_usuario) REFERENCES usuarios (id_usuario), 
	FOREIGN KEY(id_vista) REFERENCES vistas (id_vista)
);
GO

-- Tabla: filtros_seguridad_fila
CREATE TABLE filtros_seguridad_fila (
	id_filtro INTEGER NOT NULL IDENTITY, 
	id_usuario INTEGER NOT NULL, 
	id_vista INTEGER NOT NULL, 
	columna_filtro VARCHAR(50) NOT NULL, 
	operador_filtro VARCHAR(10) NOT NULL, 
	valor_filtro VARCHAR(100) NOT NULL, 
	activo BIT NOT NULL, 
	PRIMARY KEY (id_filtro), 
	FOREIGN KEY(id_usuario) REFERENCES usuarios (id_usuario), 
	FOREIGN KEY(id_vista) REFERENCES vistas (id_vista)
);
GO

-- Tabla: roles_vistas
CREATE TABLE roles_vistas (
	id_rol INTEGER NOT NULL, 
	id_vista INTEGER NOT NULL, 
	PRIMARY KEY (id_rol, id_vista), 
	FOREIGN KEY(id_rol) REFERENCES roles (id_rol), 
	FOREIGN KEY(id_vista) REFERENCES vistas (id_vista)
);
GO

