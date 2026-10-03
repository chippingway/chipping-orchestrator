# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence an approval rests on, carried across its squash only by tree equivalence.

Each case is whole dispatcher ticks on a `workflow:validating` issue whose
reviewer approves with a passing run on the head it was handed, and whose
squash publishes another commit. A squashed head carrying the tested tree,
under an unchanged context, subject, and pull request, gets a run carried
onto it -- the approval's own verify gate's where it passed whole on the
approved head, and the reviewer's where the gate ran nothing: recorded in the
squash's own handoff write and claimed by the approval, published by the next
tick's reconciliation as an artifact naming the commit that ran and the new
head as an equivalent-tree target, and only then is the label moved -- with
no second reviewer, however often the publication or the relabel has to be
retried, and on the road that finishes a squash an earlier tick began too. A
squashed head whose tree is another, or one nobody can read, or a pull
request that moved off it, gets nothing carried: the evidence is
invalidated, the handoff dropped, and the issue stays for a fresh reviewer.
So does a settled carry the relabel's retry no longer proves, and one whose
pull request moves while the retry's proof reads; a review subject replaced
while it reads holds the label for the next tick to decide, and one replaced
during the relabel itself leaves the handoff standing, so the documenting tick
hands the issue back for the carry to be proved again. A carry whose approved
subject goes while its settlement proves it is never settled over that
removal, and a carry left to a later tick takes no later review of the
squashed head in the approved one's place.
"""
from __future__ import annotations

import unittest
from functools import partial
from typing import NamedTuple
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.verification import models as _verify_models
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import review_subjects as _review_subjects
from tests.workflow.fixtures import LABEL_DOCUMENTING, LABEL_VALIDATING, _agent
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.validating import (
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
    squash_evidence_test_support as _support,
)

HEAD = _support.HEAD

SQUASHED = _support.SQUASHED

VERIFY = "_run_verify_commands"

VERIFY_COMMANDS = "VERIFY_COMMANDS"

SET_LABEL = "set_workflow_label"

PR_COMMENT = "pr_comment"

# The artifact a reviewer's run publishes on the head it was handed, and the
# one carrying that run onto the squashed head: the same commit tested and the
# same review answered, the squashed head its target.
REVIEWED = (EvidenceSource.REVIEWER_REPORTED, HEAD, HEAD, HEAD)

CARRIED = (EvidenceSource.REVIEWER_REPORTED, HEAD, SQUASHED, HEAD)

# What the approval's own verify gate printed, apart from what the reviewer
# reported, and the gate an empty configuration runs.
GATE_OUTPUT = "12 passed under the approval's gate"

_OK = _verify_models.VERIFY_STATUS_OK

_GATE_RAN_NOTHING = partial(_verify_models.VerifyResult, status=_verify_models.VERIFY_STATUS_NOT_RUN)

# A passing gate whose record proves nothing on its own, which binds nothing,
# so the reviewer's evidence is what is carried.
_GATE_BINDS_NOTHING = partial(_verify_models.VerifyResult, status=_OK)

# The approval's own gate run carried instead: this orchestrator its witness,
# the approved head the commit it ran on.
GATE_CARRIED = (EvidenceSource.ORCHESTRATOR_EXECUTED, HEAD, SQUASHED, HEAD)

# The transcript each carry publishes: the gate's own, or the reviewer's.
GATE_TRANSCRIPT = ((_world.SUITE, 0, GATE_OUTPUT),)

REVIEWER_TRANSCRIPT = ((_world.SUITE, 0, _world.SUITE_OUTPUT),)

# The request the proof of a settled carry re-reads the developer report through.
REPORT_REREAD = "reread_report_location"

# What a docs pass that changed nothing answers, and the record of the ready
# ping `in_review` takes behind it.
DOCS_NO_CHANGE = "DOCS: NO_CHANGE"

READY_PING = "ready_ping_sha"

# A dispatcher tick ahead of the one a case reads: the docs pass, changing
# nothing, handing the issue to `in_review`.
_DOCUMENTED_FIRST = ({"run_agent": _agent(last_message=DOCS_NO_CHANGE), "head_shas": (SQUASHED,)},)

# The evidence records as `SquashedRoundWorld.standing` reads them -- the
# pending and the current evidence as tested commit and target head, beside
# each history entry's retirement: the reviewer's run current, the carry owed
# beside it, the carry settled over it, and the run invalidated.
REVIEWED_RUN = (None, (HEAD, HEAD), ())

OWED_CARRY = ((HEAD, SQUASHED), (HEAD, HEAD), ())

SETTLED_CARRY = (None, (HEAD, SQUASHED), ("superseded",))

INVALIDATED_RUN = (None, None, ("invalidated",))

# Where the issue stands: the labels it moved through, those records, the
# handoff, and the artifacts. Squashed with the carry owed, the label held:
HELD = ((), OWED_CARRY, SQUASHED, (REVIEWED,))

# The carry published and settled, the label still owed over it:
RELABEL_OWED = ((), SETTLED_CARRY, SQUASHED, (REVIEWED, CARRIED))

# The carry published and settled, the label moved, and the handoff ended:
HANDED_ON = ((LABEL_DOCUMENTING,), SETTLED_CARRY, "", (REVIEWED, CARRIED))

# The same, the gate's run the carry published.
GATE_HANDED_ON = ((LABEL_DOCUMENTING,), SETTLED_CARRY, "", (REVIEWED, GATE_CARRIED))

# The squash published and its notice refused, the collapse still recorded:
ANNOUNCEMENT_OWED = ((), REVIEWED_RUN, "", (REVIEWED,))

# Nothing carried, the evidence invalidated, and the handoff dropped:
INVALIDATED = ((), INVALIDATED_RUN, "", (REVIEWED,))

# The carry settled and then refused on the relabel's retry: invalidated over
# the run it superseded, the handoff dropped, and the label never moved.
RETRY_REFUSED = ((), (None, None, ("superseded", "invalidated")), "", (REVIEWED, CARRIED))

# The carry published and refused its settlement: abandoned beside the run it
# would have superseded, the handoff dropped, and the label never moved.
SETTLEMENT_REFUSED = ((), (None, (HEAD, HEAD), ("abandoned",)), "")

# The carry settled and the label moved, the handoff left standing behind it.
MOVED_OVER = ((LABEL_DOCUMENTING,), SETTLED_CARRY, SQUASHED)

# That issue handed back and the carry proved again and refused: invalidated,
# the handoff dropped, and the label back on `validating` for a fresh reviewer.
HANDED_BACK = ((LABEL_DOCUMENTING, LABEL_VALIDATING), (None, None, ("superseded", "invalidated")), "")

# What the carried artifact says about the head it was carried onto.
EQUIVALENT_TREE = "an equivalent-tree target"

# An operator changing `VERIFY_TIMEOUT`, the approval's evidence claim gone
# from the pinned comment by hand -- removed outright, or written null -- and
# the returned review subject written null.
_MOVES_THE_CONTEXT = _support.SquashedRoundWorld.moves_the_context

_NULLS_THE_CLAIM = partial(_support.SquashedRoundWorld.drops_the_record, record=_support.APPROVED_EVIDENCE)

_DROPS_THE_SUBJECT = _support.SquashedRoundWorld.drops_the_record

_REMOVES_THE_CLAIM = partial(_NULLS_THE_CLAIM, popped=True)


class _Rewrite(NamedTuple):
    """One squash a carry follows, the configuration and gate it runs under, and what it owes and publishes.

    `gate` builds the approval's verify gate run once the configuration is in
    place; `handed_on` and `transcript` are where the issue stands once the
    label moves, and the commands the carried artifact publishes.
    """

    name: str
    count: int
    commands: tuple
    gate: object
    announced: bool
    handed_on: tuple
    transcript: tuple


def _passing_gate() -> _verify_models.VerifyResult:
    """The approval's verify gate passing whole on the approved head and tree, under the configuration now."""
    commands = tuple(config.VERIFY_COMMANDS)
    readings = {"head_before": HEAD, "head_after": HEAD, "tree_before": _world.TREE, "tree_after": _world.TREE}
    return _verify_models.VerifyResult(
        status=_OK,
        commit=HEAD,
        tree_identity=_world.TREE,
        configured_commands=commands,
        attempted_commands=tuple(
            _verify_models.VerifyCommandOutcome(command, _OK, exit_code=0, output=GATE_OUTPUT, **readings)
            for command in commands
        ),
        timeout=config.VERIFY_TIMEOUT,
        context_revision=_verify_models._context_revision(commands, config.VERIFY_TIMEOUT),
    )


# A collapse, and a one-commit branch rewritten for its subject alone, under
# the configured suite, which the approval's gate ran on the approved head --
# and a collapse under an empty `VERIFY_COMMANDS`, where the gate runs nothing
# and the reviewer's run is the only evidence there is.
_REWRITES = (
    _Rewrite(
        "a collapse", _support.COLLAPSED, (_world.SUITE,), _passing_gate,
        announced=True, handed_on=GATE_HANDED_ON, transcript=GATE_TRANSCRIPT,
    ),
    _Rewrite(
        "a subject rewrite", 1, (_world.SUITE,), _passing_gate,
        announced=False, handed_on=GATE_HANDED_ON, transcript=GATE_TRANSCRIPT,
    ),
    _Rewrite(
        "an empty configuration", _support.COLLAPSED, (), _GATE_RAN_NOTHING,
        announced=True, handed_on=HANDED_ON, transcript=REVIEWER_TRANSCRIPT,
    ),
)


def _tree_of(squashed_tree: str, _worktree, commit: str) -> str:
    """Every commit's tree is the tested one, save the squashed head's, which is `squashed_tree`."""
    return squashed_tree if commit == SQUASHED else _world.TREE


def _retries_the_relabel(case) -> None:
    """The approval's squash published, its carry settled, and the relabel behind it refused once."""
    case.approves()
    refuses = _support.RefusesTheRelabelOnce(case.github)
    case.enterContext(patch.object(case.github, SET_LABEL, refuses))
    case.later()


class CarriedEvidenceTest(_support.SquashedRoundWorld, unittest.TestCase):
    """A squash onto the tested tree carries the run, and the label moves once it is published."""

    def test_the_run_is_carried_then_the_label_moves(self) -> None:
        for rewrite in _REWRITES:
            with self.subTest(rewrite.name):
                self.setUp()
                self.enterContext(patch.object(config, VERIFY_COMMANDS, rewrite.commands))
                before = self.spent()

                approved = self.approves(
                    squash=_support.LandsTheSquash(self, count=rewrite.count), verify_result=rewrite.gate(),
                )

                self.assertEqual((self.standing(), self.claims()), (HELD, True))
                self.assertEqual(
                    (approved[VERIFY].call_count, self._announced()),
                    (1, rewrite.announced),
                )
                launched = self.later()[_world.RUN_AGENT].call_count
                self.assertEqual(
                    (launched, self.standing(), self.claims()),
                    (0, rewrite.handed_on, True),
                )
                self.assertEqual(self._carried_artifacts(), 1)
                self.assertEqual(self._carried_transcript(), rewrite.transcript)
                self.assertEqual(self.spent_since(before), (1, 1, _world.REVIEWER_TOKENS))

    def _announced(self) -> bool:
        """Whether the squash notice is on the pull request."""
        return any(_support.SQUASH_NOTICE in said.body for said in self.pull_request.issue_comments)

    def _carried_transcript(self) -> tuple:
        """The commands the latest artifact publishes, each with its exit status and output."""
        latest = _read.artifacts(self)[-1]
        return tuple((ran.command, ran.exit_status, ran.output) for ran in latest.commands)

    def _carried_artifacts(self) -> int:
        """How many comments on the pull request say they were carried onto an equivalent-tree target."""
        return sum(EQUIVALENT_TREE in said.body for said in self.pull_request.issue_comments)


class RefusedCarryTest(_support.SquashedRoundWorld, unittest.TestCase):
    """A squashed head nothing proves equivalent gets no evidence, and goes back to a fresh reviewer."""

    def test_the_evidence_is_invalidated(self) -> None:
        # Another tree, a tree nobody can read, a pull request standing past
        # the squash, and a verification context moved while the squash ran:
        # nothing is carried, the evidence about the head the pull request
        # left is invalidated, and the handoff that would have moved the label
        # over it is dropped in the same write -- so the next tick answers the
        # head with a review rather than a relabel. The approval's own verdict
        # is retired all the same.
        for name, trees, then in (
            ("another tree", partial(_tree_of, _support.OTHER_TREE), None),
            ("an unreadable tree", partial(_tree_of, ""), None),
            ("a push past the squash", partial(_tree_of, _world.TREE), _world.pushes),
            ("a moved context", partial(_tree_of, _world.TREE), _support.SquashedRoundWorld.moves_the_context),
        ):
            with self.subTest(name):
                self.setUp()
                self.enterContext(seam_patch("_tree_sha", trees))

                self.approves(squash=_support.LandsTheSquash(self, then=then), checkout_tree=None)

                self.assertEqual(
                    (self.standing(), self.pinned().get(_world.RETURNED_VERDICT)),
                    (INVALIDATED, None),
                )


    def test_a_subject_gone_in_settlement_stays_gone(self) -> None:
        # The carry is recorded, and the approved review subject goes from the
        # records while the reconciliation's settlement re-reads the developer
        # report -- on the carry's first publication, or on the retry of one
        # nobody could confirm, for the reviewer's evidence and the approval
        # gate's run alike. The settlement is composed over the comment read
        # behind its proof, which no longer carries the subject the carry
        # answers through: the removal stands, the carry is abandoned rather
        # than settled, the handoff over it is dropped, and the label never
        # moves.
        for gate, prior, carried in (
            (_GATE_BINDS_NOTHING, (), CARRIED),
            (_GATE_BINDS_NOTHING, (RefusedCarryTest._publishes_unconfirmed,), CARRIED),
            (_passing_gate, (), GATE_CARRIED),
            (_passing_gate, (RefusedCarryTest._publishes_unconfirmed,), GATE_CARRIED),
        ):
            with self.subTest(carried=carried[0], retried=bool(prior)):
                self.setUp()
                self.approves(verify_result=gate())
                for tick in prior:
                    tick(self)
                behind = _world.AnotherRoadBehind(self, REPORT_REREAD, bool, partial(
                    _support.SquashedRoundWorld.drops_the_record, record=_review_subjects.APPROVED_SUBJECT,
                ), 2)

                with patch.object(self.github, REPORT_REREAD, behind):
                    self.later()

                self.assertEqual(self.standing(), (*SETTLEMENT_REFUSED, (REVIEWED, carried)))
                self.assertIsNone(self.pinned().get(_review_subjects.APPROVED_SUBJECT))

    def test_a_later_review_is_never_carried(self) -> None:
        # The carry is left for a later tick -- held where the tail could not
        # read the pull request's thread, or behind a refused squash notice,
        # for the recovery to finish -- and meanwhile a report of the squashed
        # head settles and a reviewer is handed it and returns: a review, a
        # report, and requirements the approval was never given. The carry
        # that later tick decides takes only the approved review unchanged,
        # so it is refused: the evidence is invalidated, the handoff dropped,
        # and nothing is carried for the reconciliation to publish.
        for leaves_the_carry in (RefusedCarryTest._holds_the_carry, RefusedCarryTest._owes_the_announcement):
            with self.subTest(leaves_the_carry.__name__):
                self.setUp()
                deciding = leaves_the_carry(self)
                _support.reviews_the_squashed_head(self)

                self.later(**deciding)

                self.assertEqual(self.standing(), INVALIDATED)

    def test_an_unanswered_carry_goes_back(self) -> None:
        # The carry settles and the label moves; then what it answers for the
        # head on goes from the records -- the approval's evidence claim,
        # removed or written null, which is not taken for an approval older
        # than claims, or the review subject it was carried for -- ahead of
        # the docs pass, or once that pass handed the issue to `in_review` and
        # ahead of the ready ping. Each reader holds the approval to a carry
        # that still answers, so neither the docs pass nor the ping is taken:
        # the issue goes back to `validating`, which invalidates the carry
        # ahead of any round, and the approval with it -- its subject written
        # null, which no reader takes for an approval at all.
        for name, drops, ahead in (
            ("the claim removed, ahead of the docs pass", _REMOVES_THE_CLAIM, ()),
            ("the claim null, ahead of the docs pass", _NULLS_THE_CLAIM, ()),
            ("the review subject gone, ahead of the docs pass", _DROPS_THE_SUBJECT, ()),
            ("the claim removed, ahead of the ping", _REMOVES_THE_CLAIM, _DOCUMENTED_FIRST),
            ("the claim null, ahead of the ping", _NULLS_THE_CLAIM, _DOCUMENTED_FIRST),
            ("the review subject gone, ahead of the ping", _DROPS_THE_SUBJECT, _DOCUMENTED_FIRST),
        ):
            with self.subTest(name):
                self.setUp()
                self.approves()
                self.later()
                for options in ahead:
                    _support.dispatches(self, self.github, self.issue, SQUASHED, **options)
                drops(self)

                self.assertFalse(
                    _support.dispatches(self, self.github, self.issue, SQUASHED, head_shas=(SQUASHED,))[
                        _world.RUN_AGENT
                    ].called,
                )
                self.later()

                handed_back = (
                    self.labels()[-1],
                    self.pinned().get(READY_PING),
                    self.pinned().get(_review_subjects.APPROVED_SUBJECT, "no approval record"),
                )
                self.assertEqual(handed_back, (LABEL_VALIDATING, None, None))
                self.assertEqual(self.standing()[1:], RETRY_REFUSED[1:])

    def _holds_the_carry(self) -> dict:
        """An approval whose squash published as the thread stopped answering, its carry left to the next tick."""
        self.approves(squash=_support.LandsTheSquash(self, then=_world.stops_answering))
        self.github.report_failures.unreadable.discard(_world.PR)
        return {}

    def _owes_the_announcement(self) -> dict:
        """An approval whose squash notice was refused, its collapse -- and carry -- left for the recovery to finish."""
        with patch.object(self.github, PR_COMMENT, _support.RefusesTheNotice(self.github)):
            self.approves()
        return {"squash_result": _support.LandsTheSquash(self)}

    def _publishes_unconfirmed(self) -> None:
        """A tick whose publication of the carry nobody could confirm, held for the next."""
        self.github.report_failures.refused.add(_world.PR)
        self.later()
        self.github.report_failures.refused.discard(_world.PR)


class RetriedHandoffTest(_support.SquashedRoundWorld, unittest.TestCase):
    """A publication, a relabel, or a notice that does not land is retried by later ticks, with no second reviewer."""

    def test_an_unconfirmed_publication_is_retried(self) -> None:
        # The post goes unanswered: the reconciliation holds the tick, so no
        # handler runs and nothing moves. The next tick publishes and moves
        # the label.
        self.approves()
        self.github.report_failures.refused.add(_world.PR)

        launched = self.later()[_world.RUN_AGENT].call_count

        self.assertEqual((launched, self.standing()), (0, HELD))
        self.github.report_failures.refused.discard(_world.PR)
        self.later()
        self.assertEqual(self.standing(), HANDED_ON)
        self.assertEqual(self.spent()[0], 1)

    def test_a_refused_relabel_is_retried(self) -> None:
        # The carry settles and the relabel is refused: the handoff stands
        # over evidence that already answers for its head, and the next tick
        # moves the label without deciding or publishing anything again.
        _retries_the_relabel(self)

        self.assertEqual(self.standing(), RELABEL_OWED)
        self.later()

        self.assertEqual(self.standing(), HANDED_ON)
        self.assertEqual(self.spent()[0], 1)

    def test_a_retried_relabel_reproves_the_carry(self) -> None:
        # The carry settles and the relabel is refused; by the retry the
        # squashed head's tree no longer reads, the review subject the carry
        # answers for is gone from the records, or the verification context
        # moved. The settled carry is proved whole again before the label
        # moves, and ahead of the approval's own coverage, so none moves it:
        # the evidence is invalidated and the handoff dropped, for a fresh
        # reviewer. So it is where the approval's evidence claim is gone --
        # removed or written null -- alone or beside a moved context or a tree
        # nobody can read: a carry answers for the head only on that claim,
        # and an approval with none is not taken for one older than claims.
        for name, moves, retry in (
            ("an unreadable tree", (), {"checkout_tree": ""}),
            ("the review subject gone", (_support.SquashedRoundWorld.drops_the_record,), {}),
            ("a moved context", (_MOVES_THE_CONTEXT,), {}),
            ("the claim removed", (_REMOVES_THE_CLAIM,), {}),
            ("the claim null", (_NULLS_THE_CLAIM,), {}),
            ("the claim removed, the context moved", (_REMOVES_THE_CLAIM, _MOVES_THE_CONTEXT), {}),
            ("the claim null, the context moved", (_NULLS_THE_CLAIM, _MOVES_THE_CONTEXT), {}),
            ("the claim removed, the tree unreadable", (_REMOVES_THE_CLAIM,), {"checkout_tree": ""}),
            ("the claim null, the tree unreadable", (_NULLS_THE_CLAIM,), {"checkout_tree": ""}),
        ):
            with self.subTest(name):
                self.setUp()
                _retries_the_relabel(self)

                for move in moves:
                    move(self)
                self.later(**retry)

                self.assertEqual(self.standing(), RETRY_REFUSED)

    def test_a_push_during_the_proof_is_caught(self) -> None:
        # The carry settles and the relabel is refused; on the retry another
        # road pushes while the proof re-reads the developer report, after it
        # read the pull request. The pull request is read again behind the
        # proof, the last request ahead of the move, so the label stays: the
        # handoff is dropped, and the carry onto the head the pull request
        # left goes into history with it, for a fresh reviewer.
        _retries_the_relabel(self)
        pushes = _world.AnotherRoadBehind(self, REPORT_REREAD, lambda _location: True, _world.pushes)

        with patch.object(self.github, REPORT_REREAD, pushes):
            self.later()

        self.assertEqual(self.standing(), RETRY_REFUSED)

    def test_a_subject_moved_during_the_proof_holds(self) -> None:
        # The carry settles and the relabel is refused; on the retry a review
        # subject -- the one the latest reviewer was handed, the one the
        # reviewer that returned was handed, or the approved one -- or the
        # approval's evidence claim goes from the records while the proof
        # re-reads the developer report. The comment read last before the
        # move no longer carries what the proof was taken over, so the label
        # stays and nothing is written, and the next tick decides over what
        # the records say then: a carry its returned review, its approved
        # review, or its claim no longer stands behind is invalidated, while
        # the subject the latest reviewer was handed is not one the reviewer's
        # evidence answers for, and the label moves.
        for record, then in (
            (_review_subjects.REVIEW_SUBJECT, HANDED_ON),
            (_review_subjects.RETURNED_SUBJECT, RETRY_REFUSED),
            (_review_subjects.APPROVED_SUBJECT, RETRY_REFUSED),
            (_support.APPROVED_EVIDENCE, RETRY_REFUSED),
        ):
            with self.subTest(record):
                self.setUp()
                _retries_the_relabel(self)
                drops = partial(_support.SquashedRoundWorld.drops_the_record, record=record)
                replaced = _world.AnotherRoadBehind(self, REPORT_REREAD, bool, drops)

                with patch.object(self.github, REPORT_REREAD, replaced):
                    self.later()
                self.assertEqual(self.standing(), RELABEL_OWED)
                self.assertIsNone(self.pinned().get(record))
                self.later()

                self.assertEqual(self.standing(), then)

    def test_a_subject_gone_in_the_relabel_hands_back(self) -> None:
        # The carry settles and the label moves; during the relabel -- the one
        # that tick makes -- the review subject the carried evidence answers
        # for goes from the records: the returned one for the reviewer's
        # evidence, the one the latest reviewer was handed for the approval
        # gate's run -- or the approval's evidence claim the carry answers
        # on. The handoff is not ended over it, so the documenting
        # tick hands the issue back with no docs pass run, and validating
        # proves the carry again: refused, it is invalidated and the handoff
        # dropped, for a fresh reviewer.
        for gate, record, carried in (
            (_GATE_BINDS_NOTHING, _review_subjects.RETURNED_SUBJECT, CARRIED),
            (_passing_gate, _review_subjects.REVIEW_SUBJECT, GATE_CARRIED),
            (_GATE_BINDS_NOTHING, _support.APPROVED_EVIDENCE, CARRIED),
        ):
            with self.subTest(record):
                self.setUp()
                self.approves(verify_result=gate())
                behind = _world.AnotherRoadBehind(
                    self, SET_LABEL, bool, partial(_support.SquashedRoundWorld.drops_the_record, record=record),
                )
                with patch.object(self.github, SET_LABEL, behind):
                    self.later()
                self.assertEqual(self.standing(), (*MOVED_OVER, (REVIEWED, carried)))

                documented = _support.dispatches(self, self.github, self.issue, SQUASHED)
                self.later()

                self.assertFalse(documented[_world.RUN_AGENT].called)
                self.assertEqual(self.standing(), (*HANDED_BACK, (REVIEWED, carried)))

    def test_a_recovered_collapse_is_carried(self) -> None:
        # The squash's push lands and the notice it owes is refused, so the
        # collapse stays recorded and nothing is carried: the next tick's
        # recovery finishes the collapse, announces it, and carries the
        # evidence over the same proofs -- the reviewer's, since the run the
        # approval's gate made went with its tick and the recovery runs no
        # gate; the tick after publishes it and moves the label. One reviewer
        # in all.
        with patch.object(self.github, PR_COMMENT, _support.RefusesTheNotice(self.github)):
            self.approves(verify_result=_passing_gate())
        self.assertEqual(self.standing(), ANNOUNCEMENT_OWED)

        recovered = self.later(squash_result=_support.LandsTheSquash(self))

        self.assertEqual((self.standing(), self.claims()), (HELD, True))
        self.assertEqual(recovered[_world.RUN_AGENT].call_count, 0)
        self.later()
        self.assertEqual(self.standing(), HANDED_ON)
        self.assertEqual(self.spent()[0], 1)


if __name__ == "__main__":
    unittest.main()
