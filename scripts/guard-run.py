#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def append_command_log(
    *,
    command: str,
    decision: str,
    reason: str,
    action: str,
    approved: bool,
    returncode: int | str,
) -> None:
    log_dir = Path(os.environ.get("OMP_GUARD_LOG_DIR", str(Path.home() / "AgentWork" / ".omp-guard-logs")))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_dir.chmod(0o700)

    log_path = log_dir / "commands.log"

    event = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user": os.environ.get("USER", ""),
        "cwd": str(Path.cwd()),
        "decision": decision,
        "reason": reason,
        "action": action,
        "approved": approved,
        "returncode": returncode,
        "command": command,
    }

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")

    log_path.chmod(0o600)


def run_classifier(policy: Path, command: str) -> tuple[str, str, str]:
    classifier = Path(__file__).resolve().parent / "classify-command.py"

    if not classifier.exists():
        raise SystemExit(f"missing classifier: {classifier}")

    result = subprocess.run(
        [sys.executable, str(classifier), "--policy", str(policy), command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "classifier failed")

    decision = ""
    reason = ""

    for line in result.stdout.splitlines():
        if line.startswith("decision="):
            decision = line.split("=", 1)[1].strip()
        elif line.startswith("reason="):
            reason = line.split("=", 1)[1].strip()

    if decision not in {"allow", "ask", "block"}:
        raise SystemExit(f"classifier returned invalid decision: {decision}")

    return decision, reason, result.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify and optionally execute a command through omp-guard policy."
    )
    parser.add_argument(
        "--policy",
        default="policies/default.yml",
        help="Path to guard policy file. Default: policies/default.yml",
    )
    parser.add_argument(
        "--approve-ask",
        action="store_true",
        help="Execute commands classified as ask. Blocked commands are still refused.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify and log, but do not execute.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to classify and execute. Use -- before commands with flags.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    command = " ".join(args.command).strip()
    if command.startswith("-- "):
        command = command[3:].strip()

    if not command:
        print("usage: scripts/guard-run.py [--approve-ask] [--dry-run] -- <command>", file=sys.stderr)
        return 2

    policy = Path(args.policy)
    decision, reason, classifier_output = run_classifier(policy, command)

    print(classifier_output)

    if decision == "block":
        print("omp-guard: blocked command refused", file=sys.stderr)
        append_command_log(
            command=command,
            decision=decision,
            reason=reason,
            action="refused-block",
            approved=False,
            returncode="not-run",
        )
        return 10

    if decision == "ask" and not args.approve_ask:
        print("omp-guard: ask-classified command refused; rerun with --approve-ask to execute", file=sys.stderr)
        append_command_log(
            command=command,
            decision=decision,
            reason=reason,
            action="refused-ask",
            approved=False,
            returncode="not-run",
        )
        return 20

    if args.dry_run:
        append_command_log(
            command=command,
            decision=decision,
            reason=reason,
            action="dry-run",
            approved=args.approve_ask,
            returncode="not-run",
        )
        return 0

    result = subprocess.run(command, shell=True, executable="/bin/zsh")
    append_command_log(
        command=command,
        decision=decision,
        reason=reason,
        action="executed",
        approved=args.approve_ask,
        returncode=result.returncode,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
