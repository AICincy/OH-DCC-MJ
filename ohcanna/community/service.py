"""Thin facade tying accounts + queue together.

`CommunityService` is the entry point a CLI subcommand (wired by the parent
session) would call. It enforces validation, dedup, and role guarding so callers
never touch the state machine directly.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from ..storage import DEFAULT_DATA_ROOT
from .accounts import AccountStore, require_moderator
from .models import COASubmission, ModerationDecision, UserAccount
from .moderation import (
    DECISION_ACTIONS,
    ModerationQueue,
    SubmissionStatus,
    is_duplicate,
    transition,
    validate_submission,
)

# moderation.py re-exports DECISION_ACTIONS from models via this import path.


class SubmissionRejected(Exception):
    """Raised when a submission fails validation or is a duplicate."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


class CommunityService:
    def __init__(self, data_root: Path = DEFAULT_DATA_ROOT, salt: str = "ohcanna") -> None:
        self.data_root = Path(data_root)
        self.accounts = AccountStore(data_root=self.data_root, salt=salt)
        self.queue = ModerationQueue(data_root=self.data_root)

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def submit_coa(self, account: UserAccount, payload: dict) -> COASubmission:
        """Validate, dedup, and enqueue a COA submission.

        `payload` carries the business fields (brand, batch_id, lab_name,
        source_url, claimed_values, optional product_id/file_ref). Raises
        SubmissionRejected on validation failure or duplicate.
        """
        if account.status != "active":
            raise SubmissionRejected([f"account {account.account_id!r} is {account.status}"])

        sub = COASubmission(
            submission_id=payload.get("submission_id") or uuid.uuid4().hex,
            submitter_account_id=account.account_id,
            brand=payload.get("brand", ""),
            batch_id=payload.get("batch_id", ""),
            lab_name=payload.get("lab_name", ""),
            source_url=payload.get("source_url", ""),
            claimed_values=payload.get("claimed_values", {}) or {},
            product_id=payload.get("product_id"),
            file_ref=payload.get("file_ref"),
            submitted_at=payload.get("submitted_at") or self._now(),
            status=SubmissionStatus.PENDING,
        )

        problems = validate_submission(sub)
        if problems:
            raise SubmissionRejected(problems)

        for existing in self.queue.list_all():
            if is_duplicate(sub, existing):
                raise SubmissionRejected(
                    [
                        "duplicate of existing submission "
                        f"{existing.submission_id!r} on (brand, batch_id, lab_name)"
                    ]
                )

        return self.queue.enqueue(sub)

    def claim(self, moderator_account: UserAccount, submission_id: str) -> COASubmission:
        require_moderator(moderator_account)
        return self.queue.claim(submission_id, moderator_account)

    def moderate(
        self,
        moderator_account: UserAccount,
        submission_id: str,
        action: str,
        reason: str = "",
    ) -> COASubmission:
        """Guard role, transition, and record a ModerationDecision.

        `action` is one of approve | reject | needs_changes | escalate.
        """
        require_moderator(moderator_account)
        if action not in DECISION_ACTIONS:
            raise ValueError(
                f"invalid action {action!r}; must be one of {DECISION_ACTIONS}"
            )

        sub = self.queue.get(submission_id)
        if sub is None:
            raise KeyError(f"submission {submission_id!r} not found")

        decision = ModerationDecision(
            decision_id=uuid.uuid4().hex,
            submission_id=submission_id,
            moderator_account_id=moderator_account.account_id,
            action=action,
            reason=reason,
            decided_at=self._now(),
        )
        return self.queue.decide(submission_id, decision)

    def publish(self, moderator_account: UserAccount, submission_id: str) -> COASubmission:
        """Move an approved submission to published (operator-gated)."""
        require_moderator(moderator_account)
        return self.queue.apply_action(
            submission_id, "publish", moderator_account, reason="published"
        )

    def list_pending(self) -> list[COASubmission]:
        return self.queue.list_pending()

    def list_by_status(self, status: str) -> list[COASubmission]:
        return self.queue.list_by_status(status)
