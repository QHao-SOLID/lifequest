from flask import Blueprint, render_template, request, redirect, url_for, flash, session

from auth import login_user, register_user

auth = Blueprint("auth", __name__)


@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if login_user(request.form["username"], request.form["password"]):
            role = session.get("role")
            if role == "employer":
                return redirect(url_for("employer.dashboard"))
            if role == "University":
                return redirect(url_for("university.dashboard"))
            return redirect(url_for("candidate.dashboard"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        role = request.form.get("role", "candidate")
        avatar = request.form.get("avatar", "").strip()
        success, msg = register_user(
            request.form["username"],
            request.form["email"],
            request.form["password"],
            avatar=avatar,
            role=role,
            company_name=request.form.get("company_name", ""),
            industry=request.form.get("industry", ""),
            website=request.form.get("website", ""),
            contact_email=request.form.get("contact_email", ""),
            university_name=request.form.get("university_name", ""),
            university_type=request.form.get("university_type", ""),
            university_website=request.form.get("university_website", ""),
            university_email=request.form.get("university_email", ""),
        )
        if success:
            login_user(request.form["username"], request.form["password"])
            if role == "employer":
                flash("Company registered! Welcome to CareerOS.", "success")
                return redirect(url_for("employer.dashboard"))
            if role == "University":
                flash("University registered! Welcome to CareerOS.", "success")
                return redirect(url_for("university.dashboard"))
            flash("Welcome to CareerOS!", "success")
            return redirect(url_for("candidate.dashboard"))
        flash(msg, "danger")
    return render_template("signup.html")


@auth.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("auth.login"))
