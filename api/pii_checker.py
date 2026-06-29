"""
Detects PII and spam-indicative patterns in comments.

Returns (severity, reason, matched_text):
  ("not_ok",     "phone_number",  matched)  — mobile phone number
  ("suspicious", "national_id",   matched)  — valid Iranian national code
  ("suspicious", "email_address", matched)  — email address
  ("suspicious", "url",           matched)  — link / URL
  ("suspicious", "bank_card",     matched)  — 16-digit card (Luhn-valid)
  ("suspicious", "iban",          matched)  — Iranian IBAN (IR + 24 digits)
  (None,         None,            None)     — clean
"""

import re


def _to_ascii_digits(text: str) -> str:
    for i in range(10):
        text = text.replace(chr(0x06F0 + i), str(i))  # ۰–۹ Persian
        text = text.replace(chr(0x0660 + i), str(i))  # ٠–٩ Arabic-Indic
    return text


# ── Iranian mobile numbers ────────────────────────────────────────────────────
# Matches: 09XXXXXXXXX / +989XXXXXXXXX / 00989XXXXXXXXX
# with optional spaces, dashes, or dots between digit groups
_MOBILE_RE = re.compile(
    r'(?<!\d)'
    r'(?:(?:\+|00)\s?98|0)'   # country code (+98 / 0098) or leading 0
    r'\s?'
    r'9\d{2}'                  # operator prefix (9XX)
    r'[\s\-\./]?'
    r'\d{3}'                   # middle group
    r'[\s\-\./]?'
    r'\d{4}'                   # last group
    r'(?!\d)'
)

# ── Iranian national code (کد ملی) ────────────────────────────────────────────
_NATCODE_RE = re.compile(r'(?<!\d)(\d{10})(?!\d)')


def _valid_national_code(code: str) -> bool:
    if not code.isdigit() or len(set(code)) == 1:
        return False
    d = [int(c) for c in code]
    remainder = sum(d[i] * (10 - i) for i in range(9)) % 11
    return (remainder < 2 and d[9] == remainder) or \
           (remainder >= 2 and d[9] == 11 - remainder)


# ── Email address ─────────────────────────────────────────────────────────────
_EMAIL_RE = re.compile(
    r'(?<!\w)[a-zA-Z0-9._%+\-]{2,}@[a-zA-Z0-9.\-]{2,}\.[a-zA-Z]{2,}(?!\w)'
)

# ── URLs / links ──────────────────────────────────────────────────────────────
_URL_RE = re.compile(
    r'(?:https?://|ftp://|www\.)\S+',
    re.IGNORECASE,
)

# ── Bank card number (16 digits, optional separators, Luhn-validated) ─────────
_CARD_RE = re.compile(
    r'(?<!\d)(\d{4})[\s\-]?(\d{4})[\s\-]?(\d{4})[\s\-]?(\d{4})(?!\d)'
)


def _luhn_valid(num: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(num)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


# ── IBAN ──────────────────────────────────────────────────────────────────────
_IBAN_RE = re.compile(r'\bIR\d{24}\b', re.IGNORECASE)


def pii_check(texts: list):
    """
    Scan a list of text variants (original + normalised forms) for PII.
    Returns (severity, reason, matched_text) or (None, None, None).
    """
    seen = set()
    for raw in texts:
        t = _to_ascii_digits(raw)
        if t in seen:
            continue
        seen.add(t)

        # 1. Mobile phone — reject
        m = _MOBILE_RE.search(t)
        if m:
            return "not_ok", "phone_number", m.group(0).strip()

        # 2. National code — suspicious
        for m in _NATCODE_RE.finditer(t):
            if _valid_national_code(m.group(1)):
                return "suspicious", "national_id", m.group(1)

        # 3. Email — suspicious
        m = _EMAIL_RE.search(t)
        if m:
            return "suspicious", "email_address", m.group(0)

        # 4. URL — suspicious
        m = _URL_RE.search(t)
        if m:
            return "suspicious", "url", m.group(0)

        # 5. Bank card (Luhn-validated) — suspicious
        for m in _CARD_RE.finditer(t):
            digits = m.group(1) + m.group(2) + m.group(3) + m.group(4)
            if _luhn_valid(digits):
                return "suspicious", "bank_card", m.group(0).strip()

        # 6. IBAN — suspicious
        m = _IBAN_RE.search(t)
        if m:
            return "suspicious", "iban", m.group(0)

    return None, None, None
