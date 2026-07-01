#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / ".tmp-menu-test"
AGENTWORK = TMP / "AgentWork"
STATE_DIR = AGENTWORK / ".omp-guard-state"
LOG_DIR = AGENTWORK / ".omp-guard-logs"
CONFIG = STATE_DIR / "guard-config.json"
BIN_DIR = AGENTWORK / "bin"
FAKE_OMP = BIN_DIR / "omp"
HELP_EXIT_CODE = 2
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
MENU_OPTION_RE = re.compile(r"^  (?P<key>(?:[1-9]|10|q))\) (?P<label>.+)$")
MENU_EXPLANATION_RE = re.compile(r"^ {3}\((?P<text>.+)\)$")
EXPECTED_MENU_OPTIONS = {
    "1": ("Start OMP here with light mode", "Daily mode. On macOS: Tier 0 Seatbelt sandbox + egress proxy (workspace-confined, allowlisted network), ~0 RAM. Uses dedicated work account + AgentWork path guard + guard-scoped state."),
    "2": ("Start OMP here with docker-sbx mode", "High-isolation mode. Uses Docker/sbx for stronger containment, but costs much more RAM."),
    "3": ("Choose/create project", f"Pick or create a workspace under {AGENTWORK / 'projects'}."),
    "4": ("Show guard status", "Shows current folder, backend, state paths, shims, Docker/sbx status, and warnings."),
    "5": ("Change default backend", "Changes which backend future guard launches should prefer: light, docker-sbx, or native-mac."),
    "6": ("Run doctor", "Runs health checks for policy, permissions, logs, launchers, shims, and expected guard files."),
    "7": ("Show recent launch logs", "Shows recent guarded launches from the private AgentWork log directory."),
    "8": ("Check/install shims", "Ensures omp-guard, omp-light, and omp-sbx work from any AgentWork project."),
    "9": ("Explain security models", "Explains light, docker-sbx, native-mac, AgentWork, guard state, shims, logs, and GitHub auth."),
    "10": ("Model smoke test", "Confirms the guarded OMP model profile can respond from the current setup."),
    "q": ("Quit", "Exit without launching OMP."),
}


class CommandTimedOut(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def guarded_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["OMP_GUARD_ALLOWED_ROOT"] = str(AGENTWORK)
    env["OMP_GUARD_STATE"] = str(STATE_DIR)
    env["OMP_GUARD_LOG_DIR"] = str(LOG_DIR)
    env["OMP_GUARD_CONFIG"] = str(CONFIG)
    env["OMP_GUARD_BIN_DIR"] = str(BIN_DIR)
    env["OMP_GUARD_ALLOW_OTHER_USER"] = "1"
    env["OMP_GUARD_OMP_BIN"] = str(FAKE_OMP)
    env.pop("GITHUB_TOKEN", None)
    env.pop("GH_TOKEN", None)
    env.pop("NO_COLOR", None)
    if extra:
        env.update(extra)
    return env


def run_guard(
    args: list[str],
    *,
    cwd: Path = ROOT,
    env_extra: dict[str, str] | None = None,
    stdin: str = "",
    timeout: float = 5,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [str(ROOT / "omp-guard"), *args],
            cwd=cwd,
            env=guarded_env(env_extra),
            input=stdin,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandTimedOut(f"omp-guard {' '.join(args)} timed out") from exc


def output_of(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def setup_temp_agentwork() -> None:
    shutil.rmtree(TMP, ignore_errors=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    CONFIG.write_text(
        json.dumps(
            {
                "allowed_root": str(AGENTWORK),
                "backend": "light",
                "docker_sbx_sandbox": "omp-omp-guard",
                "log_dir": str(LOG_DIR),
                "native_mac_status": "planned",
                "state_dir": str(STATE_DIR),
                "state_home": str(STATE_DIR / "home"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    CONFIG.chmod(0o600)

    FAKE_OMP.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'FAIL: test-menu.py must not launch real or fake omp' >&2\n"
        "exit 99\n",
        encoding="utf-8",
    )
    FAKE_OMP.chmod(0o755)


def require_status_output(output: str, context: str) -> None:
    required_labels = [
        "omp-guard status",
        "inside AgentWork:",
        "project under AgentWork/projects:",
        "configured backend:",
        "guard state path:",
        "log path:",
        "shims in AgentWork/bin:",
    ]

    for label in required_labels:
        require(label in output, f"{context} missing status label {label!r}:\n{output}")

    require(str(AGENTWORK) in output, f"{context} missing temp AgentWork path:\n{output}")
    require(str(STATE_DIR) in output, f"{context} missing temp state path:\n{output}")
    require(str(LOG_DIR) in output, f"{context} missing temp log path:\n{output}")
    require("configured backend: light" in output, f"{context} missing configured backend value:\n{output}")


def assert_status_command() -> None:
    result = run_guard(["status"])
    output = output_of(result)
    require(result.returncode == 0, output)
    require_status_output(output, "omp-guard status")


def assert_menu_status_only() -> None:
    result = run_guard(["menu", "--status-only"])
    output = output_of(result)
    require(result.returncode == 0, output)
    require_status_output(output, "omp-guard menu --status-only")


def assert_interactive_menu_text() -> None:
    result = run_guard(["menu"], stdin="q\n")
    output = output_of(result)
    require(result.returncode == 0, output)
    require(
        ANSI_ESCAPE_RE.search(output) is None,
        f"interactive menu emitted ANSI escapes despite stdout being non-TTY:\n{output!r}",
    )

    lines = output.splitlines()
    seen_options: list[str] = []
    for index, line in enumerate(lines):
        match = MENU_OPTION_RE.match(line)
        if match is None:
            continue

        key = match.group("key")
        label = match.group("label")
        require(key in EXPECTED_MENU_OPTIONS, f"unexpected interactive menu option {key!r} in line:\n{line}")

        expected_label, expected_explanation = EXPECTED_MENU_OPTIONS[key]
        require(
            label == expected_label,
            f"interactive menu option {key}) label changed; expected {expected_label!r}, got {label!r}",
        )
        require(
            index + 1 < len(lines),
            f"interactive menu option {key}) {label!r} has no following explanation line:\n{output}",
        )

        explanation_line = lines[index + 1]
        explanation_match = MENU_EXPLANATION_RE.match(explanation_line)
        require(
            explanation_match is not None,
            "interactive menu option "
            f"{key}) {label!r} must be immediately followed by exactly three spaces and a parenthesized explanation; "
            f"got {explanation_line!r}",
        )
        require(
            explanation_match.group("text") == expected_explanation,
            f"interactive menu option {key}) explanation changed; expected {expected_explanation!r}, got {explanation_match.group('text')!r}",
        )

        seen_options.append(key)

    require(
        seen_options == list(EXPECTED_MENU_OPTIONS),
        f"interactive menu options changed; expected {list(EXPECTED_MENU_OPTIONS)}, got {seen_options}:\n{output}",
    )



def assert_help(args: list[str]) -> None:
    result = run_guard(args)
    output = output_of(result)
    require(result.returncode == HELP_EXIT_CODE, output)
    require("usage:" in output.lower(), f"omp-guard {' '.join(args)} did not print usage:\n{output}")
    require("./omp-guard" in output, f"omp-guard {' '.join(args)} usage omitted dispatcher name:\n{output}")


def assert_agentwork_root_warning() -> None:
    result = run_guard(["status"], cwd=AGENTWORK)
    output = output_of(result)
    require(result.returncode == 0, output)
    require_status_output(output, "omp-guard status from AgentWork root")
    require(
        "WARN: cwd is the AgentWork estate root, not a project." in output,
        f"status did not warn that cwd is exactly the simulated AgentWork root:\n{output}",
    )


def expr_is_empty_argv_check(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return isinstance(node.operand, ast.Name) and node.operand.id == "argv"

    if isinstance(node, ast.Compare):
        left = node.left
        comparator = node.comparators[0] if node.comparators else None
        has_eq = any(isinstance(op, ast.Eq) for op in node.ops)
        if not has_eq:
            return False

        def is_len_argv(expr: ast.AST) -> bool:
            return (
                isinstance(expr, ast.Call)
                and isinstance(expr.func, ast.Name)
                and expr.func.id == "len"
                and len(expr.args) == 1
                and isinstance(expr.args[0], ast.Name)
                and expr.args[0].id == "argv"
            )

        def is_zero(expr: ast.AST | None) -> bool:
            return isinstance(expr, ast.Constant) and expr.value == 0

        return (is_len_argv(left) and is_zero(comparator)) or (is_zero(left) and comparator is not None and is_len_argv(comparator))

    if isinstance(node, ast.BoolOp):
        return any(expr_is_empty_argv_check(value) for value in node.values)

    return False


def node_calls_menu_script(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if not isinstance(child.func, ast.Name) or child.func.id != "run_script":
            continue
        if child.args and isinstance(child.args[0], ast.Constant) and child.args[0].value == "menu.py":
            return True
    return False


def dispatcher_source_has_no_arg_menu_dispatch() -> bool:
    tree = ast.parse((ROOT / "omp-guard").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "main":
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.If) and expr_is_empty_argv_check(child.test):
                return any(node_calls_menu_script(body_node) for body_node in child.body)
    return False


def assert_no_arg_dispatch() -> None:
    try:
        result = run_guard(
            [],
            env_extra={"OMP_GUARD_MENU_STATUS_ONLY": "1"},
            stdin="",
            timeout=2,
        )
    except CommandTimedOut:
        result = None

    if result is not None:
        output = output_of(result)
        if result.returncode == 0:
            require_status_output(output, "omp-guard with OMP_GUARD_MENU_STATUS_ONLY=1")
            return

    require(
        dispatcher_source_has_no_arg_menu_dispatch(),
        "omp-guard with no args is not observably wired to menu, and dispatcher source lacks a no-arg menu.py dispatch",
    )


def main() -> int:
    try:
        setup_temp_agentwork()
        assert_status_command()
        assert_menu_status_only()
        assert_help(["help"])
        assert_interactive_menu_text()
        assert_help(["--help"])
        assert_no_arg_dispatch()
        assert_agentwork_root_warning()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)

    print("All menu/status tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
