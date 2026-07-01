#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hermes_common as hc  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent


def usage() -> int:
    print(
        """usage:
  hermes-guard doctor
  hermes-guard profile-doctor <profile> [--init]
  hermes-guard bootstrap-profiles
  hermes-guard validate-policy [policy-path]
  hermes-guard light --profile <profile> [--] [hermes args...]
  hermes-guard gateway --profile <profile> [--] [gateway args...]
""",
        file=sys.stderr,
    )
    return 2


def run_script(script_name: str, args: list[str], *, preserve_cwd: bool = False) -> int:
    script = ROOT / "scripts" / script_name
    if not script.exists():
        print(f"hermes-guard: missing script: {script}", file=sys.stderr)
        return 127
    cwd = None if preserve_cwd else ROOT
    return subprocess.call([sys.executable, str(script), *args], cwd=cwd)


def bootstrap_profiles() -> int:
    failed = False
    for profile in hc.CORE_PROFILES:
        code = run_script("hermes-profile-doctor.py", [profile, "--init"])
        failed = failed or code != 0
    return 1 if failed else 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in {"-h", "--help", "help"}:
        return usage()

    command = argv[0]
    rest = argv[1:]

    if command == "doctor":
        return run_script("hermes-doctor.py", rest)
    if command == "profile-doctor":
        if not rest:
            print("usage: hermes-guard profile-doctor <profile> [--init]", file=sys.stderr)
            return 2
        return run_script("hermes-profile-doctor.py", rest)
    if command == "bootstrap-profiles":
        return bootstrap_profiles()
    if command == "validate-policy":
        policy = rest or ["policies/hermes-v1.yml"]
        return run_script("validate-policy.py", policy)
    if command == "light":
        return run_script("hermes-light-launch.py", rest, preserve_cwd=True)
    if command == "gateway":
        return run_script("hermes-light-launch.py", ["--gateway", "--allow-estate-cwd", *rest], preserve_cwd=True)

    print(f"hermes-guard: unknown command: {command}", file=sys.stderr)
    return usage()


if __name__ == "__main__":
    raise SystemExit(main())
