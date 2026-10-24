"""Learn user habits from conversations: model-extracted suggestions the user approves."""

from collections import Counter
import json
import logging
import re
import threading

from ..db import connect
from ..providers import ChatMessage, ChatRequest, ProviderRegistry
from ..workflows.runtime import AgentSpec
from .store import create_habit_suggestion, list_habit_suggestions, list_memories


logger = logging.getLogger("obsygpt.memory.learning")

EXTRACT_EVERY_N_MESSAGES = 3
MAX_EXCHANGE_CHARS = 4000

EXTRACTION_SYSTEM_PROMPT = (
    "Eres un detector de habitos de usuario. Analizas el ultimo intercambio de una conversacion "
    "entre un usuario y su asistente y decides si revela una preferencia ESTABLE de como trabaja "
    "el usuario: formato de respuesta, idioma, tono, longitud, herramientas o flujo preferido.\n\n"
    "Reglas:\n"
    "- Devuelve SOLO JSON valido: {\"habit\": \"...\"} o {\"habit\": null}.\n"
    "- El habito va en tercera persona, en una sola linea de maximo 120 caracteres (ej.: 'Prefiere respuestas breves y en espanol').\n"
    "- Ignora informacion puntual de la tarea: solo preferencias de trabajo repetidas o corregidas por el usuario.\n"
    "- Si hay senal clara de correccion ('no, hazlo asi...', 'siempre quiero...'), proponla.\n"
    "- Ante la duda, devuelve null: molesta mas un mal habito que uno que falta."
)


def _count_user_messages(conversation_id: int) -> int:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = %s AND role = 'user';", (conversation_id,))
            return cursor.fetchone()[0]


def _recent_user_message_samples(conversation_id: int, limit: int = 200) -> list[str]:
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT content FROM messages WHERE conversation_id = %s AND role = 'user' ORDER BY id DESC LIMIT %s;",
                (conversation_id, limit),
            )
            return [row[0] for row in cursor.fetchall()]


def parse_model_reply(reply: str) -> str | None:
    """Extracts a habit line from the model reply, tolerating noise around the JSON."""
    text = reply.strip()
    if not text or text.lower() in {"none", "null", "ninguno", "{}"}:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    habit = data.get("habit") if isinstance(data, dict) else None
    if not isinstance(habit, str):
        return None
    habit = habit.strip()
    if not habit or habit.lower() in {"none", "null", "ninguno"}:
        return None
    return habit[:200]


def _heuristic_skill_habits(user_id: int, conversation_id: int) -> list[tuple[str, str]]:
    """Detects frequently-invoked slash skills and proposes a habit for each."""
    samples = _recent_user_message_samples(conversation_id)
    counts = Counter()
    for message in samples:
        match = re.match(r"\s*/([a-z0-9_\-]+)\b", message.lower())
        if match:
            counts[match.group(1)] += 1
    if not counts:
        return []

    known = " ".join(item["content"].lower() for item in list_memories(user_id, kind="habit", limit=100))
    proposals = []
    for skill, uses in counts.items():
        if uses >= 3 and skill not in known:
            proposals.append((f"Invoca con frecuencia la skill /{skill}", f"Usada {uses} veces en esta conversacion"))
    return proposals[:1]


def _build_exchange(user_message: str, assistant_message: str) -> str:
    exchange = f"Usuario: {user_message.strip()}\n\nAsistente: {assistant_message.strip()}"
    if len(exchange) > MAX_EXCHANGE_CHARS:
        exchange = exchange[:MAX_EXCHANGE_CHARS] + "\n[...]"
    return exchange


def _extract_with_model(agent: AgentSpec, user_id: int, exchange: str) -> str | None:
    habits = [item["content"] for item in list_memories(user_id, kind="habit", limit=30)]
    known_block = "\n".join(f"- {habit}" for habit in habits) or "- (ninguno)"

    request = ChatRequest(
        model=agent.model,
        temperature=0.1,
        messages=[
            ChatMessage(role="user", content=f"{EXTRACTION_SYSTEM_PROMPT}\n\nHabitos ya conocidos (NO los repitas):\n{known_block}\n\nIntercambio:\n---\n{exchange}\n---"),
        ],
    )
    registry = ProviderRegistry()
    chunks: list[str] = []
    for token in registry.stream_chat_with_config(
        agent.provider_type,
        request,
        api_key_env=agent.provider_api_key_env,
        base_url=agent.provider_base_url,
    ):
        chunks.append(token)
    return parse_model_reply("".join(chunks))


def learn_habits(
    user_id: int,
    conversation_id: int,
    agent: AgentSpec,
    user_message: str,
    assistant_message: str,
) -> None:
    """Runs heuristics plus one model extraction and stores non-duplicate suggestions."""
    if _count_user_messages(conversation_id) % EXTRACT_EVERY_N_MESSAGES != 0:
        return
    if len(list_habit_suggestions(user_id, status="pending")) >= 5:
        return

    for content, evidence in _heuristic_skill_habits(user_id, conversation_id):
        create_habit_suggestion(user_id, content, evidence=evidence, source="heuristic", conversation_id=conversation_id)

    exchange = _build_exchange(user_message, assistant_message)
    try:
        habit = _extract_with_model(agent, user_id, exchange)
    except Exception as error:  # noqa: BLE001
        logger.error("Habit extraction failed: %s", repr(error))
        return
    if habit:
        evidence = user_message.strip()[:200]
        create_habit_suggestion(user_id, habit, evidence=evidence, source="model", conversation_id=conversation_id)


def learn_habits_in_background(
    user_id: int,
    conversation_id: int,
    agent: AgentSpec,
    user_message: str,
    assistant_message: str,
) -> None:
    thread = threading.Thread(
        target=learn_habits,
        args=(user_id, conversation_id, agent, user_message, assistant_message),
        daemon=True,
        name=f"obsygpt-habits-{conversation_id}",
    )
    thread.start()
