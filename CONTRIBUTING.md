# Contributing to codexswitcher

Thanks for your interest in contributing! This document covers what you need to know to file issues and send pull requests.

## Reporting issues

Before opening an issue, please:

- Check the [existing issues](https://github.com/MohamedMohana/CodexSwitcher/issues) for duplicates.
- Include your OS, Python version, and `codexswitcher --version`.
- If the bug involves auth state, describe what you ran and what happened — **never paste the contents of your `auth.json`**.

## Development setup

```bash
git clone https://github.com/MohamedMohana/CodexSwitcher.git
cd CodexSwitcher
uv venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

## Running the checks

Everything the CI would run, locally:

```bash
pytest                # 126+ tests
ruff check src/ tests/
```

Both should be clean before you open a PR.

## Writing code

- Target Python 3.12+.
- Keep the module layout as it is — `cli.py` for Typer commands, `core.py` for account logic, `auth.py` for file I/O, `config.py` for paths and constants.
- Tests live in `tests/test_core.py`. Add a test for any new behavior; the existing fixtures (`tmp_env`, `_write_auth`) make it easy.
- No new runtime dependencies without discussion — the short dep list (`typer`, `rich`) is a feature.

## Commit and PR conventions

- One logical change per PR. Smaller diffs review faster.
- Commit messages: first line ≤ 72 chars, imperative mood ("Fix X", not "Fixed X"). Body explains *why*, not *what*.
- Before pushing, rebase on the latest `main` so the history stays linear.
- PRs to `main` should include a short summary and a test plan — see merged PRs for the shape.

## Security

If you find a security issue (e.g. an auth file being written with wrong permissions, a token leak through logs), please **do not** open a public issue.

Instead, report it privately via one of:

- GitHub's private vulnerability reporting: <https://github.com/MohamedMohana/CodexSwitcher/security/advisories/new>
- Email the maintainer: **mohammedommuhanna@gmail.com**

See [`SECURITY.md`](SECURITY.md) for the full policy, including what's in scope and expected response times.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE) that covers this project.
