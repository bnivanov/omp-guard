#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path


DEFAULT_AGENTWORK = Path.home() / "AgentWork"
BACKENDS = {
    "light": "Daily mode. On macOS: Tier 0 Seatbelt sandbox + egress proxy (workspace-confined FS, allowlisted network) at ~0 RAM. Not VM-grade isolation.",
    "docker-sbx": "High-isolation Docker/sbx mode. Use for risky repos, package installs, shell-heavy or untrusted work. High RAM.",
    "native-mac": "Planned/experimental macOS-native sandbox mode. Do not treat as ready until doctor says available.",
}


def env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


def main() -> int:
    estate = env_path("OMP_GUARD_ALLOWED_ROOT", DEFAULT_AGENTWORK)
    state = env_path("OMP_GUARD_STATE", estate / ".omp-guard-state")
    docs = Path(__file__).resolve().parent.parent / "docs" / "security-models.md"

    print("omp-guard security summary")
    print(f"estate root: {estate}")
    print(f"state directory: {state}")
    print("available backends: light, docker-sbx, native-mac")
    for name, description in BACKENDS.items():
        print(f"  {name}: {description}")
    print(f"full docs: {docs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
