# Power BI MCP Deployment

**Gestiona tus modelos e informes de Power BI hablando en español con Claude (o cualquier otro asistente de IA compatible).**

Este proyecto conecta tu asistente de IA con tu cuenta de Power BI, para que puedas pedirle cosas como:

> "Descarga el modelo Sales Model del workspace de Producción"
> "Sube el informe Dashboard Ventas al workspace de Test y enlázalo al modelo correcto"
> "¿Qué se ha desplegado últimamente en el workspace de Producción?"

...y que lo haga por ti, sin tocar el portal de Power BI ni escribir código.

## ¿Para quién es esto?

- Analistas y desarrolladores de Power BI que mueven modelos e informes entre entornos (Desarrollo, Test, Producción) y quieren hacerlo de forma más rápida y con un historial de lo que se ha hecho.
- Equipos que no tienen infraestructura de DevOps/CI-CD montada, pero quieren más control que el "Publicar" manual desde Power BI Desktop.
- Cualquier persona que use Power BI y Claude Desktop, **sin necesidad de saber programar**.

## Empieza aquí

| Si tú... | Empieza por... |
|---|---|
| No tienes experiencia técnica y solo quieres usarlo desde Claude Desktop | 📘 [Guía de Inicio Rápido](docs/guia-inicio-rapido.md) |
| Quieres entender todo lo que puede hacer, comparado con otras opciones de Microsoft | 📗 [Manual de Usuario completo](docs/user_manual.md) |
| Quieres configurar despliegues automáticos entre entornos (DEV → TEST → PROD) | 📙 [Guía de Configuración de Despliegues](docs/deployment-configuration.md) |
| Vas a configurarlo en GitHub Copilot u otro cliente MCP | 📄 [Configuración de Clientes MCP](docs/mcp-client-config.md) |
| Algo no funciona | 🛟 [Resolución de Problemas](docs/troubleshooting.md) |
| Eres desarrollador y quieres ver la arquitectura, herramientas y API interna | ⚙️ [Referencia Técnica](docs/technical-reference.md) |

## Qué incluye

- Soporte para los formatos habituales de Power BI: PBIX, PBIP, PBIR y JSON (informes heredados).
- Versionado automático: si trabajas fuera de un repositorio Git, cada descarga se guarda con fecha y hora para no perder versiones anteriores.
- Historial de descargas y despliegues consultable en cualquier momento.
- Reenlace automático de informes al modelo semántico correcto al moverlos entre entornos.
- Configuración "configura una vez, despliega siempre": define a qué workspace va cada modelo/informe y el servidor se encarga del resto.

## Novedades de la versión 0.2.0

Detalle completo con ejemplos de prompts y su equivalente en CLI: [Novedades 0.2.0](docs/novedades-0.2.0.md).

- **Proyectos**: agrupa varios modelos e informes bajo un nombre y despliégalos/promociónalos juntos, en el orden correcto y con reenlace automático.
- **Entornos con jerarquía**: alias libre (Desarrollo, Integración, Producción...) con una posición numérica que define la cadena de promoción.
- **`promote` (por defecto) vs `deploy` (explícito)**: promociona lo ya validado en el entorno anterior sin tocar disco; despliega directo desde una carpeta local solo para emergencias/hotfixes.
- **Detección de divergencia (drift)**: si un entorno recibió cambios fuera de la cadena normal, se avisa antes de sobrescribir en vez de hacerlo en silencio.
- **Carpetas de Fabric por artefacto**: cada modelo o informe puede vivir en su propia carpeta dentro del workspace, con auto-creación y reubicación si cambia.
- **"Respetar estructura local"**: replica la jerarquía de subcarpetas de tu proyecto local como carpetas en el workspace al desplegar.
- **Estructura de despliegue de un proyecto**: vista de solo lectura con artefactos, carpetas, workspaces y estado por entorno.
- **Creación de workspaces por proyecto**: modo automático (dev/acc/prod con nombres predecibles) o manual (tú eliges nombres y si separar modelos e informes).
- **Árbol de despliegue**: vista visual en texto de proyectos, entornos, carpetas y artefactos con la fecha del último despliegue.
- Corrección de un bug en la configuración de despliegue por CLI (`config-model`/`config-report`) que impedía guardar el flag de auto-despliegue correctamente.

## Licencia

MIT — ver [LICENSE](LICENSE).

## Contribuir

¡Las contribuciones son bienvenidas! Abre un issue o un pull request en GitHub.

## Soporte

- Issues en GitHub: https://github.com/megeagomez/PowerBiDeploymentMCP/issues
