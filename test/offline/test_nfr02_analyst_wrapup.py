"""NFR-02 RED tests for the Analyst Wrap-up site (``analysts/turn.py``).

Requirement: NFR-02 (docs/req/requirements.yaml) -- analyst closure is a scoped
call site whose final model input must be bounded.
Contract: C5 "deterministic prepared context" (docs/architecture/interface-contracts.md).

All behavioural tests call the REAL production ``take_turn``; none reimplements
the wrap-up branch and none bypasses production ``_as_text``. The model double is
a real LangChain ``Runnable`` (a ``RunnableLambda`` subclass), so LangChain
composes ``prompt | llm`` and renders the template exactly as in production.
Doubles record; they never touch a network or a real model.

Expected status against the CURRENT unmodified code:

* SHORT, TEMPLATE ERROR -- pass (controls).
* REDUCE -- FAILS: the branch invokes the model with oversized history and never
  checks size.
* REJECT -- FAILS: the branch invokes the model instead of raising
  ``ContextTooLarge``.

Scope facts confirmed from readable source (do not extend without evidence):

* ``turn.py`` wraps up when the last message is a ``HumanMessage`` equal to
  ``WRAP_UP``; it calls ``(prompt | llm).invoke(_as_text(messages))`` with
  ``tool_names`` overridden.
* ``fundamentals_analyst.py`` uses a plain ``MessagesPlaceholder("messages")`` and
  binds the other variables with ``partial`` before ``take_turn``; this file
  mirrors that shape.
* ``news_analyst.py`` was NOT readable; no claim is made about its template.
  EQUIVALENCE takes the template as input, so it stays valid either way.
* ``sentiment_analyst.py`` does not call ``take_turn`` (formats and invokes
  separately), so it is out of scope for this site.

Baseline limitation: expectations derive from the readable current ``turn.py``.
Comparison against the pinned project baseline reported locally as
``3d5ce620e7da497e09c986ef6cbc957b490de632`` (docs also cite
``9fa1196fffbcfd9de5146d2dd2869df84ab99838``) is PENDING and is not claimed.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.analysts.turn import WRAP_UP, _as_text, take_turn
from tradingagents.llm_clients.context_limit import (
    ChatMessage,
    ContextBlock,
    ContextTooLarge,
    canonical_message_bytes,
    prepare_context,
)

MAX_MESSAGE_BYTES = 65536
TICKER = "ZZTEST"
TOOL_NAME = "get_fixture_data"

# LangChain message ``type`` -> C5 role vocabulary.
_LC_TO_C5_ROLE = {"system": "system", "human": "user", "ai": "assistant"}


# ---------------------------------------------------------------------------
# Fixtures and recording double
# ---------------------------------------------------------------------------


def _wrapup_prompt() -> ChatPromptTemplate:
    """Prompt shaped like the readable analyst modules (plain placeholder)."""

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful AI assistant, collaborating with other assistants."
                " You have access to the following tools: {tool_names}."
                " Today's date is {current_date}; treat it as 'now'. {instrument_context}\n"
                "{system_message}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    return (
        prompt.partial(system_message="Synthetic analyst instructions for " + TICKER + ".")
        .partial(tool_names=TOOL_NAME)
        .partial(current_date="2026-01-05")
        .partial(instrument_context=f"The instrument to analyze is `{TICKER}`.")
    )


def _coerce_prompt_value(value) -> list:
    """Extract concrete messages from whatever the chain hands the model."""

    if hasattr(value, "to_messages"):
        return list(value.to_messages())
    return list(value)


class RecordingModel(RunnableLambda):
    """A real LangChain Runnable that records and replies without any network.

    Subclassing ``RunnableLambda`` makes ``prompt | llm`` a genuine
    ``RunnableSequence``; ``ChatPromptTemplate.__or__`` therefore converts it the
    same way it converts a production chat model. The wrapped function receives
    the ``ChatPromptValue`` and records its concrete messages.
    """

    def __init__(self) -> None:
        self.received: list[list] = []
        super().__init__(self._record)

    def _record(self, prompt_value):
        messages = _coerce_prompt_value(prompt_value)
        self.received.append(messages)
        return AIMessage(content="Synthetic final analyst report.")

    def bind_tools(self, tools):  # pragma: no cover - tool branch not under test
        return self


def _tool_call(call_id: str, payload: str = "args") -> AIMessage:
    return AIMessage(
        content=f"Looking up {payload}.",
        tool_calls=[
            {"id": call_id, "name": TOOL_NAME, "args": {"ticker": TICKER, "payload": payload}}
        ],
    )


def _history(exchanges: int, result_size: int = 40) -> list:
    """Human request, ``exchanges`` complete AI/tool exchanges, then WRAP_UP."""

    messages = [HumanMessage(content=f"Synthetic analyst request for {TICKER}.")]
    for index in range(exchanges):
        messages.append(_tool_call(f"call-{index:04d}", payload=f"exchange-{index:04d}"))
        messages.append(
            ToolMessage(
                content=f"exchange-{index:04d} " + "d" * result_size,
                tool_call_id=f"call-{index:04d}",
                name=TOOL_NAME,
            )
        )
    messages.append(HumanMessage(content=WRAP_UP))
    return messages


def _run(prompt, model, messages):
    """Invoke the REAL production wrap-up branch."""

    return take_turn(prompt, model, (), messages)


def _wrapup_override(prompt: ChatPromptTemplate) -> ChatPromptTemplate:
    """The same override production applies before formatting."""

    return prompt.partial(tool_names="none; your tool rounds are spent")


def _c5_message(message) -> ChatMessage:
    return ChatMessage(
        role=_LC_TO_C5_ROLE[message.type],
        content=message.content if isinstance(message.content, str) else str(message.content),
    )


def _c5_bytes(rendered_messages) -> int:
    return canonical_message_bytes([_c5_message(message) for message in rendered_messages])


def _joined_contents(rendered_messages) -> str:
    return "\n".join(message.content for message in rendered_messages)


def _render(prompt: ChatPromptTemplate, raw_messages) -> list:
    """ONE real rendering of the retained raw messages, as production would send it."""

    return _wrapup_override(prompt).format_messages(messages=_as_text(raw_messages))


def _projection(rendered_messages) -> list[dict]:
    return [
        {"role": _LC_TO_C5_ROLE[message.type], "content": message.content}
        for message in rendered_messages
    ]


# ---------------------------------------------------------------------------
# SHORT -- parity control (passes now and must keep passing)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nfr02_wrapup_short_prompt_is_unchanged():
    """T-NFR02-SHORT: under the cap, ``take_turn`` sends the faithful request.

    Two exchanges yield six raw history messages: initial ``HumanMessage``, two
    ``AIMessage``/``ToolMessage`` pairs, and the final ``WRAP_UP``
    ``HumanMessage``. Production ``_as_text`` rewrites tool calls as
    ``[Called ...]`` AI text and tool results as ``[get_fixture_data returned]``
    human text. The model receives the rendered system message then those six
    messages, in order, with ``WRAP_UP`` last.
    """

    prompt = _wrapup_prompt()
    model = RecordingModel()
    messages = _history(exchanges=2)
    assert len(messages) == 6

    result, report = _run(prompt, model, messages)

    assert report == "Synthetic final analyst report."
    assert result.content == report
    assert len(model.received) == 1
    received = model.received[0]

    assert received[0].type == "system"
    assert "none; your tool rounds are spent" in received[0].content
    assert len(received) == 1 + len(messages)

    history = received[1:]
    assert [message.type for message in history] == [
        "human",  # initial request
        "ai",  # exchange 0 call
        "human",  # exchange 0 result
        "ai",  # exchange 1 call
        "human",  # exchange 1 result
        "human",  # WRAP_UP
    ]
    assert history[0].content == f"Synthetic analyst request for {TICKER}."
    assert f"[Called {TOOL_NAME}(" in history[1].content
    assert "exchange-0000" in history[1].content  # tool args preserved as text
    assert history[2].content.startswith(f"[{TOOL_NAME} returned]")
    assert "exchange-0000 " in history[2].content
    assert f"[Called {TOOL_NAME}(" in history[3].content
    assert "exchange-0001" in history[3].content
    assert history[4].content.startswith(f"[{TOOL_NAME} returned]")
    assert history[5].content == WRAP_UP
    assert _c5_bytes(received) <= MAX_MESSAGE_BYTES

    # Parity with the locally formatted request (baseline comparison pending).
    assert [message.content for message in received] == [
        message.content for message in _render(prompt, messages)
    ]


# ---------------------------------------------------------------------------
# REDUCE -- RED on the current implementation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nfr02_wrapup_reduces_oversized_tool_history():
    """T-NFR02-REDUCE: oversized old tool history is reduced; newest evidence kept.

    RED today: ``take_turn`` sends the full history regardless of size. After the
    fix: one model call within the cap, oldest exchange's result absent, newest
    exchange's result present, ``WRAP_UP`` still last.
    """

    prompt = _wrapup_prompt()
    model = RecordingModel()
    messages = _history(exchanges=40, result_size=3000)

    full_rendered = _render(prompt, messages)
    assert _c5_bytes(full_rendered) > MAX_MESSAGE_BYTES, (
        "fixture precondition: the complete rendered request must exceed the cap"
    )

    _run(prompt, model, messages)

    assert len(model.received) == 1
    received = model.received[0]
    assert _c5_bytes(received) <= MAX_MESSAGE_BYTES

    body = _joined_contents(received)
    assert "exchange-0000 " not in body, "the oldest exchange must be removed first"
    assert "exchange-0039 " in body, "the newest exchange is required and must survive"
    assert received[-1].content == WRAP_UP


# ---------------------------------------------------------------------------
# REJECT -- RED on the current implementation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nfr02_wrapup_rejects_irreducible_required_evidence():
    """T-NFR02-REJECT: required evidence alone over the cap is refused unsent.

    RED today: the branch invokes the model. After the fix: typed
    ``ContextTooLarge`` with zero model calls.
    """

    prompt = _wrapup_prompt()
    model = RecordingModel()
    messages = _history(exchanges=1, result_size=MAX_MESSAGE_BYTES + 1024)

    with pytest.raises(ContextTooLarge) as excinfo:
        _run(prompt, model, messages)

    assert excinfo.value.reason_code == "CONTEXT_TOO_LARGE"
    assert model.received == [], "a rejected context must make zero model calls"


# ---------------------------------------------------------------------------
# TEMPLATE ERROR -- control through the real branch
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nfr02_wrapup_unbound_variable_fails_before_send():
    """T-NFR02 control: an unbound variable fails before the model is called.

    The template is left missing ``current_date``; production ``take_turn`` is
    invoked. Rendering fails inside the chain, so the recording body never runs.
    The error must not be ``ContextTooLarge``. Asserting the outcome (not where
    rendering happens) keeps this valid before and after the change.
    """

    partial_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "Tools: {tool_names}. Date: {current_date}."),
            MessagesPlaceholder(variable_name="messages"),
        ]
    ).partial(tool_names=TOOL_NAME)  # current_date deliberately unbound

    model = RecordingModel()
    messages = _history(exchanges=1)

    with pytest.raises(Exception) as excinfo:  # noqa: B017 - class is version-dependent
        _run(partial_prompt, model, messages)

    assert not isinstance(excinfo.value, ContextTooLarge), (
        "an unbound template variable is a template error, not CONTEXT_TOO_LARGE"
    )
    assert model.received == []


# ---------------------------------------------------------------------------
# EQUIVALENCE -- grouped optional exchange vs a single real rendering
# ---------------------------------------------------------------------------


def _blocks_with_optional_exchange(rendered, optional_exchange_index):
    """One block per rendered message, except one exchange grouped atomically.

    Rendered indices: 0 system, 1 initial request, then (call, result) pairs from
    index 2, then WRAP_UP last. The exchange at ``optional_exchange_index`` is a
    single ``required=False`` block holding both its call and its result.
    """

    blocks: list[ContextBlock] = []
    index = 0
    while index < len(rendered):
        in_exchange = index >= 2 and (index - 2) % 2 == 0 and index + 1 < len(rendered)
        if in_exchange:
            exchange = (index - 2) // 2
            blocks.append(
                ContextBlock.build(
                    f"exchange-{exchange:04d}",
                    [_c5_message(rendered[index]), _c5_message(rendered[index + 1])],
                    required=exchange != optional_exchange_index,
                )
            )
            index += 2
            continue
        blocks.append(
            ContextBlock.build(f"msg-{index:04d}", [_c5_message(rendered[index])], required=True)
        )
        index += 1
    return blocks


@pytest.mark.unit
def test_nfr02_wrapup_blocks_match_formatted_messages():
    """T-NFR02-EQUIVALENCE: grouped C5 blocks equal the real rendered request.

    Asserts (a) the under-cap representation is unchanged, (b) the oldest
    exchange is removed atomically with its single group id reported, and
    (c) ``prepare_context(...).as_provider_messages()`` equals the projection of
    ONE real ``format_messages(...)`` of the retained raw messages.
    """

    prompt = _wrapup_prompt()
    messages = _history(exchanges=3)  # 1 request + 3 exchanges + WRAP_UP
    rendered = _render(prompt, messages)
    assert len(rendered) == 1 + 1 + 6 + 1  # system, request, 3x(call, result), WRAP_UP

    # (a) Under the cap: nothing dropped, representation unchanged.
    under_blocks = _blocks_with_optional_exchange(rendered, optional_exchange_index=0)
    prepared_under = prepare_context(under_blocks, max_message_bytes=MAX_MESSAGE_BYTES)
    assert prepared_under.dropped_group_ids == ()
    assert prepared_under.as_provider_messages() == _projection(rendered)

    # (b) Forced removal of exactly the oldest optional exchange.
    blocks = _blocks_with_optional_exchange(rendered, optional_exchange_index=0)
    full_bytes = canonical_message_bytes(
        [message for block in blocks for message in block.messages]
    )
    required_bytes = canonical_message_bytes(
        [message for block in blocks if block.required for message in block.messages]
    )
    assert required_bytes < full_bytes, "the optional exchange must contribute bytes"
    cap = full_bytes - 1
    assert cap >= required_bytes, "cap must still admit the required set"

    prepared_reduced = prepare_context(blocks, max_message_bytes=cap)
    assert prepared_reduced.dropped_group_ids == ("exchange-0000",)
    assert prepared_reduced.message_bytes <= cap

    # Atomicity: neither the removed call nor its result survives.
    reduced_body = "\n".join(
        message["content"] for message in prepared_reduced.as_provider_messages()
    )
    assert "exchange-0000 " not in reduced_body
    assert "exchange-0001 " in reduced_body

    # (c) Equals ONE real rendering of the retained raw messages.
    retained_raw = [messages[0], *messages[3:]]
    real_reduced = _render(prompt, retained_raw)
    assert prepared_reduced.as_provider_messages() == _projection(real_reduced)
    assert real_reduced[-1].content == WRAP_UP
    assert len(real_reduced) == len(rendered) - 2
