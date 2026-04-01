import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

DATA_FILE = Path(__file__).parent / "data.json"
COLUMNS = ["Backlog", "Running", "Review", "Done", "Failed"]

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def load():
    if not DATA_FILE.exists():
        return init_data()
    with open(DATA_FILE) as f:
        return json.load(f)


def save(data):
    tmp = DATA_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, DATA_FILE)


def init_data():
    proj_id = new_id("proj")
    data = {
        "active_project_id": proj_id,
        "projects": [
            {
                "id": proj_id,
                "name": "My Project",
                "created_at": now(),
                "columns": {col: [] for col in COLUMNS},
            }
        ],
    }
    save(data)
    return data


def now():
    return datetime.utcnow().isoformat()


def new_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def find_project(data, proj_id):
    for p in data["projects"]:
        if p["id"] == proj_id:
            return p
    return None


def project_summary(project):
    counts = {col: len(project["columns"][col]) for col in COLUMNS}
    return {
        "id": project["id"],
        "name": project["name"],
        "created_at": project["created_at"],
        "card_counts": counts,
    }


def find_card(project, card_id):
    for col in COLUMNS:
        for card in project["columns"][col]:
            if card["id"] == card_id:
                return card, col
    return None, None


def reorder(cards):
    for i, card in enumerate(cards):
        card["order"] = i


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# --- Projects ---

@app.route("/api/projects", methods=["GET"])
def list_projects():
    data = load()
    return jsonify({
        "active_project_id": data["active_project_id"],
        "projects": [project_summary(p) for p in data["projects"]],
    })


@app.route("/api/projects", methods=["POST"])
def create_project():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    data = load()
    proj = {
        "id": new_id("proj"),
        "name": name,
        "created_at": now(),
        "columns": {col: [] for col in COLUMNS},
    }
    data["projects"].append(proj)
    data["active_project_id"] = proj["id"]
    save(data)
    return jsonify(project_summary(proj)), 201


@app.route("/api/projects/<proj_id>", methods=["DELETE"])
def delete_project(proj_id):
    data = load()
    if len(data["projects"]) <= 1:
        return jsonify({"error": "Cannot delete the only project"}), 409
    project = find_project(data, proj_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    data["projects"] = [p for p in data["projects"] if p["id"] != proj_id]
    if data["active_project_id"] == proj_id:
        data["active_project_id"] = data["projects"][0]["id"]
    save(data)
    return jsonify({"active_project_id": data["active_project_id"]})


@app.route("/api/projects/<proj_id>/board", methods=["GET"])
def get_board(proj_id):
    data = load()
    project = find_project(data, proj_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project)


@app.route("/api/active", methods=["PUT"])
def set_active():
    body = request.get_json(silent=True) or {}
    proj_id = body.get("project_id", "")
    data = load()
    if not find_project(data, proj_id):
        return jsonify({"error": "Project not found"}), 404
    data["active_project_id"] = proj_id
    save(data)
    return jsonify({"active_project_id": proj_id})


# --- Cards ---

@app.route("/api/projects/<proj_id>/cards", methods=["POST"])
def add_card(proj_id):
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    col = body.get("column", "Backlog")
    description = (body.get("description") or "").strip()

    if not title:
        return jsonify({"error": "title is required"}), 400
    if col not in COLUMNS:
        return jsonify({"error": f"column must be one of {COLUMNS}"}), 400

    data = load()
    project = find_project(data, proj_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404

    card = {
        "id": new_id("card"),
        "title": title,
        "description": description,
        "created_at": now(),
        "order": len(project["columns"][col]),
    }
    project["columns"][col].append(card)
    save(data)
    return jsonify(card), 201


@app.route("/api/projects/<proj_id>/cards/<card_id>", methods=["DELETE"])
def delete_card(proj_id, card_id):
    data = load()
    project = find_project(data, proj_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    card, col = find_card(project, card_id)
    if not card:
        return jsonify({"error": "Card not found"}), 404
    project["columns"][col] = [c for c in project["columns"][col] if c["id"] != card_id]
    reorder(project["columns"][col])
    save(data)
    return jsonify({"deleted": card_id})


@app.route("/api/projects/<proj_id>/cards/<card_id>", methods=["PATCH"])
def edit_card(proj_id, card_id):
    body = request.get_json(silent=True) or {}
    data = load()
    project = find_project(data, proj_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    card, _ = find_card(project, card_id)
    if not card:
        return jsonify({"error": "Card not found"}), 404
    if "title" in body:
        title = body["title"].strip()
        if not title:
            return jsonify({"error": "title cannot be empty"}), 400
        card["title"] = title
    if "description" in body:
        card["description"] = body["description"].strip()
    save(data)
    return jsonify(card)


@app.route("/api/projects/<proj_id>/cards/<card_id>/move", methods=["PUT"])
def move_card(proj_id, card_id):
    body = request.get_json(silent=True) or {}
    to_col = body.get("column")
    order = body.get("order", 9999)

    if to_col not in COLUMNS:
        return jsonify({"error": f"column must be one of {COLUMNS}"}), 400

    data = load()
    project = find_project(data, proj_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    card, from_col = find_card(project, card_id)
    if not card:
        return jsonify({"error": "Card not found"}), 404

    # Remove from source
    project["columns"][from_col] = [c for c in project["columns"][from_col] if c["id"] != card_id]
    reorder(project["columns"][from_col])

    # Insert into target at requested position
    target = project["columns"][to_col]
    order = max(0, min(order, len(target)))
    target.insert(order, card)
    reorder(target)

    save(data)
    return jsonify(project)


if __name__ == "__main__":
    load()  # ensure data.json is initialized
    app.run(debug=True, port=5000)
