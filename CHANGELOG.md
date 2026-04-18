# Changelog

All notable changes to `codexswitcher` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `codexswitcher rename <old> <new>` — rename a saved account and its backup.
- `codexswitcher save <name> --from <path>` — import an auth file from a backup or another machine without touching the live `auth.json`.
- `codexswitcher list --json` — machine-readable output for scripting.
- Documentation for Typer's built-in `--install-completion` flag.
- `SECURITY.md`, `CONTRIBUTING.md`, `LICENSE`, issue/PR templates.
- Dependabot config for GitHub Actions and pip.
- GitHub Actions CI running pytest + ruff on Python 3.12/3.13 across Ubuntu and macOS.

### Fixed
- `codexswitcher login <name>` no longer saves the existing auth under the new name if `codex login` was cancelled or failed. The auth-file hash is checked before/after login.
- Interactive `use` picker no longer defaults to the already-active account.
- `kill_login_server` short-circuits on platforms without `lsof` (e.g. Windows) instead of relying on exception handling.

### Changed
- Added a concrete security reporting channel (GitHub private advisories + maintainer email).

## [1.0.0] - 2026-04-18

### Added
- Initial release.
- Commands: `login`, `save`, `use`, `list`, `current`, `remove`.
- Atomic file operations with `tempfile.mkstemp` + `os.replace`.
- Hash-based active-account detection (SHA-256).
- Auto-backup on every switch.
- Auto-migration from the legacy `~/.codex/.codexswitch` directory.
