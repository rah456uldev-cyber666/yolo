# Load settings first so offline-mode environment variables (HF_HUB_OFFLINE, ...)
# are set before any Hugging Face library is imported.
from app.config import config as _config  # noqa: F401
