import pytest

from app.agent.protocol import PROTOCOL_MARKER_CLOSE, PROTOCOL_MARKER_OPEN, parse_model_output, strip_tool_blocks


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


def test_parse_recovers_llamacpp_xml_tool_call():
    text = "<tool_call>web_search\n<arg_key>url</arg_key>\n<arg_value>https://www.google.com/news?category=technology</arg_value>\n</tool_call>"

    parsed = parse_model_output(text)

    assert parsed.parse_error is None
    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "web_search"
    assert parsed.tool_call.args == {"url": "https://www.google.com/news?category=technology"}
    assert parsed.thought == ""


def test_parse_recovers_llamacpp_xml_tool_call_with_thought_and_multiple_args():
    text = (
        "Voy a buscar noticias de hoy.\n"
        "<tool_call>browser_navigate\n"
        "<arg_key>url</arg_key>\n<arg_value>https://www.google.com/search?q=noticias+ia+de+hoy</arg_value>\n"
        "<arg_key>timeout</arg_key>\n<arg_value>30</arg_value>\n"
        "</tool_call>\n"
        "Esperando la carga..."
    )

    parsed = parse_model_output(text)

    assert parsed.parse_error is None
    assert parsed.tool_call.name == "browser_navigate"
    assert parsed.tool_call.args["url"] == "https://www.google.com/search?q=noticias+ia+de+hoy"
    assert parsed.tool_call.args["timeout"] == "30"
    assert "Voy a buscar" in parsed.thought and "Esperando" in parsed.thought


def test_parse_recovers_llamacpp_xml_tool_call_without_args():
    parsed = parse_model_output("listo.\n<tool_call>list_dir\n</tool_call>")

    assert parsed.parse_error is None
    assert parsed.tool_call.name == "list_dir"
    assert parsed.tool_call.args == {}
    assert parsed.thought == "listo."


def test_parse_recovers_multiple_llamacpp_xml_tool_calls():
    text = (
        "<tool_call>web_fetch\n<arg_key>url</arg_key>\n<arg_value>https://www.ft.com/tech</arg_value>\n</tool_call>\n"
        "<tool_call>web_fetch\n<arg_key>url</arg_key>\n<arg_value>https://www.theguardian.com/tech</arg_value>\n</tool_call>\n"
        "<tool_call>browser_navigate\n<arg_key>url</arg_key>\n<arg_value>https://www.wired.com/</arg_value>\n</tool_call>"
    )

    parsed = parse_model_output(text)

    assert parsed.parse_error is None
    assert len(parsed.calls()) == 3
    assert [call.name for call in parsed.calls()] == ["web_fetch", "web_fetch", "browser_navigate"]
    assert parsed.calls()[0].args["url"] == "https://www.ft.com/tech"
    assert parsed.thought == ""


def test_protocol_tool_block_takes_precedence_over_xml():
    text = (
        PROTOCOL_MARKER_OPEN + '\n{"tool": "web_fetch", "args": {"url": "https://a.com"}}\n' + PROTOCOL_MARKER_CLOSE
        + "\n<tool_call>browser_navigate\n<arg_key>url</arg_key>\n<arg_value>https://b.com</arg_value>\n</tool_call>"
    )

    parsed = parse_model_output(text)

    assert parsed.tool_call.name == "web_fetch"


def test_strip_tool_blocks_removes_xml_tool_calls():
    from app.agent.protocol import strip_tool_blocks

    text = "Antes.\n<tool_call>web_search\n<arg_key>url</arg_key>\n<arg_value>https://x.com</arg_value>\n</tool_call>\nDespues."
    cleaned = strip_tool_blocks(text)

    assert "<tool_call>" not in cleaned
    assert "Antes." in cleaned and "Despues." in cleaned


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


def test_dots_style_recovery_parses_dispatch_subagents():
    text = """<dots_function_call>
<invoke_name">
dispatch_subagents</invoke_name>
<invoke_name>tasks</invoke_name>
<invoke_name>[{"agent": "Research Agent", "goal": "Busca 3 noticias de IA de hoy."}]</invoke_name>
</invoke_name>"""

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "dispatch_subagents"
    assert parsed.tool_call.args == {"tasks": [{"agent": "Research Agent", "goal": "Busca 3 noticias de IA de hoy."}]}
    assert "dots_function_call" not in parsed.thought
    assert parsed.parse_error is None


def test_dots_style_recovery_unterminated_block():
    text = """<dots_function_call>
<invoke_name>web_search</invoke_name>
<invoke_name>{"query": "novedades IA"}</invoke_name>"""

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "web_search"
    assert parsed.tool_call.args == {"query": "novedades IA"}


def test_dots_style_recovery_single_dict_args():
    text = '<dots_function_call><invoke_name>read_file</invoke_name><invoke_name>{"path": "README.md"}</invoke_name></dots_function_call>'

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "read_file"
    assert parsed.tool_call.args == {"path": "README.md"}


def test_standard_tool_block_still_wins_over_dots_format():
    text = (
        PROTOCOL_MARKER_OPEN
        + '\n{"tool": "memory_search", "args": {"query": "hola"}}\n'
        + PROTOCOL_MARKER_CLOSE
    )

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "memory_search"


def test_strip_tool_blocks_removes_dots_blocks():
    cleaned = strip_tool_blocks("Antes <dots_function_call><invoke_name>x</invoke_name></dots_function_call> Despues")

    assert "dots_function_call" not in cleaned
    assert "Antes" in cleaned and "Despues" in cleaned


def test_xml_tool_call_format_still_parses():
    text = "<tool_call>\nweb_search\n<arg_key>query</arg_key>\n<arg_value>noticias</arg_value>\n</tool_call>"

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "web_search"
    assert parsed.tool_call.args == {"query": "noticias"}


def test_harmony_style_recovery_parses_web_search():
    text = "Buscaré las noticias.\n<|tool_call_start|>[web_search(query='noticias IA hoy 11 octubre 2026', limit=5)]<|tool_call_end|>"

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "web_search"
    assert parsed.tool_call.args == {"query": "noticias IA hoy 11 octubre 2026", "limit": 5}
    assert "tool_call_start" not in parsed.thought


def test_run_176_sample_parses_web_search_from_harmony_block():
    text = """# Noticias de IA - Hoy

Intentare buscar las noticias mas actuales.

<|tool_call_start|>[web_search(query='noticias inteligencia artificial hoy 11 octubre 2026', limit=5)]<|tool_call_end|>
<dots_function_call>
<invoke_name="web_search</invoke_name>
<invoke_name>noticias inteligencia artificial 11 de octubre de 2026</parameter>
<parameter name="limit">5</parameter>
</invoke>
</dots_function_call>"""

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "web_search"
    assert parsed.tool_call.args["query"] == "noticias inteligencia artificial hoy 11 octubre 2026"
    assert parsed.tool_call.args["limit"] == 5


def test_dots_style_with_parameter_tags_parses_partial_args():
    text = '<dots_function_call><invoke_name="web_search</invoke_name><parameter name="limit">5</parameter></dots_function_call>'

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "web_search"
    assert parsed.tool_call.args == {"limit": "5"}


def test_strip_tool_blocks_removes_harmony_blocks():
    cleaned = strip_tool_blocks("A <|tool_call_start|>[f(x=1)]<|tool_call_end|> B")

    assert "tool_call_start" not in cleaned
    assert "A" in cleaned and "B" in cleaned


def test_dots_style_attribute_name_without_invoke_tag_parses():
    text = """<dots_function_call>
<dots_function_call>="news_search">
<dots_function_call>="news_search">
{"query": "inteligencia artificial", "limit": 5}"""

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "news_search"
    assert parsed.tool_call.args == {"query": "inteligencia artificial", "limit": 5}


def test_dots_style_without_args_yields_empty_args():
    text = '<dots_function_call>="get_workspace_info">'

    parsed = parse_model_output(text)

    assert parsed.tool_call is not None
    assert parsed.tool_call.name == "get_workspace_info"
    assert parsed.tool_call.args == {}
