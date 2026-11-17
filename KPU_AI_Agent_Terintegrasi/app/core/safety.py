"""Conservative data-minimization and source URL allowlisting.

Regexes are a baseline only; do NOT treat them as a complete DLP solution.
"""
import re
from urllib.parse import urlsplit

_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_NIK = re.compile(r"(?<!\d)\d{16}(?!\d)")
_PHONE = re.compile(r"(?<!\d)(?:\+62|62|0)8[0-9\s-]{8,14}(?!\d)")


def contains_sensitive_identifiers(text: str) -> bool:
    return any(pattern.search(text) for pattern in (_EMAIL, _NIK, _PHONE))


def is_approved_source(url: str, allowed_hosts: list[str]) -> bool:
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.hostname.lower() in allowed_hosts
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
        )
    except ValueError:
        return False
