from flask import Blueprint, abort, jsonify, render_template, request

from app.auth.security import login_required
from app.diseases import repository as repo

bp = Blueprint("diseases", __name__)

PUBLIC_FIELDS = ("slug", "name", "definition", "description", "causes_and_symptoms", "symptoms", "diagnosis",
                 "treatment", "alternative_treatment", "prognosis", "prevention", "source_pdf", "source_page")


@bp.route("/diseases")
@login_required
def library():
    q = request.args.get("q", "").strip()
    letter = request.args.get("letter", "").strip()[:1]
    diseases = repo.search(q, letter or None)
    return render_template("diseases/list.html", diseases=diseases, q=q, letter=letter,
                           letters=repo.letters(), stats=repo.stats(), available=repo.is_available())


@bp.route("/diseases/<slug>")
@login_required
def detail(slug):
    disease = repo.get_by_slug(slug)
    if not disease:
        abort(404)
    return render_template("diseases/detail.html", d=disease)


@bp.route("/symptom-checker", methods=["GET", "POST"])
@login_required
def symptom_checker():
    text = request.form.get("symptoms", "") if request.method == "POST" else request.args.get("symptoms", "")
    terms, results = repo.symptom_check(text) if text else ([], [])
    return render_template("diseases/symptom_checker.html", text=text, terms=terms, results=results)


# ------------------------------------------------------------------- JSON API --
@bp.route("/api/diseases")
@login_required
def api_list():
    q = request.args.get("q", "")
    items = repo.search(q, request.args.get("letter") or None, limit=100)
    return jsonify([{"slug": d["slug"], "name": d["name"], "definition": d["definition"],
                     "symptoms": d["symptoms"]} for d in items])


@bp.route("/api/diseases/<slug>")
@login_required
def api_detail(slug):
    d = repo.get_by_slug(slug)
    if not d:
        return jsonify({"error": "Not found"}), 404
    return jsonify({k: d[k] for k in PUBLIC_FIELDS})
