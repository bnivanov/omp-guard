#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import status


ROOT = Path(__file__).resolve().parent.parent
PROJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")

MENU_OPTIONS = [
    ("1", "Start OMP here with light mode", "Daily mode. On macOS: Tier 0 Seatbelt sandbox + egress proxy (workspace-confined, allowlisted network), ~0 RAM. Uses dedicated work account + AgentWork path guard + guard-scoped state."),
    ("2", "Start OMP here with docker-sbx mode", "High-isolation mode. Uses Docker/sbx for stronger containment, but costs much more RAM."),
    ("3", "Choose/create project", None),
    ("4", "Show guard status", "Shows current folder, backend, state paths, shims, Docker/sbx status, and warnings."),
    ("5", "Change default backend", "Changes which backend future guard launches should prefer: light, docker-sbx, or native-mac."),
    ("6", "Run doctor", "Runs health checks for policy, permissions, logs, launchers, shims, and expected guard files."),
    ("7", "Show recent launch logs", "Shows recent guarded launches from the private AgentWork log directory."),
    ("8", "Check/install shims", "Ensures omp-guard, omp-light, and omp-sbx work from any AgentWork project."),
    ("9", "Explain security models", "Explains light, docker-sbx, native-mac, AgentWork, guard state, shims, logs, and GitHub auth."),
    ("10", "Model smoke test", "Confirms the guarded OMP model profile can respond from the current setup."),
    ("q", "Quit", "Exit without launching OMP."),
]


def dim(text: str) -> str:
    if sys.stdout.isatty() and "NO_COLOR" not in os.environ:
        return f"\033[2m{text}\033[0m"
    return text


def paths() -> tuple[Path, Path, Path, Path]:
    agentwork, projects, _state, _config, log_dir, bin_dir = status.paths()
    return agentwork, projects, log_dir, bin_dir


def is_project_dir(path: Path, projects: Path) -> bool:
    return status.project_name(path, projects) is not None


def prompt(message: str) -> str:
    return input(message).strip()


def pause() -> None:
    if sys.stdin.isatty():
        input("\nPress Enter to continue...")


def run_python_script(name: str, args: list[str] | None = None) -> int:
    args = args or []
    return subprocess.call([sys.executable, str(ROOT / "scripts" / name), *args], cwd=ROOT)


def run_executable(name: str, args: list[str] | None = None) -> int:
    args = args or []
    return subprocess.call([str(ROOT / name), *args])


def warn_for_cwd(cwd: Path, agentwork: Path, projects: Path) -> None:
    if cwd == agentwork:
        print("WARN: current directory is the AgentWork estate root, not a project.")
        print(f"      Prefer: {projects}/<project>")
    elif not status.is_under(cwd, agentwork):
        print(f"WARN: current directory is outside AgentWork: {cwd}")
        print(f"      Prefer: {projects}/<project>")
    elif not is_project_dir(cwd, projects):
        print(f"WARN: current directory is inside AgentWork but not under projects/: {cwd}")
        print(f"      Prefer: {projects}/<project>")


def list_projects(projects: Path) -> list[Path]:
    if not projects.exists():
        return []
    return sorted([path for path in projects.iterdir() if path.is_dir() and not path.name.startswith(".")], key=lambda p: p.name.lower())


def create_project(projects: Path) -> Path | None:
    name = prompt("Project name: ")
    if not name:
        print("No project name entered.")
        return None
    if not PROJECT_NAME_RE.fullmatch(name):
        print("Invalid project name. Use letters, numbers, dot, underscore, or dash; start with a letter or number.")
        return None

    projects.mkdir(parents=True, exist_ok=True)
    project = (projects / name).resolve()
    if not status.is_under(project, projects):
        print("Refusing to create a project outside AgentWork/projects.")
        return None

    project.mkdir(parents=True, exist_ok=True)
    print(f"Project ready: {project}")
    return project


def choose_project() -> Path | None:
    _agentwork, projects, _log_dir, _bin_dir = paths()
    projects.mkdir(parents=True, exist_ok=True)
    choices = list_projects(projects)

    print("\nProjects")
    for index, project in enumerate(choices, start=1):
        print(f"  {index}) {project.name}")
    print("  n) Create new project")
    print("  q) Back")

    choice = prompt("Select project: ").lower()
    if choice in {"q", "quit", ""}:
        return None
    if choice in {"n", "new", "c", "create"}:
        return create_project(projects)
    if choice.isdigit():
        index = int(choice)
        if 1 <= index <= len(choices):
            return choices[index - 1]

    print("Invalid project selection.")
    return None


def launch_directory() -> Path | None:
    agentwork, projects, _log_dir, _bin_dir = paths()
    cwd = Path.cwd().resolve()
    if is_project_dir(cwd, projects):
        return cwd

    warn_for_cwd(cwd, agentwork, projects)
    print("Choose or create a project before launching OMP.")
    return choose_project()


def exec_launcher(name: str) -> int:
    project = launch_directory()
    if project is None:
        return 1
    os.chdir(project)
    launcher = ROOT / name
    print(f"Launching {name} from {project}")
    os.execv(str(launcher), [str(launcher)])
    return 127


def show_recent_logs() -> int:
    _agentwork, _projects, log_dir, _bin_dir = paths()
    log_file = log_dir / "launch.log"
    if not log_file.exists():
        print(f"No launch log found at: {log_file}")
        return 1

    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"Recent launch log entries: {log_file}")
    for line in lines[-20:]:
        print(line)
    return 0


def change_backend() -> int:
    return run_python_script("setup.py")


def check_install_shims() -> int:
    _agentwork, _projects, _log_dir, bin_dir = paths()
    result = run_python_script("install-shims.py", ["--bin-dir", str(bin_dir), "--check"])
    if result == 0:
        return 0

    answer = prompt("Install/update shims now? [y/N]: ").lower()
    if answer in {"y", "yes"}:
        return run_python_script("install-shims.py", ["--bin-dir", str(bin_dir)])
    return result


def model_smoke_test() -> int:
    print("Running light-mode omp version smoke test...")
    print("This checks whether the configured omp CLI can start; it does not enter an interactive session.")
    return run_executable("omp-light", ["--version"])


def print_menu() -> None:
    agentwork, projects, _log_dir, _bin_dir = paths()
    cwd = Path.cwd().resolve()
    print("\nomp-guard launcher")
    print(f"cwd: {cwd}")
    warn_for_cwd(cwd, agentwork, projects)
    print()
    for key, label, description in MENU_OPTIONS:
        if description is None:
            description = f"Pick or create a workspace under {projects}."
        print(f"  {key}) {label}")
        print(f"   {dim(f'({description})')}")


def interactive_menu() -> int:
    while True:
        print_menu()
        choice = prompt("Select: ").lower()
        if choice == "1":
            return exec_launcher("omp-light")
        if choice == "2":
            return exec_launcher("omp-sbx")
        if choice == "3":
            project = choose_project()
            if project is not None:
                os.chdir(project)
                print(f"Current directory: {project}")
            pause()
        elif choice == "4":
            status.print_status()
            pause()
        elif choice == "5":
            change_backend()
            pause()
        elif choice == "6":
            run_python_script("doctor.py")
            pause()
        elif choice == "7":
            show_recent_logs()
            pause()
        elif choice == "8":
            check_install_shims()
            pause()
        elif choice == "9":
            run_python_script("security.py")
            pause()
        elif choice == "10":
            model_smoke_test()
            pause()
        elif choice in {"q", "quit", "0"}:
            return 0
        else:
            print("Invalid selection.")
            pause()


def main() -> int:
    parser = argparse.ArgumentParser(description="Plain-text omp-guard launcher menu.")
    parser.add_argument("--status-only", action="store_true", help="Print guard status and exit without prompting.")
    args = parser.parse_args()

    if args.status_only or os.environ.get("OMP_GUARD_MENU_STATUS_ONLY") == "1":
        return status.print_status()

    return interactive_menu()


if __name__ == "__main__":
    raise SystemExit(main())
