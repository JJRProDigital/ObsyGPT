"""Execution guardrails for the agent loop."""

import hashlib
import json
import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GuardrailConfig:
    max_iterations: int = 12
    max_tool_calls: int = 25
    max_duration_seconds: int = 180
    max_tool_output_chars: int = 10_000
    max_total_chars: int = 50_000
    loop_repeat_limit: int = 3

    @classmethod
    def from_settings(cls, settings: dict | None) -> "GuardrailConfig":
        defaults = cls()
        if not isinstance(settings, dict):
            return defaults

        parsed: dict = {}
        type_by_field = {
            "max_iterations": int,
            "max_tool_calls": int,
            "max_duration_seconds": int,
            "max_tool_output_chars": int,
            "max_total_chars": int,
            "loop_repeat_limit": int,
        }
        for key, expected_type in type_by_field.items():
            value = settings.get(key)
            if isinstance(value, expected_type) and not isinstance(value, bool):
                parsed[key] = value
        return cls(**{**defaults.__dict__, **parsed})


class GuardrailViolation(RuntimeError):
    pass


@dataclass
class _GuardrailState:
    iterations: int = 0
    tool_call_count: int = 0
    total_chars: int = 0
    call_hashes: dict[str, int] = field(default_factory=dict)


class Guardrails:
    def __init__(self, config: GuardrailConfig | None = None, clock=time.monotonic):
        self.config = config or GuardrailConfig()
        self.clock = clock
        self.started_at = clock()
        self.state = _GuardrailState()

    @property
    def iterations(self) -> int:
        return self.state.iterations

    @property
    def tool_call_count(self) -> int:
        return self.state.tool_call_count

    def check_before_iteration(self) -> None:
        self.state.iterations += 1
        if self.state.iterations > self.config.max_iterations:
            raise GuardrailViolation(f"Guardrail: max iterations reached ({self.config.max_iterations}).")
        elapsed = self.clock() - self.started_at
        if elapsed > self.config.max_duration_seconds:
            raise GuardrailViolation(
                f"Guardrail: max duration reached ({self.config.max_duration_seconds}s, elapsed {elapsed:.0f}s)."
            )

    def check_tool_call(self, name: str, args: dict) -> None:
        self.state.tool_call_count += 1
        if self.state.tool_call_count > self.config.max_tool_calls:
            raise GuardrailViolation(f"Guardrail: max tool calls reached ({self.config.max_tool_calls}).")
        digest = hashlib.sha256(
            json.dumps([name, args], sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        repeats = self.state.call_hashes.get(digest, 0) + 1
        self.state.call_hashes[digest] = repeats
        if repeats >= self.config.loop_repeat_limit:
            raise GuardrailViolation(
                f"Guardrail: loop detected, tool '{name}' repeated {repeats} times with identical arguments."
            )

    def add_output_chars(self, count: int) -> None:
        self.state.total_chars += count
        if self.state.total_chars > self.config.max_total_chars:
            raise GuardrailViolation(
                f"Guardrail: total characters budget exceeded ({self.config.max_total_chars})."
            )

    def clip_output(self, output: str) -> str:
        if len(output) <= self.config.max_tool_output_chars:
            return output
        return output[: self.config.max_tool_output_chars] + f"\n... [truncated at {self.config.max_tool_output_chars} chars]"
