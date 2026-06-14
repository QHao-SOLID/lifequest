# AGENTS.md — LifeQuest / CareerOS

## Run

```
python app.py
```

Serves on `localhost:5000` (override with `PORT` env var). Debug mode enabled when `FLASK_ENV=development`.

## Env & Dependencies

- `.env` required for AI features. Copy `.env.example` → `.env` and set `DEEPSEEK_API_KEY`.
- Both `pyproject.toml` and `requirements.txt` exist — keep them in sync when adding packages.
- `pip install -r requirements.txt` to install all deps.

## Architecture

- **Flask app factory** in `app.py` — creates app, registers blueprints, and sets up template filters.
- **Blueprints** (no URL prefix on auth/candidate, `/employer` and `/university` have prefixes):
  - `routes/auth_routes.py` — login, signup, logout
  - `routes/candidate.py` — dashboard, profile, CV upload, friends, quests, jobs
  - `routes/employer.py` — employer dashboard, jobs, swipes, hire, matches
  - `routes/university.py` — university dashboard, profile
- **SQLite** via `db.py` — auto-created at `lifequest.db` on startup. No migration system.
- **AI** via DeepSeek API in `ai_extractor.py` — CV parsing, text classification, proof validation.
- **Game logic** in `game_mechanics.py` — XP/leveling, friends, quest generation/completion.
- **Config** in `config.py` — all paths, keys, and settings.

## Key conventions

- `from_json` is a global Jinja template filter (registered in `app.py`). Use it when rendering JSON stored in SQLite text columns (`skills`, `quests`, `cv_data`).
- `url_for()` calls in templates must include blueprint prefix: `auth.login`, `candidate.dashboard`, `employer.matches`, `university.dashboard`.
- Upload directories auto-created on startup: `uploads/`, `uploads/avatars/`, `uploads/quest_proofs/`, `uploads/cv_proofs/`.
- User roles: `"candidate"` (default), `"employer"`, `"University"` (capital-U is intentional).

## CV Upload flow

1. User uploads PDF via `/cv/upload` (POST, multipart)
2. File saved to `uploads/`
3. `extract_cv(path)` in `ai_extractor.py` parses PDF via PyPDF2 → calls DeepSeek for structured extraction
4. If DeepSeek unavailable, falls back to heuristic `_heuristic_extract` (regex-based skill/keyword matching — no random data)
5. Skills merged into profile, quests regenerated, XP awarded

## Known quirks

- **Password hashing** upgraded from SHA-256 to `werkzeug.security`. Legacy SHA-256 hashes auto-migrated on login. New registrations use werkzeug hash.
- **Session secret key** comes from `SECRET_KEY` env var. Falls back to `os.urandom(24).hex()` which invalidates all sessions on restart. Set `SECRET_KEY` in `.env` for production.
- **No CSRF protection** on any form — do not add sensitive write operations without adding CSRF first.
- **Employer swipes** table has `UNIQUE(employer_id, candidate_id)` — attempting to swipe twice throws an error (caught by try/except returning 400).
- **Blocking DeepSeek calls** — CV upload and quest generation are synchronous and may take several seconds.
- **No test suite** — no pytest, no test files, no lint/format/typecheck config.
- **Players page** — `players.html` template exists but has no active route. The `/players` endpoint was not implemented.

## File structure

```
app.py                  # App factory + entrypoint
config.py               # All config (paths, keys, settings)
auth.py                 # Password hashing, register_user, login_user
db.py                   # SQLite connection + init_db schema
game_mechanics.py       # XP, leveling, friends, quests
ai_extractor.py         # PDF parsing, DeepSeek API calls, fallback heuristics
routes/
  auth_routes.py        # Auth blueprint
  candidate.py          # Candidate blueprint
  employer.py           # Employer blueprint
  university.py         # University blueprint
utils/
  decorators.py         # login_required, employer_required, university_required
templates/              # Jinja2 templates (16 files)
static/                 # style.css, CareerOS_logo.png
uploads/                # Auto-created upload dirs
```
