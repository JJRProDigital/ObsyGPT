# Backlog ObsyGPT

Ideas aprobadas pendientes de desarrollo. Marca con `[x]` al completar.

## Sub-agentes

- [ ] **Dispatch multi-hijo en profundidad**: explotar el paralelismo real (hasta 3 hijos ya soportados) con UI dedicada — progreso en vivo por hijo, cancelación individual, y patrones preconfigurados (p.ej. "review + research" en un clic). Probar con 2-3 agentes simultáneos y validar agregación.
- [ ] **Editor visual de dispatches**: plantillas de delegación guardadas por usuario.

## Conectores

- [ ] **Conector GitHub en profundidad**: usar `github_*` tools desde Code Reviewer para revisar PRs/issues reales (no código pegado) — `github_list_issues` + `github_read_file` encadenados; OAuth con refresh token (sustituir PAT pegado); conector GitHub MCP oficial como alternativa.
- [ ] Más conectores prebuilt: Slack, Notion, Gmail, Calendar.
