"""Checks that the phone/PC app's offline data matches the disease database."""
import json
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WWW = os.path.join(ROOT, "mobile", "www")


def _load_js(name, var):
    text = open(os.path.join(WWW, "data", name), encoding="utf-8").read().strip()
    prefix = f"window.{var}="
    assert text.startswith(prefix) and text.endswith(";")
    return json.loads(text[len(prefix):-1])


def test_disease_data_matches_database():
    diseases = _load_js("diseases.js", "MB_DISEASES")
    count = sqlite3.connect(os.path.join(ROOT, "database", "diseases.db")).execute("SELECT COUNT(*) FROM diseases").fetchone()[0]
    assert len(diseases) == count > 100
    assert {"slug", "name", "symptoms", "treatment"} <= set(diseases[0])


def test_passages_have_pages():
    passages = _load_js("passages.js", "MB_PASSAGES")
    assert len(passages) > 1000
    assert all(isinstance(p["p"], int) and p["t"] for p in passages[:50])


def test_app_files_present():
    for f in ["index.html", "app.css", "manifest.webmanifest", "sw.js", "js/core.js", "js/search.js",
              "js/answer.js", "js/app.js", "js/extras.js", "fonts/inter.woff2", "icons/icon-512.png"]:
        assert os.path.isfile(os.path.join(WWW, f)), f
    sw = open(os.path.join(WWW, "sw.js")).read()
    assert "data/passages.js" in sw and "data/diseases.js" in sw
