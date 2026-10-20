# Diseño: Endpoint OpenAI-compatible (/v1)

Fecha: 2026-10-07
Estado: Aprobado (implementación inmediata)

## Objetivo

Exponer los agentes de ObsyGPT como modelos OpenAI-compatible en `POST /v1/chat/completions` y `GET /v1/models`, para que herramientas externas (IDEs, n8n, LibreChat, scripts) conversen con los agentes usando su system prompt, memoria y herramientas — convirtiendo a ObsyGPT en infraestructura y no solo cliente.

## Decisiones (validadas con el usuario)

1. **Auth**: API keys personales por usuario (`ogpt-...`, revocables, hash SHA-256, mostradas una sola vez).
2. **Tools**: por API los agentes se filtran a solo tools `safe` (las `sensitive` se saltan con `tool_skipped`; nunca hay aprobaciones pendientes de clientes externos).
3. **Persistencia**: llamadas stateless — sin conversación ni mensajes en el chat, pero cada llamada crea su `agent_run` trazable en la vista Trace. El agente usa la memoria del usuario pero no la alimenta.
4. **Streaming**: soporte de `stream=true` (SSE formato delta de OpenAI) y `stream=false`. Agentes agénticos emiten por iteración (ráfagas); no-agenticos fluido.

## Superficie de API

### `POST /v1/chat/completions`

- Body: `{"model": "<nombre del agente | agent-{id}>", "messages": [{"role": "user|assistant|system", "content": "..."}], "temperature": 0.7 (opcional), "stream": false (opcional)}`.
- Respuesta no-streaming: shape OpenAI (`id: "chatcmpl-..."`, `object: "chat.completion"`, `created`, `model`, `choices[0].{message: {role: "assistant", content}, finish_reason: "stop"}`, `usage` estimado: chars/4, documentado como aproximación).
- Respuesta streaming: SSE `data: {chunk}\n\n` con `delta.content`, cierre `data: [DONE]`.
- Errores en formato OpenAI: `{"error": {"message", "type", "code"}}` — 401 (key inválida/revocada/ausente), 404 (agente desconocido/deshabilitado), 400 (request malformado), 429 (rate limit).

### `GET /v1/models`

- Lista los agentes habilitados: `{"object": "list", "data": [{"id": "agent-6", "object": "model", "owned_by": "obsygpt"}, ...]}`.
- `model` en chat/completions resuelve por nombre del agente (insensible a mayúsculas) o por `agent-{id}`.

### Auth

- Header `Authorization: Bearer <key>`; 401 inmediato si falta/inválida/revocada.
- Cada uso actualiza `last_used_at` (best-effort).
- Rate limit por key reusando el patrón `AuthRateLimiter` de auth.

## API keys (migración 0023)

```sql
CREATE TABLE api_keys (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash TEXT NOT NULL UNIQUE,      -- SHA-256 hex de la key completa
    prefix TEXT NOT NULL,               -- 8 chars visibles para identificarla
    name TEXT NOT NULL,                 -- etiqueta elegida por el usuario
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX idx_api_keys_user ON api_keys (user_id);
```

- Generación: `ogpt-` + `secrets.token_urlsafe(32)`; se devuelve en claro **solo una vez** en la respuesta de creación.
- Migración adicional: `ALTER TABLE agent_runs ALTER COLUMN conversation_id DROP NOT NULL;` y `ALTER TABLE agent_runs ALTER COLUMN message_id DROP NOT NULL;` para trazabilidad de runs stateless. (`TraceStore.create_run` se adapta a aceptar None.)

## Flujo de `chat/completions`

1. Auth → `user_id`.
2. Resolver agente por `model` (habilitados solamente) → 404 si no existe.
3. Mensajes: system prompt del agente + mensajes del cliente (mapeo directo de roles) + los mismos bloques de contexto del chat: `build_user_instructions_block`, `build_memory_context`, `build_semantic_context_block` (sin `exclude_conversation_id` — no hay conversación).
4. Ejecución:
   - **Agentic**: `AgentRuntime` con el registro de tools filtrado a `safe` (`filter_to` con los nombres safe del catálogo del agente; las sensibles quedan fuera y cualquier intento del modelo produce `tool_skipped`).
   - **No-agentic**: llamada directa con fallbacks reutilizando el camino de `WorkflowRuntime._run_agent`.
5. Guardrails existentes (iteraciones, caps) aplican sin cambios.
6. Respuesta OpenAI-shape; streaming según `stream`.

## Degradación y errores

- Fallo del proveedor → fallbacks del agente (existente) → error OpenAI-shape 502 si todo falla.
- Key revocada a mitad de uso: la próxima llamada falla 401.
- Ninguna llamada API puede generar aprobaciones pendientes (tools sensibles filtradas de raíz).

## UI

Ajustes > Seguridad > nueva sección **"Claves de API"**: formulario crear (nombre) → muestra la key una vez con botón copiar; lista de keys con prefijo, nombre, último uso, botón revocar (con confirmación). Solo admins ven la sección (las keys son por usuario pero la gestión de agentes ya es admin; las keys se crean por usuario — el listado muestra solo las del usuario logueado).

## Nginx

`frontend/nginx.conf`: añadir `location /v1/` con el mismo proxy que `/api` (timeouts largos para streaming).

## Testing

- **Unit**: generación/hash de keys (key válida, revocada, inexistente); resolución de agentes (nombre, agent-{id}, deshabilitado → 404); filtro safe-only (tool sensible → `tool_skipped`, nunca ApprovalRequired); shape de respuesta y errores OpenAI; usage estimado.
- **Integración**: POST no-streaming con runtime fake; streaming SSE con chunks y `[DONE]`; 401/404/429 paths.
- **Migración**: nullable columns + tabla api_keys.

## Fuera de alcance (v1)

- Endpoint `/v1/completions` (legacy), embeddings de OpenAI (`/v1/embeddings`), usage exacto por tokens, persistencia opt-in de llamadas API, cuotas por key.
