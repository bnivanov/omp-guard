
# omp-guard — Oh My Pi Agent Guard

Run the [omp coding agent](https://omp.sh) (oh-my-pi) safely on a dedicated
macOS work account, with layered guard rails: macOS account separation, an
AgentWork path boundary, a **Tier 0 macOS Seatbelt sandbox + domain-allowlist
egress proxy** for daily low-RAM use, and an optional high-isolation Docker sbx
microVM for untrusted work.

> **Provenance.** `omp-guard` is forked from / derived from
> [`mikeatlas/omp-sbx`](https://github.com/mikeatlas/omp-sbx), which wrapped omp
> in a Docker sbx sandbox. omp-guard keeps that high-isolation backend but
> re-centers on a low-RAM, macOS-native default (Seatbelt + egress proxy) plus
> command policy, launch logging, and multi-backend guard tooling.

---

## New here? Start with this

**What is this?** A safety wrapper for running AI coding agents on your Mac.
It lets an agent do real work in a folder you choose, while stopping it from
reading your private files (SSH keys, passwords, other projects) or sending
your data to random places on the internet — even if the agent is tricked by a
malicious prompt.

**What you need first:**
- A Mac (Apple Silicon recommended).
- Python 3 (comes with macOS, or install via `brew install python`).
- The `omp` agent itself — install from [omp.sh](https://omp.sh). (If you skip
  this, the installer still runs and tells you to add it later.)
- For the high-isolation `docker-sbx` backend only: Docker sbx
  (`brew install docker/tap/sbx`). Not needed for daily light mode.

**Before you install: set up a separate macOS account for agent work.**

OMP and coding agents can read files, run shell commands, install packages,
and access credentials. Running them in your personal Mac account puts your
iCloud data, SSH keys, browser sessions, and personal documents at risk.

Before installing omp-guard, you should:

1. **Create a separate Standard macOS user account** for agent work (not an
   Administrator). This is the account where you'll install and run omp-guard.
2. **Do not sign the agent account into Apple Account / iCloud.** No iCloud
   Drive, no synced Desktop/Documents, no Messages, no Photos.
3. **Do not copy personal config** (`~/.ssh`, `~/.config`, `~/.omp`,
   `~/.claude`, browser profiles, API keys) from your personal account into
   the agent account. Start fresh.
4. **Review app permissions** in your personal account: revoke unnecessary
   Full Disk Access, Accessibility, Screen Recording, and Files & Folders
   access from terminal and agent apps.
5. **Disable remote access** (Remote Login, File Sharing, Screen Sharing) in
   your personal account unless you deliberately need them.

This creates the first and most important security boundary: the macOS
account boundary. omp-guard adds additional layers on top (path guards,
sandbox, network allowlist), but the account separation is foundational.

For the full step-by-step guide with checklists, see
[`docs/macOS-account-setup.md`](docs/macOS-account-setup.md).

**Install in one command:**

```bash
git clone https://github.com/bnivanov/omp-guard.git ~/AgentWork/omp-guard
cd ~/AgentWork/omp-guard
./install.sh
```

The installer checks your system, sets up a safe work area at `~/AgentWork`,
installs the commands, turns on fail-closed sandboxing, and runs a health
check — explaining each step in plain language. It's safe to run again.

**Then, in a new terminal:**

```bash
cd ~/AgentWork/projects
omp-guard          # opens a friendly menu — start here
```

That's it. The menu walks you through creating a project and launching the
agent safely. Everything below is reference detail you don't need on day one.

## What it does

- Refuses to launch outside the Agent Lab workspace by default: `~/AgentWork`
- Blocks launches from personal, shared, iCloud, and hidden credential/config paths
- Logs each launcher invocation to `~/AgentWork/.omp-guard-logs/launch.log`
- Defines guard policy in `policies/default.yml` for allowed roots, denied paths, sensitive commands, and blocked patterns
- Validates the default policy with `scripts/validate-policy.py`
- Classifies commands with `scripts/classify-command.py` as allow, ask, or block
- Runs commands through `scripts/guard-run.py`, enforcing allow/ask/block decisions and logging to `commands.log`
- Provides a top-level `./omp-guard` entrypoint for validation, classification, and guarded command execution
- Tests guard behavior with `scripts/test-guard.sh`
- Checks pre-launch readiness with `./omp-guard doctor`
- Exposes a narrow MCP server with `./omp-guard mcp-server`
- Provides daily low-RAM launch mode with `./omp-light` — on macOS this runs
  under a **Tier 0 Seatbelt sandbox + domain-allowlist egress proxy**
  (deny-by-default filesystem confined to the workspace, network limited to an
  allowlist), at ~0 RAM overhead. See [`docs/security-models.md`](docs/security-models.md) §5a.
- Records backend choice with `./omp-guard setup`
- Explains the security model with `./omp-guard security` and [`docs/security-models.md`](docs/security-models.md)
- Launches omp inside a Docker sbx microVM for the high-isolation backend, using sbx controls such as non-root user, network policies, secret proxy, and resource limits
- Bind-mounts guard-scoped OMP state from `~/AgentWork/.omp-guard-state` so sandbox state persists without exposing your normal `~/.omp`
- Sandboxes are per-directory: running from the same cwd reconnects to the same sandbox
- Recovers automatically after a force-quit: if the sandbox is left stopped (or its agent wedged), the launcher re-attaches, then stops+restarts, and as a last resort recreates the sandbox — your omp session resumes from the shared `~/.omp` either way
- `--new` flag forces a fresh sandbox


## Manual install (advanced)

Most people should use `./install.sh` (see [New here?](#new-here-start-with-this)).
These are the equivalent steps done by hand:

```bash
git clone https://github.com/bnivanov/omp-guard.git ~/AgentWork/omp-guard
cd ~/AgentWork/omp-guard

# Install command shims (omp-guard, omp-light, omp-sbx) into ~/AgentWork/bin
./omp-guard install-shims
export PATH="$HOME/AgentWork/bin:$PATH"   # add to ~/.zshrc

# Recommended: fail-closed Seatbelt (refuse to launch if it can't enforce)
echo 'export OMP_GUARD_SEATBELT=require' >> ~/.zshrc

# Alias omp to always go through the guard (daily light mode)
echo "alias omp='omp-light'" >> ~/.zshrc

# Only if you use the high-isolation backend: build the sbx template image
./build.sh
```

## Usage

```bash
omp-guard              # open the plain-text interactive launcher
omp-guard security     # explain security models and docs path
omp-guard status       # show current guard/workspace status
omp-light              # start daily low-RAM mode directly
omp-sbx                # start high-isolation Docker/sbx mode directly
omp-sbx --new          # destroy + create a fresh sandbox
omp-sbx --yes          # skip the pre-launch "press any key" pause
```

Real work should happen under `~/AgentWork/projects/<project>`. Do not start OMP from the `omp-guard` tooling repo or from the `~/AgentWork` estate root.

## Security model

Read [`docs/macOS-account-setup.md`](docs/macOS-account-setup.md) for the foundational step (creating a separate macOS account), and [`docs/security-models.md`](docs/security-models.md) for the full omp-guard security model: AgentWork estate, guard-scoped HOME/state, command policy, launch logs, shims, GitHub auth, and when to choose `light`, `docker-sbx`, or `native-mac`.

```bash
omp-guard security
```

The summary command prints the current estate root, state directory, available backends, short backend descriptions, and the documentation path.

## How it works

| Component | File | Purpose |
|---|---|---|
| Template | `sbx-kit/Dockerfile` | Extends `docker/sandbox-templates:shell-nightly` with omp binary + dev tools |
| Kit | `sbx-kit/spec.yaml` | Defines omp entrypoint, network allow-list, env, agent context |
| Launcher | `omp-sbx` | Wrapper handling banner, sandbox lifecycle, resume vs new |
| Parallel | `omp-sbx-parallel` | Git worktree-based parallel sandbox launcher |
| Browser CLI | `sbx-kit/Dockerfile` | Installs `agent-browser` (replaces Puppeteer, which can't spawn in sbx) |

### Config sharing

sbx mounts additional workspaces at their **host path** inside the container (e.g. `/Users/<user>/.omp`). The kit's startup command symlinks this to `/home/agent/.omp` so omp's `PI_CONFIG_DIR=.omp` resolves correctly.

### GitHub auth forwarding

GitHub authentication is intentionally **not** forwarded. The `omp-sbx`
launcher mounts **only** the guard-scoped state (`OMP_GUARD_STATE`,
`~/AgentWork/.omp-guard-state`) into the sandbox — it does **not** bind-mount
`~/.config/gh`, and it records `github_auth_mounted=no` in the launch log. The
kit startup command (`sbx-kit/spec.yaml`) does not configure a `gh` credential
helper.

Public GitHub reads work unauthenticated. For private repo access, pushes, PRs,
issues, or comments inside the sandbox, provision a **separate, agent-specific
GitHub credential** (a scoped PAT or a dedicated deploy key) inside the sandbox
— never the host's personal `~/.config/gh` token. This keeps agent sessions
from silently inheriting your personal write credentials.

`github.com:443` is in the sandbox network allow-list (`sbx-kit/spec.yaml`), so
an explicitly-provisioned credential can reach GitHub.

### LSP servers

The template ships with language servers for Python (`pyright`), TypeScript/JavaScript (`typescript-language-server`), Bash (`bash-language-server`), and Go (`gopls`).

**Two-part setup, split by concern:**

| Part | Location | Rebuild needed? |
|---|---|---|
| Binary install | `sbx-kit/Dockerfile` (the `LSP servers` section) | Yes — `./build.sh` |
| Server registration | `~/.omp/lsp.yml` on the host | No — live via `~/.omp` bind mount |

`lsp.yml` is bind-mounted into the sandbox, so editing it takes effect immediately on the next session. Adding or changing a *binary* requires a rebuild + `omp --new`.

#### Lazy loading

omp starts LSP servers **lazily**, keyed on `fileTypes` matching actual files in the open workspace. A server only activates for workspaces that contain a file whose extension matches one of its `fileTypes`. The message *“No language servers configured for this project”* (from `lsp status`) means **no file in the workspace matched** any server's `fileTypes` — not that the config is missing.

`rootMarkers` (`.git`, `go.mod`, `package.json`) set the project root but do **not** start a server by themselves; a matching file type is also required.

#### Adding a server

1. Install the binary in `sbx-kit/Dockerfile` — append to the global `npm install` line for npm packages, or add a separate `RUN` step for non-npm servers (`go install`, `cargo install`, etc.).
2. Register the server in `~/.omp/lsp.yml`:
   ```yaml
     gopls:
       command: gopls
       args: ["serve"]
       fileTypes: [".go"]
       rootMarkers:
         - "go.mod"
         - ".git"
   ```
3. Rebuild + load (`./build.sh`), then start a fresh sandbox (`omp --new`).

### Browser automation (agent-browser)

The omp `browser` tool (Puppeteer/Chromium) **cannot spawn inside the sbx microVM** — the bundled `chrome-linux64` binary fails with `ENOEXEC`. The template instead ships [`agent-browser`](https://github.com/vercel-labs/agent-browser), a native Rust CLI. Chrome for Testing has no Linux ARM64 builds, so the template installs `chromium-browser` via apt and points agent-browser at it via `AGENT_BROWSER_EXECUTABLE_PATH`.

```bash
agent-browser open https://example.com      # launch + navigate
agent-browser snapshot                       # accessibility tree with @eN refs
agent-browser click @e2                      # click by ref
agent-browser fill @e3 "text"                # fill input
agent-browser screenshot page.png            # capture
agent-browser close
```

For **static content** (articles, docs, GitHub issues/PRs, JSON, PDFs) no browser is needed — the omp `read` tool fetches clean text/markdown from a URL directly. Reach for `agent-browser` only when JS execution or interaction is required.

Changing the `agent-browser` version or system Chromium requires a rebuild (`./build.sh`) + `omp --new`.

### Security

For the `omp-sbx` backend, isolation is provided by the sbx microVM controls rather than by manual `cap_drop`, `gosu`, `umask`, or read-only rootfs configuration:

| Control | sbx |
|---|---|
| Isolation | MicroVM with separate kernel |
| Non-root user | Built-in `agent` UID 1000 |
| Network | Policy-based allow-list |
| Secrets | Proxy injects keys (never enter sandbox) |
| Resource limits | `sbx run --memory --cpus` |

## Parallel sessions (git worktrees)

`omp-sbx-parallel` creates a git worktree on a separate branch and launches a dedicated sandbox for it. Run it multiple times to work on multiple tasks in parallel — each gets its own worktree, branch, and sandbox.

```bash
omp-sbx-parallel                          # interactive: pick existing branch or create new
omp-sbx-parallel --new fix-auth-bug       # create new branch + worktree + sandbox
omp-sbx-parallel --branch feature-x       # use existing branch in a new worktree
```

On exit (interactive mode), you're offered cleanup:
1. Merge the branch into your current branch and remove the worktree
2. Remove the worktree only (keep the branch)
3. Keep the worktree as-is

Worktrees are created as siblings of the repo root: `~/src/myproject@fix-auth-bug`

### VS Code worktree integration

`omp-sbx-parallel` maintains a multi-root `.code-workspace` file at the repo root (`<repo-name>.code-workspace`) so VS Code can display all active worktrees as named roots in one window. The file is gitignored (`*.code-workspace`) — it's machine-local, never committed.

**What happens automatically:**

| Event | `.code-workspace` action |
|---|---|
| Worktree created/reused | Worktree added as a named root |
| Cleanup: merge + remove | Root removed |
| Cleanup: remove only | Root removed |
| Cleanup: keep as-is | Root left in file |

**Folder naming:** main checkout is `<repo-name>`; each worktree is `<repo-name> <branch>`. This lets VS Code tasks pin cwd via `${workspaceFolder:<name>}`:

```json
{
  "label": "agent: feature-x",
  "type": "shell",
  "command": "omp-sbx-parallel --branch feature-x",
  "options": { "cwd": "${workspaceFolder:myrepo feature-x}" }
}
```

Requires `jq` on the host (silently skips if unavailable). For full agent instructions, see [`INSTRUCTIONS.md`](INSTRUCTIONS.md).

**VS Code settings:** enable `git.detectWorktrees` to auto-list all worktrees in Source Control, even ones created outside VS Code.

## Rebuild the docker-sbx image after omp upgrade

(Only relevant if you use the high-isolation `docker-sbx` backend.)

```bash
cd ~/AgentWork/omp-guard
./build.sh
```

## Policy validation

Run this before changing guard policy:

```bash
scripts/validate-policy.py
```

The validator is dependency-free. It checks that `policies/default.yml` still contains the required workspace, credential-path, command-policy, network, and logging sections.

## Command classification

Classify a proposed command against the default guard policy:

```bash
scripts/classify-command.py "git status --short"
scripts/classify-command.py "git push origin main"
scripts/classify-command.py "sudo rm -rf /"
```

The classifier does not execute commands. It only returns `allow`, `ask`, or `block` based on `policies/default.yml`.

## Guarded command runner

Run a command through the guard policy:

```bash
scripts/guard-run.py -- "git status --short"
scripts/guard-run.py -- "git push origin main"
scripts/guard-run.py --approve-ask -- "git push origin main"
scripts/guard-run.py -- "sudo rm -rf /"
```

The runner executes `allow` commands, refuses `block` commands, and refuses `ask` commands unless `--approve-ask` is supplied. Every decision is logged as JSON Lines to `~/AgentWork/.omp-guard-logs/commands.log`.

## Top-level entrypoint

Use the top-level executable for common guard operations:

```bash
./omp-guard                    # interactive launcher menu
./omp-guard menu               # explicit launcher menu
./omp-guard status             # concise guard/workspace status
./omp-guard security           # concise security-model summary
./omp-guard validate-policy
./omp-guard classify "git status --short"
./omp-guard run --dry-run -- "git status --short"
./omp-guard run --approve-ask --dry-run -- "git push origin main"
```

This is a convenience wrapper around the scripts in `scripts/`. With no arguments it opens the interactive launcher; named commands keep the existing non-interactive behavior. The interactive launcher prints a short explanation directly under each option.

## Guard tests

Run the regression tests before changing guard behavior:

```bash
scripts/test-guard.sh
```

The test script validates policy loading, command classification, guarded dry-runs, ask/refuse behavior, blocked command refusal, and JSON Lines command logging.

## Doctor check

Run this before launching OMP through the guard:

```bash
./omp-guard doctor
```

The doctor check verifies the AgentWork location, required files, executable permissions, policy validation, classifier behavior, guarded command behavior, log permissions, JSON Lines command logs, and key sandbox guard text.

## MCP server

Start the narrow MCP server over stdio:

```bash
./omp-guard mcp-server
```

Initial MCP tools are intentionally limited:

- `doctor`
- `validate_policy`
- `classify_command`
- `guarded_run_dry_run`

The MCP server does not expose unrestricted command execution. The only run tool is dry-run guarded execution.

In-session guard controls are not implemented in this PR. They will come later through MCP/custom command support rather than an in-OMP `/guard` slash command.

Run the MCP smoke test:

```bash
scripts/test-mcp-server.py
```

## Launch backends

`omp-guard` supports explicit launch backends:

- `light` — Daily low-RAM mode. On macOS, confined by the Tier 0 Seatbelt
  sandbox + egress proxy (see below). ~0 RAM overhead; scales to concurrent
  agents. Not VM-grade isolation.
- `docker-sbx` — High-isolation Docker/sbx mode. Use for risky repos, package installs, shell-heavy or untrusted work. High RAM.
- `native-mac` — Planned/experimental macOS-native sandbox mode. Do not treat as ready until doctor says available.

Configure the default backend:

```bash
./omp-guard setup --backend light
./omp-guard config
```

Daily launch:

```bash
omp-light
```

High-isolation launch:

```bash
omp-sbx
```

### Tier 0: light-mode Seatbelt sandbox (macOS)

On macOS, `omp-light` wraps `omp` in a deny-by-default Seatbelt profile
(`sandbox-exec`) plus a loopback **domain-allowlist egress proxy**:

- **Filesystem**: read/write confined to the current workspace + guard-scoped
  state; reads of other projects, the personal account, `~/.ssh`, and
  credential paths are denied by the kernel.
- **Network**: all outbound denied except the proxy, which permits only
  `network.allowedDomains` from `policies/default.yml` (model APIs only by
  default; GitHub/npm/PyPI are opt-in). Decisions log to
  `~/AgentWork/.omp-guard-logs/egress.log`.

Controls:

```bash
OMP_GUARD_SEATBELT=auto     omp-light   # default: enforce if capable, else warn
OMP_GUARD_SEATBELT=require  omp-light   # refuse to launch if not enforceable
OMP_GUARD_SEATBELT=off      omp-light   # disable Tier 0
```

`sandbox-exec` is deprecated-but-functional (same API Claude Code and Codex use
on macOS). Treat it as the low-RAM convenience layer; the durable boundaries
are account separation + egress control. **Re-verify enforcement after every
macOS update:**

```bash
scripts/seatbelt-selftest.py     # proves the boundary actually holds
./omp-guard doctor               # includes the self-test
```

Interactive launcher:

```bash
omp-guard
```

Run the light launcher smoke test:

```bash
scripts/test-light-launch.py
```
