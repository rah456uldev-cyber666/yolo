import os

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader

from app.common.custom_exception import CustomException
from app.common.logger import get_logger
from app.config.config import CHUNK_OVERLAP, CHUNK_SIZE, DATA_PATH

logger = get_logger(__name__)


def load_pdf_files(data_path: str = DATA_PATH):
    if not os.path.exists(data_path):
        raise CustomException(f"DATA_PATH does not exist: {data_path}")
    logger.info("Loading PDF files from %s", data_path)
    loader = DirectoryLoader(data_path, glob="*.pdf", loader_cls=PyPDFLoader)
    documents = loader.load()
    if not documents:
        logger.warning("No PDF files were found in %s", data_path)
    else:
        logger.info("Loaded %d PDF pages", len(documents))
    return documents


def create_text_chunks(documents):
    if not documents:
        raise CustomException("No documents to split")
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = splitter.split_documents(documents)
    logger.info("Generated %d text chunks", len(chunks))
    return chunks
