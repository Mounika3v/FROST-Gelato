from __future__ import annotations
import hashlib


def account_key(email: str) -> str:
    return hashlib.sha256((email or "").strip().lower().encode()).hexdigest()[:16]


def validate_email(email: str) -> bool:
    return bool(email and "@" in email and "." in email.split("@")[-1])
