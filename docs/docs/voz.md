<p class="os-kicker" markdown>Automatizar</p>
# Voz

ObsyGPT habla y escucha, y **todo el procesamiento de voz es local**: ni la transcripción ni la síntesis salen de tu infraestructura.

## Hablar con el agente (STT)

En el composer, mantén pulsado el **micrófono** (push-to-talk): tu nota de voz se transcribe con **faster-whisper** y se envía como texto al agente.

## Respuestas habladas (TTS)

Pulsa el **altavoz** en cualquier respuesta: ObsyGPT la sintetiza con **Piper** (voz en español) y te la reproduce. El Markdown se limpia antes de sintetizar para que no escuches asteriscos ni cabeceras.

## Configuración (opcional)

Todas las variables tienen valores por defecto sensatos:

| Variable | Por defecto | Descripción |
|---|---|---|
| `VOICE_STT_MODEL` | `medium` | Modelo de Whisper (`small` más rápido, `large-v3` más preciso pero lento en CPU) |
| `VOICE_STT_LANGUAGE` | `es` | Idioma de transcripción |
| `VOICE_TTS_VOICE` | `es_ES-sharvard-medium` | Voz de Piper |
| `VOICE_LENGTH_SCALE` / `VOICE_NOISE_SCALE` / `VOICE_NOISE_W_SCALE` | — | Ritmo y variación de la voz |

Los modelos de Whisper y la voz de Piper se descargan **una sola vez** al arrancar (volumen `obsygpt_voice_data`) y el backend los calienta en segundo plano.

En Telegram el ciclo completo es automático: le envías un audio, recibes un audio de vuelta.
