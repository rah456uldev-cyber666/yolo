"""Register (mobile + OTP), login with password, logout and password reset."""
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth.otp import OtpError, issue_otp, seconds_until_resend, verify_otp
from app.auth.phone import mask_phone, normalize_phone
from app.auth.sms import DELIVERED_SMS
from app.auth.security import password_problems, safe_next
from app.common.logger import get_logger
from app.config import config
from app.db import get_db, now

logger = get_logger(__name__)
bp = Blueprint("auth", __name__)


def _start_pending(phone, purpose):
    session["pending_phone"] = phone
    session["pending_purpose"] = purpose


def _pending():
    return session.get("pending_phone"), session.get("pending_purpose")


def _send_otp(db, phone, purpose, quiet=False):
    """Send an OTP and tell the user where it went. Returns True if a code was issued."""
    session.pop("screen_otp", None)
    try:
        code, mode = issue_otp(db, phone, purpose)
    except OtpError as e:
        flash(str(e), "error")
        return False
    if mode == DELIVERED_SMS:
        if not quiet:
            flash(f"We sent a {config.OTP_LENGTH}-digit code by SMS to {mask_phone(phone)}.", "success")
    elif config.SHOW_OTP_ON_SCREEN:
        session["screen_otp"] = {"phone": phone, "purpose": purpose, "code": code}
        flash("Offline mode: no SMS could be sent, so your code is shown below.", "info")
    else:
        flash("Offline mode: no SMS could be sent. The code is printed in the server terminal.", "info")
    return True


def _screen_otp(phone, purpose):
    data = session.get("screen_otp")
    if data and data.get("phone") == phone and data.get("purpose") == purpose:
        return data.get("code")
    return None


# ---------------------------------------------------------------- register --
@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("chat.index"))
    form = {"full_name": "", "phone": ""}
    if request.method == "POST":
        form["full_name"] = request.form.get("full_name", "").strip()
        form["phone"] = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        errors = []
        if not 2 <= len(form["full_name"]) <= 80:
            errors.append("Please enter your full name.")
        try:
            phone = normalize_phone(form["phone"], config.DEFAULT_COUNTRY_CODE)
        except ValueError as e:
            errors.append(str(e))
            phone = None
        problems = password_problems(password)
        if problems:
            errors.append("Password needs " + ", ".join(problems) + ".")
        if password != confirm:
            errors.append("Passwords do not match.")

        db = get_db()
        if phone and not errors:
            existing = db.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
            if existing and existing["is_verified"]:
                errors.append("This mobile number is already registered. Please log in.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("auth/register.html", form=form), 400

        pw_hash = generate_password_hash(password)
        if existing:  # unverified earlier attempt: update it
            db.execute("UPDATE users SET full_name=?, password_hash=? WHERE id=?",
                       (form["full_name"], pw_hash, existing["id"]))
        else:
            db.execute("INSERT INTO users (full_name, phone, password_hash, created_at) VALUES (?,?,?,?)",
                       (form["full_name"], phone, pw_hash, now()))
        db.commit()
        _start_pending(phone, "register")
        _send_otp(db, phone, "register")
        return redirect(url_for("auth.verify"))
    return render_template("auth/register.html", form=form)


@bp.route("/verify", methods=["GET", "POST"])
def verify():
    phone, purpose = _pending()
    if not phone or purpose != "register":
        flash("Start by registering your mobile number.", "info")
        return redirect(url_for("auth.register"))
    db = get_db()
    if request.method == "POST":
        try:
            verify_otp(db, phone, "register", request.form.get("otp"))
        except OtpError as e:
            flash(str(e), "error")
        else:
            db.execute("UPDATE users SET is_verified=1, verified_at=? WHERE phone=?", (now(), phone))
            db.commit()
            for key in ("pending_phone", "pending_purpose", "screen_otp"):
                session.pop(key, None)
            logger.info("User %s verified", phone)
            flash("Registration successful! You can now log in with your mobile number and password.", "success")
            return redirect(url_for("auth.login", phone=phone))
    return render_template("auth/verify.html", phone=mask_phone(phone), screen_otp=_screen_otp(phone, "register"),
                           wait=seconds_until_resend(db, phone, "register"), purpose="register")


@bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    phone, purpose = _pending()
    if not phone:
        return redirect(url_for("auth.register"))
    if purpose == "reset" and not get_db().execute(
            "SELECT 1 FROM users WHERE phone=? AND is_verified=1", (phone,)).fetchone():
        flash(f"If {mask_phone(phone)} is registered, a new code has been sent.", "info")
    else:
        _send_otp(get_db(), phone, purpose)
    return redirect(url_for("auth.verify" if purpose == "register" else "auth.reset_password"))


# ------------------------------------------------------------------- login --
@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("chat.index"))
    phone_input = request.form.get("phone", request.args.get("phone", "")).strip()
    if request.method == "POST":
        password = request.form.get("password", "")
        db = get_db()
        try:
            phone = normalize_phone(phone_input, config.DEFAULT_COUNTRY_CODE)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("auth/login.html", phone=phone_input), 400
        user = db.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()

        if user and user["locked_until"] > now():
            minutes = (user["locked_until"] - now()) // 60 + 1
            flash(f"Too many failed attempts. Try again in {minutes} minute(s) or reset your password.", "error")
            return render_template("auth/login.html", phone=phone_input), 429

        if not user or not check_password_hash(user["password_hash"], password):
            if user:
                failures = user["failed_logins"] + 1
                locked = now() + config.LOGIN_LOCK_MINUTES * 60 if failures >= config.LOGIN_MAX_FAILURES else 0
                db.execute("UPDATE users SET failed_logins=?, locked_until=? WHERE id=?",
                           (0 if locked else failures, locked, user["id"]))
                db.commit()
            flash("Incorrect mobile number or password.", "error")
            return render_template("auth/login.html", phone=phone_input), 401

        if not user["is_verified"]:
            _start_pending(phone, "register")
            flash("Please verify your mobile number first.", "info")
            _send_otp(db, phone, "register")
            return redirect(url_for("auth.verify"))

        db.execute("UPDATE users SET failed_logins=0, locked_until=0, last_login_at=? WHERE id=?", (now(), user["id"]))
        db.commit()
        csrf = session.get("_csrf")
        session.clear()  # prevent session fixation
        if csrf:
            session["_csrf"] = csrf
        session["user_id"] = user["id"]
        session.permanent = bool(request.form.get("remember"))
        logger.info("User %s logged in", phone)
        flash(f"Welcome back, {user['full_name'].split()[0]}!", "success")
        return redirect(safe_next(request.args.get("next")) or url_for("chat.index"))
    return render_template("auth/login.html", phone=phone_input)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------- password reset --
@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        try:
            phone = normalize_phone(request.form.get("phone", ""), config.DEFAULT_COUNTRY_CODE)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("auth/forgot_password.html"), 400
        db = get_db()
        user = db.execute("SELECT id FROM users WHERE phone=? AND is_verified=1", (phone,)).fetchone()
        _start_pending(phone, "reset")
        session.pop("screen_otp", None)
        if user:
            _send_otp(db, phone, "reset", quiet=True)
        # Same message either way, so nobody can test which numbers are registered.
        flash(f"If {mask_phone(phone)} is registered, a reset code has been sent.", "info")
        return redirect(url_for("auth.reset_password"))
    return render_template("auth/forgot_password.html")


@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    phone, purpose = _pending()
    if not phone or purpose != "reset":
        return redirect(url_for("auth.forgot_password"))
    db = get_db()
    if request.method == "POST":
        password = request.form.get("password", "")
        problems = password_problems(password)
        if problems:
            flash("Password needs " + ", ".join(problems) + ".", "error")
        elif password != request.form.get("confirm_password", ""):
            flash("Passwords do not match.", "error")
        else:
            try:
                verify_otp(db, phone, "reset", request.form.get("otp"))
            except OtpError as e:
                flash(str(e), "error")
            else:
                db.execute("UPDATE users SET password_hash=?, failed_logins=0, locked_until=0 WHERE phone=?",
                           (generate_password_hash(password), phone))
                db.commit()
                for key in ("pending_phone", "pending_purpose", "screen_otp"):
                    session.pop(key, None)
                flash("Password updated. Please log in with your new password.", "success")
                return redirect(url_for("auth.login", phone=phone))
    return render_template("auth/reset_password.html", phone=mask_phone(phone), screen_otp=_screen_otp(phone, "reset"),
                           wait=seconds_until_resend(db, phone, "reset"))
