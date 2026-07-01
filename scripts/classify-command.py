#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


def usage() -> None:
    print("usage: scripts/classify-command.py [--policy policies/default.yml] <command>", file=sys.stderr)


def normalize(command: str) -> str:
    return re.sub(r"\s+", " ", command.strip())


def load_command_rules(policy_path: Path) -> dict[str, list[str]]:
    if not policy_path.exists():
        raise SystemExit(f"missing policy file: {policy_path}")

    rules = {
        "allow": [],
        "askBefore": [],
        "block": [],
    }

    in_commands = False
    current: str | None = None

    for line in policy_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))

        if indent == 0 and stripped.endswith(":"):
            in_commands = stripped == "commands:"
            current = None
            continue

        if not in_commands:
            continue

        if indent == 2 and stripped.endswith(":"):
            key = stripped[:-1]
            current = key if key in rules else None
            continue

        if current and indent >= 4 and stripped.startswith("- "):
            value = stripped[2:].strip()
            if len(value) >= 2 and value[0] == "\"" and value[-1] == "\"":
                value = value[1:-1]
            if value:
                rules[current].append(value)

    return rules


def matches(command: str, rule: str) -> bool:
    command = normalize(command)
    rule = normalize(rule)

    if not rule:
        return False

    if rule.startswith("-") or rule.startswith("--") or "=" in rule:
        return rule in command

    return command == rule or command.startswith(rule + " ")


def classify(command: str, rules: dict[str, list[str]]) -> tuple[str, str]:
    command = normalize(command)

    for rule in rules["block"]:
        if matches(command, rule):
            return "block", f"matched block rule: {rule}"

    for rule in rules["askBefore"]:
        if matches(command, rule):
            return "ask", f"matched askBefore rule: {rule}"

    for rule in rules["allow"]:
        if matches(command, rule):
            return "allow", f"matched allow rule: {rule}"

    return "ask", "no explicit allow rule matched"


def main() -> int:
    args = sys.argv[1:]
    policy_path = Path("policies/default.yml")

    if args[:2] and args[0] == "--policy":
        if len(args) < 3:
            usage()
            return 2
        policy_path = Path(args[1])
        args = args[2:]

    command = normalize(" ".join(args))

    if not command:
        usage()
        return 2

    rules = load_command_rules(policy_path)
    decision, reason = classify(command, rules)

    print(f"decision={decision}")
    print(f"reason={reason}")
    print(f"command={command}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
