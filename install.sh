#!/usr/bin/env bash
###############################################################################
# omp-guard installer — friendly, one-command setup.
#
#   ./install.sh
#
# What it does (and explains as it goes):
#   1. Checks you are on macOS with the tools omp-guard needs.
#   2. Creates your safe work area at ~/AgentWork (projects live here).
#   3. Installs short commands (omp-guard, omp-light, omp-sbx) you can run
#      from anywhere.
#   4. Adds them to your shell so they keep working in new terminals.
#   5. Turns on fail-closed sandboxing (won't run an agent unprotected).
#   6. Runs a health check so you know it worked.
#
# Safe to run more than once — it only fills in what's missing.
###############################################################################
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors only when writing to a real terminal.
if [ -t 1 ]; then
  B=$'\033[1m'; DIM=$'\033[2m'; GRN=$'\033[32m'; YEL=$'\033[33m'; RED=$'\033[31m'; CYN=$'\033[36m'; RST=$'\033[0m'
else
  B=''; DIM=''; GRN=''; YEL=''; RED=''; CYN=''; RST=''
fi

say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✓%s %s\n' "$GRN" "$RST" "$*"; }
warn() { printf '%s!%s %s\n' "$YEL" "$RST" "$*"; }
err()  { printf '%s✗%s %s\n' "$RED" "$RST" "$*" >&2; }
step() { printf '\n%s%s%s\n' "$B" "$*" "$RST"; }

# ── Options ──────────────────────────────────────────────────────────────────
NO_SHELL_EDIT=0
for arg in "$@"; do
  case "$arg" in
    --no-shell-edit) NO_SHELL_EDIT=1 ;;
    -h|--help)
      say "usage: ./install.sh [--no-shell-edit]"
      say "  --no-shell-edit   do not modify your ~/.zshrc or ~/.bashrc;"
      say "                    the script prints the lines to add yourself."
      say ""
      say "Before installing, set up a separate macOS account for agent work:"
      say "  1. Create a Standard (non-Admin) macOS user for agentic tools."
      say "  2. Do not sign it into Apple Account / iCloud."
      say "  3. Do not copy personal config (~/.ssh, ~/.config, ~/.omp) into it."
      say "  4. Review app permissions in your personal account (System Settings > Privacy & Security)."
      say "  5. Disable remote access (Remote Login, File Sharing, Screen Sharing)."
      say ""
      say "Full guide: docs/macOS-account-setup.md"
      ;;
    *) err "unknown option: $arg (try --help)"; exit 2 ;;
  esac
done

say "${B}${CYN}omp-guard installer${RST}"
say "${DIM}This sets up a safe place to run AI coding agents on your Mac.${RST}"
say ""
say "${B}Before you continue:${RST} omp-guard is designed to run from a"
say "${DIM}separate Standard macOS user account (not your personal account).${RST}"
say "${DIM}If you haven't set that up yet, see docs/macOS-account-setup.md${RST}"
say "${DIM}or run this installer with --help for a quick summary.${RST}"
say ""
# ── 1. Prerequisite checks ───────────────────────────────────────────────────
step "1/6  Checking your system"

FATAL=0

# macOS?
if [ "$(uname -s)" != "Darwin" ]; then
  warn "You are not on macOS. omp-guard's Seatbelt sandbox is macOS-only."
  warn "It will still install, but daily 'light' mode will run WITHOUT the sandbox."
else
  ok "macOS detected"
  # Seatbelt present? (deprecated but functional — this is what confines light mode)
  if [ -x /usr/bin/sandbox-exec ]; then
    ok "macOS sandbox (sandbox-exec) is available"
  else
    warn "sandbox-exec not found — light mode will run without the sandbox layer"
  fi
fi

# Python 3?
if command -v python3 >/dev/null 2>&1; then
  ok "Python 3 found ($(python3 --version 2>&1))"
else
  err "Python 3 is required but was not found."
  say "   Install it the easy way with Homebrew:"
  say "     ${CYN}/bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"${RST}"
  say "     ${CYN}brew install python${RST}"
  FATAL=1
fi

# omp CLI? (the agent itself — not bundled here)
if command -v omp >/dev/null 2>&1; then
  ok "omp coding agent found ($(command -v omp))"
else
  warn "The 'omp' coding agent is not installed yet."
  say  "   omp-guard runs omp safely, but you install omp separately."
  say  "   Get it from: ${CYN}https://omp.sh${RST}"
  say  "   You can finish this installer now and install omp afterward —"
  say  "   the guard will find it automatically once it's on your PATH."
fi

if [ "$FATAL" -eq 1 ]; then
  err "Please install the missing required tools above, then run ./install.sh again."
  exit 1
fi

# ── 2. Create the work area ──────────────────────────────────────────────────
step "2/6  Creating your work area"

AGENTWORK="${OMP_GUARD_ALLOWED_ROOT:-$HOME/AgentWork}"
mkdir -p "$AGENTWORK/projects"
ok "Work area ready: $AGENTWORK"
say "   ${DIM}Your projects go in $AGENTWORK/projects/<name>. Agents are only${RST}"
say "   ${DIM}allowed to run from inside this folder.${RST}"

# ── 3. Install the short commands (shims) ────────────────────────────────────
step "3/6  Installing commands (omp-guard, omp-light, omp-sbx)"

python3 "$REPO_DIR/scripts/install-shims.py" >/dev/null
BIN_DIR="$AGENTWORK/bin"
ok "Commands installed in $BIN_DIR"

# ── Detect personal user for security enforcement ──────────────────────────
# OMP_GUARD_PERSONAL_HOME must be set for the guard to protect your personal
# files. We try to auto-detect it from the console user (the person logged
# into the Mac's GUI). If that fails, we fall back to $HOME and warn.
PERSONAL_HOME="${OMP_GUARD_PERSONAL_HOME:-}"
if [ -z "$PERSONAL_HOME" ]; then
  CONSOLE_USER=$(stat -f %Su /dev/console 2>/dev/null || echo "")
  if [ -n "$CONSOLE_USER" ] && [ "$CONSOLE_USER" != "$(whoami)" ]; then
    PERSONAL_HOME="/Users/$CONSOLE_USER"
    ok "Detected personal account: $CONSOLE_USER"
  elif [ -n "$CONSOLE_USER" ] && [ "$CONSOLE_USER" = "$(whoami)" ]; then
    PERSONAL_HOME="/Users/$CONSOLE_USER"
    warn "Console user is the same as the current user ($CONSOLE_USER)."
    warn "If this is your agent account, set OMP_GUARD_PERSONAL_HOME manually"
    warn "to your personal account's home (e.g. /Users/yourname) after install."
  else
    PERSONAL_HOME="$HOME"
    warn "Could not detect console user. Using $HOME as OMP_GUARD_PERSONAL_HOME."
    warn "If this is your agent account, set OMP_GUARD_PERSONAL_HOME manually"
    warn "to your personal account's home (e.g. /Users/yourname) after install."
  fi
fi
say "   ${DIM}OMP_GUARD_PERSONAL_HOME=${PERSONAL_HOME}${RST}"

# ── 4. Wire up your shell ────────────────────────────────────────────────────
step "4/6  Adding the commands to your shell"

RC_LINES=(
  "export PATH=\"$BIN_DIR:\$PATH\""
  'export OMP_GUARD_SEATBELT=require'
  "alias omp='omp-light'"
  "export OMP_GUARD_PERSONAL_HOME=\"$PERSONAL_HOME\""
)
# Set OMP_GUARD_WORK_USER to the current user so light-launch.py knows which
# account is expected. Auto-detected at install time; user can override later.
WORK_USER="${OMP_GUARD_WORK_USER:-$(whoami)}"
RC_LINES+=("export OMP_GUARD_WORK_USER=\"$WORK_USER\"")

if [ "$NO_SHELL_EDIT" -eq 1 ]; then
  warn "Skipping shell edit (--no-shell-edit). Add these lines yourself:"
  for line in "${RC_LINES[@]}"; do
    say "   ${CYN}$line${RST}"
  done
else
  # Pick the right shell config file.
  SHELL_NAME="$(basename "${SHELL:-/bin/zsh}")"
  case "$SHELL_NAME" in
    zsh)  RC="$HOME/.zshrc" ;;
    bash) RC="$HOME/.bashrc" ;;
    *)    RC="$HOME/.zshrc" ;;
  esac
  touch "$RC"

  add_line() {
    local line="$1"
    if grep -qF "$line" "$RC" 2>/dev/null; then
      say "   ${DIM}already set: $line${RST}"
    else
      printf '\n# added by omp-guard install.sh\n%s\n' "$line" >> "$RC"
      ok "added to $RC: $line"
    fi
  }

  for line in "${RC_LINES[@]}"; do
    add_line "$line"
  done
fi

step "5/6  Safety default"
ok "Fail-closed sandbox enabled (OMP_GUARD_SEATBELT=require)"
say "   ${DIM}Agents won't launch at all if the sandbox can't protect you.${RST}"

# ── 6. Health check ──────────────────────────────────────────────────────────
step "6/6  Running a health check"
say "${DIM}(this verifies the sandbox actually works on your Mac)${RST}"
set +e
python3 "$REPO_DIR/scripts/doctor.py" | grep -iE 'seatbelt|errors:|FAIL' || true
set -e

# ── Done ─────────────────────────────────────────────────────────────────────
step "${GRN}Done!${RST}"
if [ "$NO_SHELL_EDIT" -eq 1 ]; then
  say "Add the lines shown above to your shell config, open a new terminal, then:"
else
  say "Open a new terminal (or run: ${CYN}source $RC${RST}), then:"
fi
say ""
say "  ${CYN}cd $AGENTWORK/projects${RST}"
say "  ${CYN}omp-guard${RST}          ${DIM}# friendly menu — start here${RST}"
say ""
say "Or jump straight in from a project folder:"
say "  ${CYN}omp-light${RST}          ${DIM}# daily, sandboxed, low-RAM${RST}"
say ""
if ! command -v omp >/dev/null 2>&1; then
  warn "Reminder: install the omp agent from https://omp.sh before your first run."
fi
