#!/usr/bin/env python3
"""Prove that Seatbelt enforcement actually holds on THIS macOS build.

Run this after every macOS update. If Apple ever neuters sandbox-exec, this
flips from PASS to FAIL and you know Tier 0 is no longer enforcing — time to
fall back (proxy + PF + account separation, or escalate risky work to a VM).

Each check runs a real command under the generated profile and asserts the
boundary. Exit 0 only if every enforcement check passes.
"""
from __future__ import annotations

import http.server
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seatbelt  # noqa: E402


class Result:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        tag = "PASS" if ok else "FAIL"
        line = f"{tag}: {name}"
        if detail:
            line += f"  ({detail})"
        print(line)
        if ok:
            self.passed += 1
        else:
            self.failed += 1


def run_under(profile_path: Path, argv: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/usr/bin/sandbox-exec", "-f", str(profile_path), *argv],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def main() -> int:
    ok, detail = seatbelt.capability()
    if not ok:
        print(f"FAIL: sandbox-exec not capable on this system ({detail})")
        print("\nSeatbelt Tier 0 is NOT available. Do not rely on it as a boundary.")
        return 1
    print(f"OK: {detail}\n")

    res = Result()

    with tempfile.TemporaryDirectory(dir="/private/tmp", prefix="omp-sbselftest-") as td:
        base = Path(td).resolve()
        ws = base / "ws"
        state = base / "state"
        tmp = base / "tmp"
        for d in (ws, state, tmp):
            d.mkdir(parents=True, exist_ok=True)

        inside = ws / "inside.txt"
        inside.write_text("inside-ok\n", encoding="utf-8")
        outside = base / "outside-secret.txt"
        outside.write_text("SECRET\n", encoding="utf-8")

        # Profile with NO network (proxy_port=None) for the deny-all-network check,
        # plus a profile WITH a bogus proxy port to confirm only that port is reachable.
        profile_nonet = base / "nonet.sb"
        profile_nonet.write_text(
            seatbelt.build_profile(workspace=ws, state_dir=state, tmp_dir=tmp, proxy_port=None),
            encoding="utf-8",
        )
        # Pick a free loopback port and stand up a listener so we can prove the
        # proxy port IS reachable (a broken `remote ip` rule would otherwise
        # pass the deny checks while silently killing all model traffic).
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            proxy_port = probe.getsockname()[1]

        listener = socketserver.TCPServer(("127.0.0.1", proxy_port), http.server.BaseHTTPRequestHandler)
        threading.Thread(target=listener.serve_forever, daemon=True).start()

        profile_proxy = base / "proxy.sb"
        profile_proxy.write_text(
            seatbelt.build_profile(workspace=ws, state_dir=state, tmp_dir=tmp, proxy_port=proxy_port),
            encoding="utf-8",
        )

        # 1. Read inside workspace -> allowed
        r = run_under(profile_nonet, ["/bin/cat", str(inside)])
        res.check("read inside workspace allowed", r.returncode == 0 and b"inside-ok" in r.stdout,
                  r.stderr.decode("utf-8", "replace").strip())

        # 2. Read outside workspace -> denied
        r = run_under(profile_nonet, ["/bin/cat", str(outside)])
        res.check("read outside workspace denied", r.returncode != 0 and b"SECRET" not in r.stdout)

        # 3. Read $HOME/.ssh -> denied (create a decoy so absence isn't the reason)
        home = Path.home()
        r = run_under(profile_nonet, ["/bin/ls", str(home / ".ssh")])
        res.check("read ~/.ssh denied", r.returncode != 0)

        # 4. Write inside workspace -> allowed
        r = run_under(profile_nonet, ["/usr/bin/touch", str(ws / "written")])
        res.check("write inside workspace allowed", r.returncode == 0 and (ws / "written").exists())

        # 5. Write outside workspace -> denied
        target = base / "should-not-exist"
        r = run_under(profile_nonet, ["/usr/bin/touch", str(target)])
        res.check("write outside workspace denied", r.returncode != 0 and not target.exists())

        # 6. Network with no proxy -> external connection denied
        r = run_under(profile_nonet, ["/usr/bin/curl", "-s", "-m", "5", "https://example.com",
                                      "-o", "/dev/null", "-w", "%{http_code}"])
        code = r.stdout.decode("utf-8", "replace").strip()
        res.check("external network denied (no-proxy profile)", code in ("000", ""),
                  f"http_code={code!r}")

        # 7. Proxy profile: external direct still denied ...
        r = run_under(profile_proxy, ["/usr/bin/curl", "-s", "-m", "5", "https://example.com",
                                      "-o", "/dev/null", "-w", "%{http_code}"])
        code = r.stdout.decode("utf-8", "replace").strip()
        res.check("external network denied (proxy profile, non-proxy host)", code in ("000", ""),
                  f"http_code={code!r}")

        # 8. ... but the proxy port itself IS reachable (positive proof).
        r = run_under(profile_proxy, ["/usr/bin/curl", "-s", "-m", "5",
                                      f"http://127.0.0.1:{proxy_port}",
                                      "-o", "/dev/null", "-w", "%{http_code}"])
        code = r.stdout.decode("utf-8", "replace").strip()
        res.check("loopback proxy port reachable", code not in ("000", ""),
                  f"http_code={code!r} (expected a real HTTP status from listener)")

        listener.shutdown()

    print(f"\n{res.passed} passed, {res.failed} failed")
    if res.failed:
        print("\nENFORCEMENT INCOMPLETE — do not trust Seatbelt Tier 0 on this build.")
        return 1
    print("\nSeatbelt Tier 0 enforcement verified on this macOS build.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
