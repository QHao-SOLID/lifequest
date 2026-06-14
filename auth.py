import logging
import re

from flask import session
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)


def hash_password(password):
    return generate_password_hash(password)


def verify_password(password, password_hash):
    return check_password_hash(password_hash, password)


def login_user(username, password):
    from db import get_db
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    if not user:
        return False
    stored_hash = user["password_hash"]
    if stored_hash and not stored_hash.startswith("scrypt:"):
        if stored_hash == _legacy_sha256(password):
            _migrate_password(user["id"], password)
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return True
        return False
    if verify_password(password, stored_hash):
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        return True
    return False


def _legacy_sha256(password):
    from hashlib import sha256 as _sha256
    return _sha256(password.encode()).hexdigest()


def _migrate_password(user_id, password):
    from db import get_db
    conn = get_db()
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(password), user_id),
    )
    conn.commit()
    conn.close()
    logger.info("Migrated password for user %s to werkzeug hash", user_id)


def register_user(username, email, password, avatar="", role="candidate",
                  company_name="", industry="", website="", contact_email="",
                  university_name="", university_type="", university_website="", university_email=""):
    from db import get_db
    if len(password) < 4:
        return False, "Password must be at least 4 characters"
    if not re.match(r"^[a-zA-Z0-9_]{3,20}$", username):
        return False, "Username must be 3-20 alphanumeric characters (underscores allowed)"
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return False, "Please enter a valid email address"
    if role not in ("candidate", "employer", "University"):
        role = "candidate"
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (username, email, hash_password(password), role),
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if role == "candidate":
            if not avatar:
                avatar = "🧑"
            conn.execute(
                "INSERT INTO player_profiles (user_id, avatar) VALUES (?, ?)",
                (user["id"], avatar),
            )
        elif role == "employer":
            conn.execute(
                "INSERT INTO employers (user_id, company_name, industry, website, contact_email) VALUES (?, ?, ?, ?, ?)",
                (user["id"], company_name[:100], industry[:50], website[:200], contact_email[:200]),
            )
        elif role == "University":
            conn.execute(
                "INSERT INTO universities (user_id, university_name, university_type, university_website, university_email) VALUES (?, ?, ?, ?, ?)",
                (user["id"], university_name[:200], university_type[:100], university_website[:200], university_email[:200]),
            )
        conn.commit()
        conn.close()
        return True, "Account created"
    except Exception as e:
        conn.close()
        logger.exception("Registration failed")
        return False, f"Registration failed: {e}"
