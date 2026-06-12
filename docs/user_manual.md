# Manual de Usuario — Power BI MCP Deployment Server

> **Versión**: 0.2.0  
> **Plataforma**: Windows  
> **Audiencia**: Usuarios de Power BI / Microsoft Fabric que quieren automatizar despliegues sin necesidad de conocimientos de programación ni infraestructura DevOps.

---

## 1. La Necesidad: ¿Qué Problema Resuelve?

### El ciclo de vida habitual de un informe Power BI

El trabajo con Power BI tiene un patrón repetitivo que todos reconocen: diseñas o modificas un modelo semántico o un informe en Power BI Desktop, y luego necesitas publicarlo al servicio Power BI (o Microsoft Fabric) para que otros lo usen. Hasta ahí, el proceso manual de "Publicar" desde el escritorio funciona bien.

El problema aparece cuando quieres dar un paso más:

- **¿Qué versión del informe está en producción?** ¿La de ayer o la de esta mañana?
- **¿Cómo muevo un informe de DEV a TEST sin que se desconecte del modelo semántico correcto?**
- **¿Hay un histórico de lo que se ha desplegado y cuándo?**
- **¿Puedo automatizar la publicación sin que el usuario que despliega tenga permisos directos en el workspace de producción?**

### Lo que ofrece Microsoft hoy

Microsoft tiene tres opciones principales para gestionar este ciclo de vida de forma más profesional:

| Solución | Descripción | Requisito principal |
|---|---|---|
| **[Deployment Pipelines de Fabric](https://learn.microsoft.com/en-us/fabric/cicd/deployment-pipelines/intro-to-deployment-pipelines)** | Pipelines visuales DEV→TEST→PROD dentro del portal de Fabric | Licencia Fabric/Premium capacity |
| **[fabric-cicd](https://microsoft.github.io/fabric-cicd/latest/)** (oficial desde feb. 2026) | Librería Python para despliegue code-first desde control de versiones | Git + Azure DevOps o GitHub Actions |
| **[pyfabricops](https://github.com/alisonpezzott/pyfabricops)** | Wrapper Python de las REST APIs de Fabric y Power BI | Conocimientos de Python y APIs |

Estas soluciones son excelentes, pero tienen un denominador común: **requieren infraestructura y conocimientos técnicos que muchas organizaciones pequeñas y medianas no tienen todavía**. `fabric-cicd` asume que ya tienes Git, ramas de entorno, y pipelines en Azure DevOps o GitHub Actions configurados. Los Deployment Pipelines de Fabric requieren una licencia Fabric o Premium.

### La brecha que cubre este servidor MCP

Este servidor cubre un escenario muy concreto y frecuente: **equipos que ya trabajan con Power BI de forma profesional, que tienen entornos separados (DEV, TEST, PROD), pero que aún no han establecido una política formal de DevOps**. El servidor funciona directamente desde un asistente de IA (GitHub Copilot, Claude Desktop…), lo que significa que el usuario puede describir en lenguaje natural lo que quiere hacer y el asistente ejecutará las operaciones correctas sobre Power BI.

---

## 2. Funcionalidades del Servidor MCP

### ¿Qué es un servidor MCP?

MCP (Model Context Protocol) es un protocolo abierto que permite a los asistentes de IA (como GitHub Copilot o Claude) invocar herramientas externas de forma estructurada. Cuando este servidor está configurado, el asistente puede ejecutar operaciones reales sobre Power BI — descargar, subir, listar workspaces, etc. — simplemente porque el usuario se lo pide en lenguaje natural.

### Catálogo de funcionalidades

#### A. Exploración de Workspaces

| Herramienta | Qué hace |
|---|---|
| `list_workspaces` | Lista todos los workspaces a los que tienes acceso, con filtros opcionales por nombre |
| `get_workspace_contents` | Muestra todos los artefactos de un workspace: modelos semánticos, informes y dashboards |
| `list_semantic_models` | Lista únicamente los modelos semánticos de un workspace |

**Ejemplo de uso conversacional:**
> "Muéstrame todos los workspaces que contienen 'Ventas' en el nombre"  
> "¿Qué informes hay en el workspace de Desarrollo?"

---

#### B. Descarga de Artefactos

| Herramienta | Formatos soportados |
|---|---|
| `download_semantic_model` | PBIX, PBIP |
| `download_report` | PBIR (formato moderno), JSON (legacy) |

**Versionado automático**: si descargas fuera de un repositorio Git, el servidor añade automáticamente un sufijo de fecha y hora al nombre del archivo (`ventas_20260610_143045.pbix`). Dentro de un repositorio Git, respeta el control de versiones existente y no añade sufijo.

**Ejemplo de uso:**
> "Descarga el modelo 'Sales Model' del workspace de Producción en formato PBIP a C:\modelos\"

---

#### C. Publicación de Artefactos

| Herramienta | Descripción |
|---|---|
| `upload_semantic_model` | Publica un modelo semántico (PBIX o PBIP) en un workspace |
| `upload_report` | Publica un informe (PBIR o JSON), con opción de reenlazar a otro modelo semántico |

El **reenlace automático de informes** (`rebind_to_model`) es especialmente útil al promover entre entornos: un informe descargado de DEV puede subirse a TEST apuntando al modelo semántico de TEST, no al de DEV.

**Ejemplo de uso:**
> "Sube el informe 'Dashboard Ventas' de la carpeta C:\informes\ al workspace de Test y enlázalo al modelo 'Sales Model TEST'"

---

#### D. Configuración de Despliegues Automáticos

Esta es la funcionalidad más avanzada. Permite configurar una vez adónde va cada artefacto y cómo se comporta, para que los despliegues futuros sean automáticos.

| Herramienta | Qué configura |
|---|---|
| `configure_semantic_model_deployment` | Define el workspace de destino y si el despliegue es automático |
| `configure_report_deployment` | Define workspace de destino, modelo semántico al que enlazar, y si el reenlace es automático |
| `setup_development_environment` | Configura de una sola vez un entorno completo (workspace + lista de modelos + mapeo informe→modelo) |
| `get_deployment_config` | Consulta la configuración guardada para un artefacto concreto |
| `list_deployment_configs` | Lista todas las configuraciones activas |

**Flujo de trabajo típico después de configurar:**
1. Descargas el modelo de producción al disco local.
2. Lo modificas con Power BI Desktop.
3. Le dices al asistente: "Sube el modelo Sales Model al entorno de desarrollo".
4. El servidor detecta automáticamente el workspace correcto desde la configuración y lo sube sin preguntarte más datos.

---

#### E. Historial y Auditoría

| Herramienta | Información que devuelve |
|---|---|
| `query_version_history` | Historial de descargas de un artefacto (cuándo, a qué ruta, qué versión) |
| `query_deployments` | Historial de publicaciones en un workspace (qué se subió, cuándo, qué ID se generó) |

Toda esta información se guarda en una base de datos local [DuckDB](https://duckdb.org/) en `~/.powerbi-mcp-deployment/metadata.duckdb`.

---

#### F. Recursos de Monitorización (Resources)

Los recursos son "vistas de estado" que el asistente puede consultar en cualquier momento sin que tú tengas que pedírselo explícitamente:

| Recurso | Información |
|---|---|
| `auth://status` | Si el servidor está autenticado y cuándo expira el token |
| `config://server` | Configuración activa del servidor |
| `metadata://stats` | Estadísticas de la base de datos local |
| `deployments://recent` | Los 10 últimos despliegues realizados |
| `workspaces://summary` | Resumen de workspaces con historial de actividad |
| `config://deployments` | Todas las configuraciones de despliegue guardadas |
| `deployments://{nombre_workspace}` | Historial completo de un workspace concreto |

---

#### G. Flujos de Trabajo Guiados (Prompts)

Los prompts son flujos interactivos que el asistente puede lanzar para guiarte paso a paso en operaciones complejas:

| Prompt | Qué hace |
|---|---|
| `backup-workspace` | Guía para hacer una copia de seguridad completa de un workspace |
| `deploy-workspace` | Guía para desplegar todos los artefactos de un workspace a otro |
| `sync-local-to-cloud` | Sincroniza archivos locales con el servicio Power BI |
| `migrate-report` | Migra un informe entre workspaces con reenlace de modelo |
| `deployment-pipeline` | Guía el pipeline completo DEV → TEST → PROD |
| `configure-deployment` | Asistente interactivo para configurar despliegues automáticos |

---

### Autenticación

El servidor usa **Device Flow** (flujo de dispositivo) de Microsoft, el mismo mecanismo que usa Power BI Desktop cuando inicias sesión. La primera vez que ejecutes una operación:

1. El servidor muestra un código y una URL (`https://microsoft.com/devicelogin`).
2. Abres el navegador, introduces el código y te autenticas con tu cuenta corporativa.
3. El token se guarda de forma cifrada en tu equipo usando **Windows DPAPI** (el almacén de credenciales seguro de Windows).

Los tokens se renuevan automáticamente. Solo necesitarás repetir el proceso si cierras sesión manualmente o si el token se corrompe.

> **Nota para administradores**: La autenticación puede cambiarse de Device Flow a **App Registration (Service Principal)** para despliegues no interactivos o para que usuarios de negocio desplieguen sin tener permisos directos en el workspace de destino. Esto requiere una modificación menor en el código de autenticación (`powerbi_mcp_server/auth/`).

---

### Formatos de archivo soportados

| Formato | Tipo | Descripción |
|---|---|---|
| `.pbix` | Modelo semántico | Formato binario clásico de Power BI Desktop |
| `.pbip` | Modelo semántico | Formato de proyecto (carpeta con `model.bim` y `item.metadata.json`), recomendado para control de versiones |
| `.pbir` | Informe | Formato moderno basado en carpeta (`report.json`, `definition.pbir`), recomendado |
| JSON | Informe | Formato legacy de definición de informe; sigue soportado pero se prefiere PBIR |

---

## 3. Entornos Donde Es Especialmente Útil

Este servidor encaja mejor en estos contextos:

### Equipos medianos sin infraestructura DevOps madura
Tienes 2-10 desarrolladores/analistas trabajando sobre Power BI, tienes workspaces de DEV y PROD (quizás también TEST), pero no tienes pipelines de Azure DevOps ni GitHub Actions configurados, y nadie en el equipo tiene perfil de DevOps. Con este servidor puedes tener **un ciclo de vida básico pero controlado** sin necesidad de montar esa infraestructura.

### Usuarios de negocio que versionan informes en Power BI
Un analista descarga el informe de producción, lo modifica, y quiere publicarlo de vuelta sin que el proceso sea manual y sin tener permisos de administrador en el workspace de producción. Con una App Registration configurada por el administrador una sola vez, el analista puede usar el servidor a través del asistente sin ver credenciales ni permisos.

### Entornos con restricciones de licencia
Los **Deployment Pipelines** de Fabric requieren licencia Fabric o Premium. Este servidor funciona con cualquier licencia de Power BI Pro estándar y usa las REST APIs públicas de Power BI y Fabric.

### Auditoría y trazabilidad básica sin herramientas externas
Necesitas saber qué se desplegó, cuándo y desde qué fichero local, pero no tienes un sistema de ITSM o CMDB. La base de datos DuckDB actúa como registro local de actividad.

---

## 4. Requisitos

- **Sistema operativo**: Windows (el cifrado de tokens usa Windows DPAPI)
- **Python**: 3.10 o superior
- **Cuenta Power BI**: con permisos mínimos de Visualizador para descargas, Colaborador para publicaciones
- **Cliente MCP compatible**: GitHub Copilot (VS Code), Claude Desktop, o cualquier cliente MCP

---

## 5. Instalación y Configuración Básica

### Paso 1: Instalar el servidor

```powershell
# Desde el directorio del proyecto
pip install -r requirements.txt
pip install -e .
```

### Paso 2: Configurar el cliente MCP

**Para GitHub Copilot (VS Code)** — añadir a `settings.json`:
```json
{
  "github.copilot.chat.mcp.servers": {
    "powerbi": {
      "command": "powerbi-mcp-deployment",
      "env": {
        "POWERBI_MCP_DB_PATH": "${userHome}/.powerbi-mcp-deployment/metadata.duckdb"
      }
    }
  }
}
```

**Para Claude Desktop** — añadir a `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "powerbi": {
      "command": "powerbi-mcp-deployment",
      "env": {
        "POWERBI_MCP_DB_PATH": "C:\\Users\\TuUsuario\\.powerbi-mcp-deployment\\metadata.duckdb"
      }
    }
  }
}
```

### Paso 3: Primera autenticación

Abre el chat de tu asistente de IA y escribe:

> "Lista mis workspaces de Power BI"

El servidor te mostrará un código y una URL para autenticarte. Tras hacerlo una vez, el token queda guardado.

---

## 6. Ventajas e Inconvenientes Frente a Otras Soluciones

### Comparativa general

| Criterio | Este servidor MCP | fabric-cicd (Microsoft) | Deployment Pipelines (Fabric) | Power BI REST API directa |
|---|---|---|---|---|
| **Conocimientos requeridos** | Lenguaje natural + IA | Python + Git + CI/CD | Ninguno (UI visual) | Python/REST + conocimientos API |
| **Infraestructura necesaria** | Ninguna (local) | Git + Azure DevOps / GitHub Actions | Portal de Fabric | Ninguna |
| **Licencia requerida** | Pro estándar | Pro estándar | **Fabric / Premium** | Pro estándar |
| **Historial de despliegues** | Sí (DuckDB local) | Git history | Sí (portal Fabric) | No (hay que construirlo) |
| **Reenlace automático de informes** | Sí | Sí (via PBIP) | Sí (nativo) | Manual |
| **Soporte de formatos** | PBIX, PBIP, PBIR, JSON | PBIP, PBIR | Nativo (todos) | Depende del endpoint |
| **Desplegable sin permisos directos** | Sí (con App Registration) | Sí (con SP) | Requiere permisos en pipeline | Sí (con SP) |
| **Curva de aprendizaje** | Muy baja | Media-alta | Baja (UI) | Alta |
| **Límite de plataforma** | Windows únicamente | Multiplataforma | Navegador web | Multiplataforma |
| **Artefactos soportados** | Semantic Models + Reports | Amplio (Notebooks, Lakehouses…) | Todos los de Fabric | Depende del endpoint |

---

### Ventajas de este servidor MCP

**1. Interfaz en lenguaje natural**  
No hay que aprender sintaxis de scripts ni configurar YAML. Le dices al asistente lo que quieres en español y él ejecuta las operaciones. Esto elimina la barrera de entrada para analistas que no son desarrolladores.

**2. Sin infraestructura previa**  
`fabric-cicd` es potente pero asume que ya tienes Git integrado con Fabric, ramas de entorno y un pipeline de CI/CD. Este servidor funciona desde el primer minuto, sin repositorios, sin pipelines y sin agentes de build.

**3. Funciona con licencias Pro estándar**  
Los Deployment Pipelines nativos de Fabric requieren una suscripción Fabric o Premium capacity. Este servidor usa las REST APIs públicas de Power BI que están disponibles con cualquier licencia Pro.

**4. Trazabilidad local**  
La base de datos DuckDB actúa como un registro local de auditoría: qué se descargó, qué se subió, cuándo, y desde qué archivo. Útil cuando no hay herramientas corporativas de ITSM.

**5. Configuración "configura una vez, despliega siempre"**  
El sistema de perfiles de despliegue permite que un administrador configure una sola vez la relación "este informe va a este workspace y se enlaza a este modelo", y a partir de ahí los despliegues son automáticos y sin errores de configuración manual.

**6. Reenlace de informes entre entornos**  
Al promover un informe de DEV a TEST, el servidor puede reenlazarlo automáticamente al modelo semántico de TEST en lugar del de DEV, evitando el error más común en esta operación.

---

### Inconvenientes y Limitaciones

**1. Solo Windows**  
El cifrado seguro de tokens usa la API DPAPI de Windows. No hay soporte para macOS ni Linux en la versión actual.

**2. Artefactos soportados más limitados que `fabric-cicd`**  
El servidor cubre modelos semánticos e informes. No despliega Notebooks, Lakehouses, Data Pipelines ni otros artefactos de Fabric. `fabric-cicd` tiene soporte más amplio.

**3. Sin integración nativa con Git**  
El servidor detecta si estás dentro de un repositorio Git para gestionar el versionado, pero no hace commits, no crea ramas ni disparadores automáticos. Es un sistema de despliegue asistido, no un pipeline de CI/CD completo.

**4. Base de datos local, no compartida**  
El historial de despliegues se guarda en DuckDB en el equipo local del usuario. No es una base de datos compartida en red; si varios usuarios despliegan desde equipos distintos, cada uno tiene su propio registro.

**5. Depende de un asistente de IA**  
El servidor necesita un cliente MCP compatible (GitHub Copilot, Claude Desktop, etc.) para ser usado de forma conversacional. Sin un cliente MCP, se puede invocar programáticamente pero pierde su ventaja principal.

**6. Versión alpha**  
El proyecto está en fase Alpha (v0.2.0). La API puede cambiar entre versiones y hay áreas que aún se están desarrollando (ver sección de siguientes pasos).

---

## 7. Conclusiones y Siguientes Pasos

### Conclusión

El **Power BI MCP Deployment Server** no pretende competir con `fabric-cicd` ni con los Deployment Pipelines nativos de Fabric. Cubre un nicho muy específico y real: **el espacio intermedio entre el "publicar desde el escritorio" manual y el pipeline de CI/CD corporativo completo**.

Es especialmente valioso para organizaciones que ya trabajan con Power BI de forma profesional, mantienen entornos separados, y quieren dar el siguiente paso hacia la automatización sin la complejidad de montar infraestructura DevOps. La integración con asistentes de IA elimina la curva de aprendizaje técnico y hace que el proceso sea accesible a perfiles de analista de negocio.

Con una pequeña modificación en el módulo de autenticación para usar App Registration en lugar de Device Flow, el servidor permite que usuarios sin permisos directos en los workspaces de producción puedan desplegar de forma controlada y auditada.

### Siguientes Pasos Recomendados

#### Para el usuario final
- [ ] Instalar y configurar el servidor en el entorno local
- [ ] Autenticarse y verificar acceso a los workspaces con `list_workspaces`
- [ ] Configurar los entornos con `setup_development_environment`
- [ ] Hacer una primera descarga y subida de prueba en un workspace de desarrollo
- [ ] Revisar el historial con `query_deployments` y los recursos de monitorización

#### Áreas de mejora del proyecto (para colaboradores)

**Alta prioridad:**
- [ ] Soporte para autenticación via Service Principal / App Registration (sin interacción del usuario)
- [ ] Soporte para más artefactos de Fabric: Data Pipelines, Notebooks
- [ ] Implementar promoción automática entre entornos (DEV → TEST → PROD) de forma end-to-end

**Media prioridad:**
- [ ] Compatibilidad con macOS/Linux (sustituir DPAPI por un gestor de credenciales multiplataforma)
- [ ] Opción de base de datos de metadata compartida en red para equipos multi-usuario
- [ ] Integración con Git: commit automático al descargar, tags de versión

**Baja prioridad:**
- [ ] Interfaz de consulta de historial más rica (exportar a Excel, filtros avanzados)
- [ ] Notificaciones de despliegue (Teams, correo)
- [ ] Soporte para dashboards de Power BI

---

## Apéndice: Variables de Entorno

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `POWERBI_MCP_DB_PATH` | `~/.powerbi-mcp-deployment/metadata.duckdb` | Ruta a la base de datos de metadata |
| `POWERBI_MCP_LOG_LEVEL` | `INFO` | Nivel de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `POWERBI_MCP_VERSIONING_ENABLED` | Auto-detect (Git) | `true` para forzar versionado, `false` para desactivarlo |
| `POWERBI_MCP_VERSION_FORMAT` | `%Y%m%d_%H%M%S` | Formato del sufijo de versión (Python strftime) |
| `POWERBI_MCP_CACHE_DIR` | `~/.powerbi-mcp-deployment/cache` | Directorio de caché de tokens |

---

## Apéndice: Resolución de Problemas Rápida

| Síntoma | Causa probable | Solución |
|---|---|---|
| "Error de autenticación" / HTTP 401 | Token expirado o corrupto | Borrar `~\.powerbi-mcp-deployment\cache\tokens.encrypted` y volver a autenticarse |
| "Workspace no encontrado" | Nombre incorrecto (distingue mayúsculas) | Usar `list_workspaces` para ver el nombre exacto |
| HTTP 429 (rate limit) | Demasiadas peticiones en poco tiempo | El servidor reintenta automáticamente; esperar unos minutos si persiste |
| "database is locked" | Dos instancias del servidor corriendo | Cerrar todos los procesos `powerbi-mcp-deployment` y reiniciar |
| Formato no detectado | Estructura de carpeta incorrecta | Especificar el formato explícitamente en el parámetro `format` |

Para más detalles, consulta la [guía de resolución de problemas completa](troubleshooting.md).

---

*Manual generado para la versión 0.2.0 del Power BI MCP Deployment Server.*

---

### Fuentes y Referencias

- [fabric-cicd — Documentación oficial](https://microsoft.github.io/fabric-cicd/latest/)
- [Anuncio de soporte oficial de fabric-cicd (Microsoft Blog)](https://blog.fabric.microsoft.com/en-us/blog/announcing-official-support-for-microsoft-fabric-cicd-tool/)
- [CI/CD en Microsoft Fabric: Deployment Pipelines vs fabric-cicd (Bravent)](https://www.bravent.net/en/news/ci-cd-in-microsoft-fabric-different-approaches-to-automating-data-solution-deployments/)
- [Desplegar Power BI Projects (PBIP) con fabric-cicd — Microsoft Learn](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-deploy-fabric-cicd)
- [Opciones de flujo CI/CD en Fabric — Microsoft Learn](https://learn.microsoft.com/en-us/fabric/cicd/manage-deployment)
- [pyfabricops — GitHub](https://github.com/alisonpezzott/pyfabricops)
