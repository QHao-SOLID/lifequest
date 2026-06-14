from flask import (Blueprint, flash, redirect, render_template,
                   request, session, url_for)

from db import get_db
from utils.decorators import login_required, university_required

university = Blueprint("university", __name__, url_prefix="/university")


def _get_university(uid):
    conn = get_db()
    uni = conn.execute("SELECT * FROM universities WHERE user_id = ?", (uid,)).fetchone()
    conn.close()
    return dict(uni) if uni else None


@university.route("/dashboard")
@login_required
@university_required
def dashboard():
    uid = session["user_id"]
    uni = _get_university(uid)
    if not uni:
        flash("University profile not found. Please contact support.", "danger")
        return redirect(url_for("auth.logout"))

    conn = get_db()

    students_placed = conn.execute(
        "SELECT COUNT(*) FROM hires"
    ).fetchone()[0]

    employer_partners = conn.execute(
        "SELECT COUNT(DISTINCT employer_id) FROM job_listings WHERE status = 'open'"
    ).fetchone()[0]

    total_candidates = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'candidate'"
    ).fetchone()[0]
    placement_rate = (
        f"{int(students_placed / total_candidates * 100)}%"
        if total_candidates > 0 else "0%"
    )

    conn.close()

    return render_template(
        "university_dashboard.html",
        university_name=uni.get("university_name", session["username"]),
        university_type=uni.get("university_type", "University"),
        students_placed=f"{students_placed:,}",
        avg_salary="RM 4.8k",
        employer_partners=employer_partners,
        placement_rate=placement_rate,
    )


@university.route("/profile", methods=["GET", "POST"])
@login_required
@university_required
def profile():
    uid = session["user_id"]
    uni = _get_university(uid)
    if request.method == "POST":
        conn = get_db()
        conn.execute(
            """UPDATE universities
            SET university_name=?, university_type=?, university_website=?, university_email=?
            WHERE user_id=?""",
            (
                request.form.get("university_name", ""),
                request.form.get("university_type", ""),
                request.form.get("university_website", ""),
                request.form.get("university_email", ""),
                uid,
            ),
        )
        conn.commit()
        conn.close()
        flash("University profile updated", "success")
        return redirect(url_for("university.profile"))
    return render_template(
        "university_profile.html",
        university=uni,
        username=session["username"],
    )
