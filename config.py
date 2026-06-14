import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24).hex())
DEBUG = os.environ.get("FLASK_ENV") == "development"

DATABASE = os.path.join(BASE_DIR, "lifequest.db")

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
AVATAR_FOLDER = os.path.join(UPLOAD_FOLDER, "avatars")
TASK_PROOF_FOLDER = os.path.join(UPLOAD_FOLDER, "task_proofs")
CV_PROOF_FOLDER = os.path.join(UPLOAD_FOLDER, "cv_proofs")

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = "deepseek-chat"

ALLOWED_AVATAR_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
ALLOWED_PROOF_EXT = {".pdf", ".png", ".jpg", ".jpeg"}
