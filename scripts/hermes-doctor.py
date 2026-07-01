#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hermes_common as hc  # noqa: E402
import seatbelt  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent


class Reporter:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def ok(self, message: str) -> None:
        print(f"OK: {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"WARN: {message}")

    def fail(self, message: str) -> None:
        self.errors.append(message)
        print(f"FAIL: {message}")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def check_required_files(reporter: Reporter) -> None:
    required = [
        "scripts/hermes_common.py",
        "scripts/hermes-light-launch.py",
        "scripts/hermes-doctor.py",
        "scripts/hermes-profile-doctor.py",
        "scripts/test-hermes-guard.sh",
        "policies/hermes-v1.yml",
        "policies/hermes-orchestrator.yml",
        "policies/hermes-research.yml",
        "policies/hermes-dev.yml",
        "docs/hermes-always-on-v1.md",
        "docs/hermes-profile-model.md",
        "docs/hermes-operations-runbook.md",
    ]
    for rel in required:
        path = ROOT / rel
        if path.exists():
            reporter.ok(f"exists: {rel}")
        else:
            reporter.fail(f"missing: {rel}")


def check_location(reporter: Reporter) -> None:
    root = ROOT.resolve()
    allowed = hc.allowed_root()
    if hc.is_under(root, allowed):
        reporter.ok(f"repo is inside AgentWork: {root}")
    else:
        reporter.fail(f"repo is outside AgentWork: {root}")
    if os.environ.get("OMP_GUARD_PERSONAL_HOME"):
        reporter.ok("OMP_GUARD_PERSONAL_HOME is set")
    else:
        reporter.fail("OMP_GUARD_PERSONAL_HOME is not set")


def check_hermes_binary(reporter: Reporter) -> None:
    hermes_bin = hc.find_hermes_bin()
    if not hermes_bin:
        reporter.fail("Hermes CLI not found on PATH; install Hermes or set HERMES_GUARD_HERMES_BIN")
        return
    reporter.ok(f"Hermes CLI found: {hermes_bin}")
    result = subprocess.run([hermes_bin, "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode == 0:
        reporter.ok(f"Hermes --version returned 0: {(result.stdout or result.stderr).strip()}")
    else:
        reporter.warn(f"Hermes --version returned {result.returncode}: {(result.stdout + result.stderr).strip()}")


def check_policies(reporter: Reporter) -> None:
    for rel in [
        "policies/hermes-v1.yml",
        "policies/hermes-orchestrator.yml",
        "policies/hermes-research.yml",
        "policies/hermes-dev.yml",
    ]:
        result = run([sys.executable, "scripts/validate-policy.py", rel])
        if result.returncode == 0:
            reporter.ok(f"policy validates: {rel}")
        else:
            reporter.fail(f"policy validation failed: {rel}")
            print(result.stdout)
            print(result.stderr, file=sys.stderr)


def check_seatbelt(reporter: Reporter) -> None:
    capable, detail = seatbelt.capability()
    if capable:
        reporter.ok(f"Seatbelt capability: {detail}")
    elif sys.platform == "darwin":
        reporter.fail(f"Seatbelt unavailable on macOS: {detail}")
    else:
        reporter.warn(f"Seatbelt unavailable: {detail}")


def check_profiles(reporter: Reporter) -> None:
    existing = []
    missing = []
    for profile in hc.CORE_PROFILES:
        if hc.profile_root(profile).exists():
            existing.append(profile)
        else:
            missing.append(profile)
    if missing:
        reporter.warn("missing Hermes profiles: " + ", ".join(missing) + " (run `hermes-guard bootstrap-profiles`)")
    for profile in existing:
        result = run([sys.executable, "scripts/hermes-profile-doctor.py", profile])
        if result.returncode == 0:
            reporter.ok(f"profile doctor passes: {profile}")
        else:
            reporter.fail(f"profile doctor failed: {profile}")
            print(result.stdout)
            print(result.stderr, file=sys.stderr)


def main() -> int:
    reporter = Reporter()
    print("hermes-doctor")
    print(f"repo: {ROOT}")
    print()

    check_location(reporter)
    check_required_files(reporter)
    check_policies(reporter)
    check_hermes_binary(reporter)
    check_seatbelt(reporter)
    check_profiles(reporter)

    print()
    print(f"warnings: {len(reporter.warnings)}")
    print(f"errors: {len(reporter.errors)}")
    return 1 if reporter.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
