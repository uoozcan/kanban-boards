# Kanban Boards

Multi-project Kanban board updated automatically by Claude Code and Codex.

## Projects

All project boards live in `data.json`. Each project has five columns:

| Column  | Meaning                                     |
|---------|---------------------------------------------|
| Backlog | Planned, not started                        |
| Running | Actively being worked on                    |
| Review  | Done by AI, waiting for human review        |
| Done    | Completed successfully                      |
| Failed  | Blocked, errored, or cancelled              |

## Run the web UI locally

```bash
pip install flask
python app.py
# Open http://localhost:5000
```

## CLI (for humans and AI agents)

```bash
python kanban_cli.py list
python kanban_cli.py add    --project "My Project" --column Backlog --title "New task"
python kanban_cli.py start  --title "New task"       # → Running
python kanban_cli.py done   --title "New task"       # → Done
python kanban_cli.py fail   --title "New task"       # → Failed
python kanban_cli.py review --title "New task"       # → Review
python kanban_cli.py delete --title "New task"
```

Every CLI change is automatically committed and pushed to this repository.

## Sync to your local machine

```bash
git clone https://github.com/uoozcan/kanban-boards.git
cd kanban-boards
pip install flask
python app.py
```

Pull latest updates anytime:
```bash
git pull
```
