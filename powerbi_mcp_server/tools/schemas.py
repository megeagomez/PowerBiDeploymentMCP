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
        "description": "Download / descargar a Power BI semantic model (dataset) from a workspace to a local folder "
                      "in PBIP format (project folder). Use this to backup or export a semantic model. "
                      "(PBIX download is not supported by the Power BI API — export is report-level only.)",
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
                    "description": "Carpeta base del proyecto PBIP donde guardar el modelo"
                },
                "format": {
                    "type": "string",
                    "description": "Formato de descarga (solo 'pbip' está soportado)",
                    "enum": ["pbip"]
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
                },
                "folder_path": {
                    "type": "string",
                    "description": "Ruta de carpeta dentro del workspace, p.ej. 'Ventas/Modelos'. Se crea automáticamente si no existe (opcional)."
                }
            },
            "required": ["workspace_name", "source_path"]
        }
    },

    "download_report": {
        "name": "download_report",
        "description": "Download / descargar a Power BI report from a workspace to a local folder "
                      "in PBIR format (modern report project format). Use this to backup or export a report.",
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
                    "description": "Carpeta base del proyecto PBIP donde guardar el informe"
                }
            },
            "required": ["workspace_name", "report_name", "target_path"]
        }
    },
    
    "upload_report": {
        "name": "upload_report",
        "description": "Upload / publicar / deploy a Power BI report (PBIR folder) from a local folder to a workspace. "
                      "Can rebind the report to a semantic model in the same or a different workspace "
                      "(patches definition.pbir automatically). If the rebind model is not published yet but its "
                      ".SemanticModel folder sits next to the report folder, the model is deployed first. "
                      "If several models match the rebind name, returns 'needs_disambiguation' with candidates.",
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
                },
                "folder_path": {
                    "type": "string",
                    "description": "Ruta de carpeta dentro del workspace, p.ej. 'Ventas/Informes'. Se crea automáticamente si no existe (opcional)."
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
                },
                "profile_name": {
                    "type": "string",
                    "description": "Alias del entorno al que aplica esta configuración (opcional; sin él, se guarda/consulta sin distinguir entorno)"
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
                },
                "profile_name": {
                    "type": "string",
                    "description": "Alias del entorno al que aplica esta configuración (opcional; sin él, se guarda/consulta sin distinguir entorno)"
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
                },
                "profile_name": {
                    "type": "string",
                    "description": "Alias del entorno para el que consultar la configuración (opcional)"
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
        "description": "Inicia la autenticación con Microsoft. Llama a esta herramienta primero si "
                      "cualquier otra herramienta falla con error de autenticación. Por defecto "
                      "('auto') prueba primero la caché, luego una sesión de Azure CLI (az login) "
                      "activa, y solo si ninguna funciona lanza el Device Flow interactivo. "
                      "Útil para quien trabaja con varios clientes/tenants: usa 'device_flow' para "
                      "forzar un login interactivo nuevo (p. ej. para entrar con la cuenta de otro "
                      "cliente sin esperar a que caduque la sesión actual), o 'az_cli' para forzar "
                      "que recoja explícitamente la sesión de az login activa ahora mismo "
                      "(útil tras un 'az login --tenant <otro>').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "Método de autenticación a usar (por defecto 'auto')",
                    "enum": ["auto", "device_flow", "az_cli"]
                }
            }
        }
    },

    "logout": {
        "name": "logout",
        "description": "Cierra la sesión actual borrando el token cacheado localmente. La siguiente "
                      "operación requerirá autenticarte de nuevo (vía 'authenticate'). No cierra tu "
                      "sesión de Azure CLI (az login) — si esta herramienta seguía recogiendo esa "
                      "sesión automáticamente, la próxima llamada volverá a autenticar con ella salvo "
                      "que uses 'authenticate' con method='device_flow' para forzar otra cuenta.",
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
    },

    "configure_environment": {
        "name": "configure_environment",
        "description": "Crea o actualiza un entorno de despliegue (alias libre + posición en la cadena de "
                      "promoción vía stage_order). Ej: Desarrollo=1, Integración=2, Producción=3. "
                      "'promote_project' usa stage_order, no el nombre, para saber cuál es el entorno anterior.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile_name": {
                    "type": "string",
                    "description": "Alias del entorno (nombre libre, ej. 'Desarrollo', 'UAT', 'Producción')"
                },
                "target_workspace_name": {
                    "type": "string",
                    "description": "Workspace de Fabric asociado a este entorno"
                },
                "target_workspace_id": {
                    "type": "string",
                    "description": "ID del workspace (opcional, se resuelve por nombre si se omite)"
                },
                "stage_order": {
                    "type": "integer",
                    "description": "Posición en la cadena de promoción (0, 1, 2...). Debe ser único entre entornos."
                },
                "environment_type": {
                    "type": "string",
                    "description": "Etiqueta libre de tipo de entorno (ej. 'development', 'production')"
                },
                "description": {
                    "type": "string",
                    "description": "Descripción opcional del entorno"
                }
            },
            "required": ["profile_name", "target_workspace_name"]
        }
    },

    "list_environments": {
        "name": "list_environments",
        "description": "Lista los entornos de despliegue configurados, ordenados por su posición en la cadena "
                      "de promoción (stage_order).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },

    "create_project": {
        "name": "create_project",
        "description": "Crea un proyecto: una agrupación con nombre de varios modelos semánticos y reports "
                      "que se despliegan/promocionan juntos como una unidad.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Nombre único del proyecto"
                },
                "description": {
                    "type": "string",
                    "description": "Descripción opcional del proyecto"
                }
            },
            "required": ["project_name"]
        }
    },

    "add_project_artifact": {
        "name": "add_project_artifact",
        "description": "Añade un modelo semántico o un informe a un proyecto existente. Para reports, "
                      "'rebind_to_artifact_name' debe ser el nombre de un modelo semántico ya añadido al mismo "
                      "proyecto, y se usará para reenlazar el informe automáticamente tras cada deploy/promote.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Nombre del proyecto"
                },
                "artifact_type": {
                    "type": "string",
                    "description": "Tipo de artefacto",
                    "enum": ["SemanticModel", "Report"]
                },
                "artifact_name": {
                    "type": "string",
                    "description": "Nombre del modelo semántico o informe (debe coincidir con el nombre publicado en cada entorno)"
                },
                "rebind_to_artifact_name": {
                    "type": "string",
                    "description": "Solo para reports: nombre del modelo semántico del proyecto al que reenlazar"
                },
                "sequence_order": {
                    "type": "integer",
                    "description": "Orden opcional dentro de su tipo (desempate)"
                },
                "notes": {
                    "type": "string",
                    "description": "Notas opcionales"
                },
                "folder_path": {
                    "type": "string",
                    "description": "Ruta de carpeta dentro del workspace de destino para este artefacto, p.ej. "
                                  "'Ventas/Modelos'. Se crea automáticamente si no existe. Cada artefacto del "
                                  "proyecto puede tener su propia carpeta (opcional)."
                }
            },
            "required": ["project_name", "artifact_type", "artifact_name"]
        }
    },

    "remove_project_artifact": {
        "name": "remove_project_artifact",
        "description": "Quita un modelo semántico o informe de un proyecto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Nombre del proyecto"},
                "artifact_type": {"type": "string", "enum": ["SemanticModel", "Report"]},
                "artifact_name": {"type": "string", "description": "Nombre del artefacto a quitar"}
            },
            "required": ["project_name", "artifact_type", "artifact_name"]
        }
    },

    "get_project": {
        "name": "get_project",
        "description": "Obtiene un proyecto y la lista ordenada de sus artefactos (modelos primero, luego reports).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Nombre del proyecto"}
            },
            "required": ["project_name"]
        }
    },

    "list_projects": {
        "name": "list_projects",
        "description": "Lista todos los proyectos configurados.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },

    "deploy_project": {
        "name": "deploy_project",
        "description": "Despliega TODOS los artefactos de un proyecto desde una carpeta local a un entorno "
                      "concreto, saltándose la cadena de promoción. USO EXPLÍCITO SOLAMENTE: úsalo solo cuando "
                      "el usuario pida expresamente subir desde una carpeta local, o describa una emergencia/hotfix "
                      "(p.ej. 'despliega desde mi carpeta a producción', 'necesito un hotfix urgente en prod'). "
                      "Si el usuario simplemente dice 'despliega/promociona el proyecto X a Y' sin mencionar una "
                      "carpeta local ni una emergencia, usa 'promote_project' en su lugar, que es el flujo por defecto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Nombre del proyecto"},
                "environment": {"type": "string", "description": "Alias del entorno de destino"},
                "source_dir": {
                    "type": "string",
                    "description": "Carpeta base local que contiene las subcarpetas .SemanticModel/.Report de cada artefacto"
                },
                "respect_local_structure": {
                    "type": "boolean",
                    "description": "Si es true, busca cada artefacto recursivamente dentro de source_dir y replica "
                                  "esa misma jerarquía de subcarpetas como carpetas en el workspace destino, en vez "
                                  "de asumir una estructura plana. La folder_path configurada explícitamente en el "
                                  "artefacto (si existe) siempre tiene prioridad sobre la derivada. Por defecto false."
                }
            },
            "required": ["project_name", "environment", "source_dir"]
        }
    },

    "promote_project": {
        "name": "promote_project",
        "description": "FLUJO POR DEFECTO para 'despliega/promociona el proyecto X al entorno Y'. Mueve, en "
                      "memoria y sin tocar disco, lo que ya está actualmente desplegado en el entorno inmediatamente "
                      "anterior en la cadena de promoción (según stage_order) hacia 'environment'. Si detecta que el "
                      "entorno destino recibió cambios fuera de la cadena normal (p.ej. un 'deploy' de emergencia o "
                      "una edición manual en el portal Fabric), devuelve needs_confirmation=true con el detalle en "
                      "'drift' y NO escribe nada; para confirmar y sobrescribir, vuelve a llamar con confirm_drift=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Nombre del proyecto"},
                "environment": {"type": "string", "description": "Alias del entorno de destino"},
                "confirm_drift": {
                    "type": "boolean",
                    "description": "Confirma la sobrescritura cuando una llamada previa devolvió needs_confirmation=true (por defecto false)"
                }
            },
            "required": ["project_name", "environment"]
        }
    },

    "get_project_deployment_structure": {
        "name": "get_project_deployment_structure",
        "description": "Responde a '¿cuál es la estructura de despliegue del proyecto X?': lista los artefactos "
                      "del proyecto, su carpeta configurada, y para cada entorno definido (Desarrollo/Integración/"
                      "Producción...) el workspace destino y, si ya se desplegó algo ahí, cómo llegó (deploy directo "
                      "o promote, y desde qué entorno). Es solo lectura de configuración/estado guardado — no "
                      "consulta la API de Fabric en vivo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Nombre del proyecto"}
            },
            "required": ["project_name"]
        }
    },

    "list_fabric_capacities": {
        "name": "list_fabric_capacities",
        "description": "Lista las capacidades de Fabric disponibles (nombre, ID, SKU, región, estado). Útil para "
                      "encontrar el capacity_id a pasar a auto_provision_project_workspaces o "
                      "configure_project_workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },

    "configure_project_workspace": {
        "name": "configure_project_workspace",
        "description": "MODO MANUAL de creación de workspaces: registra (creándolo en Fabric si no existe todavía) "
                      "el workspace que un proyecto debe usar en un entorno concreto, con el nombre que tú elijas. "
                      "Si omites artifact_type, ese workspace se usa tanto para los modelos semánticos como para "
                      "los reports del proyecto en ese entorno (sin separar); si indicas 'SemanticModel' o 'Report', "
                      "solo aplica a ese tipo, permitiendo tener modelos y reports en workspaces distintos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Nombre del proyecto"},
                "environment": {"type": "string", "description": "Alias del entorno (debe existir, ver configure_environment)"},
                "workspace_name": {"type": "string", "description": "Nombre del workspace a usar/crear"},
                "artifact_type": {
                    "type": "string",
                    "description": "Opcional: 'SemanticModel' o 'Report' para separar; se omite para un workspace combinado",
                    "enum": ["SemanticModel", "Report"]
                },
                "capacity_id": {
                    "type": "string",
                    "description": "ID de capacidad de Fabric opcional a asignar si el workspace se crea nuevo (ver list_fabric_capacities)"
                }
            },
            "required": ["project_name", "environment", "workspace_name"]
        }
    },

    "auto_provision_project_workspaces": {
        "name": "auto_provision_project_workspaces",
        "description": "MODO AUTOMÁTICO de creación de workspaces: para el proyecto dado, asegura que existan los "
                      "entornos dev/acc/prod (creándolos con stage_order 1/2/3 si faltan) y crea/registra, por cada "
                      "uno, un workspace separado para modelos semánticos y otro para reports, con la convención "
                      "'{proyecto}_semantic{_dev|_acc|}' y '{proyecto}_reports{_dev|_acc|}' (prod sin sufijo). "
                      "Ej. para el proyecto 'Ventas': Ventas_semantic_dev, Ventas_reports_dev, Ventas_semantic_acc, "
                      "Ventas_reports_acc, Ventas_semantic, Ventas_reports.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Nombre del proyecto"},
                "capacity_id": {
                    "type": "string",
                    "description": "ID de capacidad de Fabric opcional a asignar a los workspaces creados (ver list_fabric_capacities)"
                }
            },
            "required": ["project_name"]
        }
    },

    "get_deployment_tree": {
        "name": "get_deployment_tree",
        "description": "Árbol visual (texto ASCII con '-' y '|') de proyectos → entornos → carpetas simuladas → "
                      "artefactos, con el workspace resuelto y la fecha del último despliegue de cada uno. Omite "
                      "project_name para ver todos los proyectos configurados a la vez.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "description": "Nombre del proyecto (opcional; si se omite, muestra todos)"}
            }
        }
    }
}
