"""Self-scheduling tools: agents create and manage their own proactive triggers."""

from .base import ToolResult, ToolSpec

MAX_ACTIVE_TRIGGERS = 10


class ScheduleTriggerTool:
    spec = ToolSpec(
        name="schedule_trigger",
        description=(
            "Programa un disparador proactivo para TI MISMO: dentro de N minutos despertarás automáticamente "
            "y ejecutarás el objetivo indicado (recordatorios, seguimientos, verificaciones diferidas). "
            "Con fire_once=true se desactiva después de disparar una vez (ideal para 'mañana revisa si...'). "
            "Límite: 10 triggers activos por usuario."
        ),
        parameters='{"goal": "Revisa si llegó respuesta y resume", "interval_minutes": 60, "fire_once": true, "name": "seguimiento-respuesta", "readonly": true}',
        permission="safe",
    )

    def __init__(self, user_id: int | None = None, agent_id: int | None = None, store=None):
        self.user_id = user_id
        self.agent_id = agent_id
        self._store = store

    def run(self, args: dict) -> ToolResult:
        if self.user_id is None or self.agent_id is None:
            return ToolResult(ok=False, output="schedule_trigger requiere un usuario y agente válidos.")
        store = self._store
        if store is None:
            from ...triggers import store as trigger_store

            store = trigger_store
        goal = str(args.get("goal", "")).strip()
        if not goal:
            return ToolResult(ok=False, output="Falta el argumento obligatorio: goal")
        try:
            interval = int(args.get("interval_minutes", 60))
        except (TypeError, ValueError):
            interval = 60
        if not 1 <= interval <= 7 * 24 * 60:
            return ToolResult(ok=False, output="interval_minutes debe estar entre 1 y 10080.")
        fire_once = bool(args.get("fire_once", True))
        readonly = bool(args.get("readonly", True))
        name = str(args.get("name", "")).strip() or f"auto-{interval}min"
        active = store.count_active_triggers(self.user_id)
        if active >= MAX_ACTIVE_TRIGGERS:
            return ToolResult(ok=False, output=f"Límite alcanzado: ya tienes {active} triggers activos (máximo {MAX_ACTIVE_TRIGGERS}). Cancela alguno con cancel_trigger.")
        try:
            trigger = store.create_trigger(
                self.user_id,
                self.agent_id,
                name[:120],
                "interval",
                {"interval_minutes": interval, "fire_once": fire_once},
                goal[:8000],
                notify_channel="",
                notify_chat_id=None,
                readonly=readonly,
            )
        except ValueError as error:
            return ToolResult(ok=False, output=f"Trigger inválido: {error}")
        modo = "una vez" if fire_once else "de forma recurrente"
        return ToolResult(ok=True, output=f"Trigger #{trigger['id']} '{trigger['name']}' programado: en {interval} minutos, {modo}, ejecutarás: {goal[:200]}")


class MyTriggersTool:
    spec = ToolSpec(
        name="my_triggers",
        description="Lista tus triggers proactivos activos (los que vos mismo programaste).",
        parameters="{}",
        permission="safe",
    )

    def __init__(self, user_id: int | None = None, store=None):
        self.user_id = user_id
        self._store = store

    def run(self, args: dict) -> ToolResult:
        if self.user_id is None:
            return ToolResult(ok=False, output="my_triggers requiere un usuario válido.")
        store = self._store
        if store is None:
            from ...triggers import store as trigger_store

            store = trigger_store
        triggers = [t for t in store.list_triggers(self.user_id) if t.get("enabled")]
        if not triggers:
            return ToolResult(ok=True, output="No tienes triggers activos.")
        lines = [f"{t['id']}. {t['name']} — cada {t['config'].get('interval_minutes', '?')} min — goal: {t['goal_template'][:120]}" for t in triggers]
        return ToolResult(ok=True, output="\n".join(lines))


class CancelTriggerTool:
    spec = ToolSpec(
        name="cancel_trigger",
        description="Desactiva uno de tus triggers proactivos por id (los ids los ves con my_triggers).",
        parameters='{"trigger_id": 5}',
        permission="safe",
    )

    def __init__(self, user_id: int | None = None, store=None):
        self.user_id = user_id
        self._store = store

    def run(self, args: dict) -> ToolResult:
        if self.user_id is None:
            return ToolResult(ok=False, output="cancel_trigger requiere un usuario válido.")
        store = self._store
        if store is None:
            from ...triggers import store as trigger_store

            store = trigger_store
        try:
            trigger_id = int(args.get("trigger_id", 0))
        except (TypeError, ValueError):
            return ToolResult(ok=False, output="trigger_id inválido.")
        if not trigger_id:
            return ToolResult(ok=False, output="Falta el argumento obligatorio: trigger_id")
        trigger = store.get_trigger(trigger_id, self.user_id)
        if not trigger:
            return ToolResult(ok=False, output=f"No existe un trigger #{trigger_id} tuyo.")
        store.set_trigger_enabled(trigger_id, self.user_id, False)
        return ToolResult(ok=True, output=f"Trigger #{trigger_id} '{trigger['name']}' desactivado.")
