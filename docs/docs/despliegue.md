<p class="os-kicker" markdown>Empezar</p>
# Despliegue en tu servidor

ObsyGPT es **self-hosted**: la app entera corre en contenedores Docker que vos controlás. Esta guía cubre el despliegue con **Dokploy** (o cualquier VPS con Docker Compose) y los casos reales: dominio propio, modelo local en otra máquina y el MCP de Google Flow.

## Requisitos

- Un VPS con Docker: **2 vCPU / 4 GB** como mínimo (8 GB si vas a usar voz — los modelos STT/TTS cargan en memoria).
- Un dominio apuntando al VPS.
- Dokploy instalado (o Docker Compose directamente; el mismo `docker-compose.yml` funciona).

## 1. Crear el servicio en Dokploy

1. Dokploy → tu proyecto → **Create Service → Compose**.
2. Provider **GitHub**, repo `ObsyGPT`, branch `main`, compose path `docker-compose.yml`.
3. Recomendado: editá el compose desde la UI y **borrá los bloques `ports` de `postgres` y `backend`**. En un servidor nadie debe alcanzar esos puertos desde Internet: todo el tráfico entra por el frontend, y su nginx ya hace proxy interno de `/api`, `/v1` y `/docs` al backend.

## 2. Variables de entorno

En la pestaña **Environment** del servicio:

| Variable | Valor |
|---|---|
| `POSTGRES_PASSWORD` | contraseña fuerte (`openssl rand -hex 24`) |
| `SESSION_SECRET` | `openssl rand -hex 32` |
| `OBSYGPT_REQUIRE_STRONG_SECRETS` | `1` — rechaza arrancar con secretos débiles |
| `FRONTEND_URL` | `https://tu-dominio.com` (cookies y CORS) |
| `VITE_BACKEND_URL` | **no la definas** — la app usa same-origin por defecto |
| `OPENROUTER_API_KEY` / `OPENAI_API_KEY` / ... | opcionales: también podés cargarlas después desde el panel (quedan cifradas en la base) |

!!! note "Same-origin"
    El nginx del frontend proxifica `/api` y `/v1` al backend. El navegador nunca necesita conocer otro origen: no expongas el puerto 8000 y no definas `VITE_BACKEND_URL` salvo que el backend viva en un dominio distinto.

## 3. Dominio

En el servicio → **Domains** → dominio `tu-dominio.com` → servicio `frontend`, puerto **80**. Dokploy gestiona el certificado HTTPS automáticamente. Backend y PostgreSQL quedan solo en la red interna.

## 4. Primer acceso

1. Abrí `https://tu-dominio.com` y registrá el primer usuario: **el primero de una base vacía se convierte en admin** (después el registro se cierra; solo admins crean cuentas).
2. Desde **Ajustes**: cargá claves de proveedores, activá modelos y creá tus agentes.

Las migraciones de base de datos se aplican solas al arrancar el backend. Los volúmenes (`postgres_data`, `workspace`, `uploads`, `voice_data`) persisten entre redeploys.

## 5. Telegram (opcional)

Con el dominio público ya funciona: en **Ajustes > Agentes > edita un agente > Telegram** pegá el token del bot y tu allowlist. Las aprobaciones sensibles llegan como botones al chat. Detalles en [Telegram](telegram.md).

## 6. MCP de Google Flow (opcional)

El servicio `flow-mcp` (generación de imágenes con Google Flow) está en un **profile aparte** del compose: no arranca ni se registra por defecto, porque requiere un **login de Google humano** por navegador.

1. Environment de Dokploy:
    - `COMPOSE_PROFILES=flow`
    - `FLOW_MCP_URL=http://flow-mcp:8808`
2. Redeploy: el backend registra el servidor "Google Flow" al arrancar.
3. Verificá que el contenedor publicó noVNC **solo en loopback** (en el compose):
    ```yaml
        ports:
          - "127.0.0.1:6901:6901"
    ```
    Publicarlo en `0.0.0.0` deja tu sesión de Google al alcance de cualquiera con la IP.
4. Login de Google (una sola vez), por túnel SSH desde tu máquina:
    ```bash
    ssh -L 6901:127.0.0.1:6901 ubuntu@tu-vps
    ```
    y abrí `http://localhost:6901` (o `/vnc.html` si la raíz se ve en blanco). La sesión persiste en el volumen `obsygpt_flow_profile`; cuando termine el login podés quitar el puerto del compose.
5. Panel → **MCPs** → asigná "Google Flow" al agente que lo vaya a usar.

## 7. Modelo local en otro servidor (llama.cpp, Ollama, ...)

Si tu LLM corre en otra máquina, el backend del contenedor la alcanza por su **IP pública**, nunca por `localhost`:

1. En el servidor del modelo, exponé el servicio en todas las interfaces:
    - llama.cpp: `llama-server -m modelo.gguf --host 0.0.0.0 --port 8080 -c 16384 --api-key CLAVE_SEGURA`
    - Ollama: `OLLAMA_HOST=0.0.0.0` (y reiniciá el servicio)
2. Firewalls: permití el puerto **solo desde la IP del VPS de ObsyGPT** (`sudo ufw allow from IP_OBSYGPT to any port 8080 proto tcp`). Un servidor de inferencia abierto sin API key es un servicio gratis para cualquiera.
3. Panel → **Proveedores**: base URL `http://IP_DEL_MODELO:8080/v1`, la API key de `--api-key` (si no hay, un valor dummy: el cliente exige algo no vacío), y el nombre exacto del modelo según `/v1/models`.
4. Alineá los contextos: el `context_window` del modelo en el panel debe coincidir con `-c` (llama.cpp) o `num_ctx` (Ollama), o el modelo truncará el prompt en silencio.

## 8. Actualizaciones

Cada push a `main` → **Redeploy** en Dokploy (o configurá auto-deploy con webhook). Los datos persisten y las migraciones nuevas aplican solas al arrancar.

## Diagnóstico rápido

!!! warning "El mensaje de la UI es genérico"
    "Network error" o "Cannot reach backend" en el chat casi nunca dicen la causa real: mirá siempre los **logs del backend** (`docker logs` en Dokploy) — ahí está el traceback de verdad.

- **"Cannot reach backend at ...:8000"** → versión anterior a v0.7.4 o `VITE_BACKEND_URL` definida con otro origen. Actualizá y borrala del environment.
- **Chat con 500 y traceback `OpenRouter requires an API key`** → versión anterior a v0.7.5. Actualizá.
- **"Connection refused" hacia tu modelo local** → el servidor de inferencia está en loopback (`--host 0.0.0.0` / `OLLAMA_HOST=0.0.0.0`) o el firewall rechaza.
- **Timeout hacia tu modelo local** → el firewall descarta paquetes; revisá también el firewall del proveedor de la nube.
- **noVNC no abre por el túnel** → verificá en el VPS: contenedor corriendo (`docker ps | grep flow`), puerto publicado (`ss -tlnp | grep 6901`) y respuesta local (`curl -sI http://localhost:6901`). Si el host responde y tu máquina no, el túnel no está vivo o el navegador fue a `https://`.
