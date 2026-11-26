"""CSRF protection, login_required decorator and password rules."""
import re
import secrets
from functools import wraps

from flask import abort, flash, g, jsonify, redirect, request, session, url_for

from app.db import get_db


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_csrf():
    """Run before every request: reject POSTs without the right token."""
    if request.method != "POST":
        return
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = session.get("_csrf")
    if not expected or not sent or not secrets.compare_digest(sent, expected):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Invalid or missing CSRF token. Reload the page."}), 400
        abort(400, description="Your session expired. Please reload the page and try again.")


def load_current_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id:
        g.user = get_db().execute("SELECT * FROM users WHERE id=? AND is_verified=1", (user_id,)).fetchone()
        if g.user is None:
            session.pop("user_id", None)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Login required"}), 401
            flash("Please log in to continue.", "info")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def password_problems(password: str):
    """Return a list of problems with the password (empty list = OK)."""
    problems = []
    if len(password) < 8:
        problems.append("at least 8 characters")
    if not re.search(r"[A-Za-z]", password):
        problems.append("a letter")
    if not re.search(r"\d", password):
        problems.append("a number")
    return problems


def safe_next(target):
    """Only allow redirects to paths on this site."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None
