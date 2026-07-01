#!/usr/bin/env python3
from __future__ import annotations

import atexit
import getpass
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seatbelt  # noqa: E402  (local module, scripts/seatbelt.py)


ROOT = Path(__file__).resolve().parent.parent


def die(message: str, code: int = 2) -> None:
    print(f"omp-light: {message}", file=sys.stderr)
    raise SystemExit(code)


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def make_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def log_launch(log_dir: Path, line: str) -> None:
    make_private_dir(log_dir)
    log_file = log_dir / "launch.log"
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    log_file.chmod(0o600)


def seatbelt_policy() -> str:
    """Return the effective Seatbelt policy: 'auto' | 'require' | 'off'.

    OMP_GUARD_SEATBELT wins; legacy OMP_GUARD_DISABLE_SEATBELT=1 maps to 'off'.
    """
    policy = os.environ.get("OMP_GUARD_SEATBELT", "").strip().lower()
    if policy in {"auto", "require", "off"}:
        return policy
    if os.environ.get("OMP_GUARD_DISABLE_SEATBELT") == "1":
        return "off"
    return "auto"


def start_egress_proxy(state_dir: Path, log_dir: Path) -> tuple[subprocess.Popen | None, int | None]:
    """Start the domain-allowlist egress proxy on an ephemeral loopback port.

    Returns (process, port). On failure returns (None, None) — the caller
    decides whether that is fatal (network then fully denied under Seatbelt).
    """
    proxy_script = Path(__file__).resolve().parent / "egress-proxy.py"
    policy_file = os.environ.get("OMP_GUARD_POLICY", str(ROOT / "policies" / "default.yml"))
    decisions_log = log_dir / "egress.log"
    try:
        proc = subprocess.Popen(
            [
                sys.executable,
                str(proxy_script),
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--print-port",
                "--policy",
                policy_file,
                "--log",
                str(decisions_log),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None, None

    # First stdout line is the bound port (from --print-port). Use select so a
    # child that starts but never prints cannot hang us past the deadline.
    assert proc.stdout is not None
    import select

    deadline = time.time() + 10
    port_line = ""
    fd = proc.stdout
    while time.time() < deadline:
        if proc.poll() is not None:
            return None, None
        ready, _, _ = select.select([fd], [], [], 0.25)
        if ready:
            port_line = fd.readline().strip()
            if port_line:
                break
    if not port_line.isdigit():
        proc.terminate()
        return None, None
    return proc, int(port_line)


def main() -> int:
    argv = sys.argv[1:]
    actual_home = Path.home()
    user = getpass.getuser()

    work_user = os.environ.get("OMP_GUARD_WORK_USER", "")
    if work_user and user != work_user and os.environ.get("OMP_GUARD_ALLOW_OTHER_USER") != "1":
        die(f"refusing to run as {user}; expected {work_user} (set OMP_GUARD_WORK_USER to change, or OMP_GUARD_ALLOW_OTHER_USER=1 to skip this check)")

    allowed_root = Path(os.environ.get("OMP_GUARD_ALLOWED_ROOT", str(actual_home / "AgentWork"))).resolve()
    state_dir = Path(os.environ.get("OMP_GUARD_STATE", str(allowed_root / ".omp-guard-state"))).resolve()
    state_home = state_dir / "home"
    log_dir = Path(os.environ.get("OMP_GUARD_LOG_DIR", str(allowed_root / ".omp-guard-logs"))).resolve()
    workdir = Path.cwd().resolve()

    if not is_under(workdir, allowed_root):
        die(f"refusing to launch outside AgentWork: {workdir} (allowed root: {allowed_root})")

    personal_home = os.environ.get("OMP_GUARD_PERSONAL_HOME")
    if not personal_home:
        die("OMP_GUARD_PERSONAL_HOME is not set — refusing to launch without personal home protection")
    forbidden = [
        Path(personal_home),
        Path("/Users/Shared"),
        actual_home / "Desktop",
        actual_home / "Documents",
        actual_home / "Downloads",
        actual_home / "Library" / "Mobile Documents",
    ]

    for path in forbidden:
        if path.exists() and is_under(workdir, path):
            die(f"refusing to launch under forbidden path: {path}")

    for path in [
        state_dir,
        state_home,
        state_home / ".omp",
        state_dir / "tmp",
        state_dir / "xdg-config",
        state_dir / "xdg-cache",
        state_dir / "xdg-data",
    ]:
        make_private_dir(path)

    omp_bin = os.environ.get("OMP_GUARD_OMP_BIN") or shutil.which("omp")
    if not omp_bin:
        work_user = os.environ.get("OMP_GUARD_WORK_USER", "agentlab")
        die(f"omp CLI not found on PATH. Install/configure omp for {work_user}, or set OMP_GUARD_OMP_BIN for testing.", 127)

    env = os.environ.copy()

    # Keep model/provider env vars if the user explicitly set them, but do not
    # forward GitHub write credentials into daily light mode by accident.
    scrubbed = []
    for key in [
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "GITHUB_PAT",
        "COPILOT_GITHUB_TOKEN",
    ]:
        if key in env:
            scrubbed.append(key)
            env.pop(key, None)

    env["HOME"] = str(state_home)
    env["PI_CONFIG_DIR"] = ".omp"
    env["OMP_PROFILE"] = env.get("OMP_PROFILE", "omp-guard")
    env["PI_CODING_AGENT_DIR"] = str(state_home / ".omp" / "agent")
    env["XDG_CONFIG_HOME"] = str(state_dir / "xdg-config")
    env["XDG_CACHE_HOME"] = str(state_dir / "xdg-cache")
    env["XDG_DATA_HOME"] = str(state_dir / "xdg-data")
    env["TMPDIR"] = str(state_dir / "tmp")

    # ── Tier 0 enforcement decision ───────────────────────────────────────
    policy = seatbelt_policy()
    capable, cap_detail = seatbelt.capability()

    enforce = False
    if policy == "off":
        cap_detail = "disabled by OMP_GUARD_SEATBELT=off"
    elif policy == "require":
        if not capable:
            die(
                f"OMP_GUARD_SEATBELT=require but Seatbelt is unavailable: {cap_detail}",
                3,
            )
        enforce = True
    else:  # auto
        enforce = capable
        if not capable:
            print(f"omp-light: Seatbelt unavailable, running UNSANDBOXED ({cap_detail})", file=sys.stderr)

    proxy_proc = None
    proxy_port = None
    if enforce:
        proxy_proc, proxy_port = start_egress_proxy(state_dir, log_dir)
        if proxy_proc is None:
            print("omp-light: egress proxy failed to start; network fully denied under sandbox", file=sys.stderr)
        else:
            # Route tool/runtime HTTP(S) through the loopback proxy. Node 20+
            # honors env proxy only with NODE_USE_ENV_PROXY=1.
            proxy_url = f"http://127.0.0.1:{proxy_port}"
            for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
                env[key] = proxy_url
            env["NODE_USE_ENV_PROXY"] = "1"
            env["NO_PROXY"] = "127.0.0.1,localhost"
            env["no_proxy"] = "127.0.0.1,localhost"

    command_text = " ".join(argv) if argv else "(interactive)"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_launch(
        log_dir,
        "\t".join(
            [
                f"ts={ts}",
                f"user={user}",
                f"workdir={workdir}",
                f"allowed_root={allowed_root}",
                "backend=light",
                f"state_home={state_home}",
                f"github_tokens_scrubbed={','.join(scrubbed) if scrubbed else 'none'}",
                f"seatbelt={'on' if enforce else 'off'}",
                f"seatbelt_detail={cap_detail}",
                f"egress_proxy={'127.0.0.1:' + str(proxy_port) if proxy_port else 'none'}",
                f"mode=omp {command_text}",
            ]
        ),
    )

    if not enforce:
        os.execvpe(omp_bin, [omp_bin, *argv], env)
        return 127

    # Enforced path: run omp under sandbox-exec so we can tear down the proxy
    # on exit. omp binary dir must be readable inside the sandbox.
    omp_dir = Path(omp_bin).resolve().parent
    profile = seatbelt.build_profile(
        workspace=workdir,
        state_dir=state_dir,
        tmp_dir=state_dir / "tmp",
        proxy_port=proxy_port,
        extra_read_paths=[omp_dir],
    )
    wrapped = seatbelt.wrap_command(profile=profile, argv=[omp_bin, *argv])

    def _cleanup() -> None:
        if proxy_proc is not None and proxy_proc.poll() is None:
            proxy_proc.terminate()
            try:
                proxy_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proxy_proc.kill()

    atexit.register(_cleanup)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: sys.exit(130))

    try:
        result = subprocess.run(wrapped, env=env)
        return result.returncode
    finally:
        _cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
