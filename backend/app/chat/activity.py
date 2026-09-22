"""Agent-loop streaming plumbing shared by chat streaming and approval resumes."""

import json
from collections.abc import Generator
from queue import Queue
from threading import Thread

from ..agent.errors import ApprovalRequiredError


ACTIVITY_FRAME_OPEN = "\x00ACT\x00"
ACTIVITY_FRAME_CLOSE = "\x00"


def frame_activity(payload: dict) -> str:
    return ACTIVITY_FRAME_OPEN + json.dumps(payload, ensure_ascii=False) + ACTIVITY_FRAME_CLOSE


def drive_agent_loop(start_loop) -> Generator[tuple[str, object], None, None]:
    """Runs the blocking agent loop in a worker thread and yields ("token"|"activity"|..., payload).

    ``start_loop`` receives an ``on_activity`` callback and returns the token iterator.
    This lets activity signals (thinking, tool start/end, retries) reach the HTTP stream in
    real time even while a long tool call produces no tokens.
    """
    events: Queue = Queue()

    def on_activity(payload: dict) -> None:
        events.put(("activity", payload))

    def worker() -> None:
        try:
            for token in start_loop(on_activity):
                events.put(("token", token))
            events.put(("done", None))
        except ApprovalRequiredError as error:
            events.put(("approval", error))
        except Exception as error:  # noqa: BLE001
            events.put(("error", error))
        finally:
            events.put(("end", None))

    thread = Thread(target=worker, daemon=True)
    thread.start()
    while True:
        kind, payload = events.get()
        yield kind, payload
        if kind == "end":
            return
