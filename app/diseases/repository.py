"""Read-only access to the disease database (database/diseases.db).

Build or rebuild it with:  python scripts/build_disease_db.py
"""
import json
import os
import re
import sqlite3
from functools import lru_cache

from app.config.config import DISEASE_DB_PATH

STOPWORDS = {"and", "or", "the", "a", "an", "of", "in", "on", "my", "i", "have", "with", "pain", "feel", "feeling"}


def _connect(path=None):
    path = path or DISEASE_DB_PATH
    if not os.path.exists(path):
        return None
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _to_dict(row):
    d = dict(row)
    d["symptoms"] = json.loads(d.pop("symptoms_json") or "[]")
    return d


def is_available():
    return os.path.exists(DISEASE_DB_PATH)


def stats():
    con = _connect()
    if con is None:
        return {"count": 0}
    with con:
        meta = {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM meta")}
        count = con.execute("SELECT COUNT(*) FROM diseases").fetchone()[0]
    return {"count": count, "built_at": meta.get("built_at"), "sources": json.loads(meta.get("sources", "[]"))}


def letters():
    con = _connect()
    if con is None:
        return []
    with con:
        return [r[0] for r in con.execute("SELECT DISTINCT letter FROM diseases ORDER BY letter")]


def search(query="", letter=None, limit=500):
    """Search by disease name first, then by symptom/description text."""
    con = _connect()
    if con is None:
        return []
    query = (query or "").strip()
    with con:
        if query:
            like = f"%{query}%"
            rows = con.execute(
                """SELECT *, CASE WHEN name LIKE ? THEN 0 WHEN symptoms_json LIKE ? THEN 1 ELSE 2 END AS rank
                   FROM diseases
                   WHERE name LIKE ? OR symptoms_json LIKE ? OR causes_and_symptoms LIKE ? OR definition LIKE ?
                   ORDER BY rank, name LIMIT ?""",
                (like, like, like, like, like, like, limit),
            ).fetchall()
        elif letter:
            rows = con.execute("SELECT * FROM diseases WHERE letter=? ORDER BY name", (letter.upper(),)).fetchall()
        else:
            rows = con.execute("SELECT * FROM diseases ORDER BY name LIMIT ?", (limit,)).fetchall()
    return [_to_dict(r) for r in rows]


def get_by_slug(slug):
    con = _connect()
    if con is None:
        return None
    with con:
        row = con.execute("SELECT * FROM diseases WHERE slug=?", (slug,)).fetchone()
    return _to_dict(row) if row else None


@lru_cache(maxsize=1)
def _name_index():
    con = _connect()
    if con is None:
        return []
    with con:
        rows = con.execute("SELECT slug, name FROM diseases").fetchall()
    index = []
    for r in rows:
        name = r["name"].lower().replace("’", "'")
        variants = {name, re.sub(r"\s*\(.*?\)", "", name)}
        if "," in name:  # "Cholesterol, high" -> "high cholesterol"
            a, b = [p.strip() for p in name.split(",", 1)]
            variants.add(f"{b} {a}")
        for v in variants:
            if len(v) >= 4:
                index.append((v, r["slug"]))
    index.sort(key=lambda x: -len(x[0]))  # longest names first
    return index


def find_mentioned(text, max_results=2):
    """Return diseases whose name appears in the text (used to enrich chatbot answers)."""
    text = (text or "").lower().replace("’", "'")
    found, slugs = [], set()
    for name, slug in _name_index():
        if slug in slugs:
            continue
        if re.search(rf"\b{re.escape(name)}s?\b", text):
            disease = get_by_slug(slug)
            if disease:
                found.append(disease)
                slugs.add(slug)
                text = text.replace(name, " ")
        if len(found) >= max_results:
            break
    return found


def summarize_for_llm(disease, max_chars=1500):
    parts = [f"Disease: {disease['name']}"]
    if disease["definition"]:
        parts.append(f"Definition: {disease['definition']}")
    if disease["symptoms"]:
        parts.append("Common symptoms: " + "; ".join(disease["symptoms"]))
    if disease["treatment"]:
        parts.append(f"Treatment: {disease['treatment'][:600]}")
    if disease["prevention"]:
        parts.append(f"Prevention: {disease['prevention'][:300]}")
    return "\n".join(parts)[:max_chars]


def symptom_check(symptom_text, limit=10):
    """Rank diseases by how many of the entered symptoms they mention.

    This is a simple keyword match for education only. It is NOT a diagnosis.
    """
    terms = []
    for part in re.split(r"[,;\n]+", symptom_text or ""):
        part = part.strip().lower()
        if len(part) >= 3 and part not in STOPWORDS:
            terms.append(part)
    terms = terms[:10]
    if not terms:
        return [], []
    con = _connect()
    if con is None:
        return terms, []
    with con:
        rows = con.execute("SELECT * FROM diseases").fetchall()
    results = []
    for r in rows:
        d = _to_dict(r)
        symptom_list = " | ".join(d["symptoms"]).lower()
        body = (d["causes_and_symptoms"] or "").lower() + " " + (d["definition"] or "").lower()
        matched, score = [], 0.0
        for t in terms:
            if t in symptom_list:
                matched.append(t)
                score += 2
            elif t in body:
                matched.append(t)
                score += 1
        if matched:
            results.append({"disease": d, "matched": matched, "score": score / len(terms)})
    results.sort(key=lambda x: (-len(x["matched"]), -x["score"], x["disease"]["name"]))
    return terms, results[:limit]
