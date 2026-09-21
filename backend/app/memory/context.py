"""Build chat context blocks from stored memories and habits."""

from .store import list_memories


MAX_CONTEXT_ITEMS = 30
MAX_ITEM_CHARS = 300


def get_user_instructions(user_id: int) -> str:
    """Returns the user's global chat instructions, stripped, or an empty string."""
    try:
        from ..workspace.routes import get_user_preferences

        return str(get_user_preferences(user_id).get("instructions") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def build_user_instructions_block(user_id: int) -> str:
    """Returns a context block with the user's personal instructions for every chat."""
    instructions = get_user_instructions(user_id)
    if not instructions:
        return ""
    return (
        "INSTRUCCIONES PERSONALES DEL USUARIO (aplicalas en toda la conversacion "
        "salvo que el usuario pida lo contrario de forma explicita):\n\n" + instructions
    )


def _memory_limit(user_id: int) -> int:
    try:
        from ..workspace.routes import get_user_preferences

        memory_max = get_user_preferences(user_id).get("memory_max")
        if isinstance(memory_max, int) and 1 <= memory_max <= 100:
            return memory_max
    except Exception:  # noqa: BLE001
        pass
    return MAX_CONTEXT_ITEMS


def format_memory_block(items: list[dict], title: str) -> str:
    lines = [f"## {title}"]
    for item in items[:MAX_CONTEXT_ITEMS]:
        content = item.get("content", "").strip()
        if len(content) > MAX_ITEM_CHARS:
            content = content[:MAX_ITEM_CHARS] + "..."
        lines.append(f"- {content}")
    return "\n".join(lines)


def build_memory_context(user_id: int, project_id: int | None = None) -> str:
    """Returns a context block with user memories, habits, and (optionally) project memories."""
    limit = _memory_limit(user_id)
    display_name = ""
    try:
        from ..workspace.routes import get_user_preferences

        display_name = str(get_user_preferences(user_id).get("display_name") or "").strip()
    except Exception:  # noqa: BLE001
        pass

    try:
        memories = list_memories(user_id, kind="memory", limit=limit)
        habits = list_memories(user_id, kind="habit", limit=limit)
        project_memories = list_memories(user_id, limit=limit, project_id=project_id) if project_id is not None else []
    except Exception:  # noqa: BLE001
        return ""

    blocks = []
    if project_memories:
        blocks.append(format_memory_block(project_memories, "Memorias del proyecto"))
    if memories:
        blocks.append(format_memory_block(memories, "Memorias persistentes del usuario"))
    if habits:
        blocks.append(format_memory_block(habits, "Habitos y preferencias del usuario"))
    if not blocks:
        return ""

    header = "Contexto persistente (aplicalo de forma natural, sin citar esta lista)"
    if display_name:
        header += f". El usuario se llama {display_name}"
    return header + ":\n\n" + "\n\n".join(blocks)
