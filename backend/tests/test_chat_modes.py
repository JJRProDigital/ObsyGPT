import pytest
from pydantic import ValidationError

from app.chat.routes import MessageRequest, build_mode_directive


def test_build_mode_directive_returns_none_for_act_and_none():
    assert build_mode_directive("act") is None
    assert build_mode_directive(None) is None


def test_build_mode_directive_returns_instructions_for_plan_and_think():
    plan = build_mode_directive("plan")
    think = build_mode_directive("think")

    assert plan and "plan numerado" in plan.lower()
    assert think and "razona en profundidad" in think.lower()


def test_message_request_accepts_valid_modes():
    for mode in ["act", "plan", "think", None]:
        payload = MessageRequest(message="hola", mode=mode)
        assert payload.mode == mode


def test_message_request_rejects_invalid_mode():
    with pytest.raises(ValidationError):
        MessageRequest(message="hola", mode="vago")
