"""Offline RED: C0 request budget must bound actual outbound LLM attempts.

Frozen seam (coordinator-approved) for FR-03 / INV-01 / NFR-01:

* The factory builds ``ChatOpenAI`` (synchronous) for ``openai_compatible`` in
  both tiers, so every agent call becomes one real HTTP POST.
* The graph is invoked (via ``graph.invoke``) in a way that deliberately makes
  four attempts with ``request_limit=3``:

      q1 (quick), d1 (deep), q2 (quick), d2 (deep)

* A ``request_budget_enabled=True`` config key (integrator-approved, ignored by
  today's code) asks C0 to count *actual outbound attempts* per run and to stop
  dispatching once the limit is reached.

Current behavior (RED): all four attempts reach the transport, so the run
completes and publishes/gate-decides normally. Expected behavior: exactly 3
outbound requests, then ``execution_status == "BUDGET_EXHAUSTED"``,
``publication_status == "BLOCKED"`` (INV-01), empty ``final_trade_decision`` /
``final_rating``, and no decision written to the memory log.

No network, no CLI, no real provider: ``httpx.HTTPTransport.handle_request`` is
replaced by a fixed HTTP 200 completion fixture attached to the *requests*, so
the count is observed at the outbound boundary regardless of SDK internals.
"""

import copy
import json
from types import SimpleNamespace

import httpx
import pytest

from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients.factory import create_tier_client
from tradingagents.llm_clients.request_budget import RequestBudget

try:
    import httpx2
except ImportError:
    httpx2 = None


def _completion_body(model: str = "fixture-model") -> bytes:
    """A minimal OpenAI-compatible chat completion (HTTP 200) as one JSON body."""
    return json.dumps(
        {
            "id": "chatcmpl-fixture",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "FIXTURE OK"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    ).encode("utf-8")


def _fixture_response(http_library, request):
    """Build the 200 fixture owned by (and attached to) one outbound request."""
    return http_library.Response(
        200,
        headers={"content-type": "application/json"},
        content=_completion_body(),
        request=request,
    )


@pytest.fixture
def configured_graph(tmp_path, monkeypatch):
    # --- offline / dummy credentials: loopback never leaves the machine --------
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")

    # --- observe every outbound attempt at the transport boundary -------------
    outbound = []

    def capture_transport(http_library):
        def fake_handle_request(self, request):
            outbound.append(request)
            return _fixture_response(http_library, request)

        monkeypatch.setattr(http_library.HTTPTransport, "handle_request", fake_handle_request)

    capture_transport(httpx)
    if httpx2 is not None:
        capture_transport(httpx2)

    # --- config: distinct tier model names, small budget, no retries ----------
    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(
        {
            "llm_provider": "openai_compatible",
            "backend_url": "http://127.0.0.1:1/v1",
            "deep_think_llm": "deepseek-v4-flash",
            "quick_think_llm": "deepseek-v4-pro",
            "request_limit": 3,
            "llm_max_retries": 0,
            "checkpoint_enabled": False,
            # Integrator-approved new key; ignored by today's code (behavioral RED).
            "request_budget_enabled": True,
            "results_dir": str(tmp_path / "results"),
            "data_cache_dir": str(tmp_path / "cache"),
            "memory_log_path": str(tmp_path / "memory" / "trading_memory.md"),
        }
    )

    graph = TradingAgentsGraph(config=config, selected_analysts=("market", "fundamentals"))

    # --- no instrument lookup: fixed synthetic context -------------------------
    monkeypatch.setattr(
        graph,
        "resolve_instrument_context",
        lambda *args, **kwargs: "Instrument: NVDA (stock). Synthetic offline fixture.",
        raising=True,
    )
    return graph, outbound


@pytest.mark.parametrize("attempts", [3, 4])
def test_request_budget_counts_outbound_attempts_and_blocks_publication(
    configured_graph, monkeypatch, attempts,
):
    graph, outbound = configured_graph
    # --- a deliberate over-budget dispatch: q1, d1, q2, d2 --------------------
    def over_budget_invoke(graph_input, **kwargs):
        graph.quick_thinking_llm.invoke("q1")
        graph.deep_thinking_llm.invoke("d1")
        graph.quick_thinking_llm.invoke("q2")
        if attempts == 4:
            graph.deep_thinking_llm.invoke("d2")
        state = {**graph_input, "trader_investment_plan": "", "investment_plan": ""}
        # A syntactically valid proposal remains subject to the publication gate.
        state["candidate_rating"] = "Hold"
        state["candidate_argument_ids"] = ()
        state["final_trade_decision"] = "FINAL TRANSACTION PROPOSAL: **HOLD**"
        state["final_rating"] = "Hold"
        return state

    monkeypatch.setattr(graph.graph, "invoke", over_budget_invoke, raising=True)

    state, _signal = graph.propagate("NVDA", "2026-01-05")

    # 1. C0: the budget bounds actual outbound attempts (3, not 4).
    assert len(outbound) == 3, (
        f"expected the request budget to stop dispatch after 3 outbound attempts, "
        f"observed {len(outbound)}"
    )

    # 2. C0: the run is recorded as a terminal budget failure.
    expected = "COMPLETED" if attempts == 3 else "BUDGET_EXHAUSTED"
    assert state["execution_status"] == expected
    assert state["course_run"]["execution_status"] == expected

    # 3. INV-01: an over-budget run can never publish.
    assert state["publication_status"] == "BLOCKED"

    # 4. INV-01: no official decision leaks through on a blocked run.
    assert not state.get("final_trade_decision")
    assert not state.get("final_rating")

    # 5. FR-01: nothing was recorded in the decision memory log.
    assert graph.memory_log.load_entries() == []


def test_irreducible_context_stops_before_budget_reservation(configured_graph, monkeypatch):
    graph, outbound = configured_graph
    reservations = []
    reserve = RequestBudget.try_reserve

    def tracked_reserve(budget):
        reservations.append(budget.snapshot().run_id)
        return reserve(budget)

    monkeypatch.setattr(RequestBudget, "try_reserve", tracked_reserve)

    def oversized_invoke(graph_input, **kwargs):
        state = {**graph_input, "trader_investment_plan": "证据" * 32768}
        create_neutral_debator(graph.deep_thinking_llm)(state)
        return state

    monkeypatch.setattr(graph.graph, "invoke", oversized_invoke)
    state, _ = graph.propagate("NVDA", "2026-01-05")

    assert not outbound
    assert not reservations
    assert state["execution_status"] == "CONTEXT_TOO_LARGE"
    assert state["course_run"]["execution_status"] == "CONTEXT_TOO_LARGE"
    assert state["publication_status"] == "BLOCKED"
    assert state["publication_reason"] == "CONTEXT_TOO_LARGE"
    assert not state["final_rating"]
    assert graph.memory_log.load_entries() == []


def test_real_graph_parallel_analysts_share_one_budget(configured_graph, monkeypatch):
    graph, outbound = configured_graph
    graph.config["request_limit"] = 1
    monkeypatch.setattr(graph, "settle_all_pending", lambda **kwargs: SimpleNamespace(failed=[]))

    first, _ = graph.propagate("NVDA", "2026-01-05")
    assert len(outbound) == 1
    second, _ = graph.propagate("NVDA", "2026-01-05")
    assert len(outbound) == 2
    assert first["course_run"]["run_id"] != second["course_run"]["run_id"]
    for state in (first, second):
        assert state["execution_status"] == "BUDGET_EXHAUSTED"
        assert state["publication_status"] == "BLOCKED"
        assert not state["final_rating"]


def test_streamed_run_meters_model_requests(configured_graph):
    graph, outbound = configured_graph
    graph.config["request_limit"] = 1
    initial = graph.create_run_state("NVDA", "2026-01-05")
    trace = list(graph.stream_run(initial, **graph.propagator.get_graph_args()))
    terminal = trace[-1][1]

    assert len(outbound) == 1
    assert terminal["execution_status"] == "BUDGET_EXHAUSTED"
    assert terminal["course_run"]["run_id"] == initial["course_run"]["run_id"]
    graph.complete_run(terminal)
    graph.publish(terminal)
    assert terminal["publication_status"] == "BLOCKED"
    assert not terminal["final_rating"]


def test_provider_transport_failure_is_terminal_and_retries_are_disabled(
    configured_graph, monkeypatch,
):
    graph, _ = configured_graph
    attempts = []

    def failing_transport(_transport, request):
        attempts.append(request)
        raise httpx.ConnectError("fixture: send outcome unknown", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", failing_transport)
    assert graph.quick_thinking_llm.max_retries == graph.deep_thinking_llm.max_retries == 0

    def invoke(graph_input, **kwargs):
        graph.quick_thinking_llm.invoke("fixture")
        return graph_input

    monkeypatch.setattr(graph.graph, "invoke", invoke)
    state, _ = graph.propagate("NVDA", "2026-01-05")
    assert len(attempts) == 1
    assert state["execution_status"] == "FAILED"
    assert state["publication_status"] == "BLOCKED"
    assert not state["final_rating"]
    assert graph.memory_log.load_entries() == []


def test_cityu_profile_sends_the_approved_thinking_setting(configured_graph):
    graph, outbound = configured_graph
    model = "CS5351/DeepSeek-V4-Flash"
    config = {
        **graph.config,
        "backend_url": "https://llm.cs.cityu.edu.hk/v1",
        "deep_think_llm": model,
        "quick_think_llm": model,
        "llm_max_retries": 4,
    }
    for tier in ("quick", "deep"):
        llm = create_tier_client(config, tier).get_llm()
        assert llm.max_retries == 0
        llm.invoke("offline course profile fixture")

    assert len(outbound) == 2
    for request in outbound:
        assert str(request.url) == "https://llm.cs.cityu.edu.hk/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == model
        assert payload["thinking"] == {"type": "disabled"}
