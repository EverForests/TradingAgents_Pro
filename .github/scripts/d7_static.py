"""Run actual source type/security analysis with exact, reviewed finding budgets."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def fingerprints(records: list[dict[str, Any]]) -> list[str]:
    return sorted(hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()
                  for r in records)


def compare_findings(actual: list[str], allowed: list[str]) -> list[str]:
    """Exact multiset budget; no blanket error-code, path or message suppression."""
    remaining = list(allowed)
    new = []
    for item in actual:
        if item in remaining:
            remaining.remove(item)
        else:
            new.append(item)
    return new


def analyze(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sources = ["tradingagents", "cli", "main.py", ".github/scripts"]
    typed = subprocess.run(
        [sys.executable, "-m", "mypy", "--config-file", "mypy.ini", "--output", "json",
         *sources], cwd=root, capture_output=True, text=True, check=False,
    )
    if typed.returncode not in (0, 1) or typed.stderr.strip():
        raise RuntimeError("Type checker did not complete: " + typed.stderr[:160])
    type_records = []
    for line in typed.stdout.splitlines():
        if line.strip():
            record = json.loads(line)
            if record.get("severity") == "error":
                item = {key: record.get(key) for key in
                        ("file", "line", "column", "code", "message")}
                source = root / record["file"]
                if source.is_file():
                    line_text = source.read_text().splitlines()[record["line"] - 1]
                    item["source_line_sha256"] = hashlib.sha256(line_text.encode()).hexdigest()
                type_records.append(item)
    secured = subprocess.run(
        [sys.executable, "-m", "bandit", "-r", "tradingagents", "cli", ".github/scripts",
         "-f", "json", "--ignore-nosec", "-q"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if secured.returncode not in (0, 1):
        raise RuntimeError("Security analyzer did not complete")
    data = json.loads(secured.stdout)
    if data.get("errors"):
        raise RuntimeError("Security analyzer omitted a source file")
    security_records = []
    for finding in data["results"]:
        item = {key: finding.get(key) for key in
                ("filename", "test_id", "line_number", "issue_text",
                 "issue_severity", "issue_confidence")}
        item["code_sha256"] = hashlib.sha256(finding["code"].encode()).hexdigest()
        security_records.append(item)
    return type_records, security_records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--policy-root", type=Path)
    parser.add_argument("--report", type=Path, default=Path(".d7-receipts/static.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    policy = args.policy_root or root / ".github/governance"
    baseline = json.loads((policy / "static-baseline.json").read_text())
    types, security = analyze(root)
    new_types = compare_findings(fingerprints(types), baseline["type_fingerprints"])
    new_security = compare_findings(fingerprints(security), baseline["security_fingerprints"])
    report = {
        "schema_version": "1.0", "gate": "static", "evidence_class": "source-analysis",
        "status": "fail" if new_types or new_security else "pass",
        "observed_type_findings": len(types), "observed_security_findings": len(security),
        "new_type_findings": new_types, "new_security_findings": new_security,
        "legacy_debt": "Existing findings remain disclosed; no blanket suppression is used.",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 1 if new_types or new_security else 0


if __name__ == "__main__":
    sys.exit(main())
