"""Text protocol for agent tool calls.

The model emits tool calls as a delimited block:

    <<<TOOL
    {"tool": "read_file", "args": {"path": "README.md"}}
    TOOL>>>

Everything outside the block is treated as the model's thought/final text.
The protocol is plain text so it works with any model, including local
llama.cpp servers without native function calling.
"""

import json
import re
from dataclasses import dataclass


PROTOCOL_MARKER_OPEN = "<<<TOOL"
PROTOCOL_MARKER_CLOSE = "TOOL>>>"

_TOOL_BLOCK_PATTERN = re.compile(
    re.escape(PROTOCOL_MARKER_OPEN) + r"\s*(.*?)\s*" + re.escape(PROTOCOL_MARKER_CLOSE),
    re.DOTALL,
)

_JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)

_XML_TOOL_PATTERN = re.compile(r"<tool_call>\s*([A-Za-z0-9_.\-]+)\s*(.*?)</tool_call>", re.DOTALL)
_XML_ARG_PATTERN = re.compile(r"<arg_key>(.*?)</arg_key>\s*<arg_value>(.*?)</arg_value>", re.DOTALL)

PROTOCOL_INSTRUCTIONS = (
    "When you need to use a tool, emit exactly one block in this format:\n"
    "\n"
    + PROTOCOL_MARKER_OPEN
    + '\n{"tool": "<tool_name>", "args": {<arguments as JSON>}}\n'
    + PROTOCOL_MARKER_CLOSE
    + "\n\nRules:\n"
    "- Use at most one tool block per response.\n"
    "- The block may span multiple lines or be written on a single line; both are accepted.\n"
    '- The JSON must have "tool" (string) and "args" (object).\n'
    "- Keep argument values short: never embed code, HTML, or long documents inside the JSON block; describe them briefly instead.\n"
    "- Everything outside the block is shown to the user as your reasoning or answer.\n"
    "- Do not wrap the block in code fences or add text inside the markers.\n"
    "- When you have enough information, answer the user directly without any tool block."
)


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict


@dataclass(frozen=True)
class ParsedOutput:
    thought: str
    tool_call: ToolCall | None
    parse_error: str | None
    tool_calls: tuple[ToolCall, ...] = ()

    def calls(self) -> list[ToolCall]:
        if self.tool_calls:
            return list(self.tool_calls)
        return [self.tool_call] if self.tool_call else []


def strip_tool_blocks(text: str) -> str:
    """Removes tool-call markers (complete or dangling) from a stored message.

    Keeps conversation history clean so models do not imitate raw markers.
    """
    cleaned = _TOOL_BLOCK_PATTERN.sub("", text)
    cleaned = _XML_TOOL_PATTERN.sub("", cleaned)
    if PROTOCOL_MARKER_OPEN in cleaned:
        cleaned = cleaned.split(PROTOCOL_MARKER_OPEN, 1)[0]
    if PROTOCOL_MARKER_CLOSE in cleaned:
        cleaned = cleaned.split(PROTOCOL_MARKER_CLOSE, 1)[-1]
    return cleaned.strip()


def parse_model_output(text: str) -> ParsedOutput:
    match = _TOOL_BLOCK_PATTERN.search(text)
    if not match:
        if PROTOCOL_MARKER_OPEN in text:
            return _recover_unterminated_tool_block(text)
        xml_call = _parse_xml_tool_call(text)
        if xml_call is not None:
            return xml_call
        return ParsedOutput(thought=text.strip(), tool_call=None, parse_error=None)

    payload = match.group(1).strip()
    thought = (text[: match.start()] + text[match.end() :]).strip()
    return _build_tool_call(text, payload, thought)


def _parse_xml_tool_call(text: str) -> ParsedOutput | None:
    """Parses llama.cpp native tool-call format (one or many blocks per response):

    <tool_call>
    tool_name
    <arg_key>key</arg_key>
    <arg_value>value</arg_value>
    </tool_call>
    """
    matches = list(_XML_TOOL_PATTERN.finditer(text))
    if not matches:
        return None
    calls: list[ToolCall] = []
    for match in matches:
        tool_name = match.group(1).strip()
        if not tool_name:
            continue
        args = {key.strip(): value.strip() for key, value in _XML_ARG_PATTERN.findall(match.group(2))}
        calls.append(ToolCall(name=tool_name, args=args))
    if not calls:
        return None
    thought = _XML_TOOL_PATTERN.sub("", text).strip()
    return ParsedOutput(thought=thought, tool_call=calls[0], parse_error=None, tool_calls=tuple(calls))


def _recover_unterminated_tool_block(text: str) -> ParsedOutput:
    """Small local models sometimes drop the closing marker; recover the JSON after <<<TOOL."""
    remainder = text.split(PROTOCOL_MARKER_OPEN, 1)[1]
    json_match = _JSON_OBJECT_PATTERN.search(remainder)
    payload = json_match.group(0) if json_match else remainder.strip()
    thought = text.split(PROTOCOL_MARKER_OPEN, 1)[0].strip()
    return _build_tool_call(text, payload, thought)


def _escape_raw_strings(text: str) -> str:
    """Escapes raw newlines/tabs and content-level double quotes inside JSON string values."""
    out: list[str] = []
    in_string = False
    escaped = False
    length = len(text)
    for index, char in enumerate(text):
        if escaped:
            out.append(char)
            escaped = False
            continue
        if in_string and char == "\\":
            out.append(char)
            escaped = True
            continue
        if char == '"':
            if in_string:
                lookahead = index + 1
                while lookahead < length and text[lookahead] in " \t\r\n":
                    lookahead += 1
                next_char = text[lookahead] if lookahead < length else ""
                if next_char and next_char not in ':,}]"':
                    out.append('\\"')
                    continue
            in_string = not in_string
            out.append(char)
            continue
        if in_string and char == "\n":
            out.append("\\n")
            continue
        if in_string and char == "\r":
            continue
        if in_string and char == "\t":
            out.append("\\t")
            continue
        out.append(char)
    return "".join(out)


def _repair_payload(payload: str) -> str:
    cleaned = payload.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned[:4].lower() == "json":
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    return _escape_raw_strings(cleaned)


def _build_tool_call(text: str, payload: str, thought: str) -> ParsedOutput:  # noqa: ARG001
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        try:
            data = json.loads(_repair_payload(payload))
        except json.JSONDecodeError as error:
            return ParsedOutput(
                thought=thought,
                tool_call=None,
                parse_error=f"Invalid JSON in tool block: {error.msg}",
            )

    if not isinstance(data, dict) or not isinstance(data.get("tool"), str) or not data["tool"].strip():
        return ParsedOutput(
            thought=thought,
            tool_call=None,
            parse_error='Tool block JSON must include "tool" as a non-empty string.',
        )

    args = data.get("args", {})
    if not isinstance(args, dict):
        return ParsedOutput(
            thought=thought,
            tool_call=None,
            parse_error='"args" must be a JSON object.',
        )

    return ParsedOutput(
        thought=thought,
        tool_call=ToolCall(name=data["tool"].strip(), args=args),
        parse_error=None,
    )
