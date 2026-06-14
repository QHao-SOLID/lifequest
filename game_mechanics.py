import json

# ── Activity log ──

def log_activity(conn, user_id, action_type, description, metadata=None):
    conn.execute(
        "INSERT INTO activity_log (user_id, action_type, description, metadata) VALUES (?, ?, ?, ?)",
        (user_id, action_type, description, json.dumps(metadata or {})),
    )
    conn.commit()


def get_recent_activities(conn, user_id, limit=15):
    rows = conn.execute(
        "SELECT * FROM activity_log WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Profile completeness ──

def compute_completeness(profile):
    if not profile:
        return {"score": 0, "breakdown": {}}
    skills = json.loads(profile["skills"]) if profile["skills"] else []
    cv_data = json.loads(profile["cv_data"]) if profile["cv_data"] else {}

    has_work = 1 if cv_data.get("work_experience") else 0
    has_edu = 1 if cv_data.get("education") else 0
    skill_score = min(len(skills), 8) / 8
    has_projects = 1 if cv_data.get("projects") else 0
    has_leadership = 1 if cv_data.get("leadership") else 0

    score = int((has_work * 25) + (has_edu * 25) + (skill_score * 25) + (has_projects * 15) + (has_leadership * 10))
    return {
        "score": score,
        "breakdown": {
            "work_experience": has_work,
            "education": has_edu,
            "skills": int(skill_score * 100),
            "projects": has_projects,
            "leadership": has_leadership,
        },
    }


# ── Friend helpers ──

def are_friends(conn, user_a, user_b):
    if user_a == user_b:
        return False
    row = conn.execute(
        """SELECT 1 FROM friend_requests
        WHERE ((from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?))
        AND status = 'accepted'""",
        (user_a, user_b, user_b, user_a),
    ).fetchone()
    return row is not None


def get_friends(conn, user_id):
    rows = conn.execute(
        """SELECT u.id, u.username, p.title, p.avatar, p.last_login
        FROM friend_requests fr
        JOIN users u ON (CASE WHEN fr.from_user = ? THEN fr.to_user ELSE fr.from_user END) = u.id
        JOIN player_profiles p ON u.id = p.user_id
        WHERE (fr.from_user = ? OR fr.to_user = ?) AND fr.status = 'accepted'""",
        (user_id, user_id, user_id),
    ).fetchall()
    return [dict(r) for r in rows]


def count_friends(conn, user_id):
    return len(get_friends(conn, user_id))


def get_friend_requests_incoming(conn, user_id):
    rows = conn.execute(
        """SELECT fr.id, fr.from_user, u.username, p.title, p.avatar, fr.timestamp
        FROM friend_requests fr
        JOIN users u ON fr.from_user = u.id
        JOIN player_profiles p ON u.id = p.user_id
        WHERE fr.to_user = ? AND fr.status = 'pending'
        ORDER BY fr.timestamp DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_friend_requests_outgoing(conn, user_id):
    rows = conn.execute(
        """SELECT fr.id, fr.to_user, u.username, p.title, p.avatar, fr.timestamp
        FROM friend_requests fr
        JOIN users u ON fr.to_user = u.id
        JOIN player_profiles p ON u.id = p.user_id
        WHERE fr.from_user = ? AND fr.status = 'pending'
        ORDER BY fr.timestamp DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def send_friend_request(conn, from_id, to_id):
    if from_id == to_id:
        return False, "Cannot friend yourself"
    if are_friends(conn, from_id, to_id):
        return False, "Already friends"
    existing = conn.execute(
        "SELECT 1 FROM friend_requests WHERE from_user = ? AND to_user = ? AND status = 'pending'",
        (from_id, to_id),
    ).fetchone()
    if existing:
        return False, "Request already sent"
    reverse = conn.execute(
        "SELECT 1 FROM friend_requests WHERE from_user = ? AND to_user = ? AND status = 'pending'",
        (to_id, from_id),
    ).fetchone()
    if reverse:
        return False, "This user already sent you a request"
    conn.execute(
        "INSERT INTO friend_requests (from_user, to_user, status) VALUES (?, ?, 'pending')",
        (from_id, to_id),
    )
    conn.commit()
    return True, "Friend request sent"


def accept_friend_request(conn, request_id, user_id):
    row = conn.execute(
        "SELECT * FROM friend_requests WHERE id = ? AND to_user = ? AND status = 'pending'",
        (request_id, user_id),
    ).fetchone()
    if not row:
        return False, "Request not found"
    conn.execute("UPDATE friend_requests SET status = 'accepted' WHERE id = ?", (request_id,))
    conn.commit()
    return True, "Friend request accepted"


def reject_friend_request(conn, request_id, user_id):
    row = conn.execute(
        "SELECT * FROM friend_requests WHERE id = ? AND to_user = ? AND status = 'pending'",
        (request_id, user_id),
    ).fetchone()
    if not row:
        return False, "Request not found"
    conn.execute("DELETE FROM friend_requests WHERE id = ?", (request_id,))
    conn.commit()
    return True, "Friend request rejected"


def remove_friend(conn, user_id, friend_id):
    if not are_friends(conn, user_id, friend_id):
        return False, "Not friends"
    conn.execute(
        """DELETE FROM friend_requests
        WHERE ((from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?))
        AND status = 'accepted'""",
        (user_id, friend_id, friend_id, user_id),
    )
    conn.commit()
    return True, "Friend removed"

