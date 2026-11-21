"""D7 positive and deliberate-negative controls; fixtures never alter business code."""

from __future__ import annotations

import copy
import hashlib
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
    review = {"state": "APPROVED", "author_association": "COLLABORATOR", "commit_id": "a" * 40,
              "user": {"login": "asling3", "type": "User"},
              "submitted_at": "2026-01-01T10:00:00Z"}
    assert policy.review_approval("a" * 40, [review], "EverForests",
                                  "2026-01-01T11:00:00Z", test_committed_at="2026-01-01T09:00:00Z") == review


@pytest.mark.parametrize("mutation", ["self", "late", "wrong-sha", "bot", "unapproved", "unknown"])
def test_missing_or_invalid_prior_review_is_refused(mutation):
    review = {"state": "APPROVED", "author_association": "COLLABORATOR", "commit_id": "a" * 40,
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
        policy.review_approval("a" * 40, [review], "EverForests", "2026-01-01T11:00:00Z", test_committed_at="2026-01-01T09:00:00Z")


def test_absent_prior_review_does_not_become_an_approval():
    with pytest.raises(policy.PolicyFailure):
        policy.review_approval("a" * 40, [], "EverForests", "2026-01-01T11:00:00Z", test_committed_at="2026-01-01T09:00:00Z")


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
        "corpus_sha256": "corpus-digest", "model_id": "CS5351/DeepSeek-V4-Flash",
        "provider": "school-hosted OpenAI-compatible DeepSeek", "captured_at": "2026-01-01T00:00:00Z",
        "provider_response_sha256": "a" * 64, "answers": corpus()["positive_controls"],
    }
    raw = json.dumps(receipt["answers"], sort_keys=True)
    receipt["raw_response"] = raw
    receipt["provider_response_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
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


def test_current_real_api_permissions_and_source_asset_manifest_pass():
    policy.check_contracts(ROOT, [], ROOT / ".github/governance")


def test_review_cannot_predate_the_exact_test_commit():
    review = {"state": "APPROVED", "author_association": "COLLABORATOR", "commit_id": "a" * 40,
              "user": {"login": "asling3", "type": "User"},
              "submitted_at": "2026-01-01T08:00:00Z"}
    with pytest.raises(policy.PolicyFailure):
        policy.review_approval("a" * 40, [review], "EverForests", "2026-01-01T11:00:00Z",
                              test_committed_at="2026-01-01T09:00:00Z")


def test_naive_review_timestamp_is_refused():
    with pytest.raises(policy.PolicyFailure, match="timezone-aware"):
        policy.review_approval("a" * 40, [], "EverForests", "2026-01-01T11:00:00",
                              test_committed_at="2026-01-01T09:00:00Z")


def test_initial_nonruntime_profile_is_bounded_to_reviewed_registration():
    current = {"model": "reviewed-profile"}
    assert not semantic.profile_change_requires_receipt(True, False, current, current)
    with pytest.raises(policy.PolicyFailure):
        semantic.profile_change_requires_receipt(True, False, {"model": "unreviewed"}, current)
    assert semantic.profile_change_requires_receipt(True, True, current, current)


def fixture_history(tmp_path, *, governance_tests_only=False, modify_tests=False,
                    governance_implementation=False):
    def run(*args, time="2026-01-01T08:00:00+00:00"):
        env = dict(os.environ, GIT_AUTHOR_DATE=time, GIT_COMMITTER_DATE=time)
        return subprocess.run(["git", "-C", str(tmp_path), *args], check=True,
                              capture_output=True, text=True, env=env).stdout.strip()
    def write(rel, text):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    run("init")
    run("config", "user.name", "Synthetic Governance Fixture")
    run("config", "user.email", "fixture@example.invalid")
    write(".github/scripts/d7_policy.py", "# existing installed policy fixture\n")
    write("docs/ai-use-log.yaml", "entries:\n- id: OLD\n")
    run("add", ".")
    run("commit", "-m", "fixture baseline")
    base = run("rev-parse", "HEAD")
    test_path = "test/governance/test_fixture.py" if governance_tests_only else "test/offline/test_fixture.py"
    write(test_path, "def test_fixture():\n    assert True\n")
    write("docs/governance/plans/task.md", "# Synthetic exact test plan\n")
    run("add", ".")
    run("commit", "-m", "tests before implementation", time="2026-01-01T09:00:00+00:00")
    test_sha = run("rev-parse", "HEAD")
    implementation = ".github/scripts/new_gate.py" if governance_implementation else "tradingagents/fixture.py"
    write(implementation, "value = 1\n")
    if modify_tests:
        write(test_path, "def test_fixture():\n    assert False\n")
    write("docs/governance/approvals/task.json", json.dumps({
        "test_revision": test_sha, "plan_path": "docs/governance/plans/task.md",
        "approval_pr": 123, "implementation_paths": [implementation]}))
    run("add", ".")
    run("commit", "-m", "synthetic implementation", time="2026-01-01T11:00:00+00:00")
    return base, test_sha


def test_real_git_ancestry_and_exact_test_review_pass(tmp_path, monkeypatch):
    base, sha = fixture_history(tmp_path)
    monkeypatch.setattr(policy, "github_json", lambda _: [{
        "state": "APPROVED", "author_association": "COLLABORATOR", "commit_id": sha, "submitted_at": "2026-01-01T10:00:00Z",
        "user": {"login": "asling3", "type": "User"}}])
    result = policy.check_prior_approval(tmp_path, base, policy.changed_paths(tmp_path, base), {
        "pull_request": {"user": {"login": "EverForests"}}})
    assert sha in result


@pytest.mark.parametrize("bad_scope,changed_tests", [(True, False), (False, True)])
def test_governance_tests_cannot_approve_business_code_or_change_after_review(
        tmp_path, monkeypatch, bad_scope, changed_tests):
    base, sha = fixture_history(tmp_path, governance_tests_only=bad_scope, modify_tests=changed_tests)
    monkeypatch.setattr(policy, "github_json", lambda _: [{
        "state": "APPROVED", "author_association": "COLLABORATOR", "commit_id": sha, "submitted_at": "2026-01-01T10:00:00Z",
        "user": {"login": "asling3", "type": "User"}}])
    with pytest.raises(policy.PolicyFailure, match="No valid prior"):
        policy.check_prior_approval(tmp_path, base, policy.changed_paths(tmp_path, base), {
            "pull_request": {"user": {"login": "EverForests"}}})


def test_governance_change_without_new_ai_use_record_is_refused(tmp_path):
    base, _ = fixture_history(tmp_path)
    with pytest.raises(policy.PolicyFailure, match="AI-use update"):
        policy.check_ai_use(tmp_path, base, [".github/workflows/ci.yml"])


def test_governance_only_change_requires_prior_review_after_activation(tmp_path):
    base, _ = fixture_history(tmp_path)
    with pytest.raises(policy.PolicyFailure, match="No valid prior"):
        policy.check_prior_approval(tmp_path, base, [".github/scripts/new_gate.py"], {
            "pull_request": {"user": {"login": "EverForests"}}})


def test_governance_tests_can_approve_governance_only_implementation(tmp_path, monkeypatch):
    base, sha = fixture_history(tmp_path, governance_tests_only=True, governance_implementation=True)
    monkeypatch.setattr(policy, "github_json", lambda _: [{
        "state": "APPROVED", "author_association": "COLLABORATOR", "commit_id": sha,
        "submitted_at": "2026-01-01T10:00:00Z", "user": {"login": "asling3", "type": "User"}}])
    assert sha in policy.check_prior_approval(tmp_path, base, policy.changed_paths(tmp_path, base), {
        "pull_request": {"user": {"login": "EverForests"}}})


def test_semantic_boolean_cannot_masquerade_as_numeric_send_count():
    data = corpus()
    answers = copy.deepcopy(data["positive_controls"])
    answers[7]["result"]["sends"] = True
    assert semantic.evaluate_answers(data, answers)["failures"]


def test_semantic_extra_narrative_cannot_hide_outside_the_rubric():
    data = corpus()
    answers = copy.deepcopy(data["positive_controls"])
    answers[0]["unreviewed_narrative"] = "Guaranteed future profit"
    assert semantic.evaluate_answers(data, answers)["failures"]


def test_model_response_hash_must_be_recomputable():
    profile = json.loads((ROOT / ".github/governance/runtime-model.json").read_text())
    receipt = {"evidence_class": "recorded-model-output", "model_id": profile["deep_model"],
               "provider": profile["provider"], "captured_at": "2026-01-01T00:00:00Z",
               "configuration_sha256": semantic.configuration_digest(ROOT),
               "corpus_sha256": "corpus-digest", "provider_response_sha256": "a" * 64,
               "raw_response": "[]", "answers": corpus()["positive_controls"]}
    with pytest.raises(policy.PolicyFailure, match="hash does not match"):
        semantic.validate_model_receipt(ROOT, corpus(), "corpus-digest", receipt)
