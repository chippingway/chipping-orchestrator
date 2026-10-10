# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The per-tick base refresh leaves both read-only stages' checkouts alone.

Neither stage ships code, so a checkout under one of their labels is something
to read rather than work in progress -- an inspection target an unsafe park
left an operator, and, in the discussion stage which keeps its tree on every
exit short of the terminal that finishes the issue, the state the next round is
meant to open on. The refresh runs before any handler does, so without this
gate a tick would rebase
`origin/<base>` over that tree, and it would do it on exactly the parked issues
the handlers themselves never touch again.

The discussion stage does push once -- the plan its humans confirmed, from its
own publication and onto a pull request of that file alone -- which is why the
gate reads that stage's in-flight records as well as its parks: a rebase over
the commit a publication is mid-way through pushing would move the branch off
the very tip the record names. The other records that freeze a branch by their
presence are read here too -- the late size gate's, a squash's, and a developer
report recorded and not yet settled -- beside what ends each freeze.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.workflow.engine import base_refresh
from tests.git.base_sync.sync_test_support import _patch_base_sync
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_DISCUSSION,
    LABEL_IMPLEMENTING,
    LABEL_QUESTION,
    LABEL_VALIDATING,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
)

_BASE_REFRESH_ISSUE_NUMBER = 980
_RELABELED_ISSUE_NUMBER = 984
_UNSPENT_BASELINE_ISSUE_NUMBER = 987
_CONSUMED_PARK_ISSUE_NUMBER = 988
_IN_FLIGHT_ISSUE_NUMBER = 990
_FROZEN_CANDIDATE_ISSUE_NUMBER = 993
_REFUSED_HANDOFF_ISSUE_NUMBER = 994
_ACCEPTED_COMMIT_ISSUE_NUMBER = 995
_UNREADABLE_HEAD_ISSUE_NUMBER = 996
_STALE_EXEMPTION_ISSUE_NUMBER = 997
_PUBLISHED_COMMIT_ISSUE_NUMBER = 1001
_PARTIAL_RECORD_ISSUE_NUMBER = 1010
_FALSEY_RECORD_ISSUE_NUMBER = 1015
_LONE_LEASE_ISSUE_NUMBER = 1020
_PENDING_COLLAPSE_ISSUE_NUMBER = 1025
_PARTIAL_COLLAPSE_ISSUE_NUMBER = 1030
_REPORT_IN_FLIGHT_ISSUE_NUMBER = 1035
_REPORT_SETTLED_ISSUE_NUMBER = 1040
_HANDED_ON_ISSUE_NUMBER = 1002
_PUBLISHED_EXEMPTION_ISSUE_NUMBER = 1003
_UNREAD_MEASUREMENT_ISSUE_NUMBER = 998
_ANSWERED_MEASUREMENT_ISSUE_NUMBER = 999
_MEASUREMENT_PARK = "late_measurement_failed"
_CERTIFIED_TIP = "head-the-relabel-certified"
_ACCEPTED_COMMIT = MEASURED_CANDIDATE_SHA
# What a developer committed after the verdict: the exemption still names the
# commit it accepted, and the checkout has moved past it.
_HEAD_PAST_THE_EXEMPTION = "f" * SHA_LENGTH
_FROZEN_CANDIDATE = MEASURED_CANDIDATE_SHA
# The head a squash recorded before it collapsed the branch onto one commit.
_COLLAPSED_HEAD = "e" * SHA_LENGTH
_WORKTREE_ROOT = "/tmp/read-only-issue-"
_READ_ONLY_LABELS = (LABEL_QUESTION, LABEL_DISCUSSION)
# Both the clean hand-back and the refusal have to hold the branch still: the
# refusal names a reset target, and a rebase would move it out from under the
# operator following that instruction.
_UNCONSUMED_PARKS = (
    "discussion_response",
    "discussion_unsafe_relabel",
    "question_commits",
)
# What a discussion tick that died mid-flight leaves behind, with no park and
# no flag beside it: a round that never reported, and a publication that was
# already pushing when the process went away.
_IN_FLIGHT_RECORDS = (
    {"discussion_round_open": True},
    {"discussion_publishing_sha": "head-a-publication-was-pushing"},
)


# A late reading with its candidate gone, one field at a time: every one of
# these is a key the write that froze the pair put down beside the commit, and
# every one is something the retry reads. A comment carrying any of them and
# no candidate is the damage the dispatcher parks on a tick later.
_PARTIAL_READINGS: tuple[dict, ...] = (
    {"late_base_sha": _ACCEPTED_COMMIT},
    {"late_threshold": 400},
    {"late_additions": 12},
    {"late_phase": "measuring"},
    {"late_cycle_id": 1},
    {"late_published_pr_number": 42},
)

# The same records at values that read FALSE, which is how the key being there
# is told from the value it holds. A count of `0` is what a candidate adding
# nothing measures to, a ceiling of `0` is one an operator can configure, and
# a marker reading `false` is what a hand edit leaves -- so a freeze asking
# for truth covers none of them while the guard that refuses them asks only
# whether the comment carries the key.
# The terms a squash records before it rewrites the branch, one member at a
# time. Every one of them is a claim that a collapse is outstanding, and the
# squash's own reader refuses a comment carrying any of them -- including one
# spelled `null`, which is what a hand edit or an older binary leaves. Read
# for a value, this refresh would rebase a branch that owner then declines to
# touch, and the collapse would be stranded on a checkout something rewrote
# underneath it.
_PARTIAL_COLLAPSES: tuple[dict, ...] = (
    {"late_collapse_head": _COLLAPSED_HEAD},
    {"late_collapse_base_sha": _ACCEPTED_COMMIT},
    {"late_collapse_count": 3},
    {"late_collapse_count": None},
    {"late_collapse_head": ""},
)


# A developer report recorded and not yet settled, by each record that says
# so: the delivery a run wrote before its binding, the transaction that binding
# made before its settlement, and each spelled in a shape nobody can read,
# which is still a report somebody owes the pull request. Neither follows a
# rewrite -- the delivery binds to whichever head the receipt names when it is
# bound, and the transaction names the head it was written about.
_REPORTS_IN_FLIGHT: tuple[dict, ...] = (
    {"developer_report_delivery": {"revision": 2, "report": "A report of the rebased head."}},
    {"developer_report_pending": {"pr": 42, "revision": 2, "sha": _ACCEPTED_COMMIT}},
    {"developer_report_delivery": "unreadable"},
    {"developer_report_pending": {}},
)


_FALSEY_READINGS: tuple[dict, ...] = (
    {"late_additions": 0},
    {"late_threshold": 0},
    {"late_post_publication": False},
    {"late_base_sha": ""},
)


class _SkipCase:
    """One pre-tick sync of a seeded issue, and what it was allowed to do."""

    def _assert_skipped(
        self, issue_number: int, label: str, head: str = "", **seeded,
    ) -> None:
        # The rev-list and rebase helpers would shell out if reached, so a
        # regression that lets the sync proceed surfaces as a call on these.
        git_mock = MagicMock()
        rebased = self._sync(issue_number, label, head, git_mock, seeded)

        git_mock.assert_not_called()
        rebased.assert_not_called()

    def _assert_synced(
        self,
        issue_number: int,
        head: str = "",
        label: str = LABEL_IMPLEMENTING,
        **seeded,
    ) -> None:
        """Nothing held the branch, so the ordinary base sync went ahead."""
        git_mock = MagicMock(
            return_value=MagicMock(returncode=0, stdout="0"),
        )
        self._sync(issue_number, label, head, git_mock, seeded)

        git_mock.assert_called()

    def _sync(self, issue_number, label, head, git_mock, seeded):
        """Run one sync of this issue's worktree with git doubled out."""
        gh = FakeGitHubClient()
        issue = make_issue(issue_number, label=label)
        gh.add_issue(issue)
        if seeded:
            gh.seed_state(issue.number, **seeded)

        rebase_mock = MagicMock(return_value=(True, []))
        with _patch_base_sync(
            git=git_mock,
            dirty=MagicMock(return_value=[]),
            rebase=rebase_mock,
            head_sha=MagicMock(return_value=head),
        ):
            base_refresh._sync_worktree_with_base(
                gh,
                _TEST_SPEC,
                Path(f"{_WORKTREE_ROOT}{issue_number}"),
                issue_number,
            )
        return rebase_mock


class ReadOnlyLabelBaseRefreshSkipTest(_SkipCase, unittest.TestCase):

    def test_a_read_only_label_skips_base_sync(self) -> None:
        for offset, label in enumerate(_READ_ONLY_LABELS):
            with self.subTest(label=label):
                self._assert_skipped(_BASE_REFRESH_ISSUE_NUMBER + offset, label)

    def test_an_unconsumed_park_outlives_its_label(self) -> None:
        # The relabel to implementing takes the label away a whole tick before
        # the implementing guard reads the park: the refresh runs first. A
        # rebase in that window moves the branch off the SHA the round
        # recorded, so the guard convicts a branch nobody touched -- and its
        # refusal asks for a reset back to that same SHA, which only hands the
        # next tick the same rebase to redo. The park is what holds the
        # checkout still until the guard has answered for it.
        for offset, park_reason in enumerate(_UNCONSUMED_PARKS):
            with self.subTest(park_reason=park_reason):
                issue_number = _RELABELED_ISSUE_NUMBER + offset
                self._assert_skipped(
                    issue_number,
                    LABEL_IMPLEMENTING,
                    awaiting_human=True,
                    park_reason=park_reason,
                )

    def test_an_unspent_baseline_holds_the_branch(self) -> None:
        # The park is gone -- the guard accepted the relabel -- but the dev it
        # handed to answered with a question, or was cut short, without
        # committing. The certified tip is still what the next spawn measures
        # against, so a rebase here would move the branch off it while the
        # inherited commits it names are still there, and the spawn path would
        # read them as an interrupted dev run and publish them with no agent
        # having run at all.
        self._assert_skipped(
            _UNSPENT_BASELINE_ISSUE_NUMBER,
            LABEL_IMPLEMENTING,
            awaiting_human=True,
            park_reason="agent_question",
            read_only_baseline_sha=_CERTIFIED_TIP,
        )

    def test_unfinished_discussion_work_holds_it(self) -> None:
        # The records a discussion tick leaves while it is mid-flight, on an
        # issue an operator has already relabeled: the label is gone, and
        # neither record depends on `awaiting_human` -- an opening round leaves
        # the issue unparked by design -- so the park read above never sees
        # them. Rebasing over the commit such a tick died holding moves the
        # branch off the anchor its own stage measures it against, and on a
        # PR-backed issue the PR-aware route would push that rewrite over a
        # plan PR the publication may already have opened.
        for offset, record in enumerate(_IN_FLIGHT_RECORDS):
            with self.subTest(record=record):
                self._assert_skipped(
                    _IN_FLIGHT_ISSUE_NUMBER + offset,
                    LABEL_IMPLEMENTING,
                    awaiting_human=False,
                    park_reason=None,
                    **record,
                )

    def test_a_frozen_late_candidate_holds_the_branch(self) -> None:
        # The size gate names one commit, measures it against one base, shows
        # an agent the diff between them, and publishes or preserves exactly
        # that commit several ticks later. A rebase in any of those gaps moves
        # the branch off the SHA every one of those steps acts on -- and the
        # step that noticed would park rather than substitute whatever HEAD had
        # become, so the adjudication would stall on a rewrite nobody asked
        # for. No park and no label say so: the record is on an issue still
        # wearing whichever label the adjudication reached it under.
        self._assert_skipped(
            _FROZEN_CANDIDATE_ISSUE_NUMBER,
            LABEL_IMPLEMENTING,
            awaiting_human=False,
            park_reason=None,
            late_candidate_sha=_FROZEN_CANDIDATE,
        )

    def test_a_consumed_park_syncs_again(self) -> None:
        # The guard cleared the park and persisted it, so nothing is holding
        # the branch any more and the ordinary base sync resumes. Without this
        # the freeze would be permanent for every issue that ever passed
        # through a read-only stage.
        self._assert_synced(
            _CONSUMED_PARK_ISSUE_NUMBER, awaiting_human=False, park_reason=None,
        )


class PendingCollapseSkipTest(_SkipCase, unittest.TestCase):
    """A squash mid-rewrite is the one record a rebase cannot be undone from.

    Every other freeze here protects a commit a later reader has to find. This
    one protects a RELATIONSHIP: the recovery proves the commit on the branch
    carries the tree the recorded head left, which is what a squash produces
    and what a rebase replaces with a commit carrying the base advance too.
    """

    def test_a_pending_collapse_holds_the_branch(self) -> None:
        # A squash says what it is about to do before it does it, and the tick
        # that comes back proves the commit on the branch carries the tree the
        # recorded head left -- which is what a squash produces and what a
        # rebase destroys. Rebased inside that window the collapse is gone,
        # the recovery refuses instead of finishing it, and the pull request
        # is left standing on the history the record says was collapsed with
        # the rebase already force-pushed over it.
        self._assert_skipped(
            _PENDING_COLLAPSE_ISSUE_NUMBER,
            LABEL_VALIDATING,
            awaiting_human=False,
            park_reason=None,
            late_collapse_head=_COLLAPSED_HEAD,
            late_collapse_base_sha=_ACCEPTED_COMMIT,
            late_collapse_count=3,
        )

    def test_a_partial_collapse_holds_the_branch(self) -> None:
        # Being unreadable is not being absent: the squash refuses a comment
        # carrying any member of the group, so the freeze has to cover every
        # one of them or it covers less than the refusal it exists to make
        # reachable.
        for offset, claimed in enumerate(_PARTIAL_COLLAPSES):
            with self.subTest(record=claimed):
                self._assert_skipped(
                    _PARTIAL_COLLAPSE_ISSUE_NUMBER + offset,
                    LABEL_VALIDATING,
                    awaiting_human=False,
                    park_reason=None,
                    **claimed,
                )


class LateRecordBaseRefreshSkipTest(_SkipCase, unittest.TestCase):
    """The refresh runs first each tick, so it runs ahead of the size gate.

    Both late records name a commit a LATER tick has to find in the checkout,
    and neither reader substitutes what it finds instead: the gate measures a
    rewrite as the fresh candidate it now is, and the park waiting on a
    restored checkout goes on waiting for a commit the branch no longer holds.
    """

    def test_a_refused_handoff_holds_the_branch(self) -> None:
        # The park that refused to hand review a checkout which had left the
        # approved commit, and the record of the commit it is waiting to see
        # back. Its remedy is an operator's `git checkout` -- so a rebase
        # between that and the tick which would have noticed moves the head off
        # the commit again, and the one park answered without a comment
        # becomes one nothing can answer at all.
        self._assert_skipped(
            _REFUSED_HANDOFF_ISSUE_NUMBER,
            LABEL_IMPLEMENTING,
            awaiting_human=True,
            park_reason="late_candidate_moved",
            late_approved_sha=_ACCEPTED_COMMIT,
        )

    def test_an_accepted_commit_holds_the_branch(self) -> None:
        # A `single` verdict accepts an oversized candidate and retires the
        # generation in the same breath, so between that decision and the
        # publication several ticks later the exemption is the only record
        # saying this branch carries work already adjudicated. Rebased in that
        # window the accepted commit is gone, and the gate measures the rewrite
        # as the fresh candidate it now is: past the ceiling again, and routed
        # to an adjudication a human has already answered.
        self._assert_skipped(
            _ACCEPTED_COMMIT_ISSUE_NUMBER,
            LABEL_IMPLEMENTING,
            head=_ACCEPTED_COMMIT,
            late_exempt_sha=_ACCEPTED_COMMIT,
        )

    def test_an_unreadable_head_holds_the_branch(self) -> None:
        # A checkout this process cannot ask about is not one to rewrite.
        self._assert_skipped(
            _UNREADABLE_HEAD_ISSUE_NUMBER,
            LABEL_IMPLEMENTING,
            head="",
            late_exempt_sha=_ACCEPTED_COMMIT,
        )

    def test_an_unread_measurement_holds_the_branch(self) -> None:
        # The one size refusal that leaves no record to hold the branch by:
        # the revision would not resolve, so no commit was named and nothing
        # went on the pinned comment. What the park promises is that the work
        # is still where the developer left it -- either the exact pair to
        # re-read, or a refusal to substitute anything for a pair nobody
        # froze -- and a rebase under it makes both unanswerable, leaving the
        # retry standing on the base with the commit gone.
        self._assert_skipped(
            _UNREAD_MEASUREMENT_ISSUE_NUMBER,
            LABEL_IMPLEMENTING,
            awaiting_human=True,
            park_reason=_MEASUREMENT_PARK,
        )

    def test_a_partial_reading_holds_the_branch(self) -> None:
        # A record carrying part of a group is a record something edited, and
        # the owner that notices parks the issue rather than acting on it --
        # at DISPATCH, which is after this. Held by the candidate alone, a
        # reading whose commit a hand edit took is rebased and force-pushed
        # while it still names the base it was measured from, the ceiling, the
        # count, and the publication it was entered on. Every one of those is
        # what the retry is bound to, and the park would land on a checkout
        # standing somewhere else.
        for offset, record in enumerate(_PARTIAL_READINGS):
            with self.subTest(record=record):
                self._assert_skipped(
                    _PARTIAL_RECORD_ISSUE_NUMBER + offset,
                    LABEL_IMPLEMENTING,
                    awaiting_human=False,
                    park_reason=None,
                    **record,
                )

    def test_a_lone_lease_holds_the_branch(self) -> None:
        # The approval read from its other end. The pair is written together
        # and means nothing apart, so a lease with no commit beside it names
        # the head a push was owed against and nothing else -- and a rebase
        # under it leaves the human repairing the comment with a branch that
        # has moved too.
        self._assert_skipped(
            _LONE_LEASE_ISSUE_NUMBER,
            LABEL_IMPLEMENTING,
            awaiting_human=False,
            park_reason=None,
            late_approved_lease=_ACCEPTED_COMMIT,
        )

    def test_a_published_commit_holds_the_branch(self) -> None:
        # The window a relabel that did not land leaves: the branch is pushed
        # and its pull request open, the issue is still implementing, and the
        # record naming what went out is what has the next tick finish the
        # handoff rather than re-decide a published branch. Rebased under it
        # that record covers a commit the checkout no longer holds, and the
        # gate reads the rewrite as work nobody has ruled on.
        self._assert_skipped(
            _PUBLISHED_COMMIT_ISSUE_NUMBER,
            LABEL_IMPLEMENTING,
            head=_ACCEPTED_COMMIT,
            implementing_published_sha=_ACCEPTED_COMMIT,
        )


class FalseyLateRecordSkipTest(_SkipCase, unittest.TestCase):
    """A late key CARRIED at a value that reads false still holds the branch.

    The key being there is the claim rather than what it holds, which is how
    the guard that refuses a partial record reads it. A count of `0` is what a
    candidate adding nothing really measures to, a ceiling of `0` is one an
    operator can configure, and a marker reading `false` is what a hand edit
    leaves -- so a freeze asking for truth rebases every one of them a tick
    before the dispatcher parks the issue.
    """

    def test_a_falsey_member_holds_the_branch(self) -> None:
        for offset, record in enumerate(_FALSEY_READINGS):
            with self.subTest(record=record):
                self._assert_skipped(
                    _FALSEY_RECORD_ISSUE_NUMBER + offset,
                    LABEL_IMPLEMENTING,
                    awaiting_human=False,
                    park_reason=None,
                    **record,
                )


class ReportInFlightSkipTest(_SkipCase, unittest.TestCase):
    """A developer report recorded and not yet settled holds the branch until it settles.

    A rewrite inside that window either binds the report to a head no
    developer read or leaves a transaction about a head the pull request has
    left, which the hold can only park on. The binding and the settlement
    write each record `null`, so the freeze ends with the publication.
    """

    def test_a_report_in_flight_holds_the_branch(self) -> None:
        for offset, record in enumerate(_REPORTS_IN_FLIGHT):
            with self.subTest(record=record):
                self._assert_skipped(
                    _REPORT_IN_FLIGHT_ISSUE_NUMBER + offset,
                    LABEL_VALIDATING,
                    awaiting_human=False,
                    park_reason=None,
                    **record,
                )

    def test_a_settled_report_syncs_again(self) -> None:
        self._assert_synced(
            _REPORT_SETTLED_ISSUE_NUMBER,
            developer_report_delivery=None,
            developer_report_pending=None,
        )


class LateRecordBaseRefreshEndTest(_SkipCase, unittest.TestCase):
    """What ends each of those freezes, so none of them is permanent.

    None of these records is dropped by the step that acts on it: a park's
    reason outlives the flag beside it, an exemption is never cleared at all,
    and a publication record is overwritten rather than spent. Read on their
    own they would take a branch out of the base refresh for the rest of its
    issue's life -- so each is read against something that does end: the flag
    the park was taken under, the commit the checkout is standing on, and the
    label of the stage that still has to act on it.
    """

    def test_an_answered_measurement_syncs_again(self) -> None:
        # And it ends the way every park does. The reason outlives the flag
        # beside it -- the retry reads it to know which park it is answering
        # -- so a spent one left behind would freeze a branch nothing is
        # waiting on for the rest of the issue's life.
        self._assert_synced(
            _ANSWERED_MEASUREMENT_ISSUE_NUMBER,
            awaiting_human=False,
            park_reason=_MEASUREMENT_PARK,
        )

    def test_a_handed_on_publication_syncs_again(self) -> None:
        # And past the handoff it stops holding anything. The commit is on the
        # remote with a pull request over it, and keeping THAT in step with
        # base is the PR-aware sync's own job -- the only route that can move
        # it without stranding the SHA a reviewer is looking at.
        self._assert_synced(
            _HANDED_ON_ISSUE_NUMBER,
            head=_ACCEPTED_COMMIT,
            label=LABEL_VALIDATING,
            implementing_published_sha=_ACCEPTED_COMMIT,
        )

    def test_a_published_exemption_syncs_again(self) -> None:
        # The same for the record that is never cleared at all. An exemption
        # outlives the publication it licensed, so read on its own it would
        # take every issue that ever earned a verdict out of the base refresh
        # for the rest of its life -- validating, documenting, review, and
        # fixing included, none of which re-measures anything.
        self._assert_synced(
            _PUBLISHED_EXEMPTION_ISSUE_NUMBER,
            head=_ACCEPTED_COMMIT,
            label=LABEL_VALIDATING,
            late_exempt_sha=_ACCEPTED_COMMIT,
        )

    def test_a_stale_exemption_syncs_again(self) -> None:
        # The other half of that freeze, and the reason it reads the checkout
        # rather than the record: an exemption is never cleared -- a moved head
        # is what invalidates it -- so freezing on its presence alone would take
        # every issue that ever earned a verdict out of the base refresh for the
        # rest of its life. The developer has committed since, what the gate
        # will measure is that new work, and there is nothing here left to
        # protect.
        self._assert_synced(
            _STALE_EXEMPTION_ISSUE_NUMBER,
            head=_HEAD_PAST_THE_EXEMPTION,
            late_exempt_sha=_ACCEPTED_COMMIT,
        )


if __name__ == "__main__":
    unittest.main()
