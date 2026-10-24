"""Telegram gateway: long-polling bot per enabled agent, tasks executed headless.

Each Telegram message from an allowlisted user becomes an ObsyGPT background task
(the same engine used by the tasks panel), so approvals, retries, subagent chains
and tracing all behave exactly like any other background task. Outcomes are
delivered back to the Telegram chat; sensitive-tool approvals arrive as inline
keyboard buttons and resume the task when answered.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass

import httpx

from ..voice import stt as voice_stt

from . import store as tg_store

# httpx logs full request URLs at INFO, which would leak bot tokens into logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("obsygpt.telegram")

API_BASE = "https://api.telegram.org/bot{token}/{method}"
POLL_TIMEOUT_SECONDS = 25
POLL_ERROR_BACKOFF_SECONDS = 5.0
WATCH_INTERVAL_SECONDS = 3.0
RESYNC_EVERY_TICKS = 10
TG_MESSAGE_LIMIT = 4000  # Telegram hard limit is 4096; margin for safety
MAX_HISTORY_ENTRIES = 8
MAX_BUTTONS_PER_MESSAGE = 3

_TASK_LINK_RE = re.compile(r"Recibido\. Tarea #(\d+)")


class TelegramGatewayError(Exception):
    pass


# ---------- pure helpers (unit-tested) ----------


def parse_allowlist(raw: str) -> dict[int, str]:
    """Parses '12345:juan,67890:ana' into {12345: 'juan'}."""
    mapping: dict[int, str] = {}
    for entry in re.split(r"[,;\s]+", (raw or "").strip()):
        if not entry:
            continue
        if ":" not in entry:
            raise ValueError(f"Invalid allowlist entry '{entry}': expected '<telegram_id>:<username>'.")
        tg_part, username = entry.split(":", 1)
        if not tg_part.isdigit():
            raise ValueError(f"Invalid Telegram user id '{tg_part}' in allowlist entry '{entry}'.")
        username = username.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", username):
            raise ValueError(f"Invalid ObsyGPT username '{username}' in allowlist entry '{entry}'.")
        mapping[int(tg_part)] = username
    return mapping


def chunk_message(text: str, limit: int = TG_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    remaining = text
    while remaining:
        chunks.append(remaining[:limit])
        remaining = remaining[limit:]
    return chunks


def build_context_note(history: list[dict]) -> str:
    """Recent chat history as a context note (kept out of the task goal)."""
    if not history:
        return ""
    lines = ["Contexto previo de esta conversación de Telegram (de más antiguo a más reciente):"]
    for item in history[-MAX_HISTORY_ENTRIES:]:
        who = "Usuario" if item.get("direction") == "inbound" else "Agente"
        lines.append(f"- {who}: {str(item.get('content', ''))[:500]}")
    return "\n".join(lines)


def parse_callback_data(data: str) -> tuple[int, bool] | None:
    """Parses 'appr:<approval_id>:<0|1>'; None when malformed."""
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != "appr" or not parts[1].isdigit() or parts[2] not in {"0", "1"}:
        return None
    return int(parts[1]), parts[2] == "1"


def approval_keyboard(approvals: list[dict]) -> list[list[dict]]:
    buttons: list[list[dict]] = []
    for approval in approvals[:MAX_BUTTONS_PER_MESSAGE]:
        buttons.append(
            [
                {"text": "✅ Aprobar", "callback_data": f"appr:{approval['id']}:1"},
                {"text": "❌ Rechazar", "callback_data": f"appr:{approval['id']}:0"},
            ]
        )
    return buttons


def format_tool_args(args: dict, limit: int = 300) -> str:
    try:
        rendered = json.dumps(args, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        rendered = str(args)
    return rendered[:limit]


_MD_CODE_BLOCK = re.compile(r"```[a-zA-Z0-9_+-]*[ \t]*\r?\n?(.*?)```", re.DOTALL)
_MD_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MD_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_MD_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_MD_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def markdown_to_telegram_html(text: str) -> str:
    """Converts a safe Markdown subset to Telegram HTML; everything else is escaped.

    Stashes converted fragments behind NUL sentinels so their contents are not
    re-processed by later rules (e.g. **bold** inside a code block).
    """
    import html as _html

    placeholders: list[str] = []

    def _stash(fragment: str) -> str:
        placeholders.append(fragment)
        return f"\x00{len(placeholders) - 1}\x00"

    escaped = _html.escape(text, quote=False)
    escaped = _MD_CODE_BLOCK.sub(lambda m: _stash(f"<pre>{m.group(1)}</pre>"), escaped)
    escaped = _MD_INLINE_CODE.sub(lambda m: _stash(f"<code>{m.group(1)}</code>"), escaped)
    escaped = _MD_BOLD.sub(lambda m: _stash(f"<b>{m.group(1)}</b>"), escaped)
    escaped = _MD_ITALIC.sub(lambda m: _stash(f"<i>{m.group(1)}</i>"), escaped)
    escaped = _MD_LINK.sub(lambda m: _stash(f'<a href="{m.group(2)}">{m.group(1)}</a>'), escaped)
    escaped = _MD_HEADING.sub(lambda m: f"<b>{m.group(1)}</b>", escaped)
    for index, fragment in enumerate(placeholders):
        escaped = escaped.replace(f"\x00{index}\x00", fragment)
    return escaped


# ---------- Telegram HTTP client ----------


@dataclass
class TelegramClient:
    token: str

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=POLL_TIMEOUT_SECONDS + 10)

    async def _call(self, method: str, payload: dict) -> dict | None:
        async with self._client() as client:
            response = await client.post(API_BASE.format(token=self.token, method=method), json=payload)
            data = response.json() if response.status_code < 500 else {}
        if not data.get("ok"):
            description = data.get("description", f"HTTP {response.status_code}")
            raise TelegramGatewayError(f"Telegram API {method} failed: {description}")
        return data.get("result")

    async def get_updates(self, offset: int) -> list[dict]:
        result = await self._call(
            "getUpdates",
            {"offset": offset, "timeout": POLL_TIMEOUT_SECONDS, "allowed_updates": ["message", "callback_query"]},
        )
        return result or []

    async def delete_webhook(self) -> None:
        await self._call("deleteWebhook", {"drop_pending_updates": False})

    async def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> int | None:
        payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        result = await self._call("sendMessage", payload)
        return (result or {}).get("message_id")

    async def send_chat_action(self, chat_id: int, action: str = "typing") -> None:
        try:
            await self._call("sendChatAction", {"chat_id": chat_id, "action": action})
        except TelegramGatewayError:
            pass

    async def answer_callback_query(self, callback_query_id: str, text: str) -> None:
        try:
            await self._call("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})
        except TelegramGatewayError:
            pass

    async def clear_reply_markup(self, chat_id: int, message_id: int) -> None:
        try:
            await self._call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": json.dumps({"inline_keyboard": []})})
        except TelegramGatewayError:
            pass

    async def get_file(self, file_id: str) -> bytes:
        """Downloads a file (e.g. a voice note) from the Telegram servers."""
        result = await self._call("getFile", {"file_id": file_id})
        file_path = (result or {}).get("file_path")
        if not file_path:
            raise TelegramGatewayError("getFile returned no file_path")
        async with self._client() as client:
            response = await client.get(f"https://api.telegram.org/file/bot{self.token}/{file_path}", timeout=60)
        if response.status_code != 200:
            raise TelegramGatewayError(f"File download failed: HTTP {response.status_code}")
        return response.content

    async def send_voice(self, chat_id: int, ogg: bytes) -> int | None:
        """Uploads an ogg/opus voice note via multipart."""
        async with self._client() as client:
            response = await client.post(
                API_BASE.format(token=self.token, method="sendVoice"),
                data={"chat_id": str(chat_id)},
                files={"voice": ("nota.ogg", ogg, "audio/ogg")},
                timeout=120,
            )
            data = response.json() if response.status_code < 500 else {}
        if not data.get("ok"):
            raise TelegramGatewayError(f"sendVoice failed: {data.get('description', response.status_code)}")
        return ((data.get("result") or {}).get("voice") or {}).get("file_id") and (data["result"]["message_id"])

    async def verify(self) -> dict:
        async with self._client() as client:
            response = await client.get(API_BASE.format(token=self.token, method="getMe"), timeout=10.0)
            data = response.json() if response.status_code < 500 else {}
        if not data.get("ok"):
            raise TelegramGatewayError(data.get("description", f"HTTP {response.status_code}"))
        return data.get("result") or {}


def verify_token_sync(token: str) -> dict:
    """Blocking getMe for the admin 'verify' endpoint."""
    with httpx.Client(timeout=10.0) as client:
        response = client.get(API_BASE.format(token=token, method="getMe"))
        data = response.json() if response.status_code < 500 else {}
    if not data.get("ok"):
        raise TelegramGatewayError(data.get("description", f"HTTP {response.status_code}"))
    return data.get("result") or {}


# ---------- gateway ----------


class TelegramGateway:
    def __init__(self):
        self._pollers: dict[int, asyncio.Task] = {}
        self._offsets: dict[int, int] = {}
        self._watch_task: asyncio.Task | None = None
        self._tick_count = 0
        self._stopping = False

    async def start(self) -> None:
        self._stopping = False
        self._watch_task = asyncio.create_task(self._watch_loop())
        logger.info("Telegram gateway started")

    async def stop(self) -> None:
        self._stopping = True
        if self._watch_task:
            self._watch_task.cancel()
            self._watch_task = None
        for agent_id, poller in list(self._pollers.items()):
            poller.cancel()
            self._pollers.pop(agent_id, None)
        logger.info("Telegram gateway stopped")

    # ---------- reconciliation ----------

    async def _watch_loop(self) -> None:
        while not self._stopping:
            try:
                await asyncio.sleep(WATCH_INTERVAL_SECONDS)
                self._tick_count += 1
                if self._tick_count % RESYNC_EVERY_TICKS == 1:
                    await self._resync_pollers()
                await self._deliver_outcomes()
            except asyncio.CancelledError:
                return
            except Exception as error:  # noqa: BLE001 - watcher must never die
                logger.warning("Telegram watcher error: %s", error)

    async def _resync_pollers(self) -> None:
        try:
            agents = tg_store.list_telegram_agents()
        except Exception as error:  # noqa: BLE001 - DB may not be migrated yet
            logger.warning("Telegram resync skipped: %s", error)
            return
        enabled = {agent["id"]: agent for agent in agents if agent.get("telegram_enabled")}
        for agent_id, agent in enabled.items():
            if agent_id not in self._pollers:
                self._offsets.setdefault(agent_id, 0)
                self._pollers[agent_id] = asyncio.create_task(self._poll_agent(agent_id))
                logger.info("Telegram poller started for agent %s (%s)", agent_id, agent.get("name"))
        for agent_id in list(self._pollers):
            if agent_id not in enabled:
                self._pollers.pop(agent_id).cancel()
                logger.info("Telegram poller stopped for agent %s", agent_id)

    # ---------- inbound ----------

    async def _poll_agent(self, agent_id: int) -> None:
        webhook_cleared = False
        while not self._stopping:
            try:
                token = tg_store.get_agent_bot_token(agent_id)
                if not token:
                    await asyncio.sleep(WATCH_INTERVAL_SECONDS)
                    continue
                client = TelegramClient(token)
                try:
                    updates = await client.get_updates(self._offsets.get(agent_id, 0))
                except TelegramGatewayError as error:
                    # A webhook set by another tool blocks long polling; clear it once and retry.
                    if not webhook_cleared and "webhook is active" in str(error):
                        logger.warning("Telegram agent %s: webhook active, deleting it to enable polling", agent_id)
                        await client.delete_webhook()
                        webhook_cleared = True
                        continue
                    raise
                webhook_cleared = False
                for update in updates:
                    self._offsets[agent_id] = int(update.get("update_id", 0)) + 1
                    if "message" in update:
                        await self._handle_message(agent_id, client, update["message"])
                    elif "callback_query" in update:
                        await self._handle_callback(agent_id, client, update["callback_query"])
            except asyncio.CancelledError:
                return
            except Exception as error:  # noqa: BLE001
                logger.warning("Telegram poller for agent %s error: %s", agent_id, error)
                await asyncio.sleep(POLL_ERROR_BACKOFF_SECONDS)

    async def _handle_message(self, agent_id: int, client: TelegramClient, message: dict) -> None:
        from_user = message.get("from") or {}
        sender_tg_id = int(from_user.get("id", 0))
        chat_id = int((message.get("chat") or {}).get("id", 0))
        voice = message.get("voice") or message.get("audio")
        text = str(message.get("text") or "").strip()
        if not text and not voice:
            return
        if not chat_id or not sender_tg_id:
            return

        config = tg_store.get_agent_telegram_config(agent_id)
        if not config:
            return
        username = tg_store.resolve_allowlisted_user(config.get("telegram_allowlist", ""), sender_tg_id)
        if username is None:
            logger.warning("Telegram message ignored: sender %s is not allowlisted for agent %s", sender_tg_id, agent_id)
            return
        user_id = tg_store.resolve_user_id_by_username(username)
        if user_id is None:
            await client.send_message(chat_id, f"El usuario de ObsyGPT '{username}' (configurado en la allowlist) no existe. Ajusta la configuración de Telegram del agente.")
            return

        via_voice = False
        history = tg_store.recent_history(agent_id, chat_id)
        if not text and voice:
            file_id = str(voice.get("file_id") or "")
            if not file_id:
                return
            await client.send_chat_action(chat_id)
            try:
                audio = await client.get_file(file_id)
                context_prompt = " ".join(
                    str(item.get("content", ""))[:150] for item in history[-2:]
                ).strip()
                text = await asyncio.to_thread(
                    voice_stt.transcribe_bytes, audio, "nota.ogg", initial_prompt=context_prompt or None
                )
            except Exception as error:  # noqa: BLE001 - transcription failure must not kill the poller
                logger.warning("Telegram voice transcription failed: %s", error)
                await client.send_message(chat_id, "No pude transcribir tu nota de voz (el servicio de voz no está disponible). Revisa los logs del backend.")
                return
            if not text:
                await client.send_message(chat_id, "No escuché nada intelligible en la nota de voz. Inténtalo de nuevo.")
                return
            via_voice = True
            await client.send_message(chat_id, f"Transcripción: {text[:300]}{'…' if len(text) > 300 else ''}")

        goal = text
        context_note = build_context_note(history)
        inbound_row_id = tg_store.record_inbound(agent_id, chat_id, int(message.get("message_id", 0)), sender_tg_id, text, via_voice=via_voice)
        if inbound_row_id is None:
            return  # duplicate delivery (e.g. offset reset after restart)

        task = self._enqueue_task(user_id, goal, agent_id, context_note=context_note)
        if task is None:
            await client.send_message(chat_id, "No pude encolar la tarea: el motor de tareas no está disponible.")
            return
        tg_store.attach_task(inbound_row_id, task["id"])
        await client.send_chat_action(chat_id)
        await client.send_message(chat_id, f"Recibido. Tarea #{task['id']} en cola — te aviso cuando termine.")

    def _enqueue_task(self, user_id: int, goal: str, agent_id: int, context_note: str | None = None) -> dict | None:
        try:
            from ..tasks.routes import require_manager

            return require_manager().enqueue(user_id, goal, mode="act", agent_id=agent_id, context_note=context_note)
        except Exception as error:  # noqa: BLE001
            logger.warning("Telegram task enqueue failed: %s", error)
            return None

    async def _handle_callback(self, agent_id: int, client: TelegramClient, callback: dict) -> None:
        parsed = parse_callback_data(str(callback.get("data") or ""))
        if parsed is None:
            return
        approval_id, approved = parsed
        from_user = callback.get("from") or {}
        sender_tg_id = int(from_user.get("id", 0))
        message = callback.get("message") or {}
        chat_id = int((message.get("chat") or {}).get("id", 0))

        config = tg_store.get_agent_telegram_config(agent_id)
        username = tg_store.resolve_allowlisted_user((config or {}).get("telegram_allowlist", ""), sender_tg_id) if config else None
        if username is None:
            await client.answer_callback_query(str(callback.get("id", "")), "No autorizado")
            return
        user_id = tg_store.resolve_user_id_by_username(username)
        if user_id is None:
            await client.answer_callback_query(str(callback.get("id", "")), "Usuario no encontrado")
            return

        from ..agent import store as agent_store  # kept lazy for testability

        decision = "approved" if approved else "denied"
        approval = agent_store.decide_approval(approval_id, user_id, decision)
        if approval is None:
            await client.answer_callback_query(str(callback.get("id", "")), "Ya decidida o inexistente")
            await client.clear_reply_markup(chat_id, int(message.get("message_id", 0)))
            return

        await client.answer_callback_query(str(callback.get("id", "")), "Aprobada" if approved else "Rechazada")
        await client.clear_reply_markup(chat_id, int(message.get("message_id", 0)))
        tg_store.record_outbound(agent_id, chat_id, f"{'Aprobada' if approved else 'Rechazada'}: {approval['tool_name']}")

        if approval.get("task_id"):
            self._resume_task(user_id, int(approval["task_id"]), approval, approved)

    def _resume_task(self, user_id: int, task_id: int, approval: dict, approved: bool) -> None:
        try:
            from ..tasks.routes import require_manager

            require_manager().resume_after_approval(user_id, task_id, approval, approved)
        except Exception as error:  # noqa: BLE001
            logger.warning("Telegram approval resume failed for task %s: %s", task_id, error)

    # ---------- outbound ----------

    async def _deliver_outcomes(self) -> None:
        rows = tg_store.pending_deliveries()
        if not rows:
            return
        for row in rows:
            status = row.get("task_status")
            if status == row.get("notified_status"):
                continue
            try:
                delivered = False
                status = row.get("task_status")
                if status is None and row.get("task_id") is not None:
                    status = "deleted"  # task row removed from the UI while pending
                if status is None and row.get("task_id") is None and row.get("notified_status") is not None:
                    status = "deleted"  # task unlinked (ON DELETE SET NULL) — notify and close
                if status == row.get("notified_status"):
                    continue
                if status == "deleted":
                    await self._send_task_result(row["agent_id"], row["chat_id"], "La tarea fue eliminada antes de terminar, así que no habrá resultado. Si la querías, envíamela de nuevo.")
                    delivered = True
                elif status == "completed":
                    if row.get("via_voice"):
                        await self._send_voice_result(row["agent_id"], row["chat_id"], row.get("result") or "(sin contenido)")
                    else:
                        await self._send_task_result(row["agent_id"], row["chat_id"], row.get("result") or "(sin contenido)")
                    delivered = True
                elif status == "failed":
                    await self._send_task_result(row["agent_id"], row["chat_id"], f"La tarea falló: {str(row.get('error') or 'error desconocido')[:800]}")
                    delivered = True
                elif status in {"cancelled", "interrupted"}:
                    await self._send_task_result(row["agent_id"], row["chat_id"], f"Tarea {status}.")
                    delivered = True
                elif status == "awaiting_approval":
                    await self._send_approval_request(row)
                tg_store.mark_notified(row["id"], str(status), delivered=delivered)
            except Exception as error:  # noqa: BLE001 - one bad chat must not block the rest
                logger.warning("Telegram delivery failed for row %s: %s", row.get("id"), error)

    async def _send_task_result(self, agent_id: int, chat_id: int, text: str) -> None:
        client = self._client_for_agent(agent_id)
        if client is None:
            logger.warning("No Telegram client available for agent %s; dropping message", agent_id)
            return
        tg_store.record_outbound(agent_id, chat_id, text)
        for chunk in chunk_message(text):
            # Chunk first, then convert each chunk: a bold/code marker split
            # across chunks degrades to literal asterisks, which is better
            # than broken HTML.
            await client.send_message(chat_id, markdown_to_telegram_html(chunk))

    async def _send_voice_result(self, agent_id: int, chat_id: int, text: str) -> None:
        """Delivers a completed task result as voice notes (max 2) + text for the rest."""
        from ..voice import tts as voice_tts

        client = self._client_for_agent(agent_id)
        if client is None:
            logger.warning("No Telegram client available for agent %s; dropping voice reply", agent_id)
            return
        tg_store.record_outbound(agent_id, chat_id, text)
        chunks = voice_tts.synthesize_chunks(text)
        voice_notes = 0
        while chunks and voice_notes < 2:
            chunk = chunks.pop(0)
            try:
                wav = await asyncio.to_thread(voice_tts.synthesize, chunk)
                ogg = await asyncio.to_thread(voice_tts.wav_to_ogg, wav)
                await client.send_voice(chat_id, ogg)
                voice_notes += 1
            except Exception as error:  # noqa: BLE001 - TTS failure falls back to text
                logger.warning("Voice synthesis failed, falling back to text: %s", error)
                chunks.insert(0, chunk)
                break
        if chunks:
            rest = "\n\n".join(chunks)
            for chunk in chunk_message(rest):
                await client.send_message(chat_id, markdown_to_telegram_html(chunk))

    async def _send_approval_request(self, row: dict) -> None:
        from ..agent import store as agent_store

        approvals = agent_store.list_pending_task_approvals(row["user_id"], row["task_id"])
        if not approvals:
            return
        client = self._client_for_agent(row["agent_id"])
        if client is None:
            return
        import html as _html

        lines = ["⏸ Aprobación pendiente en la tarea #{0}:".format(row["task_id"])]
        for approval in approvals[:MAX_BUTTONS_PER_MESSAGE]:
            tool = _html.escape(str(approval["tool_name"]), quote=False)
            args = _html.escape(format_tool_args(approval.get("args") or {}), quote=False)
            lines.append(f"• <b>{tool}</b>: <code>{args}</code>")
        await client.send_message(row["chat_id"], "\n".join(lines), reply_markup={"inline_keyboard": approval_keyboard(approvals)})

    def _client_for_agent(self, agent_id: int) -> TelegramClient | None:
        try:
            token = tg_store.get_agent_bot_token(agent_id)
        except Exception:  # noqa: BLE001
            return None
        if not token:
            return None
        return TelegramClient(token)


_gateway: TelegramGateway | None = None


def get_gateway() -> TelegramGateway:
    global _gateway
    if _gateway is None:
        _gateway = TelegramGateway()
    return _gateway
