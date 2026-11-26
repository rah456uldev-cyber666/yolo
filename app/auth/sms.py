"""Sending OTP codes by SMS.

SMS_PROVIDER in .env:
    auto     - (default) real SMS to the user's own phone with Fast2SMS (India), then Twilio,
               depending on which keys are set. If no keys are set, or the internet is down,
               the OTP is shown on screen and printed in the terminal (offline demo mode).
    fast2sms - Fast2SMS only (Indian +91 numbers)
    twilio   - Twilio only (any country)
    console  - never send SMS: always show the OTP on screen / terminal

To add another provider (MSG91, AWS SNS, ...), subclass SmsProvider and add it to PROVIDERS.
"""
import requests

from app.common.logger import get_logger
from app.config import config

logger = get_logger(__name__)

DELIVERED_SMS = "sms"
DELIVERED_SCREEN = "screen"


class SmsError(Exception):
    pass


def otp_message(code):
    minutes = max(1, config.OTP_TTL_SECONDS // 60)
    return f"Your Medibot verification code is {code}. It expires in {minutes} minutes. Do not share it with anyone."


class SmsProvider:
    name = "base"

    def is_configured(self) -> bool:
        return True

    def supports(self, phone: str) -> bool:
        return True

    def send_otp(self, phone: str, code: str) -> None:
        raise NotImplementedError


class ConsoleSmsProvider(SmsProvider):
    """No SMS: prints the code in the terminal (the page also shows it if SHOW_OTP_ON_SCREEN=true)."""
    name = "console"

    def send_otp(self, phone, code):
        message = f"[OFFLINE OTP] Code for {phone}: {code}"
        print("\n" + "=" * 50 + f"\n{message}\n" + "=" * 50 + "\n", flush=True)
        logger.warning(message + "  (no SMS sent)")


class Fast2SmsProvider(SmsProvider):
    """https://www.fast2sms.com - Indian numbers only."""
    name = "fast2sms"

    def is_configured(self):
        return bool(config.FAST2SMS_API_KEY)

    def supports(self, phone):
        return phone.startswith("+91")

    def send_otp(self, phone, code):
        if not self.is_configured():
            raise SmsError("FAST2SMS_API_KEY is not set")
        if config.FAST2SMS_ROUTE == "otp":
            # OTP route: Fast2SMS sends its own template "Your OTP is XXXX". Needs website verification.
            data = {"route": "otp", "variables_values": code, "numbers": phone[3:]}
        else:
            # Quick SMS route: our own message text. Works right after recharging the account.
            data = {"route": "q", "message": otp_message(code), "language": "english",
                    "flash": "0", "numbers": phone[3:]}
        try:
            resp = requests.post("https://www.fast2sms.com/dev/bulkV2",
                                 headers={"authorization": config.FAST2SMS_API_KEY}, data=data, timeout=15)
        except requests.RequestException as e:
            raise SmsError(f"Could not reach Fast2SMS (no internet?): {e}")
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code >= 300 or not body.get("return", False):
            raise SmsError(f"Fast2SMS error {resp.status_code}: {body.get('message') or resp.text[:200]}")


class TwilioSmsProvider(SmsProvider):
    """https://www.twilio.com - any country."""
    name = "twilio"

    def is_configured(self):
        return bool(config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN and config.TWILIO_FROM_NUMBER)

    def send_otp(self, phone, code):
        if not self.is_configured():
            raise SmsError("Twilio keys are not set")
        sid = config.TWILIO_ACCOUNT_SID
        try:
            resp = requests.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                data={"To": phone, "From": config.TWILIO_FROM_NUMBER, "Body": otp_message(code)},
                auth=(sid, config.TWILIO_AUTH_TOKEN),
                timeout=15,
            )
        except requests.RequestException as e:
            raise SmsError(f"Could not reach Twilio (no internet?): {e}")
        if resp.status_code >= 300:
            try:
                detail = resp.json().get("message", "")
            except ValueError:
                detail = resp.text[:200]
            raise SmsError(f"Twilio error {resp.status_code}: {detail}")


PROVIDERS = {p.name: p for p in (Fast2SmsProvider, TwilioSmsProvider, ConsoleSmsProvider)}
AUTO_ORDER = ("fast2sms", "twilio")


def real_providers_for(phone, provider_name=None):
    """Real SMS providers to try for this number, in order."""
    name = (provider_name or config.SMS_PROVIDER or "auto").lower()
    if name == "console":
        return []
    if name == "auto":
        names = AUTO_ORDER
    elif name in PROVIDERS:
        names = (name,)
    else:
        raise SmsError(f"Unknown SMS_PROVIDER '{name}'. Use auto, fast2sms, twilio or console.")
    providers = [PROVIDERS[n]() for n in names]
    return [p for p in providers if p.is_configured() and p.supports(phone)]


def deliver_otp(phone, code, provider_name=None):
    """Send the OTP. Returns DELIVERED_SMS, or DELIVERED_SCREEN when it fell back to on-screen/terminal.

    Raises SmsError if real SMS failed and fallback is disabled.
    """
    errors = []
    for provider in real_providers_for(phone, provider_name):
        try:
            provider.send_otp(phone, code)
            logger.info("OTP sent by SMS to %s via %s", phone, provider.name)
            return DELIVERED_SMS
        except SmsError as e:
            logger.error("SMS via %s failed: %s", provider.name, e)
            errors.append(f"{provider.name}: {e}")
    name = (provider_name or config.SMS_PROVIDER or "auto").lower()
    if errors and not config.SMS_FALLBACK:
        raise SmsError("; ".join(errors))
    if name not in ("auto", "console") and not errors and not config.SMS_FALLBACK:
        raise SmsError(f"SMS provider '{name}' is not configured or does not support {phone}")
    ConsoleSmsProvider().send_otp(phone, code)
    return DELIVERED_SCREEN


def sms_status():
    """Short description for the self-check and /health."""
    configured = [n for n in AUTO_ORDER if PROVIDERS[n]().is_configured()]
    if config.SMS_PROVIDER == "console" or not configured:
        return "offline mode: OTP shown on screen / terminal (no SMS keys set)"
    return f"real SMS via {', then '.join(configured)} (falls back to on-screen OTP if offline)"
