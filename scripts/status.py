#!/usr/bin/env python3
from __future__ import annotations

import getpass
import json
import os
import subprocess
from pathlib import Path


SHIM_NAMES = ("omp-guard", "omp-light", "omp-sbx")
DEFAULT_AGENTWORK = Path.home() / "AgentWork"


def env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


def paths() -> tuple[Path, Path, Path, Path, Path]:
    agentwork = env_path("OMP_GUARD_ALLOWED_ROOT", DEFAULT_AGENTWORK)
    projects = agentwork / "projects"
    state = env_path("OMP_GUARD_STATE", agentwork / ".omp-guard-state")
    config = env_path("OMP_GUARD_CONFIG", state / "guard-config.json")
    log_dir = env_path("OMP_GUARD_LOG_DIR", agentwork / ".omp-guard-logs")
    bin_dir = env_path("OMP_GUARD_BIN_DIR", agentwork / "bin")
    return agentwork, projects, state, config, log_dir, bin_dir


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def project_name(cwd: Path, projects: Path) -> str | None:
    try:
        rel = cwd.resolve().relative_to(projects.resolve())
    except ValueError:
        return None

    if not rel.parts:
        return None

    name = rel.parts[0]
    if name.startswith("."):
        return None
    return name


def read_backend(config_path: Path) -> str:
    if not config_path.exists():
        return "not configured"

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"unreadable ({exc})"

    backend = data.get("backend")
    return str(backend) if backend else "missing"


def shim_status(bin_dir: Path) -> str:
    states: list[str] = []
    for name in SHIM_NAMES:
        path = bin_dir / name
        if path.exists() and os.access(path, os.X_OK):
            states.append(f"{name}=yes")
        elif path.exists():
            states.append(f"{name}=not-executable")
        else:
            states.append(f"{name}=missing")
    return ", ".join(states)


def heavy_process_status() -> str:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,comm=,args="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"

    if result.returncode != 0:
        return "unknown"

    matches: list[str] = []
    for line in result.stdout.splitlines():
        lower = line.lower()
        if "docker" in lower or " sbx" in lower or lower.endswith(" sbx") or "/sbx" in lower:
            if "status.py" not in lower and "menu.py" not in lower:
                matches.append(line.strip())

    if not matches:
        return "no"

    sample = "; ".join(matches[:3])
    suffix = "" if len(matches) <= 3 else f"; +{len(matches) - 3} more"
    return f"yes ({sample}{suffix})"


def print_status() -> int:
    agentwork, projects, state, config_path, log_dir, bin_dir = paths()
    cwd = Path.cwd().resolve()
    project = project_name(cwd, projects)

    print("omp-guard status")
    print(f"user: {getpass.getuser()}")
    print(f"cwd: {cwd}")
    print(f"inside AgentWork: {'yes' if is_under(cwd, agentwork) else 'no'} ({agentwork})")
    print(f"project under AgentWork/projects: {project if project else 'no'} ({projects})")
    print(f"configured backend: {read_backend(config_path)}")
    print(f"guard state path: {state}")
    print(f"log path: {log_dir / 'launch.log'}")
    print(f"shims in AgentWork/bin: {shim_status(bin_dir)}")
    print(f"heavy Docker/sbx processes: {heavy_process_status()}")

    if cwd == agentwork:
        print("WARN: cwd is the AgentWork estate root, not a project.")
    if is_under(cwd, state):
        print("WARN: cwd is inside .omp-guard-state; do not run project work there.")
    if not is_under(cwd, agentwork):
        print("WARN: cwd is outside AgentWork; launch from an AgentWork project.")

    return 0


def main() -> int:
    return print_status()


if __name__ == "__main__":
    raise SystemExit(main())
