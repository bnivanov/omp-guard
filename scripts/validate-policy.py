#!/usr/bin/env python3
"""
Validate the omp-guard default policy.

This is intentionally dependency-free. It does not fully parse YAML; it checks
for required top-level sections and critical safety rules so the policy cannot
silently lose the controls that omp-guard depends on.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"policy validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    policy_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("policies/default.yml")

    if not policy_path.exists():
        fail(f"missing policy file: {policy_path}")

    text = policy_path.read_text(encoding="utf-8")

    if "\t" in text:
        fail("policy contains tabs; use spaces for YAML indentation")

    required_top_level = [
        "schemaVersion",
        "name",
        "description",
        "workspace",
        "credentialAndPrivatePaths",
        "commands",
        "network",
        "logging",
    ]

    for key in required_top_level:
        if not re.search(rf"^{re.escape(key)}\s*:", text, flags=re.MULTILINE):
            fail(f"missing top-level section: {key}")

    required_literals = [
        "$HOME/AgentWork",
        "/Users/Shared",
        "/Users/Shared/**",
        "$HOME/Library/Mobile Documents",
        "**/.ssh",
        "**/.ssh/**",
        "**/.config",
        "**/.config/**",
        "**/.omp-guard-state",
        "**/.omp-guard-state/**",
        "**/Library/Keychains",
        "**/Library/Keychains/**",
        "git push",
        "sudo",
        "rm -rf /",
        "sudo rm -rf /",
        "diskutil",
        "systemsetup -setremotelogin on",
        "docker run --privileged",
        "$HOME/AgentWork/.omp-guard-logs/launch.log",
        "$HOME/AgentWork/.omp-guard-logs/commands.log",
    ]

    for literal in required_literals:
        if literal not in text:
            fail(f"missing required rule: {literal}")

    required_nested_markers = [
        "allowedRoots:",
        "deniedPaths:",
        "deny:",
        "allow:",
        "askBefore:",
        "block:",
        "launchLog:",
        "commandLog:",
    ]

    for marker in required_nested_markers:
        if marker not in text:
            fail(f"missing policy marker: {marker}")

    print(f"policy validation passed: {policy_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
