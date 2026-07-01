#!/usr/bin/env python3
"""Domain-allowlist egress proxy for omp-guard light mode (Tier 0).

This is the network allowlist for light mode. It is NOT an independent
boundary on its own: `HTTPS_PROXY` is only honored voluntarily, so the proxy
is load-bearing *because* the Seatbelt profile denies every other outbound
path and forces traffic through localhost:<proxy_port>. Without Seatbelt (or a
future PF layer pinning egress), an unsandboxed process can ignore the proxy
and connect directly. The proxy forwards a connection ONLY if the target host
matches the allowlist; everything else is refused and logged.

Design notes
------------
* Stdlib only (no deps), threaded, one instance shared by an agent team.
* Handles HTTPS via CONNECT (host from the CONNECT line) and plain HTTP via
  the request-line/Host header. TLS is tunneled, not inspected — we see the
  destination host, not the payload (same posture as Claude Code's proxy).
* Allowlist entries: "host" or "host:port"; leading "*." is a wildcard for
  one-or-more leading labels (e.g. "*.openrouter.ai" matches "a.openrouter.ai"
  and "a.b.openrouter.ai" but not "openrouter.ai"). A bare host allows any
  port; "host:443" restricts to that port.
* Binds 127.0.0.1 only. Never exposed off-host.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import select
import socket
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

BUFSIZE = 65536
CONNECT_TIMEOUT = 15
IDLE_TIMEOUT = 300


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Allowlist:
    def __init__(self, entries: list[str]) -> None:
        self.exact: set[str] = set()          # host with no port constraint
        self.exact_port: set[tuple[str, int]] = set()
        self.wild: list[str] = []             # "*.example.com" (any port)
        self.wild_port: list[tuple[str, int]] = []
        for raw in entries:
            entry = raw.strip()
            if not entry:
                continue
            host, _, port = entry.partition(":")
            host = host.lower().rstrip(".")
            port_num = int(port) if port and port != "*" else None
            is_wild = host.startswith("*.")
            if is_wild and port_num is not None:
                self.wild_port.append((host, port_num))
            elif is_wild:
                self.wild.append(host)
            elif port_num is not None:
                self.exact_port.add((host, port_num))
            else:
                self.exact.add(host)

    def permits(self, host: str, port: int) -> bool:
        host = host.lower().rstrip(".")
        if host in self.exact:
            return True
        if (host, port) in self.exact_port:
            return True
        for pattern in self.wild:
            if fnmatch.fnmatch(host, pattern):
                return True
        for pattern, p in self.wild_port:
            if p == port and fnmatch.fnmatch(host, pattern):
                return True
        return False


def load_allowlist(policy_path: Path) -> list[str]:
    """Parse network.allowedDomains from the guard policy (dependency-free)."""
    if not policy_path.exists():
        return []
    entries: list[str] = []
    in_network = False
    in_allowed = False
    for line in policy_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0 and stripped.endswith(":"):
            in_network = stripped == "network:"
            in_allowed = False
            continue
        if not in_network:
            continue
        if indent == 2 and stripped.endswith(":"):
            in_allowed = stripped == "allowedDomains:"
            continue
        if in_allowed and stripped.startswith("- "):
            value = stripped[2:].strip()
            if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
                value = value[1:-1]
            if value:
                entries.append(value)
    return entries


class ProxyLog:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._lock = threading.Lock()
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Best-effort tighten; parent may be a pre-existing system dir
            # (e.g. /private/tmp) we do not own — never fatal.
            try:
                path.parent.chmod(0o700)
            except OSError:
                pass

    def record(self, *, decision: str, host: str, port: int, detail: str = "") -> None:
        event = {
            "ts": now(),
            "component": "egress-proxy",
            "decision": decision,
            "host": host,
            "port": port,
        }
        if detail:
            event["detail"] = detail
        line = json.dumps(event, sort_keys=True)
        if self.path is None:
            print(line, file=sys.stderr, flush=True)
            return
        with self._lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            self.path.chmod(0o600)


def _pipe(a: socket.socket, b: socket.socket) -> None:
    """Bidirectional relay until either side closes."""
    conns = [a, b]
    try:
        while True:
            readable, _, errored = select.select(conns, [], conns, IDLE_TIMEOUT)
            if errored or not readable:
                break
            for src in readable:
                dst = b if src is a else a
                data = src.recv(BUFSIZE)
                if not data:
                    return
                dst.sendall(data)
    except OSError:
        return


class Handler(threading.Thread):
    def __init__(self, client: socket.socket, allow: Allowlist, log: ProxyLog) -> None:
        super().__init__(daemon=True)
        self.client = client
        self.allow = allow
        self.log = log

    def run(self) -> None:
        try:
            self._handle()
        except OSError:
            pass
        finally:
            try:
                self.client.close()
            except OSError:
                pass

    def _read_headers(self) -> bytes:
        data = b""
        self.client.settimeout(CONNECT_TIMEOUT)
        while b"\r\n\r\n" not in data:
            chunk = self.client.recv(BUFSIZE)
            if not chunk:
                break
            data += chunk
            if len(data) > 65536:
                break
        return data

    def _refuse(self, host: str, port: int, code: str, reason: str) -> None:
        self.log.record(decision="deny", host=host, port=port, detail=reason)
        body = f"omp-guard egress proxy: {reason}\n".encode("utf-8")
        self.client.sendall(
            b"HTTP/1.1 " + code.encode() + b"\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n" + body
        )

    def _connect_upstream(self, host: str, port: int) -> socket.socket | None:
        try:
            upstream = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
            upstream.settimeout(None)
            return upstream
        except OSError as exc:
            self.log.record(decision="error", host=host, port=port, detail=str(exc))
            self.client.sendall(
                b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n"
            )
            return None

    def _handle(self) -> None:
        head = self._read_headers()
        if not head:
            return
        try:
            request_line = head.split(b"\r\n", 1)[0].decode("latin-1")
            method, target, _ = request_line.split(" ", 2)
        except ValueError:
            return

        if method.upper() == "CONNECT":
            host, _, port_s = target.partition(":")
            port = int(port_s) if port_s else 443
            host = host.strip("[]")
            if not self.allow.permits(host, port):
                self._refuse(host, port, "403 Forbidden", f"host not allowlisted: {host}:{port}")
                return
            upstream = self._connect_upstream(host, port)
            if upstream is None:
                return
            self.log.record(decision="allow", host=host, port=port)
            self.client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self.client.settimeout(None)
            _pipe(self.client, upstream)
            upstream.close()
            return

        # Plain HTTP: derive host from absolute URI or Host header.
        host, port = self._plain_http_target(target, head)
        if host is None:
            self._refuse("", 0, "400 Bad Request", "could not determine target host")
            return
        if not self.allow.permits(host, port):
            self._refuse(host, port, "403 Forbidden", f"host not allowlisted: {host}:{port}")
            return
        upstream = self._connect_upstream(host, port)
        if upstream is None:
            return
        self.log.record(decision="allow", host=host, port=port)
        upstream.sendall(head)
        self.client.settimeout(None)
        _pipe(self.client, upstream)
        upstream.close()

    @staticmethod
    def _plain_http_target(target: str, head: bytes) -> tuple[str | None, int]:
        host: str | None = None
        port = 80
        if target.startswith("http://"):
            rest = target[len("http://"):]
            authority = rest.split("/", 1)[0]
            h, _, p = authority.partition(":")
            host = h
            if p:
                port = int(p)
            return host, port
        for line in head.split(b"\r\n")[1:]:
            if not line:
                break
            if line.lower().startswith(b"host:"):
                value = line.split(b":", 1)[1].strip().decode("latin-1")
                h, _, p = value.partition(":")
                host = h
                if p:
                    port = int(p)
                break
        return host, port


def serve(host: str, port: int, allow: Allowlist, log: ProxyLog) -> socket.socket:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(128)

    def _accept_loop() -> None:
        while True:
            try:
                client, _ = server.accept()
            except OSError:
                return
            Handler(client, allow, log).start()

    threading.Thread(target=_accept_loop, daemon=True).start()
    return server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="omp-guard domain-allowlist egress proxy")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 = ephemeral; printed on startup")
    parser.add_argument(
        "--policy",
        default=str(Path(__file__).resolve().parent.parent / "policies" / "default.yml"),
    )
    parser.add_argument("--log", default=None, help="JSON-lines decision log path")
    parser.add_argument(
        "--print-port",
        action="store_true",
        help="print the bound port to stdout then keep serving",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    entries = load_allowlist(Path(args.policy))
    if not entries:
        print(
            f"egress-proxy: no allowedDomains found in {args.policy}; refusing all egress",
            file=sys.stderr,
        )
    allow = Allowlist(entries)
    log = ProxyLog(Path(args.log).resolve() if args.log else None)

    server = serve(args.host, args.port, allow, log)
    bound_port = server.getsockname()[1]
    if args.print_port:
        print(bound_port, flush=True)
    print(
        f"egress-proxy: listening on {args.host}:{bound_port} "
        f"({len(entries)} allowlist entries)",
        file=sys.stderr,
        flush=True,
    )

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
