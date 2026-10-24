<p class="os-kicker" markdown>Automatizar</p>
# Telegram

Cada agente puede tener **su propio bot de Telegram**: le escribes desde el móvil y el mensaje se convierte en una **tarea en segundo plano** del agente, con sus tools, aprobaciones y trazas.

## Configurar el bot

1. Crea un bot con [@BotFather](https://t.me/BotFather) y copia el token.
2. Consigue tu ID numérica con `@userinfobot`.
3. En la UI: **Ajustes > Agentes > edita un agente > Telegram**:
   - Pega el token (se cifra en reposo).
   - Añade la allowlist con el formato `<telegram_id>:<usuario_obsygpt>` — mapea cada cuenta de Telegram a una cuenta de ObsyGPT (dueño de las tareas).
   - Pulsa **Probar token** para verificar el bot.
   - Activa el canal.

## Qué puedes hacer desde el chat

- **Tareas autónomas**: "resume las novedades de IA y guárdalas en una nota" — el agente trabaja en segundo plano.
- **Aprobaciones inline**: las tools sensibles pausan la tarea y llegan como botones **Aprobar / Rechazar**.
- **Notas de voz en ambas direcciones**: le envías un audio, se transcribe con Whisper local; la respuesta te llega sintetizada con Piper.

## Seguridad

- Solo los IDs de la allowlist pueden usar cada bot — los mensajes de desconocidos se **ignoran en silencio**.
- Los tokens se cifran en reposo; el tráfico de voz nunca sale de tu infraestructura (salvo la descarga inicial de modelos desde HuggingFace).
- Un token de bot solo admite un consumidor: si estaba registrado en otra herramienta con webhook, el gateway lo libera automáticamente.
