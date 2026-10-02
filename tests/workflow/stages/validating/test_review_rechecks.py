# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reviewer round writes before it spawns, what its return keeps, and what an approval's move asks last.

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

A round's return is written over what another road wrote while its subject
was resolved or while the reviewer ran -- a run it charged and folded, the
thread it read through, a notice it posted -- each kept once, however many
readings the round takes behind it. A verdict of a pull request the issue no
longer points at is not acted on.
"""

from __future__ import annotations

import itertools
import unittest
from functools import partial
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.github.developer_reports import content_digest
from orchestrator.workflow.engine import (
    comments as _comments,
    prompt_context as _prompt_context,
    report_records as _records,
    report_settled_reading as _settled_reading,
)
from orchestrator.workflow.late_split import collapses as _collapses, handoffs as _late_handoffs
from orchestrator.workflow.stages.validating import review_coverage as _review_coverage, review_report as _review_report
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
    REVIEW_CHANGES_REQUESTED_MESSAGE,
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

# What another road does while a reviewer runs beside it: it charges a run of
# its own and folds it, tokens and a cost nobody priced, and reads the thread
# through a notice it posted.
THEIR_TOKENS = 50

UNPRICED = "unknown-price"

COST_SOURCES = "issue_cost_sources"

THREAD_MARK = "last_action_comment_id"

LEDGER = "orchestrator_comment_ids"

# What an issue has spent, as the comment spells it: runs charged, runs folded,
# and tokens folded.
SPENT = ("agent_runs_used", "issue_agent_runs", "issue_total_tokens")

# A pull request the issue is pointed at in place of the one reviewed, and
# each verdict a reviewer could return about the one reviewed.
OTHER_PR = PR + 1

_VERDICT_MESSAGES = (REVIEW_APPROVED_MESSAGE, REVIEW_CHANGES_REQUESTED_MESSAGE)

# The read of the issue a subject is resolved again over, which another road's
# write can land behind.
_REQUIREMENTS_READ = (_review_coverage, "_fresh_requirements")

# When another road points the issue at another pull request -- as the seam its
# write lands behind, none being the reviewer's own run -- and how many runs of
# the reviewer that tick makes: while the reviewer runs; while the report it is
# to be handed is read, right before the reading the round is bound to, so no
# reviewer runs; and while the subject is resolved again for its verdict,
# behind the return's own reading of the comment.
_REPOINTS = (
    ("while the reviewer ran", None, 1),
    ("before the binding", (_settled_reading, "carried_text"), 0),
    ("while its subject is resolved again", _REQUIREMENTS_READ, 1),
)

# When another road's run lands beside a round, as the seam its write lands
# behind: while the reviewer runs, and while the report its subject is resolved
# from is read, right before the reading the round is bound to.
_RUNS_BESIDE = (
    ("while the reviewer ran", None),
    ("while its subject was resolved", (_settled_reading, "carried_text")),
)


class _FirstTimeThrough:
    """A step -- a spawn, a read, a squash -- during which something changes.

    The change is made the first time the step is taken past `passes` earlier
    takes -- none unless a case says so -- and never again, since settling a
    report reads a settled report again on its own way through. `answer` is
    what the step comes back with: the result itself, or the real step to call
    through to.
    """

    def __init__(self, change, answer, *, passes: int = 0) -> None:
        self._changes = [change]
        self._answer = answer
        self._passes = passes

    def __call__(self, *called, **options):
        if self._passes:
            self._passes -= 1
        elif self._changes:
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


def _runs_beside(case) -> None:
    """Another road's run beside the reviewer's, charged and folded, and the notice it posted and read through.

    The notice's id is kept as `case.theirs`.
    """
    state = case.github.read_pinned_state(case.issue)
    case.theirs = case.github.comment(case.issue, "another road's notice").id
    for spent, by in zip(SPENT, (1, 1, THEIR_TOKENS), strict=True):
        state.set(spent, state.get(spent) + by)
    state.set(COST_SOURCES, sorted({*state.get(COST_SOURCES), UNPRICED}))
    state.set(THREAD_MARK, case.theirs)
    _comments._track_orchestrator_comment(state, case.theirs)
    case.github.write_pinned_state(case.issue, state)


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

    def test_a_repoint_behind_squash_holds_the_move(self) -> None:
        # The issue is pointed at another pull request by the time the squash
        # returns -- the squash is a double here, so none of its own writes
        # lands over the repoint: the tail acts on nothing past it -- no squash
        # notice beside the evidence the reviewer declared and the approval
        # comment posted ahead of it, no seed, no write, no move to
        # documenting -- and the pointer stays as the other road left it
        # rather than written back.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        posted = len(self.github.posted_pr_comments)

        self._ticked(
            self._run_validating,
            [_agent(session_id=LATE_REVIEWER, last_message=REVIEW_APPROVED_MESSAGE)],
            committed=False,
            squash_result=_FirstTimeThrough(
                partial(world.restate, self, pr_number=OTHER_PR),
                _patch_publication._squash_outcome(LANDED_SQUASH),
            ),
        )

        self.assertNotIn(DOCUMENTED, self.github.label_history)
        self.assertEqual(
            (self.pinned()["pr_number"], len(self.github.posted_pr_comments)),
            (OTHER_PR, posted + 2),
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

class ReturnRaceTest(unittest.TestCase, _ApprovedReports):
    """A round's return, written over what another road wrote while its subject was resolved or its reviewer ran.

    Or refused off its PR.
    """

    def test_a_return_keeps_another_roads_run(self) -> None:
        # Another road charges and folds a run of its own, and reads the
        # thread through a notice it posted, while the reviewer runs or while
        # its subject is resolved, ahead of the reading the round is bound to.
        # The approval is acted on, and every write behind it -- the return's
        # own and the one behind the verify gate -- keeps both runs' charges
        # and folds, each counted once, both cost tags, the thread read as far
        # as that road read it, and its notice as the orchestrator's own.
        for window, seam in _RUNS_BESIDE:
            with self.subTest(window):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.reported_round(world.FIRST_REPORT)
                before = self.pinned()

                self._raced(partial(_runs_beside, self), REVIEW_APPROVED_MESSAGE, seam)

                self._keeps_both_runs(before)

    def test_a_repointed_verdict_is_not_acted_on(self) -> None:
        # The issue is pointed at another pull request while the reviewer
        # runs, before the reading the round is bound to, or while the subject
        # is resolved again for the verdict: the pull request reviewed still
        # stands as it was handed, but every road acting on a verdict reads the
        # pull request off the comment. Neither verdict is acted on -- nothing
        # posted or relabelled, no developer launched -- and the pointer is
        # kept as the other road left it; repointed before the binding, no
        # reviewer runs.
        for message, repoint in itertools.product(_VERDICT_MESSAGES, _REPOINTS):
            with self.subTest(repoint[0], verdict=message.splitlines()[-1]):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.reported_round(world.FIRST_REPORT)
                posted = (len(self.github.posted_comments), len(self.github.posted_pr_comments))

                mocks = self._repointed(message, repoint[1])

                self.assertEqual(
                    (
                        mocks[RUN_AGENT].call_count,
                        self.github.workflow_label(self.issue),
                        self.pinned()["pr_number"],
                        (len(self.github.posted_comments), len(self.github.posted_pr_comments)),
                    ),
                    (repoint[2], LABEL_VALIDATING, OTHER_PR, posted),
                )

    def test_a_repoint_behind_the_gate_holds_it(self) -> None:
        # An approval's verify gate passes and its subject is resolved again
        # -- behind the two readings its disposition held it to before acting
        # -- and the issue is pointed at another pull request meanwhile: the
        # comment read behind that refuses the approval -- nothing posted past
        # the evidence the reviewer declared, nothing squashed or relabelled
        # -- and keeps the pointer.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.reported_round(world.FIRST_REPORT)
        posted = len(self.github.posted_pr_comments) + 1

        self._repointed(REVIEW_APPROVED_MESSAGE, _REQUIREMENTS_READ, passes=2)

        self.assertEqual(
            (
                self.github.workflow_label(self.issue),
                self.pinned()["pr_number"],
                self.pinned().get(world.APPROVED),
                len(self.github.posted_pr_comments),
            ),
            (LABEL_VALIDATING, OTHER_PR, None, posted),
        )

    def _keeps_both_runs(self, before: dict) -> None:
        """The approval acted on, and the comment it leaves keeping another road's run beside the reviewer's, once each.

        Measured from the comment as it stood `before` the tick.
        """
        pinned = self.pinned()
        spent = [pinned[field] - before[field] for field in SPENT]
        self.assertEqual(
            (self.github.label_history[-1], pinned[LAST_REVIEWER]), (DOCUMENTED, LATE_REVIEWER),
        )
        self.assertEqual(spent, [2, 2, THEIR_TOKENS])
        self.assertEqual(
            (pinned[COST_SOURCES], pinned[THREAD_MARK]),
            (sorted({*before[COST_SOURCES], UNPRICED}), self.theirs),
        )
        ours_and_theirs = {*before[LEDGER], self.theirs}
        self.assertLessEqual(ours_and_theirs, set(pinned[LEDGER]))

    def _repointed(self, message: str, seam, *, passes: int = 0):
        """One validating tick whose reviewer returns `message`, with the issue pointed at another pull request."""
        repoints = partial(world.restate, self, pr_number=OTHER_PR)
        return self._raced(repoints, message, seam, passes=passes)

    def _raced(self, change, message: str, seam, *, passes: int = 0):
        """One validating tick whose reviewer returns `message`, with `change` made to the comment beside it.

        Made behind `seam` -- an owner and the name of the step on it -- once
        `passes` earlier calls of it have gone by, or, where there is none,
        while the reviewer runs.
        """
        reviewer = _agent(session_id=LATE_REVIEWER, last_message=message)
        if seam is None:
            return self._ticked(
                self._run_validating, MagicMock(side_effect=_FirstTimeThrough(change, reviewer)), committed=False,
            )
        owner, name = seam
        stepped = _FirstTimeThrough(change, getattr(owner, name), passes=passes)
        with patch.object(owner, name, stepped):
            return self._ticked(self._run_validating, [reviewer], committed=False)

if __name__ == "__main__":
    unittest.main()
