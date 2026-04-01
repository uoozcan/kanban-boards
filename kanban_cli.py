#!/usr/bin/env python3
"""
Kanban CLI — for Claude Code / Codex to automatically update job packages.

Usage examples:
  python kanban_cli.py list
  python kanban_cli.py add   --project "HLA Pipeline" --column Backlog --title "Run benchmark"
  python kanban_cli.py move  --project "HLA Pipeline" --title "Run benchmark" --column Running
  python kanban_cli.py done  --project "HLA Pipeline" --title "Run benchmark"
  python kanban_cli.py fail  --project "HLA Pipeline" --title "Run benchmark"
  python kanban_cli.py delete --project "HLA Pipeline" --title "Run benchmark"

All commands operate directly on data.json — no server required.
"""

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data.json"
COLUMNS = ["Backlog", "Running", "Review", "Done", "Failed"]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load():
    if not DATA_FILE.exists():
        sys.exit(f"[kanban] data.json not found at {DATA_FILE}\n"
                 "Start the server once to initialise it: python app.py")
    with open(DATA_FILE) as f:
        return json.load(f)


def save(data):
    tmp = DATA_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, DATA_FILE)


def now():
    return datetime.utcnow().isoformat()


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def git_push(message):
    """Commit data.json and push to GitHub. Silently skips if git isn't configured."""
    repo = DATA_FILE.parent
    try:
        # Stage only data.json to avoid committing unrelated files
        subprocess.run(["git", "add", "data.json"], cwd=repo, check=True,
                       capture_output=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo, capture_output=True
        )
        if result.returncode == 0:
            return  # nothing changed, skip commit
        subprocess.run(
            ["git", "commit", "-m", f"[kanban] {message}"],
            cwd=repo, check=True, capture_output=True
        )
        push = subprocess.run(
            ["git", "push"],
            cwd=repo, capture_output=True, text=True
        )
        if push.returncode == 0:
            print("[kanban] Pushed to GitHub")
        else:
            print(f"[kanban] Warning: git push failed — {push.stderr.strip()}")
            print("[kanban] Run 'git push' manually in the kanban/ folder")
    except FileNotFoundError:
        pass  # git not available
    except subprocess.CalledProcessError as e:
        print(f"[kanban] Warning: git error — {e}")


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def find_project(data, name_or_id):
    """Match by exact name (case-insensitive) or by id prefix."""
    needle = name_or_id.lower()
    for p in data["projects"]:
        if p["id"].lower() == needle or p["name"].lower() == needle:
            return p
    # partial name match as fallback
    matches = [p for p in data["projects"] if needle in p["name"].lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        names = ", ".join(f'"{p["name"]}"' for p in matches)
        sys.exit(f'[kanban] Ambiguous project name "{name_or_id}": matches {names}')
    sys.exit(f'[kanban] Project not found: "{name_or_id}"')


def find_card(project, title_or_id):
    """Find a card across all columns by title (case-insensitive) or id."""
    needle = title_or_id.lower()
    found = []
    for col in COLUMNS:
        for card in project["columns"][col]:
            if card["id"].lower() == needle or card["title"].lower() == needle:
                found.append((card, col))
    if not found:
        # partial title match
        for col in COLUMNS:
            for card in project["columns"][col]:
                if needle in card["title"].lower():
                    found.append((card, col))
    if len(found) == 1:
        return found[0]
    if len(found) > 1:
        descs = ", ".join(f'"{c["title"]}" [{col}]' for c, col in found)
        sys.exit(f'[kanban] Ambiguous card title "{title_or_id}": {descs}')
    sys.exit(f'[kanban] Card not found: "{title_or_id}"')


def reorder(cards):
    for i, card in enumerate(cards):
        card["order"] = i


def active_project(data, args):
    """Return the project specified by --project, or the active project."""
    if args.project:
        return find_project(data, args.project)
    pid = data.get("active_project_id")
    for p in data["projects"]:
        if p["id"] == pid:
            return p
    return data["projects"][0]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args):
    data = load()
    for p in data["projects"]:
        active_marker = " *" if p["id"] == data.get("active_project_id") else ""
        print(f"\n[{p['name']}]{active_marker}  (id: {p['id']})")
        for col in COLUMNS:
            cards = sorted(p["columns"][col], key=lambda c: c["order"])
            if cards:
                print(f"  {col}:")
                for card in cards:
                    desc = f" — {card['description']}" if card.get("description") else ""
                    print(f"    • {card['title']}{desc}  (id: {card['id']})")
            else:
                print(f"  {col}: (empty)")
    print()


def cmd_add(args):
    if not args.title:
        sys.exit("[kanban] --title is required for add")
    col = args.column or "Backlog"
    if col not in COLUMNS:
        sys.exit(f"[kanban] --column must be one of: {', '.join(COLUMNS)}")

    data = load()
    project = active_project(data, args)
    card = {
        "id": new_id("card"),
        "title": args.title,
        "description": args.description or "",
        "created_at": now(),
        "order": len(project["columns"][col]),
    }
    project["columns"][col].append(card)
    save(data)
    print(f"[kanban] Added '{card['title']}' to {col} in [{project['name']}]  (id: {card['id']})")
    git_push(f"add '{card['title']}' to {col} [{project['name']}]")


def cmd_move(args):
    if not args.title:
        sys.exit("[kanban] --title (or card id) is required for move")
    to_col = args.column
    if not to_col:
        sys.exit("[kanban] --column is required for move")
    if to_col not in COLUMNS:
        sys.exit(f"[kanban] --column must be one of: {', '.join(COLUMNS)}")

    data = load()
    project = active_project(data, args)
    card, from_col = find_card(project, args.title)

    if from_col == to_col:
        print(f"[kanban] '{card['title']}' is already in {to_col}")
        return

    project["columns"][from_col] = [c for c in project["columns"][from_col] if c["id"] != card["id"]]
    reorder(project["columns"][from_col])
    project["columns"][to_col].append(card)
    reorder(project["columns"][to_col])
    save(data)
    print(f"[kanban] Moved '{card['title']}' from {from_col} → {to_col} in [{project['name']}]")
    git_push(f"move '{card['title']}' {from_col} → {to_col} [{project['name']}]")


def cmd_done(args):
    args.column = "Done"
    cmd_move(args)


def cmd_fail(args):
    args.column = "Failed"
    cmd_move(args)


def cmd_delete(args):
    if not args.title:
        sys.exit("[kanban] --title (or card id) is required for delete")

    data = load()
    project = active_project(data, args)
    card, col = find_card(project, args.title)
    project["columns"][col] = [c for c in project["columns"][col] if c["id"] != card["id"]]
    reorder(project["columns"][col])
    save(data)
    print(f"[kanban] Deleted '{card['title']}' from {col} in [{project['name']}]")
    git_push(f"delete '{card['title']}' from {col} [{project['name']}]")


def cmd_start(args):
    """Convenience: move card to Running (signal work has begun)."""
    args.column = "Running"
    cmd_move(args)


def cmd_review(args):
    """Convenience: move card to Review."""
    args.column = "Review"
    cmd_move(args)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

COMMANDS = {
    "list":   (cmd_list,   "List all projects and their job packages"),
    "add":    (cmd_add,    "Add a new job package"),
    "move":   (cmd_move,   "Move a job package to a different column"),
    "done":   (cmd_done,   "Mark a job package as Done"),
    "fail":   (cmd_fail,   "Mark a job package as Failed"),
    "start":  (cmd_start,  "Mark a job package as Running (work started)"),
    "review": (cmd_review, "Mark a job package as under Review"),
    "delete": (cmd_delete, "Delete a job package"),
}


def build_parser():
    parser = argparse.ArgumentParser(
        description="Kanban CLI — update job packages from the command line or AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {k:8s}  {v[1]}" for k, v in COMMANDS.items()),
    )
    parser.add_argument("command", choices=COMMANDS.keys())
    parser.add_argument("--project",     "-p", help="Project name or id (default: active project)")
    parser.add_argument("--title",       "-t", help="Card title or id")
    parser.add_argument("--column",      "-c", help=f"Column: {', '.join(COLUMNS)}")
    parser.add_argument("--description", "-d", help="Card description (for add)")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    COMMANDS[args.command][0](args)


if __name__ == "__main__":
    main()
