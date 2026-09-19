"""work-ledger: pick a unit of work and reopen it in VS Code (or Claude Code).

With no subcommand, `work-ledger [words]` runs `open`: fuzzy-pick a task and open
its VS Code workspace with the key files and the task's .venv as interpreter.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import click

from work_ledger import config as config_mod
from work_ledger import install as install_mod
from work_ledger import ledger, vscode

# ------------------------------------------------------------------ display


def ago(ts: str | None) -> str:
    s = int((datetime.now(UTC) - ledger.parse_ts(ts)).total_seconds())
    if s < 3600:
        return f"{max(s // 60, 1)}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def where(task: dict) -> str:
    name = task.get("repo") or Path(task["folder"]).name
    if task.get("branch"):
        name += f":{task['branch']}"
    return name


def label(task: dict) -> str:
    title = task.get("title") or "(untitled)"
    if task.get("note"):
        title = f"[{task['note']}] {title}"
    if task.get("archived"):
        title = f"(archived) {title}"
    dirty = "*" if task.get("dirty_files") else " "
    return (
        f"{ago(task.get('last_seen')):>4} {dirty} {task['host']:<10.10} "
        f"{where(task):<40.40} {title}"
    )


def rel(path: str, folder: str) -> str:
    try:
        return str(Path(path).relative_to(folder))
    except ValueError:
        return path


def details(task: dict) -> str:
    lines = [
        f"{task.get('title') or '(untitled)'}",
        f"  note:        {task.get('note') or ''}",
        f"  last prompt: {task.get('last_prompt') or ''}",
        f"  host:        {task['host']}",
        f"  folder:      {task['folder']}",
        f"  branch:      {task.get('branch')}{'  (worktree)' if task.get('is_worktree') else ''}",
    ]
    lines += [f"  + folder:    {f}" for f in task.get("extra_folders") or []]
    lines += [
        f"  sessions:    {len(task['sessions'])}, last {ago(task.get('last_seen'))} ago",
        f"  id:          {task['id']}",
        "",
        f"Claude edited ({len(task['claude_files'])}):",
    ]
    lines += [f"  {rel(f, task['folder'])}" for f in reversed(task["claude_files"][-10:])]
    lines += ["", "Sessions:"]
    lines += [
        f"  {ago(s.get('last_seen')):>4}  {s.get('entrypoint') or '?':<12} {s.get('title') or ''}"
        for s in task["sessions"][:5]
    ]
    lines += ["", f"Uncommitted ({len(task['dirty_files'])}):"]
    lines += [f"  {f}" for f in task["dirty_files"][:10]]
    lines += ["", f"Changed on branch ({len(task['branch_files'])}):"]
    lines += [f"  {f}" for f in task["branch_files"][:10]]
    return "\n".join(lines)


# ------------------------------------------------------------------ picking


def pick(cfg: config_mod.Config, tasks: list[dict], query: str) -> dict:
    if not tasks:
        raise click.ClickException("no tasks in the ledger yet.")

    if shutil.which("fzf"):
        # The preview reads a cached file so moving the cursor stays fast.
        cache = cfg.ledger_dir / ".preview.json"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps([details(t) for t in tasks]), encoding="utf-8")
        code = f"import json,sys;print(json.load(open({str(cache)!r}))[int(sys.argv[1])])"
        preview = f"{shlex.quote(sys.executable)} -c {shlex.quote(code)} {{1}}"
        proc = subprocess.run(
            [
                "fzf",
                "--delimiter=\t",
                "--with-nth=2..",
                "--no-sort",
                "--query",
                query,
                "--preview",
                preview,
                "--preview-window=down,50%",
                "--header",
                "age  * = uncommitted changes",
            ],
            input="\n".join(f"{i}\t{label(t)}" for i, t in enumerate(tasks)),
            stdout=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            raise SystemExit(1)
        return tasks[int(proc.stdout.split("\t", 1)[0])]

    words = query.lower().split()
    shown = [t for t in tasks if all(w in label(t).lower() for w in words)][:30]
    if not shown:
        raise click.ClickException(f"nothing matches '{query}'.")
    if len(shown) == 1:
        return shown[0]
    for i, t in enumerate(shown, 1):
        click.echo(f"{i:>3}. {label(t)}", err=True)
    n = click.prompt("pick #", type=click.IntRange(1, len(shown)), err=True)
    return shown[n - 1]


def ssh_alias(cfg: config_mod.Config, task: dict) -> str:
    alias = cfg.remotes.get(task["host"])
    if not alias:
        raise click.ClickException(
            f"'{task.get('title')}' is on {task['host']}, which has no ssh alias. "
            f"Open it on {task['host']}, or run: "
            f"work-ledger install --remote {task['host']}=<alias>"
        )
    return alias


def remote_prepare(cfg: config_mod.Config, alias: str, tid: str) -> dict:
    cmd = ["ssh", "-o", "ConnectTimeout=6", alias, f"{cfg.remote_command} prepare {tid}"]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)  # stderr passes through
    if proc.returncode != 0:
        raise click.ClickException(f"prepare failed on {alias} (exit {proc.returncode}).")
    return json.loads(proc.stdout)


def run_or_print(cmd: list[str], dry_run: bool) -> None:
    if dry_run:
        click.echo(shlex.join(cmd))
        return
    if not (os.path.isabs(cmd[0]) or shutil.which(cmd[0])):
        raise click.ClickException(
            f"`{cmd[0]}` not found. In VS Code run 'Shell Command: Install code command in PATH'."
        )
    os.execvp(cmd[0], cmd)


# ------------------------------------------------------------------ CLI


class DefaultGroup(click.Group):
    """Runs `open` when the first argument isn't a subcommand."""

    default_cmd = "open"

    def parse_args(self, ctx, args):
        if not args or (args[0] not in self.commands and args[0] not in ("--help", "-h")):
            args.insert(0, self.default_cmd)
        return super().parse_args(ctx, args)


def picker_options(f):
    f = click.argument("query", nargs=-1)(f)
    f = click.option("--all", "include_archived", is_flag=True, help="Include archived tasks.")(f)
    return f


@click.group(cls=DefaultGroup, context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """Pick a unit of work and reopen it.

    With no subcommand, fuzzy-pick a task and open it in VS Code. Words you pass
    pre-filter the picker.
    """


@cli.command("open")
@picker_options
@click.option("--dry-run", is_flag=True, help="Print the VS Code command instead of running it.")
def open_(query, include_archived, dry_run):
    """Open a task in VS Code: workspace, key files, and its .venv interpreter (default)."""
    cfg = config_mod.load()
    task = pick(cfg, ledger.load_tasks(cfg, include_archived), " ".join(query))
    if task["host"] == cfg.host:
        try:
            prep = vscode.prepare(cfg, task)
        except FileNotFoundError as e:
            raise click.ClickException(str(e)) from e
        cmd = vscode.local_command(prep)
    else:
        alias = ssh_alias(cfg, task)
        prep = remote_prepare(cfg, alias, task["id"])
        cmd = vscode.remote_command(alias, prep)
    for m in prep.get("messages", []):
        click.echo(m, err=True)
    run_or_print(cmd, dry_run)


@cli.command()
@picker_options
@click.option("--dry-run", is_flag=True, help="Print the command instead of running it.")
def claude(query, include_archived, dry_run):
    """Resume the task's most recent Claude Code session."""
    cfg = config_mod.load()
    task = pick(cfg, ledger.load_tasks(cfg, include_archived), " ".join(query))
    session = task["sessions"][0]
    cwd, sid = session.get("cwd") or task["folder"], session["session_id"]
    if task["host"] != cfg.host:
        inner = f"cd {shlex.quote(cwd)} && exec claude --resume {shlex.quote(sid)}"
        cmd = ["ssh", "-t", ssh_alias(cfg, task), f"exec $SHELL -lc {shlex.quote(inner)}"]
        run_or_print(cmd, dry_run)
        return
    if not os.path.isdir(cwd):
        raise click.ClickException(f"{cwd} no longer exists.")
    if dry_run:
        click.echo(f"cd {shlex.quote(cwd)} && claude --resume {sid}")
        return
    os.chdir(cwd)
    run_or_print(["claude", "--resume", sid], dry_run)


@cli.command()
@picker_options
def path(query, include_archived):
    """Print a local task's folder. Shell use: cd "$(wl path)"."""
    cfg = config_mod.load()
    task = pick(cfg, ledger.load_tasks(cfg, include_archived, local_only=True), " ".join(query))
    click.echo(task["folder"])


@cli.command("list")
@click.option("--all", "include_archived", is_flag=True, help="Include archived tasks.")
@click.option("--local", is_flag=True, help="Skip fetching from remote hosts.")
def list_(include_archived, local):
    """Print recent tasks, newest first."""
    cfg = config_mod.load()
    for t in ledger.load_tasks(cfg, include_archived, local_only=local):
        click.echo(label(t))


@cli.command()
@picker_options
def show(query, include_archived):
    """Print a task's details."""
    cfg = config_mod.load()
    click.echo(details(pick(cfg, ledger.load_tasks(cfg, include_archived), " ".join(query))))


@cli.command()
@picker_options
@click.option("-m", "--message", help="Note text; prompts if omitted. Empty clears it.")
def note(query, include_archived, message):
    """Attach a short note to a task, like 'next: write tests'."""
    cfg = config_mod.load()
    task = pick(cfg, ledger.load_tasks(cfg, include_archived), " ".join(query))
    if message is None:
        message = click.prompt(
            f"note for '{task.get('title')}' (blank clears)", default="", show_default=False
        )
    ledger.save_meta(cfg, task, note=message.strip() or None)


@cli.command()
@click.argument("query", nargs=-1)
def archive(query):
    """Toggle a task's archived flag. Archived tasks are hidden by default."""
    cfg = config_mod.load()
    task = pick(cfg, ledger.load_tasks(cfg, include_archived=True), " ".join(query))
    ledger.save_meta(cfg, task, archived=not task.get("archived"))
    click.echo("unarchived" if task.get("archived") else "archived", err=True)


@cli.command("add-folder")
@click.argument("folder", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.argument("query", nargs=-1)
def add_folder(folder, query):
    """Add another repo or worktree to a local task's workspace (multi-repo work)."""
    cfg = config_mod.load()
    task = pick(cfg, ledger.load_tasks(cfg, local_only=True), " ".join(query))
    extra = [f for f in task.get("extra_folders") or [] if f != folder]
    ledger.save_meta(cfg, task, extra_folders=[*extra, folder])
    click.echo(f"added {folder} to '{task.get('title')}'", err=True)


@cli.command(hidden=True)
@click.argument("task_id")
def prepare(task_id):
    """Prepare a local task's workspace and print it as JSON (called over ssh)."""
    cfg = config_mod.load()
    task = ledger.find_task(cfg, task_id)
    if not task:
        raise click.ClickException(f"no task {task_id} on {cfg.host}.")
    try:
        click.echo(json.dumps(vscode.prepare(cfg, task)))
    except FileNotFoundError as e:
        raise click.ClickException(str(e)) from e


@cli.command(hidden=True)
def dump():
    """Print this host's session records as JSON lines (called over ssh)."""
    cfg = config_mod.load()
    for rec in ledger.read_local_sessions(cfg):
        if rec.get("host") == cfg.host:
            rec.pop("scan", None)
            click.echo(json.dumps(rec))


@cli.command()
@click.option("--host", help="Fixed name for this machine (default: short hostname).")
@click.option(
    "--ledger-dir", type=click.Path(file_okay=False), help="Ledger folder; may be synced."
)
@click.option(
    "--remote",
    "remotes",
    multiple=True,
    metavar="HOST=ALIAS",
    help="Host reachable over ssh, e.g. vm=devbox. Repeatable.",
)
@click.option(
    "--retention-days",
    type=int,
    help="Set Claude Code's cleanupPeriodDays (default 30) so transcripts last longer.",
)
def install(host, ledger_dir, remotes, retention_days):
    """Write this machine's config and add the hook to Claude Code settings. Safe to re-run."""
    cfg = config_mod.load()
    if host:
        cfg.host = host
    if ledger_dir:
        cfg.ledger_dir = Path(ledger_dir).expanduser().resolve()
    for item in remotes:
        name, sep, alias = item.partition("=")
        if not sep or not name or not alias:
            raise click.BadParameter(f"expected HOST=ALIAS, got {item!r}", param_hint="--remote")
        cfg.remotes[name] = alias

    cfg_path = config_mod.save(cfg)
    cfg.ledger_dir.mkdir(parents=True, exist_ok=True)
    settings = install_mod.claude_settings_path()
    command = install_mod.hook_command()
    backup = install_mod.apply(settings, command, retention_days)

    click.echo(f"host:     {cfg.host}")
    click.echo(f"ledger:   {cfg.ledger_dir}")
    click.echo(f"remotes:  {cfg.remotes or '(none)'}")
    click.echo(f"config:   {cfg_path}")
    click.echo(f"hooks:    {settings}" + (f"  (backup: {backup.name})" if backup else ""))
    click.echo(f"command:  {command}")
    if not shutil.which("fzf"):
        click.echo("note: fzf not found; the picker will use a numbered menu.")
    if not vscode.code_bin():
        click.echo("note: VS Code's `code` command not found on PATH.")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
