# Recommended macOS prerequisites before installing OMP or omp-guard

This guide is for users who want to run OMP, coding agents, shell agents, or
autonomous tools on a personal Mac while reducing the risk to their personal
files, iCloud data, browser sessions, SSH keys, and saved credentials.

The goal is not to make the Mac perfectly secure. The goal is to create a
safer operating boundary before installing agentic tools.

The recommended setup is:

- **Personal Mac account** = normal personal use.
- **Agent account** = OMP, omp-guard, coding agents, test repositories, terminal work.
- **No personal files or iCloud data inside the agent account.**

---

## Why this matters

OMP and similar tools are not ordinary apps. They may be able to read files,
write files, run shell commands, install packages, call other tools, use
GitHub, use browsers, and interact with local configuration.

If these tools are installed in your normal personal Mac account, they may end
up close to:

- personal documents;
- Desktop and Documents folders;
- iCloud Drive;
- browser profiles;
- saved sessions;
- SSH keys;
- API keys;
- GitHub credentials;
- app permissions such as Full Disk Access, Accessibility, Screen Recording,
  Automation, and Files & Folders.

The safer pattern is to keep agentic work inside a separate local macOS user
with fewer privileges.

---

## Target end state

Before installing OMP, omp-guard, Codex CLI, Claude Code, or similar tools,
the Mac should be in this state:

- Your normal personal account still exists and remains your personal account.
- Agentic tools are not used from the personal account.
- A second macOS account exists for agentic work.
- The second account is a **Standard** user, not an Administrator.
- The second account is not signed into Apple Account / iCloud.
- The second account does not use iCloud Drive, iCloud Keychain, Messages,
  Photos, or synced Desktop/Documents.
- Agent work happens in a dedicated local folder such as:

```text
~/AgentWork/
```

- Personal folders such as Desktop, Documents, Downloads, iCloud Drive,
  Photos, Mail, Messages, and browser profiles are not shared with the agent
  account.
- Existing hidden config folders are not copied into the agent account.
- Remote Login, File Sharing, Screen Sharing, and Remote Management are off
  unless deliberately needed.

---

## Part 1 — Clean the main personal Mac account

Start in your normal personal Mac account.

This account may still be your Administrator account. That is fine. The
important point is that it should not be the account where you run OMP or
autonomous agent tools.

### 1. Review app permissions

Open:

```text
System Settings → Privacy & Security
```

Review the following sections carefully:

```text
Full Disk Access
Files & Folders
Accessibility
Automation
Input Monitoring
Screen & System Audio Recording
Developer Tools
Local Network
Microphone
Camera
```

For each section, remove or turn off access for apps that do not clearly need
it.

Pay special attention to:

```text
Terminal
iTerm
Ghostty
Warp
VS Code
Cursor
Zed
Xcode
Docker
Python
Node
Claude
Codex
OpenAI / ChatGPT desktop apps
OMP
agent tools
unknown helper apps
old experiments
```

The strict version is:

- no terminal app should have Full Disk Access in the personal account;
- no agentic app should have Documents/Desktop/Downloads access in the personal
  account;
- no agentic app should have Accessibility unless you explicitly need it;
- no agentic app should have Screen Recording unless you explicitly need it;
- no agentic app should have Input Monitoring unless you explicitly need it;
- no old experiment should retain permissions "just in case."

A simple rule:

> If you would not want an autonomous coding agent to read or control it,
> remove the permission from the personal account.

### 2. Revoke broad file permissions

In:

```text
System Settings → Privacy & Security → Files & Folders
```

Check whether any terminal, coding, AI, or automation app has access to:

```text
Desktop
Documents
Downloads
Removable Volumes
Network Volumes
```

Turn off anything that is not needed.

This is especially important if your Desktop or Documents folders are synced
with iCloud.

### 3. Revoke Full Disk Access unless absolutely needed

In:

```text
System Settings → Privacy & Security → Full Disk Access
```

Remove anything that does not clearly require system-wide file access.

Full Disk Access is a powerful permission. For normal agentic work, it should
not be granted in your personal account.

Do not leave Full Disk Access enabled for:

```text
Terminal
iTerm
Ghostty
Warp
Claude
Codex
OMP
Python
Node
unrecognised helpers
old tools you are no longer using
```

Some apps may genuinely need Full Disk Access, such as backup tools or
security tools. Keep only what you understand.

### 4. Revoke Accessibility, Automation, and Input Monitoring where not needed

These permissions allow apps to control or observe parts of the Mac.

Review:

```text
System Settings → Privacy & Security → Accessibility
System Settings → Privacy & Security → Automation
System Settings → Privacy & Security → Input Monitoring
```

Remove old or unnecessary entries.

For agentic security, these are sensitive because they can let software:

- control other apps;
- click buttons;
- type or monitor input;
- automate workflows;
- interact with windows outside the intended project folder.

### 5. Revoke Screen & System Audio Recording where not needed

Review:

```text
System Settings → Privacy & Security → Screen & System Audio Recording
```

Remove unnecessary access.

Screen access is sensitive because an app may be able to see personal
documents, browser tabs, private messages, calendar details, passwords shown
on screen, or financial information.

### 6. Disable remote access and sharing

Open:

```text
System Settings → General → Sharing
```

Recommended default state:

```text
Remote Login: Off
File Sharing: Off
Screen Sharing: Off
Remote Management: Off
Remote Apple Events: Off
Content Caching: Off unless you know you need it
Internet Sharing: Off
```

If Remote Login is ever enabled later, do not use "All users." Use "Only these
users," and only allow the dedicated agent account if there is a specific
reason.

Also leave this off:

```text
Allow full disk access for remote users
```

The default safe position is that nobody should be able to SSH into the
personal Mac account.

---

## Part 2 — Create a separate agent account

Create a second macOS user for OMP and agentic work.

Recommended account name: any name that is clearly separate from your personal
account (e.g. `agentlab`). The name does not matter as long as it is distinct.

### 1. Create the user

Open:

```text
System Settings → Users & Groups
```

Choose:

```text
Add User / Add Account
```

When asked for account type, choose:

```text
Standard
```

Do not choose:

```text
Administrator
```

Create a strong password and save it in your password manager.

The key point is that the agent account should not be able to make
system-wide changes without an administrator password.

### 2. Log out of your personal account

After creating the account, log out of your personal account.

Then log into the new agent account.

Do not just fast-switch and leave everything open in the personal account
during setup. Clean separation is easier if you treat the agent account as a
different working environment.

---

## Part 3 — Keep the agent account local-only

When the new account starts for the first time, macOS may ask you to sign in
with an Apple Account.

Recommended answer:

```text
Do not sign in.
Set up later.
Skip.
No Apple Account.
```

The desired state is:

```text
No Apple Account
No iCloud
No iCloud Drive
No iCloud Keychain
No synced Desktop & Documents
No Messages
No Photos
No personal Safari profile
No personal browser sync
```

This matters because signing into Apple Account can bring personal data into
the agent account automatically.

Do not use your personal Apple Account in the agent account.

Do not enable:

```text
iCloud Drive
Desktop & Documents Folders
iCloud Keychain
Photos
Messages
Mail
Safari sync
Notes
Contacts
Calendars
```

The agent account should feel empty. That is intentional.

---

## Part 4 — Create a dedicated local workspace

Inside the agent account, create a simple local workspace.

Recommended folder:

```text
~/AgentWork/
```

You can create it through Finder or the terminal:

```bash
mkdir -p ~/AgentWork/projects
```

Recommended project layout:

```text
~/AgentWork/
  omp-guard/      # the guard tooling repo
  projects/       # your actual project work
  bin/            # convenience shims (created by install.sh)
```

Avoid using:

```text
Desktop
Documents
Downloads
iCloud Drive
Shared
personal folders
```

Even though the agent account has no iCloud, using a clearly named workspace
reduces confusion and makes it easier to reason about what the agent can
access.

The working rule is:

> If an agent creates it, clones it, edits it, or runs it, keep it inside
> AgentWork.

---

## Part 5 — Do not copy personal config into the agent account

Do not copy your whole home folder from the personal account.

Do not copy these folders or files from your personal account into the agent
account:

```text
~/.ssh
~/.config
~/.omp
~/.claude
~/.codex
~/.cursor
~/.gitconfig
~/.zsh_history
~/.bash_history
~/.npmrc
~/.pypirc
~/.netrc
.env files
browser profiles
Keychain files
API key files
GitHub token files
cloud provider credentials
```

These may contain secrets, tokens, saved sessions, private hostnames, old
agent settings, or personal environment configuration.

Set up the agent account fresh.

If GitHub access is needed later, create or log in deliberately from inside
the agent account. Prefer least-privilege credentials.

If SSH is needed later, create new keys specifically for the agent account. Do
not reuse personal SSH keys by default.

---

## Part 6 — Keep personal and agentic roles separate

Use the accounts like this:

### Personal account

Use for:

```text
email
family documents
banking
personal browsing
iCloud
Photos
Messages
personal writing
normal Mac administration
```

Do not use for:

```text
OMP
omp-guard
Codex CLI
Claude Code
autonomous agents
shell-based agent workflows
experimental MCP servers
unknown scripts
```

### Agent account

Use for:

```text
OMP
omp-guard
agent projects
coding agents
test repositories
GitHub experiments
local scratch work
CLI installs
sandbox experiments
```

Do not use for:

```text
personal iCloud
banking
email
family documents
Photos
Messages
personal browser sessions
main password manager
private SSH keys
personal cloud drives
```

This is the main security boundary.

---

## Part 7 — Recommended pre-install checklist

Before installing OMP, omp-guard, or any agent tooling, confirm the following.

### Personal account checklist

- [ ] Personal account is not being used for OMP or agent tools.
- [ ] Full Disk Access has been reviewed.
- [ ] Terminal apps do not have unnecessary Full Disk Access.
- [ ] Agentic apps do not have unnecessary Full Disk Access.
- [ ] Files & Folders permissions have been reviewed.
- [ ] Desktop/Documents/Downloads access has been removed from apps that do
      not need it.
- [ ] Accessibility permissions have been reviewed.
- [ ] Automation permissions have been reviewed.
- [ ] Input Monitoring permissions have been reviewed.
- [ ] Screen & System Audio Recording permissions have been reviewed.
- [ ] Remote Login is off.
- [ ] File Sharing is off.
- [ ] Screen Sharing is off.
- [ ] Remote Management is off.
- [ ] Remote Apple Events is off.
- [ ] "Allow full disk access for remote users" is off.

### Agent account checklist

- [ ] Separate macOS user exists.
- [ ] Account type is Standard, not Administrator.
- [ ] Account is not signed into Apple Account.
- [ ] iCloud is not enabled.
- [ ] iCloud Drive is not enabled.
- [ ] iCloud Keychain is not enabled.
- [ ] Desktop & Documents sync is not enabled.
- [ ] Personal browser sync is not enabled.
- [ ] No personal files have been copied in.
- [ ] No personal SSH keys have been copied in.
- [ ] No personal API keys have been copied in.
- [ ] No old `~/.omp`, `~/.claude`, or `~/.codex` config has been copied in.
- [ ] A local workspace exists, for example `~/AgentWork/`.

### Workspace checklist

- [ ] All agent projects will live under `AgentWork`.
- [ ] Repositories will be cloned fresh into the agent account.
- [ ] Secrets will be added deliberately, not inherited from the personal
      account.
- [ ] Any future remote access will be restricted to the agent account only,
      not the personal account.
- [ ] The user understands which account they are currently logged into before
      running install commands.

---

## Part 8 — Common mistakes to avoid

### Mistake 1: Installing OMP in the personal account

Do not do this for a safer setup.

Even if you later create an agent account, the personal account may already
have created configs, tokens, shell history, package installs, or permissions.

Preferred approach:

```text
Create agent account first.
Then install OMP from the agent account.
```

### Mistake 2: Making the agent account an Administrator

Do not make the agent account an Administrator unless you have a specific
reason.

A Standard account is safer because it reduces the chance that a tool can make
system-wide changes without extra approval.

### Mistake 3: Signing the agent account into iCloud

Do not sign into your personal Apple Account from the agent account.

This can bring in iCloud Drive, Desktop/Documents, Photos, Messages, Safari
data, Keychain data, and other personal sync surfaces.

### Mistake 4: Copying hidden folders from the personal account

Do not copy dotfolders from the personal account into the agent account.

Folders like `~/.ssh`, `~/.config`, `~/.claude`, `~/.codex`, and `~/.omp` may
contain sensitive credentials or old settings.

Start fresh.

### Mistake 5: Granting Full Disk Access to Terminal and forgetting about it

If Full Disk Access is ever granted temporarily, remove it afterwards.

Do not leave Terminal, agent tools, or coding tools with broad access in the
personal account.

### Mistake 6: Enabling Remote Login for all users

If SSH is ever needed, do not allow all users.

Use:

```text
Only these users
```

Then select only the dedicated agent account.

Do not enable full disk access for remote users unless you fully understand
the risk.

---

## Part 9 — Summary

The recommended macOS security model is:

> Run OMP and related agent tools inside a separate local Standard user
> account with no Apple Account, no iCloud, no personal files, no inherited
> credentials, and a dedicated local workspace. Keep the main personal account
> clean by revoking unnecessary app permissions and disabling remote
> access/sharing. Treat the account boundary as the first layer of protection
> before adding omp-guard, sandboxing, command policy, or other controls.

This should be completed before running any OMP or omp-guard installation
commands.

---

## Part 10 — What this does and does not protect against

This setup helps reduce the damage from:

- accidental file reads;
- agents scanning personal folders;
- prompt-injected commands touching personal data;
- inherited credentials from old tools;
- accidental iCloud exposure;
- broad terminal permissions in the personal account;
- remote login into the wrong account;
- agents modifying personal Desktop/Documents files.

This setup does not guarantee protection against:

- macOS privilege escalation vulnerabilities;
- malicious software installed with admin approval;
- secrets manually pasted into the agent account;
- browser sessions opened inside the agent account;
- granting Full Disk Access later;
- copying personal SSH keys or API tokens later;
- running untrusted scripts with administrator privileges;
- intentionally bypassing the separation model.

The rule is simple:

> The agent account is only as clean as what you choose to put into it.

Start clean. Add access slowly. Remove access when it is no longer needed.
