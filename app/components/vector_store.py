import os

from langchain_community.vectorstores import FAISS

from app.common.custom_exception import CustomException
from app.common.logger import get_logger
from app.components.embeddings import get_embedding_model
from app.config.config import DB_FAISS_PATH

logger = get_logger(__name__)


def load_vector_store(path: str = DB_FAISS_PATH):
    if not os.path.exists(path):
        logger.warning("No vector store found at %s. Run: python -m app.components.data_loader", path)
        return None
    try:
        logger.info("Loading vector store from %s", path)
        # allow_dangerous_deserialization is needed because FAISS metadata is a pickle.
        # Only load vector stores that you built yourself.
        return FAISS.load_local(path, get_embedding_model(), allow_dangerous_deserialization=True)
    except Exception as e:
        error = CustomException("Failed to load vector store", e)
        logger.error(str(error))
        raise error


def save_vector_store(text_chunks, path: str = DB_FAISS_PATH):
    if not text_chunks:
        raise CustomException("No chunks to index")
    logger.info("Building vector store from %d chunks", len(text_chunks))
    db = FAISS.from_documents(text_chunks, get_embedding_model())
    db.save_local(path)
    logger.info("Vector store saved to %s", path)
    return db
