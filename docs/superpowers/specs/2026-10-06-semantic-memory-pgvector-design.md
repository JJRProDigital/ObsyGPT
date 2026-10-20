# Diseño: Memoria semántica con pgvector

Fecha: 2026-10-06
Estado: Aprobado (pendiente de plan de implementación)

## Objetivo

Dotar a ObsyGPT de memoria semántica: que los agentes recuperen por relevancia (no por inyección fija) los recuerdos del usuario y el historial de conversaciones pasadas. Alcance v1: memorias manuales + mensajes históricos. Los archivos del workspace quedan fuera de esta fase y se añadirán después reutilizando el mismo índice.

## Decisiones (validadas con el usuario)

1. **Alcance**: memorias + conversaciones pasadas (opción B). Workspace fuera de v1.
2. **Modelo de embeddings**: híbrido configurable (opción C). Por defecto local (`fastembed` con modelo multilingüe); opcionalmente un endpoint OpenAI-compatible configurado en Ajustes.
3. **Acceso**: ambos mecanismos (opción C) — inyección automática de top-k sobre umbral + tool explícita `memory_search`.

## Arquitectura

Módulo nuevo `backend/app/memory/semantic/` con tres unidades de responsabilidad única:

### `embeddings.py` — EmbeddingService

- **Modo local (por defecto)**: `fastembed` con `intfloat/multilingual-e5-small` (384 dimensiones, multilingüe — las conversaciones de ObsyGPT son en español). El modelo se descarga una vez a un volumen persistente, siguiendo el patrón existente de voz (faster-whisper / Piper).
- **Modo endpoint**: `POST {base_url}/embeddings` con formato OpenAI-compatible (body `{"model", "input"}`), configurado en Ajustes > Modelo.
- Interfaz: `embed_texts(texts: list[str]) -> list[list[float]]` y `embed_one(text: str) -> list[float]`. Expone `model_id()` para versionado del índice y `dimension()` (debe coincidir con la columna `vector(N)`; si el endpoint configurado devuelve otra dimensión, el indexado se rechaza con error claro en el log y en el test de configuración).
- Carga perezosa del modelo local en un singleton por proceso; warm-up en background al arrancar (mismo patrón que el calentamiento de voz).

### `indexer.py` — Indexado en background

- Gancho: en `chat_conversations.save_message` (punto único por el que pasan chat web, Telegram y tareas en segundo plano) y tras `create_memory` / edición de memorias.
- Mecanismo: cola en memoria + thread daemon (mismo patrón que `learn_habits_in_background`). Nunca bloquea el camino crítico del chat.
- Troceado: 1 chunk por mensaje si ≤800 caracteres; si excede, división por párrafos con solapamiento mínimo. Cada chunk guarda `user_id`, `conversation_id`, `message_id`, `project_id` (nullable), texto del chunk, `model`.
- Memorias manuales: se actualiza la columna `embedding` de la fila al crear/editar; al borrar, el índice no deja residuo (el vector vive en la misma fila).
- Idempotencia: si un mensaje ya tiene embeddings con el `model` vigente, no se re-embeddea.

### `retrieval.py` — Búsqueda

- `search_semantic(user_id, query, project_id=None, k=5, threshold=0.35) -> list[Hit]` con similitud coseno (operador `<=>` de pgvector).
- Consulta con índice **HNSW** (`vector_cosine_ops`) filtrando por `user_id` siempre (aislamiento por usuario) y por `project_id` cuando la conversación pertenece a un proyecto.
- Dos fuentes combinadas en una sola respuesta: recuerdos (`memories.embedding`) y fragmentos de conversaciones (`message_embeddings`), etiquetados por origen con conversación y fecha.
- Umbral configurable por constante (default 0.35, ajustable tras pruebas reales) para evitar ruido en la inyección.

## Datos y migración (Alembic)

- **Docker**: la imagen de Postgres cambia a `pgvector/pgvector:pg16` en `docker-compose.yml` (único cambio de infraestructura). En desarrollo local se requiere la extensión instalada.
- Migración: `CREATE EXTENSION IF NOT EXISTS vector;`
- Tabla nueva:

```sql
CREATE TABLE message_embeddings (
    id BIGSERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id INT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_id INT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    project_id INT REFERENCES projects(id) ON DELETE SET NULL,
    chunk TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    model TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_message_embeddings_hnsw ON message_embeddings
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_message_embeddings_user ON message_embeddings (user_id);
```

- Columnas añadidas a `memories`: `embedding vector(384)` (nullable) y `model TEXT`.
- `database/schema.sql` se actualiza en el mismo cambio (las migraciones Alembic siguen siendo la fuente de verdad).

## Flujo de lectura

1. En `backend/app/chat/routes.py` (`stream_message`), junto al bloque actual de `build_memory_context` (~línea 101), se llama a `search_semantic(user_id, user_message, project_id)`.
2. Si hay resultados sobre el umbral, se añade un mensaje de contexto "Recuerdos relevantes" (top 5, formato: texto + origen `[conversación, fecha]`), y se registra el evento de traza `semantic_memory_loaded` (mismo estilo que `memory_loaded`).
3. Si no hay resultados o el servicio de embeddings no está disponible, no se añade nada: el chat funciona exactamente como hoy.

### Tool `memory_search`

- Registro en `build_agent_tool_registry` (permiso `safe`; habilitable por agente como el resto).
- Spec: `memory_search(query: str, k: int = 5)` — "busca en la memoria persistente del usuario (recuerdos y conversaciones pasadas) fragmentos relevantes".
- Salida: lista numerada de fragmentos con origen (conversación, fecha) para que el agente pueda citar o profundizar.
- Cada invocación queda trazada como cualquier tool.

## Degradación y errores

- Embeddings no disponible (modelo no descargado, endpoint caído, dimensión incorrecta): el indexado se salta con log de aviso; la inyección automática se omite; la tool `memory_search` devuelve un mensaje de servicio no disponible. **Ninguna ruta crítica depende del servicio.**
- Fallo al insertar en la cola: se descarta el chunk con log (la memoria semántica es best-effort; el texto original sigue en `messages`).
- Reintentos: no hay. El reindexado manual cubre lagunas.

## UI y reindexado

- Ajustes > Modelo > nueva sección **Embeddings**: modo (`local` / `endpoint`), campos `base_url`, `model`, `api_key` (solo modo endpoint), y botón **Reindexar**.
- **Reindexar**: lanza job en background que re-embeddea memorias + mensajes con el modelo vigente (detecta cambios por columna `model`); progreso visible como estado simple (en curso / completado con contadores). Útil tras cambiar de modelo o si el servicio estuvo caído.
- Sin UI adicional sobre resultados en v1 (la MemoryView actual sigue igual).

## Testing

- **Unit**: troceado de mensajes largos; `search_semantic` con embedder fake (umbral, orden, aislamiento por usuario/proyecto); formato de salida de la tool `memory_search`; `EmbeddingService` en modo endpoint con HTTP fake.
- **Integración**: guardar mensaje → indexar (thread) → buscar → inyección en `stream_message`; degradación cuando el embedder falla (chat sigue funcionando).
- **Migración**: la extensión `vector` y las tablas/columnas quedan aplicadas desde cero.

## Fuera de alcance (v1)

- Indexado de archivos del workspace (extensión futura del mismo índice).
- Búsqueda híbrida léxica+semántica (RRF); si la relevancia pura se queda corta, se añadirá sobre `messages` con FTS5-equivalente Postgres.
- Resúmenes por conversación como unidades de índice.
