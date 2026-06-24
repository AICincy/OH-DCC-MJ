"""JSON-backed account store with role guarding.

Persists to `<data_root>/community/accounts.json` (D8: JSON snapshots). Stores
only a salted email hash, never the raw address (P2 §9 privacy by design).
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Iterable

from ..storage import DEFAULT_DATA_ROOT, _atomic_write_json
from .models import ACCOUNT_STATUSES, ROLES, UserAccount, hash_email

# Roles permitted to take moderation actions.
_MODERATION_ROLES = ("moderator", "admin")


class NotAuthorized(Exception):
    """Raised when an account lacks the role required for an action."""


def require_moderator(account: UserAccount) -> None:
    """Guard: raise NotAuthorized unless `account` may moderate.

    Only active moderator/admin accounts pass. A submitter (or a suspended
    moderator) is blocked.
    """
    if account.status != "active":
        raise NotAuthorized(
            f"account {account.account_id!r} is {account.status}, cannot moderate"
        )
    if account.role not in _MODERATION_ROLES:
        raise NotAuthorized(
            f"account {account.account_id!r} has role {account.role!r}; "
            f"moderation requires one of {_MODERATION_ROLES}"
        )


class AccountStore:
    def __init__(self, data_root: Path = DEFAULT_DATA_ROOT, salt: str = "ohcanna") -> None:
        self.data_root = Path(data_root)
        self.path = self.data_root / "community" / "accounts.json"
        # Per-deployment salt for email hashing. Override per deployment.
        self.salt = salt

    # ---- persistence ---------------------------------------------------------
    def _load(self) -> list[UserAccount]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            return [UserAccount(**row) for row in json.load(f)]

    def _save(self, accounts: Iterable[UserAccount]) -> None:
        _atomic_write_json(self.path, [a.to_dict() for a in accounts])

    # ---- operations ----------------------------------------------------------
    def create_account(
        self,
        handle: str,
        email: str,
        role: str = "submitter",
        account_id: str | None = None,
        created_at: str | None = None,
    ) -> UserAccount:
        if role not in ROLES:
            raise ValueError(f"invalid role {role!r}; must be one of {ROLES}")
        accounts = self._load()
        if any(a.handle == handle for a in accounts):
            raise ValueError(f"handle {handle!r} already taken")

        account = UserAccount(
            account_id=account_id or uuid.uuid4().hex,
            handle=handle,
            email_hash=hash_email(email, self.salt),  # raw email is discarded here
            role=role,
            created_at=created_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            status="active",
        )
        accounts.append(account)
        self._save(accounts)
        return account

    def get(self, account_id: str) -> UserAccount | None:
        for a in self._load():
            if a.account_id == account_id:
                return a
        return None

    def _update(self, account_id: str, **changes) -> UserAccount:
        accounts = self._load()
        for i, a in enumerate(accounts):
            if a.account_id == account_id:
                for k, v in changes.items():
                    setattr(a, k, v)
                accounts[i] = a
                self._save(accounts)
                return a
        raise KeyError(f"account {account_id!r} not found")

    def set_role(self, account_id: str, role: str) -> UserAccount:
        if role not in ROLES:
            raise ValueError(f"invalid role {role!r}; must be one of {ROLES}")
        return self._update(account_id, role=role)

    def suspend(self, account_id: str) -> UserAccount:
        return self._update(account_id, status="suspended")

    def reinstate(self, account_id: str) -> UserAccount:
        return self._update(account_id, status="active")

    def list_accounts(self) -> list[UserAccount]:
        return self._load()
