import json
import os

from flask import (Blueprint, flash, jsonify, redirect, render_template,
                   request, session, url_for, send_from_directory)
from werkzeug.utils import secure_filename

from ai_extractor import (extract_cv, generate_tasks, process_text_entry,
                         process_task_completion, validate_cv_proof)
from config import (ALLOWED_AVATAR_EXT, ALLOWED_PROOF_EXT, AVATAR_FOLDER,
                    CV_PROOF_FOLDER, TASK_PROOF_FOLDER, UPLOAD_FOLDER)
from db import get_db
from game_mechanics import (
    accept_friend_request, are_friends, compute_completeness, count_friends,
    get_friend_requests_incoming, get_friend_requests_outgoing,
    get_friends, get_recent_activities, log_activity, reject_friend_request,
    remove_friend, send_friend_request,
)
from utils.decorators import login_required

candidate = Blueprint("candidate", __name__)


def _safe_json(row, key, default=None):
    if default is None:
        default = []
    try:
        val = row[key]
        return json.loads(val) if val else default
    except (KeyError, json.JSONDecodeError):
        return default


# ── Template filter ──

@candidate.app_template_filter("from_json")
def from_json(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return []

# ── Context processor ──

@candidate.context_processor
def inject_unread():
    if "user_id" in session and session.get("role") == "candidate":
        conn = get_db()
        count = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read = 0",
            (session["user_id"],),
        ).fetchone()[0]
        conn.close()
        return {"unread_notifications": count}
    return {"unread_notifications": 0}


# ── Dashboard ──

@candidate.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    conn = get_db()
    profile = conn.execute(
        "SELECT * FROM player_profiles WHERE user_id = ?", (uid,)
    ).fetchone()
    incoming = get_friend_requests_incoming(conn, uid)
    friend_count = count_friends(conn, uid)
    tasks = _safe_json(profile, "tasks") if profile else []
    avatar = profile["avatar"] if profile and profile["avatar"] else "🧑"
    activities = get_recent_activities(conn, uid)
    completeness = compute_completeness(profile)
    conn.close()
    return render_template(
        "dashboard.html",
        profile=profile,
        username=session["username"],
        incoming_requests=incoming[:3],
        friend_count=friend_count,
        tasks=tasks,
        avatar=avatar,
        activities=activities,
        completeness=completeness,
    )


# ── Profile ──

@candidate.route("/profile/<username>")
@login_required
def profile(username):
    uid = session["user_id"]
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not user:
        conn.close()
        flash("Player not found", "danger")
        return redirect(url_for("candidate.dashboard"))
    profile = conn.execute(
        "SELECT * FROM player_profiles WHERE user_id = ?", (user["id"],)
    ).fetchone()
    is_friend = are_friends(conn, uid, user["id"])
    p_friend_count = count_friends(conn, user["id"])
    p_avatar = profile["avatar"] if profile and profile["avatar"] else "🧑"
    is_own = uid == user["id"]
    is_employer_view = session.get("role") == "employer"
    completeness = compute_completeness(profile)
    conn.close()
    return render_template(
        "profile.html",
        profile=profile,
        p_username=username,
        p_user_id=user["id"],
        is_friend=is_friend,
        p_friend_count=p_friend_count,
        p_avatar=p_avatar,
        is_own=is_own,
        is_employer_view=is_employer_view,
        completeness=completeness,
    )


@candidate.route("/profile/update-contact", methods=["POST"])
@login_required
def update_contact():
    uid = session["user_id"]
    name = request.form.get("name", "")
    email = request.form.get("email", "")
    phone = request.form.get("phone", "")
    location = request.form.get("location", "")
    social_media_text = request.form.get("social_media", "")
    social_media = [s.strip() for s in social_media_text.split("\n") if s.strip()]
    conn = get_db()
    profile = conn.execute(
        "SELECT cv_data FROM player_profiles WHERE user_id = ?", (uid,)
    ).fetchone()
    cv_data = {}
    if profile and profile["cv_data"]:
        try:
            cv_data = json.loads(profile["cv_data"])
        except Exception:
            cv_data = {}
    if "meta" not in cv_data:
        cv_data["meta"] = {}
    cv_data["meta"]["name"] = name
    cv_data["meta"]["email"] = email
    cv_data["meta"]["phone"] = phone
    cv_data["meta"]["location"] = location
    cv_data["meta"]["social_media"] = social_media
    conn.execute(
        "UPDATE player_profiles SET cv_data = ? WHERE user_id = ?",
        (json.dumps(cv_data), uid),
    )
    conn.commit()
    log_activity(conn, uid, "contact_update", "Updated contact information")
    conn.close()
    flash("Contact information updated", "success")
    return redirect(url_for("candidate.profile", username=session["username"]))


# ── Avatar ──

@candidate.route("/profile/update-avatar", methods=["POST"])
@login_required
def update_avatar():
    uid = session["user_id"]
    conn = get_db()
    if "avatar_file" in request.files:
        f = request.files["avatar_file"]
        if f.filename:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext in ALLOWED_AVATAR_EXT:
                filename = f"{uid}{ext}"
                f.save(os.path.join(AVATAR_FOLDER, filename))
                conn.execute(
                    "UPDATE player_profiles SET avatar = ? WHERE user_id = ?",
                    (f"custom:{filename}", uid),
                )
                conn.commit()
                log_activity(conn, uid, "avatar_update", "Updated profile photo")
                conn.close()
                flash("Avatar updated", "success")
                return redirect(url_for("candidate.profile", username=session["username"]))
    emoji = request.form.get("avatar", "").strip()
    if emoji:
        conn.execute(
            "UPDATE player_profiles SET avatar = ? WHERE user_id = ?", (emoji, uid),
        )
        conn.commit()
        log_activity(conn, uid, "avatar_update", "Changed profile icon")
        conn.close()
        flash("Avatar updated", "success")
        return redirect(url_for("candidate.profile", username=session["username"]))
    conn.close()
    flash("No avatar provided", "danger")
    return redirect(url_for("candidate.profile", username=session["username"]))


# ── Friends ──

@candidate.route("/friends")
@login_required
def friends_page():
    uid = session["user_id"]
    conn = get_db()
    friends_list = get_friends(conn, uid)
    incoming = get_friend_requests_incoming(conn, uid)
    outgoing = get_friend_requests_outgoing(conn, uid)
    conn.close()
    return render_template(
        "friends.html",
        friends=friends_list,
        incoming_requests=incoming,
        outgoing_requests=outgoing,
    )


@candidate.route("/friend/send/<int:user_id>", methods=["POST"])
@login_required
def friend_send(user_id):
    uid = session["user_id"]
    conn = get_db()
    success, msg = send_friend_request(conn, uid, user_id)
    conn.close()
    return jsonify({"success": success, "message": msg})


@candidate.route("/friend/accept/<int:request_id>", methods=["POST"])
@login_required
def friend_accept(request_id):
    uid = session["user_id"]
    conn = get_db()
    success, msg = accept_friend_request(conn, request_id, uid)
    if success:
        log_activity(conn, uid, "friend_accept", f"Connected with a new contact")
    conn.close()
    flash(msg, "success" if success else "danger")
    return redirect(url_for("candidate.friends_page"))


@candidate.route("/friend/reject/<int:request_id>", methods=["POST"])
@login_required
def friend_reject(request_id):
    uid = session["user_id"]
    conn = get_db()
    success, msg = reject_friend_request(conn, request_id, uid)
    conn.close()
    flash(msg, "info" if success else "danger")
    return redirect(url_for("candidate.friends_page"))


@candidate.route("/friend/remove/<int:friend_id>", methods=["POST"])
@login_required
def friend_remove(friend_id):
    uid = session["user_id"]
    conn = get_db()
    success, msg = remove_friend(conn, uid, friend_id)
    conn.close()
    flash(msg, "info" if success else "danger")
    return redirect(url_for("candidate.friends_page"))


# ── CV upload ──

@candidate.route("/cv/upload", methods=["POST"])
@login_required
def cv_upload():
    if "cv_file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["cv_file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files accepted"}), 400
    filename = secure_filename(f"{session['user_id']}_{file.filename}")
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)
    try:
        data = extract_cv(path)
    except Exception as e:
        return jsonify({"error": f"Extraction failed: {e}"}), 500
    skills = data.get("skills", [])
    role = data.get("role", "")
    uid = session["user_id"]
    conn = get_db()
    profile = conn.execute(
        "SELECT * FROM player_profiles WHERE user_id = ?", (uid,)
    ).fetchone()
    existing_skills = json.loads(profile["skills"]) if profile and profile["skills"] else []
    merged = list(dict.fromkeys(existing_skills + skills))
    tasks = generate_tasks(data)
    conn.execute(
        """UPDATE player_profiles SET
            skills = ?, cv_data = ?, tasks = ?, title = ?,
            last_login = datetime('now')
        WHERE user_id = ?""",
        (json.dumps(merged), json.dumps(data), json.dumps(tasks), role[:50], uid),
    )
    conn.commit()
    conn.close()
    return jsonify({
        "skills": merged,
        "role": role,
        "experience": data.get("experience_level", "mid"),
        "tasks": tasks,
    })


# ── AI text import ──

@candidate.route("/cv/add-entry", methods=["POST"])
@login_required
def cv_add_entry():
    text = request.form.get("text", "").strip()
    proof = request.form.get("proof", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400
    if not proof:
        return jsonify({"error": "Proof of work required"}), 400
    validation = validate_cv_proof(text, proof)
    if validation and not validation.get("pass"):
        return jsonify({"error": f"Proof rejected: {validation.get('reason', 'Insufficient evidence')}"}), 400
    proof_file = ""
    if "proof_file" in request.files:
        f = request.files["proof_file"]
        if f.filename:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext in ALLOWED_PROOF_EXT:
                filename = f"{session['user_id']}_cv_{secure_filename(f.filename)}"
                f.save(os.path.join(CV_PROOF_FOLDER, filename))
                proof_file = filename
    try:
        result = process_text_entry(text)
    except Exception as e:
        return jsonify({"error": f"Processing failed: {e}"}), 500
    section_type = result.get("section_type", "projects")
    entry = result.get("entry", {})
    if proof_file:
        entry["proof_file"] = proof_file
    entry["proof"] = proof
    new_skills = result.get("skills_extracted", [])
    uid = session["user_id"]
    conn = get_db()
    profile = conn.execute(
        "SELECT * FROM player_profiles WHERE user_id = ?", (uid,)
    ).fetchone()
    if not profile:
        conn.close()
        return jsonify({"error": "Profile not found"}), 404
    cv_data = json.loads(profile["cv_data"]) if profile["cv_data"] else {}
    if section_type not in cv_data:
        cv_data[section_type] = []
    cv_data[section_type].append(entry)
    existing_skills = json.loads(profile["skills"]) if profile["skills"] else []
    merged = list(dict.fromkeys(existing_skills + new_skills))
    conn.execute(
        """UPDATE player_profiles SET
            cv_data = ?, skills = ?, last_login = datetime('now')
        WHERE user_id = ?""",
        (json.dumps(cv_data), json.dumps(merged), uid),
    )
    conn.commit()
    section_label = section_type.replace("_", " ").title()
    log_activity(conn, uid, "cv_add_entry",
                 f"Added {section_label} via AI: {entry.get('role') or entry.get('project_name') or entry.get('institution') or 'New entry'}",
                 {"section": section_type, "skills_added": len(new_skills)})
    conn.close()
    return jsonify({
        "success": True,
        "section_type": section_type,
        "entry": entry,
        "skills": new_skills,
        "merged_skills": merged,
    })


# ── Tasks ──

@candidate.route("/task/complete/<task_id>", methods=["POST"])
@login_required
def task_complete(task_id):
    uid = session["user_id"]
    proof = request.form.get("proof", "").strip()
    proof_url = request.form.get("proof_url", "").strip()
    if not proof and "proof_file" not in request.files:
        return jsonify({"success": False, "error": "Proof text or file is required"}), 400

    conn = get_db()
    profile = conn.execute(
        "SELECT * FROM player_profiles WHERE user_id = ?", (uid,)
    ).fetchone()
    if not profile:
        conn.close()
        return jsonify({"success": False, "error": "Profile not found"}), 404

    tasks = _safe_json(profile, "tasks")
    task = None
    for t in tasks:
        if t.get("id") == task_id and t.get("status") == "active":
            task = t
            break
    if not task:
        conn.close()
        return jsonify({"success": False, "error": "Task not found or already completed"}), 400

    proof_file = ""
    if "proof_file" in request.files:
        f = request.files["proof_file"]
        if f.filename:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext in ALLOWED_PROOF_EXT:
                filename = f"{uid}_{task_id}_{secure_filename(f.filename)}"
                f.save(os.path.join(TASK_PROOF_FOLDER, filename))
                proof_file = filename

    proof_text = proof or f"[File: {proof_file}]" if proof_file else proof
    result = process_task_completion(task, proof_text)
    if not result:
        conn.close()
        return jsonify({"success": False, "error": "AI validation unavailable"}), 500

    if not result.get("valid"):
        conn.close()
        return jsonify({"success": False, "error": f"Proof rejected: {result.get('reason', 'Insufficient evidence')}"}), 400

    task["status"] = "completed"
    task["proof"] = proof
    if proof_url:
        task["proof_url"] = proof_url
    if proof_file:
        task["proof_file"] = proof_file

    new_skills = result.get("skills_found", [])
    section_type = result.get("section_type", "projects")
    entry = result.get("entry", {})

    cv_data = json.loads(profile["cv_data"]) if profile["cv_data"] else {}
    if section_type and entry:
        if section_type not in cv_data:
            cv_data[section_type] = []
        cv_data[section_type].append(entry)

    existing_skills = json.loads(profile["skills"]) if profile["skills"] else []
    merged = list(dict.fromkeys(existing_skills + new_skills))

    conn.execute(
        "UPDATE player_profiles SET tasks = ?, skills = ?, cv_data = ? WHERE user_id = ?",
        (json.dumps(tasks), json.dumps(merged), json.dumps(cv_data), uid),
    )
    conn.commit()
    skill_list = ", ".join(new_skills) if new_skills else "achievement"
    log_activity(conn, uid, "task_complete",
                 f"Completed: {task.get('title', 'Task')}. {skill_list} added to profile.",
                 {"task_id": task_id, "skills_added": len(new_skills)})
    conn.close()
    return jsonify({
        "success": True,
        "message": f"Completed: {task.get('title')}. {skill_list} added to your profile.",
        "skills_added": new_skills,
    })


@candidate.route("/task/dismiss/<task_id>", methods=["POST"])
@login_required
def task_dismiss(task_id):
    uid = session["user_id"]
    conn = get_db()
    profile = conn.execute(
        "SELECT tasks FROM player_profiles WHERE user_id = ?", (uid,)
    ).fetchone()
    if not profile:
        conn.close()
        return jsonify({"success": False, "error": "Profile not found"}), 404

    tasks = _safe_json(profile, "tasks")
    task = None
    for t in tasks:
        if t.get("id") == task_id and t.get("status") == "active":
            t["status"] = "dismissed"
            task = t
            break
    if not task:
        conn.close()
        return jsonify({"success": False, "error": "Task not found"}), 400

    conn.execute(
        "UPDATE player_profiles SET tasks = ? WHERE user_id = ?",
        (json.dumps(tasks), uid),
    )
    conn.commit()
    log_activity(conn, uid, "task_dismiss", f"Skipped: {task.get('title', 'Task')}")
    conn.close()
    return jsonify({"success": True, "message": "Task dismissed"})


@candidate.route("/task/refresh", methods=["POST"])
@login_required
def task_refresh():
    uid = session["user_id"]
    conn = get_db()
    profile = conn.execute(
        "SELECT * FROM player_profiles WHERE user_id = ?", (uid,)
    ).fetchone()
    if not profile:
        conn.close()
        return jsonify({"success": False, "error": "Profile not found"}), 404

    cv_data = json.loads(profile["cv_data"]) if profile["cv_data"] else {}
    completed_tasks = [t for t in (_safe_json(profile, "tasks")) if t.get("status") == "completed"]
    new_tasks = generate_tasks(cv_data)

    conn.execute(
        "UPDATE player_profiles SET tasks = ? WHERE user_id = ?",
        (json.dumps(completed_tasks + new_tasks), uid),
    )
    conn.commit()
    log_activity(conn, uid, "task_refresh", f"Refreshed tasks — {len(new_tasks)} new tasks generated")
    conn.close()
    return jsonify({"success": True, "tasks": new_tasks, "message": f"{len(new_tasks)} new tasks generated"})


# ── Jobs ──

@candidate.route("/jobs")
@login_required
def jobs_browse():
    uid = session["user_id"]
    conn = get_db()
    profile = conn.execute(
        "SELECT skills FROM player_profiles WHERE user_id = ?", (uid,)
    ).fetchone()
    cand_skills = set(json.loads(profile["skills"]) if profile and profile["skills"] else [])
    rows = conn.execute(
        """SELECT j.*, e.company_name, e.industry, e.contact_email, e.user_id as emp_user_id
        FROM job_listings j JOIN employers e ON j.employer_id = e.id
        WHERE j.status = 'open' ORDER BY j.created_at DESC""",
    ).fetchall()
    listings = []
    for r in rows:
        j = dict(r)
        req = set(json.loads(j["skills_required"]) if j["skills_required"] else [])
        match_pct = int(len(cand_skills & req) / len(req) * 100) if req else 0
        j["match_pct"] = match_pct
        listings.append(j)
    notifs = conn.execute(
        "SELECT id, message, created_at FROM notifications WHERE user_id = ? AND read = 0 ORDER BY created_at DESC",
        (uid,),
    ).fetchall()
    hires = conn.execute(
        """SELECT h.*, j.title, e.company_name
        FROM hires h JOIN job_listings j ON h.job_id = j.id
        JOIN employers e ON h.employer_id = e.id
        WHERE h.candidate_id = ? ORDER BY h.created_at DESC""",
        (uid,),
    ).fetchall()
    conn.close()
    return render_template(
        "jobs_browse.html",
        jobs=listings,
        notifications=[dict(n) for n in notifs],
        hires=[dict(h) for h in hires],
    )


@candidate.route("/jobs/notifications/read", methods=["POST"])
@login_required
def jobs_notifications_read():
    uid = session["user_id"]
    conn = get_db()
    conn.execute("UPDATE notifications SET read = 1 WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@candidate.route("/jobs/<int:job_id>")
@login_required
def job_detail(job_id):
    conn = get_db()
    row = conn.execute(
        """SELECT j.*, e.company_name, e.industry, e.description as company_desc,
        e.website, e.contact_email, e.user_id as emp_user_id
        FROM job_listings j JOIN employers e ON j.employer_id = e.id
        WHERE j.id = ?""",
        (job_id,),
    ).fetchone()
    conn.close()
    if not row:
        flash("Job not found", "danger")
        return redirect(url_for("candidate.jobs_browse"))
    job = dict(row)
    job["skills_required"] = json.loads(job["skills_required"]) if job["skills_required"] else []
    return render_template("job_detail.html", job=job)


# ── Serve uploads ──

@candidate.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@candidate.route("/uploads/avatars/<filename>")
def serve_avatar(filename):
    return send_from_directory(AVATAR_FOLDER, filename)
