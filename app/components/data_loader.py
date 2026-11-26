"""Rebuild the FAISS vector store from every PDF in DATA_PATH.

Run from the project root:  python -m app.components.data_loader
"""
from app.common.custom_exception import CustomException
from app.common.logger import get_logger
from app.components.load_pdf import create_text_chunks, load_pdf_files
from app.components.vector_store import save_vector_store

logger = get_logger(__name__)


def process_and_store_pdfs():
    try:
        documents = load_pdf_files()
        chunks = create_text_chunks(documents)
        save_vector_store(chunks)
        logger.info("Vector store created")
    except Exception as e:
        error = CustomException("Failed to create vector store", e)
        logger.error(str(error))
        raise error


if __name__ == "__main__":
    process_and_store_pdfs()
