"""Moderation state machine, queue, validation, and dedup.

State machine (P2 §7 DR mandates an explicit moderation plan):

    pending ---claim---> in_review
    in_review ---approve---> approved
    in_review ---reject----> rejected
    in_review ---needs_changes--> needs_changes
    needs_changes ---claim---> in_review        (resubmission re-enters review)
    approved ---publish---> published
    <any non-terminal> ---escalate---> escalated   (routes to operator, DR/DP)

Terminal states: rejected, published. `escalated` is a holding state an operator
resolves out of band; from here it can re-enter review (e.g. operator un-holds)
but cannot be silently published.

Illegal transitions raise `IllegalTransition`.

The queue is backed by a single JSON file, written atomically via the storage
helpers (D8: JSON snapshots, no DB).
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable

from ..storage import DEFAULT_DATA_ROOT, _atomic_write_json
from .models import (
    DECISION_ACTIONS,
    COASubmission,
    ModerationDecision,
    UserAccount,
)

__all__ = [
    "DECISION_ACTIONS",
    "IllegalTransition",
    "ModerationQueue",
    "SubmissionStatus",
    "transition",
    "validate_submission",
    "is_duplicate",
]


class IllegalTransition(Exception):
    """Raised when an action is not legal from a submission's current state."""


class SubmissionStatus:
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"
    PUBLISHED = "published"
    ESCALATED = "escalated"


# action -> (allowed_from_states, resulting_state)
# `escalate` is handled specially (allowed from any non-terminal state).
_TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "claim": (
        (SubmissionStatus.PENDING, SubmissionStatus.NEEDS_CHANGES),
        SubmissionStatus.IN_REVIEW,
    ),
    "approve": ((SubmissionStatus.IN_REVIEW,), SubmissionStatus.APPROVED),
    "reject": ((SubmissionStatus.IN_REVIEW,), SubmissionStatus.REJECTED),
    "needs_changes": (
        (SubmissionStatus.IN_REVIEW,),
        SubmissionStatus.NEEDS_CHANGES,
    ),
    "publish": ((SubmissionStatus.APPROVED,), SubmissionStatus.PUBLISHED),
}

# States from which nothing further may happen (escalate included).
_TERMINAL = (SubmissionStatus.REJECTED, SubmissionStatus.PUBLISHED)

# Implausible-value bounds (a cannabis concentrate can approach but not exceed
# ~100% THC; anything outside [0, 100] is a data error, not a real claim).
_THC_MIN = 0.0
_THC_MAX = 100.0


def transition(
    submission: COASubmission, action: str, moderator: UserAccount | None = None
) -> COASubmission:
    """Return a NEW submission advanced by `action`, or raise IllegalTransition.

    `moderator` is accepted for symmetry with the service layer / future audit
    needs; the state machine itself does not require it (role guarding lives in
    accounts.require_moderator and the service facade).
    """
    current = submission.status

    if action == "escalate":
        if current in _TERMINAL or current == SubmissionStatus.ESCALATED:
            raise IllegalTransition(
                f"cannot escalate a submission in terminal/escalated state {current!r}"
            )
        return replace(submission, status=SubmissionStatus.ESCALATED)

    if action == "claim" and current == SubmissionStatus.ESCALATED:
        # Operator un-holds an escalated item back into review.
        return replace(submission, status=SubmissionStatus.IN_REVIEW)

    if action not in _TRANSITIONS:
        raise IllegalTransition(f"unknown action {action!r}")

    allowed_from, result = _TRANSITIONS[action]
    if current not in allowed_from:
        raise IllegalTransition(
            f"cannot {action} a submission in state {current!r} "
            f"(allowed from: {', '.join(allowed_from)})"
        )
    return replace(submission, status=result)


def validate_submission(sub: COASubmission) -> list[str]:
    """Return a list of human-readable problems; empty list means valid.

    A reject auto-fails validation before reaching a human (the service runs
    this on submit). Provenance (`source_url`) is mandatory per one-source-
    publication discipline (P2 §9).
    """
    problems: list[str] = []

    if not (sub.source_url or "").strip():
        problems.append("missing provenance: source_url is required")
    if not (sub.batch_id or "").strip():
        problems.append("missing batch_id")
    if not (sub.brand or "").strip():
        problems.append("missing brand")
    if not (sub.lab_name or "").strip():
        problems.append("missing lab_name")
    if not (sub.submitter_account_id or "").strip():
        problems.append("missing submitter_account_id")

    thc = sub.claimed_values.get("thc_percent") if sub.claimed_values else None
    if thc is not None:
        try:
            thc_val = float(thc)
        except (TypeError, ValueError):
            problems.append(f"claimed thc_percent is not numeric: {thc!r}")
        else:
            if not (_THC_MIN <= thc_val <= _THC_MAX):
                problems.append(
                    f"implausible claimed thc_percent {thc_val} "
                    f"(must be {_THC_MIN}-{_THC_MAX})"
                )

    return problems


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def is_duplicate(sub: COASubmission, existing: COASubmission) -> bool:
    """Two submissions collide on (brand, batch_id, lab_name), case-insensitive."""
    if sub.submission_id and sub.submission_id == existing.submission_id:
        return False  # the same record is not its own duplicate
    return (
        _norm(sub.brand) == _norm(existing.brand)
        and _norm(sub.batch_id) == _norm(existing.batch_id)
        and _norm(sub.lab_name) == _norm(existing.lab_name)
    )


class ModerationQueue:
    """JSON-file-backed queue of COA submissions.

    Persists to `<data_root>/community/submissions.json`. Decisions are appended
    to `<data_root>/community/decisions.json`. All writes are atomic.
    """

    def __init__(self, data_root: Path = DEFAULT_DATA_ROOT) -> None:
        self.data_root = Path(data_root)
        self.dir = self.data_root / "community"
        self.submissions_path = self.dir / "submissions.json"
        self.decisions_path = self.dir / "decisions.json"

    # ---- persistence helpers -------------------------------------------------
    def _load_submissions(self) -> list[COASubmission]:
        if not self.submissions_path.exists():
            return []
        import json

        with open(self.submissions_path, encoding="utf-8") as f:
            return [COASubmission(**row) for row in json.load(f)]

    def _save_submissions(self, subs: Iterable[COASubmission]) -> None:
        _atomic_write_json(self.submissions_path, [s.to_dict() for s in subs])

    def _load_decisions(self) -> list[ModerationDecision]:
        if not self.decisions_path.exists():
            return []
        import json

        with open(self.decisions_path, encoding="utf-8") as f:
            return [ModerationDecision(**row) for row in json.load(f)]

    def _save_decisions(self, decisions: Iterable[ModerationDecision]) -> None:
        _atomic_write_json(self.decisions_path, [d.to_dict() for d in decisions])

    # ---- queue operations ----------------------------------------------------
    def get(self, submission_id: str) -> COASubmission | None:
        for s in self._load_submissions():
            if s.submission_id == submission_id:
                return s
        return None

    def enqueue(self, submission: COASubmission) -> COASubmission:
        subs = self._load_submissions()
        if any(s.submission_id == submission.submission_id for s in subs):
            raise ValueError(f"submission {submission.submission_id!r} already queued")
        subs.append(submission)
        self._save_submissions(subs)
        return submission

    def _replace(self, updated: COASubmission) -> COASubmission:
        subs = self._load_submissions()
        for i, s in enumerate(subs):
            if s.submission_id == updated.submission_id:
                subs[i] = updated
                self._save_submissions(subs)
                return updated
        raise KeyError(f"submission {updated.submission_id!r} not found")

    def claim(self, submission_id: str, moderator: UserAccount) -> COASubmission:
        sub = self.get(submission_id)
        if sub is None:
            raise KeyError(f"submission {submission_id!r} not found")
        updated = transition(sub, "claim", moderator)
        notes = (sub.moderation_notes or "").strip()
        claim_note = f"claimed by {moderator.account_id}"
        updated = replace(
            updated,
            moderation_notes=f"{notes}\n{claim_note}".strip() if notes else claim_note,
        )
        return self._replace(updated)

    def apply_action(
        self, submission_id: str, action: str, moderator: UserAccount, reason: str = ""
    ) -> COASubmission:
        """Advance a submission by `action` (approve/reject/needs_changes/escalate/publish)."""
        sub = self.get(submission_id)
        if sub is None:
            raise KeyError(f"submission {submission_id!r} not found")
        updated = transition(sub, action, moderator)
        if reason:
            notes = (sub.moderation_notes or "").strip()
            stamp = f"{action}: {reason}"
            updated = replace(
                updated,
                moderation_notes=f"{notes}\n{stamp}".strip() if notes else stamp,
            )
        return self._replace(updated)

    def decide(
        self, submission_id: str, decision: ModerationDecision
    ) -> COASubmission:
        """Record a ModerationDecision and apply its action to the submission."""
        if decision.submission_id != submission_id:
            raise ValueError("decision.submission_id does not match submission_id")
        updated = self.apply_action(
            submission_id,
            decision.action,
            UserAccount(
                account_id=decision.moderator_account_id,
                handle="",
                email_hash="",
                role="moderator",
                created_at="",
            ),
            reason=decision.reason,
        )
        decisions = self._load_decisions()
        decisions.append(decision)
        self._save_decisions(decisions)
        return updated

    def list_all(self) -> list[COASubmission]:
        return self._load_submissions()

    def list_by_status(self, status: str) -> list[COASubmission]:
        return [s for s in self._load_submissions() if s.status == status]

    def list_pending(self) -> list[COASubmission]:
        return self.list_by_status(SubmissionStatus.PENDING)
