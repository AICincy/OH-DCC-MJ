"""Dataclasses for the community layer.

Style matches `ohcanna/models.py`: plain dataclasses, `Optional` for nullable
fields, `to_dict()` via `asdict`, and `extra: dict` for forward-compatible
overflow.

Privacy by design: `UserAccount` never carries a raw email. Callers hash the
email with a per-deployment salt via `hash_email` and store only the digest.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Optional


# Allowed enumerations, kept here so models and storage share one source.
ROLES = ("submitter", "moderator", "admin")
ACCOUNT_STATUSES = ("active", "suspended")
DECISION_ACTIONS = ("approve", "reject", "needs_changes", "escalate")


def hash_email(email: str, salt: str) -> str:
    """Return a salted SHA-256 hex digest of a (normalized) email.

    We store only this digest, never the raw address (P2 §9: no PII beyond
    business data). The salt is per-deployment so digests are not reversible
    via a precomputed rainbow table. Normalization (strip + lowercase) makes the
    hash stable across trivial input variation.
    """
    if not email or not email.strip():
        raise ValueError("email is required to compute a hash")
    if not salt:
        raise ValueError("a non-empty salt is required (privacy by design)")
    normalized = email.strip().lower()
    return hashlib.sha256(f"{salt}:{normalized}".encode("utf-8")).hexdigest()


@dataclass
class UserAccount:
    account_id: str
    handle: str
    email_hash: str  # salted hash ONLY, never the raw email
    role: str  # submitter | moderator | admin
    created_at: str
    status: str = "active"  # active | suspended
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class COASubmission:
    submission_id: str
    submitter_account_id: str
    brand: str
    batch_id: str
    lab_name: str
    source_url: str  # provenance (required) — one-source-publication, P2 §9
    claimed_values: dict = field(default_factory=dict)  # e.g. thc_percent
    product_id: Optional[str] = None  # optional link to a scraped product
    file_ref: Optional[str] = None  # path/hash placeholder, NOT an actual upload
    submitted_at: str = ""
    status: str = "pending"
    moderation_notes: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ModerationDecision:
    decision_id: str
    submission_id: str
    moderator_account_id: str
    action: str  # approve | reject | needs_changes | escalate
    reason: str
    decided_at: str
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
