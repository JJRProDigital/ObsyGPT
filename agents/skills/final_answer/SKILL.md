---
name: final_answer
description: Synthesize a final user-facing answer.
argument-hint: Contexto, hallazgos y borradores previos.
triggers: ["user", "model"]
---

# Instrucciones principales
1. Integra contexto, resultados de agentes y restricciones del usuario.
2. Produce una respuesta final clara, accionable y directamente util.
3. Ordena la respuesta de lo mas importante a lo accesorio.
4. Incluye supuestos, limites y siguientes pasos solo cuando aporten valor.

## Restricciones
* No incluyas trazas internas ni razonamiento privado.
* No cites fuentes o herramientas que no se hayan usado.
* No inventes consenso si los agentes discrepan.

## Recursos opcionales
templates/final-answer.md
