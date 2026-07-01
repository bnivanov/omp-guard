#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp-light-test"
FAKE_OMP = TMP / "fake-omp.sh"
LOG_DIR = TMP / "logs"
STATE_DIR = TMP / "state"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def main() -> int:
    subprocess.run(["rm", "-rf", str(TMP)], check=False)
    TMP.mkdir(parents=True, exist_ok=True)

    FAKE_OMP.write_text(
        """#!/usr/bin/env bash
echo "FAKE_OMP_ARGS=$*"
echo "FAKE_HOME=$HOME"
echo "FAKE_PI_CONFIG_DIR=$PI_CONFIG_DIR"
echo "FAKE_OMP_PROFILE=$OMP_PROFILE"
""",
        encoding="utf-8",
    )
    FAKE_OMP.chmod(0o755)

    env = os.environ.copy()
    env["OMP_GUARD_OMP_BIN"] = str(FAKE_OMP)
    env["OMP_GUARD_LOG_DIR"] = str(LOG_DIR)
    env["OMP_GUARD_STATE"] = str(STATE_DIR)
    env["OMP_GUARD_ALLOWED_ROOT"] = str(ROOT.parent)
    env.pop("GITHUB_TOKEN", None)
    env.pop("GH_TOKEN", None)
    # This test exercises the env/passthrough path, not Seatbelt enforcement
    # (that has its own test). Pin it off so it is deterministic off-macOS too.
    env["OMP_GUARD_SEATBELT"] = "off"

    result = subprocess.run(
        ["./omp-light", "--no-tools", "--help"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    output = result.stdout + result.stderr

    require(result.returncode == 0, output)
    require("FAKE_OMP_ARGS=--no-tools --help" in output, "omp-light did not pass args")
    require(f"FAKE_HOME={STATE_DIR / 'home'}" in output, "omp-light did not set guard-scoped HOME")
    require("FAKE_PI_CONFIG_DIR=.omp" in output, "omp-light did not set PI_CONFIG_DIR")
    require("FAKE_OMP_PROFILE=omp-guard" in output, "omp-light did not set OMP_PROFILE")

    log_file = LOG_DIR / "launch.log"
    require(log_file.exists(), "launch.log was not created")
    log_text = log_file.read_text(encoding="utf-8")
    require("backend=light" in log_text, "light launch was not logged")
    require("github_tokens_scrubbed=none" in log_text, "unexpected GitHub token scrub state")

    subprocess.run(["rm", "-rf", str(TMP)], check=False)

    print("All light launcher tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
