import pytest

from app.agent.guardrails import GuardrailConfig, Guardrails, GuardrailViolation


def test_iteration_limit_raises():
    guardrails = Guardrails(GuardrailConfig(max_iterations=3))

    guardrails.check_before_iteration()
    guardrails.check_before_iteration()
    guardrails.check_before_iteration()

    with pytest.raises(GuardrailViolation, match="iterations"):
        guardrails.check_before_iteration()


def test_tool_call_limit_raises():
    guardrails = Guardrails(GuardrailConfig(max_tool_calls=2))

    guardrails.check_tool_call("read_file", {"path": "a"})
    guardrails.check_tool_call("read_file", {"path": "b"})

    with pytest.raises(GuardrailViolation, match="tool calls"):
        guardrails.check_tool_call("read_file", {"path": "c"})


def test_loop_detection_triggers_on_repeated_same_call():
    guardrails = Guardrails(GuardrailConfig(loop_repeat_limit=3))

    guardrails.check_tool_call("read_file", {"path": "same.txt"})
    guardrails.check_tool_call("read_file", {"path": "same.txt"})

    with pytest.raises(GuardrailViolation, match="[Ll]oop"):
        guardrails.check_tool_call("read_file", {"path": "same.txt"})


def test_loop_detection_ignores_different_args():
    guardrails = Guardrails(GuardrailConfig(loop_repeat_limit=3))

    guardrails.check_tool_call("read_file", {"path": "a"})
    guardrails.check_tool_call("read_file", {"path": "b"})
    guardrails.check_tool_call("read_file", {"path": "c"})

    assert guardrails.tool_call_count == 3


def test_duration_limit_raises():
    clock_values = iter([0.0, 0.0, 100.0])
    guardrails = Guardrails(GuardrailConfig(max_duration_seconds=60), clock=lambda: next(clock_values))

    guardrails.check_before_iteration()

    with pytest.raises(GuardrailViolation, match="duration"):
        guardrails.check_before_iteration()


def test_total_chars_budget_enforced():
    guardrails = Guardrails(GuardrailConfig(max_total_chars=100))

    guardrails.add_output_chars(90)

    with pytest.raises(GuardrailViolation, match="characters"):
        guardrails.add_output_chars(20)


def test_clip_output_truncates_with_marker():
    guardrails = Guardrails(GuardrailConfig(max_tool_output_chars=50))

    clipped = guardrails.clip_output("x" * 500)

    assert len(clipped) < 120
    assert "truncated" in clipped.lower()


def test_from_settings_merges_defaults():
    config = GuardrailConfig.from_settings({"max_iterations": 5})

    assert config.max_iterations == 5
    assert config.max_tool_calls == 25
    assert config.loop_repeat_limit == 3


def test_from_settings_ignores_garbage():
    config = GuardrailConfig.from_settings({"max_iterations": "garbage", "unknown": 1})

    assert config.max_iterations == 12
