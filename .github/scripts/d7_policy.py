"""D7 policy checks: prospective approval, API/permission contracts and audit scope.

Governance ADR: docs/architecture/adr/002-d7-enforcement.md. No application imports.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

APP = ("tradingagents/", "cli/", "src/", "prompts/")
SENSITIVE = (*APP, ".github/", ".opencode/", "mypy.ini", "pyproject.toml")
SEMANTIC = ("prompts/", "tradingagents/agents/", "tradingagents/llm_clients/",
            "tradingagents/default_config.py")
REVIEWERS = {"EverForests", "KyrieT331", "wmq12138", "majiaqi-yan", "asling3"}
ACTIVATION = "7da6ecc9ff665d096b3def5be9ee9601628ae05e"


class PolicyFailure(ValueError):
    """An explicit policy refusal; never an accepted evaluation."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise PolicyFailure(message)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def changed_paths(root: Path, base: str, head: str = "HEAD") -> list[str]:
    require(bool(base) and len(base) == 40, "A full comparison base is required")
    return [x for x in git(root, "diff", "--name-only", base, head).splitlines() if x]


def prospective_base(root: Path, base: str) -> str:
    """A fixed Git object excludes historical implementation, never future changes."""
    try:
        git(root, "merge-base", "--is-ancestor", base, ACTIVATION)
        git(root, "merge-base", "--is-ancestor", ACTIVATION, "HEAD")
        return ACTIVATION
    except subprocess.CalledProcessError:
        return base


def api_surface(root: Path) -> dict[str, str]:
    """Collect public callable signatures without importing/executing application code."""
    result: dict[str, str] = {}
    for package in ("tradingagents", "cli"):
        for path in sorted((root / package).rglob("*.py")):
            tree = ast.parse(path.read_text(), filename=path.name)
            rel = path.relative_to(root).as_posix()
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        result[f"{rel}:{node.name}"] = ast.dump(node.args)
                elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                    for method in node.body:
                        if (isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                                and (not method.name.startswith("_") or method.name == "__init__")):
                            result[f"{rel}:{node.name}.{method.name}"] = ast.dump(method.args)
    return result


def runtime_dependencies(text: str) -> list[str]:
    import tomllib

    return list(tomllib.loads(text)["project"]["dependencies"])


def permission_edits(config: dict[str, Any]) -> list[dict[str, Any]]:
    result = [r for r in config["permissions"] if r["action"] != "read"]
    for name, agent in config.get("agents", {}).items():
        result.append({"agent": name, "permissions": agent.get("permissions", [])})
    return result


def check_contracts(root: Path, paths: list[str], policy_root: Path) -> None:
    left = root / ".opencode/opencode.jsonc"
    right = root / ".opencode/permissions.jsonc"
    require(left.read_bytes() == right.read_bytes(), "OpenCode permission copies differ")
    baseline = json.loads((policy_root / "contracts.json").read_text())
    require(permission_edits(json.loads(left.read_text())) == baseline["edit_permissions"],
            "Agent edit authority changed; renew the permission design and human review")
    require(runtime_dependencies((root / "pyproject.toml").read_text())
            == baseline["runtime_dependencies"],
            "Runtime dependencies changed; an explicit dependency contract revision is required")
    require(api_surface(root) == baseline["api_surface"],
            "Public API surface changed; renew the API contract with ADR and human review")
    for entry in json.loads((root / "src/source-manifest.json").read_text())["sources"]:
        # Manifest field names are intentionally taken from the frozen source format.
        original = root / entry["runnable_path"]
        copied = root / entry["course_source_path"]
        require(original.read_bytes() == copied.read_bytes(), "Course source snapshot differs")
        require(hashlib.sha256(original.read_bytes()).hexdigest() == entry["sha256"],
                "Course source manifest hash differs")
    if any(p.startswith(SENSITIVE) or p == "main.py" for p in paths):
        require(any(p.startswith("docs/architecture/adr/") and p.endswith(".md") for p in paths),
                "Safety/governance changes require an accompanying ADR")
        owners = (root / ".github/CODEOWNERS").read_text()
        for pattern in ["/.github/", "/tradingagents/", "/docs/architecture/adr/"]:
            require(pattern in owners, "A safety path lacks a CODEOWNERS rule")


def review_approval(test_sha: str, reviews: list[dict[str, Any]], author: str,
                    first_implementation_at: str) -> dict[str, Any]:
    before = datetime.fromisoformat(first_implementation_at.replace("Z", "+00:00"))
    for review in reviews:
        user = review.get("user", {})
        if (review.get("state") != "APPROVED" or review.get("commit_id") != test_sha
                or user.get("login") not in REVIEWERS or user.get("login") == author
                or user.get("type") != "User"):
            continue
        when = datetime.fromisoformat(review["submitted_at"].replace("Z", "+00:00"))
        if when < before:
            return review
    raise PolicyFailure("No independent exact-test approval before implementation")


def github_json(path: str) -> Any:
    require(path.startswith("/repos/EverForests/TradingAgents_Pro/"), "Unexpected repository")
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "cs5351-d7"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request("https://api.github.com" + path, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def check_prior_approval(root: Path, base: str, paths: list[str], event: dict[str, Any]) -> str:
    if not any(p.startswith(APP) or p == "main.py" for p in paths):
        return "not-applicable: no application or runtime-prompt implementation"
    records = sorted((root / "docs/governance/approvals").glob("*.json"))
    require(records, "Application changes require a prior test-approval record")
    commits = git(root, "rev-list", "--reverse", f"{base}..HEAD", "--",
                  "tradingagents", "cli", "src", "prompts", "main.py").splitlines()
    require(commits, "Cannot identify first implementation commit")
    first = commits[0]
    first_at = git(root, "show", "-s", "--format=%cI", first)
    author = event.get("pull_request", {}).get("user", {}).get("login", "")
    require(author, "Application approval requires pull-request context; direct push is refused")
    reasons = []
    for path in records:
        try:
            require(path.relative_to(root).as_posix() in paths,
                    "New application work requires a newly supplied approval record")
            record = json.loads(path.read_text())
            sha = record["test_revision"]
            require(bool(__import__("re").fullmatch("[0-9a-f]{40}", sha)), "Use full test SHA")
            require(set(record["implementation_paths"]) == {
                p for p in paths if p.startswith(APP) or p == "main.py"
            }, "Approval scope differs from the application patch")
            git(root, "merge-base", "--is-ancestor", sha, first)
            test_paths = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha)
            require(any(p.startswith(("tests/", "test/")) for p in test_paths.splitlines()),
                    "Approved revision contains no tests")
            require(not any(p.startswith(APP) or p == "main.py" for p in test_paths.splitlines()),
                    "Approved test revision already changes application code")
            require(not git(root, "diff", "--name-only", sha, "HEAD", "--", "tests", "test"),
                    "Tests changed after their approval; renew exact-test review")
            number = int(record["approval_pr"])
            reviews = github_json(f"/repos/EverForests/TradingAgents_Pro/pulls/{number}/reviews")
            review_approval(sha, reviews, author, first_at)
            return f"approved tests {sha} through PR {number}"
        except (KeyError, ValueError, subprocess.CalledProcessError) as exc:
            reasons.append(type(exc).__name__)
    raise PolicyFailure("No valid prior approval record: " + ", ".join(reasons))


def check_ai_use(root: Path, base: str, paths: list[str]) -> None:
    guarded = (*SENSITIVE, "test/governance/", "docs/governance/", "docs/delivery-readiness.md")
    if not any(p.startswith(guarded) or p == "main.py" for p in paths):
        return
    require("docs/ai-use-log.yaml" in paths, "Governance/code/prompt changes need an AI-use update")
    previous = (git(root, "show", f"{base}:docs/ai-use-log.yaml")
                if git(root, "ls-tree", "--name-only", base, "--", "docs/ai-use-log.yaml") else "")
    current = (root / "docs/ai-use-log.yaml").read_text()
    old_ids = set(__import__("re").findall(r"^- id: (.+)$", previous, __import__("re").M))
    new_ids = set(__import__("re").findall(r"^- id: (.+)$", current, __import__("re").M))
    require(new_ids - old_ids, "Add an attributable new AI-use entry; edits alone do not qualify")


def aggregate(results: dict[str, str]) -> None:
    expected = {"test", "course-artifacts", "smoke-install", "lint", "d7-governance"}
    require(set(results) == expected, "Missing or unexpected required job")
    require(all(value == "success" for value in results.values()),
            "A failed, skipped, cancelled or missing gate blocks release")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base", required=True)
    parser.add_argument("--policy-root", type=Path)
    parser.add_argument("--report", type=Path, default=Path(".d7-receipts/policy.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    policy_root = args.policy_root or root / ".github/governance"
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    event = json.loads(Path(event_path).read_text()) if event_path else {}
    report: dict[str, Any] = {"schema_version": "1.0", "gate": "policy", "base": args.base,
                              "evidence_class": "static-policy", "checks": {}}
    try:
        require(os.environ.get("GITHUB_EVENT_NAME") != "pull_request_target",
                "Privileged execution of untrusted head is forbidden")
        paths = changed_paths(root, args.base)
        check_contracts(root, paths, policy_root)
        report["checks"]["contracts_api_permissions"] = "pass"
        active_base = prospective_base(root, args.base)
        report["activation_revision"] = ACTIVATION
        report["historical_application_excluded"] = active_base != args.base
        report["checks"]["prior_test_approval"] = check_prior_approval(
            root, active_base, changed_paths(root, active_base), event)
        check_ai_use(root, args.base, paths)
        report["checks"]["ai_use"] = "pass"
        report["status"] = "pass"
        code = 0
    except (PolicyFailure, KeyError, OSError, subprocess.CalledProcessError) as exc:
        report.update(status="fail", reason=str(exc))
        code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return code


if __name__ == "__main__":
    sys.exit(main())
