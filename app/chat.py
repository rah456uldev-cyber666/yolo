"""Chat pages and API. History is stored per user in the database, not in the cookie."""
import json
import re

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from app.auth.security import login_required
from app.common.logger import get_logger
from app.config import config
from app.db import get_db, now
from app.diseases import repository as disease_repo

logger = get_logger(__name__)
bp = Blueprint("chat", __name__)

MAX_QUESTION_CHARS = 1000
EMERGENCY_PATTERNS = [
    r"chest pain", r"can'?t breathe", r"cannot breathe", r"difficulty breathing", r"not breathing",
    r"unconscious", r"severe bleeding", r"bleeding heavily", r"heart attack", r"stroke",
    r"overdose", r"poison(ed|ing)", r"seizure", r"suicid", r"kill myself", r"self[- ]harm",
]
EMERGENCY_MESSAGE = ("This may be a medical emergency. Please call your local emergency number "
                     "(112 in India and Europe, 911 in the US) or go to the nearest hospital now.")
SELF_HARM_MESSAGE = ("If you are thinking about harming yourself, please reach out right now: "
                     "call your local emergency number, or a crisis line such as 14416 (Tele-MANAS, India) "
                     "or 988 (US). You are not alone.")


def emergency_notice(text):
    t = text.lower()
    if re.search(r"suicid|kill myself|self[- ]harm|end my life", t):
        return SELF_HARM_MESSAGE
    if any(re.search(p, t) for p in EMERGENCY_PATTERNS):
        return EMERGENCY_MESSAGE
    return None


def load_history(user_id, limit=100):
    rows = get_db().execute(
        "SELECT * FROM (SELECT * FROM chat_messages WHERE user_id=? ORDER BY id DESC LIMIT ?) ORDER BY id",
        (user_id, limit),
    ).fetchall()
    out = []
    for r in rows:
        extra = json.loads(r["sources_json"] or "{}")
        out.append({"role": r["role"], "content": r["content"], "created_at": r["created_at"],
                    "sources": extra.get("sources", []), "diseases": extra.get("diseases", []),
                    "notice": extra.get("notice")})
    return out


def save_message(user_id, role, content, extra=None):
    db = get_db()
    db.execute("INSERT INTO chat_messages (user_id, role, content, sources_json, created_at) VALUES (?,?,?,?,?)",
               (user_id, role, content, json.dumps(extra or {}), now()))
    db.commit()


def answer_question(user_id, question):
    """Run the RAG pipeline and store both messages. Returns the assistant message dict."""
    from app.components.retriever import get_rag_service  # heavy import, loaded on first question

    history = [{"role": m["role"], "content": m["content"]}
               for m in load_history(user_id, limit=config.CHAT_HISTORY_TURNS * 2)]
    save_message(user_id, "user", question)

    notice = emergency_notice(question)
    mentioned = disease_repo.find_mentioned(question)
    disease_info = "\n\n".join(disease_repo.summarize_for_llm(d) for d in mentioned)
    try:
        result = get_rag_service().answer(question, history=history, disease_info=disease_info)
        answer, sources = result["answer"], result["sources"]
    except Exception as e:
        logger.exception("Chat failed")
        sources = []
        reason = str(e).split(" | ")[0] if " | " in str(e) else str(e)
        if "embedding model" in str(e).lower():
            reason = ("The search model is not set up yet. Run once: python scripts/download_models.py "
                      "(see readme.txt, OFFLINE SETUP).")
        if mentioned:
            # Still useful offline: answer from the local disease database.
            answer = ("From the disease library:\n\n" + disease_info +
                      f"\n\n(Full encyclopedia search is unavailable right now: {reason})")
        else:
            answer = f"Sorry, I could not answer that right now. {reason}"
    extra = {"sources": sources, "notice": notice,
             "diseases": [{"slug": d["slug"], "name": d["name"]} for d in mentioned]}
    save_message(user_id, "assistant", answer, extra)
    return {"role": "assistant", "content": answer, **extra}


def _validate(question):
    question = (question or "").strip()
    if not question:
        return None, "Please type a question."
    if len(question) > MAX_QUESTION_CHARS:
        return None, f"Please keep questions under {MAX_QUESTION_CHARS} characters."
    return question, None


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        question, error = _validate(request.form.get("prompt"))
        if error:
            flash(error, "error")
        else:
            answer_question(g.user["id"], question)
        return redirect(url_for("chat.index"))  # Post/Redirect/Get: refresh won't resend
    return render_template("chat.html", messages=load_history(g.user["id"]),
                           suggestions=["What are the symptoms of dengue fever?",
                                        "How is carpal tunnel syndrome treated?",
                                        "What causes cataracts?",
                                        "How can I prevent food poisoning?"])


@bp.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    data = request.get_json(silent=True) or {}
    question, error = _validate(data.get("question"))
    if error:
        return jsonify({"error": error}), 400
    return jsonify(answer_question(g.user["id"], question))


@bp.route("/api/history")
@login_required
def api_history():
    return jsonify(load_history(g.user["id"]))


@bp.route("/clear", methods=["POST"])
@login_required
def clear():
    db = get_db()
    db.execute("DELETE FROM chat_messages WHERE user_id=?", (g.user["id"],))
    db.commit()
    flash("Chat history cleared.", "info")
    return redirect(url_for("chat.index"))
