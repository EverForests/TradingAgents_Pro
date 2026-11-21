"""Frozen source-grounded evaluation and actual five-control behavioral replay.

Recorded new-model output is mandatory for prompt/model changes, not substituted
with synthetic positive answers. Governance ADR-002 defines the evidence limits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from d7_policy import SEMANTIC, PolicyFailure, changed_paths, require


def configuration_digest(root: Path) -> str:
    files: list[Path] = []
    for prefix in SEMANTIC:
        path = root / prefix
        if path.is_dir():
            files.extend(p for p in path.rglob("*") if p.is_file() and p.suffix in {".py", ".yaml", ".json"})
        elif path.is_file():
            files.append(path)
    profile = root / ".github/governance/runtime-model.json"
    if profile.is_file():
        files.append(profile)
    records = [(p.relative_to(root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
               for p in sorted(set(files))]
    return hashlib.sha256(json.dumps(records).encode()).hexdigest()


def evaluate_answers(corpus: dict[str, Any], answers: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {case["id"]: case for case in corpus["cases"]}
    actual = {answer["id"]: answer for answer in answers}
    require(len(actual) == len(answers), "Duplicate semantic answers")
    require(set(actual) == set(expected), "Missing or unexpected semantic case")
    failures = []
    for identifier, case in expected.items():
        answer = actual[identifier]
        if answer.get("result") != case["expected"]:
            failures.append(identifier)
        if set(answer.get("supported_facts", [])) != set(case["required_facts"]):
            failures.append(identifier + ":unsupported-or-missing-fact")
        if answer.get("unsupported_claims", []) != []:
            failures.append(identifier + ":unsupported-claim")
    return {"cases": len(expected), "failures": failures,
            "required_field_agreement": (len(expected) - len({x.split(":")[0] for x in failures})) / len(expected)}


def validate_model_receipt(root: Path, corpus: dict[str, Any], corpus_sha: str,
                           receipt: dict[str, Any]) -> dict[str, Any]:
    require(receipt.get("evidence_class") == "recorded-model-output",
            "A new model/prompt cannot use fixture answers as model-quality evidence")
    require(receipt.get("configuration_sha256") == configuration_digest(root),
            "Evaluation belongs to another model/prompt configuration")
    require(receipt.get("corpus_sha256") == corpus_sha, "Evaluation belongs to another corpus")
    for key in ["model_id", "provider", "captured_at", "provider_response_sha256"]:
        require(isinstance(receipt.get(key), str) and receipt[key].strip(),
                "Incomplete model-output provenance: " + key)
    evaluation = evaluate_answers(corpus, receipt["answers"])
    require(not evaluation["failures"], "Frozen semantic threshold failed")
    return evaluation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--policy-root", type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--report", type=Path, default=Path(".d7-receipts/semantic.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    policy = args.policy_root or root / ".github/governance"
    corpus_path = policy / "semantic-suite.json"
    corpus = json.loads(corpus_path.read_text())
    digest = hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    report: dict[str, Any] = {"schema_version": "1.0", "gate": "semantic",
                              "evidence_class": "deterministic-behavior-and-rubric-controls",
                              "corpus_sha256": digest}
    code = 1
    try:
        require(corpus["rubric_version"] == "1.0.0", "Unsupported semantic rubric")
        require(corpus["thresholds"] == {"required_field_agreement": 1.0, "safety_escapes": 0,
                                         "unsupported_claims": 0}, "Frozen thresholds changed")
        controls = evaluate_answers(corpus, corpus["positive_controls"])
        require(not controls["failures"], "Positive rubric controls fail")
        paths = changed_paths(root, args.base)
        changed = any(p.startswith(SEMANTIC) or p == ".github/governance/runtime-model.json" for p in paths)
        report["model_change"] = changed
        if changed:
            receipts = list((root / "docs/governance/evaluations").glob("*.json"))
            valid = []
            for receipt in receipts:
                try:
                    valid.append(validate_model_receipt(root, corpus, digest,
                                                       json.loads(receipt.read_text())))
                except (PolicyFailure, KeyError, ValueError):
                    continue
            require(valid, "Prompt/model changes need matching recorded model output passing frozen thresholds")
            report["model_output_evaluation"] = valid[0]
        command = [sys.executable, "-m", "pytest", "-q", "--tb=short",
                   "--junitxml=.d7-receipts/semantic-behavior.xml", *corpus["behavioral_nodes"]]
        replay = subprocess.run(command, cwd=root, check=False)
        require(replay.returncode == 0, "A five-control behavioral replay failed")
        report.update(status="pass", rubric_controls=controls,
                      natural_model_claim="No new natural-model measurement for unchanged model/prompt code")
        code = 0
    except (PolicyFailure, KeyError, ValueError) as exc:
        report.update(status="fail", reason=str(exc))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return code


if __name__ == "__main__":
    sys.exit(main())
