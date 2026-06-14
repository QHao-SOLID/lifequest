# LifeQuest — CareerOS

Living CV MMORPG. Gamified career platform with AI-powered CV parsing, quests, friend system, and employer matching.

## Quick Start

```
cp .env.example .env          # set DEEPSEEK_API_KEY
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000`. Debug mode on when `FLASK_ENV=development`.

## Roles

- **Candidate** — upload CV (PDF), build profile, earn XP, complete quests, add friends, browse jobs
- **Employer** — post jobs, swipe on candidates, hire matches
- **University** — university profile & dashboard

## Architecture

| Layer | Stack |
|---|---|
| Framework | Flask 3 (blueprints, Jinja2) |
| Database | SQLite (WAL mode, auto-created) |
| AI | DeepSeek API (`deepseek-chat`) via `openai` SDK |
| CV Parsing | PyPDF2 → DeepSeek extraction (heuristic fallback) |
| Game Logic | `game_mechanics.py` — XP, quests, friends, profile completeness |

## Project Structure

```
app.py               # Flask factory + entrypoint
config.py            # Settings, env vars, paths
auth.py              # Password hashing, register/login
db.py                # SQLite init + connection
game_mechanics.py    # Friends, quests, XP, completeness
ai_extractor.py      # PDF parsing, DeepSeek API, fallback
routes/
  auth_routes.py     # /login, /signup, /logout
  candidate.py       # /dashboard, /profile, /cv, /friends, /quests, /jobs
  employer.py        # /employer/*
  university.py      # /university/*
templates/           # 14 Jinja2 templates
static/              # CSS + logo
```

## Environment

| Variable | Required | Default |
|---|---|---|
| `DEEPSEEK_API_KEY` | For AI features | — |
| `SECRET_KEY` | For session persistence | Random (resets on restart) |
| `FLASK_ENV` | Debug toggle | — |
| `PORT` | Listen port | 5000 |
