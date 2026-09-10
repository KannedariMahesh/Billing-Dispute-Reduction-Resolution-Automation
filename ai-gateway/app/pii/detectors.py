import re

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"\b(?:\+?\d[\d ()-]{7,}\d)\b")


def contains_pii(value: str) -> bool:
    return bool(EMAIL_PATTERN.search(value) or PHONE_PATTERN.search(value))
