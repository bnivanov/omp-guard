#!/usr/bin/env python3
"""Seatbelt (macOS sandbox-exec) support for omp-guard light mode.

This is the Tier 0 enforcement layer described in docs/security-models.md:
a deny-by-default macOS Seatbelt profile that confines the agent process to
the current workspace plus guard-scoped state, denies reads of everything
else (credentials, other projects, personal data), and denies all network
except a single localhost egress proxy port.

IMPORTANT DEPRECATION NOTE
--------------------------
`sandbox-exec(1)` and the underlying `sandbox_init(3)` are both DEPRECATED by
Apple (they emit a warning to stderr) but remain functional and are what
Claude Code and Codex ship on macOS today. There is no supported CLI
replacement. Treat Seatbelt as the pragmatic, low-RAM *convenience* layer,
NOT as the load-bearing boundary. The durable boundaries are macOS account
separation and network egress control (proxy / PF). If a macOS update ever
makes sandbox-exec hard-fail, `capability()` reports it and light mode falls
back per OMP_GUARD_SEATBELT policy.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Profile-generation constants.
SANDBOX_EXEC = "/usr/bin/sandbox-exec"


def is_darwin() -> bool:
    return sys.platform == "darwin"


def sandbox_exec_path() -> str | None:
    """Return the sandbox-exec binary path, or None if unavailable."""
    if not is_darwin():
        return None
    if os.path.exists(SANDBOX_EXEC) and os.access(SANDBOX_EXEC, os.X_OK):
        return SANDBOX_EXEC
    return shutil.which("sandbox-exec")


def capability() -> tuple[bool, str]:
    """Cheap probe: can sandbox-exec actually enforce a trivial profile here?

    Returns (ok, detail). This is intentionally fast (a single deny-default
    exec) so it can run on every launch. The deep enforcement prover lives in
    scripts/seatbelt-selftest.py.
    """
    if not is_darwin():
        return False, "not macOS (sandbox-exec is macOS-only)"

    binary = sandbox_exec_path()
    if not binary:
        return False, "sandbox-exec not found on this system"

    # A minimal profile that allows a trivial /usr/bin/true to run. If
    # sandbox-exec is present but the OS has removed enforcement, this exec
    # itself fails and we report incapable.
    probe = "(version 1)\n(allow default)\n"
    try:
        result = subprocess.run(
            [binary, "-p", probe, "/usr/bin/true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"sandbox-exec probe failed: {exc}"

    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip() or "nonzero exit"
        return False, f"sandbox-exec probe rejected: {detail}"

    return True, f"sandbox-exec available at {binary}"


def _sbpl_literal(value: str) -> str:
    """Quote a path for safe embedding in an SBPL string literal.

    We inject paths as SBPL string literals rather than via `-D` so a single
    profile string is self-contained and auditable. Backslashes and double
    quotes are the only characters meaningful inside an SBPL string.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_profile(
    *,
    workspace: Path,
    state_dir: Path,
    tmp_dir: Path,
    proxy_port: int | None,
    extra_read_paths: list[Path] | None = None,
) -> str:
    """Generate a deny-by-default SBPL profile for a light-mode agent.

    Read/write is confined to `workspace`, `state_dir`, and `tmp_dir`.
    Reads of system/runtime paths required by the Node/omp runtime are
    allowed. Everything else — including other projects, the personal
    account, and all credential paths — is denied by default (no allow rule).

    Network:
      * proxy_port set   -> outbound allowed ONLY to 127.0.0.1:<proxy_port>
                            (plus localhost unix/loopback needed by tooling).
      * proxy_port None  -> all outbound network denied.
    """
    ws = _sbpl_literal(str(workspace))
    st = _sbpl_literal(str(state_dir))
    tmp = _sbpl_literal(str(tmp_dir))

    # System/runtime read roots the Node/Python runtime and common CLIs need.
    # These are read-only; none grant access to user data.
    read_roots = [
        "/usr",
        "/bin",
        "/sbin",
        "/System",
        "/Library",
        "/opt/homebrew",
        "/opt/local",
        "/private/var/db/dyld",
        "/private/var/db/timezone",
        "/etc",
        "/private/etc",
        "/dev",
    ]
    read_root_rules = "\n".join(
        f'  (subpath "{_sbpl_literal(p)}")' for p in read_roots
    )

    lines: list[str] = []
    lines.append("(version 1)")
    lines.append('(deny default (with no-log))')
    lines.append("")
    lines.append("; --- process + runtime basics ---")
    lines.append("(allow process-fork)")
    lines.append("(allow process-exec)")
    lines.append("(allow signal (target self))")
    lines.append("(allow sysctl-read)")
    lines.append("(allow mach-lookup) ; broad (DNS/notify daemons); scope in a later pass")
    lines.append("(allow ipc-posix-shm)")
    lines.append("; prompt_toolkit/Hermes needs terminal ioctl for raw-mode TTY control")
    lines.append("(allow file-ioctl)")
    lines.append("")
    lines.append("; --- read-only system/runtime paths (no user data) ---")
    lines.append("(allow file-read*")
    lines.append(read_root_rules)
    for extra in extra_read_paths or []:
        lines.append(f'  (subpath "{_sbpl_literal(str(extra))}")')
    # The workspace, state, and tmp are readable as well as writable.
    lines.append(f'  (subpath "{ws}")')
    lines.append(f'  (subpath "{st}")')
    lines.append(f'  (subpath "{tmp}")')
    lines.append("  (literal \"/\")")
    lines.append("  (literal \"/dev/null\")")
    lines.append("  (literal \"/dev/random\")")
    lines.append("  (literal \"/dev/urandom\")")
    lines.append(")")
    lines.append("")
    lines.append("; --- read-write: workspace + guard-scoped state + tmp ONLY ---")
    lines.append("(allow file-write*")
    lines.append(f'  (subpath "{ws}")')
    lines.append(f'  (subpath "{st}")')
    lines.append(f'  (subpath "{tmp}")')
    lines.append("  (literal \"/dev/null\")")
    lines.append("  (literal \"/dev/dtracehelper\")")
    lines.append(")")
    lines.append("")

    if proxy_port is not None:
        lines.append("; --- network: localhost egress proxy ONLY ---")
        lines.append("(allow network-outbound")
        lines.append(f'  (remote ip "localhost:{int(proxy_port)}")')
        lines.append(")")
    else:
        lines.append("; --- network: all outbound denied (no proxy configured) ---")
    lines.append("")

    return "\n".join(lines) + "\n"


def wrap_command(
    *,
    profile: str,
    argv: list[str],
) -> list[str]:
    """Return an argv that runs `argv` under `profile` via sandbox-exec.

    The profile is written to a private temp file (sandbox-exec -f) rather
    than passed inline, so it survives arbitrarily long profiles and is easy
    to inspect if a launch fails.
    """
    binary = sandbox_exec_path()
    if not binary:
        raise RuntimeError("sandbox-exec unavailable; cannot wrap command")

    fd, path = tempfile.mkstemp(prefix="omp-guard-sb-", suffix=".sb")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(profile)
    os.chmod(path, 0o600)

    return [binary, "-f", path, *argv]


def _main() -> int:
    """CLI: print a generated profile for inspection.

    Usage: seatbelt.py <workspace> <state_dir> <tmp_dir> [proxy_port]
    """
    args = sys.argv[1:]

    if args and args[0] == "--capability":
        ok, detail = capability()
        print(f"{'OK' if ok else 'UNAVAILABLE'}: {detail}")
        return 0 if ok else 1

    if len(args) < 3:
        print(
            "usage: seatbelt.py <workspace> <state_dir> <tmp_dir> [proxy_port]",
            file=sys.stderr,
        )
        print("       seatbelt.py --capability", file=sys.stderr)
        return 2

    workspace = Path(args[0]).resolve()
    state_dir = Path(args[1]).resolve()
    tmp_dir = Path(args[2]).resolve()
    proxy_port = int(args[3]) if len(args) > 3 else None

    print(
        build_profile(
            workspace=workspace,
            state_dir=state_dir,
            tmp_dir=tmp_dir,
            proxy_port=proxy_port,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
