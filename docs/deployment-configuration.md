# Sistema de Configuración de Despliegues

## Descripción General

El servidor MCP de Power BI ahora incluye un sistema completo de **memoria/configuración de despliegues** que permite automatizar subidas a desarrollo y preparar migraciones entre entornos.

## Nuevas Funcionalidades

### 1. **Configuración Persistente en DuckDB**

Tres nuevas tablas en la base de datos:

- **`deployment_profiles`**: Define perfiles de despliegue (dev, test, prod)
- **`semantic_model_configs`**: Configuración de a qué workspace va cada semantic model
- **`report_configs`**: Configuración de a qué workspace va cada report y a qué semantic model debe apuntar

### 2. **5 Nuevos Tools**

#### `configure_semantic_model_deployment`
Configura el despliegue automático para un modelo semántico.

```json
{
  "model_name": "Sales Model",
  "target_workspace_name": "Development",
  "auto_deploy": true,
  "notes": "Modelo de ventas principal"
}
```

#### `configure_report_deployment`
Configura el despliegue automático para un informe, incluyendo rebinding.

```json
{
  "report_name": "Sales Dashboard",
  "target_workspace_name": "Development",
  "target_semantic_model_name": "Sales Model",
  "target_model_workspace_name": "Development",
  "auto_deploy": true,
  "auto_rebind": true,
  "notes": "Dashboard de ventas"
}
```

#### `get_deployment_config`
Obtiene la configuración guardada para un artefacto.

```json
{
  "artifact_name": "Sales Model",
  "artifact_type": "SemanticModel"
}
```

#### `list_deployment_configs`
Lista todas las configuraciones de despliegue.

```json
{
  "artifact_type": "Report"  // opcional
}
```

#### `setup_development_environment`
Configura un entorno de desarrollo completo de una sola vez.

```json
{
  "workspace_name": "Development",
  "semantic_models": ["Sales Model", "Inventory Model", "HR Model"],
  "report_mappings": {
    "Sales Dashboard": "Sales Model",
    "Inventory Report": "Inventory Model",
    "HR Analytics": "HR Model"
  }
}
```

### 3. **7 Resources**

Los resources exponen datos que el cliente puede leer:

- **`config://server`**: Configuración del servidor
- **`auth://status`**: Estado de autenticación
- **`metadata://stats`**: Estadísticas de la base de datos
- **`deployments://recent`**: Últimos 10 despliegues
- **`workspaces://summary`**: Resumen de workspaces con historial
- **`deployments://{workspace_name}`**: Historial completo de un workspace
- **`config://deployments`**: Todas las configuraciones de despliegue

### 4. **6 Prompts**

Los prompts guían workflows interactivos:

- **`backup-workspace`**: Backup completo de un workspace
- **`deploy-workspace`**: Desplegar todos los assets entre workspaces
- **`sync-local-to-cloud`**: Sincronizar archivos locales con Power BI
- **`migrate-report`**: Migrar informe entre workspaces con rebinding
- **`deployment-pipeline`**: Pipeline Dev → Test → Prod
- **`configure-deployment`**: Configurar despliegue automático

## Flujo de Trabajo Típico

### Paso 1: Configurar Entorno de Desarrollo

```json
// Tool: setup_development_environment
{
  "workspace_name": "DEV - Sales",
  "semantic_models": [
    "Sales Model",
    "Customer Model"
  ],
  "report_mappings": {
    "Sales Dashboard": "Sales Model",
    "Customer Report": "Customer Model",
    "Executive Summary": "Sales Model"
  }
}
```

**Resultado**: Se crean automáticamente todas las configuraciones necesarias.

### Paso 2: Subir Artefactos (Ahora Automático)

```json
// Tool: upload_semantic_model
{
  "workspace_name": "DEV - Sales",  // Usa configuración guardada
  "source_path": "C:\\models\\sales.pbix"
}
```

El servidor:
1. ✅ Detecta que "Sales Model" tiene configuración guardada
2. ✅ Usa automáticamente el workspace configurado
3. ✅ Registra el despliegue en metadata

```json
// Tool: upload_report
{
  "workspace_name": "DEV - Sales",
  "source_path": "C:\\reports\\sales-dashboard"
}
```

El servidor:
1. ✅ Detecta que "Sales Dashboard" tiene configuración
2. ✅ Usa el workspace configurado
3. ✅ **Reenlaza automáticamente a "Sales Model"**
4. ✅ Registra el despliegue y rebinding

### Paso 3: Consultar Configuraciones

```json
// Tool: list_deployment_configs
{
  "artifact_type": "Report"
}
```

Devuelve todas las configuraciones de reports guardadas.

### Paso 4: Ver Recursos

```
// Resource: config://deployments
```

Muestra todas las configuraciones activas en formato JSON.

```
// Resource: deployments://DEV - Sales
```

Muestra todo el historial de despliegues en ese workspace.

### Paso 5: Usar Prompts para Workflows Complejos

```
// Prompt: deploy-workspace
{
  "source_workspace": "DEV - Sales",
  "target_workspace": "TEST - Sales",
  "environment": "test"
}
```

El prompt genera una guía interactiva paso a paso para el despliegue.

## Casos de Uso Avanzados

### Caso 1: Despliegue Completamente Automático

Una vez configurado:

```powershell
# Descargaste un modelo localmente y lo modificaste
# Ahora lo subes automáticamente al workspace correcto:

{
  "tool": "upload_semantic_model",
  "source_path": "C:\\models\\sales-updated.pbix"
}

# El servidor:
# - Detecta que es "Sales Model"
# - Lo sube a "DEV - Sales" automáticamente
# - Registra todo en metadata
```

### Caso 2: Reports con Rebinding Automático

```json
// Configuración una vez:
{
  "tool": "configure_report_deployment",
  "report_name": "Executive Dashboard",
  "target_workspace_name": "DEV - Executive",
  "target_semantic_model_name": "Consolidated Model",
  "auto_rebind": true
}

// Luego, cada vez que subas:
{
  "tool": "upload_report",
  "source_path": "C:\\reports\\executive"
}

// Se reenlaza automáticamente a "Consolidated Model"
```

### Caso 3: Migración entre Ambientes

```json
// 1. Configura DEV
{
  "tool": "setup_development_environment",
  "workspace_name": "DEV",
  "semantic_models": ["Model A"],
  "report_mappings": {"Report 1": "Model A"}
}

// 2. Configura TEST (separado)
{
  "tool": "setup_development_environment",
  "workspace_name": "TEST",
  "semantic_models": ["Model A"],
  "report_mappings": {"Report 1": "Model A"}
}

// 3. Usa el prompt para migrar
{
  "prompt": "deployment-pipeline",
  "artifact_name": "Model A",
  "artifact_type": "SemanticModel",
  "target_environment": "test"
}
```

## Base de Datos: Nuevas Tablas

### `deployment_profiles`
```sql
CREATE TABLE deployment_profiles (
    id INTEGER PRIMARY KEY,
    profile_name VARCHAR UNIQUE,      -- 'development', 'test', 'production'
    description VARCHAR,
    target_workspace_id VARCHAR,
    target_workspace_name VARCHAR,
    environment_type VARCHAR,         -- 'development', 'test', 'production'
    is_active BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
```

### `semantic_model_configs`
```sql
CREATE TABLE semantic_model_configs (
    id INTEGER PRIMARY KEY,
    model_name VARCHAR,
    local_path_pattern VARCHAR,
    target_workspace_id VARCHAR,
    target_workspace_name VARCHAR,
    profile_id INTEGER,               -- FK to deployment_profiles
    auto_deploy BOOLEAN,              -- ¿Subir automáticamente?
    deploy_on_change BOOLEAN,         -- ¿Subir al detectar cambios?
    notes VARCHAR,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
```

### `report_configs`
```sql
CREATE TABLE report_configs (
    id INTEGER PRIMARY KEY,
    report_name VARCHAR,
    local_path_pattern VARCHAR,
    target_workspace_id VARCHAR,
    target_workspace_name VARCHAR,
    target_semantic_model_id VARCHAR,     -- A qué modelo apuntar
    target_semantic_model_name VARCHAR,
    target_model_workspace_id VARCHAR,
    target_model_workspace_name VARCHAR,
    profile_id INTEGER,
    auto_deploy BOOLEAN,
    auto_rebind BOOLEAN,                  -- ¿Reenlazar automáticamente?
    notes VARCHAR,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
```

## Próximos Pasos

Con estas configuraciones en su lugar, puedes:

1. ✅ **Automatizar DEV**: Todos los despliegues a desarrollo se hacen con configuración guardada
2. ✅ **Preparar migraciones**: Las configuraciones sirven de base para migraciones entre ambientes
3. 🚧 **Próxima fase**: Funcionalidades de promoción entre entornos (DEV → TEST → PROD)

## API Reference

Ver archivos individuales:
- **Tools**: `powerbi_mcp_server/tools/schemas.py`
- **Resources**: `powerbi_mcp_server/resources.py`
- **Prompts**: `powerbi_mcp_server/prompts.py`
- **Config Manager**: `powerbi_mcp_server/metadata/deployment_config.py`
- **Database**: `powerbi_mcp_server/metadata/database.py`
