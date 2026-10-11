<p class="os-kicker" markdown>Operación</p>
# API compatible con OpenAI

ObsyGPT expone tus agentes como si fueran modelos de OpenAI: cualquier herramienta compatible con la API (IDEs, n8n, LibreChat, scripts) puede conversar con ellos.

## Crear una API key

**Ajustes > Seguridad > Claves de API**:

1. Genera una clave personal (`ogpt-...`).
2. **Se muestra una sola vez** al crearla — guárdala en tu gestor de secretos.
3. Revócala cuando quieras desde la misma pantalla.

## Endpoints

```bash
# 1) Lista tus agentes como modelos
curl -H "Authorization: Bearer ogpt-..." http://localhost:3001/v1/models

# 2) Conversa con un agente (por nombre o agent-{id})
curl -H "Authorization: Bearer ogpt-..." -H "Content-Type: application/json" \
  -d '{"model": "Code Reviewer", "messages": [{"role": "user", "content": "Hola"}]}' \
  http://localhost:3001/v1/chat/completions

# Streaming SSE estilo OpenAI
-d '{"model": "Code Reviewer", "stream": true, "messages": [...]}'
```

## Reglas del endpoint

| Aspecto | Comportamiento |
|---|---|
| `model` | Resuelve el agente por nombre (insensible a mayúsculas) o `agent-{id}` |
| Estado | **Stateless**: no crea conversaciones, pero cada llamada queda trazada |
| Tools | Solo ejecuta **tools seguras** — nunca genera aprobaciones pendientes |
| Memoria | Los agentes conservan su system prompt y memoria |
| Streaming | SSE con deltas estilo OpenAI |

## Notas de migración

Instalaciones existentes: esta funcionalidad llegó con la migración `0023_api_keys_openai_endpoint`. Al actualizar:

```bash
docker compose build && docker compose up -d
docker compose exec backend alembic upgrade head
```
