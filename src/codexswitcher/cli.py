from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from codexswitcher import __version__
from codexswitcher import config as cfg
from codexswitcher.auth import file_hash
from codexswitcher.core import (
    AccountAlreadyActiveError,
    CodexSwitcherError,
    get_current,
    kill_login_server,
    list_accounts,
    remove_account,
    rename_account,
    save_account,
    switch_account,
)

app = typer.Typer(
    name="codexswitcher",
    help="Instantly switch between multiple Codex accounts.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)
console = Console()
err_console = Console(stderr=True)


def _version(value: bool) -> None:
    if value:
        console.print(f"codexswitcher {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=_version,
        is_eager=True,
    ),
) -> None:
    pass


@app.command()
def login(
    name: str = typer.Argument(
        None, help="Name to save this account as after login."
    ),
) -> None:
    """Log into Codex (kills any stale login server first)."""
    killed = kill_login_server()
    if killed:
        pids = ", ".join(str(p) for p in killed)
        console.print(f"[dim]Killed stale login process(es): {pids}[/]")

    codex_bin = shutil.which("codex")
    if not codex_bin:
        err_console.print(
            "[bold red]Error:[/] Could not find [cyan]codex[/] command. "
            "Make sure Codex CLI is installed."
        )
        raise typer.Exit(1) from None

    before_hash = file_hash(cfg.AUTH_FILE) if cfg.AUTH_FILE.exists() else None

    subprocess.run([codex_bin, "login"], check=False)

    if not cfg.AUTH_FILE.exists():
        err_console.print(
            "[yellow]Login did not complete — no auth file was created.[/]"
        )
        return

    after_hash = file_hash(cfg.AUTH_FILE)
    if before_hash == after_hash:
        err_console.print(
            "[yellow]Login did not change the current auth — nothing to save.[/]"
        )
        return

    if name:
        _do_save(name)
    else:
        name_input = Prompt.ask(
            "[bold]Save this account as[/]",
            default="",
            console=console,
        )
        if name_input.strip():
            _do_save(name_input.strip())
        else:
            console.print(
                "[dim]Login complete. "
                "Run [cyan]codexswitcher save <name>[/] to save this account.[/]"
            )


def _do_save(name: str, source: Path | None = None) -> None:
    try:
        dest = save_account(name, source=source)
        origin = "current auth" if source is None else str(source)
        console.print(
            f"[bold green]✓[/] Saved {origin} as [cyan]{name}[/]"
        )
        console.print(f"  {dest}")
    except CodexSwitcherError as e:
        err_console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1) from None


@app.command()
def save(
    name: str = typer.Argument(..., help="Name for this account profile."),
    from_path: Path = typer.Option(
        None,
        "--from",
        help="Import auth from this file instead of the live ~/.codex/auth.json.",
        exists=False,
        dir_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Save the current Codex auth as a named account."""
    _do_save(name, source=from_path)


@app.command()
def use(
    name: str = typer.Argument(
        None, help="Account to switch to. Omit for interactive picker."
    ),
) -> None:
    """Switch to a saved Codex account."""
    if name is None:
        _interactive_switch()
        return
    _do_switch(name)


def _do_switch(name: str) -> None:
    try:
        switch_account(name)
        console.print(f"[bold green]✓[/] Switched to [cyan]{name}[/]")
        console.print(
            "[bold yellow]⚠ Restart Codex (CLI and/or app) to use the new account.[/]"
        )
    except AccountAlreadyActiveError as e:
        console.print(f"[yellow]{e}[/]")
    except CodexSwitcherError as e:
        err_console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1) from None


def _interactive_switch() -> None:
    accounts = list_accounts()
    if not accounts:
        err_console.print(
            "[bold red]Error:[/] No saved accounts. "
            "Run [cyan]codexswitcher save <name>[/] first."
        )
        raise typer.Exit(1)

    table = Table(show_header=True, header_style="bold", show_lines=False, box=None)
    table.add_column("#", style="dim", width=4)
    table.add_column("Account")
    table.add_column("Info", style="dim")

    for i, acc in enumerate(accounts, 1):
        marker = (
            "[green]*[/]"
            if acc.is_active
            else ("[yellow]~[/]" if acc.is_recorded_only else "")
        )
        label = f"{marker} {acc.name}" if marker else acc.name
        summary = acc.summary or ""
        table.add_row(str(i), label, summary)

    console.print()
    console.print(table)
    console.print()

    default_choice = next(
        (str(i) for i, a in enumerate(accounts, 1) if not a.is_active),
        "1",
    )

    choice = Prompt.ask(
        "[bold]Switch to[/]",
        choices=[str(i) for i in range(1, len(accounts) + 1)]
        + [a.name for a in accounts],
        default=default_choice,
        console=console,
    )

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(accounts):
            chosen = accounts[idx].name
        else:
            err_console.print("[bold red]Error:[/] Invalid selection.")
            raise typer.Exit(1)
    else:
        chosen = choice

    _do_switch(chosen)


@app.command("list")
def list_cmd(
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
    ),
) -> None:
    """List all saved Codex accounts."""
    accounts = list_accounts()

    if as_json:
        payload = [
            {
                "name": a.name,
                "is_active": a.is_active,
                "is_recorded_only": a.is_recorded_only,
                "summary": a.summary,
            }
            for a in accounts
        ]
        console.print_json(json.dumps(payload))
        return

    if not accounts:
        console.print("[dim]No saved Codex accounts.[/]")
        return

    table = Table(show_header=True, header_style="bold", show_lines=False)
    table.add_column("Status", width=8)
    table.add_column("Account")
    table.add_column("Auth Info", style="dim")

    for acc in accounts:
        if acc.is_active:
            status = "[green]* active[/]"
        elif acc.is_recorded_only:
            status = "[yellow]~ recorded[/]"
        else:
            status = ""

        table.add_row(status, acc.name, acc.summary or "")

    console.print(table)

    if any(a.is_recorded_only for a in accounts):
        console.print(
            "\n[dim]~ = recorded current "
            "(live auth differs from saved snapshot)[/]"
        )


@app.command()
def doctor() -> None:
    """Run diagnostic checks and report the health of the install."""
    import stat

    from codexswitcher.auth import read_auth

    cfg.ensure_dirs()

    ok = "[bold green]✓[/]"
    warn = "[yellow]![/]"
    fail = "[bold red]✗[/]"

    rows: list[tuple[str, str, str]] = []

    rows.append((ok, "codexswitcher", f"version {__version__}"))

    codex_bin = shutil.which("codex")
    if codex_bin:
        rows.append((ok, "codex CLI", codex_bin))
    else:
        rows.append((fail, "codex CLI", "not found on PATH"))

    if cfg.AUTH_FILE.exists():
        perms = stat.S_IMODE(cfg.AUTH_FILE.stat().st_mode)
        perm_mark = ok if perms == cfg.AUTH_FILE_PERMISSIONS else warn
        rows.append(
            (
                perm_mark,
                "auth.json",
                f"{cfg.AUTH_FILE} (mode {perms:o})",
            )
        )
        try:
            read_auth(cfg.AUTH_FILE)
            rows.append((ok, "auth.json parse", "valid JSON"))
        except (OSError, ValueError) as e:
            rows.append((fail, "auth.json parse", str(e)))
    else:
        rows.append((warn, "auth.json", f"missing ({cfg.AUTH_FILE})"))

    accounts = list_accounts()
    rows.append((ok, "saved accounts", f"{len(accounts)} profile(s)"))

    bad_perms = []
    for acc in accounts:
        p = cfg.account_path(acc.name)
        if p.exists():
            mode = stat.S_IMODE(p.stat().st_mode)
            if mode != cfg.AUTH_FILE_PERMISSIONS:
                bad_perms.append(f"{acc.name} (mode {mode:o})")
    if bad_perms:
        rows.append(
            (warn, "profile permissions", "loose: " + ", ".join(bad_perms))
        )
    else:
        rows.append((ok, "profile permissions", "0600 on all profiles"))

    matched_or_recorded = get_current()
    if matched_or_recorded is None and accounts:
        rows.append(
            (warn, "current account", "live auth doesn't match any profile")
        )
    elif matched_or_recorded is None:
        rows.append((warn, "current account", "no saved accounts"))
    else:
        label = (
            "active"
            if matched_or_recorded.is_active
            else "recorded (live auth differs)"
        )
        rows.append((ok, "current account", f"{matched_or_recorded.name} — {label}"))

    table = Table(show_header=True, header_style="bold", show_lines=False)
    table.add_column("", width=2)
    table.add_column("Check")
    table.add_column("Detail", style="dim")
    for mark, check, detail in rows:
        table.add_row(mark, check, detail)
    console.print(table)

    has_failure = any(row[0] == fail for row in rows)
    if has_failure:
        raise typer.Exit(1)


@app.command()
def current() -> None:
    """Show the currently active Codex account."""
    info = get_current()
    if info is None:
        if not list_accounts():
            console.print("[dim]No saved accounts yet.[/]")
        else:
            console.print(
                "[dim]Current auth is not linked to a saved account.[/]"
            )
        return

    if info.is_active:
        console.print(f"[bold green]✓[/] [cyan]{info.name}[/] (active)")
    else:
        console.print(
            f"[yellow]~[/] [cyan]{info.name}[/] "
            "(recorded, live auth differs)"
        )

    if info.summary:
        console.print(f"  {info.summary}")


@app.command()
def rename(
    old: str = typer.Argument(..., help="Current account name."),
    new: str = typer.Argument(..., help="New account name."),
) -> None:
    """Rename a saved Codex account."""
    try:
        rename_account(old, new)
        console.print(
            f"[bold green]✓[/] Renamed [cyan]{old}[/] → [cyan]{new}[/]"
        )
    except CodexSwitcherError as e:
        err_console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1) from None


@app.command()
def remove(
    name: str = typer.Argument(None, help="Account to remove. Omit for interactive picker."),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompt."
    ),
) -> None:
    """Remove a saved Codex account."""
    if name is None:
        _interactive_remove(yes)
        return
    _do_remove(name, yes)


def _interactive_remove(yes: bool) -> None:
    accounts = list_accounts()
    if not accounts:
        console.print("[dim]No saved accounts to remove.[/]")
        return

    table = Table(show_header=True, header_style="bold", show_lines=False, box=None)
    table.add_column("#", style="dim", width=4)
    table.add_column("Account")
    table.add_column("Info", style="dim")

    for i, acc in enumerate(accounts, 1):
        marker = (
            "[green]*[/]"
            if acc.is_active
            else ("[yellow]~[/]" if acc.is_recorded_only else "")
        )
        label = f"{marker} {acc.name}" if marker else acc.name
        summary = acc.summary or ""
        table.add_row(str(i), label, summary)

    console.print()
    console.print(table)
    console.print()

    choice = Prompt.ask(
        "[bold]Remove which account[/]",
        choices=[str(i) for i in range(1, len(accounts) + 1)]
        + [a.name for a in accounts],
        default="",
        console=console,
    )

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(accounts):
            chosen = accounts[idx].name
        else:
            err_console.print("[bold red]Error:[/] Invalid selection.")
            raise typer.Exit(1)
    else:
        chosen = choice

    _do_remove(chosen, yes)


def _do_remove(name: str, yes: bool) -> None:
    if not yes:
        really = typer.confirm(f"Remove account '{name}'?")
        if not really:
            console.print("[dim]Cancelled.[/]")
            raise typer.Exit()

    try:
        remove_account(name)
        console.print(f"[bold green]✓[/] Removed account [cyan]{name}[/]")
    except CodexSwitcherError as e:
        err_console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1) from None
