from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROFILE_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
CORE_PROFILES = [
    "chief-of-staff",
    "researcher",
    "marketer",
    "developer",
    "reviewer",
    "operator",
    "librarian",
]

PROFILE_POLICIES = {
    "chief-of-staff": "hermes-orchestrator.yml",
    "operator": "hermes-orchestrator.yml",
    "researcher": "hermes-research.yml",
    "marketer": "hermes-research.yml",
    "librarian": "hermes-research.yml",
    "developer": "hermes-dev.yml",
    "reviewer": "hermes-dev.yml",
}

TOKEN_ENV_KEYS = [
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_PAT",
    "COPILOT_GITHUB_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENCODE_API_KEY",
    "OPENCODE_GO_API_KEY",
]

PROFILE_DIR_KEYS = [
    "root",
    "home",
    "tmp",
    "xdg_config",
    "xdg_cache",
    "xdg_data",
    "logs",
    "sessions",
    "state",
    "cron",
    "kanban",
    "checkpoints",
    "skills",
    "memories",
]


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def allowed_root() -> Path:
    return Path(os.environ.get("OMP_GUARD_ALLOWED_ROOT", str(Path.home() / "AgentWork"))).expanduser().resolve()


def hermes_root() -> Path:
    return Path(os.environ.get("HERMES_GUARD_ROOT", str(allowed_root() / "hermes"))).expanduser().resolve()


def projects_root() -> Path:
    return allowed_root() / "projects"


def guard_log_dir() -> Path:
    return allowed_root() / ".omp-guard-logs"


def guard_tmp_root() -> Path:
    return allowed_root() / ".omp-guard-tmp" / "hermes-light"


def canonical_hermes_home(actual_home: Path | None = None) -> Path:
    """Return the canonical Hermes Desktop/CLI home for Stage A.

    Stage A deliberately uses Hermes' real account-level state so the Desktop
    app, CLI, auth, model cache, sessions, and updates remain compatible. Tests
    may set HOME to a temporary account root; the canonical home remains
    exactly $HOME/.hermes.
    """
    home = (actual_home or Path.home()).expanduser().resolve()
    explicit = os.environ.get("HERMES_GUARD_CANONICAL_HOME", "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (home / ".hermes").resolve()


def validate_canonical_hermes_home(actual_home: Path | None = None) -> tuple[Path, str]:
    home = (actual_home or Path.home()).expanduser().resolve()
    canonical = canonical_hermes_home(home)
    expected = (home / ".hermes").resolve()
    if canonical != expected:
        raise ValueError(f"canonical Hermes home must be exactly {expected}; got {canonical}")
    if not canonical.exists():
        raise FileNotFoundError(f"canonical Hermes home is missing: {canonical}")
    ok, message = check_private_dir(canonical)
    if not ok:
        raise PermissionError(message)
    return canonical, message


def ensure_guard_tmp_dir() -> Path:
    path = guard_tmp_root()
    ensure_private_dir(path)
    return path


def ensure_guard_log_dir() -> Path:
    path = guard_log_dir()
    ensure_private_dir(path)
    return path


def profile_name_is_safe(profile: str) -> bool:
    return bool(PROFILE_RE.fullmatch(profile)) and ".." not in profile and "/" not in profile


def validate_profile_name(profile: str) -> None:
    if not profile_name_is_safe(profile):
        raise ValueError(
            "unsafe Hermes profile name. Use lower-case letters, numbers, and dashes; "
            "start with a letter; do not use slashes or '..'."
        )


def profile_root(profile: str) -> Path:
    validate_profile_name(profile)
    root = hermes_root() / "profiles" / profile
    if not is_under(root, allowed_root()):
        raise ValueError(f"computed HERMES_HOME escapes AgentWork: {root}")
    return root.resolve()


def profile_paths(profile: str) -> dict[str, Path]:
    root = profile_root(profile)
    return {
        "root": root,
        "home": root / "home",
        "tmp": root / "tmp",
        "xdg_config": root / "xdg-config",
        "xdg_cache": root / "xdg-cache",
        "xdg_data": root / "xdg-data",
        "logs": root / "logs",
        "sessions": root / "sessions",
        "state": root / "state",
        "cron": root / "cron",
        "kanban": root / "kanban",
        "checkpoints": root / "checkpoints",
        "skills": root / "skills",
        "memories": root / "memories",
    }


def profile_local_runtime_paths(profile: str) -> list[Path]:
    """Return profile-local paths Hermes may use for the advanced isolated mode.

    This remains available for future experiments, but it is no longer the
    default Stage A runtime because Hermes Desktop and CLI expect canonical
    state under $HOME/.hermes.
    """
    paths = profile_paths(profile)
    home = paths["home"]
    candidates = [
        paths["root"],
        paths["home"],
        paths["tmp"],
        paths["xdg_config"],
        paths["xdg_cache"],
        paths["xdg_data"],
        paths["logs"],
        paths["sessions"],
        paths["state"],
        paths["cron"],
        paths["kanban"],
        paths["checkpoints"],
        paths["skills"],
        paths["memories"],
        home / ".local",
        home / ".local" / "state",
        home / ".local" / "state" / "hermes",
        home / ".local" / "share",
        home / ".local" / "share" / "hermes",
        home / ".cache",
        home / ".cache" / "hermes",
    ]

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        key = str(resolved)
        if key not in seen:
            deduped.append(resolved)
            seen.add(key)
    return deduped


def canonical_sidecar_paths(canonical_home: Path) -> list[Path]:
    """Return narrow HOME-relative Hermes sidecar paths used by dependencies.

    Even with HERMES_HOME set, Python/Node libraries may consult appdirs/XDG
    defaults under the real account home. We allow only Hermes-scoped sidecars,
    not broad ~/.local, ~/.cache, or ~/.config.
    """
    home = canonical_home.parent.resolve()
    return [
        home / ".local" / "state" / "hermes",
        home / ".local" / "share" / "hermes",
        home / ".cache" / "hermes",
        home / ".config" / "hermes",
    ]


def canonical_runtime_write_paths(canonical_home: Path, tmp_dir: Path, log_dir: Path) -> list[Path]:
    candidates = [canonical_home, *canonical_sidecar_paths(canonical_home), tmp_dir, log_dir]
    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        ensure_private_dir(candidate)
        resolved = candidate.resolve()
        key = str(resolved)
        if key not in seen:
            deduped.append(resolved)
            seen.add(key)
    return deduped


def ensure_private_dir(path: Path) -> None:
    existed = path.exists()
    path.mkdir(parents=True, exist_ok=True)
    if existed:
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(f"directory permissions too open: {path} is {oct(mode)}, expected 0700")
    path.chmod(0o700)


def ensure_profile_dirs(profile: str) -> dict[str, Path]:
    paths = profile_paths(profile)
    for path in list(paths.values()) + profile_local_runtime_paths(profile):
        ensure_private_dir(path)
    return paths


def check_private_dir(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing directory: {path}"
    if not path.is_dir():
        return False, f"not a directory: {path}"
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o700:
        return False, f"permissions are {oct(mode)}, expected 0700: {path}"
    return True, f"private directory: {path}"


def policy_for_profile(profile: str) -> Path:
    explicit = os.environ.get("HERMES_GUARD_POLICY")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return (ROOT / "policies" / PROFILE_POLICIES.get(profile, "hermes-v1.yml")).resolve()


def find_hermes_bin() -> str | None:
    return os.environ.get("HERMES_GUARD_HERMES_BIN") or shutil.which("hermes")


def scrubbed_env(base: dict[str, str] | None = None) -> tuple[dict[str, str], list[str]]:
    env = dict(base or os.environ)
    scrubbed: list[str] = []
    for key in TOKEN_ENV_KEYS:
        if key in env:
            scrubbed.append(key)
            env.pop(key, None)
    return env, scrubbed


def forbidden_workdir_prefixes() -> list[Path]:
    actual_home = Path.home()
    personal_home = os.environ.get("OMP_GUARD_PERSONAL_HOME")
    if not personal_home:
        raise RuntimeError("OMP_GUARD_PERSONAL_HOME is not set — refusing to launch without personal home protection")
    return [
        Path(personal_home),
        Path("/Users/Shared"),
        actual_home / "Desktop",
        actual_home / "Documents",
        actual_home / "Downloads",
        actual_home / "Library" / "Mobile Documents",
    ]


def assert_safe_workdir(workdir: Path, *, require_project_cwd: bool) -> None:
    workdir = workdir.resolve()
    root = allowed_root()
    if not is_under(workdir, root):
        raise RuntimeError(f"refusing to launch outside AgentWork: {workdir} (allowed root: {root})")
    if require_project_cwd and not is_under(workdir, projects_root()):
        raise RuntimeError(f"refusing to launch outside AgentWork/projects: {workdir} (projects root: {projects_root()})")
    for prefix in forbidden_workdir_prefixes():
        if prefix.exists() and is_under(workdir, prefix):
            raise RuntimeError(f"refusing to launch under forbidden path: {prefix}")


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd or ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
