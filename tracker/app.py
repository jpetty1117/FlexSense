from __future__ import annotations

import io
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename

import pptx_export
from tracker_core import (
    APP_META_FILE,
    CAD_FILES_DIR,
    BUCKET_LABEL,
    NOTE_CATEGORIES,
    NOTE_CATEGORY_LABELS,
    OWNER_INFO,
    OWNER_KEYS,
    SORT_OPTIONS,
    STATUSES,
    TASK_ORDER,
    TASKS,
    bucket_for,
    bom_summary,
    build_csv_bytes,
    build_gan_bytes,
    compute_labor_status_rows,
    compute_week_number,
    get_entry,
    load_bom_state,
    load_cad_state,
    load_or_init_demo_date,
    find_cad_design,
    find_cad_version,
    load_state,
    load_timesheet_state,
    next_bom_id,
    next_cad_version_number,
    normalize_state,
    parse_timesheet,
    remaining_hours,
    save_bom_state,
    save_cad_state,
    save_state,
    save_timesheet_state,
    sorted_filtered_ids,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "squish-therapy-local-dev-key")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # CAD STEP uploads can be much larger than timesheets

SITE_PASSWORD = os.environ.get("SQUISH_PASSWORD", "Squish_Therapy679?")


@app.before_request
def require_login():
    exempt_endpoints = {"login", "static"}
    if request.endpoint in exempt_endpoints or (request.endpoint and request.endpoint.startswith("static")):
        return None
    if not session.get("authenticated"):
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == SITE_PASSWORD:
            session["authenticated"] = True
            flash("Welcome to Squish Therapy Tracker!", "success")
            return redirect(url_for("tasks_page"))
        else:
            flash("Incorrect password. Access denied.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("authenticated", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.template_filter("shortdate")
def shortdate(d):
    if not d:
        return ""
    if isinstance(d, str):
        try:
            d = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            return d
    return f"{d.month}/{d.day}/{str(d.year)[2:]}"


def _state():
    state = normalize_state(load_state())
    save_state(state)
    return state


def _task_payload(tid, state=None, today=None):
    if tid not in TASKS:
        abort(404)
    state = state or _state()
    today = today or date.today()
    task = TASKS[tid]
    entry = get_entry(state, tid)
    return {
        **task,
        "start_iso": task["start"].isoformat(),
        "end_iso": task["end"].isoformat(),
        "entry": entry,
        "bucket": bucket_for(task, entry, today),
        "note_count": len(entry.get("note_entries", [])),
    }


@app.route("/")
@app.route("/tasks")
def tasks_page():
    state = _state()
    today = date.today()
    demo_date = load_or_init_demo_date()
    filter_key = request.args.get("filter", "all")
    if filter_key not in {"all", "overdue", "soon", "upcoming", "complete"}:
        filter_key = "all"
    sort_mode = request.args.get("sort", SORT_OPTIONS[0])
    if sort_mode not in SORT_OPTIONS:
        sort_mode = SORT_OPTIONS[0]

    counts = {"overdue": 0, "soon": 0, "upcoming": 0, "complete": 0}
    for tid in TASK_ORDER:
        entry = get_entry(state, tid)
        counts[bucket_for(TASKS[tid], entry, today)] += 1
    counts["all"] = len(TASK_ORDER)

    ids = sorted_filtered_ids(state, today, filter_key, sort_mode)
    task_rows = [_task_payload(tid, state=state, today=today) for tid in ids]
    complete_count = counts["complete"]
    progress_pct = (complete_count / len(TASK_ORDER) * 100) if TASK_ORDER else 0
    remaining = remaining_hours(state)
    weeks_left = (demo_date - today).days / 7
    pace = remaining / weeks_left if weeks_left > 0 else remaining

    return render_template(
        "tasks.html",
        active_tab="tasks",
        today=today,
        demo_date=demo_date,
        tasks=task_rows,
        counts=counts,
        current_filter=filter_key,
        sort_mode=sort_mode,
        sort_options=SORT_OPTIONS,
        statuses=STATUSES,
        owner_keys=OWNER_KEYS,
        owner_info=OWNER_INFO,
        progress_pct=progress_pct,
        complete_count=complete_count,
        total_tasks=len(TASK_ORDER),
        remaining=remaining,
        weeks_left=weeks_left,
        pace=pace,
        grouped=(sort_mode == "Plan order"),
        owner_grouped=(sort_mode == "Owner (A–Z)"),
    )


@app.patch("/api/tasks/<tid>")
def update_task(tid):
    if tid not in TASKS:
        return jsonify({"error": "Unknown task"}), 404
    payload = request.get_json(silent=True) or {}
    state = _state()
    entry = get_entry(state, tid)

    if "status" in payload:
        if payload["status"] not in STATUSES:
            return jsonify({"error": "Invalid status"}), 400
        entry["status"] = payload["status"]
    if "owner" in payload:
        if payload["owner"] not in [""] + OWNER_KEYS:
            return jsonify({"error": "Invalid owner"}), 400
        entry["owner"] = payload["owner"]
    if "revised" in payload:
        revised = (payload["revised"] or "").strip()
        if revised:
            try:
                datetime.strptime(revised, "%Y-%m-%d")
            except ValueError:
                return jsonify({"error": "Revised end must be YYYY-MM-DD"}), 400
        entry["revised"] = revised

    save_state(state)
    task = TASKS[tid]
    return jsonify({
        "ok": True,
        "entry": entry,
        "bucket": bucket_for(task, entry, date.today()),
        "remaining_hours": remaining_hours(state),
    })


@app.post("/api/tasks/bulk")
def bulk_update_tasks():
    payload = request.get_json(silent=True) or {}
    updates = payload.get("tasks", [])
    state = _state()
    errors = []
    for item in updates:
        tid = item.get("id")
        if tid not in TASKS:
            errors.append(f"Unknown task {tid}")
            continue
        entry = get_entry(state, tid)
        status = item.get("status", entry["status"])
        owner = item.get("owner", entry.get("owner", ""))
        revised = (item.get("revised", entry.get("revised", "")) or "").strip()
        if status not in STATUSES:
            errors.append(f"{tid}: invalid status")
            continue
        if owner not in [""] + OWNER_KEYS:
            errors.append(f"{tid}: invalid owner")
            continue
        if revised:
            try:
                datetime.strptime(revised, "%Y-%m-%d")
            except ValueError:
                errors.append(f"{tid}: revised date must be YYYY-MM-DD")
                continue
        entry.update({"status": status, "owner": owner, "revised": revised})
    save_state(state)
    return jsonify({"ok": not errors, "errors": errors, "remaining_hours": remaining_hours(state)})


@app.get("/api/tasks/<tid>/notes")
def get_notes(tid):
    if tid not in TASKS:
        return jsonify({"error": "Unknown task"}), 404
    state = _state()
    entry = get_entry(state, tid)
    return jsonify({
        "task": {"id": tid, "name": TASKS[tid]["name"]},
        "notes": entry.get("note_entries", []),
        "categories": [{"key": k, "label": label} for k, label in NOTE_CATEGORIES],
    })


@app.post("/api/tasks/<tid>/notes")
def add_note(tid):
    if tid not in TASKS:
        return jsonify({"error": "Unknown task"}), 404
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    category = payload.get("category", "note")
    date_str = (payload.get("date") or "").strip()
    if not text:
        return jsonify({"error": "Note text is required"}), 400
    valid_categories = {k for k, _ in NOTE_CATEGORIES}
    if category not in valid_categories:
        return jsonify({"error": "Invalid category"}), 400
    if date_str:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Date must be YYYY-MM-DD"}), 400

    state = _state()
    entry = get_entry(state, tid)
    entry["note_entries"].append({"date": date_str, "category": category, "text": text})
    save_state(state)
    return jsonify({"ok": True, "notes": entry["note_entries"]})


@app.put("/api/tasks/<tid>/notes/<int:index>")
def edit_note(tid, index):
    if tid not in TASKS:
        return jsonify({"error": "Unknown task"}), 404
    payload = request.get_json(silent=True) or {}
    state = _state()
    entry = get_entry(state, tid)
    notes = entry["note_entries"]
    if index < 0 or index >= len(notes):
        return jsonify({"error": "Note not found"}), 404
    text = (payload.get("text") or "").strip()
    category = payload.get("category", "note")
    date_str = (payload.get("date") or "").strip()
    if not text:
        return jsonify({"error": "Note text is required"}), 400
    if category not in {k for k, _ in NOTE_CATEGORIES}:
        return jsonify({"error": "Invalid category"}), 400
    if date_str:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Date must be YYYY-MM-DD"}), 400
    notes[index] = {"date": date_str, "category": category, "text": text}
    save_state(state)
    return jsonify({"ok": True, "notes": notes})


@app.delete("/api/tasks/<tid>/notes/<int:index>")
def delete_note(tid, index):
    if tid not in TASKS:
        return jsonify({"error": "Unknown task"}), 404
    state = _state()
    entry = get_entry(state, tid)
    notes = entry["note_entries"]
    if index < 0 or index >= len(notes):
        return jsonify({"error": "Note not found"}), 404
    del notes[index]
    save_state(state)
    return jsonify({"ok": True, "notes": notes})


@app.get("/export/csv")
def export_csv():
    data = build_csv_bytes(_state(), date.today())
    return send_file(io.BytesIO(data), mimetype="text/csv", as_attachment=True, download_name="tracker_export.csv")


@app.get("/export/gan")
def export_gan():
    data = build_gan_bytes(_state(), date.today())
    return send_file(io.BytesIO(data), mimetype="application/xml", as_attachment=True, download_name="tracker_export.gan")


@app.route("/timesheets", methods=["GET", "POST"])
def timesheets_page():
    if request.method == "POST":
        files = request.files.getlist("timesheets")
        if not files or all(not f.filename for f in files):
            flash("Choose one or more .xlsx timesheets first.", "warning")
            return redirect(url_for("timesheets_page"))
        ts_state = load_timesheet_state()
        loaded = 0
        errors = []
        for uploaded in files:
            if not uploaded.filename:
                continue
            if not uploaded.filename.lower().endswith(".xlsx"):
                errors.append(f"{uploaded.filename}: not an .xlsx file")
                continue
            try:
                uploaded.stream.seek(0)
                rec = parse_timesheet(uploaded.stream)
                member = ts_state.setdefault(rec["name"], {})
                member[rec["week_key"]] = {
                    "predicted": rec["predicted"],
                    "actual": rec["actual"],
                    "next_week": rec["next_week"],
                    "loaded_at": datetime.now().isoformat(timespec="seconds"),
                }
                loaded += 1
            except Exception as exc:
                errors.append(f"{uploaded.filename}: {exc}")
        save_timesheet_state(ts_state)
        flash(f"Loaded {loaded} timesheet(s).", "success" if loaded else "warning")
        for err in errors:
            flash(err, "warning")
        return redirect(url_for("timesheets_page"))

    ts_state = load_timesheet_state()
    member_rows, team_total = compute_labor_status_rows(ts_state)
    return render_template(
        "timesheets.html",
        active_tab="timesheets",
        member_rows=member_rows,
        team_total=team_total,
        has_data=bool(member_rows),
    )


@app.post("/timesheets/clear")
def clear_timesheets():
    save_timesheet_state({})
    flash("All timesheet history was cleared.", "success")
    return redirect(url_for("timesheets_page"))


# ---------------------------------------------------------------------------
# Bill of Materials
# ---------------------------------------------------------------------------
@app.get("/bom")
def bom_page():
    bom = load_bom_state()
    return render_template(
        "bom.html",
        active_tab="bom",
        bom=bom,
        items=bom.get("items", []),
        summary=bom_summary(bom),
        extra_label=bom.get("columns", {}).get("extra_label", "Weight / Extra"),
    )


@app.post("/api/bom/items")
def add_bom_item():
    payload = request.get_json(silent=True) or {}
    bom = load_bom_state()
    item = {
        "id": next_bom_id(bom),
        "category": str(payload.get("category", "")).strip(),
        "part": str(payload.get("part", "")).strip(),
        "part_number": str(payload.get("part_number", "")).strip(),
        "vendor": str(payload.get("vendor", "")).strip(),
        "price_link": payload.get("price_link", ""),
        "link": str(payload.get("link", "")).strip(),
        "notes": str(payload.get("notes", "")).strip(),
        "extra": str(payload.get("extra", "")).strip(),
    }
    bom.setdefault("items", []).append(item)
    save_bom_state(bom)
    return jsonify({"ok": True, "item": item, "summary": bom_summary(bom)})


@app.patch("/api/bom/items/<int:item_id>")
def update_bom_item(item_id):
    payload = request.get_json(silent=True) or {}
    bom = load_bom_state()
    item = next((x for x in bom.get("items", []) if int(x.get("id", -1)) == item_id), None)
    if item is None:
        return jsonify({"error": "BOM item not found"}), 404
    allowed = {"category", "part", "part_number", "vendor", "price_link", "link", "notes", "extra"}
    for key in allowed:
        if key not in payload:
            continue
        value = payload[key]
        if key == "price_link":
            item[key] = "" if value is None else value
        else:
            item[key] = "" if value is None else str(value).strip()
    # Once a row is edited in the tracker it is no longer tied to a particular
    # spreadsheet row; keep source_row only as historical import metadata.
    save_bom_state(bom)
    return jsonify({"ok": True, "item": item, "summary": bom_summary(bom)})


@app.delete("/api/bom/items/<int:item_id>")
def delete_bom_item(item_id):
    bom = load_bom_state()
    before = len(bom.get("items", []))
    bom["items"] = [x for x in bom.get("items", []) if int(x.get("id", -1)) != item_id]
    if len(bom["items"]) == before:
        return jsonify({"error": "BOM item not found"}), 404
    save_bom_state(bom)
    return jsonify({"ok": True, "summary": bom_summary(bom)})


@app.patch("/api/bom/settings")
def update_bom_settings():
    payload = request.get_json(silent=True) or {}
    bom = load_bom_state()
    if "budget" in payload:
        try:
            budget = float(payload["budget"])
            if budget < 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "Budget must be a non-negative number."}), 400
        bom["budget"] = budget
    save_bom_state(bom)
    return jsonify({"ok": True, "summary": bom_summary(bom)})


@app.get("/export/bom.csv")
def export_bom_csv():
    import csv
    bom = load_bom_state()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Category", "Part", "Part # / Description", "Vendor", "Price", "Part Link", "Notes", bom.get("columns", {}).get("extra_label", "Weight / Extra")])
    for item in bom.get("items", []):
        writer.writerow([
            item.get("category", ""), item.get("part", ""), item.get("part_number", ""),
            item.get("vendor", ""), item.get("price_link", ""), item.get("link", ""),
            item.get("notes", ""), item.get("extra", ""),
        ])
    data = out.getvalue().encode("utf-8-sig")
    return send_file(io.BytesIO(data), mimetype="text/csv", as_attachment=True, download_name="Squish_Therapy_BOM.csv")


# ---------------------------------------------------------------------------
# CAD model version library
# ---------------------------------------------------------------------------

def _cad_slug(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "design"


def _cad_find_or_404(design_id, version_id=None):
    state = load_cad_state()
    design = find_cad_design(state, design_id)
    if design is None:
        abort(404)
    if version_id is None:
        return state, design, None
    version = find_cad_version(design, version_id)
    if version is None:
        abort(404)
    return state, design, version


@app.get("/cad")
def cad_page():
    state = load_cad_state()
    designs = [d for d in state.get("designs", []) if isinstance(d, dict)]
    designs.sort(key=lambda d: (d.get("name") or "").lower())

    selected_design = None
    selected_version = None
    wanted_design = request.args.get("design", "")
    wanted_version = request.args.get("version", "")

    if wanted_design:
        selected_design = find_cad_design(state, wanted_design)
    if selected_design is None and designs:
        selected_design = designs[0]

    if selected_design:
        versions = sorted(
            selected_design.get("versions", []),
            key=lambda v: int(v.get("version_number", 0) or 0),
            reverse=True,
        )
        if wanted_version:
            selected_version = find_cad_version(selected_design, wanted_version)
        if selected_version is None and versions:
            selected_version = versions[0]
    else:
        versions = []

    return render_template(
        "cad.html",
        active_tab="cad",
        designs=designs,
        selected_design=selected_design,
        selected_version=selected_version,
        versions=versions,
    )


@app.post("/cad/upload")
def cad_upload():
    uploaded = request.files.get("cad_file")
    if uploaded is None or not uploaded.filename:
        flash("Choose a .STEP or .STP file first.", "warning")
        return redirect(url_for("cad_page"))

    original_name = secure_filename(uploaded.filename)
    ext = Path(original_name).suffix.lower()
    if ext not in {".step", ".stp"}:
        flash("CAD uploads currently support .STEP and .STP files.", "warning")
        return redirect(url_for("cad_page"))

    state = load_cad_state()
    design_id = (request.form.get("design_id") or "").strip()
    if design_id == "__new__":
        design_name = (request.form.get("design_name") or "").strip()
        if not design_name:
            flash("Enter a design name for a new CAD design.", "warning")
            return redirect(url_for("cad_page"))
        if any((d.get("name") or "").strip().lower() == design_name.lower() for d in state.get("designs", [])):
            flash("A design with that name already exists. Choose it from the Existing Design list to upload a new version.", "warning")
            return redirect(url_for("cad_page"))
        base = _cad_slug(design_name)
        existing_ids = {d.get("id") for d in state.get("designs", [])}
        new_id = base
        counter = 2
        while new_id in existing_ids:
            new_id = f"{base}-{counter}"
            counter += 1
        design = {
            "id": new_id,
            "name": design_name,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "versions": [],
        }
        state.setdefault("designs", []).append(design)
    else:
        design = find_cad_design(state, design_id)
        if design is None:
            flash("Choose an existing design or select New design.", "warning")
            return redirect(url_for("cad_page"))

    version_number = next_cad_version_number(design)
    version_id = f"v{version_number:03d}-{uuid.uuid4().hex[:8]}"
    label = (request.form.get("version_label") or "").strip() or f"Version {version_number}"
    change_summary = (request.form.get("change_summary") or "").strip()
    notes = (request.form.get("notes") or "").strip()

    design_dir = CAD_FILES_DIR / design["id"]
    design_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{version_id}_{original_name}"
    file_path = design_dir / stored_name
    uploaded.save(file_path)

    version = {
        "id": version_id,
        "version_number": version_number,
        "label": label,
        "original_filename": original_name,
        "stored_filename": stored_name,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "change_summary": change_summary,
        "notes": notes,
        "file_size": file_path.stat().st_size,
    }
    design.setdefault("versions", []).append(version)
    save_cad_state(state)
    flash(f"Uploaded {design['name']} — {label}. The previous versions were kept.", "success")
    return redirect(url_for("cad_page", design=design["id"], version=version_id))


@app.patch("/api/cad/<design_id>/<version_id>")
def cad_update_version(design_id, version_id):
    state, design, version = _cad_find_or_404(design_id, version_id)
    payload = request.get_json(silent=True) or {}
    for field in ("label", "change_summary", "notes"):
        if field in payload:
            version[field] = str(payload[field] or "").strip()
    save_cad_state(state)
    return jsonify({"ok": True, "version": version})


def _cad_file_path(design, version):
    path = CAD_FILES_DIR / design["id"] / version.get("stored_filename", "")
    try:
        resolved = path.resolve()
        root = CAD_FILES_DIR.resolve()
        resolved.relative_to(root)
    except (ValueError, OSError):
        abort(404)
    if not resolved.is_file():
        abort(404)
    return resolved


@app.get("/cad/model/<design_id>/<version_id>")
def cad_model_file(design_id, version_id):
    _, design, version = _cad_find_or_404(design_id, version_id)
    return send_file(_cad_file_path(design, version), mimetype="application/octet-stream", as_attachment=False)


@app.get("/cad/download/<design_id>/<version_id>")
def cad_download_file(design_id, version_id):
    _, design, version = _cad_find_or_404(design_id, version_id)
    return send_file(
        _cad_file_path(design, version),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=version.get("original_filename") or "model.step",
    )


@app.get("/slides")
def slides_page():
    today = date.today()
    demo_date = load_or_init_demo_date()
    default_from = today.replace()  # copy
    from datetime import timedelta
    default_from = today - timedelta(days=7)
    week_num = compute_week_number(today, demo_date)
    return render_template(
        "slides.html",
        active_tab="slides",
        today=today,
        demo_date=demo_date,
        default_from=default_from,
        week_num=week_num,
        owner_keys=OWNER_KEYS,
        owner_info=OWNER_INFO,
    )


@app.get("/api/slide-candidates")
def slide_candidates():
    state = _state()
    from_str = request.args.get("from", "")
    to_str = request.args.get("to", "")
    owners = request.args.getlist("owner") or OWNER_KEYS
    try:
        range_from = datetime.strptime(from_str, "%Y-%m-%d").date()
        range_to = datetime.strptime(to_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "From/To dates must be YYYY-MM-DD"}), 400

    results = []
    for owner_key in owners:
        if owner_key not in OWNER_INFO:
            continue
        full_name, role = OWNER_INFO[owner_key]
        items = []
        for tid in TASK_ORDER:
            entry = get_entry(state, tid)
            if entry.get("owner", "") != owner_key:
                continue
            for idx, note in enumerate(entry.get("note_entries", [])):
                if note.get("category") not in ("accomplishment", "challenge", "goal"):
                    continue
                note_date = note.get("date", "")
                if note_date:
                    try:
                        d = datetime.strptime(note_date, "%Y-%m-%d").date()
                        if not (range_from <= d <= range_to):
                            continue
                    except ValueError:
                        pass
                items.append({
                    "token": f"{tid}|{idx}",
                    "tid": tid,
                    "date": note_date,
                    "category": note.get("category"),
                    "category_label": NOTE_CATEGORY_LABELS.get(note.get("category"), note.get("category")),
                    "text": note.get("text", ""),
                })
        if items:
            results.append({"owner_key": owner_key, "full_name": full_name, "role": role, "items": items})
    return jsonify({"owners": results})


@app.post("/export/pptx")
def export_pptx():
    payload = request.get_json(silent=True) or {}
    try:
        meeting_date = datetime.strptime(payload.get("meeting_date", ""), "%Y-%m-%d").date()
        week_num = int(payload.get("week_num"))
    except (ValueError, TypeError):
        return jsonify({"error": "Check the meeting date (YYYY-MM-DD) and week number."}), 400

    included_owners = [k for k in payload.get("owners", []) if k in OWNER_INFO]
    selected_tokens = set(payload.get("selected_notes", []))
    state = _state()
    sections_by_owner = {k: {"accomplishment": [], "challenge": [], "goal": []} for k in included_owners}

    for owner_key in included_owners:
        for tid in TASK_ORDER:
            entry = get_entry(state, tid)
            if entry.get("owner", "") != owner_key:
                continue
            for idx, note in enumerate(entry.get("note_entries", [])):
                token = f"{tid}|{idx}"
                if token not in selected_tokens:
                    continue
                category = note.get("category")
                if category in sections_by_owner[owner_key]:
                    sections_by_owner[owner_key][category].append(f"{tid}: {note.get('text', '')}")

    owner_sections = []
    for k in included_owners:
        sec = sections_by_owner[k]
        if not (sec["accomplishment"] or sec["challenge"] or sec["goal"]):
            continue
        full_name, role = OWNER_INFO[k]
        owner_sections.append({"full_name": full_name, "role": role, **sec})

    timesheet_state = load_timesheet_state()
    member_rows, team_total = compute_labor_status_rows(timesheet_state)
    remaining = remaining_hours(state)
    demo_date = load_or_init_demo_date()
    weeks_left = max(0.0, (demo_date - date.today()).days / 7)
    pace = (remaining / weeks_left) if weeks_left > 0 else remaining
    subtitle = f"Week {week_num} · {meeting_date.strftime('%m/%d/%Y')}"

    out = io.BytesIO()
    # python-pptx can save to a file-like object, and the existing generator passes
    # that object directly to Presentation.save(), preserving the desktop behavior.
    try:
        pptx_export.generate_pptx(
            out, member_rows, team_total, remaining, weeks_left, pace,
            owner_sections, subtitle=subtitle,
        )
    except Exception as exc:
        app.logger.exception("PowerPoint export failed")
        return jsonify({"error": f"Could not generate PowerPoint: {exc}"}), 500
    out.seek(0)
    return send_file(
        out,
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        as_attachment=True,
        download_name=f"TAT_Week{week_num}_Squish_Therapy.pptx",
    )


@app.get("/api/week-number")
def week_number_api():
    try:
        meeting_date = datetime.strptime(request.args.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Date must be YYYY-MM-DD"}), 400
    return jsonify({"week_num": compute_week_number(meeting_date, load_or_init_demo_date())})


@app.errorhandler(413)
def too_large(_):
    return "Upload too large (100 MB limit).", 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
