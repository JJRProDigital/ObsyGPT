<p class="os-kicker" markdown>Trabajar</p>
# Chat

El chat es la superficie principal de ObsyGPT: una conversación con tu agente que ejecuta un **bucle agéntico iterativo** (plan → actuar → observar) usando un protocolo de herramientas en texto plano que funciona con cualquier modelo, incluidos los locales.

## Conceptos clave

- **Modos de chat**: `Act` (ejecuta tools), `Plan` (planifica antes de actuar) y `Think` (razonamiento extendido). Cambia de modo desde el composer.
- **Paleta de skills** (`Alt` + espacio): invoca skills sin escribir `/`.
- **Adjuntos**: arrastra archivos al composer; los multimodales se pasan al modelo si el agente los admite.
- **Carpetas**: organiza conversaciones en la barra lateral; renómbralas o muévelas desde el menú de cada fila.
- **Aproximación de tokens** visible para que controles el contexto.

## El bucle agéntico

1. El agente recibe tu mensaje junto con su system prompt, skills activas, tools habilitadas y memoria.
2. Decide si responde directamente o **llama a una herramienta**.
3. Las tools **seguras** (lectura, búsqueda web...) se ejecutan al instante; las **sensibles** (escritura de archivos, shell, sub-agentes) generan una **aprobación**.
4. Observa el resultado y repite hasta dar la respuesta final.

Cada paso queda registrado: mira la [Traza](#traza-de-runs).

## Aprobaciones

Cuando el agente intenta una acción sensible, el flujo se pausa y aparece una tarjeta con la tool y sus argumentos:

- **Aprobar** — la ejecución continúa exactamente donde se detuvo.
- **Rechazar** — el agente recibe el rechazo y ajusta su plan.

Puedes definir la política por herramienta en [Ajustes > Seguridad > Permisos](seguridad.md#permisos-por-herramienta): *permitir*, *preguntar* o *bloquear*.

## Sub-agentes

La tool `dispatch_subagents` delega hasta **3 líneas de trabajo paralelas** a otros agentes configurados. Los runs hijos quedan enlazados al padre en la vista de Traza, así que puedes auditar cada rama.

## Traza de runs

Todo es inspeccionable: cada run, tool call, llamada MCP y aprobación queda registrado. Abre **Traza** en la barra lateral para ver el árbol completo con duraciones, entradas y salidas.

## Atajos

| Atajo | Acción |
|---|---|
| `Alt` + espacio | Paleta de skills |
| `/nombre_skill tarea` | Invocar una skill desde el mensaje |
| Micrófono | Nota de voz push-to-talk (transcripción local) |
| Altavoz | Reproducir la respuesta hablada |
