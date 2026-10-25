<p class="os-kicker" markdown>Empezar</p>
# Modelos locales

ObsyGPT funciona muy bien con modelos 100% locales (llama.cpp u Ollama): tus conversaciones nunca salen de tu máquina. Las URLs cambian según cómo lo ejecutes.

## Instalación Docker (quickstart)

El backend corre en un contenedor, donde `127.0.0.1` es **el propio contenedor**, no tu máquina. Apunta el proveedor a tu host:

1. Arranca el servidor escuchando en todas las interfaces:
   - **llama.cpp**: `llama-server --host 0.0.0.0 --port 8080 ...` (por defecto escucha en `127.0.0.1`, inalcanzable desde el contenedor)
   - **Ollama**: escucha en `0.0.0.0` por defecto (`OLLAMA_HOST=0.0.0.0` si lo cambiaste)
2. En la UI: **Ajustes > Modelo > Proveedores guardados**, registra el proveedor con la URL base:
   - llama.cpp: `http://host.docker.internal:8080/v1`
   - Ollama: `http://host.docker.internal:11434/v1`
3. Pulsa **Detectar modelos** y activa el que quieras para tu agente.

!!! note "host.docker.internal"
    Resuelve dentro de los contenedores en Windows/macOS sin configurar nada. En Linux funciona gracias a la entrada `extra_hosts: host-gateway` ya incluida en `docker-compose.yml`.

## Instalación de desarrollo local

Si el backend corre directamente en tu máquina (uvicorn), usa las URLs locales normales:

- llama.cpp: `http://127.0.0.1:8080/v1`
- Ollama: `http://127.0.0.1:11434/v1`

## Embeddings locales

Por defecto, la memoria semántica usa **fastembed** local (sin llamadas de red). Puedes apuntar a un endpoint compatible con OpenAI en **Ajustes > Modelo > Embeddings** — ver [Memoria](memoria.md#embeddings).
