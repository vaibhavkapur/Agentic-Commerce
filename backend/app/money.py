"""GBP amounts are stored as integer pence. Parsing is strict about what it accepts."""

import re
from decimal import Decimal, InvalidOperation

CURRENCY = "GBP"
_AMOUNT_RE = re.compile(r"(?:GBP|£)?\s*(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)(?!\d)")


def parse_minor(text: str) -> int | None:
    """Parse '£2,400.00', 'GBP 2400', '2,400.5' into pence. Returns None for non-amounts."""
    if text is None:
        return None
    match = _AMOUNT_RE.search(text.strip())
    if not match:
        return None
    try:
        value = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return None
    return int((value * 100).to_integral_value())


def format_minor(amount_minor: int, currency: str = CURRENCY) -> str:
    sign = "-" if amount_minor < 0 else ""
    pounds, pence = divmod(abs(amount_minor), 100)
    return f"{currency} {sign}{pounds:,}.{pence:02d}"
