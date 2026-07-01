#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path


BACKENDS = ("light", "native-mac", "docker-sbx")

BACKEND_DESCRIPTIONS = {
    "light": "Daily mode. On macOS: Tier 0 Seatbelt sandbox + egress proxy (workspace-confined, allowlisted network) at ~0 RAM. Not VM-grade isolation.",
    "docker-sbx": "High-isolation Docker/sbx mode. Use for risky repos, package installs, shell-heavy or untrusted work. High RAM.",
    "native-mac": "Planned/experimental macOS-native sandbox mode. Do not treat as ready until doctor says available.",
}


def default_paths() -> tuple[Path, Path, Path]:
    home = Path.home()
    agentwork = Path(os.environ.get("OMP_GUARD_ALLOWED_ROOT", str(home / "AgentWork"))).resolve()
    state = Path(os.environ.get("OMP_GUARD_STATE", str(agentwork / ".omp-guard-state"))).resolve()
    config = Path(os.environ.get("OMP_GUARD_CONFIG", str(state / "guard-config.json"))).resolve()
    return agentwork, state, config


def make_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def read_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text(encoding="utf-8"))


def write_config(config_path: Path, data: dict) -> None:
    make_private_dir(config_path.parent)
    config_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    config_path.chmod(0o600)


def choose_backend() -> str:
    print("Choose omp-guard isolation backend:")
    print(f"  1) light       {BACKEND_DESCRIPTIONS['light']}")
    print(f"  2) native-mac  {BACKEND_DESCRIPTIONS['native-mac']}")
    print(f"  3) docker-sbx  {BACKEND_DESCRIPTIONS['docker-sbx']}")
    print()
    choice = input("Select 1, 2, or 3 [1]: ").strip() or "1"

    if choice == "1":
        return "light"
    if choice == "2":
        return "native-mac"
    if choice == "3":
        return "docker-sbx"

    raise SystemExit(f"invalid choice: {choice}")


def show_config(config_path: Path) -> int:
    if not config_path.exists():
        print(f"No omp-guard config found at: {config_path}")
        print("Run: ./omp-guard setup --backend light")
        return 1

    print(config_path.read_text(encoding="utf-8").rstrip())
    return 0


def detect_personal_home() -> str | None:
    """Detect the personal user's home directory from the macOS console user."""
    try:
        import subprocess
        console_user = subprocess.run(
            ["stat", "-f", "%Su", "/dev/console"],
            capture_output=True, text=True, check=True
        ).stdout.strip()
        if console_user and console_user != os.environ.get("USER", ""):
            return f"/Users/{console_user}"
    except (subprocess.CalledProcessError, OSError):
        pass
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure omp-guard launch backend.")
    parser.add_argument("--backend", choices=BACKENDS, help="Isolation backend to use.")
    parser.add_argument("--show", action="store_true", help="Show current config and exit.")
    parser.add_argument("--config-path", action="store_true", help="Print config path and exit.")
    parser.add_argument("--personal-home", help="Path to the personal (non-work) user's home directory.")
    args = parser.parse_args()

    agentwork, state, config_path = default_paths()

    if args.config_path:
        print(config_path)
        return 0

    if args.show:
        return show_config(config_path)

    backend = args.backend or choose_backend()
    personal_home = args.personal_home or detect_personal_home() or os.environ.get("OMP_GUARD_PERSONAL_HOME") or ""

    make_private_dir(agentwork)
    make_private_dir(state)

    data = {
        "backend": backend,
        "allowed_root": str(agentwork),
        "state_dir": str(state),
        "state_home": str(state / "home"),
        "log_dir": str(Path(os.environ.get("OMP_GUARD_LOG_DIR", str(agentwork / ".omp-guard-logs"))).resolve()),
        "personal_home": personal_home,
        "docker_sbx_sandbox": "omp-omp-guard",
        "native_mac_status": "planned",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": BACKEND_DESCRIPTIONS,
    }

    write_config(config_path, data)

    mode = stat.S_IMODE(config_path.stat().st_mode)
    if mode != 0o600:
        raise SystemExit(f"config permissions are {oct(mode)}, expected 0o600")

    print(f"Configured omp-guard backend: {backend}")
    print(f"Config: {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
