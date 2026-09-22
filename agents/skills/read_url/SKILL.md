---
name: read_url
description: Read and extract clean content from a URL.
argument-hint: URL publica para leer y sintetizar.
triggers: ["user", "model"]
---

# Instrucciones principales
1. Valida que la entrada contiene una URL publica.
2. Extrae el contenido principal y descarta navegacion, anuncios y boilerplate.
3. Devuelve un resumen fiel, puntos clave y cualquier dato accionable.
4. Cita la URL original en la respuesta.

## Restricciones
* No leas URLs privadas, locales o potencialmente internas.
* No inventes contenido que no aparezca en la pagina.
* Si la pagina no se puede leer, explica el fallo y pide otra fuente.

## Recursos opcionales
examples/read-url.md
