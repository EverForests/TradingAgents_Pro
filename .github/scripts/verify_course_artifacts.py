"""Check the course schema, normative references and PR AI-use records."""

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True)


def check_registry() -> None:
    registry = yaml.safe_load(Path("docs/req/requirements.yaml").read_text())
    schema = json.loads(Path("docs/req/req-schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(registry)
    requirements = registry["requirements"]
    ids = [entry["id"] for entry in requirements]
    if len(set(ids)) != len(ids):
        raise ValueError("Requirement IDs must be unique")

    contract_doc = Path("docs/architecture/interface-contracts.md").read_text()
    verification_doc = Path("docs/code-governance/verification-constraints.md").read_text()
    contracts = set(re.findall(r"^## (C\d+)\b", contract_doc, re.MULTILINE))
    cases = set()
    for row in verification_doc.splitlines():
        if row.startswith("| T-"):
            cases.update(case.strip() for case in row.split("|")[1].split(","))
    for entry in requirements:
        unresolved = (set(entry["contracts"]) - contracts) | (set(entry["test_cases"]) - cases)
        if unresolved:
            raise ValueError(f"{entry['id']} has unresolved references: {sorted(unresolved)}")


def entries(content: str) -> dict:
    records = yaml.safe_load(content)["entries"]
    result = {record["id"]: record for record in records}
    if len(result) != len(records):
        raise ValueError("AI-use IDs must be unique")
    return result


def check_ai_log(base: str | None) -> None:
    log = "docs/ai-use-log.yaml"
    current = entries(Path(log).read_text())
    if base is None:
        return
    common = git("merge-base", base, "HEAD").strip()
    changed = git("diff", "--name-only", "-z", common, "HEAD").split("\0")
    if any(name.startswith(("tradingagents/", "cli/", "src/", "prompts/")) for name in changed):
        if log not in changed:
            raise ValueError("Application and runtime prompt changes require an AI-use record")
        # The first course PR adds this log to the upstream-based main branch.
        previous = entries(git("show", f"{common}:{log}")) if git(
            "ls-tree", "--name-only", common, "--", log
        ).strip() else {}
        new_records = [record for key, record in current.items() if key not in previous]
        if not any(
            all(isinstance(record.get(key), str) and record[key].strip() for key in ("tool", "scope"))
            for record in new_records
        ):
            raise ValueError("Add a new AI-use record with its tool and scope")


if __name__ == "__main__":
    check_registry()
    check_ai_log(sys.argv[1] if len(sys.argv) > 1 else None)
    if Path(".opencode/opencode.jsonc").read_bytes() != Path(".opencode/permissions.jsonc").read_bytes():
        raise ValueError("The two OpenCode permission copies differ")
    print("Course schema, references, AI-use log and permission copies validated")
