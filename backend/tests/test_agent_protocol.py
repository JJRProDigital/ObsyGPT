import pytest

from app.agent.protocol import PROTOCOL_MARKER_CLOSE, PROTOCOL_MARKER_OPEN, parse_model_output


def test_parse_extracts_tool_call_and_thought():
    text = "Voy a leer el README primero.\n" + PROTOCOL_MARKER_OPEN + '\n{"tool": "read_file", "args": {"path": "README.md"}}\n' + PROTOCOL_MARKER_CLOSE

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "read_file"
    assert parsed.tool_call.args == {"path": "README.md"}
    assert "Voy a leer el README primero." in parsed.thought
    assert parsed.parse_error is None


def test_parse_without_block_returns_full_text_as_thought():
    parsed = parse_model_output("Esta es la respuesta final sin herramientas.")

    assert parsed.tool_call is None
    assert parsed.thought == "Esta es la respuesta final sin herramientas."
    assert parsed.parse_error is None


def test_parse_malformed_json_sets_parse_error():
    text = "Pensando...\n" + PROTOCOL_MARKER_OPEN + "\n{tool: read_file, args: no json}\n" + PROTOCOL_MARKER_CLOSE

    parsed = parse_model_output(text)

    assert parsed.tool_call is None
    assert parsed.parse_error is not None
    assert "Pensando..." in parsed.thought


def test_parse_repairs_unescaped_html_quotes_in_goal():
    payload = '{"tool": "dispatch_subagents", "args": {"tasks": [{"agent": "Code Reviewer", "goal": "Revisar: <meta name="viewport" content="width=device-width"> y demas"}]}}'
    text = PROTOCOL_MARKER_OPEN + "\n" + payload + "\n" + PROTOCOL_MARKER_CLOSE

    parsed = parse_model_output(text)

    assert parsed.parse_error is None
    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "dispatch_subagents"
    goal = parsed.tool_call.args["tasks"][0]["goal"]
    assert 'name="viewport"' in goal
    assert 'content="width=device-width"' in goal


def test_parse_repairs_raw_newlines_inside_strings():
    payload = '{"tool": "write_file", "args": {"path": "a.txt", "content": "linea uno\nlinea dos"}}'
    text = PROTOCOL_MARKER_OPEN + "\n" + payload + "\n" + PROTOCOL_MARKER_CLOSE

    parsed = parse_model_output(text)

    assert parsed.parse_error is None
    assert parsed.tool_call.args["content"] == "linea uno\nlinea dos"


def test_parse_repairs_code_fenced_payload():
    payload = '```json\n{"tool": "list_dir", "args": {"path": "."}}\n```'
    text = PROTOCOL_MARKER_OPEN + "\n" + payload + "\n" + PROTOCOL_MARKER_CLOSE

    parsed = parse_model_output(text)

    assert parsed.parse_error is None
    assert parsed.tool_call.name == "list_dir"


def test_parse_keeps_valid_payload_untouched_through_repair_path():
    payload = '{"tool": "read_file", "args": {"path": "README.md", "note": "con: colon y } bracket en texto"}}'
    text = PROTOCOL_MARKER_OPEN + "\n" + payload + "\n" + PROTOCOL_MARKER_CLOSE

    parsed = parse_model_output(text)

    assert parsed.parse_error is None
    assert parsed.tool_call.args["path"] == "README.md"


def test_parse_first_block_wins_when_multiple_blocks():
    text = (
        PROTOCOL_MARKER_OPEN + '\n{"tool": "list_dir", "args": {"path": "."}}\n' + PROTOCOL_MARKER_CLOSE
        + " texto intermedio "
        + PROTOCOL_MARKER_OPEN + '\n{"tool": "read_file", "args": {"path": "x"}}\n' + PROTOCOL_MARKER_CLOSE
    )

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "list_dir"


def test_parse_rejects_non_string_tool_name():
    text = PROTOCOL_MARKER_OPEN + '\n{"tool": 42, "args": {}}\n' + PROTOCOL_MARKER_CLOSE

    parsed = parse_model_output(text)

    assert parsed.tool_call is None
    assert parsed.parse_error is not None


def test_parse_rejects_missing_args_defaults_to_empty():
    text = PROTOCOL_MARKER_OPEN + '\n{"tool": "list_dir"}\n' + PROTOCOL_MARKER_CLOSE

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "list_dir"
    assert parsed.tool_call.args == {}


def test_parse_keeps_text_after_block_in_thought():
    text = (
        "Antes.\n" + PROTOCOL_MARKER_OPEN + '\n{"tool": "list_dir", "args": {}}\n' + PROTOCOL_MARKER_CLOSE + "\nDespues."
    )

    parsed = parse_model_output(text)

    assert "Antes." in parsed.thought
    assert "Despues." in parsed.thought


def test_parse_accepts_single_line_tool_block():
    text = (
        "Procedo a navegar a la URL solicitada.\n\n"
        + PROTOCOL_MARKER_OPEN
        + ' {"tool": "browser_navigate", "args": {"url": "https://example.com"}} '
        + PROTOCOL_MARKER_CLOSE
        + "\n\n(Esperando la carga de la pagina...)"
    )

    parsed = parse_model_output(text)

    assert parsed.parse_error is None
    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "browser_navigate"
    assert parsed.tool_call.args == {"url": "https://example.com"}
    assert "Procedo a navegar" in parsed.thought
    assert PROTOCOL_MARKER_OPEN not in parsed.thought


def test_parse_recovers_unterminated_tool_block():
    text = "Voy a buscar.\n" + PROTOCOL_MARKER_OPEN + ' {"tool": "web_fetch", "args": {"url": "https://x.com"}}'

    parsed = parse_model_output(text)

    assert parsed.parse_error is None
    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "web_fetch"
    assert parsed.thought == "Voy a buscar."


def test_parse_recovers_unterminated_block_without_json():
    parsed = parse_model_output("Pensando.\n" + PROTOCOL_MARKER_OPEN + " no soy json")

    assert parsed.tool_call is None
    assert parsed.parse_error is not None


def test_strip_tool_blocks_removes_inline_and_multiline():
    from app.agent.protocol import strip_tool_blocks

    inline = "Antes.\n" + PROTOCOL_MARKER_OPEN + ' {"tool": "browser_navigate", "args": {"url": "https://x.com"}} ' + PROTOCOL_MARKER_CLOSE + "\nDespues."
    cleaned_inline = strip_tool_blocks(inline)
    assert PROTOCOL_MARKER_OPEN not in cleaned_inline and PROTOCOL_MARKER_CLOSE not in cleaned_inline
    assert "Antes." in cleaned_inline and "Despues." in cleaned_inline

    multiline = "A\n" + PROTOCOL_MARKER_OPEN + '\n{"tool": "web_fetch", "args": {}}\n' + PROTOCOL_MARKER_CLOSE + "\nB"
    cleaned = strip_tool_blocks(multiline)
    assert PROTOCOL_MARKER_OPEN not in cleaned and PROTOCOL_MARKER_CLOSE not in cleaned
    assert "A" in cleaned and "B" in cleaned


def test_strip_tool_blocks_removes_dangling_marker():
    from app.agent.protocol import strip_tool_blocks

    text = "Respuesta util.\n" + PROTOCOL_MARKER_OPEN + ' {"tool": "x"'
    cleaned = strip_tool_blocks(text)
    assert cleaned == "Respuesta util."


def test_strip_tool_blocks_keeps_clean_text():
    from app.agent.protocol import strip_tool_blocks

    assert strip_tool_blocks("Sin marcadores aqui.") == "Sin marcadores aqui."
