import json

from flask import (Blueprint, flash, jsonify, redirect, render_template,
                   request, session, url_for)

from ai_extractor import analyze_candidate_fit
from db import get_db
from utils.decorators import employer_required, login_required

employer = Blueprint("employer", __name__, url_prefix="/employer")


def _get_employer(uid):
    conn = get_db()
    emp = conn.execute("SELECT * FROM employers WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    return dict(emp) if emp else None


def _relevant_candidates(conn, employer_id):
    candidates = conn.execute(
        """SELECT u.id, u.username, p.skills, p.avatar
        FROM users u JOIN player_profiles p ON u.id = p.user_id
        WHERE u.role = 'candidate'"""
    ).fetchall()
    swiped = set(
        row["candidate_id"] for row in conn.execute(
            "SELECT candidate_id FROM employer_swipes WHERE employer_id = ?", (employer_id,)
        ).fetchall()
    )
    jobs = conn.execute(
        "SELECT skills_required FROM job_listings WHERE employer_id = ? AND status = 'open'",
        (employer_id,),
    ).fetchall()
    job_skill_sets = []
    for j in jobs:
        req = set()
        if j["skills_required"] and j["skills_required"].strip():
            try:
                req = set(json.loads(j["skills_required"]))
            except json.JSONDecodeError:
                req = set()
        if req:
            job_skill_sets.append(req)

    result = []
    for c in candidates:
        if c["id"] in swiped:
            continue
        cand_skills = set()
        if c["skills"] and c["skills"].strip():
            try:
                cand_skills = set(json.loads(c["skills"]))
            except json.JSONDecodeError:
                cand_skills = set()
        if not cand_skills:
            continue
        for req in job_skill_sets:
            if cand_skills & req:
                match_pct = int(len(cand_skills & req) / len(req) * 100)
                result.append(dict(c) | {"match_pct": match_pct})
                break
    return result


@employer.route("/dashboard")
@login_required
@employer_required
def dashboard():
    uid = session["user_id"]
    emp = _get_employer(uid)
    conn = get_db()
    jobs = conn.execute(
        "SELECT * FROM job_listings WHERE employer_id = ? ORDER BY created_at DESC",
        (emp["id"],),
    ).fetchall()
    candidates = _relevant_candidates(conn, emp["id"])
    conn.close()
    return render_template(
        "employer_dashboard.html",
        employer=emp,
        jobs=[dict(j) for j in jobs],
        candidates=candidates,
    )


@employer.route("/jobs/create", methods=["POST"])
@login_required
@employer_required
def job_create():
    emp = _get_employer(session["user_id"])
    conn = get_db()
    skills_input = request.form.get("skills", "[]").strip()
    if not skills_input:
        skills_input = "[]"
    try:
        json.loads(skills_input)
    except json.JSONDecodeError:
        skills_input = "[]"
    conn.execute(
        """INSERT INTO job_listings (employer_id, title, description, skills_required, location, salary_range)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (emp["id"], request.form["title"], request.form.get("description", ""),
         skills_input, request.form.get("location", ""),
         request.form.get("salary", "")),
    )
    conn.commit()
    conn.close()
    flash("Job posted", "success")
    return redirect(url_for("employer.dashboard"))


@employer.route("/jobs/<int:job_id>/close", methods=["POST"])
@login_required
@employer_required
def job_close(job_id):
    emp = _get_employer(session["user_id"])
    conn = get_db()
    conn.execute(
        "UPDATE job_listings SET status = 'closed' WHERE id = ? AND employer_id = ?",
        (job_id, emp["id"]),
    )
    conn.commit()
    conn.close()
    flash("Job closed", "info")
    return redirect(url_for("employer.dashboard"))


@employer.route("/jobs/<int:job_id>/delete", methods=["POST"])
@login_required
@employer_required
def job_delete(job_id):
    emp = _get_employer(session["user_id"])
    conn = get_db()
    conn.execute(
        "DELETE FROM job_listings WHERE id = ? AND employer_id = ?",
        (job_id, emp["id"]),
    )
    conn.commit()
    conn.close()
    flash("Job deleted", "info")
    return redirect(url_for("employer.dashboard"))


@employer.route("/search")
@login_required
@employer_required
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"results": []})
    conn = get_db()
    if q.isdigit():
        rows = conn.execute(
            """SELECT u.id, u.username, p.skills, p.title, p.avatar
            FROM users u JOIN player_profiles p ON u.id = p.user_id
            WHERE u.role = 'candidate' AND u.id = ?""",
            (int(q),),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT u.id, u.username, p.skills, p.title, p.avatar
            FROM users u JOIN player_profiles p ON u.id = p.user_id
            WHERE u.role = 'candidate' AND u.username LIKE ?""",
            (f"%{q}%",),
        ).fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        sk = json.loads(d["skills"]) if d["skills"] else []
        d["skills"] = sk[:6]
        results.append(d)
    return jsonify({"results": results})


@employer.route("/analyze-fit", methods=["POST"])
@login_required
@employer_required
def analyze_fit():
    candidate_id = request.form.get("candidate_id")
    job_id = request.form.get("job_id")
    if not candidate_id or not job_id:
        return jsonify({"error": "Missing candidate_id or job_id"}), 400

    conn = get_db()
    profile = conn.execute(
        "SELECT cv_data FROM player_profiles WHERE user_id = ?", (candidate_id,)
    ).fetchone()
    job = conn.execute(
        """SELECT j.*, e.company_name
        FROM job_listings j JOIN employers e ON j.employer_id = e.id
        WHERE j.id = ?""",
        (job_id,),
    ).fetchone()
    conn.close()

    if not profile or not job:
        return jsonify({"error": "Candidate or job not found"}), 404

    cv_data = json.loads(profile["cv_data"]) if profile["cv_data"] else {}
    job_data = dict(job)
    job_data["skills_required"] = json.loads(job_data["skills_required"]) if job_data["skills_required"] else []

    result = analyze_candidate_fit(cv_data, job_data)
    return jsonify(result)


@employer.route("/swipe/<int:candidate_id>/<action>", methods=["POST"])
@login_required
@employer_required
def swipe(candidate_id, action):
    if action not in ("accepted", "rejected"):
        return jsonify({"error": "Invalid action"}), 400
    emp = _get_employer(session["user_id"])
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO employer_swipes (employer_id, candidate_id, action) VALUES (?, ?, ?)",
            (emp["id"], candidate_id, action),
        )
        conn.commit()
    except Exception:
        conn.close()
        return jsonify({"error": "Already swiped"}), 400
    conn.close()
    return jsonify({"success": True, "action": action})


@employer.route("/matches")
@login_required
@employer_required
def matches():
    emp = _get_employer(session["user_id"])
    conn = get_db()
    rows = conn.execute(
        """SELECT es.candidate_id, u.username, p.skills, p.title, p.avatar
        FROM employer_swipes es
        JOIN users u ON es.candidate_id = u.id
        JOIN player_profiles p ON u.id = p.user_id
        WHERE es.employer_id = ? AND es.action = 'accepted'
        ORDER BY es.created_at DESC""",
        (emp["id"],),
    ).fetchall()
    jobs = conn.execute(
        "SELECT id, title FROM job_listings WHERE employer_id = ? AND status = 'open'",
        (emp["id"],),
    ).fetchall()
    conn.close()
    return render_template(
        "employer_matches.html",
        matches=[dict(r) for r in rows],
        jobs=[dict(j) for j in jobs],
    )


@employer.route("/hire/<int:candidate_id>", methods=["POST"])
@login_required
@employer_required
def hire(candidate_id):
    emp = _get_employer(session["user_id"])
    job_id = request.form.get("job_id")
    if not job_id:
        flash("Select a job", "danger")
        return redirect(url_for("employer.matches"))
    conn = get_db()
    conn.execute(
        "INSERT INTO hires (job_id, candidate_id, employer_id) VALUES (?, ?, ?)",
        (job_id, candidate_id, emp["id"]),
    )
    conn.execute(
        "UPDATE job_listings SET status = 'closed' WHERE id = ?", (job_id,)
    )
    conn.commit()
    job_title = conn.execute(
        "SELECT title FROM job_listings WHERE id = ?", (job_id,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
        (candidate_id, f"Hired by {emp['company_name']} for {job_title}."),
    )
    conn.commit()
    conn.close()
    flash("Candidate hired!", "success")
    return redirect(url_for("employer.matches"))


@employer.route("/profile", methods=["GET", "POST"])
@login_required
@employer_required
def profile():
    uid = session["user_id"]
    emp = _get_employer(uid)
    if request.method == "POST":
        conn = get_db()
        conn.execute(
            """UPDATE employers SET company_name=?, industry=?, website=?, description=?, contact_email=?
            WHERE user_id=?""",
            (request.form["company_name"], request.form.get("industry", ""),
             request.form.get("website", ""), request.form.get("description", ""),
             request.form.get("contact_email", ""), uid),
        )
        conn.commit()
        conn.close()
        flash("Profile updated", "success")
        return redirect(url_for("employer.profile"))
    return render_template("employer_profile.html", employer=emp)


@employer.route("/history")
@login_required
@employer_required
def history():
    emp = _get_employer(session["user_id"])
    conn = get_db()
    rows = conn.execute(
        """SELECT es.id as swipe_id, es.action, es.created_at,
        u.id as candidate_id, u.username, p.skills, p.title, p.avatar
        FROM employer_swipes es
        JOIN users u ON es.candidate_id = u.id
        JOIN player_profiles p ON u.id = p.user_id
        WHERE es.employer_id = ? ORDER BY es.created_at DESC""",
        (emp["id"],),
    ).fetchall()
    conn.close()
    return render_template(
        "employer_history.html",
        swipes=[dict(r) for r in rows],
    )


@employer.route("/history/revert/<int:swipe_id>", methods=["POST"])
@login_required
@employer_required
def history_revert(swipe_id):
    conn = get_db()
    conn.execute("DELETE FROM employer_swipes WHERE id = ?", (swipe_id,))
    conn.commit()
    conn.close()
    flash("Swipe reverted. Candidate will appear in match deck again.", "info")
    return redirect(url_for("employer.history"))
