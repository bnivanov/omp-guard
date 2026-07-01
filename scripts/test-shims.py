#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp-shims-test"
BIN = TMP / "bin"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def main() -> int:
    subprocess.run(["rm", "-rf", str(TMP)], check=False)

    install = subprocess.run(
        ["scripts/install-shims.py", "--bin-dir", str(BIN)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(install.returncode == 0, install.stdout + install.stderr)

    check = subprocess.run(
        ["scripts/install-shims.py", "--bin-dir", str(BIN), "--check"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    require(check.returncode == 0, check.stdout + check.stderr)

    for name in ["omp-guard", "omp-light", "omp-sbx"]:
        path = BIN / name
        require(path.exists(), f"missing shim: {name}")
        require(os.access(path, os.X_OK), f"shim not executable: {name}")
        text = path.read_text(encoding="utf-8")
        require(str(ROOT / name) in text, f"shim target incorrect: {name}")

    help_result = subprocess.run(
        [str(BIN / "omp-guard"), "help"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output = help_result.stdout + help_result.stderr
    require(help_result.returncode == 2, output)
    require("./omp-light" in output, "omp-guard help did not mention omp-light")
    require("./omp-sbx" in output, "omp-guard help did not mention omp-sbx")

    subprocess.run(["rm", "-rf", str(TMP)], check=False)

    print("All shim tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
