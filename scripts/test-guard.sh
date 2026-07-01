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

assert_exit_code() {
  local actual="$1"
  local expected="$2"
  local label="$3"

  if [ "$actual" -ne "$expected" ]; then
    fail "$label returned exit code $actual, expected $expected"
  fi
}

python3 scripts/validate-policy.py >/dev/null
pass "policy validates"

out="$(./omp-guard validate-policy)"
assert_contains "$out" "policy validation passed"
pass "entrypoint validates policy"

out="$(./omp-guard classify "git status --short")"
assert_contains "$out" "decision=allow"
pass "classifies git status as allow"

out="$(./omp-guard classify "git push origin main")"
assert_contains "$out" "decision=ask"
pass "classifies git push as ask"

out="$(./omp-guard classify "sudo rm -rf /")"
assert_contains "$out" "decision=block"
pass "classifies destructive sudo rm as block"

TMP_LOG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/omp-guard-test.XXXXXX")"
trap 'rm -rf "$TMP_LOG_DIR"' EXIT

out="$(env OMP_GUARD_LOG_DIR="$TMP_LOG_DIR" ./omp-guard run --dry-run -- "git status --short")"
assert_contains "$out" "decision=allow"
pass "dry-run allow command succeeds"

set +e
out="$(env OMP_GUARD_LOG_DIR="$TMP_LOG_DIR" ./omp-guard run --dry-run -- "git push origin main" 2>&1)"
code="$?"
set -e
assert_exit_code "$code" 20 "ask command without approval"
assert_contains "$out" "decision=ask"
assert_contains "$out" "ask-classified command refused"
pass "ask command is refused without approval"

out="$(env OMP_GUARD_LOG_DIR="$TMP_LOG_DIR" ./omp-guard run --approve-ask --dry-run -- "git push origin main")"
assert_contains "$out" "decision=ask"
pass "ask command can be dry-run approved"

set +e
out="$(env OMP_GUARD_LOG_DIR="$TMP_LOG_DIR" ./omp-guard run -- "sudo rm -rf /" 2>&1)"
code="$?"
set -e
assert_exit_code "$code" 10 "blocked command"
assert_contains "$out" "decision=block"
assert_contains "$out" "blocked command refused"
pass "blocked command is refused"

[ -s "$TMP_LOG_DIR/commands.log" ] || fail "commands.log was not created"

grep -Fq '"decision": "allow"' "$TMP_LOG_DIR/commands.log" || fail "commands.log missing allow decision"
grep -Fq '"decision": "ask"' "$TMP_LOG_DIR/commands.log" || fail "commands.log missing ask decision"
grep -Fq '"decision": "block"' "$TMP_LOG_DIR/commands.log" || fail "commands.log missing block decision"

pass "commands are logged as JSON Lines"

echo "All guard tests passed."
