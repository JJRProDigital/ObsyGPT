---
name: github-dev-pack-review-pr
description: Revisar un pull request de GitHub y devolver hallazgos priorizados con evidencia del codigo.
argument-hint: owner/repo (usa github_list_issues para ver PRs abiertos)
triggers: ["user"]
---

# Revision de Pull Requests

Cuando el usuario pida revisar un PR:

1. Usa `github_list_issues` con state=open para localizar el PR o issue indicado.
2. Usa `github_read_file` para leer los archivos afectados (empieza por el diff o archivos mencionados).
3. Evalua: correccion, seguridad, rendimiento, legibilidad y cobertura de pruebas.
4. Devuelve un informe con secciones: **Bloqueantes**, **Importantes**, **Menores** y **Preguntas al autor**.
5. Cita archivo y linea exacta de cada hallazgo.

## Restricciones

- No apruebes cambios que no hayas leido.
- Si el token no tiene acceso al repo, dilo y sugerir al usuario que revise los permisos.
- Nunca hagas push ni cierres el PR sin confirmacion explicita.
