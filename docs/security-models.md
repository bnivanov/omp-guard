# omp-guard security models

`omp-guard` is a set of guard rails for running agentic coding tools on a dedicated macOS work estate. It is not one single sandbox. It combines macOS account separation, an AgentWork path boundary, guard-scoped OMP state, command classification, logging, shims, and multiple launch backends.

The short version:

- Use `omp-light` for normal trusted work when low RAM matters.
- Use `omp-sbx` for risky or unfamiliar work when stronger isolation is worth the RAM/CPU cost.
- Treat `native-mac` as planned/experimental until `omp-guard doctor` says it is available.
- Work under `~/AgentWork/projects/<project>`.
- Do not work from `~/AgentWork` itself, from the `omp-guard` repo, or from the personal macOS account.

## 1. Core threat model

`omp-guard` is designed to reduce risk from agentic tools and the workflows around them:

- prompt injection that convinces an agent to read, exfiltrate, or mutate files outside the intended project;
- accidental shell commands issued by the user or by an agent;
- repository scripts with broad side effects, such as `npm`, `pip`, `brew`, build hooks, postinstall scripts, or test scripts;
- over-broad local file access from tools that can read the filesystem;
- accidental use of heavy Docker/sbx isolation when daily light mode is enough.

### What it is meant to protect

The intended setup separates the personal macOS world from the agentic work world. In that model, `omp-guard` helps protect:

- the personal macOS account (configured via `OMP_GUARD_PERSONAL_HOME`);
- iCloud, Desktop, Documents, and Downloads locations outside AgentWork;
- personal browser profiles;
- personal SSH, GitHub, and OMP credentials;
- personal keychain and account data as far as macOS account separation allows;
- laptop resources by avoiding Docker/sbx for routine work where light mode is sufficient.

### What it does not fully protect

These guard rails are deliberately honest about their limits:

- If the user grants credentials to an agent session, the agent can use those credentials.
- Light mode is not VM-grade isolation. It runs with account/path/state guard rails under a dedicated macOS work account.
- Any files intentionally placed under AgentWork may be accessible to agent processes depending on mode and mounts.
- Internet/network access can still expose data if tools are allowed to send it.
- Root, admin, or `sudo` changes can bypass assumptions and should remain blocked, explicit, or manual.

## 2. Estate model

The intended folder model is:

```text
$HOME/AgentWork/
  bin/
  .omp-guard-state/
  omp-guard/
  projects/
```

Roles:

- `~/AgentWork/` is the protected estate for agentic work.
- `~/AgentWork/bin/` holds convenience shims for `omp-guard`, `omp-light`, and `omp-sbx`.
- `~/AgentWork/.omp-guard-state/` is the control-plane vault inside AgentWork. It holds guard-scoped OMP state, config, caches, and temporary files.
- `~/AgentWork/omp-guard/` is only the tooling repo.
- `~/AgentWork/projects/*` is where real project work happens.

Do not work from the AgentWork root. Do not work from the `omp-guard` repo unless you are modifying the guard itself. Normal sessions should start in `~/AgentWork/projects/<project>`.

## 3. Security layer 1: macOS account separation

The first and most important boundary is the macOS account boundary. For step-by-step setup instructions, see [`macOS-account-setup.md`](macOS-account-setup.md).

- Agentic work happens as a dedicated macOS user (configured via `OMP_GUARD_WORK_USER`, default `agentlab`).
- The personal account is configured via `OMP_GUARD_PERSONAL_HOME`.
- The personal home should not be readable by the work account.
- The work account should not be an admin user.

This is stronger than relying on tool prompts alone. If an agent asks to read a personal file but the operating system denies the work account access, the prompt is not the only thing protecting the file.

This does not make the work account safe from itself. A process running as the work account can still read and modify files that account can access. The value is separation between the personal world and the agentic work world.

## 4. Security layer 2: AgentWork path boundary

Launchers refuse to run outside `~/AgentWork` by default. This prevents casual or accidental launches from personal folders, broad system folders, shared folders, or credential-heavy locations.

Blocked or refused locations include:

- The personal home (configured via `OMP_GUARD_PERSONAL_HOME`);
- `/Users/Shared`;
- Documents;
- Downloads;
- iCloud-style paths such as `Library/Mobile Documents`;
- hidden credential/config paths such as `.ssh`, `.config`, `.aws`, `.docker`, `.gnupg`, `.omp`, `.omp-guard-state`, `.claude`, and `.codex`.

The intended working location is always:

```text
~/AgentWork/projects/<project>
```

The path boundary is a guard rail against mistakes. It is not a replacement for macOS permissions or VM isolation.

## 5. Security layer 3: guard-scoped HOME/state

`omp-light` rewrites `HOME` to:

```text
~/AgentWork/.omp-guard-state/home
```

It also sets OMP-related and XDG paths so OMP stores login, model, profile, cache, and temporary state under the guard state area rather than the normal macOS home directory.

This prevents OMP from copying or inheriting a personal `~/.omp`. One guard-scoped login can be reused by supported guard backends without exposing the personal account's OMP configuration.

`.omp-guard-state` is control-plane state, not project source. It should not be committed to git.

## 5a. Security layer 3b: Tier 0 Seatbelt sandbox (light mode)

As of the Seatbelt work, `omp-light` no longer runs the agent unconfined. On
macOS it wraps `omp` in a deny-by-default **Seatbelt profile** (via
`sandbox-exec`) plus a **domain-allowlist egress proxy**. This is the "Tier 0"
enforcement layer and is the daily-driver equivalent of what Claude Code and
Codex do natively on macOS — at ~0 RAM overhead, which is what makes it viable
on a 16 GB machine and scalable to concurrent agents.

What the profile enforces (`scripts/seatbelt.py`):

- **Filesystem: deny by default.** Read/write is confined to the current
  workspace, guard-scoped state, and scoped `TMPDIR`. Reads of everything else
  — other projects, the personal account, `~/.ssh`, Keychain, credential
  paths — are denied by the kernel, not by a prompt.
- **Network: deny by default.** All outbound is blocked except the loopback
  egress proxy port. The proxy (`scripts/egress-proxy.py`) then permits only
  hosts on `network.allowedDomains` in the policy and logs every allow/deny to
  `.omp-guard-logs/egress.log`. This is the anti-exfiltration boundary: even a
  file the agent *can* read cannot leave the machine to a non-allowlisted host.

The default allowlist is **minimal** (model APIs only). GitHub, npm, and PyPI
are exfiltration-capable channels and are opt-in (commented groups in the
policy), not always-on.

### Deprecation posture (important)

`sandbox-exec(1)` and `sandbox_init(3)` are both **DEPRECATED** by Apple and
emit a warning, but remain functional and are what Claude Code / Codex ship on
macOS today. There is no supported CLI replacement. Treat Seatbelt as the
pragmatic, low-RAM **convenience** layer, not the load-bearing boundary. The
durable, non-deprecated boundaries are **macOS account separation** and
**network egress control** (the proxy, optionally backed by PF). If a macOS
update ever makes enforcement fail, `scripts/seatbelt-selftest.py` flips to
FAIL and `omp-guard doctor` reports it.

### Controls

- `OMP_GUARD_SEATBELT=auto` (default): enforce if capable, else warn and run
  unsandboxed.
- `OMP_GUARD_SEATBELT=require`: refuse to launch if Seatbelt cannot enforce.
- `OMP_GUARD_SEATBELT=off` (or legacy `OMP_GUARD_DISABLE_SEATBELT=1`): disable.
- Run `scripts/seatbelt-selftest.py` after every macOS update to re-verify the
  boundary actually holds on that build.

### Known limits (v1)

- Enforcement is process-scoped: children inherit the profile, so the *root*
  agent must be the sandboxed process (it is — `omp-light` wraps `omp`).
- `mach-lookup` is currently allowed broadly (DNS/notify daemons); scope it in
  a later pass.
- The proxy sees the destination host from the HTTPS `CONNECT host:port` line
  (or the plain-HTTP `Host` header), not the TLS payload — allowlisting by
  destination, not content inspection.
- Seatbelt does not protect *within* the allowed scope (the agent can still
  edit its own workspace). Genuinely untrusted code belongs in `docker-sbx`.

## 6. Security layer 4: command policy and guard-run

The command policy lives in:

```text
policies/default.yml
```

The classifier returns one of three decisions:

- `allow` — low-risk command can proceed;
- `ask` — potentially sensitive command needs explicit approval;
- `block` — command should not run through the guard.

Examples from the regression tests:

| Command | Decision |
|---|---|
| `git status --short` | `allow` |
| `git push origin main` | `ask` |
| `sudo rm -rf /` | `block` |

`scripts/guard-run.py` applies the classifier, refuses blocked commands, refuses ask-classified commands unless approved, and logs decisions.

This is currently a guard component, not a universal interception layer for every shell command OMP might run. Unless a command is wired through `guard-run`, do not claim it is fully intercepted. This is not full shell sandboxing.

## 7. Security layer 5: launch logging and doctor

Launch logs are written under:

```text
~/AgentWork/.omp-guard-logs/
```

Command logs are JSON Lines. They record guard decisions for commands that go through `guard-run`.

`omp-guard doctor` checks expected files, executable permissions, policy validation, classifier behavior, guarded command behavior, log permissions, JSON Lines command logs, shims, and path guard text.

Logs are private under AgentWork by convention and permissions, but they are not a secret vault. Do not put secrets in prompts or commands just because logging exists.

## 8. Security layer 6: shims

Shims live in:

```text
~/AgentWork/bin/
```

They let these commands run from any AgentWork project:

- `omp-guard`;
- `omp-light`;
- `omp-sbx`.

Shims do not provide security by themselves. They are convenience wrappers that point to the real launchers in the `omp-guard` repo.

## 9. Backend model: light

`omp-light` is the daily low-RAM mode. It does not start a Docker VM.

It uses:

- a dedicated work account and the AgentWork path guard;
- guard-scoped `HOME` and state;
- **Tier 0 Seatbelt sandbox + egress proxy on macOS** (see §5a): deny-by-default
  filesystem confined to the workspace/state, and network restricted to an
  allowlist through a loopback proxy;
- token scrubbing for common GitHub write-token environment variables;
- launch logging (including `seatbelt=on/off` and the egress proxy port).

Use light mode for normal trusted work: planning, model conversations, editing
known project files, documentation, and small code changes.

With Tier 0 active, light mode is meaningfully confined for *this* workspace at
~0 RAM cost, but it is still not VM-grade isolation and Seatbelt is a
deprecated (though functional) API. For genuinely untrusted code, use
`docker-sbx`. If Tier 0 is disabled or unavailable, OMP runs inside the
work account and can access whatever that account can access.

## 10. Backend model: docker-sbx

`omp-sbx` is the high-isolation mode using Docker/sbx. It provides stronger containment than light mode because work runs inside the sbx microVM model rather than directly in the macOS account.

Costs and fit:

- higher RAM and CPU overhead;
- better fit for risky repos, package installs, unfamiliar scripts, shell-heavy work, browser/network automation, and untrusted code;
- on a 16 GB Mac, not suitable as the always-on default.

For daily mode, a Docker helper process may remain present, but heavy Docker Desktop or VM processes should not be running unless the stronger isolation mode is needed.

## 11. Backend model: native-mac

`native-mac` is planned/experimental. The intent is to use macOS-native sandboxing rather than a VM, with lower RAM overhead than Docker/sbx.

It will probably be weaker and more fragile than VM isolation. Do not treat it as ready until `omp-guard doctor` says it is available.

## 12. GitHub auth model

Public GitHub access can work unauthenticated. Authenticated repo operations require explicit GitHub auth.

Light mode scrubs common GitHub write-token environment variables by default, including `GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_PAT`, and `COPILOT_GITHUB_TOKEN`. This reduces the chance that an agent silently mutates private repositories or pushes changes with inherited credentials.

Future approved GitHub modes may allow explicit per-session or per-project auth. Until then, treat private repo mutation, push, and PR operations as requiring explicit GitHub auth and manual approval.

## 13. Which mode should I use?

| Situation | Recommended mode |
|---|---|
| Normal known project work | `light` |
| Editing docs or own code | `light` |
| First inspection of an unknown repo | `docker-sbx` |
| Running `npm`, `pip`, `brew`, package hooks, or scripts from unknown source | `docker-sbx` |
| Anything needing `sudo`, admin, or root | Do not let the agent run it automatically |
| Private repo mutation, push, or PR | Require explicit GitHub auth and manual approval |
| Always-on background agent | `light` only if low risk; otherwise do not run it on the laptop |

## 14. Practical operating rules

- Work from `~/AgentWork/projects/<project>`.
- Use `omp-light` by default.
- Use `omp-sbx` only when risk justifies the RAM cost.
- Never copy personal `~/.omp`, `~/.ssh`, browser profiles, or personal `.config` into AgentWork.
- Do not run agents from the personal home (`$OMP_GUARD_PERSONAL_HOME`).
- Do not make the work account an admin user.
- Do not `chmod` or `chown` Homebrew or system directories to the work account.
- Do not keep Docker running unless needed.

## 15. Summary command

Run:

```bash
omp-guard security
```

It prints the current estate root, state directory, available backends, one-line backend descriptions, and the path to this document.
