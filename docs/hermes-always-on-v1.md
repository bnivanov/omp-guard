# Hermes Always-On v1 Guard

This repo is not trying to make Hermes fully autonomous on day one. The safe v1 sequence is:

1. Run Hermes only from the dedicated macOS Standard agent account.
2. Keep all Hermes state under `~/AgentWork/hermes`.
3. Launch Hermes through `hermes-light`, not directly.
4. Bootstrap isolated profiles before gateway or cron.
5. Prove one manual Kanban profile before workers, gateway, cron, or LaunchAgent.

## Commands added in this slice

After `./omp-guard install-shims`, these commands are installed into `~/AgentWork/bin`:

```bash
hermes-guard doctor
hermes-guard bootstrap-profiles
hermes-profile-doctor chief-of-staff
hermes-light --profile chief-of-staff --version
hermes-gateway-light --profile chief-of-staff --foreground
```

## State layout

```text
~/AgentWork/hermes/
  profiles/
    chief-of-staff/
      SOUL.md
      profile.yml
      home/
      tmp/
      xdg-config/
      xdg-cache/
      xdg-data/
      logs/
      skills/
      memories/
```

`HERMES_HOME` is set to the profile root. `HOME`, XDG directories, and `TMPDIR` are moved inside that profile root so a Hermes worker does not inherit the normal macOS home.

## Stage A target

Stage A is single-profile only:

```text
chief-of-staff only
no workers
no cron
no browser
no messaging
manual Kanban task creation only
```

Exit criteria:

```text
Can create/list/comment/archive tasks.
Cannot run terminal.
Cannot access personal home.
Cannot use non-allowlisted network.
```

## First local run

Run from the agent account:

```bash
cd ~/AgentWork/omp-guard
git checkout hermes-trial-slice-1
./omp-guard install-shims
hermes-guard bootstrap-profiles
hermes-profile-doctor chief-of-staff
hermes-doctor
```

Then test from a project workspace:

```bash
mkdir -p ~/AgentWork/projects/hermes-trial
cd ~/AgentWork/projects/hermes-trial
hermes-light --profile chief-of-staff --version
```

Do not enable `hermes-gateway-light`, cron, or a LaunchAgent until this passes.
