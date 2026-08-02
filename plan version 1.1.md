# Plan versión 1.1 — Power BI MCP Deployment

Plan de trabajo derivado de la revisión de código del 2026-08-02. Separado en **Bugs** (corregir comportamiento roto) y **Mejoras de funcionalidad** (nueva capacidad). Cada ítem incluye archivo(s) afectado(s), causa/contexto, fix propuesto y criterio de aceptación, para que pueda implementarse sin re-analizar el proyecto.

**Orden de implementación recomendado:** B1 → B2 → B3 → B4 → resto de bugs → F1 → F2 → F3 → F4 → resto de mejoras.

---

## BUGS

### B1. Rebinding roto para PBIP con informe + modelo en workspaces distintos (CRÍTICO)

- **Archivos:** `powerbi_mcp_server/api/reports.py` (método `upload_pbir`, ~línea 151), `powerbi_mcp_server/tools/handlers.py` (método `upload_report`).
- **Causa:** al subir con rebind solo se parchea `datasetId` dentro de `report.json`. En el formato PBIR moderno el enlace al modelo vive en **`definition.pbir`**, en el bloque `datasetReference`. Un PBIP descargado trae `{"datasetReference": {"byPath": {"path": "../X.SemanticModel"}}}`; si el informe se sube solo o a un workspace distinto del modelo, Fabric no encuentra el sibling y la subida falla.
- **Fix:** en `upload_pbir`, cuando se recibe `semantic_model_id` y el part procesado es `definition.pbir`, reescribir el `datasetReference` de `byPath` a `byConnection` (patrón usado por fabric-cicd de Microsoft):

  ```json
  {
    "datasetReference": {
      "byConnection": {
        "connectionString": null,
        "pbiServiceModelId": null,
        "pbiModelVirtualServerName": "sobe_wowvirtualserver",
        "pbiModelDatabaseName": "<semantic_model_id>",
        "name": "EntityDataSource",
        "connectionType": "pbiServiceXmlaStyleLive"
      }
    }
  }
  ```

  Conservar el campo `version` que traiga el archivo original. Mantener el parche de `report.json` para informes legacy.
- **Además:** en `handlers.upload_report`, si el directorio origen es un proyecto PBIP que contiene también carpeta `*.SemanticModel` hermana y se pide rebind a un modelo que aún no existe en el workspace destino del modelo, desplegar primero el modelo y usar su ID para el rebind (orquestación modelo → informe).
- **Aceptación:** subir un PBIP con informe y modelo, informe al workspace A y modelo al workspace B, en una sola operación, sin staging intermedio ni mover artefactos después. El informe queda enlazado al modelo de B.

### B2. `print()` a stdout corrompe el protocolo MCP

- **Archivo:** `powerbi_mcp_server/api/http_utils.py` (~línea 69).
- **Causa:** `request_with_retry` hace `print("⚠️ Rate limit alcanzado…")` a stdout. En un servidor MCP por stdio, stdout es el transporte JSON-RPC: ese print corrompe el protocolo justo cuando hay un 429.
- **Fix:** eliminar el `print`; dejar solo `logger.warning`. Revisar con grep que no quede ningún otro `print()` dentro del paquete `powerbi_mcp_server/`.
- **Aceptación:** `grep -rn "print(" powerbi_mcp_server/` no devuelve nada (fuera de docstrings/comentarios).

### B3. Re-autenticación obligatoria cada hora (caché MSAL no persistida)

- **Archivos:** `powerbi_mcp_server/auth/device_flow.py` (~línea 35), `powerbi_mcp_server/auth/token_manager.py`.
- **Causa:** `msal.PublicClientApplication` se crea sin token cache persistente, por lo que la caché MSAL es solo en memoria y `get_accounts()` siempre vuelve vacío entre procesos. Lo único persistido (DPAPI) es el access token, que caduca en ~1 h. El refresh token nunca sobrevive al proceso → device flow otra vez cada hora.
- **Fix:** usar `msal.SerializableTokenCache`, serializarla a disco cifrada con DPAPI (reutilizar `_encrypt_data`/`_decrypt_data` de `token_manager.py`; archivo p. ej. `~/.powerbi-mcp-deployment/cache/msal_cache.encrypted`). Cargarla al crear el `PublicClientApplication` (parámetro `token_cache=`) y guardarla si `cache.has_state_changed` tras cada operación. Crear una función helper `_get_msal_app()` que compartan `try_silent_auth`, `initiate_device_flow` y `complete_device_flow_sync`.
- **Aceptación:** autenticarse, matar el proceso, esperar a que el access token caduque (o borrarlo), arrancar de nuevo → `try_silent_auth` obtiene token sin device flow.

### B4. Cliente API con token congelado (401 tras expiración)

- **Archivos:** `powerbi_mcp_server/tools/handlers.py` (método `_ensure_authenticated`, ~línea 41), `powerbi_mcp_server/api/client.py`.
- **Causa:** `PowerBIClient` se construye una vez con el token de ese momento y se cachea en `self._client`. Si el servidor vive más que el token, todas las llamadas devuelven 401 hasta reiniciar.
- **Fix:** cambiar `PowerBIClient.__init__` para aceptar un `token_provider: Callable[[], str]` en lugar de un string, y construir los headers en cada request (o mediante una property `headers`). En `_ensure_authenticated`, pasar `auth.get_token` como provider. Alternativa mínima: comparar el token actual con el usado al construir el cliente y recrearlo si cambió.
- **Aceptación:** con un token renovado en disco (tras B3), una llamada a cualquier tool después de la expiración del token original funciona sin reiniciar el servidor.

### B5. `export_semantic_model` usa un endpoint inexistente

- **Archivo:** `powerbi_mcp_server/api/client.py` (~línea 212).
- **Causa:** hace `POST /groups/{ws}/datasets/{id}/export`. La API de Power BI no tiene export de datasets; el export a PBIX es de **reports** (`GET /groups/{ws}/reports/{id}/Export`, y exporta informe+modelo juntos).
- **Fix:** verificar contra la API real. Opciones: (a) eliminar la ruta PBIX para modelos y dejar solo PBIP (recomendado — PBIP es el formato de despliegue del proyecto); (b) reimplementar usando el export de reports cuando exista un informe asociado. Actualizar `download_semantic_model` en handlers y el schema `download_semantic_model` en `tools/schemas.py` en consecuencia.
- **Aceptación:** descargar un modelo no ofrece rutas que fallan; la opción PBIX o funciona de verdad o no se ofrece.

### B6. Rebind con coincidencia parcial elegida en silencio

- **Archivos:** `powerbi_mcp_server/tools/handlers.py` (~líneas 251-254 y 297-300), `powerbi_mcp_server/api/reports.py` (`find_semantic_models_by_name`).
- **Causa:** `find_semantic_models_by_name` devuelve matches parciales y los handlers cogen `models[0]` sin avisar → posible rebind al modelo equivocado.
- **Fix:** si hay exactamente 1 match exacto, usarlo. Si hay 0 exactos y ≥1 parciales, o >1 matches, NO ejecutar el rebind: devolver `{"success": false, "needs_disambiguation": true, "candidates": [...]}` con nombres e IDs para que el cliente (LLM) pregunte al usuario y reintente con el nombre exacto.
- **Aceptación:** con dos modelos "Ventas" y "Ventas Detalle", pedir rebind a "Ventas" usa el exacto; pedir rebind a "Venta" devuelve la lista de candidatos sin ejecutar nada.

### B7. Retry y LRO inconsistentes en operaciones Fabric

- **Archivo:** `powerbi_mcp_server/api/client.py` (`get_item_definition`, `create_item`, `update_item_definition`, `_poll_lro_operation`).
- **Causa:** estas operaciones usan `requests.post/get` directo, sin el retry de 429 que sí tienen las demás. El polling LRO ignora el header `Retry-After`, duerme 2 s fijos y tiene timeout de 120 s (corto para modelos grandes).
- **Fix:** usar `request_with_retry` en todas las llamadas HTTP del cliente. En `_poll_lro_operation`: respetar `Retry-After` si viene, y subir el timeout por defecto a 600 s (parametrizable).
- **Aceptación:** todas las llamadas HTTP del cliente pasan por `request_with_retry`; el LRO respeta `Retry-After`.

### B8. `call_tool` despacha con `getattr` sin validar

- **Archivo:** `powerbi_mcp_server/server.py` (~línea 77).
- **Causa:** `getattr(self.tool_handlers, name)` permite invocar cualquier método del handler (p. ej. `_ensure_authenticated`) como si fuera un tool.
- **Fix:** validar `name in TOOL_SCHEMAS` antes de despachar; si no está, devolver error "Unknown tool".
- **Aceptación:** llamar al tool `_ensure_authenticated` devuelve "Unknown tool".

### B9. `format: 'json'` de `download_report` se ignora (y descripción engañosa en upload)

- **Archivos:** `powerbi_mcp_server/tools/handlers.py` (`download_report`), `powerbi_mcp_server/tools/schemas.py` (`download_report`, `upload_report`).
- **Causa:** el schema ofrece `format: pbir|json` pero el handler siempre llama a `download_pbir`. La descripción de `upload_report` dice soportar "legacy JSON" y no es cierto.
- **Fix (mínimo, recomendado):** quitar `json` del enum y las menciones a legacy JSON de las descripciones. Documentar que el formato soportado es PBIR.
- **Aceptación:** schemas y comportamiento real coinciden.

### B10. Versionado automático solo aplica a PBIX

- **Archivos:** `powerbi_mcp_server/api/semantic_models.py` (`download_pbip`), `powerbi_mcp_server/api/reports.py` (`download_pbir`).
- **Causa:** las descargas PBIP/PBIR pasan `version_suffix=None` y sobrescriben la carpeta sin comprobar Git. La lógica de `VersioningManager` (auto-detección de Git) solo protege el caso PBIX.
- **Fix:** antes de sobrescribir una carpeta `.SemanticModel`/`.Report` existente fuera de un repo Git (usar `git_utils.is_git_repository`), renombrar la existente con sufijo timestamp (mismo formato `%Y%m%d_%H%M%S` de `VersioningConfig`) o descargar a carpeta versionada. Registrar el `version_suffix` en metadata.
- **Aceptación:** descargar dos veces el mismo modelo PBIP en carpeta sin Git no pierde la versión anterior; dentro de un repo Git se sobrescribe (comportamiento actual, correcto).

### B11. Inyección OData en filtro por nombre de workspace

- **Archivo:** `powerbi_mcp_server/api/client.py` (`get_workspace_by_name`, ~línea 102).
- **Causa:** interpola el nombre en `name eq '{workspace_name}'`; un apóstrofe en el nombre rompe el filtro.
- **Fix:** escapar `'` → `''` antes de interpolar.
- **Aceptación:** un workspace llamado `O'Brien Dev` se encuentra correctamente.

---

## MEJORAS DE FUNCIONALIDAD

### F1. Modelo de datos: proyectos, entornos y parámetros

- **Archivos:** `powerbi_mcp_server/metadata/database.py` (nuevo `SCHEMA_VERSION = 3` + migración), `powerbi_mcp_server/metadata/deployment_config.py`.
- **Contexto:** hoy la config es por artefacto con un único destino (`semantic_model_configs`/`report_configs` indexadas por nombre). `deployment_profiles.environment_type` existe pero los handlers nunca rellenan `profile_id` → la dimensión "entorno" está muerta. No existe el concepto "proyecto".
- **Nuevas tablas:**
  - `projects (id, project_name UNIQUE, description, created_at)`
  - `project_environments (id, project_id FK, environment VARCHAR CHECK IN ('dev','acc','prod'), models_workspace_id, models_workspace_name, reports_workspace_id, reports_workspace_name, created_at)` — workspaces de modelos e informes pueden diferir.
  - `project_artifacts (id, project_id FK, artifact_name, artifact_type CHECK IN ('SemanticModel','Report'), local_path_pattern, target_model_name NULL, created_at)` — `target_model_name` solo para reports (a qué modelo del proyecto se enlaza).
  - `parameter_values (id, project_id FK, model_name, parameter_name, environment, value, created_at, updated_at, UNIQUE(project_id, model_name, parameter_name, environment))`
- **Migración:** detectar versión < 3 en `initialize_schema` y crear las tablas nuevas sin tocar las existentes (siguen sirviendo para artefactos sueltos sin proyecto).
- **Aceptación:** arranca sobre una BD v2 existente sin perder datos; las tablas nuevas existen y hay CRUD en `MetadataDatabase` para cada una.

### F2. Tool `deploy_project(project, environment)` — el flujo "sube el proyecto X a dev/acc/prod"

- **Archivos:** `powerbi_mcp_server/tools/handlers.py`, `powerbi_mcp_server/tools/schemas.py`, `powerbi_mcp_server/metadata/deployment_config.py`.
- **Comportamiento:**
  1. Resolver proyecto y entorno en BD; si falta el proyecto o el entorno no está configurado → devolver `needs_configuration` (ver F3).
  2. Desplegar **modelos primero** (PBIP → workspace de modelos del entorno), obteniendo IDs.
  3. Aplicar **parámetros** del entorno (`parameter_values`) vía `POST /groups/{ws}/datasets/{id}/Default.UpdateParameters`. Si la API responde que el caller no es owner, intentar `POST .../Default.TakeOver` y reintentar una vez. Avisar en el resultado de que los parámetros no se aplican hasta un refresh.
  4. Desplegar **informes** con rebind vía `definition.pbir` (usa el fix B1) al workspace de informes del entorno, enlazados al ID del modelo recién desplegado.
  5. Registrar todo en `uploads` y devolver resumen: artefactos creados vs actualizados, parámetros aplicados, warnings.
- **Warning de primer despliegue:** `upsert_item` ya devuelve `created: bool`. Si `created=True`, incluir en el resultado un warning explícito: *"Primer despliegue de {artefacto} en {entorno}: hay que configurar credenciales/gateway del origen de datos en el portal y lanzar un refresh inicial."*
- **Aceptación:** con un proyecto configurado, una sola llamada `deploy_project("X", "acc")` deja modelos e informes en sus workspaces, parámetros de acc aplicados, e informa de qué era primera vez.

### F3. Flujo de primera subida: entrevista de configuración

- **Archivos:** `powerbi_mcp_server/tools/handlers.py` (`upload_semantic_model`, `upload_report`, `deploy_project`), `powerbi_mcp_server/tools/schemas.py` (nuevos tools `configure_project`, `add_artifact_to_project`, `set_parameter_values`).
- **Comportamiento:** cuando se sube un artefacto que no está en ningún proyecto ni tiene config individual, el tool NO sube a ciegas: devuelve

  ```json
  {
    "success": false,
    "needs_configuration": true,
    "questions": {
      "is_part_of_project": "¿Este artefacto forma parte de un proyecto más grande? ¿Cuál?",
      "environment": "¿A qué entorno pertenece este despliegue: dev, acc o prod?",
      "parameters": [ { "name": "...", "current_value": "..." } ]
    },
    "available_workspaces": [...],
    "next_step": "Llama a configure_project / add_artifact_to_project / set_parameter_values y reintenta"
  }
  ```

  El LLM cliente hace las preguntas al usuario y llama a los tools de configuración. Añadir un parámetro `skip_configuration: true` para permitir subida directa sin entrevista (comportamiento actual).
- **Nota:** existe esqueleto sin usar en `deployment_config.py` (`prompt_and_configure_model/report`, ~línea 197) — reutilizar o eliminar.
- **Aceptación:** subir un artefacto nuevo sin config devuelve las preguntas; con `skip_configuration: true` sube directamente como hoy.

### F4. Descubrimiento de parámetros de modelos

- **Archivos:** nuevo módulo `powerbi_mcp_server/api/parameters.py` (o dentro de `semantic_models.py`), `powerbi_mcp_server/api/client.py`.
- **Comportamiento:**
  - **Local (PBIP):** parsear parámetros M del modelo: en TMDL buscar en `definition/expressions.tmdl` expresiones con `IsParameterQuery=true`; en `model.bim` (JSON), buscar en `model.expressions` las que contengan `IsParameterQuery=true` en su expresión M. Extraer nombre y valor actual.
  - **Publicado:** `GET /groups/{ws}/datasets/{id}/parameters` en `client.py`.
  - Usado por F3 (para preguntar valores por entorno) y F2 (para validar que los parámetros configurados existen).
- **Aceptación:** dado un PBIP con 2 parámetros M, el descubrimiento devuelve sus nombres y valores actuales; para un dataset publicado, devuelve lo mismo vía API.

### F5. CLI sobre los handlers (eliminar duplicación)

- **Archivo:** `pbi_cli.py`.
- **Contexto:** el CLI reimplementa la lógica usando los módulos de bajo nivel; cada fix (p. ej. B1) habría que hacerlo dos veces.
- **Fix:** refactorizar el CLI para instanciar `MetadataManager` + `ToolHandlers` y llamar a los mismos handlers que usa el servidor (con `asyncio.run`). El CLI solo aporta parsing de argumentos, spinner y presentación. Añadir comandos nuevos: `deploy-project <proyecto> <entorno>`, `configure-project`, `set-params`.
- **Aceptación:** `pbi_cli.py` no importa `SemanticModelOperations`/`ReportOperations` directamente; todos los comandos pasan por `ToolHandlers`.

### F6. Eliminar/migrar código legacy

- **Archivos:** `powerbi_object_manager.py` (2.789 líneas), `pbi.py`.
- **Contexto:** duplican auth, retry y llamadas API fuera del paquete. Lo único con valor no cubierto por el paquete es la creación de estructura (workspaces/lakehouses/carpetas) desde YAML.
- **Fix:** migrar `create_structure_from_yaml` y las operaciones de creación de workspaces/lakehouses a un módulo del paquete (p. ej. `powerbi_mcp_server/api/provisioning.py`) usando `PowerBIClient`; después borrar `powerbi_object_manager.py` y `pbi.py`. Si no se quiere migrar aún, moverlos a una carpeta `legacy/` con README que indique que no se mantienen.
- **Aceptación:** no queda código de producción fuera de `powerbi_mcp_server/` + `pbi_cli.py`.

### F7. Tests

- **Archivos:** nuevo directorio `tests/`.
- **Mínimo viable (con `pytest`, API mockeada con `responses` o `unittest.mock`):**
  - Empaquetado de parts PBIP/PBIR (exclusión de `.pbi`/`.platform`, rutas con `/`).
  - Parcheo de `definition.pbir` byPath → byConnection (B1) — el test más importante.
  - Desambiguación de modelos (B6).
  - Migración de esquema v2 → v3 (F1) sobre BD temporal.
  - `request_with_retry` con 429 y `Retry-After` (B7).
- **Aceptación:** `pytest` pasa en local; añadir `pytest` a requirements de desarrollo.

### F8. Auth multiplataforma y service principal

- **Archivos:** `powerbi_mcp_server/auth/token_manager.py`, `powerbi_mcp_server/auth/device_flow.py`.
- **Fix:**
  - Aislar DPAPI tras una interfaz de almacenamiento; si `win32crypt` no está disponible, usar `keyring` como fallback (import perezoso, no a nivel de módulo).
  - Cablear `service_principal_authenticate` (ya existe, ~línea 79 de `device_flow.py`): si están definidas `POWERBI_MCP_TENANT_ID`, `POWERBI_MCP_CLIENT_ID`, `POWERBI_MCP_CLIENT_SECRET`, usar SP en lugar de device flow (necesario para CI/CD futuro).
- **Aceptación:** el paquete importa sin error en un entorno sin pywin32; con las 3 variables de entorno definidas, se autentica como SP sin interacción.

### F9. Robustez menor de BD

- **Archivo:** `powerbi_mcp_server/metadata/database.py`.
- **Fix:** sustituir el patrón `_next_id` (MAX+1, carrera si CLI y servidor corren a la vez) por `CREATE SEQUENCE` de DuckDB. Limpiar el código extraño de `cleanup_orphaned_entries` (~línea 340: `if 'orphaned_ids' in dir()`).
- **Aceptación:** inserciones concurrentes desde dos procesos no colisionan en IDs.

---

## Notas para el implementador

- El servidor es MCP por **stdio**: nunca escribir a stdout desde el paquete `powerbi_mcp_server` (solo logging a archivo, ya configurado en `logging_config.py`).
- Los mensajes de cara al usuario (descripciones de tools, errores) van en **español**; logs internos en inglés (convención actual del código).
- `upsert_item` en `client.py` ya distingue create/update — apoyarse en ese flag para los warnings de primer despliegue.
- La BD de metadatos vive en `~/.powerbi-mcp-deployment/metadata.duckdb` (o `POWERBI_MCP_DB_PATH`). Hay una copia de prueba en `.powerbi-mcp-deployment/metadata.duckdb` dentro del repo.
- Probar cambios con el CLI (`python pbi_cli.py …`) es más rápido que levantar el servidor MCP completo.
