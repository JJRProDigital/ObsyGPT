<p class="os-kicker" markdown>Empezar</p>
# Recorrido visual

Una pantalla por sección: esto es lo que verás al entrar en ObsyGPT.

## Chat

El corazón de la app: conversaciones con tu agente activo, historial y carpetas en la barra lateral, selector de agente y modelo, modos **Act** / **Plan** / **Think** y paleta de skills (`Alt` + espacio).

![Chat](../assets/screenshots/chat.png)

- **Nuevo chat** desde la barra lateral; organiza conversaciones en carpetas.
- El **composer** acepta adjuntos y modo voz (micrófono push-to-talk).
- Cuando el agente intenta una acción sensible, aparece una **tarjeta de aprobación** con Aprobar / Rechazar.

## Tareas

Tareas en segundo plano del agente: programadas, recurrentes, pausables y cancelables. La insignia muestra cuántas están activas.

![Tareas](../assets/screenshots/tasks.png)

## Proyectos

Carpetas de proyecto con instrucciones, memoria, archivos y chats propios. Ideal para aislar contexto por cliente o iniciativa.

![Proyectos](../assets/screenshots/projects.png)

## Traza

Todo queda registrado: cada run, tool call, llamada MCP y aprobación es inspeccionable desde aquí, incluidos los runs hijos de sub-agentes.

![Traza](../assets/screenshots/trace.png)

## Memoria

Recuerdos por usuario que se inyectan en el chat, conversaciones indexadas semánticamente y sugerencias de hábitos aprendidos.

![Memoria](../assets/screenshots/memory.png)

## Skills

Biblioteca de skills siguiendo el estándar Agent Skills (`SKILL.md`), editor integrado y generador con IA. Se invocan desde el chat con `/nombre_skill tarea`.

![Skills](../assets/screenshots/skills.png)

## Herramientas

Catálogo de tools disponibles y sus permisos (seguras vs. sensibles con aprobación).

![Herramientas](../assets/screenshots/tools.png)

## Conectores

Credenciales cifradas por usuario para GitHub (repos, archivos, issues) y Google Drive (solo lectura).

![Conectores](../assets/screenshots/connectors.png)

## Historial

Listado completo de conversaciones pasadas con filtros.

![Historial](../assets/screenshots/history.png)

## Ajustes

Pestañas: Modelo, Preferencias, Seguridad, Sistema, Agentes, Triggers, Datos y Administración (solo admin), con buscador integrado.

![Ajustes - Modelo](../assets/screenshots/settings-modelo.png)

![Ajustes - Agentes](../assets/screenshots/settings-agentes.png)

![Ajustes - Triggers](../assets/screenshots/settings-triggers.png)

## Monitorización (admin)

Métricas agregadas: runs/día, uso de tools, duraciones y fallbacks, con exportación OTLP opcional.

![Monitorización](../assets/screenshots/monitoring.png)

## Diagnóstico

Estado del sistema: salud de servicios, modelos activos y configuración efectiva.

![Diagnóstico](../assets/screenshots/diagnostics.png)
