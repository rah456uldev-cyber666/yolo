import os
from functools import lru_cache

from app.config.config import EMBEDDING_MODEL, EMBEDDING_MODEL_DIR, OFFLINE_MODE  # sets offline env vars first
from app.common.custom_exception import CustomException
from app.common.logger import get_logger

logger = get_logger(__name__)


def resolve_embedding_model():
    """Prefer the copy bundled in models/, so no internet is needed."""
    if os.path.isfile(os.path.join(EMBEDDING_MODEL_DIR, "config.json")):
        return EMBEDDING_MODEL_DIR
    return EMBEDDING_MODEL


@lru_cache(maxsize=1)
def get_embedding_model():
    """Load the embedding model once and reuse it (it is slow to load)."""
    from langchain_huggingface import HuggingFaceEmbeddings

    model_ref = resolve_embedding_model()
    try:
        logger.info("Loading embedding model from %s (offline mode: %s)", model_ref, OFFLINE_MODE)
        model = HuggingFaceEmbeddings(model_name=model_ref, model_kwargs={"device": "cpu"})
        logger.info("Embedding model loaded")
        return model
    except Exception as e:
        hint = ""
        if model_ref != EMBEDDING_MODEL_DIR:
            hint = (" The embedding model is not in models/ yet. Run once with internet: "
                    "python scripts/download_models.py")
        error = CustomException("Failed to load embedding model." + hint, e)
        logger.error(str(error))
        raise error
