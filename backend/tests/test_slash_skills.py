from app.chat.routes import build_slash_skill_prompt, parse_slash_skill


def test_parse_slash_skill_extracts_name_and_task():
    assert parse_slash_skill("/invoice-risk revisa esta factura") == ("invoice-risk", "revisa esta factura")


def test_parse_slash_skill_ignores_regular_messages_and_escaped_slash():
    assert parse_slash_skill("hola /invoice-risk") is None
    assert parse_slash_skill("//invoice-risk") is None


def test_build_slash_skill_prompt_embeds_skill_md_and_task():
    prompt = build_slash_skill_prompt(
        {
            "name": "invoice-risk",
            "description": "Detect risky invoices.",
            "argument_hint": "Invoice text",
            "triggers": ["user"],
            "body": "# Instrucciones principales\n1. Analiza la factura.",
            "resources": "examples/invoice.txt",
        },
        "revisa factura 123",
    )

    assert "agents/skills/invoice-risk/SKILL.md" in prompt
    assert "---\nname: invoice-risk" in prompt
    assert "triggers: [\"user\"]" in prompt
    assert "## Tarea del usuario\nrevisa factura 123" in prompt
