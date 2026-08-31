# Hermes Profile Model

Each Hermes profile is a separate identity and state boundary. Do not use one all-powerful profile.

## Initial profiles

```text
chief-of-staff
researcher
marketer
developer
reviewer
operator
librarian
```

Create them with:

```bash
hermes-guard bootstrap-profiles
```

Validate one profile with:

```bash
hermes-profile-doctor chief-of-staff
```

## Role boundaries

`chief-of-staff` orchestrates work. It should use Kanban and memory, not terminal, browser, cron creation, GitHub write, or external posting.

`researcher` gathers cited information. It should not mutate repos, publish externally, or use terminal initially.

`developer` implements scoped changes only in assigned workspaces or worktrees. It must not use sudo, push to GitHub, merge PRs, or edit outside the assigned workspace.

`reviewer` verifies diffs and tests. It should not patch files unless explicitly assigned an implementation card.

`librarian` curates wiki and proposed skills. It should not directly promote durable skills without human review.

## Files per profile

Each profile has:

```text
SOUL.md       role identity and behavioural constraints
profile.yml   local manifest describing expected toolsets and policy
home/         profile-scoped HOME
skills/       profile-local skills area
memories/     profile-local memory area
logs/         profile-local launcher/proxy logs
```

Do not seed profiles with personal SSH keys, browser profiles, GitHub auth, iCloud files, or normal `~/.config` contents.

## Toolset policy

Toolsets are declared in `profile.yml` as a guard expectation. The manifest is not a substitute for Hermes' own config; it is an independent local safety check so the guard can fail obvious profile drift before always-on operation.
