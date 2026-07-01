#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


TOOLS = [
    {
        "name": "doctor",
        "description": "Run the omp-guard pre-launch doctor check.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "validate_policy",
        "description": "Validate the default omp-guard policy file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "policy_path": {
                    "type": "string",
                    "description": "Optional policy path. Defaults to policies/default.yml.",
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "classify_command",
        "description": "Classify a command as allow, ask, or block without executing it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to classify.",
                }
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
    {
        "name": "guarded_run_dry_run",
        "description": "Run a dry-run guarded command decision. This never executes the command.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to classify through the guarded runner.",
                },
                "approve_ask": {
                    "type": "boolean",
                    "description": "Whether to approve ask-classified commands for dry-run only.",
                    "default": False,
                },
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
]


def respond(message_id: Any, result: Any) -> None:
    print(json.dumps({"jsonrpc": "2.0", "id": message_id, "result": result}), flush=True)


def error(message_id: Any, code: int, message: str) -> None:
    print(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {"code": code, "message": message},
            }
        ),
        flush=True,
    )


def notification(method: str, params: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        payload["params"] = params
    print(json.dumps(payload), flush=True)


def text_result(text: str) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": text,
            }
        ]
    }


def run_command(args: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output = result.stdout
    if result.stderr:
        output += result.stderr
    return result.returncode, output.strip()


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "doctor":
        code, output = run_command(["./omp-guard", "doctor"])
        return text_result(f"exit_code={code}\n{output}")

    if name == "validate_policy":
        policy_path = arguments.get("policy_path")
        args = ["./omp-guard", "validate-policy"]
        if policy_path:
            args.append(str(policy_path))
        code, output = run_command(args)
        return text_result(f"exit_code={code}\n{output}")

    if name == "classify_command":
        command = str(arguments.get("command", "")).strip()
        if not command:
            raise ValueError("command is required")
        code, output = run_command(["./omp-guard", "classify", command])
        return text_result(f"exit_code={code}\n{output}")

    if name == "guarded_run_dry_run":
        command = str(arguments.get("command", "")).strip()
        if not command:
            raise ValueError("command is required")

        args = ["./omp-guard", "run", "--dry-run"]
        if bool(arguments.get("approve_ask", False)):
            args.append("--approve-ask")
        args.extend(["--", command])

        code, output = run_command(args)
        return text_result(f"exit_code={code}\n{output}")

    raise ValueError(f"unknown tool: {name}")


def handle(request: dict[str, Any]) -> None:
    message_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if method == "initialize":
        respond(
            message_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": "omp-guard",
                    "version": "0.1.0",
                },
            },
        )
        return

    if method == "notifications/initialized":
        return

    if method == "ping":
        respond(message_id, {})
        return

    if method == "tools/list":
        respond(message_id, {"tools": TOOLS})
        return

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}

        try:
            result = call_tool(str(name), arguments)
            respond(message_id, result)
        except Exception as exc:
            error(message_id, -32000, str(exc))
        return

    error(message_id, -32601, f"method not found: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            error(None, -32700, f"parse error: {exc}")
            continue

        try:
            handle(request)
        except Exception as exc:
            error(request.get("id"), -32603, f"internal error: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
