#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


COMMANDS = {
    "omp-guard": ROOT / "omp-guard",
    "omp-light": ROOT / "omp-light",
    "omp-sbx": ROOT / "omp-sbx",
}


def default_agentwork() -> Path:
    return Path(os.environ.get("OMP_GUARD_ALLOWED_ROOT", str(Path.home() / "AgentWork"))).resolve()


def default_bin_dir() -> Path:
    return Path(os.environ.get("OMP_GUARD_BIN_DIR", str(default_agentwork() / "bin"))).resolve()


def make_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def write_shim(name: str, target: Path, bin_dir: Path) -> Path:
    if not target.exists():
        raise SystemExit(f"missing target for {name}: {target}")

    shim = bin_dir / name
    content = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"exec {shlex.quote(str(target))} \"$@\"\n"
    )

    shim.write_text(content, encoding="utf-8")
    shim.chmod(0o700)
    return shim


def check_shim(name: str, target: Path, bin_dir: Path) -> bool:
    shim = bin_dir / name

    if not shim.exists():
        print(f"FAIL: missing shim: {shim}")
        return False

    if not os.access(shim, os.X_OK):
        print(f"FAIL: shim is not executable: {shim}")
        return False

    text = shim.read_text(encoding="utf-8", errors="replace")
    if str(target) not in text:
        print(f"FAIL: shim does not point to expected target: {shim} -> {target}")
        return False

    print(f"OK: {name} -> {target}")
    return True


def install(bin_dir: Path) -> int:
    make_private_dir(bin_dir)

    for name, target in COMMANDS.items():
        shim = write_shim(name, target, bin_dir)
        print(f"installed: {shim} -> {target}")

    print()
    print("Add this to your shell PATH if it is not already present:")
    print(f'export PATH="{bin_dir}:$PATH"')
    return 0


def check(bin_dir: Path) -> int:
    ok = True

    for name, target in COMMANDS.items():
        ok = check_shim(name, target, bin_dir) and ok

    return 0 if ok else 1


def print_path_line(bin_dir: Path) -> int:
    print(f'export PATH="{bin_dir}:$PATH"')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install omp-guard command shims into AgentWork/bin.")
    parser.add_argument("--bin-dir", default=str(default_bin_dir()), help="Directory to install shims into.")
    parser.add_argument("--check", action="store_true", help="Check installed shims instead of writing them.")
    parser.add_argument("--print-path-line", action="store_true", help="Print the shell PATH line and exit.")
    args = parser.parse_args()

    bin_dir = Path(args.bin_dir).expanduser().resolve()

    if args.print_path_line:
        return print_path_line(bin_dir)

    if args.check:
        return check(bin_dir)

    return install(bin_dir)


if __name__ == "__main__":
    raise SystemExit(main())
