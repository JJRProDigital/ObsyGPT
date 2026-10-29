<p class="os-kicker" markdown>Trabajar</p>
# Proyectos

Un **proyecto** agrupa chats, tareas, archivos, instrucciones y memoria en un solo contexto. Úsalo para aislar el trabajo por cliente, producto o iniciativa.

## Qué incluye un proyecto

| Pestaña | Contenido |
|---|---|
| Chats | Conversaciones asociadas al proyecto |
| Tareas | Tareas en segundo plano con contexto del proyecto |
| Conocimiento | Documentos y archivos que el agente consulta |
| Instrucciones | Reglas y objetivos específicos inyectados al agente |
| Memoria | Recuerdos propios del proyecto |
| Archivos | La carpeta física del proyecto dentro del workspace |

## Crear un proyecto

En la vista **Proyectos**, pulsa **Nuevo proyecto**, define nombre y descripción, y (opcional) una carpeta del workspace. Al abrir un proyecto, sus instrucciones y memoria se inyectan automáticamente en cada conversación y tarea que corras dentro.

## Cómo lo usan los agentes

- **Instrucciones de proyecto**: anteponen contexto estable ("somos la agencia X, tono formal...") sin duplicarlo en cada chat.
- **Memoria de proyecto**: recuerdos indexados con pgvector, recuperados semánticamente durante el chat.
- **Archivos**: las tools de lectura/escritura pueden trabajar dentro de la carpeta del proyecto.

## Buenas prácticas

- Un proyecto por cliente o initiative — evita mezclar instrucciones contradictorias.
- Pon en *Instrucciones* solo lo estable; lo cambiante, mejor en la memoria o en los archivos.
- Usa *Conocimiento* para material de referencia de larga vida (PDFs, notas, especificaciones).
