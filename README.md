# codexswitcher

> Instantly switch between multiple Codex accounts — save, swap, and manage auth profiles.

> [!WARNING]
> Not affiliated with OpenAI or Codex. Not an official tool.

Codex stores your authentication session in a single `~/.codex/auth.json` file. This file is shared by both the **Codex CLI** (`codex`) and the **Codex desktop app** (`codex app`). If you use separate **personal** and **business** accounts, moving between them means logging out and logging back in every time — in both the CLI and the app.

`codexswitcher` fixes that. It keeps named snapshots of your `auth.json` so you can switch between them instantly — no re-login required. A single switch updates auth for **both** the terminal and the desktop app.

## Features

- **Works with both CLI & app** — one switch covers `codex` and `codex app`
- **Instant switching** — swap `auth.json` with one command
- **Interactive picker** — select from your saved accounts
- **Atomic file operations** — temp file + `os.replace()`, never a corrupt state
- **Auto-backup** — current auth backed up before every switch
- **Hash-based detection** — SHA-256 comparison identifies the active account
- **Byte-perfect copies** — original file format preserved exactly
- **Secure permissions** — `chmod 600` enforced on all auth files
- **Auto-migration** — seamlessly upgrades data from older `CodexSwitch` installs

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

Don't have uv? Install it in one line:

```bash
# On macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or, from PyPI
pip install uv
```

## Installation

```bash
# Clone and install as a global CLI tool
git clone https://github.com/MohamedMohana/CodexSwitcher.git
cd CodexSwitcher
uv tool install .
```

After this, `codexswitcher` is available everywhere.

## Quick Start

There is **no account limit** — save as many as you need. The interactive picker lets you choose from all of them.

```bash
# 1. Log in and save each account (repeat for as many as you have)
codexswitcher login personal
codexswitcher login business
codexswitcher login client-acme
codexswitcher login client-globex

# 2. See all your saved accounts
codexswitcher list

# 3. Switch between them — directly by name or interactively
codexswitcher use personal          # direct
codexswitcher use                   # interactive picker (choose from table)

# 4. Check which one is active
codexswitcher current
```

## Commands

### `codexswitcher login [name]`

Log into a Codex account. Automatically kills any stale `codex login` process before starting, so you never get "port already in use" errors.

If you pass a name, it saves the account right after login. If you omit the name, it prompts you after a successful login.

```bash
# Login and save in one step
codexswitcher login personal

# Login first, then decide whether to save
codexswitcher login
```

This command:
1. Kills any lingering `codex login` server on port 1455
2. Runs `codex login`
3. Prompts you to save the new account (or saves automatically if you passed a name)

### `codexswitcher save <name>`

Save the current `~/.codex/auth.json` as a named profile.

```bash
codexswitcher save personal
codexswitcher save business
codexswitcher save client-project
```

### `codexswitcher use [name]`

Switch to a saved account. Pass the name directly, or omit it for an interactive picker.

```bash
# Switch directly
codexswitcher use personal

# Interactive picker — shows a table and prompts you
codexswitcher use
```

After switching, **restart Codex** if it is already running. This applies to both:
- The CLI (`codex`)
- The desktop app (`codex app`)

### `codexswitcher list`

List all saved accounts. `*` marks the active one, `~` marks the recorded current when live auth differs.

```bash
codexswitcher list
```

```
┏━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Status   ┃ Account      ┃ Auth Info                   ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ * active │ personal     │ mode=chatgpt, id=9a86901f…  │
│          │ business     │ mode=chatgpt, id=7c3b2a…    │
│          │ client-acme  │ mode=chatgpt, id=f1d3e8…    │
│          │ client-globex│ mode=api-key, api-key=yes   │
└──────────┴──────────────┴─────────────────────────────┘
```

### `codexswitcher current`

Show which account is currently active.

```bash
codexswitcher current
```

```
✓ personal (active)
  mode=chatgpt, id=9a86901f...
```

### `codexswitcher remove [name]`

Remove a saved account. Pass the name directly, or omit it for an interactive picker. Prompts for confirmation unless you pass `-y`.

```bash
# Remove by name
codexswitcher remove old-account
codexswitcher remove old-account -y    # skip confirmation

# Interactive picker — shows a table and prompts you
codexswitcher remove
```

### `codexswitcher --version`

Show the installed version.

```bash
codexswitcher -v
codexswitcher --version
```

## How It Works

```
~/.codex/
├── auth.json                              ← Live auth (both codex CLI & app read this)
└── .codexswitcher/
    ├── accounts/
    │   ├── personal.auth.json             ← Saved snapshot
    │   ├── business.auth.json             ← Saved snapshot
    │   ├── client-acme.auth.json          ← Saved snapshot
    │   └── client-globex.auth.json        ← Saved snapshot
    ├── backups/
    │   └── business-backup.auth.json      ← Auto-backup before switch
    └── .current                           ← Tracks active account name
```

When you run `codexswitcher save personal`, it copies `auth.json` → `personal.auth.json`.

When you run `codexswitcher use personal`, it:
1. Backs up the current `auth.json` (if linked to a saved account)
2. Copies `personal.auth.json` → `auth.json` (atomic replace)
3. Updates the `.current` state file

Since both the CLI and the desktop app read from the same `auth.json`, a single switch updates auth for both.

## Configuration

All paths can be overridden with environment variables:

| Variable | Default | Description |
|---|---|---|
| `CODEX_HOME` | `~/.codex` | Codex config directory |
| `CODEX_AUTH_FILE` | `$CODEX_HOME/auth.json` | Live auth file path |
| `CODEXSWITCHER_DIR` | `$CODEX_HOME/.codexswitcher` | codexswitcher storage directory |

## Upgrading from CodexSwitch

If you previously used `CodexSwitch` (the older name), `codexswitcher` automatically migrates your saved accounts on first run:

- Your old `~/.codex/.codexswitch/` directory is moved to `~/.codex/.codexswitcher/`
- All saved accounts and the active account state are preserved
- No manual steps needed — just run any `codexswitcher` command

## Development

```bash
# Clone the repo
git clone https://github.com/MohamedMohana/CodexSwitcher.git
cd CodexSwitcher

# Install with dev dependencies
uv sync --all-extras

# Activate the virtual environment (optional — lets you run commands without 'uv run')
# macOS / Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate

# Run tests
pytest -v

# Lint
ruff check src/ tests/

# Run locally without installing
codexswitcher --help
```

## License

MIT
