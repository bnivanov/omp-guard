#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = ROOT / "docs" / "security-models.md"
SECURITY_SCRIPT = ROOT / "scripts" / "security.py"
MENU_SCRIPT = ROOT / "scripts" / "menu.py"
TMP = ROOT / ".tmp-security-docs-test"
AGENTWORK = TMP / "AgentWork"
STATE_DIR = AGENTWORK / ".omp-guard-state"
LOG_DIR = AGENTWORK / ".omp-guard-logs"
CONFIG = STATE_DIR / "guard-config.json"
BIN_DIR = AGENTWORK / "bin"


DOC_PHRASES = [
    "light",
    "docker-sbx",
    "native-mac",
    "AgentWork",
    "guard-scoped HOME",
    "GitHub auth",
    "shims",
    "doctor",
    "command policy",
    "Seatbelt",
    "egress proxy",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def test_env() -> dict[str, str]:
    env = os.environ.copy()
    env["OMP_GUARD_ALLOWED_ROOT"] = str(AGENTWORK)
    env["OMP_GUARD_STATE"] = str(STATE_DIR)
    env["OMP_GUARD_LOG_DIR"] = str(LOG_DIR)
    env["OMP_GUARD_CONFIG"] = str(CONFIG)
    env["OMP_GUARD_BIN_DIR"] = str(BIN_DIR)
    env["OMP_GUARD_ALLOW_OTHER_USER"] = "1"
    env.pop("GITHUB_TOKEN", None)
    env.pop("GH_TOKEN", None)
    return env


def run_command(args: list[str], *, stdin: str = "", timeout: float = 5) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        env=test_env(),
        input=stdin,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def output_of(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def setup_tmp_agentwork() -> None:
    shutil.rmtree(TMP, ignore_errors=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def assert_security_doc() -> None:
    require(DOC_PATH.exists(), f"missing security models doc: {DOC_PATH.relative_to(ROOT)}")
    text = DOC_PATH.read_text(encoding="utf-8")
    folded = text.casefold()

    for phrase in DOC_PHRASES:
        require(
            phrase.casefold() in folded,
            f"security models doc does not mention {phrase!r}",
        )

    require(
        "stronger isolation" in folded and "docker-sbx" in folded,
        "security models doc should describe docker-sbx as the stronger isolation option",
    )
    require(
        "light" in folded
        and ("account/path/state" in folded or "guard-scoped" in folded)
        and ("not vm-grade isolation" in folded or "not a vm sandbox" in folded or "not full shell sandboxing" in folded),
        "security models doc should make clear that light mode is account/path/state guard rails, not VM-grade isolation",
    )


def assert_security_command() -> None:
    result = run_command(["./omp-guard", "security"])
    output = output_of(result)

    require(result.returncode == 0, output)
    require("security" in output.casefold(), f"security command did not print a security summary:\n{output}")
    require(
        "docs/security-models.md" in output or str(DOC_PATH) in output,
        f"security command did not print the security doc path:\n{output}",
    )


def assert_security_script() -> None:
    require(SECURITY_SCRIPT.exists(), f"missing script: {SECURITY_SCRIPT.relative_to(ROOT)}")

    result = run_command([sys.executable, str(SECURITY_SCRIPT)])
    output = output_of(result)

    require(result.returncode == 0, output)
    require("security" in output.casefold(), f"security.py did not print a security summary:\n{output}")
    require(
        "docs/security-models.md" in output or str(DOC_PATH) in output,
        f"security.py did not print the security doc path:\n{output}",
    )


def assert_menu_exposes_security_models() -> None:
    require(MENU_SCRIPT.exists(), f"missing script: {MENU_SCRIPT.relative_to(ROOT)}")

    result = run_command([sys.executable, str(MENU_SCRIPT)], stdin="q\n")
    output = output_of(result)

    require(result.returncode == 0, output)
    require(
        "Explain security models" in output,
        f"menu did not expose the security models option:\n{output}",
    )


def main() -> int:
    try:
        setup_tmp_agentwork()
        assert_security_doc()
        assert_security_script()
        assert_security_command()
        assert_menu_exposes_security_models()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)

    print("All security docs tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
