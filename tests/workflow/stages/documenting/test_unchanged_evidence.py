# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification evidence an approval rests on, behind a docs pass that changed nothing.

A clean `DOCS: NO_CHANGE` leaves the pull request on the head the approval
moved here, so the evidence may go on answering for it -- once it is proved
whole again behind the pass: an equivalent-tree squash's carry keeps its
tested commit, its artifact, and the report it answers to exactly as they
were, and the issue reaches `in_review` with the docs agent the only launch.

The pass is long enough for anything that evidence answers for to move: a
push, the tree, the verification context, the requirements, the report, the
artifact deleted or edited, a review subject no longer recorded. Each of those
is the evidence proved to no longer answer: no verdict, no notice, no
`in_review` -- the evidence is invalidated into history with the approval it
answers for, and the issue goes back to `validating` behind a write that
landed. A hand edit of the pinned comment while the pass is out refuses the
completion over the records it moved, and the ticks behind hand back and
retire what no longer stands, or run the pass again over what the comment
then carries. A reading nobody could take holds everything,
and the pass runs again once it answers. Evidence that was never recorded,
whose record will not read, or that the approval names but the comment does
not carry never counts as passing: the issue goes back.
"""
from __future__ import annotations

import unittest
from copy import copy
from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.verification_evidence import VerifiedCommand
from orchestrator.workflow.engine import (
    comments as _comments,
    final_docs_records as _final_docs,
    report_settlement_state as _report_settlement,
    review_subjects as _review_subjects,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.validating import review_coverage as _review_coverage, state as _validating_state
from tests.workflow import approved_squash as _approved_squash, review_world as _world
from tests.workflow.fixtures import LABEL_DOCUMENTING, LABEL_IN_REVIEW, LABEL_VALIDATING, _agent
from tests.workflow.stages.documenting import (
    documenting_completion_test_support as completion,
    documenting_evidence_test_support as evidence,
    documenting_scenario_test_support as scenario,
)

HEAD = _world.HEAD

SQUASHED = _approved_squash.SQUASHED

RUN_AGENT = _world.RUN_AGENT

# The labels a docs pass that changed nothing moves the issue through, and
# the ones a pass whose evidence no longer answers does.
_HANDED_ON = (LABEL_DOCUMENTING, LABEL_IN_REVIEW)

_HANDED_BACK = (LABEL_DOCUMENTING, LABEL_VALIDATING)

# The squash's carry current over the reviewer's run it superseded, and that
# carry invalidated behind it.
_CARRIED = (None, (HEAD, SQUASHED), ("superseded",))

_INVALIDATED = (None, None, ("superseded", "invalidated"))

# The reviewer's run on the head itself, current, with nothing behind it.
_RUN_ON_THE_HEAD = (None, (HEAD, HEAD), ())

# The client request an artifact is re-read through.
_ARTIFACT_REREAD = "reread_verification_artifact"

# The client request the completion's watermark walk reads the pull request's
# thread through, the last of the requests that walk makes.
_WALKS_THE_THREAD = "pr_conversation_comments_after"


class _Behind:
    """Each read of the issue a snapshot, as GitHub serves one, and `move` made on the case behind one request.

    The request is the client's re-read of an artifact unless `owner` and
    `request` name another: the client's read of the pull request's thread
    that the completion's watermark walk ends on, or the approval's final
    check, read on the owner that defines it. The proof reads the issue and
    the pull request before it re-reads the artifact, so a move there lands
    behind the readings it was first measured by -- an edit behind the
    snapshot the requirements were hashed from, a merge behind the pull
    request proved open -- and one behind the final check lands behind every
    reading but the last. The walk's requests are the completion's own, so a
    move behind them lands wherever that walk is taken. Taken on the case it
    is made for; a patch made on an owner module stays in place for the rest
    of the test, so a move on one comes last.
    """

    def __init__(self, case, move, owner=None, request: str = _ARTIFACT_REREAD) -> None:
        owner = case.github if owner is None else owner
        self._case = case
        self._move = move
        self._reads = case.github.get_issue
        self._requested = getattr(owner, request)
        case.enterContext(patch.object(case.github, "get_issue", side_effect=self._snapshot))
        case.enterContext(patch.object(owner, request, side_effect=self._answers))

    def _snapshot(self, number: int):
        return copy(self._reads(number))

    def _answers(self, *asked, **named):
        answered = self._requested(*asked, **named)
        self._move(self._case)
        return answered


# What moves while the pass is out, each one thing the evidence answers for.
_MOVES = (
    ("a push", _world.pushes),
    ("another tree", evidence.EvidenceWorld.another_tree),
    ("a moved context", evidence.EvidenceWorld.moves_the_context),
    ("edited requirements", evidence.EvidenceWorld.edits_the_requirements),
    ("an edited report", evidence.EvidenceWorld.edits_the_report),
    ("a deleted artifact", evidence.EvidenceWorld.deletes_the_artifact),
    ("an edited artifact", evidence.EvidenceWorld.edits_the_artifact),
    (
        "requirements edited behind the proof's artifact read",
        partial(_Behind, move=evidence.EvidenceWorld.edits_the_requirements),
    ),
    (
        "a push behind the completion's watermark walk",
        partial(_Behind, move=_world.pushes, request=_WALKS_THE_THREAD),
    ),
    (
        "a push behind the approval's final check",
        partial(_Behind, move=_world.pushes, owner=_review_coverage, request="_approval_holds"),
    ),
)

# A reading that raises rather than answering once the pass is out: the read
# of the pull request's thread the completion's watermark walk ends on, and
# git's reading of the squashed head's tree, git not started at all.
_RAISED = (_WALKS_THE_THREAD, evidence.UNSTARTED_TREE_READ)

# A reading that stops answering while the pass is out: the pull request's
# thread, the pull request, the issue, git's reading of the squashed head's
# tree, git's lookup of what an id names, and each reading that raises.
_UNREAD = (None, "get_pr", "get_issue", evidence.TREE_READ, evidence.LOOKUP, *_RAISED)

# A command the configuration does not list.
_UNCONFIGURED = "uv run ruff check"

# The requirements baseline the settled report is held to, and a revision a
# human rewrites it to.
_BASELINE = "user_content_hash"

_ANOTHER_BASELINE = "0123abcd" * 8

# A comment id nothing on the issue or its pull request carries.
_UNPOSTED_COMMENT = 9_999_999

# What a human rewrites by hand while the pass is out that the next pass
# answers, each made over the pinned comment it is made on, beside where that
# pass hands the issue and the evidence it leaves: the reviewer's round
# recorded as one a reply bought, reaching requirements the settled report was
# never held to, and the ledger of this orchestrator's own comments naming one
# more, which leaves the requirements read as they were.
_RERUN_EDITS = (
    (
        "a round a reply bought",
        lambda _pinned: {
            _validating_state._REVIEWER_OWES_A_ROUND: _validating_state._ROUND_BOUGHT_BY_A_REPLY,
            _validating_state._ROUND_BOUGHT_THROUGH: _ANOTHER_BASELINE,
        },
        (_HANDED_BACK, _INVALIDATED),
    ),
    (
        "one more comment the ledger names",
        lambda pinned: {_comments._ORCH_COMMENT_IDS: [*pinned[_comments._ORCH_COMMENT_IDS], _UNPOSTED_COMMENT]},
        (_HANDED_ON, _CARRIED),
    ),
)

LABEL_DONE = "done"

# What current evidence a hand edit leaves no approval could rest on carries:
# a run of the configured suite that failed, and a passing run that leaves it
# out.
_UNPASSING = (
    (VerifiedCommand(_world.SUITE, 1, evidence.FAILED_OUTPUT),),
    (VerifiedCommand(_UNCONFIGURED, 0, _world.SUITE_OUTPUT),),
)


def _noted(case, asked: list, answering, *args, **kwargs):
    """The client request `answering`'s answer, its name noted in `asked` where the docs notice is already out."""
    if case.announced():
        asked.append(answering.__name__)
    return answering(*args, **kwargs)


def _retires_the_approval(state) -> bool:
    """Whether a pinned write carries the approval written null: the invalidation's own write."""
    return state.carries(evidence.APPROVED_SUBJECT) and state.get(evidence.APPROVED_SUBJECT) is None


class RetainedEvidenceTest(evidence.EvidenceWorld, unittest.TestCase):
    """A pass that changed nothing over evidence still answering for its head hands the issue on, evidence kept."""

    def test_a_squash_carry_is_kept(self) -> None:
        # The squash published an equivalent tree and carried the reviewer's
        # run onto it. The pass changes nothing, the carry is proved whole
        # again, and the issue reaches `in_review` with nothing about the
        # evidence written: the tested commit is still the approved one, the
        # artifact on the pull request is the carry's own, and the report
        # still names the commit it was written about. The completion records
        # that carry as the evidence the unchanged squash rests on, apart from
        # the approval. The docs agent is the one launch; no developer and no
        # reviewer runs.
        self.squashed()
        kept, spent = self.retained(), self.spent()

        documented = self.documents()

        self.assertEqual(documented[RUN_AGENT].call_count, 1)
        self.assertEqual(self.spent_since(spent)[0], 1)
        self.assertEqual(self.standing()[:3], (_HANDED_ON, _CARRIED, ""))
        self.assertEqual(len(self.standing()[3]), 2)
        self.assertEqual(self.retained(), kept)
        report = _report_settlement.read_current_report(self.github.read_pinned_state(self.issue))
        self.assertEqual(report.subject.source_sha, HEAD)
        self.assertEqual(
            (self.pinned()[evidence.DOCS_VERDICT], self.pinned()[evidence.CHECKED_DOCS_SHA]),
            ("no_change", SQUASHED),
        )
        self._assert_completed_over_the_carry()


    def test_no_pull_request_read_behind_the_notice(self) -> None:
        # The completion's watermark walk is taken ahead of the proof, whose
        # own reading of the pull request is then the last request anything
        # the pass writes is decided behind: once the notice is out, nothing
        # asks the pull request or its thread anything, so no push lands
        # behind a reading the handoff then acts on.
        self.squashed()
        asked: list[str] = []
        for request in ("get_pr", _WALKS_THE_THREAD):
            answering = getattr(self.github, request)
            noted = partial(_noted, self, asked, answering)
            self.enterContext(patch.object(self.github, request, side_effect=noted))

        self.documents()

        self.assertEqual(self.labels(), _HANDED_ON)
        self.assertTrue(self.announced())
        self.assertEqual(asked, [])


    def _assert_completed_over_the_carry(self) -> None:
        """The completion records the squash as the head entered and completed on, over the carry still current."""
        state = self.github.read_pinned_state(self.issue)
        final = _final_docs.read_final_docs(state)
        recorded = (final.verification, final.entry_head, final.final_head)
        self.assertEqual(recorded, (_final_docs.FinalVerification.RETAINED, SQUASHED, SQUASHED))
        self.assertTrue(final.evidence.names(_settlement.read_current_evidence(state)))

class InvalidatedEvidenceTest(evidence.EvidenceWorld, unittest.TestCase):
    """A pass over evidence that no longer answers for its head withholds the handoff and hands the issue back."""

    def test_a_move_during_the_pass_invalidates(self) -> None:
        for name, move in _MOVES:
            with self.subTest(name):
                self.setUp()
                self.squashed()

                documented = self.documents(during=move)

                self.assertEqual(documented[RUN_AGENT].call_count, 1)
                self._assert_handed_back(_INVALIDATED)

    def test_a_head_review_no_longer_recorded(self) -> None:
        # No squash: the evidence is the reviewer's run on the head itself,
        # which the opening never holds to a review subject. Retained while
        # the review it answers for is recorded; with that record gone, the
        # proof behind the pass refuses it.
        for drops in (False, True):
            with self.subTest(drops=drops):
                self.setUp()
                self.enterContext(patch.object(config, "SQUASH_ON_APPROVAL", False))
                self.tick(_world.reviewer(_world.declared_run()))
                if drops:
                    self.drops_the_record()

                self.documents()

                if drops:
                    self._assert_handed_back((None, None, ("invalidated",)))
                else:
                    self.assertEqual(self.standing()[:2], (_HANDED_ON, _RUN_ON_THE_HEAD))

    def test_unpassing_evidence_is_never_kept(self) -> None:
        # No squash, and an approval whose evidence claim is gone, which the
        # opening holds to no evidence at all. The current record and its
        # artifact are then rewritten -- in the current format, each still
        # describing the other -- to a run whose command failed, or to a
        # passing run that leaves the configured suite out: current, and
        # nothing an approval may rest on. The pass completes over neither:
        # the evidence is invalidated and the issue goes back.
        for commands in _UNPASSING:
            with self.subTest(command=commands[0].command, exit_status=commands[0].exit_status):
                self.setUp()
                self.enterContext(patch.object(config, "SQUASH_ON_APPROVAL", False))
                self.tick(_world.reviewer(_world.declared_run()))
                evidence.records_instead(self, commands)

                self.assertEqual(self.documents()[RUN_AGENT].call_count, 1)

                self._assert_handed_back((None, None, ("invalidated",)))

    def test_an_unlanded_invalidation_moves_nothing(self) -> None:
        # The invalidation's write is refused, or lands and loses its answer:
        # nothing is relabelled. The next tick's opening finds the approval
        # no longer standing -- its artifact gone, or the approval retired --
        # and hands the issue back with no second pass.
        for how, records in ((completion.REFUSED, _CARRIED), (completion.LOST, _INVALIDATED)):
            with self.subTest(how=how):
                self.setUp()
                self.squashed()
                fails = completion._FailsTheCompletion(self.github, how, carrying=_retires_the_approval)
                with patch.object(self.github, "edit_pinned_state", fails):
                    self.documents(during=evidence.EvidenceWorld.deletes_the_artifact)
                self.assertEqual(self.labels(), (LABEL_DOCUMENTING,))

                handed = self.documents()

                handed[RUN_AGENT].assert_not_called()
                self.assertEqual(self.standing()[:2], (_HANDED_BACK, records))
                self.assertFalse(self.announced())

    def _assert_handed_back(self, records: tuple) -> None:
        """Back on `validating`, the evidence as `records` reads, its approval retired, nothing announced."""
        self.assertEqual(self.standing()[:3], (_HANDED_BACK, records, ""))
        self.assertIsNone(self.pinned()[evidence.APPROVED_SUBJECT])
        self.assertIsNone(self.pinned().get(evidence.DOCS_VERDICT))
        self.assertFalse(self.announced())


class HeldEvidenceTest(evidence.EvidenceWorld, unittest.TestCase):
    """A pass whose evidence nobody could prove, or whose records a human moved, is handed on nowhere."""

    def test_an_unread_reading_holds(self) -> None:
        # A reading the proof needs stops answering while the pass is out:
        # nothing is announced, stamped, retired, or relabelled, and what the
        # run itself spent still lands. Once the reading answers, the next
        # tick runs the pass again and hands the issue on with the evidence
        # as it was.
        for request in _UNREAD:
            with self.subTest(request=request):
                self.setUp()
                self.squashed()
                kept, spent = self.retained(), self.spent()
                unanswered = evidence.Unanswered(request)

                self.documents(during=unanswered)
                unanswered.answers(self)

                self._assert_held(kept, spent)
                self.assertEqual(self.documents()[RUN_AGENT].call_count, 1)
                self.assertEqual(self.standing()[:2], (_HANDED_ON, _CARRIED))

    def test_an_antigravity_pass_held_reruns(self) -> None:
        # An Antigravity docs launch lands its launch record first, and the
        # pass that finishes drops it. Held over a reading that raised -- the
        # thread the completion's watermark walk reads, or a tree read git
        # could not start -- the run still finished: the write that holds
        # drops the record beside the run's usage and leaves the evidence as
        # it was, so once the reading answers, the next tick runs the pass
        # again rather than parking a launch whose outcome nothing recorded.
        for request in _RAISED:
            with self.subTest(request=request):
                held = self._held_on_antigravity(request)
                self.assertEqual(held, ((LABEL_DOCUMENTING,), None, (1, 1)))

                rerun = self.documents()
                parked = self.pinned().get(evidence.PARK_REASON)
                self.assertEqual((rerun[RUN_AGENT].call_count, parked), (1, None))
                self.assertEqual(self.standing()[:2], (_HANDED_ON, _CARRIED))

    def test_an_ended_pull_request_holds(self) -> None:
        # The pull request is merged while the pass is out, or behind the
        # proof's re-read of the artifact, which leaves its head where it was.
        # Nothing is announced, retired, or relabelled over it, and the next
        # tick's terminal finalizes the issue with no second pass.
        for merges in (evidence.merges, partial(_Behind, move=evidence.merges)):
            with self.subTest(behind_the_artifact_read=merges is not evidence.merges):
                self.setUp()
                self.squashed()
                kept, spent = self.retained(), self.spent()

                self.documents(during=merges)

                self._assert_held(kept, spent)
                self.documents()[RUN_AGENT].assert_not_called()
                self.assertEqual(self.labels(), (LABEL_DOCUMENTING, LABEL_DONE))

    def test_a_hand_edit_under_the_pass_stands(self) -> None:
        # A record the proof read is rewritten by hand while the pass is out:
        # the review the carry answers for goes, or the requirements baseline
        # its report is held to moves. The completion is decided on both, so
        # it is refused with nothing announced and the edit kept; the next
        # tick reads what is there and runs no second pass -- its opening
        # hands back a carry whose review no longer stands, and its drift
        # check unwinds a baseline the issue no longer reads as -- and never
        # hands the issue on.
        for record, edited in ((_review_subjects.RETURNED_SUBJECT, None), (_BASELINE, _ANOTHER_BASELINE)):
            with self.subTest(record):
                self.setUp()
                self.squashed()

                self.documents(during=partial(evidence.rewrites, edited={record: edited}))
                self.assertEqual(self.labels(), (LABEL_DOCUMENTING,))
                self.assertFalse(self.announced())
                self.assertEqual(self.pinned()[record], edited)

                self.documents()[RUN_AGENT].assert_not_called()
                self.assertNotIn(LABEL_IN_REVIEW, self.labels())
                self.assertFalse(self.announced())

    def test_a_hand_edit_the_next_pass_answers(self) -> None:
        # The proof holds the report to the requirements a round a reply
        # bought reached, where one did, and reads them without the comments
        # the ledger names as this orchestrator's own. A hand edit of either
        # while the pass is out refuses the completion over it, with nothing
        # announced or stamped and the edit kept. Nothing opening the next
        # tick reads either, so that tick runs the pass again over what the
        # comment carries: a round bought through requirements the report was
        # never held to invalidates the evidence and hands the issue back, and
        # a ledger that leaves the requirements as they were hands it on with
        # the evidence kept.
        for name, edits, handed in _RERUN_EDITS:
            with self.subTest(name):
                self.setUp()
                self.squashed()
                edited = edits(self.pinned())

                self.documents(during=partial(evidence.rewrites, edited=edited))
                self.assertEqual(self.labels(), (LABEL_DOCUMENTING,))
                self.assertFalse(self.announced())
                self.assertIsNone(self.pinned().get(evidence.DOCS_VERDICT))
                self.assertEqual({record: self.pinned()[record] for record in edited}, edited)

                self.assertEqual(self.documents()[RUN_AGENT].call_count, 1)
                self.assertEqual(self.standing()[:2], handed)

    def _held_on_antigravity(self, request: str) -> tuple:
        """An Antigravity pass held over `request` raising, which then answers: its labels, launch record, and runs."""
        self.setUp()
        self.squashed()
        self.runs_on_antigravity()
        spent = self.spent()
        unanswered = evidence.Unanswered(request)
        self.documents(during=unanswered)
        unanswered.answers(self)
        launched = self.pinned().get(evidence.LAUNCHED_DOCS_SHA)
        return self.labels(), launched, self.spent_since(spent)[:2]

    def _assert_held(self, kept: tuple, spent: tuple) -> None:
        """Still documenting, the evidence and approval as `kept`, nothing announced or stamped, one run spent."""
        self.assertEqual(self.labels(), (LABEL_DOCUMENTING,))
        self.assertEqual(self.retained(), kept)
        self.assertFalse(self.announced())
        self.assertIsNone(self.pinned().get(evidence.DOCS_VERDICT))
        self.assertEqual(self.spent_since(spent)[:2], (1, 1))


class UnprovenEvidenceTest(unittest.TestCase, scenario._FinalDocsFixture):
    """What an issue carrying no evidence anything could prove does behind a pass that changed nothing."""

    def test_unproven_evidence_never_passes(self) -> None:
        # No evidence recorded at all, or a current record that will not read
        # -- cleared, with nothing to index: the pass ran, but nothing is
        # stamped or announced, and the issue goes back. A claim on evidence
        # the comment does not carry goes back before any pass runs.
        for seeded, ran in (
            ({}, 1),
            ({evidence.CURRENT_EVIDENCE: {"receipt": "damaged"}}, 1),
            ({"review_approved_evidence": {"receipt": "gone"}}, 0),
        ):
            with self.subTest(seeded=sorted(seeded)):
                gh, issue = self._seeded(**seeded)

                self.assertEqual(self._documents(gh, issue)[RUN_AGENT].call_count, ran)
                self.assertEqual(gh.label_history, [(self.issue_number, LABEL_VALIDATING)])
                self.assertIsNone(gh.pinned_data(self.issue_number).get(evidence.CURRENT_EVIDENCE))
                self.assertIsNone(gh.pinned_data(self.issue_number).get(evidence.DOCS_VERDICT))
                self.assertEqual(gh.posted_pr_comments, [])

    def _documents(self, gh, issue) -> dict:
        """One documenting tick whose pass changed nothing, on a branch level with its remote."""
        return self._run_documenting(
            gh, issue,
            run_agent=_agent(last_message=evidence.DOCS_NO_CHANGE),
            head_shas=[HEAD, HEAD],
            branch_ahead_behind=(0, 0),
        )


if __name__ == "__main__":
    unittest.main()
