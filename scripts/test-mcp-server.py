#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def send(proc: subprocess.Popen[str], payload: dict) -> dict:
    assert proc.stdin is not None
    assert proc.stdout is not None

    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()

    line = proc.stdout.readline()
    if not line:
        raise RuntimeError("MCP server returned no response")

    return json.loads(line)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def main() -> int:
    proc = subprocess.Popen(
        ["./omp-guard", "mcp-server"],
        cwd=ROOT,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        init = send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "omp-guard-test", "version": "0.1.0"},
                },
            },
        )
        require(init["result"]["serverInfo"]["name"] == "omp-guard", "initialize failed")

        tools = send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in tools["result"]["tools"]}

        require("doctor" in names, "doctor tool missing")
        require("validate_policy" in names, "validate_policy tool missing")
        require("classify_command" in names, "classify_command tool missing")
        require("guarded_run_dry_run" in names, "guarded_run_dry_run tool missing")

        classify = send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "classify_command",
                    "arguments": {"command": "git status --short"},
                },
            },
        )
        text = classify["result"]["content"][0]["text"]
        require("decision=allow" in text, "classify_command did not return allow")

        blocked = send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "guarded_run_dry_run",
                    "arguments": {"command": "sudo rm -rf /"},
                },
            },
        )
        text = blocked["result"]["content"][0]["text"]
        require("decision=block" in text, "guarded_run_dry_run did not block destructive command")
        require("blocked command refused" in text, "blocked refusal text missing")

        print("All MCP smoke tests passed.")
        return 0

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
