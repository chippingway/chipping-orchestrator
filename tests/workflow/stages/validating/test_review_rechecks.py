# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reviewer round writes before it spawns, and what an approval's move asks last.

The spec and the subject a reviewer is handed are on the pinned comment before
it spawns, so a round that dies mid-review still says which spec ran and what
it was shown. The move to `workflow:documenting` an approval earns is taken
only while the approval still covers the report, the requirements, and the
head standing when the move is made, and while the pinned comment still
carries the report records in hand: a report settled over the approved one as
it is read again, an issue edited or a head pushed while the approved branch
is squashed, or a baseline moved on to requirements the approval never named,
holds the move -- with nothing written over the later report -- for the next
tick to answer. So does a current report its settlement handoff no longer
describes, on every road that would reuse an approval: the settled squash
handoff, the recovery of an unfinished squash, and the ready ping.
"""

from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.github.developer_reports import content_digest
from orchestrator.workflow.engine import (
    prompt_context as _prompt_context,
    report_records as _records,
    report_settled_reading as _settled_reading,
)
from orchestrator.workflow.late_split import collapses as _collapses, handoffs as _late_handoffs
from orchestrator.workflow.stages.validating import review_report as _review_report
from tests.workflow import (
    drift_reports as _drift_world,
    fix_reports as _fix_world,
    patch_publication as _patch_publication,
    published_reports as _published_reports,
    reviewed_reports as world,
)
from tests.workflow.fixtures import (
    LABEL_DOCUMENTING,
    LABEL_VALIDATING,
    REVIEW_APPROVED_MESSAGE,
    _agent,
)

ISSUE = 1_799

PR = 17_990

RUN_AGENT = world.RUN_AGENT

HANDOFF_SHA = _late_handoffs.LATE_COLLAPSE_HANDOFF

# Where the pinned comment records the reviewer session a round ran.
LAST_REVIEWER = "last_review_session_id"

LATE_REVIEWER = "late-reviewer"

# What a squash that published a branch with nothing to collapse hands back:
# success, the head, the commits collapsed, and no error.
LANDED_SQUASH = (True, None, 0, None)

# What a developer resumed on an edit answers when it says the work, and the
# report, already cover it.
ACK_REPLY = "ACK: the report already covers the edited criteria."

DOCUMENTED = (ISSUE, LABEL_DOCUMENTING)

# A head a push lands on while the approved branch is squashed.
PUSHED_HEAD = "d0c5" * 10

# The base a squash an earlier tick began was collapsing onto.
COLLAPSE_BASE = "ba5e" * 10

# The two moments a ready ping can find the settled pair disagreeing: before
# the tick reads anything, and while GitHub answers whether it is mergeable.
BEFORE_THE_TICK = "before the tick"

WHILE_MERGING = "while merging"


class _FirstTimeThrough:
    """A step -- a spawn, a read, a squash -- during which something changes.

    The change is made the first time the step is taken and never again, since
    settling a report reads a settled report again on its own way through.
    `answer` is what the step comes back with: the result itself, or the real
    step to call through to.
    """

    def __init__(self, change, answer) -> None:
        self._changes = [change]
        self._answer = answer

    def __call__(self, *called, **options):
        if self._changes:
            self._changes.pop()()
        if callable(self._answer):
            return self._answer(*called, **options)
        return self._answer


def _unpairs(case) -> None:
    """Restate the handoff beside the current report as one revision on.

    What a hand edit, or a write that landed half, leaves: the two records a
    settlement writes together no longer describe the same report, and
    neither says which revision is the latest.
    """
    handoff = dict(case.pinned()[_records.REPORT_HANDOFF])
    world.restate(case, **{
        _records.REPORT_HANDOFF: {**handoff, "revision": handoff["revision"] + 1},
    })


class _ApprovedReports(world._ReviewedReports):
    """The approval of the first report, where each case needs to find it."""

    def _approved_and_relabelled(self) -> None:
        """Approve the first report, and put the issue back on `validating`."""
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        self.reviewed(REVIEW_APPROVED_MESSAGE)
        self.github.apply_foreign_label(self.issue, LABEL_VALIDATING)

    def _approved_and_documented(self) -> None:
        """Approve the first report, and document its head for `in_review`."""
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        self.reviewed(REVIEW_APPROVED_MESSAGE)
        self.documented()


class ReviewRecheckTest(unittest.TestCase, _ApprovedReports):
    """A round's record is durable first, and an approval's move is asked last."""

    def test_the_handed_subject_is_written_first(self) -> None:
        # The spec and the subject are on the pinned comment when the
        # reviewer spawns, so a round that dies mid-review -- here one the
        # shutdown sweep interrupts, whose tick writes nothing after it --
        # still says which spec ran and what it was shown.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        at_spawn = {}

        self._ticked(
            self._run_validating,
            MagicMock(side_effect=_FirstTimeThrough(
                lambda: at_spawn.update(self.pinned()),
                _agent(session_id=LATE_REVIEWER, interrupted=True),
            )),
            committed=False,
        )

        handed = {
            "pr": PR,
            "sha": _fix_world.PUBLISHED_HEAD,
            "requirements": self.pinned()["user_content_hash"],
            "report_revision": 2,
            "report_content": content_digest(world.FIRST_REPORT),
        }
        for written in (at_spawn, self.pinned()):
            self.assertEqual(
                (written.get("review_agent"), written.get(world.REVIEWED)),
                (config.REVIEW_AGENT_SPEC, handed),
            )
        self.assertNotEqual(self.pinned().get(LAST_REVIEWER), LATE_REVIEWER)

    def test_a_report_settled_at_handoff_is_kept(self) -> None:
        # A squash handoff whose relabel did not land, under an approval of
        # the first report, while another road settles a later report on that
        # very head as the approved one is read again at its location. The
        # label is not moved and nothing the tick holds is written over the
        # later report; the next tick drops the handoff and hands a fresh
        # reviewer the later report.
        self._approved_and_relabelled()
        world.restate(self, **{HANDOFF_SHA: self.pull_request.head.sha})
        reread = _FirstTimeThrough(
            partial(
                _published_reports.republishes_the_report,
                self.github, self.issue, world.SECOND_REPORT,
            ),
            _settled_reading.still_carries,
        )

        with patch.object(_settled_reading, "still_carries", reread):
            self.reviewed()[RUN_AGENT].assert_not_called()
        kept = (
            self.records()["current"].report_revision,
            self.github.label_history.count(DOCUMENTED),
        )
        reviewed = self.reviewed()

        self.assertEqual(kept, (3, 1))
        self.assertIn(f"> {world.SECOND_REPORT}", world.prompt(reviewed))
        self.assertIsNone(self.pinned().get(HANDOFF_SHA))

    def test_an_edit_during_squash_holds_the_move(self) -> None:
        # The issue is edited while the approved branch is squashed. The
        # rewrite is finished -- no branch is left standing mid-rewrite -- but
        # the approval was never given those requirements, so the label is not
        # moved to documenting, and the next tick hands the edit to the
        # developer rather than relabelling or spawning a reviewer.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)

        squashed = self._ticked(
            self._run_validating,
            [_agent(session_id=LATE_REVIEWER, last_message=REVIEW_APPROVED_MESSAGE)],
            committed=False,
            squash_result=_FirstTimeThrough(
                partial(_drift_world.edits, self, _drift_world.LATER_BODY),
                _patch_publication._squash_outcome(LANDED_SQUASH),
            ),
        )
        resumed = self._ticked(
            self._run_validating,
            MagicMock(side_effect=_fix_world._Runs(ACK_REPLY)),
            committed=False,
        )

        squashed["_squash_and_force_push"].assert_called_once()
        self.assertIn("edited the issue", world.prompt(resumed))
        self.assertNotIn(DOCUMENTED, self.github.label_history)

    def test_a_push_during_squash_holds_the_move(self) -> None:
        # A push lands while the approved branch is squashed. The pull request
        # no longer stands on the commit the approval's move is owed over, so
        # the label is not moved to documenting, and the next reviewer round
        # refuses the report about the head the push replaced.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)

        squashed = self._ticked(
            self._run_validating,
            [_agent(session_id=LATE_REVIEWER, last_message=REVIEW_APPROVED_MESSAGE)],
            committed=False,
            squash_result=_FirstTimeThrough(
                partial(setattr, self.pull_request.head, "sha", PUSHED_HEAD),
                _patch_publication._squash_outcome(LANDED_SQUASH),
            ),
        )

        squashed["_squash_and_force_push"].assert_called_once()
        self.assertNotIn(DOCUMENTED, self.github.label_history)
        self.assert_refused(
            self.reviewed(),
            _review_report._MOVED_COMMIT.format(
                reported=_fix_world.PUBLISHED_HEAD, head=PUSHED_HEAD,
            ),
        )

    def test_a_moved_baseline_voids_the_handoff(self) -> None:
        # The issue is edited and the drift baseline has moved on to it -- a
        # developer resumed on the edit, a reply settled -- while the approval
        # still names the revision before it. A baseline agreeing with the
        # issue says nothing about what the reviewer read, so the settled
        # handoff is not moved past a reviewer: it goes, and the report written
        # before the edit is refused for the developer to answer.
        self._approved_and_relabelled()
        world.restate(self, **{HANDOFF_SHA: self.pull_request.head.sha})
        _drift_world.edits(self, _drift_world.LATER_BODY)
        world.restate(self, user_content_hash=_prompt_context._delivered_thread(
            self.github, self.issue, self.github.read_pinned_state(self.issue),
        ).requirements_revision)

        self.assert_refused(self.reviewed(), _review_report._MOVED_REQUIREMENTS)

        self.assertEqual(
            (
                self.pinned().get(HANDOFF_SHA),
                self.github.label_history.count(DOCUMENTED),
            ),
            (None, 1),
        )


class SettledPairTest(unittest.TestCase, _ApprovedReports):
    """An approval is reused only while the settled pair it covered agrees.

    The approved report is still the current record, but the handoff that
    settled it now describes another revision. A reviewer spawn refuses that
    pair, so no road may carry the approval of it past a reviewer either.
    """

    def test_an_unpaired_pair_voids_the_handoff(self) -> None:
        # A squash handoff whose relabel did not land: the label is not moved
        # past a reviewer, the record goes, and the reviewer round refuses.
        self._approved_and_relabelled()
        world.restate(self, **{HANDOFF_SHA: self.pull_request.head.sha})
        _unpairs(self)

        self.assert_refused(self.reviewed(), _review_report._STALE)

        self.assertEqual(
            (
                self.pinned().get(HANDOFF_SHA),
                self.github.label_history.count(DOCUMENTED),
            ),
            (None, 1),
        )

    def test_an_unpaired_pair_holds_recovery(self) -> None:
        # A squash an earlier tick began and did not finish is finished -- no
        # branch may be left standing mid-rewrite -- but the label is not
        # moved past a reviewer: the next tick drops the handoff the squash
        # left, and its reviewer round refuses the pair.
        self._approved_and_relabelled()
        state = self.github.read_pinned_state(self.issue)
        _collapses.record_pending_collapse(
            state, head=_fix_world.PUBLISHED_HEAD, base_sha=COLLAPSE_BASE, count=2,
        )
        self.github.write_pinned_state(self.issue, state)
        _unpairs(self)

        recovered = self._ticked(
            self._run_validating,
            [_agent(session_id=LATE_REVIEWER, last_message=REVIEW_APPROVED_MESSAGE)],
            committed=False,
            squash_result=(True, self.pull_request.head.sha, 1, None),
        )

        recovered["_squash_and_force_push"].assert_called_once()
        self.assertEqual(self.github.label_history.count(DOCUMENTED), 1)
        self.assert_refused(self.reviewed(), _review_report._STALE)

    def test_an_unpaired_pair_pings_nobody(self) -> None:
        # Unpaired before the tick, the hand-back sends the issue back to
        # `validating`; unpaired while GitHub answers mergeability, the ping
        # is not taken and nothing is written. Either way nobody is told the
        # pull request is ready, and the next reviewer refuses the pair.
        for when, relabelled in (
            (BEFORE_THE_TICK, [(ISSUE, LABEL_VALIDATING)]), (WHILE_MERGING, []),
        ):
            with self.subTest(when):
                self._approved_and_documented()
                relabels = len(self.github.label_history)

                self._unpaired_in_review(when)

                self.assertEqual(
                    (
                        world.ready_pings(self.github),
                        self.pinned().get("ready_ping_sha"),
                        self.github.label_history[relabels:],
                    ),
                    ([], None, relabelled),
                )
                self.assert_refused(self.reviewed(), _review_report._STALE)

    def _unpaired_in_review(self, when: str) -> None:
        """One `in_review` tick, over a pair unpaired at the moment `when` names."""
        if when == BEFORE_THE_TICK:
            _unpairs(self)
            self.in_review_tick()
            return
        with patch.object(
            self.github, "pr_is_mergeable",
            _FirstTimeThrough(partial(_unpairs, self), True),
        ):
            self.in_review_tick()

if __name__ == "__main__":
    unittest.main()
