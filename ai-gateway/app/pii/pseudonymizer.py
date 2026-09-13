import hashlib


def pseudonymize(value: str, namespace: str = "billing-dispute") -> str:
    digest = hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()
    return f"anon-{digest[:16]}"
