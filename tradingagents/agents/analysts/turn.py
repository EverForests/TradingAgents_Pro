"""One turn of a tool-using analyst, and its last turn once its tool rounds are spent."""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tradingagents.llm_clients.budget_transport import scoped_context_limit
from tradingagents.llm_clients.context_limit import (
    ChatMessage,
    ContextBlock,
    prepare_context,
)

WRAP_UP = (
    "You have used every tool round this report allows. Write your final report "
    "now from the tool results above, and say which data you could not retrieve."
)

# LangChain message ``type`` -> C5 role vocabulary used by the canonical message
# measurement (C5: the final provider-facing message array).
_LC_TO_C5_ROLE = {"system": "system", "human": "user", "ai": "assistant"}

# Group ids used by wrap-up preparation. Stable ids let a dropped group be traced
# back to the exchange it represents.
_SYSTEM_GROUP = "system"
_REQUEST_GROUP = "request"
_WRAP_UP_GROUP = "wrap-up"
_EXCHANGE_PREFIX = "exchange-"
_HISTORY_PREFIX = "history-"


def take_turn(prompt, llm, tools, messages):
    """The analyst's reply and its report, which stays empty while it calls tools.

    Told to wrap up, it answers without tools: a model offered tools may call one
    whatever it is told. Its earlier calls and their results reach it as text,
    since a provider may refuse a history holding tool calls when none are bound.
    """
    if messages and isinstance(messages[-1], HumanMessage) and messages[-1].content == WRAP_UP:
        # The prompt lists the tools it offers; a model told of tools it cannot
        # call may still try, and some providers then answer with nothing.
        prompt = prompt.partial(tool_names="none; your tool rounds are spent")
        # NFR-02 / C5: render the complete request once, measure it as C5 blocks and
        # send only what fits. Required: system instructions, the initial request,
        # the newest complete tool exchange, and this wrap-up instruction.
        retained_messages = _prepared_wrap_up_messages(prompt, messages)
        # Marked for the C5 size check only across the send itself: the check
        # runs before the C4 reservation at the transport.
        with scoped_context_limit():
            result = (prompt | llm).invoke(_as_text(retained_messages))
        return result, result.content
    result = (prompt | llm.bind_tools(tools)).invoke(messages)
    return result, "" if result.tool_calls else result.content


def _as_text(messages):
    """The history with its tool calls and tool results written out as plain messages."""
    written = []
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            said = message.content if isinstance(message.content, str) else ""
            calls = "; ".join(f"{c['name']}({json.dumps(c['args'], default=str)})" for c in message.tool_calls)
            written.append(AIMessage(content=f"{said}\n[Called {calls}]".strip()))
        elif isinstance(message, ToolMessage):
            written.append(HumanMessage(content=f"[{message.name or 'Tool'} returned]\n{message.content}"))
        else:
            written.append(message)
    return written


def _prepared_wrap_up_messages(prompt, messages):
    """Return the raw history to send so the rendered request fits the C5 cap.

    The complete prompt is rendered with ``format_messages`` (system message
    included) and expressed as C5 ``ContextBlock`` records covering every rendered
    message exactly once. Sizing and reduction use the public ``prepare_context``.
    When nothing needs removing, ``messages`` itself is returned unchanged.

    Requirement: NFR-02. Contract: C5. Invariant link: only optional discussion may
    be removed; required evidence is preserved and refusal precedes any send.
    """
    exchanges = _tool_exchanges(messages)
    formatted = prompt.format_messages(messages=_as_text(messages))

    blocks, group_for_message = _wrap_up_blocks(formatted, messages, exchanges)
    _assert_full_coverage(blocks, formatted)

    prepared = prepare_context(blocks)
    if not prepared.dropped_group_ids:
        return messages

    dropped = set(prepared.dropped_group_ids)
    return [
        message
        for index, message in enumerate(messages)
        if _group_prefix_for(index, exchanges) not in dropped
    ]


def _group_prefix_for(index, exchanges):
    """Group id owning the raw message at ``index`` (used for retention)."""

    for exchange_index, (start, end) in enumerate(exchanges):
        if start <= index <= end:
            return f"{_EXCHANGE_PREFIX}{exchange_index:04d}"
    return None


def _tool_exchanges(messages):
    """Validated spans of complete tool exchanges in the raw history.

    An exchange is an ``AIMessage`` carrying one or more ``tool_calls`` plus every
    ``ToolMessage`` immediately following it, which must resolve those calls. The
    whole span is one atomic unit, even when a single call declares several tools.

    Raises:
        ValueError: an orphan, duplicate or mismatched tool result appears; a
            declared call id has no result; or a tool message carries non-string
            content that text wrapping cannot represent faithfully.

    Returns:
        ``(start, end)`` inclusive tuples in original order.
    """
    exchanges = []
    seen_call_ids = set()
    resolved_result_ids = set()
    position = 0

    while position < len(messages):
        message = messages[position]

        if isinstance(message, AIMessage) and message.tool_calls:
            if not isinstance(message.content, str):
                raise ValueError(
                    f"tool-call message at position {position} has non-string content; "
                    "text wrapping would diverge from the sent request"
                )
            declared = []
            for call in message.tool_calls:
                call_id = call.get("id")
                if not isinstance(call_id, str) or not call_id:
                    raise ValueError(
                        f"tool call at position {position} has no id; pairs cannot be verified"
                    )
                if call_id in seen_call_ids:
                    raise ValueError(f"duplicate tool call id {call_id!r}")
                seen_call_ids.add(call_id)
                declared.append(call_id)

            start = position
            position += 1
            while position < len(messages) and isinstance(messages[position], ToolMessage):
                result = messages[position]
                result_id = result.tool_call_id
                if result_id in resolved_result_ids:
                    raise ValueError(f"duplicate tool result for id {result_id!r}")
                if result_id not in declared:
                    raise ValueError(
                        f"tool result at position {position} has id {result_id!r}, which no "
                        "open call declared in this exchange"
                    )
                if not isinstance(result.content, str):
                    raise ValueError(
                        f"tool result at position {position} has non-string content; "
                        "text wrapping would diverge from the sent request"
                    )
                resolved_result_ids.add(result_id)
                position += 1

            missing = [call_id for call_id in declared if call_id not in resolved_result_ids]
            if missing:
                raise ValueError(
                    f"tool call(s) {missing!r} have no matching result; refusing to send a "
                    "partial exchange"
                )
            exchanges.append((start, position - 1))
            continue

        if isinstance(message, ToolMessage):
            raise ValueError(
                f"tool result at position {position} has no preceding tool call; "
                "refusing to separate evidence"
            )
        position += 1

    return exchanges


def _wrap_up_blocks(formatted, messages, exchanges):
    """C5 blocks covering every rendered message exactly once, in order.

    The block layout is derived from the rendered list, so coverage cannot depend
    on assumptions about the template. Grouping decides only which adjacent
    rendered messages share a block:

    * the system message -> required ``system`` group;
    * the initial request -> required ``request`` group;
    * each complete tool exchange -> one atomic group, required only for the newest;
    * the final wrap-up instruction -> required ``wrap-up`` group;
    * any other historical message -> its own required ``history-NNNN`` group.

    Ordinary history stays required here: this release removes optional discussion
    only at the neutral-risk site, where turns are explicitly marked optional. The
    analyst history is the analyst's own evidence, so it is not silently dropped.
    """
    c5_messages = [_to_c5_message(message, position) for position, message in enumerate(formatted)]
    blocks = []

    history_count = 0
    system_seen = False
    rendered_to_raw = _rendered_to_raw_map(len(formatted), len(messages))

    for rendered_position, c5_message in enumerate(c5_messages):
        raw_index = rendered_to_raw[rendered_position]
        if raw_index is None:
            # System message (no raw counterpart).
            if system_seen:
                raise ValueError("unexpected additional system message in rendered prompt")
            system_seen = True
            blocks.append(ContextBlock.build(_SYSTEM_GROUP, [c5_message], required=True))
            continue

        exchange_group = _group_prefix_for(raw_index, exchanges)
        if raw_index == 0:
            blocks.append(ContextBlock.build(_REQUEST_GROUP, [c5_message], required=True))
        elif exchange_group is not None:
            exchange_index = int(exchange_group.rsplit("-", 1)[1])
            if blocks and blocks[-1].group_id == exchange_group:
                blocks[-1] = ContextBlock.build(
                    exchange_group,
                    [*blocks[-1].messages, c5_message],
                    required=blocks[-1].required,
                )
            else:
                blocks.append(
                    ContextBlock.build(
                        exchange_group,
                        [c5_message],
                        required=exchange_index == len(exchanges) - 1,
                    )
                )
        elif raw_index == len(messages) - 1:
            blocks.append(ContextBlock.build(_WRAP_UP_GROUP, [c5_message], required=True))
        else:
            blocks.append(
                ContextBlock.build(f"{_HISTORY_PREFIX}{history_count:04d}", [c5_message], required=True)
            )
            history_count += 1

    return blocks, rendered_to_raw


def _rendered_to_raw_map(rendered_count, raw_count):
    """Map each rendered position to the raw message it came from, or None.

    ``_as_text`` maps one raw message to exactly one rendered history message, so
    the rendered list is ``[*system, *_as_text(messages)]``. Any extra rendered
    entries beyond ``raw_count`` must therefore be leading system messages.
    """
    system_count = rendered_count - raw_count
    if system_count < 0:
        raise ValueError(
            "rendered prompt is shorter than the raw history; template shape is unsupported"
        )
    return [None] * system_count + list(range(raw_count))


def _assert_full_coverage(blocks, formatted):
    """Fail closed unless blocks reproduce the rendered request message for message."""

    flattened = [message for block in blocks for message in block.messages]
    expected = [_to_c5_message(message, position) for position, message in enumerate(formatted)]
    if flattened != expected:
        raise ValueError(
            "prepared blocks do not reproduce the rendered request; refusing to measure a "
            "representation that differs from what would be sent"
        )


def _to_c5_message(message, position):
    """Project a LangChain message onto the C5 provider-facing record.

    Only string content is representable: ``_as_text`` and the provider both treat
    content as text here, and coercing blocks with ``str`` would make the measured
    bytes differ from the sent request.
    """
    if not isinstance(message.content, str):
        raise ValueError(
            f"message at rendered position {position} has non-string content "
            f"({type(message.content).__name__}); refusing to measure a lossy projection"
        )
    role = _LC_TO_C5_ROLE.get(message.type)
    if role is None:
        raise ValueError(
            f"message at rendered position {position} has unsupported type {message.type!r}"
        )
    return ChatMessage(role=role, content=message.content)
