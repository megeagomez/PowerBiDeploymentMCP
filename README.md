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

## Licencia

MIT — ver [LICENSE](LICENSE).

## Contribuir

¡Las contribuciones son bienvenidas! Abre un issue o un pull request en GitHub.

## Soporte

- Issues en GitHub: https://github.com/megeagomez/PowerBiDeploymentMCP/issues
