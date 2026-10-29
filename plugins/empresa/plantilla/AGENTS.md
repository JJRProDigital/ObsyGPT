# Instrucciones del proyecto: Empresa

Este proyecto redacta emails, presupuestos y contenido con la voz de la empresa. El agente propone; una persona aprueba y envía.

## Antes de cualquier tarea

- Lee `empresa/voz-y-estilo.md`, `empresa/reglas-duras.md` y `empresa/errores-vistos.md`.
- Las reglas duras están por encima de cualquier pedido.
- Los precios, plazos y condiciones salen únicamente de `datos-maestros/`. Si falta un dato, pregunta; nunca lo inventa.

## Flujo

1. `/empresa-brief <tipo> <encargo>` escribe el brief en `trabajos/<slug>/brief.md`.
2. Una persona resuelve las Preguntas abiertas y cambia a mano `estado: borrador` por `estado: aprobado`, con `aprobado_por` y fecha.
3. `/empresa-redactar <slug>` escribe `borrador.md`.
4. `/empresa-revisar <slug>` revisa el borrador contra el brief, las reglas y la checklist del tipo.
5. Una persona lee, ajusta y envía.

## Límites

- Solo se redacta desde briefs con `estado: aprobado`.
- Todo borrador queda como «pendiente de revisión humana».
- El agente nunca envía ni publica nada.
- Cada tipo sigue su guía en `tipos/<tipo>/guia.md` e imita los ejemplos de `ejemplos/<tipo>/`.
- Cada corrección humana repetida se anota en `empresa/errores-vistos.md`.
