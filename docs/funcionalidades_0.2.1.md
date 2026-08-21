# Funcionalidades candidatas — v0.2.1

## 1. Trazabilidad de llamadas ("decision path" / audit trail)

### Por qué

Nos proponen una funcionalidad de explicabilidad: poder abrir cualquier respuesta del LLM
y ver su "ruta de decisión" — qué se consultó, qué transformaciones se ejecutaron, qué
permisos aplicaron y de qué datos concretos salió el resultado — con un botón tipo
"enséñame cómo llegaste aquí" para quien audita. La idea original habla de modelos
semánticos consultados; en `powerbi-mcp-deployment` no hay eso, pero sí un equivalente
directo: cada respuesta del LLM se traduce en una o varias **tool calls MCP**, y cada tool
call dispara **llamadas REST** contra Fabric/Power BI con un token concreto. Formalizar
ese rastro es justo lo que el artículo `articulo_version_0.2_.md` narra a mano para una
sesión concreta ("Debajo: `project-create Ventas`...") — esta funcionalidad lo automatiza.

Acerca la herramienta de "demo potente" a "infraestructura gobernable": el analista sigue
preguntando en lenguaje natural, pero quien audita puede reconstruir, para cualquier
respuesta, la secuencia exacta de llamadas y con qué identidad se hicieron.

### Dónde vive: MCP server, no Claude ni el cliente

Claude/el cliente ya exponen gratis qué tool llamaron y con qué argumentos — es parte de
la propia conversación, no hay que construir nada para eso. Lo que **no** ve nadie hoy es
qué pasa *dentro* de la tool call: las llamadas REST concretas, con qué credencial, y qué
devolvió Fabric. Eso solo lo tiene `powerbi_mcp_server`, así que el rastro tiene que
generarse y guardarse ahí.

Estado actual (verificado en el repo): el logging (`logging_config.py` →
`~/.powerbi-mcp-deployment/logs/server.log`) es texto libre, no ligado a una llamada
concreta. La única auditoría estructurada que existe es la tabla `promotion_events`
(`metadata/database.py`), acotada al subsistema de proyectos/promoción — no cubre el
resto de tools ni las llamadas REST individuales.

### Diseño técnico

**Parte A — log de inicio/fin de cada tool call.**
Punto de intercepción único: `powerbi_mcp_server/server.py`, función `call_tool()`
(líneas 72-104) — es donde se despachan las ~30 tools vía
`getattr(self.tool_handlers, name)`, así que no hace falta tocar cada handler.

- `call_id` (uuid4) generado al entrar.
- Log de inicio: `call_id`, `tool`, `arguments` (redactados), `started_at`.
- Log de fin: `call_id`, `completed_at`, `duration_ms`, `status`, `output_summary`.
  - `status = "fail"` si hay excepción o `result.get("success") is False`.
  - `status = "warning"` si `success` es `True` pero el dict trae una clave
    `warning`/`warnings` no vacía (convención nueva y opcional: los handlers que quieran
    señalizar un warning —p. ej. drift confirmado, fallback usado— añaden esa clave; no
    hace falta tocar los 30 handlers existentes de golpe).
  - `status = "ok"` en el resto de casos.
- Redacción: nunca loguear `client_secret`, tokens, cabecera `Authorization`; truncar
  payloads grandes (p. ej. contenido base64 de PBIP) en el resumen.

Persistencia — nueva tabla en `metadata/database.py`, mismo patrón que `promotion_events`
(bump de `SCHEMA_VERSION` de 5 a 6):

```sql
CREATE TABLE IF NOT EXISTS tool_call_log (
    call_id VARCHAR PRIMARY KEY,
    tool_name VARCHAR NOT NULL,
    arguments_json VARCHAR,
    status VARCHAR NOT NULL,          -- ok | warning | fail
    output_summary VARCHAR,
    error_message VARCHAR,
    principal VARCHAR,                -- ver punto 2: user_email o "sp:<client_id>"
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    duration_ms INTEGER
)
```

**Parte B — rastro de llamadas REST + resource "enséñame cómo llegaste aquí".**
Para el "de qué datos concretos salió el resultado" hace falta un nivel más: qué llamadas
REST disparó cada tool call.

- Punto único de salida hacia Fabric: `powerbi_mcp_server/api/http_utils.py`,
  `request_with_retry` (todo pasa por aquí vía `PowerBIClient`).
- Propagar el `call_id` activo con un `contextvars.ContextVar`, desde `server.py` hasta
  `request_with_retry`, sin cambiar la firma de las ~40 funciones intermedias de
  `client.py`.
- Nueva tabla `api_call_log` (mismo patrón): `id, call_id (FK), method, url, status_code,
  attempt, occurred_at`. Una fila por request real (incluidos reintentos 429); nunca el
  body completo, solo método/URL/status.

Exposición — reutilizar el patrón de resources ya existente (`deployments://recent`,
`deployments://<workspace>` en `server.py:145-164` y `resources.py`), no crear un
mecanismo nuevo:

- `audit://recent` — últimas N tool calls (id, tool, status, principal, timestamps).
- `audit://<call_id>` — detalle: argumentos redactados, resultado, y las llamadas REST
  que disparó con su status.
- Dos métodos nuevos en `resources.py` (`get_recent_audit_events`, `get_audit_detail`)
  reutilizando `MetadataManager`/`repository.py`.

Este es "el botón": cuando alguien pida "enséñame cómo llegaste aquí", Claude ya sabe qué
tool llamó por el propio hilo de conversación, y puede leer `audit://<call_id>` para
mostrar el detalle de bajo nivel — sin que el cliente ni Claude tengan que construir nada
propio.

---

## 2. Autenticación desatendida (service principal + sesión `az login`)

> **Estado:** la reutilización de sesión `az login` (punto 2 de este apartado) está
> implementada — ver `powerbi_mcp_server/auth/device_flow.py::azure_cli_authenticate`. Se
> cableó tanto en `pbi_cli.py::get_token()` como en
> `authenticator.py::ensure_authenticated()`/`start_device_flow()`, no solo en el CLI como
> sugería el título original: el servidor MCP lanzado por Claude Desktop o VS Code/Copilot
> corre como proceso hijo bajo la misma sesión interactiva de Windows, así que no hay ninguna
> razón técnica para restringirlo al CLI. La autenticación por Service Principal (punto 1)
> sigue pendiente.

### Por qué

Hoy la única vía de autenticación operativa es Device Flow interactivo — requiere que un
humano abra el navegador y complete el login. Vale para uso manual desde terminal o chat,
pero bloquea cualquier automatización sin supervisión (pipeline programado, tarea
en background, CI/CD). El propio artículo de la v0.2.0 ya lo señala como limitación
conocida: *"`auth` hoy es device flow interactivo... para meter esto en GitHub Actions o
Azure DevOps falta añadir login con service principal al CLI — no está hecho todavía"*.
Y ya estaba anotado como tarea pendiente **F8** en `plan version 1.1.md` (línea 188):
*"Cablear `service_principal_authenticate` (ya existe, ~línea 79 de `device_flow.py`)"*.

### Diseño técnico

`powerbi_mcp_server/auth/device_flow.py:114` ya tiene
`service_principal_authenticate(tenant_id, client_id, client_secret)` implementada y
funcional — simplemente no la llama nadie todavía. El trabajo es cablearla, más añadir un
segundo camino de conveniencia para reusar una sesión `az login` ya existente.

1. **Service principal (ruta principal, para desatendido real: CI/CD, tareas
   programadas).**
   - En `PowerBIAuthenticator.ensure_authenticated()`
     (`auth/authenticator.py`) y en `get_token()` (`pbi_cli.py:171`), comprobar
     **antes que nada** las variables de entorno `POWERBI_MCP_TENANT_ID` /
     `POWERBI_MCP_CLIENT_ID` / `POWERBI_MCP_CLIENT_SECRET` (nombres ya propuestos en
     `plan version 1.1.md` F8, para no chocar con otras `AZURE_*` que pueda tener el
     proceso). Si las tres están definidas, usar `service_principal_authenticate(...)`
     directamente — sin caché DPAPI, sin device flow, sin intervención humana.
   - Guardar el resultado vía `state_manager.update_state()` como hoy, añadiendo
     `auth_method: "service_principal"` y `principal: f"sp:{client_id}"` — este campo
     alimenta la columna `principal` de `tool_call_log` (funcionalidad 1) y responde a
     "qué permisos aplicaron": el rol efectivo es el que tenga ese SP en el workspace de
     Fabric (mismo principio que ya aplica hoy con usuarios: *"si no tengo contributor en
     el workspace, el LLM tampoco lo tiene"*).
   - Precedencia: si las 3 variables SP están presentes, se usan siempre — no se mezcla
     con una sesión de usuario cacheada, para evitar el caso confuso de "¿actúo como yo o
     como el SP?".

2. **Sesión `az login` existente (ruta secundaria, conveniencia — implementada tanto en
   CLI como en el servidor MCP).**
   - Se añadió `AzureCliCredential` (de `azure.identity`, ya era dependencia del proyecto —
     ya se usaba `ClientSecretCredential` en el mismo fichero) como intento adicional en
     `azure_cli_authenticate()`: `AzureCliCredential().get_token(*POWERBI_SCOPE)`.
     Falla rápido y en silencio (`CredentialUnavailableError`) si no hay `az login` activo,
     así que es seguro probarlo como un escalón más antes de caer al device flow; cualquier
     otro error se propaga en vez de enmascararse.
   - Orden final de intentos: (1) variables SP, cuando esa pieza exista → (2) caché
     DPAPI/MSAL silencioso existente → (3) `az login` vía `AzureCliCredential` → (4) device
     flow interactivo (solo en el CLI; en el servidor MCP, en su lugar se lanza
     `AuthenticationRequired` como hoy). Los pasos 2-3 son idénticos en ambos contextos —
     solo el paso 4 distingue CLI de servidor MCP.

3. **Criterio de aceptación.** Con las 3 variables `POWERBI_MCP_*` definidas (cuando esa
   pieza exista), tanto `python pbi_cli.py <comando>` como el servidor MCP se autenticarán
   sin ninguna interacción. Con una sesión `az login` activa (y sin variables SP), tanto
   `pbi_cli.py` como el servidor MCP evitan el device flow — confirmado con
   `tests/test_device_flow_azure_cli.py`. Sin ninguna de las dos, el comportamiento actual
   (device flow) no cambia.

---

## Relación entre ambas funcionalidades

El campo `principal` que registra la funcionalidad de autenticación desatendida (usuario
humano vía device flow, o `sp:<client_id>` vía service principal) es exactamente el dato
que la funcionalidad de trazabilidad necesita para responder "qué permisos aplicaron" en
cada entrada de `tool_call_log`. Tiene sentido implementarlas en ese orden: primero el
cableado de auth (más pequeño, ya semi-hecho), después el logging estructurado que lo
consume.

## Fuera de alcance de este documento

- Migrar el logging existente de `powerbi_object_manager.py`/`pbi.py` (código legacy,
  cubierto por F6 de `plan version 1.1.md`).
- Autenticación con certificado (alternativa a client secret) para el service principal.
- UI/dashboard sobre `audit://recent` — de momento es un resource MCP de solo lectura,
  consumible desde el chat.
