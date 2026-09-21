---
name: extract_pdf
description: Extract text and metadata from uploaded PDFs.
argument-hint: PDF adjunto o referencia a un archivo ya subido.
triggers: ["user"]
---

# Instrucciones principales
1. Identifica el PDF adjunto que el usuario quiere procesar.
2. Extrae texto, metadatos visibles y estructura basica del documento.
3. Conserva secciones, tablas o paginas relevantes cuando sea posible.
4. Devuelve un resultado organizado por pagina o seccion.

## Restricciones
* No asumas texto que no se haya extraido.
* Si el PDF esta escaneado o incompleto, indicalo claramente.
* No expongas datos sensibles salvo que sean necesarios para la tarea.

## Recursos opcionales
examples/pdf-extraction.md
