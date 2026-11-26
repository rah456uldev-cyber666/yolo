"""Build the offline data files used by the mobile/PC app (mobile/www/data/).

    python scripts/build_mobile_data.py

Creates:
  diseases.js  - the disease library (from database/diseases.db)
  passages.js  - the encyclopedia text split into short passages with page numbers,
                   searched on the device (no internet, no server)
Run it again after adding PDFs to Data/ and rebuilding the disease database.
"""
import json
import logging
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "mobile", "www", "data")
PAGE_HEADER = re.compile(r"^\s*GALE ENCYCLOPEDIA OF MEDICINE\s*2?\s*\d*\s*$", re.I)
MAX_CHARS = 700


def build_diseases():
    con = sqlite3.connect(os.path.join(ROOT, "database", "diseases.db"))
    con.row_factory = sqlite3.Row
    cols = ["slug", "name", "definition", "description", "causes_and_symptoms", "diagnosis", "treatment",
            "alternative_treatment", "prognosis", "prevention", "source_page"]
    items = []
    for r in con.execute("SELECT * FROM diseases ORDER BY name"):
        d = {c: r[c] for c in cols}
        d["symptoms"] = json.loads(r["symptoms_json"] or "[]")
        items.append(d)
    return items


def clean_page(text):
    lines, skip_next = [], False
    for line in text.split("\n"):
        if PAGE_HEADER.match(line):
            skip_next = True
            continue
        if skip_next:
            skip_next = False
            continue
        lines.append(line.strip())
    out = ""
    for line in lines:
        if not line:
            continue
        if out.endswith("-") and line[:1].islower():
            out = out[:-1] + line
        else:
            out = (out + " " + line) if out else line
    return re.sub(r"\s{2,}", " ", out).strip()


def build_passages():
    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    data_dir = os.path.join(ROOT, "Data")
    passages = []
    for name in sorted(f for f in os.listdir(data_dir) if f.lower().endswith(".pdf")):
        reader = PdfReader(os.path.join(data_dir, name))
        for i, page in enumerate(reader.pages):
            text = clean_page(page.extract_text() or "")
            if len(text) < 80:
                continue
            sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
            chunk = ""
            for s in sentences:
                if chunk and len(chunk) + len(s) > MAX_CHARS:
                    passages.append({"p": i + 1, "t": chunk})
                    chunk = s
                else:
                    chunk = (chunk + " " + s).strip()
            if len(chunk) > 60:
                passages.append({"p": i + 1, "t": chunk})
    return passages


def main():
    os.makedirs(OUT, exist_ok=True)
    diseases = build_diseases()
    # Saved as .js (not .json) so the app also works when opened straight from a file.
    with open(os.path.join(OUT, "diseases.js"), "w", encoding="utf-8") as f:
        f.write("window.MB_DISEASES=" + json.dumps(diseases, ensure_ascii=False, separators=(",", ":")) + ";\n")
    passages = build_passages()
    with open(os.path.join(OUT, "passages.js"), "w", encoding="utf-8") as f:
        f.write("window.MB_PASSAGES=" + json.dumps(passages, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"Saved {len(diseases)} diseases and {len(passages)} passages to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
