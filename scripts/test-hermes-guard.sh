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

for policy in policies/hermes-v1.yml policies/hermes-orchestrator.yml policies/hermes-research.yml policies/hermes-dev.yml; do
  python3 scripts/validate-policy.py "$policy" >/dev/null
  pass "policy validates: $policy"
done

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/hermes-guard-test.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/projects/probe" "$TMP_ROOT/personal"

COMMON_ENV=(
  "OMP_GUARD_ALLOWED_ROOT=$TMP_ROOT"
  "OMP_GUARD_PERSONAL_HOME=$TMP_ROOT/personal"
  "HERMES_GUARD_HERMES_BIN=/usr/bin/true"
  "HERMES_GUARD_SEATBELT=off"
)

out="$(env "${COMMON_ENV[@]}" python3 scripts/hermes-profile-doctor.py chief-of-staff --init)"
assert_contains "$out" "OK: profile initialized"
pass "profile doctor initializes chief-of-staff"

out="$(env "${COMMON_ENV[@]}" python3 scripts/hermes-profile-doctor.py chief-of-staff)"
assert_contains "$out" "errors: 0"
pass "profile doctor validates chief-of-staff"

set +e
out="$(env "${COMMON_ENV[@]}" python3 scripts/hermes-profile-doctor.py ../bad 2>&1)"
code="$?"
set -e
[ "$code" -ne 0 ] || fail "unsafe profile name unexpectedly passed"
assert_contains "$out" "unsafe Hermes profile name"
pass "unsafe profile name is rejected"

(
  cd "$TMP_ROOT/projects/probe"
  env "${COMMON_ENV[@]}" python3 "$ROOT/scripts/hermes-light-launch.py" --profile chief-of-staff --version
)
pass "hermes-light launches under profile-scoped env with fake Hermes binary"

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
