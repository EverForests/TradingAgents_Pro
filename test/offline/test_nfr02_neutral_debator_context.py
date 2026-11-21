"""NFR-02 behavioral regressions at the existing Neutral Risk Debater call site.

Requirement: NFR-02 (docs/req/requirements.yaml).
Contract: C5 "deterministic prepared context" (docs/architecture/interface-contracts.md).
Trace: docs/architecture/trace-matrix.md (NFR-02); runtime policy row "NFR-02".

Baseline (failing-before) tests for the *existing* scoped call site. They do
NOT import the planned NFR-02 owner module
``tradingagents.llm_clients.context_limit``: the failure on the unmodified
baseline must be a behavioral gap (oversized input sent / no refusal), never an
ImportError or a missing-module error. Only the pre-existing
``create_neutral_debator`` factory is exercised.

Human-approved design decisions (operator is the NFR-02 owner):

* Black-box only, standard-library recording test doubles (``SimpleNamespace``
  response). No langchain import, no network access.
* ``MAX_MESSAGE_BYTES`` is a configurable *test threshold*, not an empirically
  justified production optimum; it is stated once as a module constant.
* Two independent cases, because the two outcomes are not interchangeable:
    - T-NFR02-REDUCE: required content fits, optional history pushes the
      complete request over the cap. Exactly one request must be sent, its
      canonical UTF-8 size must be within the cap, and required blocks must
      survive. Zero sends FAILS here (an implementation that rejects everything
      has not implemented deterministic reduction).
    - T-NFR02-REJECT: required content alone cannot fit. An explicit
      CONTEXT_TOO_LARGE failure must be raised with zero sends. A silent
      return, a dropped-evidence send, or a sent request FAILS here.
* Identical normalized input intends identical prepared bytes (C5
  determinism). T-NFR02-REDUCE compares the normalized prepared payload *and*
  its byte count across two independent runs.
* A separate measurement sanity test guards the measuring helper itself, so a
  measurement regression cannot make the behavioral cases vacuously pass.

Canonical measurement (C5): the final provider-facing messages as JSON with
``ensure_ascii=False``, ``sort_keys=True``, ``separators=(",", ":")``,
``allow_nan=False``, then UTF-8. The planned ``PreparedRequest`` record is not
built yet, so size is re-measured here from the payload the call site actually
hands to the model. This keeps the test independent of the owner module while
still measuring the contract-defined quantity.
"""

import json
from types import SimpleNamespace

import pytest

from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator

# Configurable test threshold for these offline cases: bytes of canonical UTF-8
# message (C5 acceptance cap). Not a production optimum and not a token count.
MAX_MESSAGE_BYTES = 65536

# Explicit name of the C5 terminal failure reason used by C0/C4/C5.
CONTEXT_TOO_LARGE = "CONTEXT_TOO_LARGE"

# Synthetic, shareable identifiers and content: no real company data, no secrets.
TICKER = "ZZTEST"
TRADER_DECISION = f"Synthetic trader plan: hold a 25% position in {TICKER}."

# Required blocks under C5 that must be retained whenever a request is sent.
REQUIRED_SUBSTRINGS = (
    "Neutral Risk Analyst",  # role/task identity
    "Synthetic trader plan",  # trader decision anchoring the task
    "Synthetic market report",  # current required evidence
    "Synthetic fundamentals report",  # current required evidence
)

# Distinctive marker for mandatory content in the irreducible fixture, so dropped
# mandatory evidence is distinguishable from reduced optional history.
MANDATORY_MARKER = "MANDATORY-NONREDUCIBLE-EVIDENCE"

# Optional-history filler. ASCII on purpose: multibyte boundary behaviour is a
# separate planned case (T-NFR02-UTF8), not these cases.
_OPTIONAL_TURN = (
    "Optional earlier debate turn kept only as reducible discussion history. "
)


class RecordingLLM:
    """Standard-library recording stand-in for a chat model.

    Implements only the surface the baseline node uses: ``invoke(messages)``
    returning an object with ``content``. Records every payload so the test can
    measure the actual final model input and count sends without trusting any
    application-provided counter.
    """

    def __init__(self, reply: str = "Synthetic neutral argument.") -> None:
        self._reply = reply
        self.calls: list[object] = []

    def invoke(self, messages):
        self.calls.append(messages)
        return SimpleNamespace(content=self._reply)


def canonical_message_bytes(messages) -> int:
    """C5 canonical size of the final provider-facing messages, in UTF-8 bytes.

    Normalizes a bare string prompt or a list of dict/object messages to the
    ``[{role, content}, ...]`` array only for measurement. Nothing is sent.
    """

    encoded = json.dumps(
        _as_message_array(messages),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return len(encoded.encode("utf-8"))


def _as_message_array(messages) -> list[dict]:
    """Normalize provider-facing messages for the C5 canonical measurement.

    A bare string is the baseline shape (``llm.invoke(prompt)``) and must be
    measured as user content, not as an attribute-less object.
    """

    if isinstance(messages, str):
        return [{"role": "user", "content": messages}]
    if isinstance(messages, dict):
        messages = [messages]
    return [
        {
            "role": message.get("role", "user"),
            "content": message.get("content", ""),
        }
        if isinstance(message, dict)
        else {
            "role": getattr(message, "role", "user"),
            "content": str(getattr(message, "content", "")),
        }
        for message in messages
    ]


def _message_text(messages) -> str:
    """All text the model received, joined, for required-block checks."""

    return "\n".join(str(item["content"]) for item in _as_message_array(messages))


def _optional_history(minimum_bytes: int) -> str:
    """Synthetic optional debate history comfortably above ``minimum_bytes``."""

    turns = (minimum_bytes // len(_OPTIONAL_TURN)) + 2
    return "\n".join(f"[optional turn {index:05d}] {_OPTIONAL_TURN}" for index in range(turns))


def build_state(
    *,
    market_report: str = "Synthetic market report: flat trend, no signal.",
    fundamentals_report: str = "Synthetic fundamentals report: placeholder operands only.",
    history: str = "",
) -> dict:
    """Synthetic AgentState for the neutral risk node."""

    return {
        "company_of_interest": TICKER,
        "asset_type": "stock",
        "instrument_context": f"The instrument to analyze is `{TICKER}`.",
        "portfolio_context": "Portfolio context: not provided in this synthetic run.",
        "market_report": market_report,
        "sentiment_report": "Synthetic sentiment report: unavailable in this fixture.",
        "news_report": "Synthetic news report: no items in window.",
        "fundamentals_report": fundamentals_report,
        "trader_investment_plan": TRADER_DECISION,
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


def _run_node(state: dict) -> RecordingLLM:
    llm = RecordingLLM()
    create_neutral_debator(llm)(state)
    return llm


@pytest.mark.unit
def test_nfr02_measurement_sanity_70k_ascii_exceeds_threshold():
    """Measurement helper sanity, not a requirement case.

    A 70,000-character ASCII string prompt must measure above the 65,536-byte
    test threshold. This fails loudly if the canonical measurement regresses
    (for example, by treating a string prompt as attribute-less content), which
    would otherwise let the behavioral cases pass vacuously.
    """

    prompt = "a" * 70_000
    assert len(prompt.encode("utf-8")) == 70_000
    assert canonical_message_bytes(prompt) > MAX_MESSAGE_BYTES, (
        "measurement regression: a 70,000-character ASCII string prompt was "
        f"measured as {canonical_message_bytes(prompt)} bytes"
    )
    # A structured message array must measure the same content, not less.
    assert canonical_message_bytes({"role": "user", "content": prompt}) > MAX_MESSAGE_BYTES


@pytest.mark.unit
def test_nfr02_neutral_debator_reduces_oversized_optional_history():
    """T-NFR02-REDUCE: reducible history is dropped so the request fits the cap.

    Required evidence is small; synthetic optional history pushes the complete
    request over MAX_MESSAGE_BYTES. Expected: exactly one request is sent, its
    canonical UTF-8 size is within the cap, and all required blocks remain.
    Rejecting the request, silently returning, or sending it oversized fails.
    """

    history = _optional_history(MAX_MESSAGE_BYTES)
    assert len(history.encode("utf-8")) > MAX_MESSAGE_BYTES, (
        "fixture precondition: synthetic optional history must exceed the cap"
    )

    llm = _run_node(build_state(history=history))

    assert len(llm.calls) == 1, (
        "NFR-02 violated: oversized but reducible input must produce exactly one "
        f"bounded request (observed {len(llm.calls)} sends). Rejecting reducible "
        "context means deterministic reduction is not implemented."
    )

    sent_bytes = canonical_message_bytes(llm.calls[0])
    assert sent_bytes <= MAX_MESSAGE_BYTES, (
        "NFR-02 violated: the Neutral Risk Debater sent an oversized final message "
        f"({sent_bytes} UTF-8 bytes > configured {MAX_MESSAGE_BYTES} bytes) instead "
        "of removing optional history."
    )

    text = _message_text(llm.calls[0])
    missing = [required for required in REQUIRED_SUBSTRINGS if required not in text]
    assert not missing, (
        "NFR-02 violated: the reduced request dropped required blocks: " + repr(missing)
    )

    # Determinism: same input and config -> same prepared payload and bytes,
    # compared across two independent node/stub pairs.
    first_payload = _as_message_array(llm.calls[0])
    repeat = _run_node(build_state(history=history))
    assert len(repeat.calls) == 1
    repeat_payload = _as_message_array(repeat.calls[0])
    assert repeat_payload == first_payload, (
        "NFR-02 violated: identical input produced a different prepared payload."
    )
    assert canonical_message_bytes(repeat.calls[0]) == sent_bytes, (
        "NFR-02 violated: identical input produced different prepared message sizes."
    )


@pytest.mark.unit
def test_nfr02_neutral_debator_rejects_irreducible_context():
    """T-NFR02-REJECT: mandatory content that cannot fit is refused before sending.

    Required evidence alone exceeds MAX_MESSAGE_BYTES and is not optional
    history, so it cannot be removed. Expected: an explicit CONTEXT_TOO_LARGE
    failure and zero model requests. A silent return, a send with trimmed
    mandatory evidence, or an unrelated error fails.
    """

    oversized_evidence = (
        f"{MANDATORY_MARKER} mandatory market evidence, not optional history. "
    ) * ((MAX_MESSAGE_BYTES // len(MANDATORY_MARKER)) + 64)
    assert len(oversized_evidence.encode("utf-8")) > MAX_MESSAGE_BYTES, (
        "fixture precondition: mandatory evidence alone must exceed the cap"
    )

    llm = RecordingLLM()
    node = create_neutral_debator(llm)

    try:
        node(build_state(market_report=oversized_evidence, history=""))
    except Exception as exc:  # deliberate: the refusal must be explicit
        reason = getattr(exc, "reason_code", None) or getattr(exc, "reason", None)
        assert type(exc).__name__ == "ContextTooLarge" or reason == CONTEXT_TOO_LARGE, (
            "NFR-02 violated: an oversized irreducible request failed with an "
            f"unrelated error {type(exc).__name__}: {exc!r} instead of an explicit "
            "CONTEXT_TOO_LARGE refusal."
        )
    else:
        pytest.fail(
            "NFR-02 violated: oversized irreducible context was not refused; the "
            "node returned normally after "
            f"{len(llm.calls)} model request(s) instead of raising CONTEXT_TOO_LARGE."
        )

    assert llm.calls == [], (
        "NFR-02 violated: a CONTEXT_TOO_LARGE rejection must make zero model "
        f"requests (observed {len(llm.calls)})."
    )
