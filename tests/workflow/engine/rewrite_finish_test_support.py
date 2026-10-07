# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One landed base rewrite and the issue it finishes, driven through the finalizer over the in-memory client.

Issue #7 is on `workflow:fixing` with PR #42 over its branch, and its pinned
comment carries the attempt an auto rebase pinned before git ran -- the anchor
the push was leased against, the terms it was made under, and the head the
replay produced. What a case varies is the road that reached the finish
(`Road`), what the comment carries beside the attempt, and what another road
writes meanwhile. What it reads back is what GitHub was left with: the pinned
record, the label, the notices, and the events -- every key spelled
literally, since live issues already carry them.
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.git.base_sync.rewrite_handoffs import (
    _CheckoutReading,
    _LandedRewrite,
    _PushOutcome,
    _RewriteAttempt,
    _RewriteCandidate,
    _RewriteRefusal,
)
from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.git.ref_transport import _RefRead
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.engine import rewrite_finish as _finish
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad, LandedFinish
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue
from tests.workflow.repo_values import _TEST_SPEC

ISSUE = 7
PR_NUMBER = 42
BRANCH = "orchestrator/acme__widget/issue-7"

_SHA_PAIRS = 20

# The head the pull request stood on, and the replay the rebase made of it.
ANCHOR = "a1" * _SHA_PAIRS
LANDED = "b2" * _SHA_PAIRS
# A head nothing in this attempt produced.
OTHER = "c3" * _SHA_PAIRS

LABEL_FIXING = "workflow:fixing"
LABEL_VALIDATING = "workflow:validating"

KEY_PR = "pr_number"
KEY_REVIEW_ROUND = "review_round"
KEY_AWAITING_HUMAN = "awaiting_human"
KEY_PARK_REASON = "park_reason"
KEY_WATERMARK = "last_action_comment_id"
KEY_LEDGER = "orchestrator_comment_ids"
KEY_REWRITE_DEBT = "developer_report_rewrite_debt"
KEY_PENDING_PUSH = "pending_auto_base_rebase_push_sha"
KEY_REWRITE_PR = "pending_auto_base_rebase_rewrite_pr"
KEY_REWRITE_STAGE = "pending_auto_base_rebase_rewrite_stage"
KEY_REWRITE_SHA = "pending_auto_base_rebase_rewrite_sha"
KEY_ANNOUNCED = "pending_auto_base_rebase_announced_sha"

# Every field one attempt puts on the comment, which a finish retires as one.
ATTEMPT_KEYS = (KEY_PENDING_PUSH, KEY_REWRITE_PR, KEY_REWRITE_STAGE, KEY_REWRITE_SHA, KEY_ANNOUNCED)

PARK_UNRECORDED_DEBT = "auto_base_rebase_unrecorded_debt"

# A round a reviewer already spent on the head the rewrite replaced.
SPENT_ROUND = 3

# How many commits the head the publication replaced was behind its base.
LAG = 2


def owed(previous: str = ANCHOR, rewritten: str = LANDED, *, pr: int = PR_NUMBER) -> dict:
    """The pinned debt a rewrite of PR #42's branch from `previous` onto `rewritten` leaves."""
    return {"pr": pr, "branch": BRANCH, "previous_head": previous, "rewritten_head": rewritten}


def attempt_record(**overrides: object) -> dict:
    """The record an attempt that rebased PR #42 from `ANCHOR` onto `LANDED` pinned, with `overrides`."""
    record = {
        KEY_PR: PR_NUMBER,
        "branch": BRANCH,
        KEY_REVIEW_ROUND: SPENT_ROUND,
        KEY_PENDING_PUSH: ANCHOR,
        KEY_REWRITE_PR: PR_NUMBER,
        KEY_REWRITE_STAGE: LABEL_FIXING,
        KEY_REWRITE_SHA: LANDED,
    }
    record.update(overrides)
    return {name: kept for name, kept in record.items() if kept is not None}


def attempt(record: dict) -> dict:
    """The attempt's members as `record` carries them."""
    return {key: record.get(key) for key in ATTEMPT_KEYS}


def checkpoint(record: dict) -> tuple:
    """What `record` carries of a finish's checkpoint: the debt, the mark, the anchor, and the round."""
    return (
        record.get(KEY_REWRITE_DEBT),
        record.get(KEY_ANNOUNCED),
        record.get(KEY_PENDING_PUSH),
        record.get(KEY_REVIEW_ROUND),
    )


@dataclass(frozen=True)
class Road:
    """Which road reached a finish, and what it found: the push it made, the base and remote it read, its reply.

    `head` is the commit the rebase left, `LANDED` unless a case has it replay
    nothing, `refusal` the guard a REFUSED publication names, `behind` the lag
    counted against the base -- None for a comparison that did not happen --
    and `remote` where the remote was last read, None for a reading that
    established nothing.
    """

    road: FinishRoad = FinishRoad.PUBLICATION
    outcome: _PushOutcome = _PushOutcome.ACCEPTED
    behind: int | None = 0
    remote: str | None = LANDED
    retry: int | None = None
    head: str = LANDED
    refusal: _RewriteRefusal | None = None

    def landing(self) -> _LandedRewrite:
        """The landing of `ANCHOR`'s replay onto `head` this road hands over."""
        reading = _CheckoutReading(
            head=self.head,
            tree="2" * _SHA_PAIRS * 2,
            status=_WorktreeStatus(readable=True),
            base=self._base(),
        )
        candidate = _RewriteCandidate(
            attempt=_RewriteAttempt(anchor=ANCHOR, pr_number=PR_NUMBER, stage=WorkflowLabel.FIXING),
            branch=BRANCH,
            original_tree="1" * _SHA_PAIRS * 2,
            checkout=reading,
            remote=_RefRead(sha=ANCHOR),
        )
        return _LandedRewrite(
            candidate=candidate, outcome=self.outcome, remote=_RefRead(sha=self.remote), refusal=self.refusal,
        )

    def _base(self) -> _BranchDivergence:
        """The landed head counted against its base: `behind` it, or a count that did not happen."""
        if self.behind is None:
            return _BranchDivergence()
        return _BranchDivergence(tip=OTHER, ahead=1, behind=self.behind, readable=True)


# The tick that published its own rebase, a recovery that found that push
# standing, and one that pushed the replay again.
PUBLISHED = Road()
FOUND = Road(FinishRoad.RECOVERY, _PushOutcome.OBSERVED)
PUSHED_AGAIN = Road(FinishRoad.RECOVERY, _PushOutcome.ACCEPTED)


@dataclass
class FinishWorld:
    """Issue #7, its client, and the finishes handed to the finalizer over what it pins."""

    github: FakeGitHubClient
    issue: FakeIssue

    @classmethod
    def seeded(cls, *, label: str = LABEL_FIXING, **pinned: object) -> FinishWorld:
        """Issue #7 on `label`, pinning `attempt_record` with `pinned` over it -- a field given None dropped."""
        issue = make_issue(ISSUE, label=label)
        github = FakeGitHubClient([issue])
        github.seed_state(issue, **attempt_record(**pinned))
        return cls(github, issue)

    def finish(self, road: Road = PUBLISHED) -> LandedFinish:
        """The finish of the landing `road` reached, over the issue as it reads now."""
        return LandedFinish(
            gh=self.github,
            spec=_TEST_SPEC,
            issue=self.issue,
            state=self.github.read_pinned_state(self.issue),
            landed=road.landing(),
            label=self.github.workflow_label(self.issue),
            road=road.road,
            lag=LAG,
            retry=road.retry,
        )

    def finalizes(self, road: Road = PUBLISHED) -> FinishOutcome:
        """Finish the landing `road` reached through the finalizer."""
        return _finish.finalizes(self.finish(road))

    def pinned(self) -> dict:
        """The record the pinned comment carries now."""
        return self.github.pinned_data(ISSUE)

    def another_road(self, **fields: object) -> None:
        """Another road's whole-record write over the comment as it stands."""
        written = self.github.read_pinned_state(self.issue)
        written.data.update(fields)
        self.github.write_pinned_state(self.issue, written)

    def said(self) -> tuple[list[str], list[dict]]:
        """The notices PR #42 was given, and the `base_rebased` events filed, each without its timestamp."""
        notices = [
            body for number, body in self.github.posted_pr_comments
            if number == PR_NUMBER
        ]
        events = [
            _untimed(event) for event in self.github.recorded_events
            if event.get("event") == "base_rebased"
        ]
        return notices, events

    def relabels(self) -> tuple[str | None, ...]:
        """Every workflow label written onto issue #7, in order."""
        history = self.github.label_history
        return tuple(label for number, label in history if number == ISSUE)


def _untimed(event: dict) -> dict:
    """One recorded event without its timestamp, which is the moment it was filed."""
    return {name: recorded for name, recorded in event.items() if name != "ts"}
