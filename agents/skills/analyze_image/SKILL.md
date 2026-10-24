---
name: analyze_image
description: Analyze an uploaded image with a vision-capable model.
argument-hint: Imagen adjunta y pregunta concreta sobre la imagen.
triggers: ["user"]
---

# Instrucciones principales
1. Describe primero los elementos visuales observables.
2. Responde la pregunta del usuario usando solo evidencia visible.
3. Diferencia observaciones de inferencias.
4. Si hace falta OCR, transcribe el texto visible y marca baja confianza.

## Restricciones
* No identifiques personas reales ni atributos sensibles.
* No afirmes detalles no visibles.
* No uses analisis de imagen si el modelo activo no soporta vision.

## Recursos opcionales
examples/image-analysis.md
