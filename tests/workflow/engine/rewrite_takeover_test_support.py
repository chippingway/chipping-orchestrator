# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One auto-rebase replay the size gate handed to an adjudication, over the in-memory client.

Issue #7 is on `workflow:decomposing` with PR #42 over its branch. Its pinned
comment carries the attempt the auto rebase pinned -- the anchor PR #42
stood on, the terms it was made under, and the replay it recorded -- beside
the live late generation the size gate froze over that replay: the replay as
its candidate, the base it was measured over, a count past the ceiling, and
the publication it was entered on. Every key is spelled literally, since live
issues already carry them.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    rewrite_takeover as _takeover,
)
from orchestrator.workflow.engine.rewrite_takeover import TakeoverOutcome
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeIssue, make_issue

ISSUE = 7
PR_NUMBER = 42

_SHA_PAIRS = 20

# The head PR #42 stands on, the replay the rebase made of it, the base the
# gate measured the replay over, and a head nothing here produced.
ANCHOR = "a1" * _SHA_PAIRS
REPLAY = "b2" * _SHA_PAIRS
BASE = "e5" * _SHA_PAIRS
OTHER = "c3" * _SHA_PAIRS

LABEL_DECOMPOSING = "workflow:decomposing"
LABEL_FIXING = "workflow:fixing"

KEY_PENDING_PUSH = "pending_auto_base_rebase_push_sha"
KEY_REWRITE_PR = "pending_auto_base_rebase_rewrite_pr"
KEY_REWRITE_STAGE = "pending_auto_base_rebase_rewrite_stage"
KEY_REWRITE_SHA = "pending_auto_base_rebase_rewrite_sha"
KEY_ANNOUNCED = "pending_auto_base_rebase_announced_sha"
KEY_REPLAY = "late_auto_rebase_replay_sha"

# Every field one attempt puts on the comment, which a handoff retires as one.
ATTEMPT_KEYS = (KEY_PENDING_PUSH, KEY_REWRITE_PR, KEY_REWRITE_STAGE, KEY_REWRITE_SHA, KEY_ANNOUNCED)

# The park the auto rebase left standing over the pair, which a handoff
# retires with the attempt it belongs to.
STRANDED = MappingProxyType({
    "awaiting_human": True,
    "park_reason": "auto_base_rebase_failed",
})

# The flags a retired park reads as.
UNPARKED = MappingProxyType({
    "awaiting_human": False,
    "park_reason": None,
})

# A round a reviewer spent and the comment the issue last acted on: records a
# handoff leaves where it found them.
STANDING = MappingProxyType({
    "review_round": 3,
    "last_action_comment_id": 1007,
})

_ATTEMPT = MappingProxyType({
    KEY_PENDING_PUSH: ANCHOR,
    KEY_REWRITE_PR: PR_NUMBER,
    KEY_REWRITE_STAGE: LABEL_FIXING,
    KEY_REWRITE_SHA: REPLAY,
})

# The live generation the size gate froze over the replay, measured past its
# ceiling and entered on PR #42 standing on the anchor.
GENERATION = MappingProxyType({
    "late_cycle_id": 12,
    "late_generation": 1,
    "late_root_issue": ISSUE,
    "late_current_issue": ISSUE,
    "late_lineage_depth": 0,
    "late_candidate_sha": REPLAY,
    "late_base_sha": BASE,
    "late_threshold": 4000,
    "late_additions": 4098,
    "late_phase": "measuring",
    "late_post_publication": True,
    "late_source_stage": LABEL_FIXING,
    "late_published_pr_number": PR_NUMBER,
    "late_published_sha": ANCHOR,
})


def late_group(record: dict) -> dict:
    """What `record` carries of the late generation, the taken-over replay aside."""
    return {
        key: kept for key, kept in record.items()
        if key.startswith("late_") and key != KEY_REPLAY
    }


def _present(record: dict) -> dict:
    """`record` without the fields it gives None, which a seeded comment does not carry."""
    return {key: kept for key, kept in record.items() if kept is not None}


@dataclass
class TakeoverWorld:
    """Issue #7, its client, and handoffs taken over what it pins."""

    github: FakeGitHubClient
    issue: FakeIssue

    @classmethod
    def seeded(cls, **pinned: object) -> TakeoverWorld:
        """Issue #7 pinning the attempt and the generation with `pinned` over them -- a field given None dropped."""
        issue = make_issue(ISSUE, label=LABEL_DECOMPOSING)
        github = FakeGitHubClient([issue])
        github.seed_state(issue, **_present({"pr_number": PR_NUMBER, **_ATTEMPT, **GENERATION, **pinned}))
        return cls(github, issue)

    def takes_over(self) -> TakeoverOutcome:
        """Hand the attempt over, over the issue as it reads now."""
        return _takeover.takes_over(self.github, self.issue, self.github.read_pinned_state(self.issue))

    def standing(self, keys) -> dict:
        """What the pinned comment carries now under each of `keys`."""
        durable = self.pinned()
        return {key: durable.get(key) for key in keys}

    def pinned(self) -> dict:
        """The record the pinned comment carries now."""
        return self.github.pinned_data(ISSUE)

    def says(self, body: str, *, ours: bool = False) -> int:
        """A comment past everything on issue #7's thread -- a trusted human's, or this orchestrator's own; its id."""
        if ours:
            return self.github.comment(self.issue, _comments._with_orch_marker(body)).id
        said = FakeComment(id=self.github.next_reply_id(self.issue), body=body)
        self.issue.comments.append(said)
        return said.id

    def baseline_through(self, last: int, *, legacy: bool = False) -> str:
        """Issue #7's requirements baseline over its title, its body, and its thread through comment `last`.

        `legacy` spells it as the algorithm that counted a bare continue did.
        """
        return _content_hash._compute_user_content_hash(
            self.issue,
            _comments._orchestrator_ids(self.github.read_pinned_state(self.issue)),
            include_bare_continue=legacy,
            comments=[seen for seen in self.issue.comments if seen.id <= last],
        )

    def another_road(self, **fields: object) -> None:
        """Another road's whole-record write over the comment as it stands."""
        written = self.github.read_pinned_state(self.issue)
        written.data.update(fields)
        self.github.write_pinned_state(self.issue, written)
