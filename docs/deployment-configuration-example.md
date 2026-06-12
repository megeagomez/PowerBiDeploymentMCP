# Ejemplo de Uso: Sistema de Configuración de Despliegues

Este documento muestra un ejemplo completo de uso del sistema de configuración de despliegues.

## Escenario

Tienes un proyecto de Power BI con:
- 2 modelos semánticos: "Sales Model" y "Inventory Model"
- 3 informes:
  - "Sales Dashboard" (usa Sales Model)
  - "Inventory Report" (usa Inventory Model)
  - "Executive Summary" (usa Sales Model)

Quieres configurar un ambiente de desarrollo para que todas las subidas sean automáticas.

## Paso 1: Configuración Inicial del Ambiente

### Opción A: Configuración Manual (Una por una)

```json
// 1. Configurar Sales Model
{
  "tool": "configure_semantic_model_deployment",
  "arguments": {
    "model_name": "Sales Model",
    "target_workspace_name": "DEV - Analytics",
    "auto_deploy": true,
    "notes": "Modelo de ventas principal"
  }
}

// 2. Configurar Inventory Model
{
  "tool": "configure_semantic_model_deployment",
  "arguments": {
    "model_name": "Inventory Model",
    "target_workspace_name": "DEV - Analytics",
    "auto_deploy": true,
    "notes": "Modelo de inventario"
  }
}

// 3. Configurar Sales Dashboard
{
  "tool": "configure_report_deployment",
  "arguments": {
    "report_name": "Sales Dashboard",
    "target_workspace_name": "DEV - Analytics",
    "target_semantic_model_name": "Sales Model",
    "target_model_workspace_name": "DEV - Analytics",
    "auto_deploy": true,
    "auto_rebind": true,
    "notes": "Dashboard principal de ventas"
  }
}

// 4. Configurar Inventory Report
{
  "tool": "configure_report_deployment",
  "arguments": {
    "report_name": "Inventory Report",
    "target_workspace_name": "DEV - Analytics",
    "target_semantic_model_name": "Inventory Model",
    "target_model_workspace_name": "DEV - Analytics",
    "auto_deploy": true,
    "auto_rebind": true
  }
}

// 5. Configurar Executive Summary
{
  "tool": "configure_report_deployment",
  "arguments": {
    "report_name": "Executive Summary",
    "target_workspace_name": "DEV - Analytics",
    "target_semantic_model_name": "Sales Model",
    "target_model_workspace_name": "DEV - Analytics",
    "auto_deploy": true,
    "auto_rebind": true
  }
}
```

### Opción B: Configuración Rápida (Todo de una vez) ✅ RECOMENDADO

```json
{
  "tool": "setup_development_environment",
  "arguments": {
    "workspace_name": "DEV - Analytics",
    "semantic_models": [
      "Sales Model",
      "Inventory Model"
    ],
    "report_mappings": {
      "Sales Dashboard": "Sales Model",
      "Inventory Report": "Inventory Model",
      "Executive Summary": "Sales Model"
    }
  }
}
```

**Respuesta:**
```json
{
  "success": true,
  "environment": "development",
  "workspace": "DEV - Analytics",
  "configuration": {
    "profile_id": 1,
    "workspace_name": "DEV - Analytics",
    "semantic_models": [
      {
        "id": 1,
        "model_name": "Sales Model",
        "target_workspace": "DEV - Analytics"
      },
      {
        "id": 2,
        "model_name": "Inventory Model",
        "target_workspace": "DEV - Analytics"
      }
    ],
    "reports": [
      {
        "id": 1,
        "report_name": "Sales Dashboard",
        "target_workspace": "DEV - Analytics",
        "rebind_to": "Sales Model"
      },
      {
        "id": 2,
        "report_name": "Inventory Report",
        "target_workspace": "DEV - Analytics",
        "rebind_to": "Inventory Model"
      },
      {
        "id": 3,
        "report_name": "Executive Summary",
        "target_workspace": "DEV - Analytics",
        "rebind_to": "Sales Model"
      }
    ]
  },
  "message": "Ambiente de desarrollo configurado: DEV - Analytics\n  - 2 modelos semánticos\n  - 3 informes"
}
```

## Paso 2: Verificar Configuraciones

```json
{
  "tool": "list_deployment_configs",
  "arguments": {}
}
```

**Respuesta:**
```json
{
  "success": true,
  "profiles": [
    {
      "id": 1,
      "profile_name": "development",
      "target_workspace_name": "DEV - Analytics",
      "environment_type": "development",
      "is_active": true
    }
  ],
  "semantic_models": [
    {
      "id": 1,
      "model_name": "Sales Model",
      "target_workspace_name": "DEV - Analytics",
      "auto_deploy": true,
      "profile_id": 1
    },
    {
      "id": 2,
      "model_name": "Inventory Model",
      "target_workspace_name": "DEV - Analytics",
      "auto_deploy": true,
      "profile_id": 1
    }
  ],
  "reports": [
    {
      "id": 1,
      "report_name": "Sales Dashboard",
      "target_workspace_name": "DEV - Analytics",
      "target_semantic_model_name": "Sales Model",
      "auto_deploy": true,
      "auto_rebind": true,
      "profile_id": 1
    },
    // ... otros reports
  ],
  "summary": {
    "profiles": 1,
    "semantic_models": 2,
    "reports": 3
  }
}
```

## Paso 3: Usar Configuraciones Automáticas

### Subir Semantic Model

```json
{
  "tool": "upload_semantic_model",
  "arguments": {
    "workspace_name": "DEV - Analytics",
    "source_path": "C:\\powerbi\\models\\sales.pbix"
  }
}
```

**Lo que ocurre internamente:**
1. ✅ El servidor detecta que es "Sales Model" (del nombre del archivo)
2. ✅ Busca configuración guardada: encuentra que va a "DEV - Analytics"
3. ✅ Usa el workspace configurado automáticamente
4. ✅ Sube el modelo
5. ✅ Registra el despliegue en metadata

**Respuesta:**
```json
{
  "success": true,
  "workspace": "DEV - Analytics",
  "dataset_name": "Sales Model",
  "dataset_id": "abc-123-def",
  "operation": "updated",
  "used_config": true,
  "message": "Modelo semántico subido usando configuración guardada"
}
```

### Subir Report con Rebinding Automático

```json
{
  "tool": "upload_report",
  "arguments": {
    "workspace_name": "DEV - Analytics",
    "source_path": "C:\\powerbi\\reports\\sales-dashboard"
  }
}
```

**Lo que ocurre internamente:**
1. ✅ Detecta que es "Sales Dashboard"
2. ✅ Busca configuración: encuentra rebinding a "Sales Model"
3. ✅ Busca "Sales Model" en "DEV - Analytics"
4. ✅ **Reenlaza automáticamente el report a ese modelo**
5. ✅ Sube el report
6. ✅ Registra despliegue y rebinding

**Respuesta:**
```json
{
  "success": true,
  "workspace": "DEV - Analytics",
  "report_name": "Sales Dashboard",
  "report_id": "xyz-456-abc",
  "rebind_performed": true,
  "rebind_to_model": "Sales Model",
  "used_config": true,
  "message": "Informe subido y reenlazado a 'Sales Model' automáticamente"
}
```

## Paso 4: Consultar Historial

### Ver Despliegues Recientes

```
Resource: deployments://recent
```

**Respuesta:**
```json
[
  {
    "artifact_name": "Sales Dashboard",
    "artifact_type": "Report",
    "workspace_name": "DEV - Analytics",
    "upload_timestamp": "2026-05-16T10:30:00",
    "operation_type": "update",
    "asset_id": "xyz-456-abc"
  },
  {
    "artifact_name": "Sales Model",
    "artifact_type": "SemanticModel",
    "workspace_name": "DEV - Analytics",
    "upload_timestamp": "2026-05-16T10:28:00",
    "operation_type": "update",
    "asset_id": "abc-123-def"
  }
]
```

### Ver Historial de un Workspace

```
Resource: deployments://DEV - Analytics
```

Devuelve todo el historial de despliegues en ese workspace.

## Paso 5: Workflows Avanzados con Prompts

### Backup del Workspace

```
Prompt: backup-workspace
Arguments: {
  "workspace_name": "DEV - Analytics",
  "backup_path": "C:\\backups\\2026-05-16",
  "include_semantic_models": true,
  "include_reports": true
}
```

**Guía generada:**
```markdown
# Backup del Workspace: DEV - Analytics

Voy a ayudarte a crear un backup completo del workspace 'DEV - Analytics'.

## Pasos a seguir:

1. **Listar contenido del workspace**
   - Primero obtendremos la lista de todos los assets en el workspace

2. **Descargar modelos semánticos** ✓
   - Descargaremos todos los semantic models en formato PBIX/PBIP

3. **Descargar informes** ✓
   - Descargaremos todos los reports en formato PBIR

4. **Organizar estructura de carpetas**
   - Estructura sugerida:
     ```
     C:\backups\2026-05-16/
     ├── semantic-models/
     └── reports/
     ```

¿Deseas proceder con el backup?
```

### Sincronización Local → Cloud

```
Prompt: sync-local-to-cloud
Arguments: {
  "local_path": "C:\\powerbi\\project",
  "target_workspace": "DEV - Analytics",
  "dry_run": true
}
```

**Guía generada:**
```markdown
# Sincronización Local → Cloud

Sincronizando archivos desde: `C:\powerbi\project`
Hacia workspace: **DEV - Analytics**
Modo: 🔍 DRY RUN (solo análisis)

## Proceso de Sincronización:

### 1. Escaneo Local
- Buscar archivos PBIX, PBIP, PBIR en el directorio
- Calcular hash de archivos para detectar cambios

### 2. Comparación con Cloud
- Consultar workspace_mappings en metadata
- Identificar:
  - ✨ **Nuevos**: Sales Model (nunca subido)
  - 🔄 **Modificados**: Inventory Model (cambió desde última subida)
  - ✓ **Sin cambios**: Executive Summary

### 3. Aplicación de Configuraciones
- Usar configuraciones guardadas para rebinding automático

### 4. Simulación
- Se subirían: 1 nuevo, 1 modificado
- Se saltarían: 1 sin cambios
```

## Paso 6: Ver Estado del Servidor

### Configuración del Servidor

```
Resource: config://server
```

**Respuesta:**
```json
{
  "server_name": "powerbi-mcp-deployment",
  "version": "0.1.0",
  "database": {
    "path": "C:\\Users\\user\\.powerbi-mcp-deployment\\metadata.duckdb",
    "schema_version": 2
  },
  "versioning": {
    "enabled": "auto",
    "format": "%Y%m%d_%H%M%S"
  }
}
```

### Estadísticas de Metadata

```
Resource: metadata://stats
```

**Respuesta:**
```json
{
  "database_health": "healthy",
  "statistics": {
    "total_downloads": 15,
    "total_uploads": 23,
    "active_mappings": 5,
    "deployment_profiles": 1,
    "semantic_model_configs": 2,
    "report_configs": 3,
    "recent_deployments": 8
  },
  "timestamp": "2026-05-16T10:35:00"
}
```

### Todas las Configuraciones

```
Resource: config://deployments
```

Devuelve todas las configuraciones de deployment_profiles, semantic_model_configs y report_configs.

## Resumen

Con este sistema:

1. ✅ **Configuras una vez** usando `setup_development_environment`
2. ✅ **Subes automáticamente** - el servidor usa las configuraciones guardadas
3. ✅ **Rebinding automático** - los reports se enlazan al modelo correcto
4. ✅ **Historial completo** - todo queda registrado en metadata
5. ✅ **Resources para monitoreo** - ves el estado en tiempo real
6. ✅ **Prompts para workflows** - guías interactivas para operaciones complejas

**Próximo paso**: Usar estas configuraciones para migraciones entre ambientes (DEV → TEST → PROD)
