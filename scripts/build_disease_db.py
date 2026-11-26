"""Build the disease database (symptoms, treatments, remedies) from the encyclopedia PDFs.

Usage (from the project root):
    python scripts/build_disease_db.py                 # reads every PDF in Data/
    python scripts/build_disease_db.py --pdf-dir Data --out database/diseases.db

How it works
------------
Every Gale Encyclopedia entry starts with its title followed by a "Definition"
heading, and is divided into standard headings (Description, Causes and
symptoms, Diagnosis, Treatment, Alternative treatment, Prognosis, Prevention,
Resources). The script walks the text line by line, detects those headings and
stores each section. Entries that have a symptoms section are treated as
diseases/conditions; drugs, tests and procedures are skipped.

PDF text extraction is never perfect, so some entries may contain small
artefacts (e.g. stray words from side boxes). Re-run the script after adding
more volumes of the encyclopedia to Data/.
"""
import argparse
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    sys.exit("pypdf is required: pip install pypdf")

# Section headings used by the encyclopedia -> column name in the database.
SECTION_MAP = {
    "definition": "definition",
    "description": "description",
    "demographics": "description",
    "causes and symptoms": "causes_and_symptoms",
    "causes": "causes_and_symptoms",
    "symptoms": "causes_and_symptoms",
    "signs and symptoms": "causes_and_symptoms",
    "diagnosis": "diagnosis",
    "treatment": "treatment",
    "treatments": "treatment",
    "surgery": "treatment",
    "drugs": "treatment",
    "medications": "treatment",
    "home care": "treatment",
    "alternative treatment": "alternative_treatment",
    "alternative treatments": "alternative_treatment",
    "alternative and complementary therapies": "alternative_treatment",
    "prognosis": "prognosis",
    "prevention": "prevention",
}
# Headings that end the useful part of an entry (or belong to non-disease entries).
STOP_HEADINGS = {"resources", "books", "periodicals", "organizations", "organization", "other"}
IGNORED_HEADINGS = {
    "purpose", "precautions", "preparation", "aftercare", "risks", "normal results",
    "abnormal results", "side effects", "interactions", "recommended dosage", "origins",
    "special conditions", "preparations", "general use", "key terms",
}

PAGE_HEADER = re.compile(r"^\s*GALE ENCYCLOPEDIA OF MEDICINE\s*2?\s*\d*\s*$", re.I)
PAGE_HEADER_INLINE = re.compile(r"GALE ENCYCLOPEDIA OF MEDICINE\s*2\s*\d+", re.I)
CAPTION_HINTS = ("(Illustration by", "(Photograph by", "Reproduced by permission", "(Courtesy of",
                 "Custom Medical Stock", "Photo Researchers", "(Photo by", "Phototake")
BULLET = re.compile(r"^\s*[•●▪\-–]\s*(.+)$")
SYMPTOM_WORDS = re.compile(r"\b(symptom|symptoms|signs?|include|includes|including|experience|suffer|complain)\b", re.I)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def read_lines(pdf_paths):
    """Yield (pdf_name, page_number, line) for every text line, without page headers."""
    for path in pdf_paths:
        reader = PdfReader(path)
        name = os.path.basename(path)
        for page_index, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
            except Exception:
                continue
            lines = text.split("\n")
            skip_running_head = False
            for line in lines:
                if PAGE_HEADER.match(line):
                    skip_running_head = True  # next line is the running head (entry name)
                    continue
                if skip_running_head:
                    skip_running_head = False
                    continue
                line = PAGE_HEADER_INLINE.sub("", line)
                yield name, page_index + 1, line.rstrip()


def join_text(lines):
    """Join PDF lines into clean paragraphs, fixing words hyphenated across lines."""
    out = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if BULLET.match(line) and line.lstrip()[:1] in "•●▪":
            out = (out + "\n" if out else "") + "• " + BULLET.match(line).group(1).strip()
        elif out.endswith("-") and line[:1].islower():
            out = out[:-1] + line
        elif out:
            out += " " + line
        else:
            out = line
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


def strip_side_boxes(lines):
    """Remove 'KEY TERMS' glossary boxes and figure captions that pypdf mixes into the text."""
    cleaned, in_box, prev_ended = [], False, True
    for line in lines:
        s = line.strip()
        if s.upper() == "KEY TERMS":
            in_box, prev_ended = True, True
            continue
        if in_box:
            looks_like_term = "—" in s[:60]
            if looks_like_term or not prev_ended:
                prev_ended = s.endswith(".")
                continue
            in_box = False
        if any(h in s for h in CAPTION_HINTS):
            continue
        cleaned.append(line)
    return cleaned


def extract_symptom_list(section_lines, text):
    """Pull a short list of symptoms: bullet points first, then 'symptoms include ...' phrases."""
    items = []
    for line in section_lines:
        m = BULLET.match(line)
        if m:
            item = m.group(1).strip().rstrip(".;,")
            if 2 < len(item) < 80:
                items.append(item)
    if not items:
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if not SYMPTOM_WORDS.search(sentence):
                continue
            m = re.search(r"\b(?:include|includes|including|are|such as)\b[:\s]+(.+?)[.]?$", sentence, re.I)
            if not m:
                continue
            tail = re.sub(r"\([^)]*\)", "", m.group(1))
            for part in re.split(r",|;|\band\b|\bor\b", tail):
                part = part.strip(" .:")
                if 2 < len(part) < 50 and len(part.split()) <= 6:
                    items.append(part)
            if len(items) >= 15:
                break
    seen, unique = set(), []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique[:20]


def find_title(buffer):
    """The entry title is the line(s) just before 'Definition'."""
    candidates = [l.strip() for l in buffer[-4:] if l.strip()]
    if not candidates:
        return None
    title = candidates[-1]
    # Titles that wrap onto a second line start with a lowercase word, e.g. "resuscitation (CPR)".
    if len(candidates) >= 2 and title[:1].islower():
        title = candidates[-2] + " " + title
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) > 80 or title.endswith(".") or not title[:1].isupper():
        return None
    return title


def parse_entries(line_iter):
    entries, current, buffer = [], None, []
    section, section_lines = None, {}

    def close_section():
        if current is not None and section:
            current["_raw"].setdefault(section, []).extend(section_lines.get(section, []))

    for pdf_name, page, line in line_iter:
        s = line.strip()
        key = s.lower().rstrip(":")
        if key == "definition":
            title = find_title(buffer)
            if title:
                if current is not None:
                    entries.append(current)
                current = {"name": title, "pdf": pdf_name, "page": page, "_raw": {}, "_headings": set()}
                section = "definition"
                current["_headings"].add("definition")
                buffer = []
                continue
        buffer.append(line)
        buffer = buffer[-6:]
        if current is None:
            continue
        if key in SECTION_MAP and len(s) < 45:
            section = SECTION_MAP[key]
            current["_headings"].add(key)
            continue
        if key in STOP_HEADINGS or key in IGNORED_HEADINGS:
            section = None if key in STOP_HEADINGS or key in IGNORED_HEADINGS else section
            current["_headings"].add(key)
            continue
        if section:
            current["_raw"].setdefault(section, []).append(line)
    if current is not None:
        entries.append(current)
    return entries


def build_records(entries):
    records, used_slugs = [], set()
    for e in entries:
        raw = {k: strip_side_boxes(v) for k, v in e["_raw"].items()}
        has_symptoms = "causes_and_symptoms" in raw
        if not has_symptoms or "purpose" in e["_headings"]:
            continue  # drug, test or procedure rather than a disease
        rec = {col: join_text(raw.get(col, [])) for col in (
            "definition", "description", "causes_and_symptoms", "diagnosis",
            "treatment", "alternative_treatment", "prognosis", "prevention")}
        if len(rec["causes_and_symptoms"]) < 80:
            continue
        rec["symptoms"] = extract_symptom_list(raw.get("causes_and_symptoms", []), rec["causes_and_symptoms"])
        rec["name"] = e["name"]
        slug = slugify(e["name"])
        n = 2
        while slug in used_slugs:
            slug = f"{slugify(e['name'])}-{n}"
            n += 1
        used_slugs.add(slug)
        rec["slug"] = slug
        rec["source_pdf"] = e["pdf"]
        rec["source_page"] = e["page"]
        records.append(rec)
    return records


SCHEMA = """
DROP TABLE IF EXISTS diseases;
CREATE TABLE diseases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    letter TEXT NOT NULL,
    definition TEXT,
    description TEXT,
    causes_and_symptoms TEXT,
    symptoms_json TEXT,
    diagnosis TEXT,
    treatment TEXT,
    alternative_treatment TEXT,
    prognosis TEXT,
    prevention TEXT,
    source_pdf TEXT,
    source_page INTEGER
);
CREATE INDEX idx_diseases_name ON diseases(name);
CREATE INDEX idx_diseases_letter ON diseases(letter);
DROP TABLE IF EXISTS meta;
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


def write_database(records, out_path, sources):
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    con = sqlite3.connect(out_path)
    con.executescript(SCHEMA)
    con.executemany(
        """INSERT INTO diseases (slug, name, letter, definition, description, causes_and_symptoms,
               symptoms_json, diagnosis, treatment, alternative_treatment, prognosis, prevention,
               source_pdf, source_page)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [(r["slug"], r["name"], r["name"][0].upper(), r["definition"], r["description"],
          r["causes_and_symptoms"], json.dumps(r["symptoms"]), r["diagnosis"], r["treatment"],
          r["alternative_treatment"], r["prognosis"], r["prevention"], r["source_pdf"], r["source_page"])
         for r in records],
    )
    con.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", [
        ("built_at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        ("sources", json.dumps(sources)),
        ("count", str(len(records))),
    ])
    con.commit()
    con.close()


def main(argv=None):
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # hide noisy font warnings
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf-dir", default=os.path.join(root, "Data"))
    parser.add_argument("--out", default=os.path.join(root, "database", "diseases.db"))
    parser.add_argument("--json", default=os.path.join(root, "database", "diseases.json"),
                        help="Also export to JSON (use '' to skip)")
    args = parser.parse_args(argv)

    pdfs = sorted(os.path.join(args.pdf_dir, f) for f in os.listdir(args.pdf_dir) if f.lower().endswith(".pdf"))
    if not pdfs:
        sys.exit(f"No PDF files found in {args.pdf_dir}")
    print(f"Reading {len(pdfs)} PDF file(s)...")
    entries = parse_entries(read_lines(pdfs))
    records = build_records(entries)
    write_database(records, args.out, [os.path.basename(p) for p in pdfs])
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"Found {len(entries)} encyclopedia entries, saved {len(records)} diseases/conditions to {args.out}")


if __name__ == "__main__":
    main()
