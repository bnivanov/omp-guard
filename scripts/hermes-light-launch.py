#!/usr/bin/env python3
from __future__ import annotations

import argparse
import atexit
import getpass
import os
import select
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hermes_common as hc  # noqa: E402
import seatbelt  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent


def die(message: str, code: int = 2) -> None:
    print(f"hermes-light: {message}", file=sys.stderr)
    raise SystemExit(code)


def make_private_file_append(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    path.chmod(0o600)


def write_launch_logs(global_log: Path, profile_log: Path, line: str) -> None:
    """Write central and profile-local launch evidence.

    The central guard log is useful for cross-profile audit. The profile-local
    copy remains a fallback when an old central log has bad ownership or
    permissions from earlier manual debugging.
    """
    failures: list[str] = []
    wrote = False
    for label, path in (("central", global_log), ("profile", profile_log)):
        try:
            make_private_file_append(path, line)
            wrote = True
        except OSError as exc:
            failures.append(f"{label} launch log unavailable at {path}: {exc}")

    if not wrote:
        die("; ".join(failures), 5)
    for failure in failures:
        print(f"hermes-light: WARN: {failure}", file=sys.stderr)


def seatbelt_policy() -> str:
    policy = os.environ.get("HERMES_GUARD_SEATBELT", "").strip().lower()
    if policy in {"auto", "require", "off"}:
        return policy
    policy = os.environ.get("OMP_GUARD_SEATBELT", "").strip().lower()
    if policy in {"auto", "require", "off"}:
        return policy
    return "require"


def start_egress_proxy(policy_file: Path, log_dir: Path) -> tuple[subprocess.Popen | None, int | None]:
    proxy_script = ROOT / "scripts" / "egress-proxy.py"
    decisions_log = log_dir / "hermes-egress.log"
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
                str(policy_file),
                "--log",
                str(decisions_log),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None, None

    assert proc.stdout is not None
    deadline = time.time() + 10
    port_line = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            return None, None
        ready, _, _ = select.select([proc.stdout], [], [], 0.25)
        if ready:
            port_line = proc.stdout.readline().strip()
            if port_line:
                break
    if not port_line.isdigit():
        proc.terminate()
        return None, None
    return proc, int(port_line)


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Launch Hermes with omp-guard's macOS account, workspace, Seatbelt, and egress controls."
    )
    parser.add_argument("--profile", required=True, help="Hermes profile name, e.g. chief-of-staff or researcher.")
    parser.add_argument("--gateway", action="store_true", help="Run `hermes gateway` for the selected profile.")
    parser.add_argument(
        "--profile-local-home",
        action="store_true",
        help="Advanced/debug mode: use the old profile-local HERMES_HOME instead of canonical ~/.hermes.",
    )
    parser.add_argument(
        "--allow-estate-cwd",
        action="store_true",
        help="Allow launching from AgentWork outside projects. Intended for controlled gateway runs only.",
    )
    args, rest = parser.parse_known_args(argv)
    if rest and rest[0] == "--":
        rest = rest[1:]
    return args, rest


def selected_xcode_developer_dir() -> Path | None:
    tool = Path("/usr/bin/xcode-select")
    if not tool.exists():
        return None
    try:
        result = subprocess.run(
            [str(tool), "-p"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.strip()
    if not raw:
        return None
    path = Path(raw).resolve()
    if path.exists():
        return path
    return None


def hermes_runtime_read_paths(hermes_bin: str, actual_home: Path) -> list[Path]:
    """Return narrow read-only runtime paths needed to execute Hermes itself.

    In canonical mode ~/.hermes is writable as state, but the runtime code path
    is still listed separately in launch evidence. In profile-local debug mode
    this function prevents accidentally allowing all of global ~/.hermes when
    only the installed code/venv subtree is needed.
    """
    paths: list[Path] = []

    hermes_bin_path = Path(hermes_bin).resolve()
    paths.append(hermes_bin_path.parent)

    explicit = os.environ.get("HERMES_GUARD_RUNTIME_DIR", "").strip()
    candidates = [Path(explicit).expanduser()] if explicit else []
    candidates.extend(
        [
            actual_home / ".hermes" / "hermes-agent",
            actual_home / ".local" / "share" / "uv" / "python",
        ]
    )
    xcode_dir = selected_xcode_developer_dir()
    if xcode_dir is not None:
        candidates.append(xcode_dir)

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except FileNotFoundError:
            continue
        if not resolved.exists():
            continue
        if resolved == (actual_home / ".hermes").resolve():
            die("refusing to allow the whole global ~/.hermes directory as Hermes runtime read path")
        paths.append(resolved)

    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key not in seen:
            deduped.append(path)
            seen.add(key)
    return deduped


def maybe_dump_seatbelt_profile(profile_text: str) -> None:
    dump_path = os.environ.get("HERMES_GUARD_DUMP_SEATBELT_PROFILE", "").strip()
    if not dump_path:
        return
    path = Path(dump_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile_text, encoding="utf-8")
    path.chmod(0o600)


def configure_canonical_env(env: dict[str, str], actual_home: Path) -> tuple[Path, Path, str]:
    canonical_home, _ = hc.validate_canonical_hermes_home(actual_home)
    tmp_dir = hc.ensure_guard_tmp_dir()
    env["HERMES_HOME"] = str(canonical_home)
    env["HOME"] = str(actual_home)
    for key in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        env.pop(key, None)
    env["TMPDIR"] = str(tmp_dir)
    return canonical_home, tmp_dir, "canonical-hermes-home"


def configure_profile_local_env(env: dict[str, str], paths: dict[str, Path]) -> tuple[Path, Path, str]:
    env["HERMES_HOME"] = str(paths["root"])
    env["HOME"] = str(paths["home"])
    env["XDG_CONFIG_HOME"] = str(paths["xdg_config"])
    env["XDG_CACHE_HOME"] = str(paths["xdg_cache"])
    env["XDG_DATA_HOME"] = str(paths["xdg_data"])
    env["XDG_STATE_HOME"] = str(paths["state"])
    env["TMPDIR"] = str(paths["tmp"])
    return paths["root"], paths["tmp"], "profile-local-hermes-home"


def main() -> int:
    args, hermes_args = parse_args(sys.argv[1:])
    profile = args.profile
    try:
        hc.validate_profile_name(profile)
    except ValueError as exc:
        die(str(exc))

    actual_home = Path.home().resolve()
    user = getpass.getuser()
    work_user = os.environ.get("OMP_GUARD_WORK_USER", "")
    if work_user and user != work_user and os.environ.get("OMP_GUARD_ALLOW_OTHER_USER") != "1":
        die(
            f"refusing to run as {user}; expected {work_user} "
            "(set OMP_GUARD_WORK_USER to change, or OMP_GUARD_ALLOW_OTHER_USER=1 to skip this check)"
        )

    workdir = Path.cwd().resolve()
    require_project_cwd = not args.allow_estate_cwd and not args.gateway
    try:
        hc.assert_safe_workdir(workdir, require_project_cwd=require_project_cwd)
        paths = hc.ensure_profile_dirs(profile)
        guard_log_dir = hc.ensure_guard_log_dir()
    except (OSError, PermissionError, RuntimeError, ValueError) as exc:
        die(str(exc))

    hermes_bin = hc.find_hermes_bin()
    if not hermes_bin:
        die("Hermes CLI not found on PATH. Install/configure Hermes, or set HERMES_GUARD_HERMES_BIN for testing.", 127)

    policy_file = hc.policy_for_profile(profile)
    if not policy_file.exists():
        die(f"Hermes policy file missing: {policy_file}")

    env, scrubbed = hc.scrubbed_env(os.environ)
    profile_local = args.profile_local_home or os.environ.get("HERMES_GUARD_PROFILE_LOCAL_HOME") == "1"
    try:
        if profile_local:
            hermes_home, tmp_dir, home_mode = configure_profile_local_env(env, paths)
            runtime_write_paths = hc.profile_local_runtime_paths(profile)
        else:
            hermes_home, tmp_dir, home_mode = configure_canonical_env(env, actual_home)
            runtime_write_paths = hc.canonical_runtime_write_paths(hermes_home, tmp_dir, guard_log_dir)
    except (OSError, PermissionError, RuntimeError, ValueError, FileNotFoundError) as exc:
        die(str(exc))

    env["HERMES_GUARD_PROFILE"] = profile
    env["HERMES_GUARD_POLICY_EFFECTIVE"] = str(policy_file)

    policy = seatbelt_policy()
    capable, cap_detail = seatbelt.capability()
    enforce = False
    if policy == "off":
        cap_detail = "disabled by HERMES_GUARD_SEATBELT=off/OMP_GUARD_SEATBELT=off"
    elif policy == "require":
        if not capable:
            die(f"Seatbelt is required but unavailable: {cap_detail}", 3)
        enforce = True
    else:
        enforce = capable
        if not capable:
            print(f"hermes-light: Seatbelt unavailable, running UNSANDBOXED ({cap_detail})", file=sys.stderr)

    proxy_proc = None
    proxy_port = None
    if enforce:
        proxy_proc, proxy_port = start_egress_proxy(policy_file, guard_log_dir)
        if proxy_proc is None:
            if os.environ.get("HERMES_GUARD_REQUIRE_PROXY", "1") != "0":
                die("egress proxy failed to start while Seatbelt is enforced; refusing to launch", 4)
            print("hermes-light: egress proxy failed; network fully denied under sandbox", file=sys.stderr)
        else:
            proxy_url = f"http://127.0.0.1:{proxy_port}"
            for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
                env[key] = proxy_url
            env["NODE_USE_ENV_PROXY"] = "1"
            env["NO_PROXY"] = "127.0.0.1,localhost"
            env["no_proxy"] = "127.0.0.1,localhost"

    hermes_argv = [hermes_bin, "gateway", *hermes_args] if args.gateway else [hermes_bin, *hermes_args]
    runtime_read_paths = hermes_runtime_read_paths(hermes_bin, actual_home)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    xdg_state = env.get("XDG_STATE_HOME", "(unset)")
    launch_line = "\t".join(
        [
            f"ts={ts}",
            f"user={user}",
            f"profile={profile}",
            f"home_mode={home_mode}",
            f"workdir={workdir}",
            f"home={env.get('HOME')}",
            f"hermes_home={hermes_home}",
            f"xdg_state_home={xdg_state}",
            f"tmpdir={tmp_dir}",
            f"policy={policy_file}",
            f"tokens_scrubbed={','.join(scrubbed) if scrubbed else 'none'}",
            f"seatbelt={'on' if enforce else 'off'}",
            f"seatbelt_detail={cap_detail}",
            f"egress_proxy={'127.0.0.1:' + str(proxy_port) if proxy_port else 'none'}",
            f"runtime_read_paths={','.join(str(path) for path in runtime_read_paths)}",
            f"runtime_write_paths={','.join(str(path) for path in runtime_write_paths)}",
            f"mode={home_mode} {'gateway' if args.gateway else 'hermes'} {' '.join(hermes_args) if hermes_args else '(interactive)'}",
        ]
    )
    write_launch_logs(
        guard_log_dir / "hermes-launch.log",
        paths["logs"] / "hermes-launch.log",
        launch_line,
    )

    if not enforce:
        os.execvpe(hermes_bin, hermes_argv, env)
        return 127

    sb_profile = seatbelt.build_profile(
        workspace=workdir,
        state_dir=hermes_home,
        tmp_dir=tmp_dir,
        proxy_port=proxy_port,
        extra_read_paths=runtime_read_paths,
        extra_write_paths=runtime_write_paths,
    )
    maybe_dump_seatbelt_profile(sb_profile)
    wrapped = seatbelt.wrap_command(profile=sb_profile, argv=hermes_argv)

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
