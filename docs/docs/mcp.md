<p class="os-kicker" markdown>Extender</p>
# MCP

ObsyGPT habla el **Model Context Protocol**: registra servidores MCP y sus herramientas quedan disponibles para tus agentes como tools más, con aprobación si son sensibles.

## Registrar un servidor

**Ajustes > Administración > MCPs > Registrar MCP**:

| Campo | Descripción |
|---|---|
| Nombre | Identificador del servidor |
| Conexión | `command` (proceso local) o `url` (servidor remoto) |
| Comando / URL | `npx -y @modelcontextprotocol/server-filesystem ./workspace` o `https://...` |
| Activado | Habilita el servidor para el handshake |

Al guardar, ObsyGPT hace un **handshake real** (`initialize` → `tools/list`) para inspeccionar las herramientas que expone.

![MCPs](assets/screenshots/settings-modelo.png)

## Inspeccionar y probar

- **Validar MCP** — repite el handshake y lista las tools detectadas.
- **Ejecutar método MCP** — llama a cualquier método (`tools/list`, `tools/call`...) con parámetros JSON para verificar el servidor antes de dárselo a un agente.

## Conectar a agentes

En **Ajustes > Agentes > MCP** activa los servidores que ese agente debe usar. Cada herramienta del servidor aparece como tool del agente y respeta las [políticas de permisos](herramientas.md#politicas-por-herramienta).

## Todo trazado

Cada llamada MCP queda registrada en la [Traza](chat.md#traza-de-runs) con su método, argumentos y resultado.
