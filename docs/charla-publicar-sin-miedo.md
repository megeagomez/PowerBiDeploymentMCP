# Publicar sin miedo — Guion de charla (50 min, con demos)

> Cómo funciona el Power BI MCP Deployment Server, contado tres veces — una por cada tipo de
> persona que lo va a usar: quien no programa, quien programa pero no tiene Azure DevOps, y
> quien ya vive en Azure DevOps o GitHub Actions.

**Duración**: 50 min (incluye 4 demos en vivo)
**Formato**: diapositivas + terminal + Claude Desktop
**Requiere**: proyectos `.pbip` de prueba — ver "Prepara antes" de cada demo

**Las tres audiencias**

1. **Sin código** — usuario de Power BI que quiere profesionalizar su publicación sin aprender a programar.
2. **Sin Azure DevOps** — ingeniero o dev que sabe programar pero no tiene (o no puede montar) una plataforma DevOps.
3. **Ya en CI/CD** — equipo que ya usa Azure DevOps o GitHub Actions y quiere saber si esto le sirve para algo.

---

## 0. Apertura (00:00–02:00 · 2 min)

**En la diapositiva**
- Título: *Publicar sin miedo* — un MCP para desplegar Power BI / Fabric.
- Subtítulo: de "Publicar" en Desktop a un ciclo de vida controlado, sin infraestructura previa.

**Qué dices**
Arranca con una pregunta a la sala: "¿cuántos habéis sobrescrito sin querer un informe de
producción, o no sabéis qué versión hay publicada ahora mismo?" Cuenta en dos frases que esto
nació de automatizar tu propio trabajo con Fabric y acabó siendo un servidor MCP que cualquier
asistente de IA puede usar. Anuncia la estructura: "Hoy no hay una sola audiencia — hay tres, y
cada una se lleva algo distinto. Vamos a verlo con demos reales, no solo diapositivas."

---

## 1. El problema y el panorama (02:00–07:00 · 5 min)

**En la diapositiva — el ciclo habitual**
- Diseñas o modificas en Power BI Desktop.
- Publicas a mano ("Reemplazar") y confías en que no rompe nada.
- ¿Qué versión hay en Producción ahora mismo? ¿Cuándo se subió? ¿Se puede rastrear?

**En la diapositiva — lo que ya ofrece Microsoft**

| Solución | Qué exige |
|---|---|
| Deployment Pipelines (Fabric) | Licencia Fabric / capacidad Premium |
| fabric-cicd (oficial, feb. 2026) | Git + Azure DevOps o GitHub Actions ya montados |
| pyfabricops / REST directa | Saber Python y la API |

**Qué dices**
Las tres opciones son buenas — pero cada una asume algo que mucha gente todavía no tiene:
licencia Premium, infraestructura DevOps ya construida, o saber programar contra una API REST.
Este MCP vive en el hueco entre "Publicar a mano" y "pipeline corporativo completo". Y en una
frase: un MCP es un protocolo abierto que deja que un asistente de IA ejecute funciones reales y
deterministas — no inventa nada, llama a la misma API REST que llamaría un script. Si no tienes
permisos de colaborador en el workspace, la IA tampoco los tiene.

Transición: "Vamos a verlo desde el punto de vista de cada audiencia, empezando por la que menos
código quiere ver."

---

## Acto 1 — Audiencia 1: Power BI sin código (07:00–23:00 · 16 min)

### Contexto (07:00–11:00 · 4 min)

**En la diapositiva**
- **Perfil:** analista o power user; domina Power BI Desktop, no quiere ni necesita programar.
- **Dolor:** publicar a mano sin saber si "Reemplazar" va a romper algo, sin histórico de qué
  se subió y cuándo.
- **Qué le da esto:** hablar con Claude Desktop o Copilot en español natural — el servidor
  traduce eso a llamadas reales contra la API de Fabric / Power BI.

**Qué dices**
Enseña que instalar el servidor es una entrada en un archivo de configuración (ya hecha antes
de la charla), y que la primera vez que preguntas algo, pide autenticarse con la cuenta
corporativa igual que Power BI Desktop — nada nuevo que aprender.

### Demo 1 — Publicar un proyecto .pbip completo, hablando (11:00–16:00 · 5 min)

**Prepara antes**
- Workspace de prueba, p. ej. `Ventas Demo`, con un modelo `Ventas` y un informe `Ventas` ya
  publicados y con datos cargados (visuales con cifras reales, no vacíos).
- En local, el proyecto completo: `D:\Demo\Ventas\Ventas.SemanticModel\` +
  `D:\Demo\Ventas\Ventas.Report\` + `Ventas.pbip` (ábrelo en Desktop antes de empezar).
- Por si el tiempo aprieta: una segunda copia de esa misma carpeta con el cambio ya hecho (una
  medida nueva "Margen %"), para sustituir en vez de editar en directo.

**Transcript**

| Rol | Contenido |
|---|---|
| Pantalla | Muestra el informe ya publicado en el portal, con sus cifras — esto es lo que hay "antes". |
| Prompt | "Lista los workspaces que tengan 'Demo' en el nombre" |
| Tool MCP | `list_workspaces` |
| Prompt | "¿Qué hay publicado en el workspace Ventas Demo?" |
| Tool MCP | `get_workspace_contents` → aparecen el modelo Ventas y el informe Ventas |
| Pantalla | En Power BI Desktop: abre `Ventas.pbip`, añade la medida "Margen %", guarda. (O sustituye por la carpeta "después".) |
| Prompt | "Sube el proyecto que tengo en D:\Demo\Ventas al workspace Ventas Demo" |
| Tool MCP | `upload_semantic_model` (existe → `"operation": "updated"`) y luego `upload_report` (existe → `"updated"`) |
| Pantalla | Antes de refrescar el portal, pregunta a la sala: "¿alguien cree que esto acaba de borrar los datos que ya había cargados?" |
| Resultado | Refresca el informe: la medida nueva aparece. Las cifras y filas que ya estaban cargadas siguen intactas — no hizo falta recargar nada para no perder histórico. |

### ¿Qué acaba de pasar por debajo? (16:00–19:00 · 3 min)

**En la diapositiva**
Claude → `upload_semantic_model` → API de Fabric `POST /items/{id}/updateDefinition` →
sustituye la **definición** (tablas, medidas, relaciones, TMDL) → no dispara un refresh, no
borra datos.

> **Confirmación técnica — sí, se confirma**
>
> La ruta PBIP (`upload_semantic_model` sobre un proyecto que ya existe) llama a
> `updateDefinition`, que sustituye la **definición** del modelo — tablas, columnas, medidas,
> relaciones — pero no ejecuta ninguna carga ni borrado de datos. Lo que ya está en caché (modo
> Import) sigue tal cual quedó en el último refresh; `updateDefinition` no dispara un refresh
> automático.
>
> Si quitas una columna o tabla de la definición, esa parte deja de estar accesible en el
> siguiente refresh — pero la llamada en sí misma no toca ni una fila. En Direct Lake el matiz
> es aún más simple: el modelo son punteros a tablas del lakehouse, así que los datos ni
> siquiera viven dentro del modelo.
>
> **Matiz importante:** esto aplica a la ruta PBIP/TMDL. La ruta PBIX (`import_pbix`, la API
> clásica de importación de Power BI) es un mecanismo distinto: sube el paquete binario
> completo y, si el nombre ya existe, por defecto Power BI crea un dataset nuevo en paralelo en
> vez de sobrescribir el existente.

**Qué dices — pbix vs. pbip, para dejarlo zanjado**
**Descarga:** solo PBIP para modelos — la API de Power BI no tiene endpoint de exportación de
dataset a `.pbix`; el export a binario es solo a nivel de informe. **Subida:** sí, `.pbix` está
soportado para modelos (junto con `.pbip`). **Informes:** solo PBIR (formato moderno) o JSON
legacy — un informe nunca se sube como `.pbix` suelto, ese formato siempre va ligado a un
modelo.

### Demo 2 — Subir modelo semántico e informe por separado (19:00–23:00 · 4 min)

**Prepara antes**
- Modelo ya publicado en un workspace `Test`, llamado `ModeloVentas`.
- En local, tres piezas sueltas (sin sus hermanos): `D:\Demo\ModeloVentas.SemanticModel\`,
  `D:\Demo\ModeloVentas.pbix`, y `D:\Demo\DashboardVentas.Report\`.

**Transcript**

| Rol | Contenido |
|---|---|
| Prompt | "Sube el modelo semántico que tengo en D:\Demo\ModeloVentas.SemanticModel al workspace Test" |
| Tool MCP | `upload_semantic_model` (formato pbip) |
| Prompt | "Ahora sube D:\Demo\ModeloVentas.pbix al mismo workspace como 'ModeloVentas Pbix'" |
| Tool MCP | `upload_semantic_model` detecta la extensión `.pbix` → usa `import_pbix` por debajo |
| Pantalla | Di en voz alta: mismo tool MCP, dos caminos de API distintos por debajo, según el formato del archivo. |
| Prompt | "Sube el informe que tengo en D:\Demo\DashboardVentas.Report al workspace Test y enlázalo al modelo ModeloVentas" |
| Tool MCP | `upload_report` con `rebind_to_model="ModeloVentas"` |
| Resultado | El informe se publica sin haber subido nunca su `.SemanticModel` hermano, y queda apuntando al modelo correcto — el reenlace parchea `definition.pbir` automáticamente. |

**Cierre del acto**
Con esto, cualquiera que sepa usar Power BI Desktop ya tiene publicación versionada, sin
escribir una línea de código.

---

## Acto 2 — Audiencia 2: Sin Azure DevOps (23:00–36:00 · 13 min)

### Contexto (23:00–26:00 · 3 min)

**En la diapositiva**
- **Perfil:** 2-10 devs/analistas técnicos, ya tienen DEV/TEST/PROD, saben lo que es Git — pero
  no tienen (o no les dejan montar) pipelines de Azure DevOps ni GitHub Actions.
- **Dolor:** promocionar entre entornos a mano es propenso a error — reenlazar al modelo
  equivocado, no saber si alguien tocó Producción por su cuenta.
- **Qué le da esto:** el mismo servidor trae un CLI real (`pbi_cli.py`) — sin IA de por medio si
  no la quieren — con entornos encadenados, proyectos, y detección de divergencia (drift) antes
  de sobrescribir nada.

**Qué dices**
Aquí ya no hablamos en lenguaje natural, hablamos en comandos — y cada comando tiene su tool MCP
equivalente exacto, así que el mismo flujo funciona desde terminal o desde el chat, según quién
lo use ese día.

### Demo 3 — Entornos, proyectos y detección de drift (26:00–36:00 · 10 min)

La demo estrella.

**Prepara antes**
- Tres workspaces reales: `WS Dev`, `WS Integración`, `WS Prod` (o crea los entornos en vivo si
  sobra tiempo).
- Proyecto local `D:\Proyectos\Ventas\` con subcarpetas `Modelos\ModeloVentas.SemanticModel` e
  `Informes\DashboardVentas.Report` — para poder enseñar `--respect-local-structure`.

**Transcript**

```
pbi_cli.py env-create Desarrollo "WS Dev" --stage-order 1
pbi_cli.py env-create Integración "WS Integración" --stage-order 2
pbi_cli.py env-create Producción "WS Prod" --stage-order 3
```
> Nota: el orden (`stage_order`) es lo único que importa para la cadena de promoción — el
> nombre del entorno es libre.

```
pbi_cli.py project-create Ventas
pbi_cli.py project-add-artifact Ventas model ModeloVentas --folder "Ventas/Modelos"
pbi_cli.py project-add-artifact Ventas report DashboardVentas --rebind ModeloVentas --folder "Ventas/Informes"
```

```
pbi_cli.py deploy Ventas Desarrollo D:\Proyectos\Ventas --respect-local-structure
```
> Nota: primer despliegue real — replica la estructura de carpetas local dentro del workspace,
> sin configurar cada carpeta a mano.

```
pbi_cli.py promote Ventas Integración
```
> Nota: esto es "promote", no "deploy": mueve en memoria lo que ya está en Desarrollo hacia
> Integración — no vuelve a tocar el disco.

```
pbi_cli.py deploy Ventas Producción D:\Proyectos\Ventas
```
> Nota: simula una urgencia — un hotfix que se salta la cadena y publica directo en Producción.

```
pbi_cli.py promote Ventas Producción
```
Resultado:
```
⚠ Divergencia detectada respecto al entorno origen (Integración):
    [SemanticModel] ModeloVentas:
      - el último cambio en este entorno fue un 'deploy' directo, no una promoción
  ¿Confirmas la sobrescritura? [y/N]
```
> Nota: este es el momento clave — compara el hash de lo que hay en Producción contra lo último
> promocionado desde Integración, ve que no coincide, y PARA en vez de sobrescribir sin avisar.

```
pbi_cli.py promote Ventas Producción --yes
pbi_cli.py project-tree Ventas
```
Resultado: árbol ASCII final — entornos, carpetas, artefactos, workspace resuelto y fecha del
último despliegue de cada uno.

**Cierre del acto**
Nada de esto necesita YAML, ni un agente de build, ni una licencia Premium. Es una base de datos
local (DuckDB) más disciplina de nombres — pero la disciplina te la impone la propia
herramienta, no la memoria de cada uno.

---

## Acto 3 — Audiencia 3: Ya en Azure DevOps / GitHub Actions (36:00–45:00 · 9 min)

### Contexto (36:00–40:00 · 4 min)

**En la diapositiva — honestidad por delante**
- Esta audiencia **ya tiene** lo bueno: pipelines reales, historial en Git, aprobaciones. Este
  MCP no compite con eso.
- **Dónde sí aporta hoy:** iteración local rápida antes de comitear, hotfixes de emergencia con
  auditoría propia que no ensucia el pipeline, backup/exploración de workspaces sin escribir un
  script REST desde cero, y una vía para que gente de negocio opere dentro de la misma
  disciplina de entornos sin tocar el pipeline de ingeniería.

> **Estado actual — sé transparente aquí**
>
> Hoy la autenticación es Device Flow interactivo: un humano tiene que abrir el navegador una
> vez. Perfecto para uso manual desde terminal o chat, pero bloquea meter esto sin supervisión
> dentro de un pipeline de GitHub Actions o Azure DevOps.
>
> La función de login por Service Principal ya existe en el código
> (`service_principal_authenticate`) pero todavía no está conectada — es la primera pieza del
> roadmap 0.2.1. Hasta que aterrice, este servidor es una herramienta de operador humano, no un
> paso de pipeline desatendido.

**En la diapositiva — comparativa rápida**

| Criterio | Este MCP | fabric-cicd | Deployment Pipelines |
|---|---|---|---|
| Conocimientos | Lenguaje natural + IA | Python + Git + CI/CD | Ninguno (UI) |
| Infraestructura | Ninguna (local) | Git + ADO / GH Actions | Portal Fabric |
| Licencia | Pro estándar | Pro estándar | Fabric / Premium |
| Ejecución desatendida | Roadmap 0.2.1 | Sí | Sí |

### Demo 4 — Auditoría, trazabilidad y backup (40:00–45:00 · 5 min)

**Prepara antes**
- Reutiliza lo desplegado en la Demo 3 (workspace `WS Prod` con historial ya generado).
- Carpeta de destino vacía para el backup, p. ej. `D:\Backups\`.

**Transcript**

| Rol | Contenido |
|---|---|
| Prompt | "Muéstrame el historial de despliegues del workspace WS Prod" |
| Tool MCP | `query_deployments` → qué se subió, cuándo, con qué ID de asset |
| Prompt | "¿Cuándo se descargó por última vez el modelo ModeloVentas y a qué ruta local?" |
| Tool MCP | `query_version_history` |
| Prompt | "Haz una copia de seguridad completa del workspace WS Prod en D:\Backups\" |
| Tool MCP | `download_workspace` → todos los modelos e informes del workspace, en pbip/pbir, a disco |
| Resultado | Reaparece el árbol de despliegue (`project-tree`) de la Demo 3: una vista de estado que un ingeniero de plataforma podría enseñarle a auditoría sin dar acceso al portal. |

**Cierre del acto**
Si ya tenéis un pipeline real, usad el pipeline. Esto es la navaja suiza para todo lo que pasa
alrededor del pipeline: el día a día de quien no está commiteando YAML.

---

## Cierre (45:00–50:00 · 5 min)

**En la diapositiva — una frase por audiencia**
1. **Audiencia 1:** de "publicar y rezar" a publicar con confianza, en español, sin código.
2. **Audiencia 2:** entornos, proyectos y protección contra sobrescrituras accidentales, sin
   montar infraestructura DevOps.
3. **Audiencia 3:** una capa de auditoría y operación manual que convive con vuestro pipeline —
   y que en 0.2.1 empieza a poder correr desatendida.

**En la diapositiva — roadmap corto**
- Autenticación por Service Principal → habilita CI/CD real (GitHub Actions, Azure DevOps).
- Reutilizar sesión `az login` existente, como atajo de conveniencia.
- Hoy solo Windows (el cifrado de tokens usa DPAPI) — multiplataforma queda pendiente.

**Qué dices**
Agradece, deja el repositorio y la documentación a la vista, y abre turno de preguntas
anticipando la más típica: "¿esto reemplaza a Azure DevOps?" — no, cubre el hueco antes de que
lo tengas.

---

*Guion preparado para una sesión de 50 minutos sobre el Power BI MCP Deployment Server — ajusta
los tiempos de cada demo a la velocidad real del entorno el día de la charla.*
