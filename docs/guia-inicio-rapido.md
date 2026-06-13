# Guía de Inicio Rápido — Para usuarios de Power BI sin conocimientos de informática

> Esta guía está pensada para alguien que **sabe usar Power BI** pero **nunca ha usado una terminal, instalado Python, ni configurado nada parecido**. Si sigues los pasos en orden, en unos 10-15 minutos tendrás un asistente de IA capaz de gestionar tus modelos e informes de Power BI hablando en español.

---

## 1. ¿Qué vas a instalar y por qué?

Vas a conectar **Claude Desktop** (un programa de chat con inteligencia artificial) con el **Power BI MCP Deployment Server** (este proyecto). Una vez conectados, podrás escribir cosas como:

> "Descarga el modelo Sales Model del workspace de Producción"
> "Sube el informe Dashboard Ventas al workspace de Test"

y Claude lo hará por ti, sin que tengas que tocar el portal de Power BI ni escribir código.

Para que esto funcione necesitas tres cosas, en este orden:

1. **Claude Desktop** — la aplicación de chat.
2. **`uv`** — un programa pequeño que se encarga de descargar y ejecutar el servidor de Power BI automáticamente. No necesitas saber qué es ni cómo funciona, solo instalarlo una vez.
3. **Un archivo de configuración** — un fichero de texto donde le decimos a Claude Desktop "usa este servidor de Power BI".

---

## 2. Instalar Claude Desktop

Si todavía no lo tienes, descárgalo desde la web oficial de Anthropic e instálalo como cualquier otro programa de Windows (doble clic en el instalador, "Siguiente", "Siguiente", "Finalizar").

Si ya lo tienes instalado, puedes pasar al siguiente paso.

---

## 3. Instalar `uv`

`uv` es la pieza que permite que Claude Desktop ejecute el servidor de Power BI sin que tengas que instalar Python, librerías, ni nada manualmente.

1. Pulsa la tecla de **Windows** y escribe `PowerShell`. Haz clic en **Windows PowerShell** (el icono azul).
2. Se abrirá una ventana negra/azul con texto. No te preocupes, solo vas a copiar y pegar una línea.
3. Copia este comando completo:

   ```powershell
   irm https://astral.sh/uv/install.ps1 | iex
   ```

4. Pégalo en la ventana de PowerShell (clic derecho para pegar) y pulsa **Enter**.
5. Espera unos segundos hasta que termine. Verás un mensaje indicando que `uv` se ha instalado.
6. **Cierra la ventana de PowerShell.**

> Esto solo se hace **una vez** en tu ordenador, no hay que repetirlo cada vez que uses Claude.

---

## 4. Configurar Claude Desktop para usar el servidor de Power BI

Ahora tenemos que editar un archivo de configuración de Claude Desktop. Es un archivo de texto con formato JSON — parece código, pero solo vamos a copiar y pegar un bloque ya preparado.

### 4.1. Abrir el archivo de configuración

1. Abre Claude Desktop.
2. Ve al menú **Archivo → Configuración** (o el icono de ajustes).
3. Busca la sección **Desarrollador** (Developer) y pulsa **Editar configuración** (Edit Config). Esto abrirá la carpeta donde está el archivo `claude_desktop_config.json` en el Explorador de Windows.
4. Abre ese archivo con el **Bloc de notas** (clic derecho sobre el archivo → Abrir con → Bloc de notas).

### 4.2. Pegar la configuración

Si el archivo está vacío o solo tiene `{}`, sustituye todo su contenido por esto:

```json
{
  "mcpServers": {
    "powerbi": {
      "command": "uvx",
      "args": ["powerbi-mcp-deployment"]
    }
  }
}
```

Si el archivo ya tiene otros servidores configurados (verás algo como `"mcpServers": { "otroServidor": { ... } }`), añade el bloque `"powerbi": { ... }` dentro de `"mcpServers"`, separándolo del anterior con una coma. Por ejemplo:

```json
{
  "mcpServers": {
    "otroServidor": {
      "command": "..."
    },
    "powerbi": {
      "command": "uvx",
      "args": ["powerbi-mcp-deployment"]
    }
  }
}
```

> **Importante**: el formato JSON es estricto con las comas y las llaves `{ }`. Si no estás seguro, copia exactamente el primer bloque (el que sustituye todo el archivo) si es la primera vez que configuras un servidor MCP.

### 4.3. Guardar y reiniciar

1. Guarda el archivo (`Ctrl+S`) y cierra el Bloc de notas.
2. **Cierra Claude Desktop por completo** (no basta con cerrar la ventana — búscalo en la bandeja del sistema, junto al reloj, y selecciona "Salir" o "Quit").
3. Vuelve a abrir Claude Desktop.

La primera vez que Claude Desktop arranque con esta configuración, `uv` descargará automáticamente el servidor de Power BI (esto puede tardar entre 30 segundos y 2 minutos, dependiendo de tu conexión). No necesitas hacer nada, solo esperar.

---

## 5. Primer uso: conectar tu cuenta de Power BI

1. En el chat de Claude Desktop, escribe:

   > Lista mis workspaces de Power BI

2. Claude te responderá con un **código** y una dirección web (algo como `https://microsoft.com/devicelogin`).
3. Abre esa dirección en tu navegador, escribe el código que te ha dado Claude, y entra con tu cuenta de Microsoft/Power BI habitual (la misma que usas en `app.powerbi.com`).
4. Vuelve a Claude Desktop. En unos segundos debería mostrarte la lista de tus workspaces.

Este inicio de sesión solo es necesario **una vez**. Claude recordará tu sesión para las siguientes veces (de forma segura, cifrada en tu propio equipo).

---

## 6. Ejemplos de cosas que puedes pedirle

Una vez configurado, puedes hablarle a Claude en español de forma natural:

- "¿Qué workspaces tengo disponibles?"
- "Muéstrame los informes y modelos del workspace 'Ventas DEV'"
- "Descarga el modelo 'Sales Model' a la carpeta C:\Mis Modelos\"
- "Sube el informe que tengo en C:\Informes\Dashboard al workspace 'Ventas TEST' y enlázalo al modelo 'Sales Model TEST'"
- "¿Qué se ha desplegado últimamente en el workspace 'Ventas PROD'?"

Para una explicación más completa de todo lo que puede hacer el servidor (incluyendo configuración de despliegues automáticos DEV → TEST → PROD), consulta el [Manual de Usuario completo](user_manual.md).

---

## 7. Si algo no funciona

| Síntoma | Qué probar |
|---|---|
| Claude dice que no encuentra el servidor "powerbi" | Revisa que el archivo `claude_desktop_config.json` esté bien escrito (sin comas de más o de menos) y reinicia Claude Desktop por completo. |
| Tarda mucho la primera vez | Es normal — `uv` está descargando el servidor. Espera 1-2 minutos. Las siguientes veces será instantáneo. |
| El código de inicio de sesión ha caducado | Vuelve a escribir "Lista mis workspaces de Power BI" para que Claude genere un código nuevo. |
| "Workspace no encontrado" | Comprueba el nombre exacto en `app.powerbi.com` (distingue mayúsculas y minúsculas). |

Para problemas más específicos, consulta la [guía de resolución de problemas](troubleshooting.md).
