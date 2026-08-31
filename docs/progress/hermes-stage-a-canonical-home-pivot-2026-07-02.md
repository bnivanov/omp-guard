# Hermes Stage A canonical-home pivot

Date: 2 July 2026

## Decision

Stage A now uses the canonical Hermes Desktop/CLI state directory:

```text
/Users/agentlab/.hermes
```

The previous profile-local runtime model under `~/AgentWork/hermes/profiles/<profile>` is retained only as an advanced/debug path. It is no longer the default Stage A runtime.

## Rationale

Hermes Desktop and Hermes CLI share account-level state under `~/.hermes`, including config, auth, model caches, session DBs, logs, updates, skills, memories, and Desktop integration files. Maintaining a second profile-local Hermes home caused persistence divergence and made guarded launches fragile after Desktop or CLI activity.

The safer operational decision is to keep Hermes state where Hermes expects it, and make `omp-guard` enforce the execution boundary instead.

## New Stage A boundary

`hermes-light --profile chief-of-staff` now treats `--profile` as an identity, policy, and logging selector. By default it does not create a separate Hermes runtime. It launches Hermes with:

```text
HERMES_HOME=$HOME/.hermes
HOME=$HOME
XDG_CONFIG_HOME unset
XDG_CACHE_HOME unset
XDG_DATA_HOME unset
XDG_STATE_HOME unset
TMPDIR=$OMP_GUARD_ALLOWED_ROOT/.omp-guard-tmp/hermes-light
```

The Seatbelt profile allows writes only to the current project workspace, canonical `~/.hermes`, the guard temp directory, and the guard log directory. It does not allow broad read/write access to `/Users/agentlab`.

## Still not enabled

This pivot does not enable gateway, cron, LaunchAgent, Kanban worker dispatch, browser automation, MCP, GitHub write, developer execution, or Stage B researcher operation.

## Stage A validation target

A clean Stage A pass now means:

```text
1. hermes-light launches only from ~/AgentWork/projects/<project>
2. HERMES_HOME is /Users/agentlab/.hermes
3. HOME is /Users/agentlab
4. XDG state/config/cache/data are not redirected to profile-local Hermes paths
5. Seatbelt is on in normal guarded runs
6. Egress proxy is on in normal guarded runs
7. token environment variables are scrubbed before launching Hermes
8. launch logs show home_mode=canonical-hermes-home
9. no session-store warning appears
10. no gateway/cron/worker functionality is enabled
```
