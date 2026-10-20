"""Agent tool: search the user's persistent semantic memory."""

from .base import ToolResult, ToolSpec
from ...memory.semantic.retrieval import search_semantic


class MemorySearchTool:
    spec = ToolSpec(
        name="memory_search",
        description=(
            "Busca en la memoria persistente del usuario (recuerdos guardados y conversaciones pasadas) "
            "los fragmentos más relevantes para una consulta. Úsala cuando necesites contexto histórico."
        ),
        parameters='{"query": "<texto a buscar>", "k": "<opcional: máximo de resultados, por defecto 5>"}',
        permission="safe",
    )

    def __init__(self, user_id: int | None = None):
        self.user_id = user_id

    def run(self, args: dict) -> ToolResult:
        if self.user_id is None:
            return ToolResult(ok=False, output="La memoria semántica no está disponible en este momento.")
        query = str(args.get("query", "")).strip()
        if not query:
            return ToolResult(ok=False, output="Debes indicar 'query': el texto a buscar en la memoria.")
        try:
            k = int(args.get("k", 5))
        except (TypeError, ValueError):
            k = 5
        k = max(1, min(k, 20))
        try:
            hits = search_semantic(self.user_id, query, k=k)
        except Exception:  # noqa: BLE001
            return ToolResult(ok=False, output="La memoria semántica no está disponible en este momento.")
        if not hits:
            return ToolResult(ok=True, output="No encontré fragmentos relevantes en la memoria para esa consulta.")
        lines = []
        for index, hit in enumerate(hits, start=1):
            origin = hit.get("title") or (f"conversación #{hit['conversation_id']}" if hit.get("conversation_id") else hit["source"])
            text = hit["text"].replace("\n", " ").strip()
            if len(text) > 400:
                text = text[:400] + "..."
            lines.append(f"{index}. [{origin}, {str(hit['when'])[:10]}] {text}")
        return ToolResult(ok=True, output="\n".join(lines))
