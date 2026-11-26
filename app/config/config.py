"""Central configuration. Every value can be overridden in the .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Project root (the folder that contains app/, Data/, vectorstore/ ...)
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _path(name, default):
    value = Path(os.environ.get(name, default))
    return value if value.is_absolute() else BASE_DIR / value


# ---- Flask -----------------------------------------------------------------
# A fixed secret key keeps users logged in across restarts. Set it in .env!
SECRET_KEY = os.environ.get("SECRET_KEY", "")
SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)  # True when served over HTTPS
SESSION_LIFETIME_DAYS = int(os.environ.get("SESSION_LIFETIME_DAYS", 7))

# ---- Offline mode ----------------------------------------------------------
# When true (default), nothing is downloaded from the internet at runtime:
# the embedding model is read from models/ (or the local Hugging Face cache)
# and answers come from a local Ollama model.
OFFLINE_MODE = _bool("OFFLINE_MODE", True)

# ---- LLM ---------------------------------------------------------------------
# ollama = local model on this computer (works without internet, default)
# groq   = Groq cloud API (needs internet and GROQ_API_KEY)
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", 180))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", os.environ.get("LLM_MODEL", "llama-3.1-8b-instant"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", 0.2))
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", 600))

# ---- Retrieval (RAG) -------------------------------------------------------
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
# Local copy of the embedding model (created by: python scripts/download_models.py)
EMBEDDING_MODEL_DIR = str(_path("EMBEDDING_MODEL_DIR", "models/all-MiniLM-L6-v2"))
DATA_PATH = str(_path("DATA_PATH", "Data"))
DB_FAISS_PATH = str(_path("DB_FAISS_PATH", "vectorstore/db_faiss"))
CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 500))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", 50))
RETRIEVER_K = int(os.environ.get("RETRIEVER_K", 4))
CHAT_HISTORY_TURNS = int(os.environ.get("CHAT_HISTORY_TURNS", 3))

# ---- Databases -------------------------------------------------------------
USER_DB_PATH = str(_path("USER_DB_PATH", "database/medibot.db"))
DISEASE_DB_PATH = str(_path("DISEASE_DB_PATH", "database/diseases.db"))

# ---- OTP / SMS ---------------------------------------------------------------
# auto (default) = real SMS via Fast2SMS, then Twilio, whichever has keys in .env.
#                  If no keys are set, or there is no internet, the OTP is shown
#                  on screen / in the terminal instead (offline demo mode).
# fast2sms | twilio = only that provider (still falls back if SMS_FALLBACK=true)
# console = never send SMS; always show the OTP on screen / in the terminal
SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "auto").strip().lower()
SMS_FALLBACK = _bool("SMS_FALLBACK", True)            # fall back to on-screen OTP if SMS fails
SHOW_OTP_ON_SCREEN = _bool("SHOW_OTP_ON_SCREEN", True)  # show fallback OTP on the page (demo/offline)
DEFAULT_COUNTRY_CODE = os.environ.get("DEFAULT_COUNTRY_CODE", "+91")
OTP_LENGTH = int(os.environ.get("OTP_LENGTH", 6))
OTP_TTL_SECONDS = int(os.environ.get("OTP_TTL_SECONDS", 300))
OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", 5))
OTP_RESEND_COOLDOWN_SECONDS = int(os.environ.get("OTP_RESEND_COOLDOWN_SECONDS", 60))
OTP_MAX_SENDS_PER_HOUR = int(os.environ.get("OTP_MAX_SENDS_PER_HOUR", 5))

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")
FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY", "")
FAST2SMS_ROUTE = os.environ.get("FAST2SMS_ROUTE", "q").strip().lower()  # q (Quick SMS) | otp

# ---- Login protection -------------------------------------------------------
LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", 5))
LOGIN_LOCK_MINUTES = int(os.environ.get("LOGIN_LOCK_MINUTES", 15))

# ---- Logging -----------------------------------------------------------------
LOGS_DIR = str(_path("LOGS_DIR", "logs"))

# Tell Hugging Face libraries not to touch the network in offline mode.
if OFFLINE_MODE:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
