"""NFR-02 C5 acceptance tests for tool-call/result pairing.

Requirement: NFR-02 (docs/req/requirements.yaml).
Contract: C5 "deterministic prepared context" (docs/architecture/interface-contracts.md):
"a tool-call/result pair is indivisible; if a member is required, preserve the
whole pair. Text-wrapped tools retain name, arguments and corresponding result."
Case: T-NFR02-PAIRING (docs/code-governance/verification-constraints.md).

Offline and deterministic: synthetic fixtures and standard-library doubles only;
no network, no model request. The cap values used here are test thresholds.

Scope note: the scoped text sites (analyst closure, neutral debater) send one
prompt string and contain no tool exchange in v1, so pairing is verified at the
structured ``prepare_context`` boundary that the same C5 record set defines.
Whether a future site actually emits tool exchanges there is an integration
question outside this test file.
"""

import pytest

from tradingagents.llm_clients.context_limit import (
    ChatMessage,
    ContextBlock,
    canonical_message_bytes,
    prepare_context,
)

# Small caps keep these fixtures readable while exercising real reduction.
TIGHT_CAP = 400


def _tool_call(call_id: str, name: str = "get_fixture_data") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": '{"ticker": "ZZTEST"}'},
    }


def _pair_block(group_id: str, call_id: str, *, required: bool, payload: str = "ok") -> ContextBlock:
    """One assistant tool call plus its matching tool result, in one block."""

    return ContextBlock.build(
        group_id,
        [
            ChatMessage(role="assistant", content="", tool_calls=[_tool_call(call_id)]),
            ChatMessage(role="tool", content=payload, tool_call_id=call_id),
        ],
        required=required,
    )


def _filler_block(group_id: str, *, required: bool, size: int = 200) -> ContextBlock:
    return ContextBlock.build(
        group_id,
        [ChatMessage(role="user", content="f" * size)],
        required=required,
    )


def _contents(blocks) -> list[str]:
    return [message.content for message in blocks]


# ---------------------------------------------------------------------------
# Preserved when the request fits
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nfr02_pairing_complete_pair_preserved_when_request_fits():
    """T-NFR02-PAIRING: a complete pair survives unchanged below the cap."""

    pair = _pair_block("exchange", "call-1", required=False)
    blocks = [_filler_block("head", required=True, size=20), pair]

    prepared = prepare_context(blocks, max_message_bytes=65536)

    assert prepared.dropped_group_ids == ()
    assert len(prepared.messages) == 3
    call_message, result_message = prepared.messages[1], prepared.messages[2]
    assert call_message.tool_calls[0]["id"] == "call-1"
    assert call_message.tool_calls[0]["function"]["name"] == "get_fixture_data"
    assert call_message.tool_calls[0]["function"]["arguments"] == '{"ticker": "ZZTEST"}'
    assert result_message.role == "tool"
    assert result_message.tool_call_id == "call-1"
    assert result_message.content == "ok"


@pytest.mark.unit
def test_nfr02_pairing_result_follows_call_in_serialized_order():
    """T-NFR02-PAIRING: the result is emitted after its call, not reordered."""

    prepared = prepare_context(
        [_pair_block("exchange", "call-2", required=True)],
        max_message_bytes=65536,
    )
    provider_messages = prepared.as_provider_messages()
    assert [message["role"] for message in provider_messages] == ["assistant", "tool"]
    assert provider_messages[0]["tool_calls"][0]["id"] == provider_messages[1]["tool_call_id"]


# ---------------------------------------------------------------------------
# Removed atomically when reduction is needed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nfr02_pairing_optional_pair_removed_atomically_when_reduced():
    """T-NFR02-PAIRING: reducing drops the call and result together, never one."""

    required = _filler_block("required", required=True, size=20)
    optional_pair = _pair_block("exchange", "call-old", required=False, payload="r" * 300)

    full = prepare_context([required, optional_pair], max_message_bytes=65536)
    reduced = prepare_context([required, optional_pair], max_message_bytes=full.message_bytes - 1)

    assert reduced.dropped_group_ids == ("exchange",)
    assert _contents(reduced.messages) == _contents(required.messages)
    serialized = reduced.as_provider_messages()
    assert [message["role"] for message in serialized] == ["user"]
    assert all("call-old" not in str(message) for message in serialized)


@pytest.mark.unit
def test_nfr02_pairing_older_optional_pair_removed_before_newer_optional_pair():
    """T-NFR02-PAIRING: atomic removal still follows oldest-first order."""

    required = _filler_block("required", required=True, size=20)
    old_pair = _pair_block("exchange-old", "call-old", required=False, payload="o" * 150)
    new_pair = _pair_block("exchange-new", "call-new", required=False, payload="n" * 150)

    full = prepare_context([required, old_pair, new_pair], max_message_bytes=65536)
    reduced = prepare_context(
        [required, old_pair, new_pair], max_message_bytes=full.message_bytes - 1
    )

    assert reduced.dropped_group_ids == ("exchange-old",)
    ids = [
        call["id"]
        for message in reduced.as_provider_messages()
        for call in (message.get("tool_calls") or [])
    ]
    assert ids == ["call-new"]
    assert any(message.get("tool_call_id") == "call-new" for message in reduced.as_provider_messages())


# ---------------------------------------------------------------------------
# Required pairing evidence is never partially removed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nfr02_pairing_required_pair_survives_reduction_intact():
    """T-NFR02-PAIRING: reduction never drops half of a required pair."""

    required_pair = _pair_block("exchange-required", "call-req", required=True, payload="payload")
    optional_filler = _filler_block("history", required=False, size=300)

    full = prepare_context([required_pair, optional_filler], max_message_bytes=65536)
    reduced = prepare_context(
        [required_pair, optional_filler], max_message_bytes=full.message_bytes - 1
    )

    assert reduced.dropped_group_ids == ("history",)
    serialized = reduced.as_provider_messages()
    assert [message["role"] for message in serialized] == ["assistant", "tool"]
    assert serialized[0]["tool_calls"][0]["id"] == "call-req"
    assert serialized[1]["tool_call_id"] == "call-req"
    assert serialized[1]["content"] == "payload"


@pytest.mark.unit
def test_nfr02_pairing_required_pair_is_measured_and_refused_not_trimmed():
    """T-NFR02-PAIRING: a required pair that cannot fit is refused, not altered."""

    required_pair = _pair_block("exchange-required", "call-req", required=True, payload="p" * 500)
    required_bytes = canonical_message_bytes(required_pair.messages)

    with pytest.raises(ContextTooLargeAlias) as excinfo:
        prepare_context([required_pair], max_message_bytes=required_bytes - 1)
    assert excinfo.value.reason_code == "CONTEXT_TOO_LARGE"


# ---------------------------------------------------------------------------
# Malformed pairings are rejected by validation
# ---------------------------------------------------------------------------


def _pair_blocks(messages, *, required: bool = True, group_id: str = "exchange"):
    return [ContextBlock.build(group_id, messages, required=required)]


@pytest.mark.unit
def test_nfr02_pairing_rejects_call_without_result():
    """T-NFR02-PAIRING: a call with no result is a malformed pair."""

    blocks = _pair_blocks([ChatMessage(role="assistant", content="", tool_calls=[_tool_call("call-1")])])
    with pytest.raises(ValueError, match="no paired tool result"):
        prepare_context(blocks, max_message_bytes=65536)


@pytest.mark.unit
def test_nfr02_pairing_rejects_result_without_call():
    """T-NFR02-PAIRING: an orphan tool result is rejected."""

    blocks = _pair_blocks([ChatMessage(role="tool", content="orphan", tool_call_id="call-x")])
    with pytest.raises(ValueError, match="without a paired tool call"):
        prepare_context(blocks, max_message_bytes=65536)


@pytest.mark.unit
def test_nfr02_pairing_rejects_duplicate_call_id():
    """T-NFR02-PAIRING: the same call id twice is rejected."""

    blocks = _pair_blocks(
        [
            ChatMessage(role="assistant", content="", tool_calls=[_tool_call("call-1")]),
            ChatMessage(role="tool", content="a", tool_call_id="call-1"),
            ChatMessage(role="assistant", content="", tool_calls=[_tool_call("call-1")]),
        ]
    )
    with pytest.raises(ValueError, match="duplicate tool call id"):
        prepare_context(blocks, max_message_bytes=65536)


@pytest.mark.unit
def test_nfr02_pairing_rejects_duplicate_result():
    """T-NFR02-PAIRING: two results for one call id is rejected."""

    blocks = _pair_blocks(
        [
            ChatMessage(role="assistant", content="", tool_calls=[_tool_call("call-1")]),
            ChatMessage(role="tool", content="a", tool_call_id="call-1"),
            ChatMessage(role="tool", content="b", tool_call_id="call-1"),
        ]
    )
    with pytest.raises(ValueError, match="duplicate tool result"):
        prepare_context(blocks, max_message_bytes=65536)


@pytest.mark.unit
def test_nfr02_pairing_rejects_mismatched_result_id():
    """T-NFR02-PAIRING: a result id that matches no call is rejected."""

    blocks = _pair_blocks(
        [
            ChatMessage(role="assistant", content="", tool_calls=[_tool_call("call-1")]),
            ChatMessage(role="tool", content="a", tool_call_id="call-2"),
        ]
    )
    with pytest.raises(ValueError):
        prepare_context(blocks, max_message_bytes=65536)


@pytest.mark.unit
def test_nfr02_pairing_rejects_pair_split_across_blocks():
    """T-NFR02-PAIRING: a call and its result in different blocks is rejected."""

    blocks = [
        ContextBlock.build(
            "call-block",
            [ChatMessage(role="assistant", content="", tool_calls=[_tool_call("call-1")])],
            required=True,
        ),
        ContextBlock.build(
            "result-block",
            [ChatMessage(role="tool", content="a", tool_call_id="call-1")],
            required=True,
        ),
    ]
    with pytest.raises(ValueError, match="different blocks"):
        prepare_context(blocks, max_message_bytes=65536)


@pytest.mark.unit
def test_nfr02_pairing_rejects_result_before_call():
    """T-NFR02-PAIRING: chronological order is enforced."""

    blocks = _pair_blocks(
        [
            ChatMessage(role="tool", content="early", tool_call_id="call-1"),
            ChatMessage(role="assistant", content="", tool_calls=[_tool_call("call-1")]),
        ]
    )
    with pytest.raises(ValueError, match="appears before its call"):
        prepare_context(blocks, max_message_bytes=65536)


@pytest.mark.unit
def test_nfr02_pairing_rejects_tool_message_without_call_id():
    """T-NFR02-PAIRING: a tool message must carry tool_call_id."""

    blocks = _pair_blocks(
        [
            ChatMessage(role="assistant", content="", tool_calls=[_tool_call("call-1")]),
            ChatMessage(role="tool", content="a"),
        ]
    )
    with pytest.raises(ValueError, match="must carry a nonempty tool_call_id"):
        prepare_context(blocks, max_message_bytes=65536)


# Local alias so the refusal test reads clearly without importing the class twice.
from tradingagents.llm_clients.context_limit import ContextTooLarge as ContextTooLargeAlias  # noqa: E402
