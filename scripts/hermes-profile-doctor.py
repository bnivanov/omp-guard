#!/usr/bin/env python3
from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hermes_common as hc  # noqa: E402


SOUL_TEMPLATES = {
    "chief-of-staff": """# Chief of Staff\n\nYou are the orchestrator for Bobby's local Hermes agent organisation.\n\nYou decompose, route, supervise, and report. You do not perform specialist work yourself.\n\nYour default action is to create clear Kanban tasks with title, assignee, acceptance criteria, constraints, workspace, evidence required, and dependencies.\n\nYou must not run terminal commands, edit source code, browse authenticated websites, send external messages, create cron jobs, install packages, request secrets, or store secrets.\n\nEscalate to Bobby when a task needs credentials, external publication, GitHub mutation, access outside AgentWork, broader tools, or has failed twice.\n""",
    "researcher": """# Researcher\n\nYou are a disciplined research agent.\n\nYou gather evidence, compare sources, cite claims, and separate fact from inference. Prefer primary sources. Flag uncertainty. Do not publish, mutate repositories, or store secrets.\n""",
    "marketer": """# Marketer\n\nYou are a controlled drafting agent.\n\nYou turn approved research into drafts, positioning, messaging, and campaign materials inside the assigned drafts workspace. You do not publish externally or use social accounts.\n""",
    "developer": """# Developer\n\nYou are an implementation agent.\n\nYou work only in the assigned workspace or worktree. Make small, testable changes. Run relevant tests. Leave evidence. Do not use sudo, install packages, push to GitHub, or edit outside the assigned workspace unless explicitly authorised.\n""",
    "reviewer": """# Reviewer\n\nYou are a skeptical code and safety reviewer.\n\nYou verify claims, inspect diffs, run tests where allowed, and identify residual risk. Do not implement unless explicitly assigned an implementation card.\n""",
    "operator": """# Operator\n\nYou are a controlled operations agent.\n\nYou maintain local routines, summaries, and watchdog checks only where explicitly configured. You do not create new cron jobs, send email, publish externally, or use shell admin powers.\n""",
    "librarian": """# Librarian\n\nYou maintain durable local knowledge, wiki notes, and proposed skill updates.\n\nYou may draft skill changes for review, but approved skills require Bobby's approval before promotion. Do not store secrets or raw dumps.\n""",
}

PROFILE_MANIFESTS = {
    "chief-of-staff": """profile: chief-of-staff\ndescription: Orchestrates work through Kanban and memory only.\nallowed_toolsets:\n  - kanban\n  - memory\n  - session_search\n  - clarify\nforbidden_toolsets:\n  - terminal\n  - browser\n  - cronjob\n  - github_write\nnetwork_policy: hermes-orchestrator.yml\n""",
    "researcher": """profile: researcher\ndescription: Finds, verifies, cites, and summarizes external information.\nallowed_toolsets:\n  - web\n  - file-read\n  - memory\n  - kanban\nforbidden_toolsets:\n  - terminal\n  - browser\n  - github_write\nnetwork_policy: hermes-research.yml\n""",
    "marketer": """profile: marketer\ndescription: Drafts controlled marketing copy from approved inputs.\nallowed_toolsets:\n  - web\n  - file-read\n  - file-write-drafts\n  - memory\n  - kanban\nforbidden_toolsets:\n  - external_posting\n  - browser\n  - github_write\nnetwork_policy: hermes-research.yml\n""",
    "developer": """profile: developer\ndescription: Implements scoped changes in assigned workspaces only.\nallowed_toolsets:\n  - terminal\n  - file\n  - code_execution\n  - kanban\nforbidden_toolsets:\n  - sudo\n  - github_push\n  - github_merge\nnetwork_policy: hermes-dev.yml\n""",
    "reviewer": """profile: reviewer\ndescription: Reviews diffs, tests, safety posture, and residual risk.\nallowed_toolsets:\n  - file-read\n  - terminal-test-only\n  - kanban\nforbidden_toolsets:\n  - file-patch\n  - github_push\n  - github_merge\nnetwork_policy: hermes-dev.yml\n""",
    "operator": """profile: operator\ndescription: Runs approved operational routines only.\nallowed_toolsets:\n  - cronjob\n  - kanban\n  - file\n  - memory\nforbidden_toolsets:\n  - shell_admin\n  - package_install\n  - external_send\nnetwork_policy: hermes-orchestrator.yml\n""",
    "librarian": """profile: librarian\ndescription: Curates wiki notes and proposed skills.\nallowed_toolsets:\n  - memory\n  - skills-draft\n  - file\n  - kanban\nforbidden_toolsets:\n  - terminal\n  - browser\n  - external_skill_write\nnetwork_policy: hermes-research.yml\n""",
}

ROLE_FORBIDDEN_TERMS = {
    "chief-of-staff": ["terminal", "browser", "cronjob", "github_write", "github_push", "external_posting"],
    "researcher": ["terminal", "github_write", "github_push", "external_posting"],
    "marketer": ["github_write", "github_push", "external_posting"],
    "reviewer": ["github_push", "github_merge"],
}


class Reporter:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def ok(self, message: str) -> None:
        print(f"OK: {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"WARN: {message}")

    def fail(self, message: str) -> None:
        self.errors.append(message)
        print(f"FAIL: {message}")


def init_profile(profile: str) -> None:
    paths = hc.ensure_profile_dirs(profile)
    soul = paths["root"] / "SOUL.md"
    manifest = paths["root"] / "profile.yml"
    if not soul.exists():
        soul.write_text(SOUL_TEMPLATES.get(profile, f"# {profile}\n\nControlled Hermes profile.\n"), encoding="utf-8")
        soul.chmod(0o600)
    if not manifest.exists():
        manifest.write_text(PROFILE_MANIFESTS.get(profile, f"profile: {profile}\nnetwork_policy: hermes-v1.yml\n"), encoding="utf-8")
        manifest.chmod(0o600)


def check_file_private(path: Path, reporter: Reporter, label: str) -> None:
    if not path.exists():
        reporter.fail(f"missing {label}: {path}")
        return
    if not path.is_file():
        reporter.fail(f"{label} is not a file: {path}")
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        reporter.fail(f"{label} permissions too open: {path} is {oct(mode)}, expected 0600/0640 max")
    else:
        reporter.ok(f"private {label}: {path}")
    if not path.read_text(encoding="utf-8", errors="replace").strip():
        reporter.fail(f"{label} is empty: {path}")


def check_manifest(profile: str, manifest: Path, reporter: Reporter) -> None:
    if not manifest.exists():
        reporter.warn(f"missing profile manifest: {manifest}")
        return
    text = manifest.read_text(encoding="utf-8", errors="replace")
    if f"profile: {profile}" in text:
        reporter.ok("manifest declares matching profile")
    else:
        reporter.fail("manifest does not declare the expected profile")
    policy_name = hc.policy_for_profile(profile).name
    if policy_name in text:
        reporter.ok(f"manifest references expected network policy: {policy_name}")
    else:
        reporter.warn(f"manifest does not reference expected network policy: {policy_name}")
    allowed_block = text.split("forbidden_toolsets:", 1)[0]
    for term in ROLE_FORBIDDEN_TERMS.get(profile, []):
        if f"- {term}" in allowed_block:
            reporter.fail(f"manifest appears to allow forbidden toolset for {profile}: {term}")


def check_no_seeded_credentials(paths: dict[str, Path], reporter: Reporter) -> None:
    risky = [
        paths["home"] / ".ssh",
        paths["home"] / ".config" / "gh",
        paths["home"] / "Library" / "Keychains",
        paths["home"] / "Library" / "Application Support" / "Google" / "Chrome",
        paths["home"] / "Library" / "Safari",
    ]
    found = False
    for path in risky:
        if path.exists():
            found = True
            reporter.fail(f"seeded credential/browser path exists inside Hermes profile home: {path}")
    if not found:
        reporter.ok("no seeded SSH/GitHub/browser credential paths found inside profile home")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one isolated Hermes profile home.")
    parser.add_argument("profile", help="Hermes profile name, e.g. chief-of-staff")
    parser.add_argument("--init", action="store_true", help="Create the profile directory, SOUL.md, and profile.yml if missing.")
    args = parser.parse_args()

    reporter = Reporter()
    profile = args.profile
    print(f"hermes-profile-doctor: {profile}")

    try:
        hc.validate_profile_name(profile)
        reporter.ok("profile name is safe")
    except ValueError as exc:
        reporter.fail(str(exc))
        return 1

    if args.init:
        try:
            init_profile(profile)
            reporter.ok("profile initialized")
        except (OSError, PermissionError, ValueError) as exc:
            reporter.fail(f"profile initialization failed: {exc}")
            return 1

    try:
        paths = hc.profile_paths(profile)
    except ValueError as exc:
        reporter.fail(str(exc))
        return 1

    if hc.is_under(paths["root"], hc.allowed_root()):
        reporter.ok(f"HERMES_HOME is under AgentWork: {paths['root']}")
    else:
        reporter.fail(f"HERMES_HOME escapes AgentWork: {paths['root']}")

    for key in ["root", "home", "tmp", "xdg_config", "xdg_cache", "xdg_data", "logs", "skills", "memories"]:
        ok, message = hc.check_private_dir(paths[key])
        (reporter.ok if ok else reporter.fail)(message)

    check_file_private(paths["root"] / "SOUL.md", reporter, "SOUL.md")
    check_file_private(paths["root"] / "profile.yml", reporter, "profile.yml")
    check_manifest(profile, paths["root"] / "profile.yml", reporter)
    check_no_seeded_credentials(paths, reporter)

    policy = hc.policy_for_profile(profile)
    if policy.exists():
        reporter.ok(f"network policy exists: {policy}")
    else:
        reporter.fail(f"network policy missing: {policy}")

    print()
    print(f"warnings: {len(reporter.warnings)}")
    print(f"errors: {len(reporter.errors)}")
    return 1 if reporter.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
