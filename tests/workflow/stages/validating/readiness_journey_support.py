# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a walk past an approval told the pull request and the issue, and in what order, through the ready ping.

The squash-rebase journey (`squash_rebase_journey_support`) records every run
a dispatch spawns beside how far the threads had been numbered when it was
spawned, and every comment either thread carries is numbered in the one
ascending space GitHub numbers them in. So the walk reads back as one timeline
(`told`): each developer report by the commit it is about, each verification
artifact by its witness, tested commit, and target head, each spawn by its
role, and each ready ping -- the one comment that tells a human the pull
request is ready for review and merge.

The roles a run is spawned under are spelled here, where the timeline names
them, and the journey records its runs under them.
"""
from __future__ import annotations

from operator import itemgetter

from orchestrator.github import developer_reports as _reports, verification_artifacts as _artifacts
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import verification_settlement_state as _settlement

# What a timeline entry is, beside what it carries.
REPORT = "report"

ARTIFACT = "artifact"

SPAWN = "spawn"

READY = "ready"

# The roles a run is spawned under.
REFRESHER = "refresher"

REVIEWER = "reviewer"

DOCUMENTER = "documenter"

# The witness of a reviewer's own declared run.
REVIEWER_REPORTED = EvidenceSource.REVIEWER_REPORTED

# The words every ready ping carries, and the pinned records it is recorded by.
_READY_WORDS = "ready for review/merge"

_READY_PING_SHA = "ready_ping_sha"

_READY_PING_PENDING = "ready_ping_pending"

# A ready ping as the timeline tells it.
_PINGED = (READY,)

# Where a comment sorts against a spawn its high water reached.
_COMMENT_ORDER = 0

_SPAWN_ORDER = 1


def high_water(case) -> int:
    """The highest id either of the case's threads carries, 0 for none: how far the walk has been told."""
    threads = (*case.issue.comments, *case.pull_request.issue_comments)
    return max((said.id for said in threads), default=0)


def refreshed_into_review(head: str) -> tuple:
    """What a walk tells from a report refresh of `head` on, through the ready ping, in order.

    The refresh spawned and the report of `head` it publishes, the reviewer
    spawned and the artifact of its own run on `head`, the docs pass behind
    that approval, and the ready ping last.
    """
    walked = (
        (SPAWN, REFRESHER),
        (REPORT, head),
        (SPAWN, REVIEWER),
        (ARTIFACT, REVIEWER_REPORTED, head, head),
        (SPAWN, DOCUMENTER),
        (READY,),
    )
    return walked


class ReadinessReadings:
    """The timeline of a walk on a case that records `happened` -- each spawn's high water and role, in order."""

    def told(self, since: int = 0) -> tuple:
        """Every report, artifact, spawn, and ready ping past the high water `since`, in the order it happened.

        A spawn sorts after every comment its high water reached and before
        every comment numbered past it.
        """
        entries = []
        for said, entry in self._comment_entries():
            if said.id > since:
                entries.append((said.id, _COMMENT_ORDER, entry))
        for mark, role in self.happened:
            if mark >= since:
                entries.append((mark, _SPAWN_ORDER, (SPAWN, role)))
        entries.sort(key=itemgetter(0, 1))
        return tuple(ordered[-1] for ordered in entries)

    def ready_pings(self) -> list:
        """Every ready ping on the issue thread, oldest first."""
        return [said for said in self.issue.comments if _READY_WORDS in (said.body or "")]

    def assert_ready_on(self, head: str, since: int = 0) -> None:
        """One ready ping past `since`, the last thing the walk told, recorded on `head` over passing evidence of it.

        An artifact answering for `head` was told before it, nothing is left
        pending, and the evidence current is the one that answers for `head`,
        passing.
        """
        told = self.told(since)
        pinged = told.count(_PINGED)
        self.assertEqual((pinged, told[-1]), (1, _PINGED))
        self.assertTrue(any(_answers_for(entry, head) for entry in told))
        pinned = PinnedState(state_data=self.pinned())
        self.assertEqual(_recorded(pinned), (head, None, head, True))

    def assert_refreshed_into_review(self, head: str, since: int) -> None:
        """The walk past `since` ends on a report refresh of `head` reviewed, documented, and then pinged once.

        Every reviewer spawned on the walk approved through one run of the
        verification gate, and the last was handed `head`.
        """
        expected = refreshed_into_review(head)
        told = self.told(since)
        reviewers = [prompt for role, prompt in self.spawns if role == REVIEWER]
        self.assertEqual(told[-len(expected):], expected)
        self.assertEqual(self.verifications, len(reviewers))
        self.assertIn(head, reviewers[-1])
        self.assert_ready_on(head, since)

    def assert_quiet(self, ticks: int = 3) -> None:
        """`ticks` more dispatches spawn, verify, write, relabel, and tell nothing."""
        standing = self._quiet_standing()
        for _ in range(ticks):
            self.dispatched()
        self.assertEqual(self._quiet_standing(), standing)

    def _quiet_standing(self) -> tuple:
        """Everything a quiet dispatch must leave as it is: what was told and run, and every write the client took."""
        github = self.github
        ran = (len(self.spawns), self.verifications)
        wrote = (
            github.write_state_calls,
            len(github.label_history),
            len(github.posted_comments),
            len(github.posted_pr_comments),
        )
        return self.told(), ran, wrote

    def _comment_entries(self) -> list:
        """Each report and artifact on the pull request, and each ready ping on the issue, beside its comment."""
        bot = self.github._bot_login
        entries = [(said, (READY,)) for said in self.ready_pings()]
        for said in self.pull_request.issue_comments:
            report = _reports.developer_report_from_comment(said, bot_login=bot)
            artifact = _artifacts.verification_artifact_from_comment(said, bot_login=bot)
            if report is not None:
                entries.append((said, (REPORT, report.source_sha)))
            elif artifact is not None:
                entries.append((said, (ARTIFACT, artifact.source, artifact.tested_sha, artifact.target_head)))
        return entries


class RefusesTheSettlement:
    """GitHub refusing, once, the edit that records a posted ping -- the one dropping its pending record.

    Every other edit is answered as always. The refusal is the in-memory
    client's own, set for that one edit alone.
    """

    def __init__(self, github) -> None:
        self._edit = github.edit_pinned_state
        self._failures = github.pinned_failures
        self._refused = False

    def __call__(self, issue, state, **options):
        if self._refused or not _settles_a_ping(state, options["over"]):
            return self._edit(issue, state, **options)
        self._refused = True
        self._failures.refused.add(issue.number)
        edited = self._edit(issue, state, **options)
        self._failures.refused.discard(issue.number)
        return edited


def _settles_a_ping(state, over) -> bool:
    """Whether an edit of `over` into `state` records a ping as made: its pending record dropped beside the stamp."""
    was_pending = isinstance(over.get(_READY_PING_PENDING), dict)
    dropped = was_pending and state.get(_READY_PING_PENDING) is None
    return dropped and bool(state.get(_READY_PING_SHA))


def _answers_for(entry: tuple, head: str) -> bool:
    """Whether a timeline `entry` is an artifact answering for `head`."""
    return entry[0] == ARTIFACT and entry[-1] == head


def _recorded(pinned: PinnedState) -> tuple:
    """The head recorded as pinged and the ping pending, then the head the current evidence answers for and its pass."""
    current = _settlement.read_current_evidence(pinned)
    pinged = (pinned.get(_READY_PING_SHA), pinned.get(_READY_PING_PENDING))
    return (*pinged, current.binding.target.target_head, current.passed)
