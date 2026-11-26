"""Language model providers.

LLM_PROVIDER=ollama (default) runs a model locally with Ollama - no internet needed.
LLM_PROVIDER=groq uses the Groq cloud API - needs internet and GROQ_API_KEY.

Both return an object with .invoke(prompt) -> object with .content (same as LangChain chat models).
"""
from dataclasses import dataclass

import requests

from app.common.custom_exception import CustomException
from app.common.logger import get_logger
from app.config import config

logger = get_logger(__name__)


class LlmUnavailable(Exception):
    """The model could not be reached (e.g. Ollama not running)."""


@dataclass
class LlmReply:
    content: str


class OllamaChat:
    """Minimal client for a local Ollama server (https://ollama.com)."""

    def __init__(self, model=None, base_url=None, temperature=None, max_tokens=None, timeout=None):
        self.model = model or config.OLLAMA_MODEL
        self.base_url = (base_url or config.OLLAMA_BASE_URL).rstrip("/")
        self.temperature = config.LLM_TEMPERATURE if temperature is None else temperature
        self.max_tokens = max_tokens or config.LLM_MAX_TOKENS
        self.timeout = timeout or config.OLLAMA_TIMEOUT_SECONDS

    def invoke(self, prompt: str) -> LlmReply:
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "keep_alive": "30m",
                    "options": {"temperature": self.temperature, "num_predict": self.max_tokens},
                },
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise LlmUnavailable(f"Ollama is not running at {self.base_url}. Start the Ollama app "
                                 f"(or run 'ollama serve'). Details: {e}")
        if resp.status_code == 404:
            raise LlmUnavailable(f"Model '{self.model}' is not installed. Run: ollama pull {self.model}")
        if resp.status_code >= 300:
            raise LlmUnavailable(f"Ollama error {resp.status_code}: {resp.text[:200]}")
        return LlmReply(resp.json().get("message", {}).get("content", "").strip())

    def status(self):
        """Return (ok, message) for the self-check and /health."""
        try:
            tags = requests.get(f"{self.base_url}/api/tags", timeout=3).json().get("models", [])
        except requests.RequestException:
            return False, f"Ollama is not running at {self.base_url}"
        names = {m.get("name") for m in tags} | {m.get("model") for m in tags}
        wanted = {self.model, f"{self.model}:latest"}
        if names & wanted:
            return True, f"Ollama is running and '{self.model}' is installed"
        return False, f"Ollama is running but '{self.model}' is not installed (run: ollama pull {self.model})"

    @property
    def label(self):
        return f"{self.model} (local, Ollama)"


def _load_groq():
    if not config.GROQ_API_KEY:
        raise CustomException("GROQ_API_KEY is not set. Add it to .env or use LLM_PROVIDER=ollama.")
    from langchain_groq import ChatGroq

    llm = ChatGroq(groq_api_key=config.GROQ_API_KEY, model_name=config.GROQ_MODEL,
                   temperature=config.LLM_TEMPERATURE, max_tokens=config.LLM_MAX_TOKENS)
    llm.label = f"{config.GROQ_MODEL} (Groq cloud)"  # type: ignore[attr-defined]
    return llm


def load_llm(provider: str = None):
    provider = (provider or config.LLM_PROVIDER).lower()
    logger.info("Using LLM provider: %s", provider)
    if provider == "ollama":
        return OllamaChat()
    if provider == "groq":
        return _load_groq()
    raise CustomException(f"Unknown LLM_PROVIDER '{provider}'. Use 'ollama' or 'groq'.")


def llm_label():
    if config.LLM_PROVIDER == "groq":
        return f"{config.GROQ_MODEL} (Groq cloud)"
    return f"{config.OLLAMA_MODEL} (local, Ollama)"
