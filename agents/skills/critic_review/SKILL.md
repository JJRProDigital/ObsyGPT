---
name: critic_review
description: Review an intermediate answer for quality and accuracy.
argument-hint: Borrador o respuesta intermedia a revisar.
triggers: ["user", "model"]
---

# Instrucciones principales
1. Evalua exactitud, completitud, claridad y riesgos de la respuesta.
2. Identifica afirmaciones no justificadas, contradicciones y omisiones.
3. Propone correcciones concretas y priorizadas.
4. Devuelve una version revisada si el usuario lo pide.

## Restricciones
* No reescribas por estilo si hay errores factuales sin resolver.
* No suavices riesgos importantes.
* No apruebes una respuesta si faltan evidencias clave.

## Recursos opcionales
templates/critic-review.md
