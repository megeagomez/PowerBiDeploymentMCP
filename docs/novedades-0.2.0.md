# Novedades de la versión 0.2.0 — Proyectos, entornos y carpetas

Esta versión añade varias piezas que se apoyan entre sí:

1. **Proyectos**: agrupar varios modelos e informes para desplegarlos/promocionarlos juntos.
2. **Entornos con jerarquía**: Desarrollo → Integración → Producción (o los nombres que quieras), con detección automática de divergencia.
3. **Carpetas de Fabric**: organizar cada artefacto en su carpeta dentro del workspace, con auto-creación.
4. **Creación de workspaces por proyecto**: automática (dev/acc/prod con nombres predecibles) o manual, con o sin separar modelos e informes.
5. **Árbol de despliegue**: vista visual de proyectos, entornos, carpetas y artefactos con su fecha de último despliegue.

Cada apartado incluye un **prompt de ejemplo** (para pedírselo a Claude Desktop en lenguaje natural, vía MCP) y su **equivalente exacto en el CLI** (`pbi_cli.py`), para que puedas probar la misma funcionalidad por los dos caminos.

---

## 1. Entornos con jerarquía

Cada entorno tiene un alias libre y una posición numérica (`stage_order`) que define la cadena de promoción — el nombre no importa, lo que importa es el orden.

**Prompt:**
> Crea un entorno llamado Desarrollo que apunte al workspace "WS Dev", con orden 1 en la cadena de promoción

> Crea un entorno llamado Integración que apunte al workspace "WS Integración", con orden 2

> Crea un entorno llamado Producción que apunte al workspace "WS Prod", con orden 3

> Lista los entornos configurados y su orden de promoción

**CLI equivalente:**
```
pbi_cli.py env-create Desarrollo "WS Dev" --stage-order 1
pbi_cli.py env-create Integración "WS Integración" --stage-order 2
pbi_cli.py env-create Producción "WS Prod" --stage-order 3
pbi_cli.py env-list
```

---

## 2. Proyectos: agrupar modelos e informes

Un proyecto agrupa varios modelos semánticos y reports para moverlos juntos, en el orden correcto (modelos antes que reports, con reenlace automático).

**Prompt:**
> Crea el proyecto Ventas

> Añade el modelo ModeloVentas al proyecto Ventas

> Añade el informe DashboardVentas al proyecto Ventas, reenlazado al modelo ModeloVentas

> Muéstrame los artefactos del proyecto Ventas

> Lista todos los proyectos que tengo configurados

**CLI equivalente:**
```
pbi_cli.py project-create Ventas
pbi_cli.py project-add-artifact Ventas model ModeloVentas
pbi_cli.py project-add-artifact Ventas report DashboardVentas --rebind ModeloVentas
pbi_cli.py project-show Ventas
pbi_cli.py project-list
```

Para quitar un artefacto: *"Quita el informe DashboardVentas del proyecto Ventas"* → `pbi_cli.py project-remove-artifact Ventas report DashboardVentas`.

---

## 3. Carpetas de Fabric por artefacto

Cada artefacto de un proyecto puede vivir en su propia carpeta dentro del workspace (rutas anidadas tipo `"Ventas/Modelos"`). Si la carpeta no existe, se crea sola; si el artefacto ya existía en otra carpeta y lo vuelves a desplegar, se mueve a la nueva.

**Prompt:**
> Añade el modelo ModeloVentas al proyecto Ventas en la carpeta "Ventas/Modelos"

> Añade el informe DashboardVentas al proyecto Ventas, reenlazado a ModeloVentas, en la carpeta "Ventas/Informes"

**CLI equivalente:**
```
pbi_cli.py project-add-artifact Ventas model ModeloVentas --folder "Ventas/Modelos"
pbi_cli.py project-add-artifact Ventas report DashboardVentas --rebind ModeloVentas --folder "Ventas/Informes"
```

También funciona fuera del sistema de proyectos, en una subida suelta:

**Prompt:**
> Sube el modelo semántico que tengo en D:\Modelo.SemanticModel al workspace "WS Dev", en la carpeta "Otra/Ruta"

**CLI equivalente:**
```
pbi_cli.py upload-model "WS Dev" D:\Modelo.SemanticModel --folder "Otra/Ruta"
pbi_cli.py upload-report "WS Dev" D:\Informe.Report --folder "Otra/Ruta"
```

### "Respetar estructura local"

Si tu carpeta de proyecto ya tiene subcarpetas en disco (p.ej. `Ventas\Modelos\ModeloVentas.SemanticModel`, `Ventas\Informes\DashboardVentas.Report`), puedes replicar esa misma organización en el workspace automáticamente, sin configurar la carpeta de cada artefacto a mano. Solo aplica a `deploy` (sube desde disco); `promote` no lo necesita porque no toca disco.

**Prompt:**
> Despliega el proyecto Ventas desde D:\Proyectos\Ventas al entorno Desarrollo, respetando la estructura de carpetas local

**CLI equivalente:**
```
pbi_cli.py deploy Ventas Desarrollo D:\Proyectos\Ventas --respect-local-structure
```

Si un artefacto ya tiene una carpeta configurada explícitamente (con `--folder`), esa configuración manda siempre sobre la estructura local detectada.

---

## 4. Deploy (explícito) vs Promote (por defecto)

- **`promote`** es el flujo normal: mueve, en memoria, lo que ya está desplegado en el entorno anterior de la cadena hacia el siguiente. No toca tu disco.
- **`deploy`** es explícito: sube directamente desde una carpeta local a **cualquier** entorno, saltándose la cadena — para emergencias/hotfixes.

**Prompt (flujo normal — promote):**
> Promociona el proyecto Ventas a Producción

*(el asistente entiende solo, por el `stage_order`, que el origen es Integración — no hace falta decirlo)*

**CLI equivalente:**
```
pbi_cli.py promote Ventas Producción
```

**Prompt (emergencia — deploy explícito):**
> Necesito un hotfix urgente: despliega el proyecto Ventas directamente desde D:\Proyectos\Ventas al entorno Producción

**CLI equivalente:**
```
pbi_cli.py deploy Ventas Producción D:\Proyectos\Ventas
```

Si simplemente dices "despliega/promociona el proyecto X a Y" sin mencionar una carpeta local ni una emergencia, el asistente usa `promote` por defecto.

---

## 5. Detección de divergencia (drift) antes de sobrescribir

Si alguien hizo un `deploy` de emergencia saltándose la cadena, o si el contenido de un entorno se editó a mano fuera de esta herramienta, `promote` lo detecta y **no sobrescribe nada sin avisar**.

**Prompt (secuencia para provocarlo y verlo en acción):**
> Despliega el proyecto Ventas directamente desde D:\Proyectos\Ventas al entorno Producción *(hotfix de emergencia, salta la cadena)*

> Promociona el proyecto Ventas a Producción *(debería avisar de divergencia)*

> Confirma la promoción de Ventas a Producción a pesar de la divergencia

**CLI equivalente:**
```
pbi_cli.py deploy Ventas Producción D:\Proyectos\Ventas
pbi_cli.py promote Ventas Producción
  ⚠ Divergencia detectada respecto al entorno origen (Integración):
    [SemanticModel] ModeloVentas:
      - el último cambio en este entorno fue un 'deploy' directo, no una promoción
  ¿Confirmas la sobrescritura? [y/N]

pbi_cli.py promote Ventas Producción --yes
```

---

## 6. Estructura de despliegue de un proyecto

Vista de solo lectura: qué artefactos tiene el proyecto, a qué carpeta de qué workspace va cada uno en cada entorno, y si ya hay algo desplegado ahí (y desde qué entorno se promocionó).

**Prompt:**
> Dime la estructura de despliegue del proyecto Ventas

**CLI equivalente:**
```
pbi_cli.py project-structure Ventas
```

---

## 7. Configuración de despliegue por entorno (modelos/informes sueltos)

Además de los proyectos, sigue existiendo la configuración de auto-despliegue para un modelo o informe individual — ahora corregida (el flag de auto-despliegue no se guardaba bien) y con soporte de entorno.

**Prompt:**
> Configura el despliegue del modelo ModeloVentas al workspace "WS Dev" para el entorno Desarrollo, con auto-despliegue activado

**CLI equivalente:**
```
pbi_cli.py config-model ModeloVentas "WS Dev" --auto --profile Desarrollo
pbi_cli.py config-report DashboardVentas "WS Dev" --model ModeloVentas --auto --profile Desarrollo
```

---

## 8. Creación de workspaces por proyecto

Además de reutilizar workspaces ya existentes, ahora puedes crearlos directamente desde aquí — en modo automático (siguiendo una convención de nombres fija) o manual (tú eliges los nombres y si separar modelos de informes).

### Modo automático (dev/acc/prod)

Asegura que existan los entornos **dev**, **acc** y **prod** (los crea con `stage_order` 1/2/3 si faltan) y crea, para cada uno, **un workspace separado para modelos y otro para informes**, con la convención `{proyecto}_semantic{_dev|_acc|}` / `{proyecto}_reports{_dev|_acc|}` (producción sin sufijo). Para el proyecto "Ventas": `Ventas_semantic_dev`, `Ventas_reports_dev`, `Ventas_semantic_acc`, `Ventas_reports_acc`, `Ventas_semantic`, `Ventas_reports`.

**Prompt:**
> Aprovisiona automáticamente los workspaces del proyecto Ventas para dev, acc y prod

**CLI equivalente:**
```
pbi_cli.py project-provision-workspaces Ventas
```

Si quieres asignarlos a una capacidad de Fabric, consulta antes las disponibles y pasa el ID:

**Prompt:**
> Lista las capacidades de Fabric disponibles

> Aprovisiona los workspaces del proyecto Ventas usando la capacidad cap-123-...

**CLI equivalente:**
```
pbi_cli.py capacities
pbi_cli.py project-provision-workspaces Ventas --capacity-id cap-123-...
```

### Modo manual

Tú decides el nombre de cada workspace, y si separar modelos e informes o mantenerlos juntos. Omite el tipo para un workspace combinado (modelos + informes); indícalo (`model`/`report`) para separarlos.

**Prompt:**
> Configura el workspace "MiWorkspaceVentas" como destino combinado (modelos e informes) del proyecto Ventas en el entorno Desarrollo

> Configura el workspace "VentasModelosProd" para los modelos semánticos del proyecto Ventas en Producción, y "VentasInformesProd" para los informes

**CLI equivalente:**
```
pbi_cli.py project-set-workspace Ventas Desarrollo "MiWorkspaceVentas"
pbi_cli.py project-set-workspace Ventas Producción "VentasModelosProd" --type model
pbi_cli.py project-set-workspace Ventas Producción "VentasInformesProd" --type report
```

Si el workspace indicado no existe todavía, se crea; si ya existe, se reutiliza. Estos workspaces por proyecto tienen prioridad sobre el workspace por defecto del entorno a la hora de desplegar o promocionar — así, dentro de un mismo workspace de Producción compartido, cada proyecto puede tener sus propios workspaces dedicados en vez de mezclarse.

---

## 9. Árbol de despliegue

Vista visual (texto ASCII con `-` y `|`) de uno o todos los proyectos: entornos, carpetas simuladas, artefactos, workspace resuelto y fecha del último despliegue.

**Prompt:**
> Muéstrame el árbol de despliegue del proyecto Ventas

> Muéstrame el árbol de despliegue de todos mis proyectos

**CLI equivalente:**
```
pbi_cli.py project-tree Ventas
pbi_cli.py project-tree
```

Ejemplo de salida:
```
Ventas
|-- dev (stage_order=1)
|   |-- Modelos
|   |   |-- [SemanticModel] ModeloVentas  (Ventas_semantic_dev, últ. despliegue: 2026-08-17 09:12:03)
|   |-- Informes
|       |-- [Report] DashboardVentas  (Ventas_reports_dev, últ. despliegue: sin desplegar)
|-- acc (stage_order=2)
|   ...
|-- prod (stage_order=3)
    ...
```

---

## Resumen de comandos nuevos

| Comando CLI | Tool MCP equivalente | Qué hace |
|---|---|---|
| `env-create` / `env-list` | `configure_environment` / `list_environments` | Crear y listar entornos con su posición en la cadena |
| `project-create` / `project-list` / `project-show` | `create_project` / `list_projects` / `get_project` | Crear y consultar proyectos |
| `project-add-artifact [--folder]` / `project-remove-artifact` | `add_project_artifact` / `remove_project_artifact` | Añadir/quitar modelos e informes de un proyecto, con carpeta opcional |
| `project-structure <proyecto>` | `get_project_deployment_structure` | Estructura completa de despliegue: artefactos, carpetas, entornos, estado |
| `deploy <proyecto> <entorno> <carpeta> [--respect-local-structure]` | `deploy_project` | Despliegue explícito desde local (hotfix) |
| `promote <proyecto> <entorno> [--yes]` | `promote_project` | Promoción por defecto entre entornos, con detección de drift |
| `upload-model` / `upload-report [--folder]` | `upload_semantic_model` / `upload_report` | Subida suelta con carpeta de destino opcional |
| `config-model` / `config-report [--profile]` | `configure_semantic_model_deployment` / `configure_report_deployment` | Configuración de auto-despliegue por entorno |
| `project-provision-workspaces [--capacity-id]` | `auto_provision_project_workspaces` | Modo automático: crea dev/acc/prod + 6 workspaces por proyecto |
| `project-set-workspace [--type] [--capacity-id]` | `configure_project_workspace` | Modo manual: asigna/crea el workspace de un proyecto por entorno |
| `capacities` | `list_fabric_capacities` | Lista las capacidades de Fabric disponibles |
| `project-tree [proyecto]` | `get_deployment_tree` | Árbol ASCII de proyecto(s)/entornos/carpetas/artefactos |

Todas las tools MCP de la tabla están disponibles directamente desde Claude Desktop en lenguaje natural — no hace falta usar el CLI, es solo la vía alternativa para probar lo mismo desde la terminal.
