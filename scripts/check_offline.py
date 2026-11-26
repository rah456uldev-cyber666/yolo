"""Check that everything Medibot needs to run offline is in place.

    python scripts/check_offline.py

Tip for a demo: turn off Wi-Fi, run this, then start the app.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from app.config import config  # noqa: E402

OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"
problems = 0


def report(status, text):
    global problems
    if status == BAD:
        problems += 1
    print(f"{status} {text}")


print("Medibot offline self-check\n")
report(OK if config.OFFLINE_MODE else WARN,
       f"OFFLINE_MODE={config.OFFLINE_MODE} (Hugging Face network access {'disabled' if config.OFFLINE_MODE else 'allowed'})")

# Embedding model
if os.path.isfile(os.path.join(config.EMBEDDING_MODEL_DIR, "config.json")):
    report(OK, f"Embedding model bundled in {os.path.relpath(config.EMBEDDING_MODEL_DIR)}")
else:
    report(BAD, "Embedding model not in models/. Run once with internet: python scripts/download_models.py")

# Vector index and databases
report(OK if os.path.isfile(os.path.join(config.DB_FAISS_PATH, "index.faiss")) else BAD,
       f"Encyclopedia search index: {os.path.relpath(config.DB_FAISS_PATH)}")
report(OK if os.path.isfile(config.DISEASE_DB_PATH) else BAD,
       f"Disease database: {os.path.relpath(config.DISEASE_DB_PATH)}")

# LLM
from app.components.llm import OllamaChat  # noqa: E402

if config.LLM_PROVIDER == "ollama":
    ok, msg = OllamaChat().status()
    report(OK if ok else BAD, msg + ("" if ok else "  (chat will still answer with encyclopedia text only)"))
else:
    report(WARN, f"LLM_PROVIDER={config.LLM_PROVIDER}: answers need internet. Use LLM_PROVIDER=ollama for offline.")

# SMS
from app.auth.sms import sms_status  # noqa: E402

report(OK, "OTP: " + sms_status())

# Quick functional test of the embedding model (no network)
if os.path.isfile(os.path.join(config.EMBEDDING_MODEL_DIR, "config.json")):
    try:
        from app.components.embeddings import get_embedding_model
        vec = get_embedding_model().embed_query("fever and headache")
        report(OK, f"Embedding model works offline ({len(vec)} dimensions)")
    except Exception as e:
        report(BAD, f"Embedding model failed to load: {e}")

print("\nAll good - Medibot can run without internet." if not problems
      else f"\n{problems} problem(s) found. See readme.txt, section 'OFFLINE SETUP'.")
sys.exit(1 if problems else 0)
