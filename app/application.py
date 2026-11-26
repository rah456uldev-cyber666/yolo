"""Medibot web application.

Development:  python -m app.application
Production:   gunicorn -w 2 -b 0.0.0.0:5000 "app.application:app"      (Linux/macOS)
              waitress-serve --port=5000 app.application:app            (Windows)
"""
import os
import secrets
from datetime import timedelta

from flask import Flask, jsonify, render_template, request
from markupsafe import Markup, escape

from app.auth import routes as auth_routes
from app.auth.security import check_csrf, csrf_token, load_current_user
from app.auth.sms import sms_status
from app.chat import bp as chat_bp
from app.components.llm import llm_label
from app.common.logger import get_logger
from app.config import config
from app.db import init_db
from app.diseases import repository as disease_repo
from app.diseases.routes import bp as diseases_bp

logger = get_logger(__name__)


def nl2br(value):
    """Escape the text first (prevents XSS), then turn new lines into <br>."""
    return Markup("<br>\n".join(escape(value or "").split("\n")))


def create_app(test_config=None):
    app = Flask(__name__)
    secret = config.SECRET_KEY
    if not secret:
        secret = secrets.token_hex(32)
        logger.warning("SECRET_KEY is not set in .env - using a temporary key (users will be logged out on restart).")
    app.config.update(
        SECRET_KEY=secret,
        USER_DB_PATH=config.USER_DB_PATH,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.SESSION_COOKIE_SECURE,
        PERMANENT_SESSION_LIFETIME=timedelta(days=config.SESSION_LIFETIME_DAYS),
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    init_db(app)
    app.jinja_env.filters["nl2br"] = nl2br
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["llm_label"] = llm_label

    app.before_request(load_current_user)
    app.before_request(check_csrf)

    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(diseases_bp)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    @app.route("/health")
    def health():
        return jsonify({
            "status": "ok",
            "vector_store": os.path.exists(config.DB_FAISS_PATH),
            "disease_db": disease_repo.stats().get("count", 0),
            "offline_mode": config.OFFLINE_MODE,
            "llm": llm_label(),
            "sms": sms_status(),
        })

    @app.route("/about")
    def about():
        return render_template("about.html", stats=disease_repo.stats(), llm=llm_label(),
                               offline=config.OFFLINE_MODE, sms=sms_status())

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(429)
    @app.errorhandler(500)
    def handle_error(err):
        code = getattr(err, "code", 500) or 500
        if request.path.startswith("/api/"):
            return jsonify({"error": getattr(err, "description", "Server error")}), code
        return render_template("error.html", code=code,
                               message=getattr(err, "description", "Something went wrong.")), code

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)),
            debug=False, use_reloader=False)
