---
name: summarize_document
description: Summarize extracted document content.
argument-hint: Texto extraido, documento adjunto o seleccion de contenido.
triggers: ["user", "model"]
---

# Instrucciones principales
1. Identifica objetivo, audiencia y extension deseada del resumen.
2. Resume tesis principal, puntos clave, decisiones, riesgos y siguientes pasos.
3. Mantiene la terminologia del documento original.
4. Incluye una seccion de dudas o informacion faltante si aplica.

## Restricciones
* No cambies el sentido del documento.
* No anadas conclusiones que no esten respaldadas por el contenido.
* No ocultes contradicciones o limitaciones importantes.

## Recursos opcionales
templates/document-summary.md
