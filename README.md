# ObsyGPT

Workspace de agentes IA self-hosted: chatea con agentes configurables, delega trabajo en sub-agentes paralelos y extiéndelo todo con skills, servidores MCP, plugins y conectores — con aprobación humana para cada acción sensible.

[![CI](https://github.com/JJRProDigital/ObsyGPT/actions/workflows/ci.yml/badge.svg)](https://github.com/JJRProDigital/ObsyGPT/actions/workflows/ci.yml)
[![Licencia: MIT](https://img.shields.io/badge/Licencia-MIT-D5B06D.svg)](LICENSE)

## Inicio rápido (Docker)

```bash
git clone https://github.com/JJRProDigital/ObsyGPT
cd ObsyGPT
cp .env.example .env    # pega tu API key
docker compose up -d
```

Abre `http://localhost:3001` y regístrate — **la primera cuenta creada es el administrador**.

## Qué incluye

- **Chat agéntico** — bucle iterativo plan → actuar → observar con un protocolo de herramientas en texto plano que funciona con cualquier modelo (OpenRouter, OpenAI, Anthropic, Gemini, Ollama, llama.cpp o cualquier endpoint compatible con OpenAI), incluidos modelos locales.
- **Aprobaciones de acciones sensibles** — escrituras de archivos, comandos de shell y despacho de sub-agentes pausan el flujo hasta que apruebas o rechazas desde la UI; el bucle se reanuda exactamente donde se detuvo.
- **Sub-agentes** — la tool `dispatch_subagents` delega hasta 3 líneas de trabajo paralelas a otros agentes configurados; los runs hijos quedan enlazados al padre en la vista de traza.
- **Estándar Agent Skills** — las skills viven en `agents/skills/<nombre>/SKILL.md` (frontmatter + Markdown + recursos opcionales), editables desde la UI e invocables desde el chat con `/nombre_skill tarea`.
- **MCP** — registra servidores MCP (comando o URL), inspecciona sus herramientas con un handshake real `initialize`/`tools/list` y expónselas a los agentes como tools con aprobación.
- **Conectores** — credenciales cifradas por usuario; incluidos: GitHub (buscar repos, leer archivos, listar/crear issues) y Google Drive (solo lectura).
- **Plugins** — paquetes compartibles (`plugin.json`) que agrupan skills, servidores MCP y definiciones de sub-agentes; instálalos desde el catálogo local o desde marketplaces git.
- **Proyectos y tareas** — carpetas de proyecto, instrucciones y memoria por proyecto; tareas en segundo plano con programación, recurrencia, pausa/reanudación/cancelación y auto-recuperación.
- **Memoria persistente y hábitos** — recuerdos por usuario inyectados en el chat, más sugerencias de hábitos aprendidos.
- **Monitorización** — panel de administración (runs/día, uso de tools, duraciones, fallbacks) y exportación OTLP opcional (eventos `user_prompt`, `assistant_response`, `tool_result`, `api_error`; contenido redactado por defecto).
- **Todo trazado** — cada run, tool call, llamada MCP y aprobación queda registrado e inspeccionable.

## Requisitos

- Docker (quickstart todo-en-uno), **o**
- Python 3.13 + Node 20 + PostgreSQL 16 (desarrollo local, ver abajo)

## Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `POSTGRES_PASSWORD` | recomendada | Contraseña del servicio Postgres (por defecto `obsygpt_dev_password`) |
| `OPENROUTER_API_KEY` | un proveedor | Key del proveedor por defecto sembrado |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | opcional | Proveedores adicionales |
| `SESSION_SECRET` | sí | Cadena aleatoria que firma las sesiones (`python -c "import secrets; print(secrets.token_urlsafe())"`) |
| `FRONTEND_URL` | por defecto vale | Origen público del frontend (CORS), por defecto `http://localhost:3001` |
| `FRONTEND_PORT` | por defecto vale | Puerto del host para la UI (por defecto 3001) |
| `VITE_BACKEND_URL` | dejar vacía | Vacía = la UI usa el proxy nginx integrado |

Avanzadas opcionales: `CONNECTOR_ENCRYPTION_KEY` (clave Fernet para credenciales de conectores; se deriva de `SESSION_SECRET` si se omite), `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_EXPORTER_OTLP_HEADERS` / `OTEL_CONTENT_CAPTURE` (export de monitorización), `AGENT_COMMAND_ALLOWLIST` (allowlist de prefijos para la tool de shell), `AGENT_COMMAND_ENV_PASSTHROUGH` (variables de entorno extra que la tool de shell puede heredar, separadas por comas), `OBSYGPT_REQUIRE_STRONG_SECRETS=1` (falla el arranque si `SESSION_SECRET` no está configurada — recomendado en producción).

## Modelos locales (llama.cpp / Ollama)

ObsyGPT funciona muy bien con modelos totalmente locales. Las URLs cambian según cómo lo ejecutes:

**Instalación Docker** (quickstart): el backend corre en un contenedor, donde `127.0.0.1` es el propio contenedor — no tu máquina. Apunta el provider a tu host:

1. Arranca el servidor escuchando en todas las interfaces:
   - llama.cpp: `llama-server --host 0.0.0.0 --port 8080 ...` (por defecto escucha en `127.0.0.1`, inalcanzable desde el contenedor)
   - Ollama: escucha en `0.0.0.0` por defecto (`OLLAMA_HOST=0.0.0.0` si lo cambiaste)
2. En la UI: Ajustes > Modelo > Proveedores guardados, registra el provider con la URL base:
   - llama.cpp: `http://host.docker.internal:8080/v1`
   - Ollama: `http://host.docker.internal:11434/v1`
3. Pulsa **Detectar modelos** y activa el que quieras para tu agente.

`host.docker.internal` resuelve dentro de los contenedores en Windows/macOS sin configurar nada; en Linux funciona gracias a la entrada `extra_hosts: host-gateway` ya incluida en `docker-compose.yml`.

**Instalación de desarrollo local** (Python + uvicorn en tu máquina): usa las URLs locales normales — `http://127.0.0.1:8080/v1` (llama.cpp) o `http://127.0.0.1:11434/v1` (Ollama).

## Notas de seguridad

- Cambia `POSTGRES_PASSWORD` y `SESSION_SECRET` antes de exponer la app más allá de localhost. Con la secretaria por defecto el backend arranca pero emite un aviso CRÍTICO en el log: las cookies de sesión y las credenciales cifradas de los conectores quedan desprotegidas. En producción usa `OBSYGPT_REQUIRE_STRONG_SECRETS=1` para que el arranque falle directamente.
- La primera cuenta registrada es el admin; el registro sigue abierto para más cuentas — configura tu proxy inverso si quieres restringirlo.
- Las tools de shell y escritura de archivos están acotadas a la carpeta del workspace y protegidas por aprobaciones; la tool de shell hereda un entorno mínimo (sin API keys ni secretos del proceso — usa `AGENT_COMMAND_ENV_PASSTHROUGH` si un comando necesita alguna variable concreta) y valida cada segmento de comandos encadenados contra la allowlist. Las tools de navegador requieren Playwright (no incluido en la imagen Docker) — ver desarrollo local.
- `web_fetch`, `read_url` y la navegación del navegador rechazan URLs hacia localhost, IPs privadas y hosts que resuelvan a direcciones internas (mitigación SSRF).
- Las credenciales de los conectores se cifran en reposo y no vuelven a mostrarse tras guardarlas.

## Desarrollo local

```bash
docker compose up -d postgres

# Backend
cd backend
python -m venv .venv && .venv\Scripts\activate     # Windows; source .venv/bin/activate en Linux/macOS
pip install -r requirements.txt
cp .env.example .env                               # aquí DATABASE_URL apunta a localhost
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Frontend (otra terminal)
cd frontend-modern
npm install
npm run dev                                         # http://127.0.0.1:5173
```

Ejecutar tests: `cd backend && python -m pytest -q` · Comprobación de build del frontend: `cd frontend-modern && npm run build`.

Las tools de navegador requieren además `pip install playwright && playwright install chromium`.

## Estructura del proyecto

```text
backend/            App FastAPI: bucle de agente, tools, skills, MCP, conectores, plugins, tareas, monitorización
  app/admin/        API de administración: un módulo por dominio (providers, models, agents, skills, mcps, workflows, plugins, users, audit, traces, settings, monitoring)
  app/chat/         Chat: conversations, specs (ensamblado de agentes), streaming, approvals, attachments
frontend-modern/    UI React + TypeScript + Vite (src/views por pantalla, src/components, src/state, src/lib, src/types)
agents/skills/      Agent Skills (estándar SKILL.md)
plugins/            Catálogo local de plugins
database/schema.sql Esquema PostgreSQL completo (las migraciones Alembic son la fuente de verdad)
scripts/            Herramientas de release
```

## Publicación de releases

Este repositorio se publica desde un repo privado de desarrollo como snapshots versionados:

```powershell
# desde el checkout de desarrollo
.\scripts\publish-public.ps1 -Version 0.1.2 -Notes "notas del release"
```

## Licencia

MIT — ver [LICENSE](LICENSE).
