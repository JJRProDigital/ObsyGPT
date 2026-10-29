"""Trigger engine: background asyncio loop that evaluates due triggers and
enqueues agent tasks. Like the Telegram gateway, it lives inside the FastAPI
process, so it runs anywhere the stack runs (Linux VPS, Mac, Windows) with no
system cron dependency."""

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from urllib.request import Request, urlopen

from . import store as trigger_store

logger = logging.getLogger("obsygpt.triggers")

TICK_SECONDS = 20.0
FETCH_TIMEOUT_SECONDS = 15
MAX_FETCH_BYTES = 2 * 1024 * 1024
RSS_ITEM_PATTERN = re.compile(r"<item>(.*?)</item>", re.DOTALL)
RSS_TITLE_PATTERN = re.compile(r"<title>(.*?)</title>", re.DOTALL)
MAX_SUMMARY_ITEMS = 5
MAX_GOAL_CONTEXT_CHARS = 1200


class TriggerError(Exception):
    pass


# ---------- pure helpers (unit-tested) ----------


def parse_time_of_day(value: str) -> list[time]:
    """Parses 'HH:MM' or comma-separated 'HH:MM,HH:MM,HH:MM' into time objects;
    raises ValueError for anything else."""
    slots: list[time] = []
    for part in str(value).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            hours, minutes = part.split(":")
            slots.append(time(int(hours), int(minutes)))
        except (TypeError, ValueError):
            raise ValueError("time_of_day must be 'HH:MM' or comma-separated 'HH:MM,HH:MM' (00:00-23:59).")
    if not slots:
        raise ValueError("time_of_day must be 'HH:MM' or comma-separated 'HH:MM,HH:MM' (00:00-23:59).")
    return slots


def validate_config(trigger_type: str, config: dict) -> None:
    if trigger_type in {"interval", "change_detection"}:
        time_of_day = str(config.get("time_of_day") or "").strip()
        if trigger_type == "interval" and time_of_day:
            # Daily-brief anchors: time_of_day replaces the cadence requirement.
            parse_time_of_day(time_of_day)
        else:
            minutes = int(config.get("interval_minutes", 0))
            if not 1 <= minutes <= 7 * 24 * 60:
                raise ValueError("interval_minutes must be between 1 and 10080.")
    if trigger_type == "change_detection":
        source_type = config.get("source_type", "url")
        if source_type not in {"url", "rss"}:
            raise ValueError("source_type must be 'url' or 'rss'.")
        url = str(config.get("url", "")).strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("change_detection requires an http(s) source url.")
        # SSRF guard: only public endpoints.
        from ..url_safety import validate_public_url

        validate_public_url(url)


def rss_titles(xml: str) -> list[str]:
    titles: list[str] = []
    for item in RSS_ITEM_PATTERN.findall(xml):
        match = RSS_TITLE_PATTERN.search(item)
        if match:
            value = re.sub(r"<!\[CDATA\[|\]\]>", "", match.group(1)).strip()
            value = re.sub(r"<[^>]+>", "", value).strip()
            if value:
                titles.append(value)
    return titles


def source_snapshot(trigger_type: str, source_type: str, body: str) -> tuple[str, str]:
    """Returns (snapshot_hash, human_summary) for a fetched source body."""
    if trigger_type == "change_detection" and source_type == "rss":
        titles = rss_titles(body)
        if not titles:
            raise TriggerError("RSS returned no items (blocked or empty feed).")
        digest = hashlib.sha256("\n".join(titles).encode("utf-8")).hexdigest()
        summary = "; ".join(titles[:MAX_SUMMARY_ITEMS])
        return digest, summary
    normalized = re.sub(r"\s+", " ", body).strip()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest, normalized[:400]


def render_goal(goal_template: str, trigger_name: str, summary: str | None, extra_context: str | None = None) -> str:
    goal = goal_template.strip()
    context_lines = [f"[Disparo automático del trigger '{trigger_name}']"]
    if summary:
        context_lines.append(f"Novedad detectada: {summary[:MAX_GOAL_CONTEXT_CHARS]}")
    if extra_context:
        context_lines.append(extra_context[:MAX_GOAL_CONTEXT_CHARS])
    return goal + "\n\n" + "\n".join(context_lines)


def fetch_source(url: str) -> str:
    request = Request(url, headers={"User-Agent": "ObsyGPT/1.0"})
    with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        return response.read(MAX_FETCH_BYTES + 1).decode("utf-8", "ignore")


def is_due(trigger: dict, now: datetime) -> bool:
    """Interval/change triggers fire on their cadence; webhook ones only via the endpoint.

    Interval triggers with config.time_of_day are anchored briefs: they fire once per
    LOCAL day for each listed wall-clock time ("08:00" or "08:00,14:00,20:00"),
    regardless of restarts or downtime. interval_minutes is ignored in that mode."""
    if trigger["trigger_type"] == "webhook":
        return False
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    last = trigger.get("last_fired_at")
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    time_of_day = str((trigger.get("config") or {}).get("time_of_day") or "").strip()
    if time_of_day:
        slots = parse_time_of_day(time_of_day)
        local_now = now.astimezone()
        # Latest slot today whose wall-clock time has already passed.
        due_slot = max((slot for slot in slots if slot <= local_now.time()), default=None)
        if due_slot is None:
            return False
        if last is None:
            return True
        last_local = last.astimezone()
        if last_local.date() < local_now.date():
            return True
        return last_local.time() < due_slot
    if not last:
        return True
    cooldown = max(int(trigger.get("cooldown_seconds") or 0), int((trigger.get("config") or {}).get("interval_minutes", 0)) * 60)
    return now >= last + timedelta(seconds=cooldown)


@dataclass
class FireOutcome:
    fired: bool
    task_id: int | None = None
    reason: str = ""


# ---------- engine ----------


class TriggerEngine:
    def __init__(self):
        self._loop_task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("Trigger engine started")

    async def stop(self) -> None:
        self._stopping = True
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
        logger.info("Trigger engine stopped")

    async def _run_loop(self) -> None:
        while not self._stopping:
            try:
                await asyncio.sleep(TICK_SECONDS)
                await self._tick()
            except asyncio.CancelledError:
                return
            except Exception as error:  # noqa: BLE001 - the engine must never die
                logger.warning("Trigger engine tick error: %s", error)

    async def _tick(self) -> None:
        now = datetime.now(timezone.utc)
        for trigger in trigger_store.list_enabled_triggers():
            if not is_due(trigger, now):
                continue
            try:
                await self.evaluate_trigger(trigger, now)
            except Exception as error:  # noqa: BLE001 - one bad trigger must not block the rest
                logger.warning("Trigger %s (%s) evaluation failed: %s", trigger.get("id"), trigger.get("name"), error)

    async def evaluate_trigger(self, trigger: dict, now: datetime | None = None) -> FireOutcome:
        """Evaluates one trigger; fires (enqueues a task) when its condition holds."""
        trigger_type = trigger["trigger_type"]
        config = trigger.get("config") or {}
        summary: str | None = None
        snapshot: str | None = trigger.get("last_snapshot")

        if trigger_type == "change_detection":
            fetched = await asyncio.to_thread(fetch_source, str(config.get("url", "")))
            digest, detected = await asyncio.to_thread(source_snapshot, trigger_type, config.get("source_type", "url"), fetched)
            if digest == snapshot:
                return FireOutcome(fired=False, reason="snapshot unchanged")
            snapshot = digest
            summary = detected
        elif trigger_type == "webhook":
            # Webhook triggers fire through POST /api/triggers/{id}/fire; the
            # endpoint calls fire_now() directly. Here they are skipped.
            return FireOutcome(fired=False, reason="webhook fires via endpoint")

        return self.fire_now(trigger, summary=summary, snapshot=snapshot)

    def _brief_context(self, previous_snapshot) -> str:  # noqa: ANN001
        """Daily-brief context lines: today's date plus yesterday's brief (resolved
        deterministically from the task id stored in last_snapshot)."""
        local_now = datetime.now().astimezone()
        lines = [f"[Fecha de hoy: {local_now.strftime('%Y-%m-%d %H:%M')} hora local]"]
        yesterday = self._resolve_previous_brief(previous_snapshot)
        if yesterday:
            lines.append("[Brief anterior (actualiza; no repitas ítems sin cambios)]:\n" + yesterday)
        else:
            lines.append("[Primer día: no hay brief anterior; construye el estado inicial]")
        return "\n".join(lines)

    def _resolve_previous_brief(self, snapshot) -> str | None:  # noqa: ANN001
        raw = str(snapshot or "").strip()
        if not raw:
            return None
        if not raw.isdigit():
            return raw[:MAX_GOAL_CONTEXT_CHARS]
        try:
            from ..tasks import store as task_store

            task = task_store.get_task(int(raw))
        except Exception:  # noqa: BLE001 — a missing task must never block today's brief
            return None
        if not task:
            return None
        result = str(task.get("result") or "").strip()
        return result[:MAX_GOAL_CONTEXT_CHARS] or None

    def fire_now(self, trigger: dict, summary: str | None = None, snapshot: str | None = None) -> FireOutcome:
        from ..tasks.routes import require_manager

        config = trigger.get("config") or {}
        extra_context: str | None = None
        if str(config.get("time_of_day") or "").strip():
            extra_context = self._brief_context(trigger.get("last_snapshot"))
            snapshot = None  # replaced below: the new task id feeds tomorrow's brief
        goal = render_goal(trigger["goal_template"], trigger["name"], summary, extra_context=extra_context)
        task = require_manager().enqueue(
            trigger["user_id"],
            goal,
            mode="act",
            agent_id=trigger["agent_id"],
            readonly=bool(trigger.get("readonly", True)),
        )
        if extra_context is not None:
            snapshot = str(task["id"])
        trigger_store.mark_fired(trigger["id"], snapshot)
        if (trigger.get("config") or {}).get("fire_once"):
            try:
                trigger_store.set_trigger_enabled(trigger["id"], trigger["user_id"], False)
                logger.info("Trigger %s was fire_once — disabled after firing", trigger["id"])
            except Exception as error:  # noqa: BLE001
                logger.warning("Could not disable fire_once trigger %s: %s", trigger["id"], error)
        if trigger.get("notify_channel") == "telegram" and trigger.get("notify_chat_id"):
            try:
                trigger_store.record_proactive_delivery(trigger["agent_id"], int(trigger["notify_chat_id"]), f"[Trigger: {trigger['name']}]", task["id"])
            except Exception as error:  # noqa: BLE001 - notification failure must not fail the fire
                logger.warning("Proactive Telegram delivery registration failed: %s", error)
        logger.info("Trigger %s fired -> task #%s", trigger["id"], task["id"])
        return FireOutcome(fired=True, task_id=task["id"])


_engine: TriggerEngine | None = None


def get_engine() -> TriggerEngine:
    global _engine
    if _engine is None:
        _engine = TriggerEngine()
    return _engine
