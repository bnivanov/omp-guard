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

assert_not_contains() {
  local haystack="$1"
  local needle="$2"

  if printf '%s\n' "$haystack" | grep -Fq "$needle"; then
    echo "$haystack" >&2
    fail "expected output not to contain: $needle"
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
TMP_ROOT="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$TMP_ROOT")"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p \
  "$TMP_ROOT/projects/probe" \
  "$TMP_ROOT/personal" \
  "$TMP_ROOT/bin" \
  "$TMP_ROOT/runtime/hermes-agent" \
  "$TMP_ROOT/home/.hermes/hermes-agent"
chmod 700 "$TMP_ROOT/home" "$TMP_ROOT/home/.hermes"
touch "$TMP_ROOT/home/.hermes/config.yaml" "$TMP_ROOT/home/.hermes/state.db"

cat > "$TMP_ROOT/bin/fake-hermes" <<'INNER'
#!/usr/bin/env bash
set -euo pipefail

for key in HERMES_HOME HOME TMPDIR HERMES_GUARD_PROFILE HERMES_GUARD_POLICY_EFFECTIVE; do
  if [ -z "${!key:-}" ]; then
    echo "missing $key" >&2
    exit 88
  fi
done

[ "$HERMES_GUARD_PROFILE" = "chief-of-staff" ] || { echo "unexpected profile: $HERMES_GUARD_PROFILE" >&2; exit 88; }
[ "$HOME" = "$TEST_HOME" ] || { echo "HOME not canonical account home: $HOME" >&2; exit 88; }
[ "$HERMES_HOME" = "$TEST_HOME/.hermes" ] || { echo "HERMES_HOME not canonical account Hermes home: $HERMES_HOME" >&2; exit 88; }

for key in XDG_CONFIG_HOME XDG_CACHE_HOME XDG_DATA_HOME XDG_STATE_HOME; do
  value="${!key:-}"
  case "$value" in
    *hermes/profiles/chief-of-staff*)
      echo "$key leaked old profile-local path: $value" >&2
      exit 88
      ;;
  esac
done

for token_key in GITHUB_TOKEN GH_TOKEN GITHUB_PAT COPILOT_GITHUB_TOKEN OPENAI_API_KEY ANTHROPIC_API_KEY OPENROUTER_API_KEY OPENCODE_API_KEY OPENCODE_GO_API_KEY; do
  if [ "${!token_key+x}" = "x" ]; then
    echo "token leaked to Hermes process: $token_key" >&2
    exit 88
  fi
done

printf 'FAKE_HERMES_OK\n'
INNER
chmod 700 "$TMP_ROOT/bin/fake-hermes"

COMMON_ENV=(
  "HOME=$TMP_ROOT/home"
  "TEST_HOME=$TMP_ROOT/home"
  "OMP_GUARD_ALLOWED_ROOT=$TMP_ROOT"
  "OMP_GUARD_PERSONAL_HOME=$TMP_ROOT/personal"
  "HERMES_GUARD_HERMES_BIN=$TMP_ROOT/bin/fake-hermes"
  "HERMES_GUARD_RUNTIME_DIR=$TMP_ROOT/runtime/hermes-agent"
  "HERMES_GUARD_SEATBELT=off"
  "GITHUB_TOKEN=do-not-forward"
  "GH_TOKEN=do-not-forward"
  "OPENAI_API_KEY=do-not-forward"
  "ANTHROPIC_API_KEY=do-not-forward"
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
pass "profile doctor still validates profile identity directories"

out="$(env "${COMMON_ENV[@]}" python3 - <<'PY'
from pathlib import Path
import os
import sys

sys.path.insert(0, "scripts")
import hermes_common as hc

canonical, _ = hc.validate_canonical_hermes_home(Path(os.environ["HOME"]))
expected = Path(os.environ["HOME"]) / ".hermes"
if canonical != expected.resolve():
    raise SystemExit(f"unexpected canonical home: {canonical}")
log_dir = hc.ensure_guard_log_dir()
tmp_dir = hc.ensure_guard_tmp_dir()
for path in (canonical, log_dir, tmp_dir):
    if not path.exists():
        raise SystemExit(f"missing canonical Stage A path: {path}")
print("CANONICAL_STAGE_A_PATHS_OK")
PY
)"
assert_contains "$out" "CANONICAL_STAGE_A_PATHS_OK"
pass "canonical Hermes home and guard runtime paths validate"

out="$(env "${COMMON_ENV[@]}" python3 - <<'PY'
from pathlib import Path
import os
import sys

sys.path.insert(0, "scripts")
import hermes_common as hc
import seatbelt

workspace = Path(os.environ["OMP_GUARD_ALLOWED_ROOT"]) / "projects" / "probe"
canonical, _ = hc.validate_canonical_hermes_home(Path(os.environ["HOME"]))
tmp_dir = hc.ensure_guard_tmp_dir()
log_dir = hc.ensure_guard_log_dir()
profile = seatbelt.build_profile(
    workspace=workspace,
    state_dir=canonical,
    tmp_dir=tmp_dir,
    proxy_port=12345,
    extra_read_paths=[Path(os.environ["HERMES_GUARD_RUNTIME_DIR"])],
    extra_write_paths=hc.canonical_runtime_write_paths(canonical, tmp_dir, log_dir),
)
required = [
    "(allow file-ioctl)",
    str(workspace),
    str(canonical),
    str(tmp_dir),
    str(log_dir),
    str(Path(os.environ["HERMES_GUARD_RUNTIME_DIR"])),
]
for needle in required:
    if needle not in profile:
        raise SystemExit(f"missing Seatbelt rule for {needle}")
for forbidden in (
    f'(subpath "{Path(os.environ["HOME"])}")',
    f'(subpath "{Path(os.environ["OMP_GUARD_ALLOWED_ROOT"])}")',
    f'(subpath "{Path(os.environ["OMP_GUARD_ALLOWED_ROOT"]) / "personal"}")',
):
    if forbidden in profile:
        raise SystemExit(f"Seatbelt profile unexpectedly grants broad path: {forbidden}")
print("SEATBELT_CANONICAL_PROFILE_OK")
PY
)"
assert_contains "$out" "SEATBELT_CANONICAL_PROFILE_OK"
pass "Seatbelt profile allows canonical ~/.hermes but not broad account/root paths"

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
pass "hermes-light launches fake Hermes with canonical account home"

central_launch_log="$TMP_ROOT/.omp-guard-logs/hermes-launch.log"
profile_launch_log="$TMP_ROOT/hermes/profiles/chief-of-staff/logs/hermes-launch.log"
[ -f "$central_launch_log" ] || fail "missing central Hermes launch log: $central_launch_log"
[ -f "$profile_launch_log" ] || fail "missing profile-local Hermes launch log: $profile_launch_log"
for launch_log in "$central_launch_log" "$profile_launch_log"; do
  log_text="$(cat "$launch_log")"
  assert_contains "$log_text" "profile=chief-of-staff"
  assert_contains "$log_text" "home_mode=canonical-hermes-home"
  assert_contains "$log_text" "seatbelt=off"
  assert_contains "$log_text" "home=$TMP_ROOT/home"
  assert_contains "$log_text" "hermes_home=$TMP_ROOT/home/.hermes"
  assert_contains "$log_text" "xdg_state_home=(unset)"
  assert_contains "$log_text" "tokens_scrubbed=GITHUB_TOKEN,GH_TOKEN,OPENAI_API_KEY,ANTHROPIC_API_KEY"
  assert_contains "$log_text" "runtime_read_paths=$TMP_ROOT/bin,$TMP_ROOT/runtime/hermes-agent,$TMP_ROOT/home/.hermes/hermes-agent"
  assert_contains "$log_text" "$TMP_ROOT/.omp-guard-logs"
  assert_contains "$log_text" "$TMP_ROOT/.omp-guard-tmp/hermes-light"
done
pass "Hermes launch logs capture canonical Stage A runtime evidence"

out="$(env "${COMMON_ENV[@]}" python3 scripts/hermes-doctor.py)"
assert_contains "$out" "canonical Hermes home is exactly $TMP_ROOT/home/.hermes"
assert_contains "$out" "central Hermes launch log is writable"
pass "hermes-doctor validates canonical Hermes home and central launch log"

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
