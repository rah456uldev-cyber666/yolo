"""Retrieval-augmented answering over the encyclopedia.

The vector store, embedding model and LLM are loaded once (on first use) and
reused for every question, instead of being rebuilt per request.
"""
import os
import threading

from langchain_core.prompts import PromptTemplate

from app.common.custom_exception import CustomException
from app.common.logger import get_logger
from app.components.llm import load_llm
from app.components.vector_store import load_vector_store
from app.config.config import RETRIEVER_K

logger = get_logger(__name__)

ANSWER_PROMPT = PromptTemplate(
    input_variables=["context", "history", "question", "disease_info"],
    template="""You are Medibot, a careful medical information assistant.
Answer the user's question using ONLY the encyclopedia context and disease notes below.
- Be clear and concise (one short paragraph, or a short bullet list when listing symptoms or treatments).
- If the context does not contain the answer, say you could not find it in the encyclopedia. Do not guess.
- Never give a definitive diagnosis or exact drug doses. Suggest seeing a doctor where appropriate.

Recent conversation:
{history}

Disease notes:
{disease_info}

Encyclopedia context:
{context}

Question: {question}

Answer:""",
)

CONDENSE_PROMPT = PromptTemplate(
    input_variables=["history", "question"],
    template="""Rewrite the follow-up question as a single standalone question, using the conversation for context.
Return only the rewritten question.

Conversation:
{history}

Follow-up question: {question}

Standalone question:""",
)


class RagService:
    def __init__(self, db, llm, k=RETRIEVER_K):
        self.db = db
        self.llm = llm
        self.k = k

    @staticmethod
    def _format_history(history):
        if not history:
            return "(none)"
        return "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in history)

    def _standalone_question(self, question, history):
        # Only short follow-ups ("how is it treated?") need rewriting. Skipping the
        # rest saves one model call, which matters for a local model on a laptop CPU.
        if not history or len(question.split()) > 12:
            return question
        try:
            prompt = CONDENSE_PROMPT.format(history=self._format_history(history), question=question)
            rewritten = self.llm.invoke(prompt).content.strip()
            return rewritten or question
        except Exception as e:  # fall back to the raw question
            logger.warning("Could not condense question: %s", e)
            return question

    def answer(self, question, history=None, disease_info=""):
        search_query = self._standalone_question(question, history)
        docs = self.db.similarity_search(search_query, k=self.k)
        context = "\n\n---\n\n".join(d.page_content for d in docs)
        prompt = ANSWER_PROMPT.format(
            context=context or "(nothing found)",
            history=self._format_history(history),
            question=question,
            disease_info=disease_info or "(none)",
        )
        try:
            result = self.llm.invoke(prompt).content.strip()
            used_llm = True
        except Exception as e:
            # The AI model is not available (e.g. Ollama not running). Still answer,
            # straight from the encyclopedia passages and the disease database.
            logger.warning("LLM unavailable, using extractive fallback: %s", e)
            result = self._extractive_answer(docs, disease_info, e)
            used_llm = False

        sources, seen = [], set()
        for d in docs:
            page = d.metadata.get("page")
            source = os.path.basename(str(d.metadata.get("source", "encyclopedia")))
            key = (source, page)
            if key in seen:
                continue
            seen.add(key)
            sources.append({
                "source": source,
                "page": (page + 1) if isinstance(page, int) else page,
                "snippet": d.page_content[:220].replace("\n", " "),
            })
        return {"answer": result, "sources": sources, "search_query": search_query, "used_llm": used_llm}

    @staticmethod
    def _extractive_answer(docs, disease_info, error):
        parts = ["(The AI model is not running, so here is the most relevant text from the encyclopedia.)"]
        if disease_info:
            parts.append(disease_info)
        for d in docs[:2]:
            parts.append("• " + " ".join(d.page_content.split()))
        if len(parts) == 1:
            parts.append("Nothing relevant was found.")
        parts.append(f"Tip: {error}")
        return "\n\n".join(parts)


_service = None
_lock = threading.Lock()


def get_rag_service():
    """Return the shared RagService, creating it on first use."""
    global _service
    if _service is None:
        with _lock:
            if _service is None:
                db = load_vector_store()
                if db is None:
                    raise CustomException("Vector store not found. Build it with: python -m app.components.data_loader")
                _service = RagService(db, load_llm())
                logger.info("RAG service ready")
    return _service
