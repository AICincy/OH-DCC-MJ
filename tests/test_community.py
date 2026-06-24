"""Tests for the community layer (accounts, COA submission, moderation).

All tests use a tmp_path data root so nothing touches the real `data/` tree and
the suite stays fully offline.
"""
from __future__ import annotations

import json

import pytest

from ohcanna.community.accounts import AccountStore, NotAuthorized, require_moderator
from ohcanna.community.models import (
    COASubmission,
    UserAccount,
    hash_email,
)
from ohcanna.community.moderation import (
    IllegalTransition,
    ModerationQueue,
    SubmissionStatus,
    is_duplicate,
    transition,
    validate_submission,
)
from ohcanna.community.service import CommunityService, SubmissionRejected


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #
def _payload(**over) -> dict:
    base = {
        "brand": "Klutch",
        "batch_id": "B-1001",
        "lab_name": "North Coast Testing",
        "source_url": "https://example.com/coa/B-1001.pdf",
        "claimed_values": {"thc_percent": 78.5},
    }
    base.update(over)
    return base


def _make_sub(**over) -> COASubmission:
    base = dict(
        submission_id="s1",
        submitter_account_id="acct-1",
        brand="Klutch",
        batch_id="B-1001",
        lab_name="North Coast Testing",
        source_url="https://example.com/coa/B-1001.pdf",
        claimed_values={"thc_percent": 78.5},
    )
    base.update(over)
    return COASubmission(**base)


# --------------------------------------------------------------------------- #
# accounts + PII handling
# --------------------------------------------------------------------------- #
def test_email_is_hashed_not_stored_raw(tmp_path):
    store = AccountStore(data_root=tmp_path, salt="pepper")
    acct = store.create_account(handle="alice", email="Alice@Example.com")

    # The returned account carries a hash, not the address.
    assert "@" not in acct.email_hash
    assert acct.email_hash == hash_email("alice@example.com", "pepper")

    # And the raw email never lands on disk.
    raw = (tmp_path / "community" / "accounts.json").read_text()
    assert "Alice@Example.com" not in raw
    assert "alice@example.com" not in raw
    assert acct.email_hash in raw


def test_hash_email_is_salted_and_normalized():
    # Normalization: case/whitespace do not change the digest.
    assert hash_email("  USER@x.com ", "s") == hash_email("user@x.com", "s")
    # Salt matters: different salt -> different digest.
    assert hash_email("user@x.com", "a") != hash_email("user@x.com", "b")
    with pytest.raises(ValueError):
        hash_email("user@x.com", "")


def test_role_assignment_and_suspend(tmp_path):
    store = AccountStore(data_root=tmp_path)
    acct = store.create_account(handle="mod", email="m@x.com")
    assert acct.role == "submitter"

    promoted = store.set_role(acct.account_id, "moderator")
    assert promoted.role == "moderator"
    assert store.get(acct.account_id).role == "moderator"

    suspended = store.suspend(acct.account_id)
    assert suspended.status == "suspended"


def test_require_moderator_blocks_submitter(tmp_path):
    store = AccountStore(data_root=tmp_path)
    submitter = store.create_account(handle="sub", email="s@x.com")
    with pytest.raises(NotAuthorized):
        require_moderator(submitter)

    mod = store.create_account(handle="mod", email="m@x.com", role="moderator")
    require_moderator(mod)  # does not raise

    # A suspended moderator is also blocked.
    store.suspend(mod.account_id)
    with pytest.raises(NotAuthorized):
        require_moderator(store.get(mod.account_id))


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def test_valid_submission_passes_validation():
    assert validate_submission(_make_sub()) == []


def test_missing_source_url_fails_validation():
    problems = validate_submission(_make_sub(source_url=""))
    assert any("source_url" in p for p in problems)


def test_missing_batch_id_fails_validation():
    problems = validate_submission(_make_sub(batch_id=""))
    assert any("batch_id" in p for p in problems)


def test_implausible_thc_fails_validation():
    problems = validate_submission(_make_sub(claimed_values={"thc_percent": 250}))
    assert any("thc" in p.lower() for p in problems)


# --------------------------------------------------------------------------- #
# dedup
# --------------------------------------------------------------------------- #
def test_dedup_catches_same_brand_batch_lab():
    a = _make_sub(submission_id="s1")
    b = _make_sub(submission_id="s2", source_url="https://other.example/coa")
    assert is_duplicate(b, a) is True
    # case-insensitive on the key fields
    c = _make_sub(submission_id="s3", brand="klutch", lab_name="north coast testing")
    assert is_duplicate(c, a) is True
    # different batch -> not a duplicate
    d = _make_sub(submission_id="s4", batch_id="B-9999")
    assert is_duplicate(d, a) is False
    # a record is not its own duplicate
    assert is_duplicate(a, a) is False


# --------------------------------------------------------------------------- #
# state machine
# --------------------------------------------------------------------------- #
def test_state_machine_happy_path():
    sub = _make_sub(status=SubmissionStatus.PENDING)
    sub = transition(sub, "claim")
    assert sub.status == SubmissionStatus.IN_REVIEW
    sub = transition(sub, "approve")
    assert sub.status == SubmissionStatus.APPROVED
    sub = transition(sub, "publish")
    assert sub.status == SubmissionStatus.PUBLISHED


def test_illegal_transition_raises():
    rejected = _make_sub(status=SubmissionStatus.REJECTED)
    with pytest.raises(IllegalTransition):
        transition(rejected, "approve")

    pending = _make_sub(status=SubmissionStatus.PENDING)
    # cannot approve before claiming into review
    with pytest.raises(IllegalTransition):
        transition(pending, "approve")


def test_escalate_path():
    sub = _make_sub(status=SubmissionStatus.IN_REVIEW)
    sub = transition(sub, "escalate")
    assert sub.status == SubmissionStatus.ESCALATED
    # operator can un-hold an escalated item back into review
    sub = transition(sub, "claim")
    assert sub.status == SubmissionStatus.IN_REVIEW
    # cannot escalate a terminal/published item
    published = _make_sub(status=SubmissionStatus.PUBLISHED)
    with pytest.raises(IllegalTransition):
        transition(published, "escalate")


# --------------------------------------------------------------------------- #
# queue persistence
# --------------------------------------------------------------------------- #
def test_queue_enqueue_and_list(tmp_path):
    q = ModerationQueue(data_root=tmp_path)
    q.enqueue(_make_sub(submission_id="s1"))
    assert len(q.list_pending()) == 1
    # written to the expected JSON path
    p = tmp_path / "community" / "submissions.json"
    assert p.exists()
    assert json.loads(p.read_text())[0]["submission_id"] == "s1"
    # double-enqueue of the same id is rejected
    with pytest.raises(ValueError):
        q.enqueue(_make_sub(submission_id="s1"))


# --------------------------------------------------------------------------- #
# service facade — full happy path
# --------------------------------------------------------------------------- #
def test_service_full_happy_path(tmp_path):
    svc = CommunityService(data_root=tmp_path, salt="pepper")
    submitter = svc.accounts.create_account(handle="alice", email="a@x.com")
    mod = svc.accounts.create_account(handle="mod", email="m@x.com", role="moderator")

    sub = svc.submit_coa(submitter, _payload())
    assert sub.status == SubmissionStatus.PENDING

    pending = svc.list_pending()
    assert [s.submission_id for s in pending] == [sub.submission_id]

    claimed = svc.claim(mod, sub.submission_id)
    assert claimed.status == SubmissionStatus.IN_REVIEW

    approved = svc.moderate(mod, sub.submission_id, "approve", reason="COA checks out")
    assert approved.status == SubmissionStatus.APPROVED

    published = svc.publish(mod, sub.submission_id)
    assert published.status == SubmissionStatus.PUBLISHED

    # a ModerationDecision was recorded
    decisions = json.loads((tmp_path / "community" / "decisions.json").read_text())
    assert any(d["action"] == "approve" for d in decisions)


def test_service_blocks_submitter_from_moderating(tmp_path):
    svc = CommunityService(data_root=tmp_path)
    submitter = svc.accounts.create_account(handle="alice", email="a@x.com")
    sub = svc.submit_coa(submitter, _payload())
    with pytest.raises(NotAuthorized):
        svc.moderate(submitter, sub.submission_id, "approve")


def test_service_rejects_invalid_and_duplicate(tmp_path):
    svc = CommunityService(data_root=tmp_path)
    submitter = svc.accounts.create_account(handle="alice", email="a@x.com")

    # missing provenance fails before reaching a human
    with pytest.raises(SubmissionRejected):
        svc.submit_coa(submitter, _payload(source_url=""))

    svc.submit_coa(submitter, _payload())
    # second submission, same brand+batch+lab -> duplicate
    with pytest.raises(SubmissionRejected):
        svc.submit_coa(submitter, _payload(source_url="https://other.example/x"))


def test_service_escalate_path(tmp_path):
    svc = CommunityService(data_root=tmp_path)
    submitter = svc.accounts.create_account(handle="alice", email="a@x.com")
    mod = svc.accounts.create_account(handle="mod", email="m@x.com", role="admin")

    sub = svc.submit_coa(submitter, _payload())
    svc.claim(mod, sub.submission_id)
    escalated = svc.moderate(mod, sub.submission_id, "escalate", reason="needs operator")
    assert escalated.status == SubmissionStatus.ESCALATED
