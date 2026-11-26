import re

E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(raw: str, default_country_code: str = "+91") -> str:
    """Turn user input like '98765 43210' or '+1 (555) 123-4567' into E.164 ('+919876543210').

    Raises ValueError if the number is not valid.
    """
    if not raw:
        raise ValueError("Please enter your mobile number.")
    number = re.sub(r"[\s\-().]", "", raw.strip())
    if number.startswith("00"):
        number = "+" + number[2:]
    if not number.startswith("+"):
        number = number.lstrip("0")
        number = default_country_code + number
    if not E164.match(number):
        raise ValueError("Please enter a valid mobile number, e.g. 9876543210 or +919876543210.")
    return number


def mask_phone(phone: str) -> str:
    """'+919876543210' -> '+91******3210' for display."""
    if len(phone) <= 6:
        return phone
    return phone[:3] + "*" * (len(phone) - 7) + phone[-4:]
