from functools import wraps
from flask import session, flash, redirect, url_for


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def employer_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first", "danger")
            return redirect(url_for("auth.login"))
        if session.get("role") != "employer":
            flash("Employer access only", "danger")
            return redirect(url_for("candidate.dashboard"))
        return f(*args, **kwargs)
    return decorated


def university_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first", "danger")
            return redirect(url_for("auth.login"))
        if session.get("role") != "University":
            flash("University access only", "danger")
            return redirect(url_for("candidate.dashboard"))
        return f(*args, **kwargs)
    return decorated
