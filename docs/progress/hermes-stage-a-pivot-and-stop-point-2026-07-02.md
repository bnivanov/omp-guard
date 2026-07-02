# Hermes Stage A pivot and stop point

Date: 2 July 2026

## Status

Stage A is not ready to progress to Stage B.

Hermes Desktop is usable inside the protected `agentlab` account, and the Hermes project can be anchored under `~/AgentWork/projects`. However, guarded interactive Hermes through `hermes-light` plus Seatbelt plus the egress proxy is not yet stable enough to rely on.

## What was validated

- Hermes Desktop runs from the standard `agentlab` macOS account.
- Hermes CLI/runtime state is account-local to `agentlab`.
- Hermes Desktop and CLI expect canonical state under `/Users/agentlab/.hermes`.
- Hermes projects should be anchored under `/Users/agentlab/AgentWork/projects`.
- `hermes-light --profile chief-of-staff --version` can launch quickly in canonical-home mode.
- Launch logs show canonical-home mode, project cwd, Seatbelt status, egress proxy status, and token-scrub status.

## What did not pass

The real interactive guarded path did not pass cleanly.

A fast `--version` run is not enough. Stage A requires interactive Hermes to connect to the model provider, persist the session, work through the egress proxy, remain responsive, and resume cleanly.

During the latest interactive test, Hermes was slow to boot and produced a connection error. That is a stop signal.

## Architecture decision

Stage A should use canonical Hermes state:

```text
/Users/agentlab/.hermes
```

The earlier profile-local Hermes runtime tree should be treated as advanced/debug only:

```text
/Users/agentlab/AgentWork/hermes/profiles/<profile>
```

The guard should protect the execution boundary rather than trying to make Hermes maintain a duplicate default runtime.

## Operating decision

For now:

- use Hermes Desktop manually inside `agentlab`;
- keep Hermes projects under `/Users/agentlab/AgentWork/projects`;
- do not rely on interactive `hermes-light` Seatbelt mode yet;
- do not start Stage B;
- do not enable gateway, cron, LaunchAgent, workers, browser automation, MCP, GitHub write, developer execution, or external publishing.

## Next implementation slice

Before this PR is marked ready or merged, add a deliberate Stage A simplification and validation patch:

1. make canonical `/Users/agentlab/.hermes` mode the explicit Stage A default;
2. keep profile-local runtime mode as advanced/debug only;
3. keep project-root enforcement;
4. keep token scrubbing;
5. keep launch logging;
6. keep egress proxy controls;
7. add explicit provider-connectivity validation;
8. replace brittle SQLite-only smoke tests with real interactive launch validation;
9. document the weaker Seatbelt-off fallback for controlled learning;
10. ensure tests reflect the Hermes Desktop / CLI / Xcode / SQLite findings from this debugging session.

## New Stage A pass gate

A clean Stage A pass requires:

1. Hermes Desktop works in `agentlab`.
2. The Hermes project is anchored under `~/AgentWork/projects`.
3. `hermes-light --profile chief-of-staff --version` works quickly.
4. `hermes-light --profile chief-of-staff` launches interactively without a session-store warning.
5. A harmless model call succeeds without a connection error.
6. Launch logs show the correct project cwd.
7. Launch logs show token scrubbing.
8. Launch logs show either guarded mode with Seatbelt and egress proxy on, or an explicit documented fallback mode.
9. No personal home, iCloud, Downloads, Desktop, or Documents path is used as a workspace.
10. The repo tests reflect the real validation path.

## Bottom line

The separate `agentlab` account remains the durable safety boundary. Seatbelt is useful, but it should not be treated as the load-bearing foundation until the real interactive Hermes path is stable.

Do not proceed to Stage B until Stage A has a stable, boring, repeatable operating mode.
