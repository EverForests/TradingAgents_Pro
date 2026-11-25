"""NFR-02 C5 acceptance tests for short input, UTF-8 measurement and ordering.

Requirement: NFR-02 (docs/req/requirements.yaml).
Contract: C5 "deterministic prepared context" (docs/architecture/interface-contracts.md);
cases T-NFR02-SHORT, T-NFR02-UTF8, T-NFR02-ORDER as fixed in
docs/code-governance/verification-constraints.md.

Offline and deterministic: fixed synthetic fixtures, standard-library doubles, no
network, no real model request. The configurable cap used here is a *test
threshold*, not an empirically justified production optimum.

PARITY REFERENCE LIMITATION (retained deliberately): the neutral-debater
prompt-parity tests below compare the integrated node's request against a literal
reference transcribed in this session from the pre-integration
``tradingagents/agents/risk_mgmt/neutral_debator.py`` source. Upstream baseline
``9fa1196fffbcfd9de5146d2dd2869df84ab99838`` is not readable by the test author,
so this literal is a session-derived reference and **has not yet been
independently compared with the pinned baseline commit**. Replacing it with the
baseline blob is an open evidence item for human verification.
"""

import json
from types import SimpleNamespace

import pytest

from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.llm_clients.context_limit import (
    ChatMessage,
    ContextBlock,
    ContextTooLarge,
    TextContextParts,
    canonical_message_bytes,
    prepare_context,
    prepare_text_context,
)

# Configurable test threshold (C5 acceptance configuration), not a production optimum.
MAX_MESSAGE_BYTES = 65536

TICKER = "ZZTEST"

# ---------------------------------------------------------------------------
# Reference prompt template, transcribed from the pre-integration neutral node.
# This is a frozen fixture, not a model call and not an upstream-commit oracle.
# ---------------------------------------------------------------------------
_REFERENCE_TEMPLATE = (
    "As the Neutral Risk Analyst, your role is to provide a balanced perspective, weighing "
    "both the potential benefits and risks of the trader's decision or plan. You prioritize a "
    "well-rounded approach, evaluating the upsides and downsides while factoring in broader "
    "market trends, potential economic shifts, and diversification strategies.Here is the "
    "trader's decision:\n"
    "\n"
    "{trader_decision}\n"
    "\n"
    "Your task is to challenge both the Aggressive and Conservative Analysts, pointing out "
    "where each perspective may be overly optimistic or overly cautious. Use insights from the "
    "following data sources to support a moderate, sustainable strategy to adjust the trader's "
    "decision:\n"
    "\n"
    "{instrument_context}\n"
    "{portfolio_context}\n"
    "Market Research Report: {market}\n"
    "Social Media Sentiment Report: {sentiment}\n"
    "Latest World Affairs Report: {news}\n"
    "Company Fundamentals Report: {fundamentals}\n"
    "Here is the current conversation history: {history} Here is the last response from the "
    "aggressive analyst: {aggressive} Here is the last response from the conservative analyst: "
    "{conservative}. If there are no responses from the other viewpoints yet, present your own "
    "argument based on the available data.\n"
    "\n"
    "Engage actively by analyzing both sides critically, addressing weaknesses in the "
    "aggressive and conservative arguments to advocate for a more balanced approach. Challenge "
    "each of their points to illustrate why a moderate risk strategy might offer the best of "
    "both worlds, providing growth potential while safeguarding against extreme volatility. "
    "Focus on debating rather than simply presenting data, aiming to show that a balanced view "
    "can lead to the most reliable outcomes. Output conversationally as if you are speaking "
    "without any special formatting."
    "{language}"
)


def _reference_neutral_prompt(
    *,
    trader_decision: str,
    instrument_context: str,
    portfolio_context: str,
    market: str,
    sentiment: str,
    news: str,
    fundamentals: str,
    history: str,
    aggressive: str,
    conservative: str,
    language: str = "",
) -> str:
    return _REFERENCE_TEMPLATE.format(
        trader_decision=trader_decision,
        instrument_context=instrument_context,
        portfolio_context=portfolio_context,
        market=market,
        sentiment=sentiment,
        news=news,
        fundamentals=fundamentals,
        history=history,
        aggressive=aggressive,
        conservative=conservative,
        language=language,
    )


class RecordingLLM:
    """Standard-library recording model double."""

    def __init__(self, reply: str = "Synthetic neutral argument.") -> None:
        self._reply = reply
        self.calls: list[object] = []

    def invoke(self, messages):
        self.calls.append(messages)
        return SimpleNamespace(content=self._reply)


def _state(*, history: str = "") -> dict:
    """Fixed synthetic AgentState for the neutral node."""

    return {
        "company_of_interest": TICKER,
        "asset_type": "stock",
        "instrument_context": f"The instrument to analyze is `{TICKER}`.",
        "portfolio_context": "Portfolio context: not provided in this synthetic run.",
        "market_report": "Synthetic market report.",
        "sentiment_report": "Synthetic sentiment report.",
        "news_report": "Synthetic news report.",
        "fundamentals_report": "Synthetic fundamentals report.",
        "trader_investment_plan": f"Synthetic trader plan for {TICKER}.",
        "risk_debate_state": {
            "history": history,
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "latest_speaker": "Aggressive",
            "current_aggressive_response": "Synthetic aggressive opening.",
            "current_conservative_response": "Synthetic conservative opening.",
            "current_neutral_response": "",
            "count": 1,
        },
    }


def _sent_prompt(state: dict) -> str:
    llm = RecordingLLM()
    create_neutral_debator(llm)(state)
    assert len(llm.calls) == 1, f"expected exactly one model call, got {len(llm.calls)}"
    sent = llm.calls[0]
    assert isinstance(sent, str), "the node must keep the string llm.invoke interface"
    return sent


# ---------------------------------------------------------------------------
# T-NFR02-SHORT
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_nfr02_short_structured_request_passes_unchanged():
    """T-NFR02-SHORT: below the cap, prepare_context returns identical messages."""

    blocks = [
        ContextBlock.build("a", [ChatMessage(role="user", content="alpha")], required=True),
        ContextBlock.build("b", [ChatMessage(role="user", content="beta")], required=False),
    ]
    prepared = prepare_context(blocks, max_message_bytes=MAX_MESSAGE_BYTES)

    assert prepared.status == "READY"
    assert [message.content for message in prepared.messages] == ["alpha", "beta"]
    assert prepared.dropped_group_ids == ()
    assert prepared.message_bytes == prepared.original_message_bytes


@pytest.mark.unit
def test_nfr02_short_neutral_prompt_matches_reference():
    """T-NFR02-SHORT parity: the short neutral request equals the frozen reference.

    The reference is session-transcribed (see module docstring); this does not
    establish parity with the pinned upstream commit.
    """

    state = _state()
    sent = _sent_prompt(state)

    expected = _reference_neutral_prompt(
        trader_decision=state["trader_investment_plan"],
        instrument_context=state["instrument_context"],
        portfolio_context=state["portfolio_context"],
        market=state["market_report"],
        sentiment=state["sentiment_report"],
        news=state["news_report"],
        fundamentals=state["fundamentals_report"],
        history="",
        aggressive="Synthetic aggressive opening.",
        conservative="Synthetic conservative opening.",
        language="",
    )
    assert sent == expected


@pytest.mark.unit
def test_nfr02_short_neutral_prompt_with_history_matches_reference():
    """T-NFR02-SHORT parity: a fitting history is preserved verbatim in place."""

    history = "Neutral Analyst: Earlier neutral turn.\nAggressive Analyst: Earlier aggressive turn."
    state = _state(history=history)
    sent = _sent_prompt(state)

    expected = _reference_neutral_prompt(
        trader_decision=state["trader_investment_plan"],
        instrument_context=state["instrument_context"],
        portfolio_context=state["portfolio_context"],
        market=state["market_report"],
        sentiment=state["sentiment_report"],
        news=state["news_report"],
        fundamentals=state["fundamentals_report"],
        history=history,
        aggressive="Synthetic aggressive opening.",
        conservative="Synthetic conservative opening.",
        language="",
    )
    assert sent == expected


@pytest.mark.unit
def test_nfr02_short_neutral_prompt_with_three_turns_matches_reference():
    """T-NFR02-SHORT parity: three consecutive turns survive intact, in order.

    A short request requiring no reduction must reproduce the frozen reference
    character for character, including every original ``\\n`` separator between
    turns. This is the case that would fail if turn splitting moved, doubled or
    dropped a newline. The reference is session-transcribed (see module
    docstring) and has not yet been independently compared with the pinned
    baseline commit.
    """

    history = (
        "Neutral Analyst: First turn from the neutral analyst.\n"
        "Neutral Analyst: Second turn from the neutral analyst.\n"
        "Neutral Analyst: Third turn from the neutral analyst."
    )
    state = _state(history=history)
    sent = _sent_prompt(state)

    expected = _reference_neutral_prompt(
        trader_decision=state["trader_investment_plan"],
        instrument_context=state["instrument_context"],
        portfolio_context=state["portfolio_context"],
        market=state["market_report"],
        sentiment=state["sentiment_report"],
        news=state["news_report"],
        fundamentals=state["fundamentals_report"],
        history=history,
        aggressive="Synthetic aggressive opening.",
        conservative="Synthetic conservative opening.",
        language="",
    )
    assert sent == expected
    # Separators are asserted explicitly so a split/join defect is unambiguous.
    assert "analyst.\nNeutral Analyst: Second" in sent
    assert "analyst.\nNeutral Analyst: Third" in sent


# ---------------------------------------------------------------------------
# T-NFR02-UTF8
# ---------------------------------------------------------------------------


def _json_user_message_bytes(prompt: str) -> int:
    """Independent re-derivation of the C5 canonical size for one user message."""

    return len(
        json.dumps(
            [{"role": "user", "content": prompt}],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("sample", "label", "multibyte"),
    [
        ("ASCII only text", "ascii", False),
        ("中文字符测试", "chinese", True),
        ("emoji 🙂🚀", "emoji", True),
    ],
)
def test_nfr02_utf8_canonical_measurement_counts_utf8_bytes(sample, label, multibyte):
    """T-NFR02-UTF8: canonical size is UTF-8 byte length, not character count."""

    prompt = "Prompt: " + sample
    measured = canonical_message_bytes([ChatMessage(role="user", content=prompt)])
    assert measured == _json_user_message_bytes(prompt)
    if multibyte:
        assert measured > len(prompt), f"{label} sample must exercise multibyte encoding"


@pytest.mark.unit
@pytest.mark.parametrize("sample", ["ASCII text", "中文🙂" * 100, "🙂", "é", "中文"])
def test_nfr02_utf8_exact_boundary_is_inclusive(sample):
    """T-NFR02-UTF8: exactly at the cap passes; one byte over is rejected."""

    parts = TextContextParts(
        required_prefix="Prompt: " + sample,
        optional_turns=(),
        required_suffix="",
    )
    exact = _json_user_message_bytes(parts.render_full())

    at_cap = prepare_text_context(parts, max_message_bytes=exact)
    assert at_cap.status == "READY"
    assert at_cap.message_bytes == exact

    with pytest.raises(ContextTooLarge) as excinfo:
        prepare_text_context(parts, max_message_bytes=exact - 1)
    assert excinfo.value.reason_code == "CONTEXT_TOO_LARGE"


# ---------------------------------------------------------------------------
# T-NFR02-ORDER
# ---------------------------------------------------------------------------


def _optional_turn_blocks(count: int) -> list[ContextBlock]:
    return [
        ContextBlock.build(
            f"h{index:04d}",
            [ChatMessage(role="user", content=f"turn-{index}-" + "f" * 40)],
            required=False,
        )
        for index in range(count)
    ]


@pytest.mark.unit
def test_nfr02_order_drops_oldest_first_with_exact_dropped_ids():
    """T-NFR02-ORDER: the oldest optional group is dropped first and reported."""

    required = ContextBlock.build(
        "required", [ChatMessage(role="user", content="fixed")], required=True
    )
    optional = _optional_turn_blocks(5)

    full = prepare_context([required, *optional], max_message_bytes=MAX_MESSAGE_BYTES)
    assert full.dropped_group_ids == ()

    reduced = prepare_context([required, *optional], max_message_bytes=full.message_bytes - 1)
    assert reduced.message_bytes <= full.message_bytes - 1
    assert reduced.dropped_group_ids == ("h0000",)
    assert reduced.messages[0].content == "fixed"
    assert reduced.messages[-1].content.startswith("turn-4-")


@pytest.mark.unit
def test_nfr02_order_is_deterministic_for_identical_input():
    """T-NFR02-ORDER: identical input and config produce identical output."""

    required = ContextBlock.build(
        "required", [ChatMessage(role="user", content="fixed")], required=True
    )
    optional = _optional_turn_blocks(4)

    first = prepare_context([required, *optional], max_message_bytes=200)
    second = prepare_context([required, *optional], max_message_bytes=200)

    assert first == second
    assert first.dropped_group_ids == second.dropped_group_ids
    assert first.message_bytes <= 200


@pytest.mark.unit
def test_nfr02_order_neutral_node_drops_oldest_oversized_turn():
    """T-NFR02-ORDER at the scoped site: oldest complete turn is removed first.

    Fixture shape (all boundaries verified ``Neutral Analyst:`` turns, no trailing
    newline): turn 0 carries all oversized content, turn 1 is short, turn 2 is
    short and newest. The complete request exceeds the cap while turns 1+2 fit, so
    the reducer must drop turn 0 only.
    """

    oversized_oldest = "Neutral Analyst: " + ("oldest oversized turn filler " * 3000)
    middle = "Neutral Analyst: MIDDLE-TURN-MARKER."
    newest = "Neutral Analyst: NEWEST-TURN-MARKER."
    history = "\n".join((oversized_oldest, middle, newest))

    full_bytes = _json_user_message_bytes(
        _reference_neutral_prompt(
            trader_decision="Synthetic trader plan for ZZTEST.",
            instrument_context="The instrument to analyze is `ZZTEST`.",
            portfolio_context="Portfolio context: not provided in this synthetic run.",
            market="Synthetic market report.",
            sentiment="Synthetic sentiment report.",
            news="Synthetic news report.",
            fundamentals="Synthetic fundamentals report.",
            history=history,
            aggressive="Synthetic aggressive opening.",
            conservative="Synthetic conservative opening.",
        )
    )
    assert full_bytes > MAX_MESSAGE_BYTES, "fixture precondition: request must be oversized"

    sent = _sent_prompt(_state(history=history))
    sent_bytes = _json_user_message_bytes(sent)

    assert sent_bytes <= MAX_MESSAGE_BYTES
    assert "oldest oversized turn filler" not in sent, "oldest turn must be removed"
    assert "MIDDLE-TURN-MARKER" in sent, "short middle turn must survive"
    assert "NEWEST-TURN-MARKER" in sent, "newest turn must survive"
    assert "Neutral Risk Analyst" in sent
