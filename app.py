import os

from flask import Flask, session, redirect, url_for

from config import (AVATAR_FOLDER, CV_PROOF_FOLDER, DEBUG, TASK_PROOF_FOLDER,
                    SECRET_KEY, UPLOAD_FOLDER)


def create_app():
    app = Flask(__name__)
    app.secret_key = SECRET_KEY

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(AVATAR_FOLDER, exist_ok=True)
    os.makedirs(TASK_PROOF_FOLDER, exist_ok=True)
    os.makedirs(CV_PROOF_FOLDER, exist_ok=True)

    from db import init_db
    init_db()

    @app.route("/")
    def index():
        if "user_id" in session:
            role = session.get("role")
            if role == "employer":
                return redirect(url_for("employer.dashboard"))
            if role == "University":
                return redirect(url_for("university.dashboard"))
            return redirect(url_for("candidate.dashboard"))
        return redirect(url_for("auth.login"))

    from routes.auth_routes import auth
    from routes.candidate import candidate
    from routes.employer import employer
    from routes.university import university

    app.register_blueprint(auth)
    app.register_blueprint(candidate)
    app.register_blueprint(employer)
    app.register_blueprint(university)

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=DEBUG, host="0.0.0.0", port=port)
