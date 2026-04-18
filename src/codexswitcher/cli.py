from __future__ import annotations

import shutil
import subprocess

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from codexswitcher import __version__
from codexswitcher import config as cfg
from codexswitcher.core import (
    AccountAlreadyActiveError,
    CodexSwitcherError,
    get_current,
    kill_login_server,
    list_accounts,
    remove_account,
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

    subprocess.run([codex_bin, "login"], check=False)

    if not cfg.AUTH_FILE.exists():
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


def _do_save(name: str) -> None:
    try:
        dest = save_account(name)
        console.print(f"[bold green]✓[/] Saved current auth as [cyan]{name}[/]")
        console.print(f"  {dest}")
    except CodexSwitcherError as e:
        err_console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1) from None


@app.command()
def save(
    name: str = typer.Argument(..., help="Name for this account profile."),
) -> None:
    """Save the current Codex auth as a named account."""
    _do_save(name)


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
        console.print("[dim]Restart Codex if it is already running.[/]")
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

    current = get_current()
    default_hint = current.name if current else None

    choice = Prompt.ask(
        "[bold]Switch to[/]",
        choices=[str(i) for i in range(1, len(accounts) + 1)]
        + [a.name for a in accounts],
        default=default_hint or "1",
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
def list_cmd() -> None:
    """List all saved Codex accounts."""
    accounts = list_accounts()
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
