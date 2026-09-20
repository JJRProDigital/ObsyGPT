---
name: web_search
description: Search the web and return ranked results.
argument-hint: Search query and optional result constraints.
triggers: ["user", "model"]
---

# Instrucciones principales
1. Convierte la tarea del usuario en una consulta de busqueda concreta.
2. Prioriza fuentes recientes, oficiales o verificables.
3. Resume los resultados por relevancia e incluye enlaces cuando existan.
4. Senala incertidumbre, fechas y posibles sesgos de las fuentes.

## Restricciones
* No inventes URLs, titulos ni datos.
* No uses busqueda web para informacion sensible si el usuario no lo pidio.
* No presentes resultados no verificados como hechos definitivos.

## Recursos opcionales
examples/search-query.md
