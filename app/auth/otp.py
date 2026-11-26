"""One-time passwords: generation, rate limiting and verification.

Codes are never stored in plain text, only as an HMAC hash. Each code expires
after OTP_TTL_SECONDS and allows OTP_MAX_ATTEMPTS guesses.
"""
import hashlib
import hmac
import secrets

from flask import current_app

from app.auth.sms import SmsError, deliver_otp
from app.common.logger import get_logger
from app.config import config
from app.db import now

logger = get_logger(__name__)


class OtpError(Exception):
    pass


def _hash(phone, purpose, code):
    key = current_app.config["SECRET_KEY"].encode()
    return hmac.new(key, f"{phone}|{purpose}|{code}".encode(), hashlib.sha256).hexdigest()


def generate_code(length=None):
    length = length or config.OTP_LENGTH
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def seconds_until_resend(db, phone, purpose):
    row = db.execute(
        "SELECT created_at FROM otp_codes WHERE phone=? AND purpose=? ORDER BY id DESC LIMIT 1",
        (phone, purpose),
    ).fetchone()
    if not row:
        return 0
    return max(0, row["created_at"] + config.OTP_RESEND_COOLDOWN_SECONDS - now())


def issue_otp(db, phone, purpose):
    """Create a new OTP, invalidate older ones and send it by SMS.

    Returns (code, mode) where mode is "sms" or "screen" (offline fallback).
    """
    wait = seconds_until_resend(db, phone, purpose)
    if wait:
        raise OtpError(f"Please wait {wait} seconds before requesting another code.")
    sent_last_hour = db.execute(
        "SELECT COUNT(*) FROM otp_codes WHERE phone=? AND created_at>?", (phone, now() - 3600)
    ).fetchone()[0]
    if sent_last_hour >= config.OTP_MAX_SENDS_PER_HOUR:
        raise OtpError("Too many codes requested for this number. Please try again in an hour.")

    code = generate_code()
    db.execute("UPDATE otp_codes SET consumed=1 WHERE phone=? AND purpose=? AND consumed=0", (phone, purpose))
    db.execute(
        "INSERT INTO otp_codes (phone, purpose, code_hash, created_at, expires_at) VALUES (?,?,?,?,?)",
        (phone, purpose, _hash(phone, purpose, code), now(), now() + config.OTP_TTL_SECONDS),
    )
    db.commit()
    try:
        mode = deliver_otp(phone, code)
    except SmsError as e:
        logger.error("Failed to send OTP to %s: %s", phone, e)
        raise OtpError("We could not send the SMS right now. Please try again shortly.")
    logger.info("OTP (%s) for %s delivered via %s", purpose, phone, mode)
    return code, mode


def verify_otp(db, phone, purpose, code):
    """Return True if the code is right. Raises OtpError with a user-friendly message otherwise."""
    code = (code or "").strip()
    row = db.execute(
        "SELECT * FROM otp_codes WHERE phone=? AND purpose=? AND consumed=0 ORDER BY id DESC LIMIT 1",
        (phone, purpose),
    ).fetchone()
    if not row:
        raise OtpError("No active code. Please request a new one.")
    if row["expires_at"] < now():
        db.execute("UPDATE otp_codes SET consumed=1 WHERE id=?", (row["id"],))
        db.commit()
        raise OtpError("This code has expired. Please request a new one.")
    if row["attempts"] >= config.OTP_MAX_ATTEMPTS:
        raise OtpError("Too many wrong attempts. Please request a new code.")
    if not hmac.compare_digest(row["code_hash"], _hash(phone, purpose, code)):
        db.execute("UPDATE otp_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
        db.commit()
        left = config.OTP_MAX_ATTEMPTS - row["attempts"] - 1
        raise OtpError(f"Incorrect code. {left} attempt(s) left." if left > 0
                       else "Too many wrong attempts. Please request a new code.")
    db.execute("UPDATE otp_codes SET consumed=1 WHERE id=?", (row["id"],))
    db.commit()
    return True
