"""
MCP Prompts

Implements prompts for the Power BI MCP server that guide users
through common workflows and operations.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# Prompt definitions
PROMPTS = {
    'backup-workspace': {
        'name': 'backup-workspace',
        'description': 'Guía interactiva para crear un backup completo de un workspace de Power BI',
        'arguments': [
            {
                'name': 'workspace_name',
                'description': 'Nombre del workspace a respaldar',
                'required': True
            },
            {
                'name': 'backup_path',
                'description': 'Ruta local donde guardar el backup',
                'required': True
            },
            {
                'name': 'include_semantic_models',
                'description': 'Incluir modelos semánticos en el backup',
                'required': False
            },
            {
                'name': 'include_reports',
                'description': 'Incluir informes en el backup',
                'required': False
            }
        ]
    },
    
    'deploy-workspace': {
        'name': 'deploy-workspace',
        'description': 'Guía interactiva para desplegar todos los assets de un workspace a otro ambiente',
        'arguments': [
            {
                'name': 'source_workspace',
                'description': 'Workspace de origen',
                'required': True
            },
            {
                'name': 'target_workspace',
                'description': 'Workspace de destino',
                'required': True
            },
            {
                'name': 'environment',
                'description': 'Tipo de ambiente (development, test, production)',
                'required': False
            }
        ]
    },
    
    'sync-local-to-cloud': {
        'name': 'sync-local-to-cloud',
        'description': 'Compara archivos locales con Power BI y sube los cambios detectados',
        'arguments': [
            {
                'name': 'local_path',
                'description': 'Ruta local con los archivos a sincronizar',
                'required': True
            },
            {
                'name': 'target_workspace',
                'description': 'Workspace de destino en Power BI',
                'required': True
            },
            {
                'name': 'dry_run',
                'description': 'Solo mostrar cambios sin aplicarlos',
                'required': False
            }
        ]
    },
    
    'migrate-report': {
        'name': 'migrate-report',
        'description': 'Mueve un informe de un workspace a otro, reenlazando al modelo semántico correcto',
        'arguments': [
            {
                'name': 'report_name',
                'description': 'Nombre del informe a migrar',
                'required': True
            },
            {
                'name': 'source_workspace',
                'description': 'Workspace de origen',
                'required': True
            },
            {
                'name': 'target_workspace',
                'description': 'Workspace de destino',
                'required': True
            },
            {
                'name': 'target_semantic_model',
                'description': 'Modelo semántico al que reenlazar en el destino',
                'required': False
            }
        ]
    },
    
    'deployment-pipeline': {
        'name': 'deployment-pipeline',
        'description': 'Guía para desplegar desde Dev → Test → Prod con validaciones',
        'arguments': [
            {
                'name': 'artifact_name',
                'description': 'Nombre del artefacto a desplegar',
                'required': True
            },
            {
                'name': 'artifact_type',
                'description': 'Tipo de artefacto (SemanticModel o Report)',
                'required': True
            },
            {
                'name': 'target_environment',
                'description': 'Ambiente destino (test o production)',
                'required': True
            }
        ]
    },
    
    'configure-deployment': {
        'name': 'configure-deployment',
        'description': 'Configura el despliegue automático para un modelo semántico o informe',
        'arguments': [
            {
                'name': 'artifact_name',
                'description': 'Nombre del artefacto',
                'required': True
            },
            {
                'name': 'artifact_type',
                'description': 'Tipo (SemanticModel o Report)',
                'required': True
            }
        ]
    }
}


class PromptHandlers:
    """Handles MCP prompt execution"""
    
    def __init__(self, metadata_manager, tool_handlers):
        self.metadata = metadata_manager
        self.tools = tool_handlers
    
    async def backup_workspace(self, arguments: Dict[str, Any]) -> str:
        """
        Generate backup workspace workflow prompt
        
        Returns a guided prompt for backing up a workspace
        """
        workspace_name = arguments.get('workspace_name')
        backup_path = arguments.get('backup_path')
        include_models = arguments.get('include_semantic_models', True)
        include_reports = arguments.get('include_reports', True)
        
        prompt = f"""# Backup del Workspace: {workspace_name}

Voy a ayudarte a crear un backup completo del workspace '{workspace_name}'.

## Pasos a seguir:

1. **Listar contenido del workspace**
   - Primero obtendremos la lista de todos los assets en el workspace

2. **Descargar modelos semánticos** {'✓' if include_models else '✗'}
   {'- Descargaremos todos los semantic models en formato PBIX/PBIP' if include_models else ''}

3. **Descargar informes** {'✓' if include_reports else '✗'}
   {'- Descargaremos todos los reports en formato PBIR' if include_reports else ''}

4. **Organizar estructura de carpetas**
   - Estructura sugerida:
     ```
     {backup_path}/
     ├── semantic-models/
     └── reports/
     ```

5. **Registrar metadata del backup**
   - Guardaremos información de versión y timestamp

¿Deseas proceder con el backup? 

Puedo empezar ejecutando:
- `get_workspace_contents` para ver qué hay en el workspace
- Luego descargar cada asset automáticamente
"""
        
        logger.info(f"Generated backup-workspace prompt for {workspace_name}")
        return prompt
    
    async def deploy_workspace(self, arguments: Dict[str, Any]) -> str:
        """
        Generate deploy workspace workflow prompt
        """
        source_workspace = arguments.get('source_workspace')
        target_workspace = arguments.get('target_workspace')
        environment = arguments.get('environment', 'development')
        
        prompt = f"""# Despliegue de Workspace

Voy a ayudarte a desplegar assets desde '{source_workspace}' hacia '{target_workspace}'.

## Información del despliegue:

- **Origen**: {source_workspace}
- **Destino**: {target_workspace}
- **Ambiente**: {environment}

## Proceso:

### 1. Análisis Previo
- Listar assets en workspace de origen
- Verificar configuraciones de despliegue existentes
- Identificar dependencias (reports → semantic models)

### 2. Estrategia de Despliegue

**Modelos Semánticos:**
- Verificar si ya existen en destino (actualizar vs crear)
- Aplicar configuraciones guardadas si existen

**Informes:**
- Identificar modelos semánticos requeridos
- Configurar rebinding automático según memoria de configuración
- Verificar que los modelos existan en destino

### 3. Ejecución
- Desplegar semantic models primero
- Desplegar reports con rebinding automático
- Registrar todos los deployments en metadata

## ¿Qué deseas hacer?

a) Ver la configuración actual de despliegue para este workspace
b) Proceder con el despliegue automático
c) Configurar mappings antes de desplegar
d) Desplegar solo ciertos assets

Dime tu preferencia y procederemos.
"""
        
        logger.info(f"Generated deploy-workspace prompt: {source_workspace} → {target_workspace}")
        return prompt
    
    async def sync_local_to_cloud(self, arguments: Dict[str, Any]) -> str:
        """
        Generate sync local to cloud workflow prompt
        """
        local_path = arguments.get('local_path')
        target_workspace = arguments.get('target_workspace')
        dry_run = arguments.get('dry_run', False)
        
        prompt = f"""# Sincronización Local → Cloud

Sincronizando archivos desde: `{local_path}`
Hacia workspace: **{target_workspace}**
Modo: {'🔍 DRY RUN (solo análisis)' if dry_run else '📤 DEPLOY (aplicará cambios)'}

## Proceso de Sincronización:

### 1. Escaneo Local
- Buscar archivos PBIX, PBIP, PBIR en `{local_path}`
- Identificar tipo de cada archivo
- Calcular hash de archivos para detectar cambios

### 2. Comparación con Cloud
- Consultar workspace_mappings en metadata
- Identificar:
  - ✨ **Nuevos**: Archivos que nunca se han subido
  - 🔄 **Modificados**: Archivos que cambiaron desde última subida
  - ✓ **Sin cambios**: Archivos idénticos a última versión

### 3. Aplicación de Configuraciones
- Verificar si existen configuraciones de despliegue para cada archivo
- Aplicar rebinding automático para reports
- Usar configuraciones guardadas de workspace destino

### 4. {'Simulación' if dry_run else 'Ejecución'}
{'- Mostrar qué cambios se aplicarían (sin ejecutar)' if dry_run else '- Subir archivos nuevos/modificados'}
{'- Reportar estadísticas' if dry_run else '- Actualizar metadata y workspace_mappings'}

¿Proceder con la sincronización?
"""
        
        logger.info(f"Generated sync-local-to-cloud prompt for {local_path}")
        return prompt
    
    async def migrate_report(self, arguments: Dict[str, Any]) -> str:
        """
        Generate migrate report workflow prompt
        """
        report_name = arguments.get('report_name')
        source_workspace = arguments.get('source_workspace')
        target_workspace = arguments.get('target_workspace')
        target_model = arguments.get('target_semantic_model')
        
        prompt = f"""# Migración de Informe

Migrando informe: **{report_name}**
Desde: {source_workspace}
Hacia: {target_workspace}
{f'Reenlazar a: {target_model}' if target_model else ''}

## Pasos de Migración:

### 1. Verificación Pre-Migración
- Confirmar que el informe existe en workspace de origen
- Identificar modelo semántico actual
- Verificar que el workspace destino existe

### 2. Identificación de Dependencias
{f'- Verificar que el modelo "{target_model}" existe en workspace destino' if target_model else '- Buscar configuración guardada de rebinding'}
- Validar compatibilidad (tablas, columnas, medidas)

### 3. Descarga Temporal
- Descargar informe en formato PBIR
- Preservar recursos estáticos (imágenes, temas)

### 4. Rebinding del Modelo
{f'- Actualizar conexión para apuntar a "{target_model}"' if target_model else '- Usar configuración guardada o mantener modelo original'}
- Actualizar workspace reference

### 5. Subida al Destino
- Subir informe reconfigurado a {target_workspace}
- Registrar migración en metadata
- Guardar configuración para futuras migraciones

## ¿Continuar con la migración?

{'✓ Configuración completa - listo para migrar' if target_model else '⚠ Necesito saber a qué modelo reenlazar en destino'}
"""
        
        logger.info(f"Generated migrate-report prompt for {report_name}")
        return prompt
    
    async def deployment_pipeline(self, arguments: Dict[str, Any]) -> str:
        """
        Generate deployment pipeline workflow prompt
        """
        artifact_name = arguments.get('artifact_name')
        artifact_type = arguments.get('artifact_type')
        target_env = arguments.get('target_environment')
        
        prompt = f"""# Pipeline de Despliegue

Artefacto: **{artifact_name}** ({artifact_type})
Destino: **{target_env.upper()}**

## Pipeline: Dev → Test → Prod

{'```mermaid\ngraph LR\n    A[Development] -->|Promover| B[Test]\n    B -->|Promover| C[Production]\n    style ' + ('B fill:#f9f' if target_env == 'test' else 'C fill:#f9f') + '\n```'}

## Verificaciones de {target_env.upper()}:

### ✓ Pre-checks
- Confirmar que el artefacto existe en ambiente previo
- Verificar última versión y cambios
- Validar dependencias (para reports)

### 📋 Validaciones de Ambiente
"""
        
        if target_env == 'test':
            prompt += """
**Test Environment:**
- ✓ Workspace de test configurado
- ✓ Modelos semánticos de test disponibles
- ✓ Permisos de despliegue verificados
"""
        else:  # production
            prompt += """
**Production Environment:**
- ⚠ **CRÍTICO**: Validación en Test completada
- ✓ Aprobación de cambios documentada
- ✓ Backup de versión actual creado
- ✓ Plan de rollback preparado
"""
        
        prompt += f"""

### 🚀 Proceso de Promoción
1. Descargar desde ambiente anterior
2. Aplicar configuraciones de {target_env}
3. Subir a workspace de {target_env}
4. Verificar funcionamiento
5. Registrar deployment

## Estado Actual:

"""
        
        # Check if config exists
        prompt += "Consultando configuración guardada...\n\n"
        prompt += "¿Proceder con la promoción?"
        
        logger.info(f"Generated deployment-pipeline prompt: {artifact_name} → {target_env}")
        return prompt
    
    async def configure_deployment(self, arguments: Dict[str, Any]) -> str:
        """
        Generate configure deployment workflow prompt
        """
        artifact_name = arguments.get('artifact_name')
        artifact_type = arguments.get('artifact_type')
        
        prompt = f"""# Configurar Despliegue Automático

Configurando: **{artifact_name}** ({artifact_type})

Esta configuración se guardará en la base de datos y se usará automáticamente
en futuros despliegues.

## Configuración para {artifact_type}:

"""
        
        if artifact_type == 'SemanticModel':
            prompt += """
### Modelo Semántico

Necesito saber:

1. **Workspace de Destino (Development)**
   - ¿A qué workspace debe ir este modelo en desarrollo?
   
2. **Despliegue Automático**
   - ¿Subir automáticamente cuando se detecten cambios locales?
   
3. **Notas**
   - Cualquier información adicional sobre este modelo

Una vez configurado, cuando ejecutes `upload_semantic_model`, el sistema:
- Automáticamente usará el workspace configurado
- Aplicará las reglas de despliegue guardadas
- Registrará todo en metadata
"""
        else:  # Report
            prompt += """
### Informe

Necesito saber:

1. **Workspace de Destino (Development)**
   - ¿A qué workspace debe ir este informe en desarrollo?
   
2. **Modelo Semántico Target**
   - ¿A qué modelo semántico debe apuntar?
   - ¿En qué workspace está ese modelo?
   
3. **Rebinding Automático**
   - ¿Reenlazar automáticamente al subir?
   
4. **Despliegue Automático**
   - ¿Subir automáticamente cuando se detecten cambios locales?
   
5. **Notas**
   - Cualquier información adicional

Una vez configurado, cuando ejecutes `upload_report`, el sistema:
- Automáticamente usará el workspace configurado
- Reenlazará al modelo semántico correcto
- Aplicará las reglas de despliegue guardadas
- Registrará todo en metadata
"""
        
        prompt += """

## ¿Cómo proceder?

Puedo hacerte preguntas interactivas o puedes proporcionarme la configuración directamente.

Formato de configuración:
```json
{
  "target_workspace": "Workspace Name",
  "target_semantic_model": "Model Name",  // solo para reports
  "auto_deploy": true,
  "auto_rebind": true,  // solo para reports
  "notes": "Notas adicionales"
}
```

¿Cómo deseas configurar este artefacto?
"""
        
        logger.info(f"Generated configure-deployment prompt for {artifact_name}")
        return prompt


def get_prompt_by_name(name: str) -> Dict[str, Any]:
    """Get prompt definition by name"""
    return PROMPTS.get(name)


def list_all_prompts() -> List[Dict[str, Any]]:
    """List all available prompts"""
    return list(PROMPTS.values())
