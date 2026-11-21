"""D7 workflow acceptance, established before governance implementation."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())


def test_d7_has_one_required_aggregate():
    """A passing ordinary CI must not stand in for the D7 aggregate."""
    assert "d7-required" in workflow()["jobs"], "D7 required aggregate is absent"


def test_d7_aggregate_cannot_accept_skipped_or_missing_jobs():
    jobs = workflow()["jobs"]
    required = jobs.get("d7-required", {})
    assert required.get("if") == "always()", "The aggregate must run after failures"
    assert set(required.get("needs", [])) >= {
        "test", "course-artifacts", "smoke-install", "lint", "d7-governance"
    }, "The aggregate omits a required gate"
    assert "success" in str(required.get("steps", [])), "Every needed job must succeed"


def test_d7_executes_type_security_and_policy_checks():
    run = str(workflow()["jobs"].get("d7-governance", {}))
    for required in ["d7_static.py", "d7_policy.py", "test/governance"]:
        assert required in run, f"D7 does not execute {required}"


def test_d7_has_blocking_semantic_evaluation():
    run = str(workflow()["jobs"].get("d7-governance", {}))
    assert "d7_semantic.py" in run, "No blocking fixed semantic evaluator"
    assert "continue-on-error" not in run, "A failed semantic gate cannot be ignored"


def test_d7_does_not_execute_untrusted_code_with_privileged_event():
    config = workflow()
    events = config.get("on", config.get(True, {}))
    assert "pull_request_target" not in events
    assert config["permissions"]["contents"] == "read"


def test_d7_has_trusted_base_execution_and_receipts():
    run = str(workflow()["jobs"].get("d7-governance", {}))
    assert "trusted-policy" in run, "PR policy must be evaluated from its trusted base"
    assert "upload-artifact" in run, "Retain gate execution receipts"
