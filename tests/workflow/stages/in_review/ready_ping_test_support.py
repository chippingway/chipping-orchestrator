# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An in_review issue one tick from its ready ping, and what GitHub or a restart can do to that ping.

Each double is armed off what its request carries -- an edit arming a ping,
the edit settling one, the ping's own post -- rather than off how many
requests came before it, and answers every other request as always. The ways
an edit is left unanswered are the in-memory client's own (`pinned_failures`);
a comment filled to its limit is its pinned record edited in place, as a
maintainer's hand would.
"""
from __future__ import annotations

import re
import sys
from typing import Self
from unittest.mock import patch

from orchestrator.github.comments import ORCHESTRATOR_COMMENT_MARKER
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import content_hash as _content_hash
from tests.support.fakes import FakeComment, FakeGitHubClient, FakePR, FakePRRef, FakeUser, make_issue
from tests.workflow import verified_approvals as _verified
from tests.workflow.fixtures import _agent, _issue_branch, _PatchedWorkflowMixin

ISSUE = 41

PR = 410

HEAD = "c0ffee12" * 5

# The pinned keys and comment words the ping is read back by -- formats live
# issues carry, so spelled here rather than read off the owner.
READY = "ready for review/merge"

PENDING = "ready_ping_pending"

READY_PING_SHA = "ready_ping_sha"

LEDGER = "orchestrator_comment_ids"

PR_LAST_COMMENT_ID = "pr_last_comment_id"

# The client requests the doubles stand in for.
EDIT_PINNED_STATE = "edit_pinned_state"

COMMENT = "comment"

MERGEABILITY = "pr_is_mergeable"

# How GitHub leaves an edit unanswered, as the client's `pinned_failures` names
# it: a comment the edit could not read, refused before anything went out; an
# edit sent and refused, which never landed; and one that landed and whose
# answer was lost. The second and third come back alike -- unconfirmed -- and
# only a later reading tells them apart. And how a process leaves it: killed
# with the edit unsent.
UNREADABLE = "unreadable"

REFUSED = "refused"

LOST = "lost"

DIES = "dies"

# What a comment carrying a ping's receipt spells it as.
RECEIPT = re.compile("<!--orchestrator-ready-ping:receipt=([0-9a-f]+)-->")

# A ping as a human copying one onto the thread would paste it: its words, its
# receipt, and the marker every post of this orchestrator closes on.
COPIED = (
    f":bell: PR #{PR} is {READY}.\n\n<!--orchestrator-ready-ping:receipt={{receipt}}-->"
    f"\n\n{ORCHESTRATOR_COMMENT_MARKER}"
)

# Who replies on the thread as a human.
HUMAN = "alice"

# A field a human fills a pinned comment up to its limit with.
_FILLER = "operator_note"

# Every cursor the stage reads already seeded, so no tick spends a write
# migrating one.
_CURSORS = (PR_LAST_COMMENT_ID, "pr_last_review_comment_id", "pr_last_review_summary_id")


def failing(case, how: str, *, settling: bool):
    """A patch leaving `case`'s ping arming, or its settlement, unanswered the way `how` names."""
    return patch.object(
        case.github, EDIT_PINNED_STATE, _FailsTheWrite(case.github, how, settling=settling),
    )


class _ReadyPingFixture(_PatchedWorkflowMixin):
    """An issue in review whose pull request is mergeable, approved, and unvetoed on `HEAD`, over passing evidence."""

    def seeded(self) -> None:
        """Seed the issue with its drift baseline, every cursor in place, and settled evidence of `HEAD`, unpinged."""
        github = FakeGitHubClient()
        issue = make_issue(ISSUE, label="in_review")
        github.add_issue(issue)
        self.pull_request = FakePR(
            number=PR, head_branch=_issue_branch(ISSUE), head=FakePRRef(sha=HEAD),
            approved=True, mergeable=True, check_state="success",
        )
        github.add_pr(self.pull_request)
        github.seed_state(
            issue, branch=_issue_branch(ISSUE), pr_number=PR, review_round=1,
            user_content_hash=_content_hash._compute_user_content_hash(issue, set()),
            **dict.fromkeys(_CURSORS, 0),
        )
        _verified.verifies_the_approval(github, issue)
        self.github = github
        self.issue = issue

    def tick(self):
        """One in_review tick, over the checkout on this host and the branch fetched where the pull request stands."""
        return self._run_in_review(
            self.github, self.issue, run_agent=_agent(),
            issue_checkout=_verified.CHECKOUT, fetched_branch_tip=self.pull_request.head.sha,
        )

    def pinned(self) -> dict:
        """The issue's pinned record as it stands."""
        return self.github.pinned_data(ISSUE)

    def pings(self) -> list:
        """Every ready ping the issue thread carries."""
        return [said for said in self.issue.comments if READY in (said.body or "")]

    def replies(self, body: str) -> int:
        """Append a reply a human wrote on the thread now; its id."""
        reply_id = self.github.next_reply_id(self.issue)
        author = FakeUser(HUMAN)
        self.issue.comments.append(FakeComment(id=reply_id, body=body, user=author))
        return reply_id

    def fills(self, *, filled: bool = True) -> None:
        """Fill the pinned comment up to exactly its limit, as a human's notes on it might; or take them off."""
        pinned = self.github._pinned[ISSUE].state_data
        pinned.pop(_FILLER, None)
        if filled:
            pinned[_FILLER] = ""
            pinned[_FILLER] = "x" * (MAX_PINNED_BODY - len(pinned_state_body(pinned)))

    def assert_settled(self, receipt: str | None = None) -> None:
        """One ping on the thread -- under `receipt`, where given -- recorded on the head, and a quiet tick after.

        The head is the one the pull request stands on.
        """
        pinged = self.pings()
        pinned = self.pinned()
        carried = [RECEIPT.search(said.body).group(1) for said in pinged]
        self.assertEqual(len(carried), 1)
        if receipt is not None:
            self.assertEqual(carried, [receipt])
        self.assertEqual(pinned[READY_PING_SHA], self.pull_request.head.sha)
        self.assertIsNone(pinned[PENDING])
        self.assertIn(pinged[0].id, pinned[LEDGER])
        settled = (self.github.write_state_calls, len(self.issue.comments), self.github.label_history)
        self.tick()
        quiet = (self.github.write_state_calls, len(self.issue.comments), self.github.label_history)
        self.assertEqual(quiet, settled)


class _EditedWhileMerging:
    """The merge gate's mergeability answered while a maintainer edits the pinned comment by hand.

    `fields` are what the edit writes into the record, as a human's hand
    would, between the reading the tick decided on and the ping's first write
    -- or the park's, where `mergeable` is False.
    """

    def __init__(self, case, *, mergeable: bool = True, **fields) -> None:
        self._pinned = case.github._pinned[ISSUE]
        self._mergeable = mergeable
        self._fields = fields

    def __call__(self, *called, **options) -> bool:
        self._pinned.state_data.update(self._fields)
        return self._mergeable


class _FailsTheWrite:
    """The ping's arming or its settlement, left unanswered the way `how` names; every other edit answered.

    The settlement is the edit dropping a pending record the comment it lands
    over carries, and the arming the edit putting one down. A failure the
    client names is set for that one edit alone, so it is gone again by the
    time the tick that follows reads the comment; DIES is a poller killed
    with the edit unsent.
    """

    def __init__(self, github, how: str, *, settling: bool) -> None:
        self._edit = github.edit_pinned_state
        self._failures = github.pinned_failures
        self._how = how
        self._settling = settling

    def __call__(self, issue, state, **options):
        armed = isinstance(state.get(PENDING), dict)
        dropped = isinstance(options["over"].get(PENDING), dict) and not armed
        targeted = dropped if self._settling else armed
        if not targeted:
            return self._edit(issue, state, **options)
        if self._how == DIES:
            sys.exit(issue.number)
        failures = getattr(self._failures, self._how)
        failures.add(issue.number)
        edited = self._edit(issue, state, **options)
        failures.discard(issue.number)
        return edited


class _BehindArming:
    """The arming edit answered, and the comment then left as the settlement's preparation cannot take it.

    `full` fills it to its limit by hand; otherwise the reading the
    preparation takes behind the arming goes unanswered once.
    """

    def __init__(self, case, *, full: bool) -> None:
        self._case = case
        self._edit = case.github.edit_pinned_state
        self._failures = case.github.pinned_failures
        self._full = full

    def __call__(self, issue, state, **options):
        edited = self._edit(issue, state, **options)
        if not isinstance(state.get(PENDING), dict):
            return edited
        if self._full:
            self._case.fills()
        else:
            self._failures.unanswered_once.add(issue.number)
        return edited


class _UnansweredPost:
    """The ping's post answered with an error: landed on the thread first where `lands`, as a lost response."""

    def __init__(self, github, *, lands: bool) -> None:
        self._comment = github.comment
        self._lands = lands

    def __call__(self, issue, body):
        if READY not in body:
            return self._comment(issue, body)
        if self._lands:
            self._comment(issue, body)
        raise RuntimeError("GitHub did not answer the ready ping's post")


class _UnreadOnce:
    """The issue thread's first read behind the request named `behind` left unanswered; all else answered.

    Entered as a context. Unanswered once rather than for good, since a read
    that fails says nothing about the one after it: a later read in the same
    tick going through is what a tick that took the failure for an absence
    would post a second ping behind. The feedback scan ahead of the merge gate
    reads the thread as always, so behind the gate's first request -- its
    mergeability -- the read left unanswered is a pending ping's recovery, and
    behind the ping's post it is the read looking for what that post landed.
    """

    def __init__(self, github, behind: str) -> None:
        self._asked = getattr(github, behind)
        self._reads = github.comments_after
        self._owed = False
        self._patches = (
            patch.object(github, behind, self._arms),
            patch.object(github, "comments_after", self._read),
        )

    def __enter__(self) -> Self:
        for patched in self._patches:
            patched.start()
        return self

    def __exit__(self, *raised) -> None:
        for patched in reversed(self._patches):
            patched.stop()

    def _arms(self, *called, **options):
        self._owed = True
        return self._asked(*called, **options)

    def _read(self, *called, **options):
        if self._owed:
            self._owed = False
            raise RuntimeError("GitHub did not answer the issue thread's read")
        return self._reads(*called, **options)
