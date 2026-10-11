<p class="os-kicker" markdown>Empezar</p>
# Proveedores de LLM

ObsyGPT se conecta a **cualquier modelo** a través de proveedores: OpenRouter, OpenAI, Anthropic, Gemini, Ollama, llama.cpp o cualquier endpoint compatible con la API de OpenAI (routers como OmniRoute, Groq, DeepSeek, vLLM...). Regístralos en **Ajustes > Modelo > Proveedores** y actívalos para tus agentes.

## Cómo funciona

Un proveedor en ObsyGPT tiene tres piezas:

| Campo | Qué es | Ejemplo |
|---|---|---|
| Nombre | Etiqueta para identificarlo | `OpenRouter principal` |
| Base URL | Endpoint del API (vacío = URL por defecto del tipo) | `https://openrouter.ai/api/v1` |
| API key | La clave, **pegada en el panel** (opcional) o vía variable de entorno | — |

!!! success "Claves en el panel, cifradas en reposo"
    Puedes pegar la API key directamente en **Ajustes > Modelo > Proveedores**: se guarda **cifrada con Fernet** (clave derivada de `SESSION_SECRET` o `CONNECTOR_ENCRYPTION_KEY`), nunca se vuelve a mostrar en la UI ni se devuelve por la API. La fila muestra una etiqueta **«Clave guardada»** y un botón para reemplazarla.

!!! note "Alternativa por variable de entorno"
    También puedes dejar la clave fuera de la base de datos: la UI acepta el *nombre* de una variable de entorno (`api_key_env`, p. ej. `OPENROUTER_API_KEY`) y el backend la lee de su entorno (`.env`). Si hay clave guardada en el panel, **tiene prioridad** sobre la variable de entorno. Útil para despliegues gestionados con secret managers.

## Pasos generales

1. **Ajustes > Modelo > Proveedores > Añadir provider**: nombre, tipo, API key pegada en el panel (o variable de entorno), y Base URL solo si no usas la de por defecto.
2. Marca **Enabled** y pulsa **Detectar modelos** — ObsyGPT consulta el endpoint de modelos del proveedor y te lista los disponibles.
3. Activa los modelos que quieras en **Ajustes > Modelo > Modelos**.
4. Selecciónalos como modelo activo o asígnalos a un agente concreto (ver [Agentes](agentes.md)).

![Proveedores](assets/screenshots/settings-modelo.png)

## Proveedores soportados

| Proveedor | Tipo | Base URL por defecto | Variable de clave | Capacidades |
|---|---|---|---|---|
| OpenRouter | `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | Visión, tools, JSON |
| OpenAI | `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | Visión, audio, tools, JSON |
| Anthropic | `anthropic` | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` | Visión, tools |
| Gemini | `gemini` | `https://generativelanguage.googleapis.com` | `GEMINI_API_KEY` | Visión, audio, tools, JSON |
| Ollama | `ollama` | `http://127.0.0.1:11434/v1` | (sin clave) | Visión, JSON |
| llama.cpp | `llamacpp` | `http://127.0.0.1:8080/v1` | (sin clave) | JSON |
| OpenAI-compatible | `openai_compatible` | (obligatoria) | opcional | Visión, tools, JSON |

## OpenRouter

Un solo contrato para cientos de modelos (GPT, Claude, Gemini, Llama, Mistral...). Ideal para empezar rápido y usar fallbacks entre proveedores.

1. Crea la clave en [openrouter.ai/keys](https://openrouter.ai/keys) y pégala en el panel (o defínela en `.env` como `OPENROUTER_API_KEY`).
2. Registra el proveedor con tipo `openrouter` — la Base URL por defecto ya es correcta, puedes dejarla vacía.
3. **Detectar modelos** y activa los que uses.

Con OpenRouter tienes acceso a los modelos más capaces para [sub-agentes](chat.md#sub-agentes) y [workflows](agentes.md#fallbacks) sin gestionar varias cuentas.

## OpenAI

1. Clave en [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → pégala en el panel o en `.env` como `OPENAI_API_KEY`.
2. Registra el proveedor con tipo `openai` — Base URL por defecto `https://api.openai.com/v1`, déjala vacía.
3. Detecta modelos y activa (`gpt-4o`, `gpt-4o-mini`...).

Soporta **audio** y **visión**: es la mejor opción si quieres pruebas de [voz](voz.md) multimodal completas.

## Anthropic

1. Clave en [console.anthropic.com](https://console.anthropic.com) → pégala en el panel o en `.env` como `ANTHROPIC_API_KEY`.
2. Registra el proveedor con tipo `anthropic` — Base URL por defecto `https://api.anthropic.com`.
3. Detecta modelos y activa (`claude-sonnet-4-5`, `claude-opus-4-1`...).

## Gemini

1. Clave en [Google AI Studio](https://aistudio.google.com/apikey) → pégala en el panel o en `.env` como `GEMINI_API_KEY`.
2. Registra el proveedor con tipo `gemini` — Base URL por defecto `https://generativelanguage.googleapis.com`.
3. Detecta modelos y activa (`gemini-2.5-pro`, `gemini-2.5-flash`...).

## Ollama y llama.cpp (locales)

100% locales, sin clave. **Ojo con la URL según instalación**: con Docker, `127.0.0.1` dentro del contenedor no es tu máquina — usa `http://host.docker.internal:11434/v1` (Ollama) o `http://host.docker.internal:8080/v1` (llama.cpp). Detalles completos en [Modelos locales](modelos-locales.md).

## Otros routers y endpoints (OpenAI-compatible)

Cualquier servicio que hable la API de OpenAI se conecta con el tipo `openai_compatible`: OmniRoute, Groq, DeepSeek, Together AI, Mistral, Fireworks, OpenAI local (vLLM, LiteLLM, LM Studio...).

1. Registra el proveedor con tipo **OpenAI-compatible** y la **Base URL del servicio** (normalmente `https://<dominio>/v1`).
2. Si el servicio requiere clave, pégala en el panel o ponla en `.env` con un nombre propio (por ejemplo `OMNIROUTE_API_KEY`) y escribe ese nombre en *API key env var*.
3. **Detectar modelos** — si el servicio expone `/models`, se rellenan solos; si no, crea el modelo a mano en **Ajustes > Modelo > Modelos**.

!!! tip "Base URL casi siempre termina en `/v1`"
    Los servicios compatibles con OpenAI exponen `.../v1/chat/completions`. Si la detección falla, revisa que la Base URL incluya el `/v1` final.

!!! note "Instalación Docker + endpoint en tu máquina"
    Si el router corre en tu propia máquina, aplica la misma regla que los modelos locales: `http://host.docker.internal:<puerto>/v1` desde contenedores. Ver [Modelos locales](modelos-locales.md#instalacion-docker-quickstart).

## Fallbacks entre proveedores

En **Ajustes > Agentes > edita un agente > Fallbacks** encadena modelos de distintos proveedores por prioridad: si el principal falla (caída, rate limit), ObsyGPT reintenta con el siguiente. Ejemplo: OpenRouter → OpenAI → Ollama local. Los activaciones se muestran en [Monitorización](monitoreo.md).

## Embeddings

La [memoria semántica](memoria.md#embeddings) también acepta un endpoint compatible con OpenAI en **Ajustes > Modelo > Embeddings**, o el modelo local por defecto (sin salidas de red).
