"""Community layer: user accounts, COA submission, and moderation queue.

This is a JSON-file-backed domain layer (consistent with decision D8 "JSON
snapshots", no external database). It is pure Python and fully offline: no web
server, no auth provider, no file-upload hosting (those are deployment concerns
deferred like the rest of the publication layer).

Built per P2 §7 decision DR, which contemplated revisiting COA submission in
Phase 3 *with an explicit moderation plan*. The moderation workflow here is
therefore mandatory, not optional.

Privacy by design (P2 §9): we never store raw email (only a salted hash) and we
collect only business-relevant fields. COAs are sensitive; provenance
(`source_url`) is required so we never republish a third-party COA without a
traceable source (one-source-publication).
"""
from __future__ import annotations

from .models import COASubmission, ModerationDecision, UserAccount, hash_email
from .accounts import AccountStore, NotAuthorized, require_moderator
from .moderation import (
    IllegalTransition,
    ModerationQueue,
    SubmissionStatus,
    transition,
    validate_submission,
    is_duplicate,
)
from .service import CommunityService

__all__ = [
    "COASubmission",
    "ModerationDecision",
    "UserAccount",
    "hash_email",
    "AccountStore",
    "NotAuthorized",
    "require_moderator",
    "IllegalTransition",
    "ModerationQueue",
    "SubmissionStatus",
    "transition",
    "validate_submission",
    "is_duplicate",
    "CommunityService",
]
