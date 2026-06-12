"""
MCP Tool Schemas

Defines schemas for all MCP tools exposed by the Power BI MCP server.
"""

from typing import Dict

# Tool schemas following MCP protocol
TOOL_SCHEMAS: Dict[str, Dict] = {
    "list_workspaces": {
        "name": "list_workspaces",
        "description": "Lista todos los workspaces de Power BI accesibles al usuario autenticado. "
                      "Opcionalmente filtra por nombre usando una consulta OData.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Consulta OData opcional para filtrar workspaces (ej: \"name eq 'Mi Workspace'\")"
                }
            }
        }
    },
    
    "get_workspace_contents": {
        "name": "get_workspace_contents",
        "description": "Obtiene el contenido de un workspace específico: datasets, reports, dashboards. "
                      "Opcionalmente filtra por tipo de elemento.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_name": {
                    "type": "string",
                    "description": "Nombre del workspace"
                },
                "item_type": {
                    "type": "string",
                    "description": "Tipo de elemento opcional para filtrar ('SemanticModel', 'Report', 'Dashboard')"
                }
            },
            "required": ["workspace_name"]
        }
    },
    
    "download_semantic_model": {
        "name": "download_semantic_model",
        "description": "Download / descargar a Power BI semantic model (dataset) from a workspace to a local file. "
                      "Supports PBIX and PBIP formats. Use this to backup or export a semantic model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_name": {
                    "type": "string",
                    "description": "Nombre del workspace"
                },
                "dataset_name": {
                    "type": "string",
                    "description": "Nombre del modelo semántico a descargar"
                },
                "target_path": {
                    "type": "string",
                    "description": "Ruta local donde guardar el archivo/carpeta"
                },
                "format": {
                    "type": "string",
                    "description": "Formato de descarga: 'pbix' o 'pbip'. Si no se especifica, se detecta automáticamente.",
                    "enum": ["pbix", "pbip"]
                }
            },
            "required": ["workspace_name", "dataset_name", "target_path"]
        }
    },
    
    "upload_semantic_model": {
        "name": "upload_semantic_model",
        "description": "Upload / publicar / deploy a Power BI semantic model (dataset) from a local file to a workspace. "
                      "Supports PBIX and PBIP formats. Use this to publish or deploy a semantic model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_name": {
                    "type": "string",
                    "description": "Nombre del workspace de destino"
                },
                "source_path": {
                    "type": "string",
                    "description": "Ruta local del archivo/carpeta PBIX o PBIP"
                },
                "dataset_name": {
                    "type": "string",
                    "description": "Nombre opcional para el dataset (por defecto usa el nombre del archivo)"
                }
            },
            "required": ["workspace_name", "source_path"]
        }
    },
    
    "download_report": {
        "name": "download_report",
        "description": "Download / descargar a Power BI report from a workspace to a local folder. "
                      "Supports PBIR (modern) and legacy JSON formats. Use this to backup or export a report.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_name": {
                    "type": "string",
                    "description": "Nombre del workspace"
                },
                "report_name": {
                    "type": "string",
                    "description": "Nombre del informe a descargar"
                },
                "target_path": {
                    "type": "string",
                    "description": "Ruta local donde guardar la carpeta del informe"
                },
                "format": {
                    "type": "string",
                    "description": "Formato de descarga: 'pbir' o 'json'. Si no se especifica, se usa 'pbir'.",
                    "enum": ["pbir", "json"]
                }
            },
            "required": ["workspace_name", "report_name", "target_path"]
        }
    },
    
    "upload_report": {
        "name": "upload_report",
        "description": "Upload / publicar / deploy a Power BI report from a local folder to a workspace. "
                      "Supports PBIR and legacy JSON formats. Can rebind the report to a different semantic model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_name": {
                    "type": "string",
                    "description": "Nombre del workspace de destino"
                },
                "source_path": {
                    "type": "string",
                    "description": "Ruta local de la carpeta PBIR o archivo JSON"
                },
                "report_name": {
                    "type": "string",
                    "description": "Nombre opcional para el informe (por defecto usa el nombre de la carpeta)"
                },
                "rebind_to_model": {
                    "type": "string",
                    "description": "Nombre del modelo semántico al que reenlazar (opcional)"
                },
                "rebind_workspace_name": {
                    "type": "string",
                    "description": "Workspace donde buscar 'rebind_to_model' si está en un workspace distinto al de destino (opcional)"
                }
            },
            "required": ["workspace_name", "source_path"]
        }
    },

    "rebind_report": {
        "name": "rebind_report",
        "description": "Reenlaza un informe ya publicado a otro modelo semántico, sin volver a subir su contenido. "
                      "El modelo destino puede estar en el mismo workspace o en uno distinto (cross-workspace).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_name": {
                    "type": "string",
                    "description": "Workspace donde está publicado el informe"
                },
                "report_name": {
                    "type": "string",
                    "description": "Nombre del informe a reenlazar"
                },
                "target_model_name": {
                    "type": "string",
                    "description": "Nombre del modelo semántico al que reenlazar"
                },
                "target_model_workspace_name": {
                    "type": "string",
                    "description": "Workspace donde está el modelo semántico destino (por defecto, el mismo que 'workspace_name')"
                }
            },
            "required": ["workspace_name", "report_name", "target_model_name"]
        }
    },

    "download_workspace": {
        "name": "download_workspace",
        "description": "Download / descargar todos los semantic models y reports de un workspace a una carpeta local. "
                      "Descarga en formato PBIP y PBIR respectivamente. Útil para backups completos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_name": {
                    "type": "string",
                    "description": "Nombre del workspace a descargar"
                },
                "destination_path": {
                    "type": "string",
                    "description": "Carpeta base donde se guardará todo el contenido del workspace"
                },
                "include_semantic_models": {
                    "type": "boolean",
                    "description": "Incluir modelos semánticos (por defecto: true)"
                },
                "include_reports": {
                    "type": "boolean",
                    "description": "Incluir informes (por defecto: true)"
                }
            },
            "required": ["workspace_name", "destination_path"]
        }
    },

    "list_semantic_models": {
        "name": "list_semantic_models",
        "description": "Lista todos los modelos semánticos en un workspace específico.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_name": {
                    "type": "string",
                    "description": "Nombre del workspace"
                }
            },
            "required": ["workspace_name"]
        }
    },
    
    "query_version_history": {
        "name": "query_version_history",
        "description": "Consulta el historial de versiones de un artefacto (descargas registradas en metadatos).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artifact_name": {
                    "type": "string",
                    "description": "Nombre del artefacto"
                },
                "artifact_type": {
                    "type": "string",
                    "description": "Tipo de artefacto opcional ('SemanticModel', 'Report')"
                }
            },
            "required": ["artifact_name"]
        }
    },
    
    "query_deployments": {
        "name": "query_deployments",
        "description": "Consulta el historial de despliegues (uploads) a un workspace específico.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_name": {
                    "type": "string",
                    "description": "Nombre del workspace"
                }
            },
            "required": ["workspace_name"]
        }
    },
    
    "configure_semantic_model_deployment": {
        "name": "configure_semantic_model_deployment",
        "description": "Configura el despliegue automático para un modelo semántico. Guarda configuración de workspace destino y opciones.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model_name": {
                    "type": "string",
                    "description": "Nombre del modelo semántico"
                },
                "target_workspace_name": {
                    "type": "string",
                    "description": "Workspace de destino para despliegues"
                },
                "target_workspace_id": {
                    "type": "string",
                    "description": "ID del workspace de destino (opcional)"
                },
                "auto_deploy": {
                    "type": "boolean",
                    "description": "Desplegar automáticamente en futuras subidas"
                },
                "notes": {
                    "type": "string",
                    "description": "Notas sobre la configuración"
                }
            },
            "required": ["model_name", "target_workspace_name"]
        }
    },
    
    "configure_report_deployment": {
        "name": "configure_report_deployment",
        "description": "Configura el despliegue automático para un informe. Guarda configuración de workspace destino, modelo semántico para rebinding, y opciones.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "report_name": {
                    "type": "string",
                    "description": "Nombre del informe"
                },
                "target_workspace_name": {
                    "type": "string",
                    "description": "Workspace de destino para despliegues"
                },
                "target_workspace_id": {
                    "type": "string",
                    "description": "ID del workspace de destino (opcional)"
                },
                "target_semantic_model_name": {
                    "type": "string",
                    "description": "Modelo semántico al que reenlazar automáticamente"
                },
                "target_model_workspace_name": {
                    "type": "string",
                    "description": "Workspace donde está el modelo semántico target"
                },
                "auto_deploy": {
                    "type": "boolean",
                    "description": "Desplegar automáticamente en futuras subidas"
                },
                "auto_rebind": {
                    "type": "boolean",
                    "description": "Reenlazar automáticamente al modelo configurado"
                },
                "notes": {
                    "type": "string",
                    "description": "Notas sobre la configuración"
                }
            },
            "required": ["report_name", "target_workspace_name"]
        }
    },
    
    "get_deployment_config": {
        "name": "get_deployment_config",
        "description": "Obtiene la configuración de despliegue guardada para un artefacto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artifact_name": {
                    "type": "string",
                    "description": "Nombre del artefacto"
                },
                "artifact_type": {
                    "type": "string",
                    "description": "Tipo de artefacto ('SemanticModel' o 'Report')",
                    "enum": ["SemanticModel", "Report"]
                }
            },
            "required": ["artifact_name", "artifact_type"]
        }
    },
    
    "list_deployment_configs": {
        "name": "list_deployment_configs",
        "description": "Lista todas las configuraciones de despliegue guardadas (semantic models y reports).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artifact_type": {
                    "type": "string",
                    "description": "Filtrar por tipo de artefacto (opcional)",
                    "enum": ["SemanticModel", "Report"]
                }
            }
        }
    },
    
    "authenticate": {
        "name": "authenticate",
        "description": "Inicia la autenticación con Microsoft (Device Flow). "
                      "Devuelve la URL y el código para autenticarte en el navegador. "
                      "Llama a esta herramienta primero si cualquier otra herramienta falla con error de autenticación.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },

    "setup_development_environment": {
        "name": "setup_development_environment",
        "description": "Configura un entorno de desarrollo completo con workspace, semantic models y reports.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace_name": {
                    "type": "string",
                    "description": "Nombre del workspace de desarrollo"
                },
                "workspace_id": {
                    "type": "string",
                    "description": "ID del workspace (opcional)"
                },
                "semantic_models": {
                    "type": "array",
                    "description": "Lista de nombres de semantic models para este ambiente",
                    "items": {
                        "type": "string"
                    }
                },
                "report_mappings": {
                    "type": "object",
                    "description": "Mapeo de informes a semantic models: {report_name: semantic_model_name}"
                }
            },
            "required": ["workspace_name"]
        }
    }
}
