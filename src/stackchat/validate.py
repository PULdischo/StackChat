"""ISBN-10 / ISBN-13 and ISSN validation and normalization.

- Strips hyphens and whitespace from input.
- Validates check digits.
- Converts ISBN-10 to ISBN-13 (and vice-versa) when requested.
- Returns ``(normalized, error_message)``; ``error_message`` is None on success.
"""

from __future__ import annotations

import re

_ISBN10_RE = re.compile(r"^[0-9]{9}[0-9Xx]$")
_ISBN13_RE = re.compile(r"^[0-9]{13}$")
_ISSN_RE = re.compile(r"^[0-9]{7}[0-9Xx]$")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _strip(value: str) -> str:
    """Remove hyphens, spaces, and en/em-dashes."""
    return re.sub(r"[\s\-\u2013\u2014]", "", value).strip()


def _isbn10_check_digit(digits9: str) -> str:
    """Compute the ISBN-10 check digit for the first 9 digits."""
    total = sum((10 - i) * int(d) for i, d in enumerate(digits9))
    rem = total % 11
    check = 11 - rem
    if check == 10:
        return "X"
    if check == 11:
        return "0"
    return str(check)


def _isbn13_check_digit(digits12: str) -> str:
    """Compute the ISBN-13 check digit for the first 12 digits."""
    total = sum(
        int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits12)
    )
    rem = total % 10
    check = (10 - rem) % 10
    return str(check)


def _issn_check_digit(digits7: str) -> str:
    """Compute the ISSN check digit for the first 7 digits."""
    total = sum((8 - i) * int(d) for i, d in enumerate(digits7))
    rem = total % 11
    check = 11 - rem
    if check == 10:
        return "X"
    if check == 11:
        return "0"
    return str(check)


# ── Public API ────────────────────────────────────────────────────────────────


def normalize_isbn(value: str) -> tuple[str, str | None]:
    """Normalize and validate an ISBN-10 or ISBN-13.

    Returns:
        ``(normalized_isbn, None)`` on success, or
        ``("", error_message)`` on failure.

    The returned value is always 10 or 13 digits (plus possible trailing 'X'
    for ISBN-10), with no hyphens.
    """
    raw = _strip(value).upper()
    if not raw:
        return "", "ISBN must not be empty."

    if _ISBN13_RE.match(raw):
        expected = _isbn13_check_digit(raw[:12])
        if raw[12] != expected:
            return "", (
                f"Invalid ISBN-13 check digit: got '{raw[12]}', "
                f"expected '{expected}'."
            )
        return raw, None

    if _ISBN10_RE.match(raw):
        expected = _isbn10_check_digit(raw[:9])
        if raw[9] != expected:
            return "", (
                f"Invalid ISBN-10 check digit: got '{raw[9]}', "
                f"expected '{expected}'."
            )
        return raw, None

    # Try interpreting as 13 digits with a stray check-digit mismatch for a
    # better error message:
    stripped_digits = re.sub(r"[^0-9Xx]", "", raw)
    if len(stripped_digits) in (10, 13):
        return "", (
            f"Invalid ISBN check digit for '{value}'. "
            "Verify the number and try again."
        )
    return "", (
        f"'{value}' does not look like a valid ISBN-10 or ISBN-13. "
        "Expected 10 or 13 digits (hyphens optional)."
    )


def normalize_issn(value: str) -> tuple[str, str | None]:
    """Normalize and validate an ISSN.

    Returns:
        ``(normalized_issn, None)`` on success, or
        ``("", error_message)`` on failure.

    The returned value is in ``XXXX-XXXX`` form.
    """
    raw = _strip(value).upper()
    if not raw:
        return "", "ISSN must not be empty."

    if not _ISSN_RE.match(raw):
        return "", (
            f"'{value}' does not look like a valid ISSN. "
            "Expected 8 characters (7 digits + check digit or X), hyphens optional."
        )

    expected = _issn_check_digit(raw[:7])
    if raw[7] != expected:
        return "", (
            f"Invalid ISSN check digit: got '{raw[7]}', expected '{expected}'."
        )

    # Return formatted with hyphen
    return f"{raw[:4]}-{raw[4:]}", None
