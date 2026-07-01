#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
AGENTWORK = HOME / "AgentWork"
LOG_DIR = AGENTWORK / ".omp-guard-logs"


errors: list[str] = []
warnings: list[str] = []


def ok(message: str) -> None:
    print(f"OK: {message}")


def warn(message: str) -> None:
    warnings.append(message)
    print(f"WARN: {message}")


def fail(message: str) -> None:
    errors.append(message)
    print(f"FAIL: {message}")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def is_executable(path: Path) -> bool:
    return path.exists() and os.access(path, os.X_OK)


def check_user() -> None:
    work_user = os.environ.get("OMP_GUARD_WORK_USER", "")
    user = os.environ.get("USER") or run(["id", "-un"]).stdout.strip()
    if not work_user:
        ok(f"running as {user} (no OMP_GUARD_WORK_USER set — user check skipped)")
    elif user == work_user:
        ok(f"running as {work_user}")
    else:
        warn(f"expected user {work_user}, got {user} (set OMP_GUARD_WORK_USER to change)")


def check_location() -> None:
    root_real = ROOT.resolve()
    agentwork_real = AGENTWORK.resolve()

    if str(root_real).startswith(str(agentwork_real) + "/") or root_real == agentwork_real:
        ok(f"repo is inside AgentWork: {root_real}")
    else:
        fail(f"repo is outside AgentWork: {root_real}")

    personal_home = os.environ.get("OMP_GUARD_PERSONAL_HOME")
    if not personal_home:
        fail("OMP_GUARD_PERSONAL_HOME is not set — personal account paths will not be protected")
        personal_home = "/nonexistent"
    forbidden_prefixes = [
        Path(personal_home),
        Path("/Users/Shared"),
        HOME / "Desktop",
        HOME / "Documents",
        HOME / "Downloads",
        HOME / "Library" / "Mobile Documents",
    ]

    for prefix in forbidden_prefixes:
        try:
            prefix_real = prefix.resolve()
        except FileNotFoundError:
            prefix_real = prefix

        if str(root_real).startswith(str(prefix_real)):
            fail(f"repo is under forbidden path: {prefix}")


def check_required_files() -> None:
    required = [
        "README.md",
        "install.sh",
        "omp-guard",
        "omp-sbx",
        "policies/default.yml",
        "scripts/validate-policy.py",
        "scripts/classify-command.py",
        "scripts/guard-run.py",
        "scripts/test-guard.sh",
        "scripts/status.py",
        "scripts/menu.py",
        "scripts/security.py",
        "scripts/seatbelt.py",
        "scripts/egress-proxy.py",
        "scripts/seatbelt-selftest.py",
        "docs/security-models.md",
    ]

    for rel in required:
        path = ROOT / rel
        if path.exists():
            ok(f"exists: {rel}")
        else:
            fail(f"missing: {rel}")

    executable = [
        "install.sh",
        "omp-guard",
        "omp-sbx",
        "scripts/validate-policy.py",
        "scripts/classify-command.py",
        "scripts/guard-run.py",
        "scripts/test-guard.sh",
        "scripts/status.py",
        "scripts/menu.py",
        "scripts/security.py",
        "scripts/seatbelt.py",
        "scripts/egress-proxy.py",
        "scripts/seatbelt-selftest.py",
    ]

    for rel in executable:
        path = ROOT / rel
        if is_executable(path):
            ok(f"executable: {rel}")
        else:
            fail(f"not executable: {rel}")


def check_policy() -> None:
    result = run([sys.executable, "scripts/validate-policy.py"])
    if result.returncode == 0:
        ok("policy validation passes")
    else:
        fail("policy validation failed")
        print(result.stdout)
        print(result.stderr, file=sys.stderr)


def check_classifier() -> None:
    cases = [
        ("git status --short", "decision=allow"),
        ("git push origin main", "decision=ask"),
        ("sudo rm -rf /", "decision=block"),
    ]

    for command, expected in cases:
        result = run([sys.executable, "scripts/classify-command.py", command])
        output = result.stdout + result.stderr

        if result.returncode == 0 and expected in output:
            ok(f"classifier: {command} -> {expected.removeprefix('decision=')}")
        else:
            fail(f"classifier unexpected result for: {command}")
            print(output)


def check_guard_runner() -> None:
    env = os.environ.copy()
    tmp_log_dir = ROOT / ".tmp-doctor-logs"
    if tmp_log_dir.exists():
        subprocess.run(["rm", "-rf", str(tmp_log_dir)], check=False)
    env["OMP_GUARD_LOG_DIR"] = str(tmp_log_dir)

    try:
        allow = subprocess.run(
            [sys.executable, "scripts/guard-run.py", "--dry-run", "--", "git status --short"],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if allow.returncode == 0 and "decision=allow" in allow.stdout:
            ok("guard-run dry-run allow works")
        else:
            fail("guard-run dry-run allow failed")
            print(allow.stdout + allow.stderr)

        blocked = subprocess.run(
            [sys.executable, "scripts/guard-run.py", "--", "sudo rm -rf /"],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if blocked.returncode == 10 and "decision=block" in (blocked.stdout + blocked.stderr):
            ok("guard-run blocks destructive command")
        else:
            fail("guard-run block behavior failed")
            print(blocked.stdout + blocked.stderr)

        log_file = tmp_log_dir / "commands.log"
        if log_file.exists() and log_file.stat().st_size > 0:
            ok("guard-run writes command log")
            for line in log_file.read_text(encoding="utf-8").splitlines():
                json.loads(line)
            ok("guard-run command log is JSON Lines")
        else:
            fail("guard-run did not write command log")

    finally:
        subprocess.run(["rm", "-rf", str(tmp_log_dir)], check=False)


def check_logs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.chmod(0o700)

    mode = stat.S_IMODE(LOG_DIR.stat().st_mode)
    if mode == 0o700:
        ok(f"log directory permissions are 700: {LOG_DIR}")
    else:
        warn(f"log directory permissions are {oct(mode)}, expected 0o700")

    command_log = LOG_DIR / "commands.log"
    if command_log.exists():
        mode = stat.S_IMODE(command_log.stat().st_mode)
        if mode == 0o600:
            ok("commands.log permissions are 600")
        else:
            warn(f"commands.log permissions are {oct(mode)}, expected 0o600")

        lines = [line for line in command_log.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        if lines:
            try:
                json.loads(lines[-1])
                ok("latest commands.log line is valid JSON")
            except json.JSONDecodeError:
                warn("latest commands.log line is not JSON; this may be from older pre-JSON test entries")
    else:
        warn("commands.log does not exist yet; it will be created on first guarded command")


def check_path_guard_text() -> None:
    text = (ROOT / "omp-sbx").read_text(encoding="utf-8", errors="replace")

    required = [
        "Workspace path guard",
        "OMP_GUARD_ALLOWED_ROOT",
        "refusing to launch outside AgentWork",
        "GitHub auth forwarding is intentionally disabled by default",
        ".omp-guard-state",
    ]

    for needle in required:
        if needle in text:
            ok(f"omp-sbx contains: {needle}")
        else:
            fail(f"omp-sbx missing expected guard text: {needle}")


def check_git_state() -> None:
    result = run(["git", "status", "--short"])
    if result.returncode != 0:
        warn("could not read git status")
        return

    allowed_dirty = {
        "README.md",
        "omp-guard",
        "scripts/doctor.py",
        "scripts/status.py",
        "scripts/menu.py",
        "scripts/security.py",
        "scripts/test-menu.py",
        "scripts/test-security-docs.py",
        "docs/security-models.md",
    }
    dirty_lines = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        rel = line[3:].strip()
        if rel in allowed_dirty or rel == "docs/" or rel.startswith("docs/"):
            continue
        dirty_lines.append(line)

    if dirty_lines:
        warn("git working tree has unrelated changes")
        print(result.stdout)
    else:
        ok("git working tree has no unrelated changes")


def check_seatbelt() -> None:
    """Report Tier 0 (light-mode Seatbelt) availability and enforcement.

    On non-macOS this is a WARN (Tier 0 unavailable), never a hard FAIL — the
    guard still works via account separation + path guard, just without the
    kernel sandbox.
    """
    if sys.platform != "darwin":
        warn("Seatbelt Tier 0 unavailable: not macOS (light mode runs unsandboxed)")
        return

    result = run([sys.executable, "scripts/seatbelt.py", "--capability"])
    if result.returncode == 0:
        ok(f"Seatbelt capability: {result.stdout.strip()}")
    else:
        warn(f"Seatbelt not capable: {result.stdout.strip() or result.stderr.strip()}")
        return

    # Deep enforcement prover. This is the durability signal after OS updates.
    selftest = run([sys.executable, "scripts/seatbelt-selftest.py"])
    if selftest.returncode == 0:
        ok("Seatbelt enforcement self-test passed (Tier 0 boundary holds)")
    else:
        fail("Seatbelt enforcement self-test FAILED — Tier 0 not enforcing on this build")
        tail = "\n".join(selftest.stdout.strip().splitlines()[-6:])
        print(tail)


def main() -> int:
    print("omp-guard doctor")
    print(f"repo: {ROOT}")
    print()

    check_user()
    check_location()
    check_required_files()
    check_policy()
    check_classifier()
    check_guard_runner()
    check_logs()
    check_path_guard_text()
    check_seatbelt()
    check_git_state()

    print()
    print(f"warnings: {len(warnings)}")
    print(f"errors: {len(errors)}")

    if errors:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
