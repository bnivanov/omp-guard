#!/usr/bin/env python3
"""Unit tests for the Tier 0 building blocks: allowlist matching, profile
generation, and the light-mode Seatbelt gating decision.

These are deterministic and OS-agnostic (they do NOT require sandbox-exec).
The live enforcement proof lives in scripts/seatbelt-selftest.py.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import seatbelt  # noqa: E402


def _load_proxy_module():
    """egress-proxy.py has a hyphen; load it by path."""
    spec = importlib.util.spec_from_file_location("egress_proxy", SCRIPTS / "egress-proxy.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


egress = _load_proxy_module()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def test_allowlist_exact() -> None:
    a = egress.Allowlist(["api.anthropic.com:443"])
    require(a.permits("api.anthropic.com", 443), "exact host:port should match")
    require(not a.permits("api.anthropic.com", 80), "wrong port should not match")
    require(not a.permits("evil.com", 443), "other host should not match")


def test_allowlist_any_port() -> None:
    a = egress.Allowlist(["host.docker.internal"])
    require(a.permits("host.docker.internal", 11434), "bare host allows any port")
    require(a.permits("host.docker.internal", 443), "bare host allows any port (2)")


def test_allowlist_wildcard() -> None:
    a = egress.Allowlist(["*.openrouter.ai:443"])
    require(a.permits("api.openrouter.ai", 443), "wildcard should match one label")
    require(a.permits("a.b.openrouter.ai", 443), "wildcard should match multiple labels")
    require(not a.permits("openrouter.ai", 443), "wildcard should NOT match bare apex")
    require(not a.permits("api.openrouter.ai", 80), "wildcard port must still match")
    require(not a.permits("openrouter.ai.evil.com", 443), "suffix confusion must not match")


def test_allowlist_empty_denies_all() -> None:
    a = egress.Allowlist([])
    require(not a.permits("api.anthropic.com", 443), "empty allowlist denies everything")


def test_load_allowlist_from_policy() -> None:
    policy = SCRIPTS.parent / "policies" / "default.yml"
    entries = egress.load_allowlist(policy)
    require("api.anthropic.com:443" in entries, "model API should be in default allowlist")
    # GitHub/npm are opt-in (commented) — must NOT be active by default.
    require("github.com:443" not in entries, "github must be opt-in, not default")
    require("registry.npmjs.org:443" not in entries, "npm must be opt-in, not default")


def test_profile_denies_by_default() -> None:
    prof = seatbelt.build_profile(
        workspace=Path("/tmp/ws"), state_dir=Path("/tmp/st"),
        tmp_dir=Path("/tmp/tm"), proxy_port=8899,
    )
    require("(deny default" in prof, "profile must deny by default")
    require('(subpath "/tmp/ws")' in prof, "workspace must be allowed")
    require('(remote ip "localhost:8899")' in prof, "proxy port must be allowed")


def test_profile_no_proxy_denies_network() -> None:
    prof = seatbelt.build_profile(
        workspace=Path("/tmp/ws"), state_dir=Path("/tmp/st"),
        tmp_dir=Path("/tmp/tm"), proxy_port=None,
    )
    require("network-outbound" not in prof, "no-proxy profile must not allow outbound")
    require("all outbound network denied" in prof.lower() or "network-outbound" not in prof,
           "no-proxy profile must deny network")


def test_profile_does_not_leak_home() -> None:
    prof = seatbelt.build_profile(
        workspace=Path("/tmp/ws"), state_dir=Path("/tmp/st"),
        tmp_dir=Path("/tmp/tm"), proxy_port=8899,
    )
    # No blanket read of the whole home or /Users — only scoped carve-outs.
    require('(subpath "/Users")' not in prof, "must not blanket-allow /Users")
    require('(subpath "/private/var/folders")' not in prof, "must not allow per-user temp")
    # No socket escape hatches in the network rule.
    require("remote unix-socket" not in prof, "must not allow unix-socket egress")
    require("system-socket" not in prof, "must not allow raw system sockets")
    require("network-bind" not in prof, "must not allow binding/listening")


def test_profile_sbpl_quoting() -> None:
    # A path with a double-quote must be escaped, not break the profile.
    prof = seatbelt.build_profile(
        workspace=Path('/tmp/a"b'), state_dir=Path("/tmp/st"),
        tmp_dir=Path("/tmp/tm"), proxy_port=None,
    )
    require('a\\"b' in prof, "double-quote in path must be escaped")


def test_seatbelt_policy_gating() -> None:
    import light_launch  # noqa

    orig = dict(__import__("os").environ)
    os_env = __import__("os").environ
    try:
        for key in ("OMP_GUARD_SEATBELT", "OMP_GUARD_DISABLE_SEATBELT"):
            os_env.pop(key, None)
        require(light_launch.seatbelt_policy() == "auto", "default policy is auto")

        os_env["OMP_GUARD_DISABLE_SEATBELT"] = "1"
        require(light_launch.seatbelt_policy() == "off", "legacy disable maps to off")
        os_env.pop("OMP_GUARD_DISABLE_SEATBELT")

        os_env["OMP_GUARD_SEATBELT"] = "require"
        require(light_launch.seatbelt_policy() == "require", "explicit require honored")

        os_env["OMP_GUARD_SEATBELT"] = "off"
        require(light_launch.seatbelt_policy() == "off", "explicit off honored")

        os_env["OMP_GUARD_SEATBELT"] = "bogus"
        require(light_launch.seatbelt_policy() == "auto", "unknown value falls back to auto")
    finally:
        os_env.clear()
        os_env.update(orig)


def main() -> int:
    # light-launch.py has a hyphen; expose it as light_launch for the gating test.
    spec = importlib.util.spec_from_file_location("light_launch", SCRIPTS / "light-launch.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["light_launch"] = module
    spec.loader.exec_module(module)

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print(f"\nAll {len(tests)} seatbelt unit tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
