# Verificación manual — bugs corregidos en versión 1.1

Guía paso a paso para comprobar cada bug corregido (B1–B11 del `plan version 1.1.md`).

## Preparación (una vez)

1. Abre una terminal en `D:\Python apps\MCP Deploy`.
2. Usa el Python del venv en todos los comandos: `.venv\Scripts\python.exe`.
3. Necesitas dos workspaces de prueba en Power BI/Fabric a los que tengas permiso de escritura. En esta guía se llaman **`WS-Informes`** y **`WS-Modelos`** — sustitúyelos por los tuyos.
4. Necesitas un PBIP descargado con informe + modelo. Si no tienes uno a mano, en el paso B1.1 se descarga.
5. Autentícate una vez:

```bash
.venv\Scripts\python.exe pbi_cli.py auth
```

> Los logs del servidor están en `%USERPROFILE%\.powerbi-mcp-deployment\logs\server.log` — varios pasos piden mirarlos.

---

## B1 — Rebinding de PBIP con informe y modelo en workspaces distintos

**Qué se corrigió:** al subir un informe con rebind ahora se parchea `definition.pbir` (de `byPath` a `byConnection` con el ID del modelo), y si el modelo del rebind no está publicado pero su carpeta `.SemanticModel` está junto a la del informe, se despliega primero automáticamente.

1. Descarga un proyecto completo (informe + modelo) a una carpeta vacía:

```bash
.venv\Scripts\python.exe pbi_cli.py download-model WS-Origen MiModelo D:\PruebaPBIP\
```

```bash
.venv\Scripts\python.exe pbi_cli.py download-report WS-Origen MiInforme D:\PruebaPBIP\
```

2. Comprueba que `D:\PruebaPBIP\MiInforme.Report\definition.pbir` contiene `byPath` (referencia local).
   Tras el paso 4, si vuelves a descargar el informe, `definition.pbir` debe contener
   `"byConnection": {"connectionString": "semanticmodelid=<GUID>"}` — ese es el único
   campo del esquema real (confirmado contra la documentación oficial de Microsoft;
   la primera versión del fix usaba campos adicionales que Fabric rechazaba).
3. Sube **el modelo al workspace de modelos**:

```bash
.venv\Scripts\python.exe pbi_cli.py upload-model WS-Modelos D:\PruebaPBIP\MiModelo.SemanticModel
```

4. Sube **el informe al workspace de informes**, reenlazado al modelo del otro workspace:

```bash
.venv\Scripts\python.exe pbi_cli.py upload-report WS-Informes D:\PruebaPBIP\MiInforme.Report --rebind MiModelo --rebind-workspace WS-Modelos
```

5. **Resultado esperado:** la subida termina sin error (antes fallaba u obligaba a subir todo al mismo workspace). En el portal, abre el informe en `WS-Informes` → debe renderizar datos. En la vista de linaje (Lineage view) de `WS-Informes`, el informe debe apuntar al modelo de `WS-Modelos`.
6. **Orquestación automática (segunda parte del fix):** borra el modelo de `WS-Modelos` en el portal y repite solo el paso 4. Ahora el CLI debe avisar "Modelo 'MiModelo' no publicado aún — desplegando primero..." y desplegar modelo + informe en una sola orden.

---

## B2 — Sin `print()` a stdout en el servidor (protocolo MCP)

**Qué se corrigió:** el aviso de rate-limit (429) escribía a stdout, corrompiendo el JSON-RPC del servidor stdio.

1. Comprobación estática (suficiente):

```bash
grep -rn "print(" powerbi_mcp_server/
```

2. **Resultado esperado:** ninguna coincidencia (los mensajes van solo al log).
3. Comprobación funcional opcional: usa el servidor desde Claude Desktop un rato con operaciones masivas (`download_workspace` de un workspace grande, que provoca 429). El cliente MCP no debe desconectarse ni mostrar errores de parseo; el aviso de rate-limit aparece en `server.log`.

---

## B3 — La sesión sobrevive a la caducidad del token (caché MSAL persistente)

**Qué se corrigió:** el refresh token de MSAL ahora se guarda cifrado con DPAPI en `%USERPROFILE%\.powerbi-mcp-deployment\cache\msal_cache.encrypted`, así la renovación silenciosa funciona entre procesos y ya no hay que repetir el device flow cada hora.

1. Autentícate: `.venv\Scripts\python.exe pbi_cli.py auth` (completa el device flow si lo pide).
2. Comprueba que existe el archivo nuevo: `%USERPROFILE%\.powerbi-mcp-deployment\cache\msal_cache.encrypted`.
3. Fuerza la caducidad del token de acceso borrando solo el token DPAPI (NO borres `msal_cache.encrypted`):

```bash
del "%USERPROFILE%\.powerbi-mcp-deployment\cache\tokens.encrypted"
```

4. En una terminal nueva, lanza cualquier comando:

```bash
.venv\Scripts\python.exe pbi_cli.py workspaces
```

5. **Resultado esperado:** el CLI muestra "Renovado silenciosamente: <tu usuario>" y lista los workspaces **sin pedirte código de device flow**. Antes del fix, aquí siempre saltaba el device flow.
6. Prueba real de larga duración: espera >1 hora tras autenticar (token caducado) y repite el paso 4 — mismo resultado, sin device flow.

---

## B4 — El servidor no da 401 tras renovarse el token

**Qué se corrigió:** el cliente HTTP ya no congela el token en el arranque; construye los headers en cada petición con el token vigente.

1. Esta comprobación es sobre el **servidor MCP de larga vida** (Claude Desktop). Arranca Claude Desktop con el servidor configurado y haz una operación cualquiera (listar workspaces).
2. Deja la sesión abierta **más de 1 hora** (que caduque el token inicial).
3. Pide otra operación (p. ej. "lista los modelos de WS-Modelos").
4. **Resultado esperado:** funciona sin reiniciar Claude Desktop. Antes del fix, tras la caducidad todas las llamadas devolvían error 401 hasta reiniciar. En `server.log` no debe aparecer ningún 401 seguido de fallo.

---

## B5 — La descarga PBIX de modelos ya no se ofrece (endpoint inexistente)

**Qué se corrigió:** se eliminó la ruta de descarga PBIX de modelos (la API no tiene export de datasets); los modelos se descargan siempre como PBIP.

1. Mira la ayuda del comando:

```bash
.venv\Scripts\python.exe pbi_cli.py download-model --help
```

2. **Resultado esperado:** ya no existe la opción `--format` (antes ofrecía `pbix|pbip`).
3. Desde Claude Desktop, pide: *"descarga el modelo X del workspace Y en formato pbix"*. **Resultado esperado:** el tool responde con un error claro en español explicando que PBIX no está soportado y que se usa `pbip` — no un error HTTP críptico.
4. La descarga normal sigue funcionando (paso B1.1).

---

## B6 — Rebind ambiguo pide desambiguación en vez de adivinar

**Qué se corrigió:** si el nombre del modelo para rebind coincide con varios modelos (o solo parcialmente), el tool devuelve la lista de candidatos en vez de coger el primero en silencio.

1. En `WS-Modelos`, ten dos modelos cuyos nombres compartan prefijo, p. ej. `Ventas` y `Ventas Detalle` (puedes subir el mismo PBIP dos veces con `--name` distinto):

```bash
.venv\Scripts\python.exe pbi_cli.py upload-model WS-Modelos D:\PruebaPBIP\MiModelo.SemanticModel --name "Ventas"
```

```bash
.venv\Scripts\python.exe pbi_cli.py upload-model WS-Modelos D:\PruebaPBIP\MiModelo.SemanticModel --name "Ventas Detalle"
```

2. Desde Claude Desktop, pide: *"reenlaza el informe MiInforme de WS-Informes al modelo 'Venta' de WS-Modelos"* (nombre parcial, sin match exacto).
3. **Resultado esperado:** el tool NO ejecuta el rebind; responde con `needs_disambiguation: true` y la lista de candidatos (`Ventas`, `Ventas Detalle`) con sus IDs, y Claude te pregunta cuál quieres.
4. Repite con el nombre exacto `Ventas`. **Resultado esperado:** el rebind se ejecuta.

---

## B7 — Retries y LRO robustos en operaciones Fabric

**Qué se corrigió:** `getDefinition`, `createItem` y `updateDefinition` ahora reintentan ante 429; el polling de operaciones largas respeta `Retry-After` y su timeout subió de 120 s a 600 s.

1. Comprobación funcional: descarga un workspace grande completo (muchos artefactos seguidos provocan 429):

```bash
.venv\Scripts\python.exe pbi_cli.py download-workspace WS-Grande D:\BackupWS\
```

2. **Resultado esperado:** la descarga completa termina sin abortar. Si hubo throttling, en `server.log` (o en la salida) aparecen líneas "Rate limit hit (429), retrying in Xs" y la operación continúa tras el reintento.
3. Sube un modelo grande (>120 s de proceso en Fabric). **Resultado esperado:** ya no falla con "LRO operation timed out after 120s".

---

## B8 — No se pueden invocar métodos internos como tools

**Qué se corrigió:** `call_tool` valida el nombre contra la lista de tools registrados antes de despachar.

1. Esta comprobación necesita enviar una llamada MCP cruda. Opción sencilla con el inspector oficial de MCP (necesita Node):

```bash
npx @modelcontextprotocol/inspector .venv\Scripts\python.exe scripts\run_server.py
```

2. En la UI del inspector, pestaña **Tools**: verifica que `_ensure_authenticated` o `_resolve_rebind_model` **no aparecen** en la lista.
3. Con la opción "call tool" manual del inspector, invoca un tool con nombre `_ensure_authenticated`.
4. **Resultado esperado:** respuesta `{"success": false, "error": "Unknown tool: _ensure_authenticated"}` — no se ejecuta nada.

---

## B9 — Schemas alineados con el comportamiento real

**Qué se corrigió:** `download_report` ya no ofrece el formato `json` (nunca estuvo implementado) y las descripciones ya no mencionan "legacy JSON".

1. Con el inspector del paso B8 (o desde Claude Desktop preguntando "¿qué opciones tiene el tool download_report?"):
2. **Resultado esperado:** `download_report` no tiene propiedad `format`; `download_semantic_model` solo admite `pbip`; la descripción de `upload_report` menciona el parcheo de `definition.pbir` y la desambiguación, y no menciona JSON legacy.

---

## B10 — Las descargas PBIP/PBIR no machacan la versión anterior (fuera de Git)

**Qué se corrigió:** si la carpeta destino ya contiene una descarga previa y NO está dentro de un repo Git, la anterior se conserva renombrada con timestamp.

1. Usa una carpeta **sin Git**, p. ej. `D:\PruebaVersionado\`:

```bash
.venv\Scripts\python.exe pbi_cli.py download-model WS-Modelos MiModelo D:\PruebaVersionado\
```

2. Repite exactamente el mismo comando.
3. **Resultado esperado:** el CLI indica "Versión anterior conservada con sufijo: <timestamp>" y en la carpeta hay dos: `MiModelo.SemanticModel` (nueva) y `MiModelo_20260802_HHMMSS.SemanticModel` (anterior). Lo mismo aplica a informes con `download-report` (`MiInforme_<ts>.Report`).
4. Contraprueba Git: crea una carpeta con repo (`git init D:\PruebaGit`), descarga dos veces ahí. **Resultado esperado:** NO se crea copia con timestamp (el historial lo lleva Git).
5. El historial registra el sufijo:

```bash
.venv\Scripts\python.exe pbi_cli.py history MiModelo --type SemanticModel
```

---

## B11 — Workspaces con apóstrofe en el nombre

**Qué se corrigió:** el filtro OData escapa las comillas simples.

1. Si tienes (o puedes crear) un workspace con apóstrofe, p. ej. `Miguel's Test`:

```bash
.venv\Scripts\python.exe pbi_cli.py contents "Miguel's Test"
```

2. **Resultado esperado:** encuentra el workspace y lista su contenido. Antes del fix, la petición fallaba con error 400 de OData.
3. Si no puedes crear el workspace, basta la comprobación estática: en `powerbi_mcp_server/api/client.py`, `get_workspace_by_name` contiene `workspace_name.replace("'", "''")`.

---

## Extra — corrección incluida de propina

Al revisar se detectó que el historial (`downloads`/`uploads`) nunca guardaba el email del usuario (se leía la clave `email` cuando la real es `user_email`). Verificación: tras cualquier subida, `pbi_cli.py deployments WS-Informes` / consultar la tabla `uploads` debe mostrar tu email en `user_email` en las filas nuevas.

## Checklist final

| Bug | Comprobado | Notas |
|-----|-----------|-------|
| B1 rebinding cross-workspace | ☐ | |
| B2 sin print a stdout | ☐ | |
| B3 sesión persistente | ☐ | |
| B4 sin 401 tras 1h | ☐ | |
| B5 PBIX de modelos retirado | ☐ | |
| B6 desambiguación rebind | ☐ | |
| B7 retries/LRO | ☐ | |
| B8 tools internas bloqueadas | ☐ | |
| B9 schemas coherentes | ☐ | |
| B10 versionado carpetas | ☐ | |
| B11 apóstrofes | ☐ | |
