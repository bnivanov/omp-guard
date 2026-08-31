# Hermes Operations Runbook

## Local validation

```bash
cd ~/AgentWork/omp-guard
./omp-guard doctor
python3 scripts/seatbelt-selftest.py
bash scripts/test-hermes-guard.sh
hermes-guard bootstrap-profiles
hermes-doctor
```

## Stage A procedure

1. Confirm you are in the dedicated agent account.
2. Confirm `OMP_GUARD_PERSONAL_HOME` points at the personal macOS account home.
3. Install shims with `./omp-guard install-shims`.
4. Bootstrap profiles with `hermes-guard bootstrap-profiles`.
5. Validate `chief-of-staff` with `hermes-profile-doctor chief-of-staff`.
6. Launch Hermes from `~/AgentWork/projects/hermes-trial` with `hermes-light --profile chief-of-staff --version`.

## Gateway rule

Run the gateway only in foreground until manual tests pass:

```bash
hermes-gateway-light --profile chief-of-staff --foreground
```

Do not install a LaunchAgent in this slice.

## Kill switch for later stages

Before enabling gateway persistence or cron, add guarded scripts for:

```text
hermes-stop-all
hermes-disable-gateway
hermes-disable-cron
hermes-network-lockdown
hermes-backup-state
hermes-restore-state
```

Minimum manual stop while still in foreground testing:

```bash
pkill -f "hermes gateway"
pkill -f "hermes"
```

Do not use a system daemon. Always-on v1 should use a user-level LaunchAgent in the agent account only, after multiple successful foreground runs.

## Audit checks for later stages

Daily audit should eventually report:

```text
blocked tasks
long-running tasks
tasks completed in last 24h
tasks created by chief-of-staff
network/tool escalation requests
skills modified
memory modified
cron jobs created or changed
```
