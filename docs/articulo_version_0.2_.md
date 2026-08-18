# Despliegue de proyectos con el MCP de deploy

El concepto de proyecto, y el de entorno (dev-acc-prod), se los acabo de añadir al servidor MCP.

Se puede usar comando a comando, pero lo normal es ir prompt a prompt y dejar que el LLM traduzca cada frase a la llamada que toca. Va un ejemplo con el proyecto Ventas, un modelo de retail y otro de mayorista, prompt a prompt y lo que pasa por debajo de cada uno:

**"Créame el proyecto Ventas"**
Debajo: `project-create Ventas`. Solo crea el registro del proyecto en la base de metadatos, todavía no toca Fabric.

**"El proyecto Ventas tiene dos modelos semánticos: uno en c:\modelosemanticoventasretail y otro en c:\modelosemanticoventasmayorista"**
Debajo: registra los dos artefactos contra el proyecto — `project-add-artifact Ventas model retail` y `project-add-artifact Ventas model mayorista`. Sigue sin tocar Fabric, es metadatos locales.

**"Mete retail en una carpeta llamada Retail y mayorista en una carpeta llamada Mayorista"**
Debajo: añade `--folder Retail` y `--folder Mayorista` a esos mismos artefactos, para que al desplegar se repliquen como subcarpetas dentro del workspace de destino.

**"Crea el workspace data_dev y sube ahí los modelos semánticos"**
Debajo: primero pregunta qué capacidad de Fabric asignar, porque el workspace no existe todavía. Luego `project-set-workspace Ventas DEV data_dev --capacity-id <ID>` para crear el workspace y enlazarlo al entorno DEV, y `deploy Ventas DEV <carpeta_local>` para subir los modelos de verdad.

**"Añade un entorno ACC que vaya después de DEV, y luego PROD después de ACC"**
Debajo: dos `env-create`, cada uno con un `--stage-order` mayor que el anterior. El orden es literal — si se equivoca de número la cadena de promoción queda mal — así que antes de crear el segundo confirma el orden que ha entendido.

**"Reenlaza el informe de Retail al modelo de Mayorista"**
Debajo: `rebind-report data_dev Retail Mayorista`. Cambia a qué modelo apunta el informe ya publicado, sin tocar los datos de ningún modelo.

**"Promociona Ventas de DEV a ACC"**
Debajo: `promote Ventas ACC`. Antes de mover nada compara el hash de lo que hay en ACC contra lo último desplegado desde DEV; si encuentra algo en ACC que no viene de esa cadena (drift), para y pregunta en vez de sobrescribirlo sin más.

**"Enséñame cómo ha quedado todo"**
Debajo: `project-tree Ventas`. Solo lectura: imprime el árbol proyecto → entorno → carpeta → artefacto tal cual está en la base de metadatos.

## Qué es el MCP aquí

Es una capa de herramientas deterministas que construí yo sobre la API REST de Fabric: crear proyecto, configurar entorno, desplegar, promocionar. El LLM no toca Fabric directamente, decide qué función llamar y con qué parámetros a partir de lo que le pido en lenguaje natural. Por debajo se ejecuta la misma llamada que haría un script en Azure DevOps o que haría yo a mano con `az rest`. No se salta permisos ni capacidad: si no tengo contributor en el workspace, el LLM tampoco lo tiene.

## Qué pasó

Antes de tocar nada consultó el estado actual y encontró un proyecto a medio configurar, de una sesión mía anterior que no había terminado. No lo ignoró ni decidió por su cuenta: preguntó qué hacer con él y qué capacidad de Fabric quería para los workspaces nuevos.

Con mis respuestas, ejecutó la secuencia: creó el proyecto, añadió los cuatro artefactos respetando la carpeta anidada, creó el entorno PROD (ACC ya existía), enlazó el workspace del proyecto en cada entorno, desplegó a ACC desde la carpeta local y promocionó ese contenido de ACC a PROD. Al final me enseñó el árbol de despliegue completo para comprobar que todo había quedado donde tocaba.

Nada de esto es "inteligencia sobre Power BI", son llamadas normales a la API de Fabric. Lo que aportó el LLM fue traducir una frase ambigua en la secuencia correcta de llamadas, y parar a preguntar cuando la ambigüedad tenía consecuencias reales.

## Dos perfiles distintos

Si eres analista y necesitas un flujo dev→acc→prod repetible sin escribir PowerShell ni tocar Postman, esto sustituye el clic a clic en el portal de Fabric: describes la intención, el LLM pregunta lo que importa (nombres, capacidad, qué hacer con lo que ya existe) y ejecuta. No te libera de entender qué es un workspace, un rebind o una capacidad de Fabric, solo de escribir el código que lo hace.

Si tu trabajo es que el despliegue sea repetible para un equipo entero, el valor está en otro sitio: usas el LLM para prototipar rápido, como en esta sesión, y luego le pides el CLI equivalente para sacarlo del chat y meterlo en algo versionado.

## El CLI real detrás de esto

La sesión de arriba, traducida a comandos del CLI del proyecto (no llamadas sueltas a la API REST, los mismos verbos que invocó el LLM por mí):

```bash
python pbi_cli.py auth

python pbi_cli.py project-create test_meg --description "Demo LinkedIn: ventas y VentasEstrella"

python pbi_cli.py project-add-artifact test_meg model ventas
python pbi_cli.py project-add-artifact test_meg model VentasEstrella --folder VentasEstrella
python pbi_cli.py project-add-artifact test_meg report ventas --rebind ventas
python pbi_cli.py project-add-artifact test_meg report VentasEstrella --folder VentasEstrella --rebind VentasEstrella

python pbi_cli.py env-create PROD test_meg_PROD --stage-order 2

python pbi_cli.py project-set-workspace test_meg ACC test_meg_ACC
python pbi_cli.py project-set-workspace test_meg PROD test_meg_PROD --capacity-id <ID>

python pbi_cli.py deploy test_meg ACC "D:\...\demo" --respect-local-structure
python pbi_cli.py promote test_meg PROD

python pbi_cli.py project-tree test_meg
```

Cada comando hace las mismas llamadas REST que haría un script manual; la diferencia es que ya no orquesto yo el orden, los IDs intermedios ni el polling de las operaciones asíncronas.

Una cosa que hay que decir clara: `auth` hoy es device flow interactivo, pensado para lanzarlo desde terminal, no desde una pipeline sin supervisión. Para meter esto en GitHub Actions o Azure DevOps falta añadir login con service principal al CLI — no está hecho todavía. El resto de comandos ya son perfectamente scriptables en cuanto esa pieza exista.

## Lo que el MCP no hace

No sustituye entender qué es una promoción entre entornos, un rebind de report a modelo, o por qué una capacidad inactiva te hace fallar el despliegue. Cada ejecución interpreta lenguaje natural, así que para algo que corre cientos de veces sin supervisión lo correcto es fijar el comportamiento en código, no dejar que el LLM decida en caliente cada vez. Y sigue dependiendo de los permisos, la licencia y la capacidad reales del tenant — ahí no hay atajo.
