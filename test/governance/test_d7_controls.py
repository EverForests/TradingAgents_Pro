"""D7 positive and deliberate-negative controls; fixtures never alter business code."""

from __future__ import annotations

import copy
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema.exceptions import ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
policy = importlib.import_module("d7_policy")
semantic = importlib.import_module("d7_semantic")
static = importlib.import_module("d7_static")
artifacts = importlib.import_module("verify_course_artifacts")


def corpus():
    return json.loads((ROOT / ".github/governance/semantic-suite.json").read_text())


def test_independent_exact_test_review_before_implementation_passes():
    review = {"state": "APPROVED", "commit_id": "a" * 40,
              "user": {"login": "asling3", "type": "User"},
              "submitted_at": "2026-01-01T10:00:00Z"}
    assert policy.review_approval("a" * 40, [review], "EverForests",
                                  "2026-01-01T11:00:00Z") == review


@pytest.mark.parametrize("mutation", ["self", "late", "wrong-sha", "bot", "unapproved", "unknown"])
def test_missing_or_invalid_prior_review_is_refused(mutation):
    review = {"state": "APPROVED", "commit_id": "a" * 40,
              "user": {"login": "asling3", "type": "User"},
              "submitted_at": "2026-01-01T10:00:00Z"}
    if mutation == "self":
        review["user"]["login"] = "EverForests"
    elif mutation == "late":
        review["submitted_at"] = "2026-01-01T12:00:00Z"
    elif mutation == "wrong-sha":
        review["commit_id"] = "b" * 40
    elif mutation == "bot":
        review["user"]["type"] = "Bot"
    elif mutation == "unapproved":
        review["state"] = "COMMENTED"
    else:
        review["user"]["login"] = "untrusted-fixture"
    with pytest.raises(policy.PolicyFailure, match="No independent"):
        policy.review_approval("a" * 40, [review], "EverForests", "2026-01-01T11:00:00Z")


def test_absent_prior_review_does_not_become_an_approval():
    with pytest.raises(policy.PolicyFailure):
        policy.review_approval("a" * 40, [], "EverForests", "2026-01-01T11:00:00Z")


def test_aggregate_accepts_exactly_all_success():
    policy.aggregate(dict.fromkeys(["test", "course-artifacts", "smoke-install", "lint", "d7-governance"], "success"))


@pytest.mark.parametrize("result", ["failure", "skipped", "cancelled", "timed_out", ""])
def test_aggregate_refuses_every_unsuccessful_state(result):
    states = dict.fromkeys(["test", "course-artifacts", "smoke-install", "lint", "d7-governance"], "success")
    states["d7-governance"] = result
    with pytest.raises(policy.PolicyFailure):
        policy.aggregate(states)


def test_aggregate_refuses_missing_gate():
    with pytest.raises(policy.PolicyFailure, match="Missing"):
        policy.aggregate({"test": "success"})


def test_all_nine_annotated_semantic_positive_controls_pass():
    data = corpus()
    result = semantic.evaluate_answers(data, data["positive_controls"])
    assert result["required_field_agreement"] == 1.0
    assert result["cases"] == 9
    assert not result["failures"]


@pytest.mark.parametrize("index", range(9))
def test_each_semantic_control_rejects_a_contradictory_output(index):
    data = corpus()
    answers = copy.deepcopy(data["positive_controls"])
    answers[index]["result"] = {"fabricated": "answer contradicts the annotated source"}
    result = semantic.evaluate_answers(data, answers)
    assert result["failures"]
    assert result["required_field_agreement"] < 1.0


def test_resolvable_reference_does_not_allow_unsupported_claim():
    data = corpus()
    answers = copy.deepcopy(data["positive_controls"])
    answers[0]["unsupported_claims"] = ["The synthetic source guarantees investment returns"]
    assert semantic.evaluate_answers(data, answers)["failures"]


def test_semantic_support_requires_expected_facts_not_only_valid_ids():
    data = corpus()
    answers = copy.deepcopy(data["positive_controls"])
    answers[2]["supported_facts"] = ["a-valid-but-unrelated-source"]
    assert semantic.evaluate_answers(data, answers)["failures"]


def test_semantic_missing_or_duplicate_cases_are_refused():
    data = corpus()
    with pytest.raises(policy.PolicyFailure):
        semantic.evaluate_answers(data, data["positive_controls"][:-1])
    with pytest.raises(policy.PolicyFailure):
        semantic.evaluate_answers(data, data["positive_controls"] + data["positive_controls"][:1])


def test_model_change_cannot_pass_using_fake_fixture_evidence():
    with pytest.raises(policy.PolicyFailure, match="fixture answers"):
        semantic.validate_model_receipt(ROOT, corpus(), "corpus-digest", {
            "evidence_class": "deterministic-fake-model", "answers": corpus()["positive_controls"]})


def test_model_evaluation_must_match_current_configuration():
    with pytest.raises(policy.PolicyFailure, match="another model/prompt"):
        semantic.validate_model_receipt(ROOT, corpus(), "corpus-digest", {
            "evidence_class": "recorded-model-output", "configuration_sha256": "wrong"})


def test_reviewed_model_output_can_pass_the_frozen_rubric():
    receipt = {
        "evidence_class": "recorded-model-output",
        "configuration_sha256": semantic.configuration_digest(ROOT),
        "corpus_sha256": "corpus-digest", "model_id": "synthetic-provenance-control",
        "provider": "synthetic-fixture-not-a-live-result", "captured_at": "2026-01-01T00:00:00Z",
        "provider_response_sha256": "a" * 64, "answers": corpus()["positive_controls"],
    }
    assert not semantic.validate_model_receipt(ROOT, corpus(), "corpus-digest", receipt)["failures"]


def test_static_finding_budget_is_exact_and_preserves_multiplicity():
    assert static.compare_findings(["a", "b"], ["a", "b"]) == []
    assert static.compare_findings(["a", "c"], ["a", "b"]) == ["c"]
    assert static.compare_findings(["a", "a"], ["a"]) == ["a"]


def test_read_permission_changes_do_not_silently_expand_edit_authority():
    original = json.loads((ROOT / ".opencode/opencode.jsonc").read_text())
    updated = copy.deepcopy(original)
    updated["permissions"].append({"action": "read", "resource": "fixture.md", "effect": "allow"})
    assert policy.permission_edits(original) == policy.permission_edits(updated)
    updated["permissions"].append({"action": "edit", "resource": "*", "effect": "allow"})
    assert policy.permission_edits(original) != policy.permission_edits(updated)


def test_actual_type_checker_refuses_new_assignment_error(tmp_path):
    source = tmp_path / "type_counterexample.py"
    source.write_text('value: int = "not an integer"\n')
    result = subprocess.run([sys.executable, "-m", "mypy", "--no-incremental", str(source)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "assignment" in result.stdout


def test_actual_security_analyzer_refuses_shell_injection_counterexample(tmp_path):
    source = tmp_path / "security_counterexample.py"
    source.write_text('import subprocess\nsubprocess.run(input(), shell=True)\n')
    result = subprocess.run([sys.executable, "-m", "bandit", "-q", "-f", "json", str(source)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert any(x["test_id"] == "B602" for x in json.loads(result.stdout)["results"])


def test_policy_cli_returns_nonzero_on_mismatched_permission_copies(tmp_path):
    def run(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    run("init")
    run("config", "user.name", "Synthetic Governance Fixture")
    run("config", "user.email", "fixture@example.invalid")
    (tmp_path / "fixture.txt").write_text("base")
    run("add", ".")
    run("commit", "-m", "fixture base")
    base = run("rev-parse", "HEAD")
    (tmp_path / ".opencode").mkdir()
    (tmp_path / ".opencode/opencode.jsonc").write_text('{"permissions": []}')
    (tmp_path / ".opencode/permissions.jsonc").write_text('{"permissions": [1]}')
    run("add", ".")
    run("commit", "-m", "deliberately invalid copies")
    report = tmp_path / "report.json"
    env = dict(os.environ)
    env.pop("GITHUB_EVENT_PATH", None)
    result = subprocess.run([sys.executable, str(ROOT / ".github/scripts/d7_policy.py"),
                             "--root", str(tmp_path), "--base", base, "--report", str(report)],
                            capture_output=True, text=True, check=False, env=env)
    assert result.returncode == 1
    assert json.loads(report.read_text())["reason"] == "OpenCode permission copies differ"


@pytest.mark.parametrize("mutation", ["duplicate-id", "unknown-reference", "invalid-status"])
def test_real_schema_and_reference_gate_refuses_corrupt_registry(tmp_path, monkeypatch, mutation):
    for rel in ["docs/req/requirements.yaml", "docs/req/req-schema.json",
                "docs/architecture/interface-contracts.md",
                "docs/code-governance/verification-constraints.md"]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((ROOT / rel).read_bytes())
    p = tmp_path / "docs/req/requirements.yaml"
    data = yaml.safe_load(p.read_text())
    if mutation == "duplicate-id":
        data["requirements"][1]["id"] = data["requirements"][0]["id"]
    elif mutation == "unknown-reference":
        data["requirements"][0]["test_cases"] = ["T-DOES-NOT-EXIST"]
    else:
        data["requirements"][0]["status"] = "silently-approved-fixture"
    p.write_text(yaml.safe_dump(data))
    monkeypatch.chdir(tmp_path)
    with pytest.raises((ValueError, ValidationError)):
        artifacts.check_registry()


def test_schema_gate_accepts_the_current_registry(monkeypatch):
    monkeypatch.chdir(ROOT)
    artifacts.check_registry()
