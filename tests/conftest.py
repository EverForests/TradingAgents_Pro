"""Shared pytest fixtures that prevent CI hangs when API keys are absent."""

import os
import socket

import pytest


def _blank_settings_overlay():
    """Blank every TRADINGAGENTS_* setting before the package is imported.

    The package loads .env on import and folds these variables into
    DEFAULT_CONFIG, so a contributor's own settings would become the defaults
    the suite asserts on. A blank value is still present, so load_dotenv leaves
    it alone, and the overlay reads it as unset. Tests of the overlay set their own.
    """
    from dotenv import dotenv_values, find_dotenv

    names = set(os.environ)
    for filename in (".env", ".env.enterprise"):
        names |= set(dotenv_values(find_dotenv(filename, usecwd=True)))
    for name in names:
        if name.startswith("TRADINGAGENTS_"):
            os.environ[name] = ""


_blank_settings_overlay()


def _own_file_locations():
    """Keep the suite's results, cache and memory log in a directory of its own.

    Set before the package is imported, whose defaults put them in the user's
    home: a test reading the user's cache would see what their runs fetched.
    """
    import tempfile

    home = tempfile.mkdtemp(prefix="tradingagents-tests-")
    os.environ["TRADINGAGENTS_RESULTS_DIR"] = os.path.join(home, "logs")
    os.environ["TRADINGAGENTS_CACHE_DIR"] = os.path.join(home, "cache")
    os.environ["TRADINGAGENTS_MEMORY_LOG_PATH"] = os.path.join(home, "memory", "trading_memory.md")


_own_file_locations()


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")
    # yfinance caches each symbol's time zone on disk, in the home directory
    # by default; the suite keeps it in a directory of its own.
    import tempfile

    import yfinance

    yfinance.set_tz_cache_location(tempfile.mkdtemp(prefix="tradingagents-tests-yf-"))


@pytest.fixture(autouse=True)
def _no_network(request, monkeypatch):
    """Tests do not reach the network; one that must is marked integration."""
    if request.node.get_closest_marker("integration"):
        return

    def refuse(*args, **kwargs):
        raise OSError(f"test tried to reach the network: {args[1:] or kwargs}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: refuse(None, *a))
    # yfinance's HTTP client is libcurl, which never touches Python's sockets.
    from curl_cffi import requests as curl_requests

    monkeypatch.setattr(curl_requests.Session, "request", refuse)
    monkeypatch.setattr(curl_requests.AsyncSession, "request", refuse)


@pytest.fixture(autouse=True)
def _at_a_terminal(monkeypatch):
    """Tests of the interactive steps run as if at a terminal; pytest's stdin is
    not one. A test of an unattended run sets isatty to False itself."""
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)


@pytest.fixture(autouse=True)
def _own_cli_prefs(tmp_path, monkeypatch):
    """The CLI keeps the last run's selections in the user's home; tests keep theirs apart."""
    monkeypatch.setattr("cli.prefs._PREFS_PATH", tmp_path / "cli_prefs.json")


@pytest.fixture
def publication_state(tmp_path):
    """Supply a v1 candidate and retained evidence to tests of publication consumers."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    def build(ticker, date, rating, body, *, results_dir=tmp_path, publish=True):
        run_id = "fixture-run"
        identity = {"contract_version": "1.0", "run_id": run_id, "ticker": ticker, "as_of_date": date}
        root = results_dir / ticker / date / "evidence" / run_id
        root.mkdir(parents=True, exist_ok=True)
        (root / "snapshot.md").write_text(
            f"### Recent verified closes\n\n| Date | Close |\n|---|---:|\n| {date} | 100 |\n",
            encoding="utf-8",
        )
        state = {
            "course_run": {**identity, "execution_status": "RUNNING", "request_limit": 40},
            "candidate_rating": rating,
            "candidate_decision": body,
            "candidate_argument_ids": ["argument-1"],
            "evidence_index": {
                "snapshot-1": {
                    **identity, "evidence_id": "snapshot-1", "source_kind": "market_snapshot",
                    "vendor": "yahoo", "source_ref": "fixture:snapshot",
                    "content_ref": f"evidence://{run_id}/snapshot.md",
                    "window_start": date, "window_end": date,
                },
            },
            "argument_index": {
                "argument-1": {
                    **identity, "argument_id": "argument-1", "claim": "Snapshot supports the claim",
                    "evidence_ids": ["snapshot-1"],
                },
            },
        }
        if publish:
            graph = object.__new__(TradingAgentsGraph)
            graph.config = {"results_dir": str(results_dir)}
            graph.complete_run(state)
            assert graph.publish(state) == ("BLOCKED" if rating is None else "APPROVED")
        return state

    return build


_API_KEY_ENV_VARS = (
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_CN_API_KEY",
    "ZHIPU_API_KEY",
    "ZHIPU_CN_API_KEY",
    "MINIMAX_API_KEY",
    "MINIMAX_CN_API_KEY",
    "OPENROUTER_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
)


@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    for env_var in _API_KEY_ENV_VARS:
        # `or` not a .get default: an env var present but empty (e.g. a key left
        # blank in a .env copied from .env.example) must still get the placeholder.
        monkeypatch.setenv(env_var, os.environ.get(env_var) or "placeholder")


@pytest.fixture(autouse=True)
def _isolate_config():
    """Reset the global dataflows config before and after each test.

    ``set_config`` merges (it never clears keys absent from the override), so a
    test that sets e.g. ``tool_vendors`` would otherwise leak into later tests
    and make routing behavior order-dependent. Replace the global outright so
    every test starts from a clean DEFAULT_CONFIG.
    """
    import copy

    import tradingagents.dataflows.config as config_module
    import tradingagents.default_config as default_config

    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    yield
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
