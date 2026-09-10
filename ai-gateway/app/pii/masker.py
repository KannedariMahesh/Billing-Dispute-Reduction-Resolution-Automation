from .detectors import EMAIL_PATTERN, PHONE_PATTERN


def mask_pii(value: str) -> str:
    value = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)
    return PHONE_PATTERN.sub("[REDACTED_PHONE]", value)
