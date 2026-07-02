#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

pass() {
  echo "PASS: $*"
}

assert_contains() {
  local haystack="$1"
  local needle="$2"

  if ! printf '%s\n' "$haystack" | grep -Fq "$needle"; then
    echo "$haystack" >&2
    fail "expected output to contain: $needle"
  fi
}

python3 -m py_compile \
  scripts/hermes_common.py \
  scripts/hermes-light-launch.py \
  scripts/hermes-profile-doctor.py \
  scripts/hermes-doctor.py \
  scripts/seatbelt.py
pass "Hermes Python scripts compile"

for policy in policies/hermes-v1.yml policies/hermes-orchestrator.yml policies/hermes-research.yml policies/hermes-dev.yml; do
  python3 scripts/validate-policy.py "$policy" >/dev/null
  pass "policy validates: $policy"
done

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/hermes-guard-test.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/projects/probe" "$TMP_ROOT/personal" "$TMP_ROOT/bin" "$TMP_ROOT/runtime/hermes-agent"

cat > "$TMP_ROOT/bin/fake-hermes" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

for key in HERMES_HOME HOME XDG_CONFIG_HOME XDG_CACHE_HOME XDG_DATA_HOME XDG_STATE_HOME TMPDIR HERMES_GUARD_PROFILE HERMES_GUARD_POLICY_EFFECTIVE; do
  if [ -z "${!key:-}" ]; then
    echo "missing $key" >&2
    exit 88
  fi
done

[ "$HERMES_GUARD_PROFILE" = "chief-of-staff" ] || { echo "unexpected profile: $HERMES_GUARD_PROFILE" >&2; exit 88; }
[ "$HOME" = "$HERMES_HOME/home" ] || { echo "HOME not profile-local: $HOME" >&2; exit 88; }
[ "$XDG_CONFIG_HOME" = "$HERMES_HOME/xdg-config" ] || { echo "XDG_CONFIG_HOME not profile-local: $XDG_CONFIG_HOME" >&2; exit 88; }
[ "$XDG_CACHE_HOME" = "$HERMES_HOME/xdg-cache" ] || { echo "XDG_CACHE_HOME not profile-local: $XDG_CACHE_HOME" >&2; exit 88; }
[ "$XDG_DATA_HOME" = "$HERMES_HOME/xdg-data" ] || { echo "XDG_DATA_HOME not profile-local: $XDG_DATA_HOME" >&2; exit 88; }
[ "$XDG_STATE_HOME" = "$HERMES_HOME/state" ] || { echo "XDG_STATE_HOME not profile-local: $XDG_STATE_HOME" >&2; exit 88; }
[ "$TMPDIR" = "$HERMES_HOME/tmp" ] || { echo "TMPDIR not profile-local: $TMPDIR" >&2; exit 88; }

for token_key in GITHUB_TOKEN GH_TOKEN GITHUB_PAT COPILOT_GITHUB_TOKEN; do
  if [ "${!token_key+x}" = "x" ]; then
    echo "GitHub token leaked to Hermes process: $token_key" >&2
    exit 88
  fi
done

printf 'FAKE_HERMES_OK\n'
SH
chmod 700 "$TMP_ROOT/bin/fake-hermes"

COMMON_ENV=(
  "OMP_GUARD_ALLOWED_ROOT=$TMP_ROOT"
  "OMP_GUARD_PERSONAL_HOME=$TMP_ROOT/personal"
  "HERMES_GUARD_HERMES_BIN=$TMP_ROOT/bin/fake-hermes"
  "HERMES_GUARD_RUNTIME_DIR=$TMP_ROOT/runtime/hermes-agent"
  "HERMES_GUARD_SEATBELT=off"
  "GITHUB_TOKEN=do-not-forward"
  "GH_TOKEN=do-not-forward"
)

out="$(env "${COMMON_ENV[@]}" python3 scripts/hermes-profile-doctor.py chief-of-staff --init)"
assert_contains "$out" "OK: profile initialized"
pass "profile doctor initializes chief-of-staff"

out="$(env "${COMMON_ENV[@]}" python3 scripts/hermes-profile-doctor.py chief-of-staff)"
assert_contains "$out" "errors: 0"
assert_contains "$out" "$TMP_ROOT/hermes/profiles/chief-of-staff/state"
assert_contains "$out" "$TMP_ROOT/hermes/profiles/chief-of-staff/sessions"
assert_contains "$out" "$TMP_ROOT/hermes/profiles/chief-of-staff/kanban"
assert_contains "$out" "$TMP_ROOT/hermes/profiles/chief-of-staff/cron"
assert_contains "$out" "$TMP_ROOT/hermes/profiles/chief-of-staff/checkpoints"
pass "profile doctor validates Stage A runtime directories"

out="$(env "${COMMON_ENV[@]}" python3 - <<'PY'
from pathlib import Path
import sys

sys.path.insert(0, "scripts")
import hermes_common as hc

paths = hc.ensure_profile_dirs("chief-of-staff")
for key in ("state", "sessions", "kanban", "cron", "checkpoints"):
    path = paths[key]
    if not path.exists():
        raise SystemExit(f"missing {key}: {path}")
for path in hc.profile_local_runtime_paths("chief-of-staff"):
    if not path.exists():
        raise SystemExit(f"missing profile-local runtime path: {path}")
print("PROFILE_RUNTIME_DIRS_OK")
PY
)"
assert_contains "$out" "PROFILE_RUNTIME_DIRS_OK"
pass "profile bootstrap creates Hermes runtime directories"

out="$(env "${COMMON_ENV[@]}" python3 - <<'PY'
from pathlib import Path
import os
import sys

sys.path.insert(0, "scripts")
import hermes_common as hc
import seatbelt

workspace = Path(os.environ["OMP_GUARD_ALLOWED_ROOT"]) / "projects" / "probe"
paths = hc.ensure_profile_dirs("chief-of-staff")
profile = seatbelt.build_profile(
    workspace=workspace,
    state_dir=paths["root"],
    tmp_dir=paths["tmp"],
    proxy_port=12345,
    extra_read_paths=[Path(os.environ["HERMES_GUARD_RUNTIME_DIR"])],
    extra_write_paths=hc.profile_local_runtime_paths("chief-of-staff"),
)
required = [
    "(allow file-ioctl)",
    str(paths["state"]),
    str(paths["sessions"]),
    str(paths["home"] / ".local" / "state" / "hermes"),
]
for needle in required:
    if needle not in profile:
        raise SystemExit(f"missing Seatbelt rule for {needle}")
forbidden = str(Path(os.environ["OMP_GUARD_ALLOWED_ROOT"]) / ".hermes")
if forbidden in profile:
    raise SystemExit(f"Seatbelt profile unexpectedly allows global Hermes path: {forbidden}")
print("SEATBELT_PROFILE_OK")
PY
)"
assert_contains "$out" "SEATBELT_PROFILE_OK"
pass "Seatbelt profile includes profile-local runtime paths and not global Hermes"

out="$(env "${COMMON_ENV[@]}" python3 - <<'PY'
from pathlib import Path
import os
import subprocess
import sys

sys.path.insert(0, "scripts")
import hermes_common as hc
import seatbelt

ok, detail = seatbelt.capability()
if not ok:
    print(f"SEATBELT_SQLITE_SKIPPED: {detail}")
    raise SystemExit(0)

workspace = Path(os.environ["OMP_GUARD_ALLOWED_ROOT"]) / "projects" / "probe"
paths = hc.ensure_profile_dirs("chief-of-staff")
profile = seatbelt.build_profile(
    workspace=workspace,
    state_dir=paths["root"],
    tmp_dir=paths["tmp"],
    proxy_port=None,
    extra_write_paths=hc.profile_local_runtime_paths("chief-of-staff"),
)
code = """
from pathlib import Path
import os
import sqlite3
path = Path(os.environ['XDG_STATE_HOME']) / 'seatbelt-sqlite-test.db'
conn = sqlite3.connect(path)
conn.execute('create table if not exists t(x text)')
conn.execute('insert into t values (?)', ('ok',))
conn.commit()
conn.close()
print('SQLITE_OK')
"""
env = dict(os.environ)
env.update(
    {
        "HERMES_HOME": str(paths["root"]),
        "HOME": str(paths["home"]),
        "XDG_STATE_HOME": str(paths["state"]),
        "TMPDIR": str(paths["tmp"]),
    }
)
cmd = seatbelt.wrap_command(profile=profile, argv=[sys.executable, "-c", code])
result = subprocess.run(cmd, cwd=str(workspace), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
if result.returncode != 0:
    print(result.stdout)
    print(result.stderr, file=sys.stderr)
    raise SystemExit(result.returncode)
if "SQLITE_OK" not in result.stdout:
    raise SystemExit(f"unexpected sqlite probe output: {result.stdout!r}")
print("SEATBELT_SQLITE_OK")
PY
)"
assert_contains "$out" "SEATBELT_"
pass "conditional Seatbelt SQLite create check passes or skips"

set +e
out="$(env "${COMMON_ENV[@]}" python3 scripts/hermes-profile-doctor.py ../bad 2>&1)"
code="$?"
set -e
[ "$code" -ne 0 ] || fail "unsafe profile name unexpectedly passed"
assert_contains "$out" "unsafe Hermes profile name"
pass "unsafe profile name is rejected"

out="$(
  (
    cd "$TMP_ROOT/projects/probe"
    env "${COMMON_ENV[@]}" python3 "$ROOT/scripts/hermes-light-launch.py" --profile chief-of-staff --version
  ) 2>&1
)"
assert_contains "$out" "FAKE_HERMES_OK"
pass "hermes-light launches under profile-scoped env with fake Hermes binary"

launch_log="$TMP_ROOT/.omp-guard-logs/hermes-launch.log"
[ -f "$launch_log" ] || fail "missing Hermes launch log: $launch_log"
log_text="$(cat "$launch_log")"
assert_contains "$log_text" "profile=chief-of-staff"
assert_contains "$log_text" "seatbelt=off"
assert_contains "$log_text" "xdg_state_home=$TMP_ROOT/hermes/profiles/chief-of-staff/state"
assert_contains "$log_text" "github_tokens_scrubbed=GITHUB_TOKEN,GH_TOKEN"
assert_contains "$log_text" "runtime_read_paths=$TMP_ROOT/bin,$TMP_ROOT/runtime/hermes-agent"
assert_contains "$log_text" "runtime_write_paths=$TMP_ROOT/hermes/profiles/chief-of-staff"
pass "Hermes launch log captures Stage A runtime evidence"

set +e
out="$(env "${COMMON_ENV[@]}" python3 scripts/hermes-light-launch.py --profile chief-of-staff --version 2>&1)"
code="$?"
set -e
[ "$code" -ne 0 ] || fail "launcher unexpectedly allowed cwd outside AgentWork/projects"
assert_contains "$out" "refusing to launch outside AgentWork"
pass "hermes-light refuses cwd outside AgentWork/projects"

out="$(env "${COMMON_ENV[@]}" python3 scripts/install-shims.py --bin-dir "$TMP_ROOT/bin")"
assert_contains "$out" "hermes-light"
assert_contains "$out" "hermes-profile-doctor"
pass "install-shims includes Hermes commands"

out="$(env "${COMMON_ENV[@]}" python3 scripts/install-shims.py --bin-dir "$TMP_ROOT/bin" --check)"
assert_contains "$out" "OK: hermes-light"
assert_contains "$out" "OK: hermes-doctor"
pass "Hermes command shims validate"

echo "All Hermes guard smoke tests passed."
