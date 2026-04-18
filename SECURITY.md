# Security Policy

Thanks for helping keep `codexswitcher` and its users safe. This project handles local authentication files for Codex, so security reports are taken seriously.

## Reporting a vulnerability

**Please do not file a public issue for security problems.** Use one of the private channels below so the issue can be fixed before it's widely known.

- **GitHub private vulnerability reporting** (preferred): <https://github.com/MohamedMohana/CodexSwitcher/security/advisories/new>
- **Email**: mohammedommuhanna@gmail.com

Please include:

- A description of the issue and its impact.
- Steps to reproduce, or a minimal proof of concept.
- The version of `codexswitcher` (`codexswitcher --version`) and your OS.

You should expect an acknowledgement within **72 hours** and a more detailed response within **7 days**. If the issue is confirmed, a fix will be prepared privately and released with a public advisory crediting the reporter (unless they prefer to remain anonymous).

## Supported versions

Only the latest released version on `main` is supported with security fixes. If you're on an older release, upgrade before reporting — the issue may already be fixed.

## Scope

In scope:

- Auth files (`auth.json` and saved profiles) being written with wrong permissions.
- Auth contents leaking to logs, stdout, stderr, or temporary files that aren't cleaned up.
- Path traversal or injection via account names.
- Privilege escalation or arbitrary command execution triggered by the CLI.

Out of scope:

- Issues in upstream dependencies (report those to the relevant project).
- Issues that require an attacker to already have root or full filesystem access on the user's machine.
- Typos, UX complaints, and missing features — use a regular issue for those.

## Safe harbor

Good-faith security research that follows this policy will not result in legal action. If in doubt, ask before testing.
