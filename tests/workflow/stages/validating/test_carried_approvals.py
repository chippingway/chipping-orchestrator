# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What moves an approval over carried evidence on, and what never does.

A carry answers for the head it was carried onto only on the approval's word,
so the approval is retired with it -- its subject written null, which no
reader takes for an approval at all, rather than left without a claim, which
readers would take for one recorded before approvals named evidence. Whichever
road invalidated the carry -- the arrival in `validating` of one its claim no
longer names, removed or written null, or the relabel's retry no longer
proving it, even with no room on the comment for the evidence's own history
entry -- a move onto `workflow:documenting` or `in_review` that no review
earned is refused there and handed back: no docs pass runs and no ready ping
is taken.

The readers past `validating` hold the approval to the records it answers on
across their own requests too: the approval's evidence claim removed or
written null while the docs pass re-reads the developer report, or while the
ready ping's readiness is read, refuses the move and is kept rather than
written back over.

A carry whose publication is refused on anything but a reading nobody could
take -- ahead of the post, a context moved, the squashed head's tree unread, a
push past the squash; at the reading of its own artifact, that artifact
edited; at its settlement, a context moved after the post -- is abandoned
with the approval it was recorded for, so nothing moves the label over it once
the refusal clears. A pull request nobody could read leaves it owed, and the
next tick publishes it and moves the label. So is a carry of the reviewer's
evidence whose source -- the artifact it copied its transcript from -- is
edited or deleted while it is owed: ahead of its post, behind it, or before
the retry of a post whose response was lost.

A carry of the reviewer's evidence whose record no longer names the source
it copied -- the member removed by hand -- is damage, and is dropped rather
than published with nothing holding it to that source.

A carry that could not settle for want of room on the pinned comment --
ahead of its post or behind it -- is still owed, and the move it was recorded
for waits on it: the handoff stands, nothing parks, and once the room is back
the next tick settles it and moves the label, with no second report or
reviewer.

An approval another road recorded in place of the one a carry was recorded
for, of another subject, stands wherever that carry goes: abandoned before it
settled, or invalidated in `validating` once settled.
"""
from __future__ import annotations

import unittest
from functools import partial
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.engine import (
    review_subjects as _review_subjects,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.fixtures import LABEL_DOCUMENTING, LABEL_IN_REVIEW, LABEL_VALIDATING, _agent
from tests.workflow.stages.validating import (
    approval_proof_test_support as _proof,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
    squash_evidence_test_support as _support,
)

HEAD = _support.HEAD

SQUASHED = _support.SQUASHED

# What a docs pass that changed nothing answers, the record of the ready ping
# `in_review` takes behind it, and the request a reader re-reads the developer
# report through.
DOCS_NO_CHANGE = "DOCS: NO_CHANGE"

READY_PING = "ready_ping_sha"

REPORT_REREAD = "reread_report_location"

# What the carried artifact says about the head it was carried onto.
EQUIVALENT_TREE = "an equivalent-tree target"

# The approval's evidence claim gone from the pinned comment by hand: written
# null, or removed outright.
_NULLS_THE_CLAIM = partial(_support.SquashedRoundWorld.drops_the_record, record=_support.APPROVED_EVIDENCE)

_REMOVES_THE_CLAIM = partial(_NULLS_THE_CLAIM, popped=True)

# The run options of a dispatcher tick whose agent, where one runs, is a docs
# pass that changed nothing, and a tick of them ahead of the one a case reads.
_DOCUMENTS = MappingProxyType({"run_agent": _agent(last_message=DOCS_NO_CHANGE), "head_shas": (SQUASHED,)})

_DOCUMENTED_FIRST = (_DOCUMENTS,)

# An approval another road records of another subject than the one the carry
# was recorded for.
REPLACEMENT = MappingProxyType({"pr": _world.PR, "sha": _world.OTHER_HEAD})

# A field another road fills the pinned comment to its limit with, and what an
# edit makes the reviewer's artifact report in place of the suite's output.
_FILLER = "filler"

_FAILED = "1 failed"

# The request that posts a verification artifact.
_POSTS_THE_ARTIFACT = "_post_verification_artifact"

# Where a carry whose publication was refused leaves the issue: the label
# never moved, nothing owed, the reviewer's run still current beside the carry
# abandoned, and no handoff.
_ABANDONED = ((), (None, (HEAD, HEAD), ("abandoned",)), "")

# A settled carry invalidated over the run it superseded, and no handoff.
_INVALIDATED = ((None, None, ("superseded", "invalidated")), "")

# A carry dropped as damage: the label never moved, nothing owed, the
# reviewer's run still current, no history entry, and no handoff.
_DROPPED = ((), (None, (HEAD, HEAD), ()), "")

# A carry still owed beside the reviewer's run, the handoff standing over it,
# and that carry settled with the label moved and the handoff ended.
_OWED = ((), ((HEAD, SQUASHED), (HEAD, HEAD), ()), SQUASHED)

_HANDED_ON = ((LABEL_DOCUMENTING,), (None, (HEAD, SQUASHED), ("superseded",)), "")

# The member of the pending record naming the evidence a carry copied, and
# the record a park leaves its reason in.
_COPIED_FROM = "copied_from"

_PARK_REASON = "park_reason"


class RetiredApprovalTest(_support.SquashedRoundWorld, unittest.TestCase):
    """Neither the docs pass nor the ready ping is taken over an approval whose carry was invalidated."""

    def test_a_retired_approval_is_never_moved_on(self) -> None:
        # The carry is invalidated, and then somebody moves the label on with
        # no review behind it. The stage it lands on reads the approval first
        # and finds none it may act on, so it hands the issue back to
        # `validating` with no docs pass run and no ping taken.
        for retires, label in (
            (partial(RetiredApprovalTest._unclaims_the_carry, popped=True), LABEL_DOCUMENTING),
            (partial(RetiredApprovalTest._unclaims_the_carry, popped=True), LABEL_IN_REVIEW),
            (partial(RetiredApprovalTest._unclaims_the_carry, popped=False), LABEL_DOCUMENTING),
            (partial(RetiredApprovalTest._unclaims_the_carry, popped=False), LABEL_IN_REVIEW),
            (RetiredApprovalTest._refuses_the_retried_carry, LABEL_DOCUMENTING),
            (RetiredApprovalTest._refuses_the_retried_carry, LABEL_IN_REVIEW),
            (RetiredApprovalTest._refuses_with_no_room, LABEL_DOCUMENTING),
            (RetiredApprovalTest._refuses_with_no_room, LABEL_IN_REVIEW),
        ):
            with self.subTest(retires=getattr(retires, "keywords", retires), label=label):
                self.setUp()
                retires(self)
                self.github.apply_foreign_label(self.issue, label)

                stray = _support.dispatches(self, self.github, self.issue, SQUASHED, **_DOCUMENTS)

                self.assertFalse(stray[_world.RUN_AGENT].called)
                self.assertEqual(
                    (self.github.workflow_label(self.issue), self.pinned().get(READY_PING)),
                    (LABEL_VALIDATING, None),
                )

    def _unclaims_the_carry(self, *, popped: bool) -> None:
        """A settled carry whose claim goes by hand, handed back by the docs pass and invalidated in `validating`."""
        self.approves()
        self.later()
        self.drops_the_record(_support.APPROVED_EVIDENCE, popped=popped)
        _support.dispatches(self, self.github, self.issue, SQUASHED)
        self.later()

    def _refuses_the_retried_carry(self) -> None:
        """A settled carry whose relabel is refused, and which the retry no longer proves under a moved context."""
        self.approves()
        refuses = _support.RefusesTheRelabelOnce(self.github)
        self.enterContext(patch.object(self.github, "set_workflow_label", refuses))
        self.later()
        self.moves_the_context()
        self.later()

    def _refuses_with_no_room(self) -> None:
        """A settled carry the relabel's retry no longer proves, with no room on the comment to invalidate it.

        The tree goes unread on the retry, with the comment filled to the
        limit; the room comes back after, and the tree reads again.
        """
        self.approves()
        refuses = _support.RefusesTheRelabelOnce(self.github)
        self.enterContext(patch.object(self.github, "set_workflow_label", refuses))
        self.later()
        filled = self.github.read_pinned_state(self.issue)
        filled.set(_FILLER, "")
        room = MAX_PINNED_BODY - len(pinned_state_body(filled.data))
        filled.set(_FILLER, "y" * room)
        self.github.write_pinned_state(self.issue, filled)
        self.later(checkout_tree="")
        self.drops_the_record(_FILLER, popped=True)


class MovedUnderTheReaderTest(_support.SquashedRoundWorld, unittest.TestCase):
    """A reader past `validating` refuses its move where the approval's records moved under its own requests."""

    def test_a_claim_gone_mid_read_holds_the_move(self) -> None:
        # The carry settles and the label moves. The approval's evidence
        # claim goes -- written null or removed -- while the documenting
        # stage's opening re-reads the developer report, or, once the docs
        # pass handed the issue to `in_review`, while the ready ping's
        # readiness re-reads it. The comment read behind those requests no
        # longer carries the claim the reader holds, so the docs pass is not
        # run and the issue goes back, or the ping is not taken and nothing is
        # written back over the claim.
        for drops, ahead, after in (
            (_NULLS_THE_CLAIM, (), (LABEL_VALIDATING, None, None)),
            (_REMOVES_THE_CLAIM, (), (LABEL_VALIDATING, None, "absent")),
            (_NULLS_THE_CLAIM, _DOCUMENTED_FIRST, (LABEL_IN_REVIEW, None, None)),
            (_REMOVES_THE_CLAIM, _DOCUMENTED_FIRST, (LABEL_IN_REVIEW, None, "absent")),
        ):
            with self.subTest(after=after):
                self.setUp()
                self.approves()
                self.later()
                for options in ahead:
                    _support.dispatches(self, self.github, self.issue, SQUASHED, **options)
                behind = _world.AnotherRoadBehind(self, REPORT_REREAD, bool, drops, 1 + len(ahead))

                with patch.object(self.github, REPORT_REREAD, behind):
                    self.assertFalse(
                        _support.dispatches(self, self.github, self.issue, SQUASHED, **_DOCUMENTS)[
                            _world.RUN_AGENT
                        ].called,
                    )
                self.assertEqual(
                    (
                        self.github.workflow_label(self.issue),
                        self.pinned().get(READY_PING),
                        self.pinned().get(_support.APPROVED_EVIDENCE, "absent"),
                    ),
                    after,
                )

    def test_a_replacement_approval_is_kept(self) -> None:
        # The carry is recorded, and while its settlement re-reads the
        # developer report another road puts an approval of another subject
        # in place of the one the carry was recorded for. The settlement is
        # refused and the carry abandoned, but the approval retired with a
        # carry is only its own: the replacement stands as written.
        self.approves()
        replaces = _world.AnotherRoadBehind(self, REPORT_REREAD, bool, _replaces_the_approval, 2)

        with patch.object(self.github, REPORT_REREAD, replaces):
            self.later()

        self.assertEqual(self.standing()[:2], _ABANDONED[:2])
        self.assertEqual(self.pinned().get(_review_subjects.APPROVED_SUBJECT), dict(REPLACEMENT))

    def test_a_replacement_outlives_a_settled_carry(self) -> None:
        # The carry settles and the label moves. Another road then puts an
        # approval of another subject in place of the one the carry was
        # recorded for, and the issue comes back to `validating`, which
        # invalidates the carry its approval no longer covers -- and leaves
        # the replacement as written, since only the approval the carry was
        # recorded for is the carry's to retire.
        self.approves()
        self.later()
        _replaces_the_approval(self)
        self.github.apply_foreign_label(self.issue, LABEL_VALIDATING)

        self.later()

        self.assertEqual(self.standing()[1:3], _INVALIDATED)
        self.assertEqual(self.pinned().get(_review_subjects.APPROVED_SUBJECT), dict(REPLACEMENT))


def _replaces_the_approval(case) -> None:
    """Another road's approval of another subject put in place of the one on the comment."""
    state = case.github.read_pinned_state(case.issue)
    state.set(_review_subjects.APPROVED_SUBJECT, dict(REPLACEMENT))
    case.github.write_pinned_state(case.issue, state)


def _rewrites_the_source(case, said: str, saying: str) -> None:
    """A human editing the artifact an owed carry copied -- the current evidence's -- to say `saying` for `said`."""
    current = _settlement.read_current_evidence(case.github.read_pinned_state(case.issue))
    thread = case.pull_request.issue_comments
    source = next(posted for posted in thread if posted.id == current.comment_id)
    source.body = source.body.replace(said, saying)


# That artifact edited to report a failure, and the edit undone.
_EDITS_THE_SOURCE = partial(_rewrites_the_source, said=_world.SUITE_OUTPUT, saying=_FAILED)

_PUTS_BACK_THE_SOURCE = partial(_rewrites_the_source, said=_FAILED, saying=_world.SUITE_OUTPUT)


class RefusedPublicationTest(_support.SquashedRoundWorld, unittest.TestCase):
    """A carry refused publication outright is abandoned with its approval; one nobody could read is retried."""

    def test_only_an_unread_publication_is_retried(self) -> None:
        # The carry is recorded and its publication is refused: under a moved
        # context on a tick only the reconciliation ran -- the context put
        # back before the next, on a comment filled to its limit or not --
        # over a squashed tree nobody can read, past a push, at its own artifact found edited under its receipt on the
        # retry of a post whose response was lost -- the edit undone before
        # the next tick -- or at its settlement, under a context moved behind
        # the post and put back before the next tick. Each abandons the carry
        # and retires the approval, so the next tick does not move the label
        # over it. A pull request nobody
        # could read only holds the publication, which the next tick makes,
        # and then moves the label.
        for refuses, then, retired in (
            (RefusedPublicationTest._refuses_under_a_moved_context, _ABANDONED, True),
            (RefusedPublicationTest._refuses_an_unread_tree, _ABANDONED, True),
            (_world.pushes, _ABANDONED, True),
            (RefusedPublicationTest._refuses_on_a_full_comment, _ABANDONED, True),
            (RefusedPublicationTest._refuses_an_edited_artifact, _ABANDONED, True),
            (RefusedPublicationTest._refuses_a_settlement_under_a_moved_context, _ABANDONED, True),
            (RefusedPublicationTest._holds_an_unread_pull_request, _HANDED_ON, False),
        ):
            with self.subTest(refuses.__name__):
                self.setUp()
                self.approves()
                refuses(self)

                self.later()

                self.assertEqual(self.standing()[:3], then)
                self.assertEqual(self.pinned().get(_review_subjects.APPROVED_SUBJECT) is None, retired)

    def _refuses_under_a_moved_context(self) -> None:
        """A tick on which only the reconciliation ran, under a moved context, which is then put back."""
        timeout = config.VERIFY_TIMEOUT
        self.moves_the_context()
        self._run(lambda: _world.reconciles(self), run_agent=[], fetched_branch_tip=SQUASHED)
        self.enterContext(patch.object(config, "VERIFY_TIMEOUT", timeout))

    def _refuses_an_unread_tree(self) -> None:
        """A tick on which the squashed head's tree reads as nothing."""
        self.later(checkout_tree="")

    def _refuses_on_a_full_comment(self) -> None:
        """A tick only the reconciliation ran, under a moved context, on a full comment; both put back after."""
        timeout = config.VERIFY_TIMEOUT
        filled = self.github.read_pinned_state(self.issue)
        filled.set(_FILLER, "")
        room = MAX_PINNED_BODY - len(pinned_state_body(filled.data))
        filled.set(_FILLER, "y" * room)
        self.github.write_pinned_state(self.issue, filled)
        self.moves_the_context()
        self._run(lambda: _world.reconciles(self), run_agent=[], fetched_branch_tip=SQUASHED)
        self.drops_the_record(_FILLER, popped=True)
        self.enterContext(patch.object(config, "VERIFY_TIMEOUT", timeout))

    def _refuses_an_edited_artifact(self) -> None:
        """A post whose response was lost, its artifact edited under its receipt before the retry, then put back."""
        self.github.report_failures.lost.add(_world.PR)
        self.later()
        self.github.report_failures.lost.discard(_world.PR)
        landed = next(said for said in self.pull_request.issue_comments if EQUIVALENT_TREE in said.body)
        posted = landed.body
        landed.body = posted.replace(_world.SUITE_OUTPUT, "1 failed")
        self.later()
        landed.body = posted

    def _refuses_a_settlement_under_a_moved_context(self) -> None:
        """A tick whose context moves behind the post, ahead of the settlement, and is put back after it."""
        timeout = config.VERIFY_TIMEOUT
        moves = _world.AnotherRoadBehind(
            self, "_post_verification_artifact", bool, _support.SquashedRoundWorld.moves_the_context,
        )
        with patch.object(self.github, "_post_verification_artifact", moves):
            self.later()
        self.enterContext(patch.object(config, "VERIFY_TIMEOUT", timeout))

    def _holds_an_unread_pull_request(self) -> None:
        """A tick on which the pull request's thread does not answer."""
        self.github.report_failures.unreadable.add(_world.PR)
        self.later()
        self.github.report_failures.unreadable.discard(_world.PR)


class CopiedSourceTest(_support.SquashedRoundWorld, unittest.TestCase):
    """A carry of the reviewer's evidence is held to the artifact it copied until it settles."""

    def test_a_moved_source_abandons_the_carry(self) -> None:
        # The squash carries the reviewer's evidence, copying the transcript
        # its artifact carries -- under an empty `VERIFY_COMMANDS`, or a gate
        # whose run binds nothing. That artifact is edited ahead of the
        # carry's post, or behind it ahead of the settlement, or edited or
        # deleted before the retry of a post whose response was lost. Each
        # refuses the carry, which is abandoned with its approval: the label
        # never moves, an edit undone before the next tick moves nothing, and
        # no second reviewer runs.
        for configured, moves in (
            ((), CopiedSourceTest._edits_ahead_of_the_post),
            ((), CopiedSourceTest._edits_behind_the_post),
            ((), CopiedSourceTest._edits_before_the_retry),
            ((), CopiedSourceTest._deletes_before_the_retry),
            (None, CopiedSourceTest._edits_ahead_of_the_post),
            (None, CopiedSourceTest._edits_before_the_retry),
        ):
            with self.subTest(configured=configured, moves=moves.__name__):
                self.setUp()
                if configured is not None:
                    self.enterContext(patch.object(config, "VERIFY_COMMANDS", configured))
                self.approves()
                moves(self)

                self.later()

                approval = self.pinned().get(_review_subjects.APPROVED_SUBJECT)
                self.assertEqual(self.standing()[:3], _ABANDONED)
                self.assertEqual((approval, self.spent()[0]), (None, 1))

    def test_a_carry_naming_no_source_is_dropped(self) -> None:
        # The carry's record loses the source it copied -- the member removed
        # by hand, ahead of its post or ahead of the retry of a post whose
        # response was lost -- and that source is then edited, or deleted
        # before the retry. A reviewer's account carried to another head is
        # only ever such a copy, so the record reads as damage and is dropped
        # rather than published with nothing to hold it to: the label never
        # moves, the handoff goes, and no second reviewer runs.
        for retried, moves in (
            (False, _EDITS_THE_SOURCE),
            (True, _EDITS_THE_SOURCE),
            (True, _proof.deletes_the_artifact),
        ):
            with self.subTest(retried=retried, deleted=moves is _proof.deletes_the_artifact):
                self.setUp()
                self.approves()
                if retried:
                    self._loses_the_post()
                pinned = self.github.read_pinned_state(self.issue)
                pinned.get(_records.PENDING_EVIDENCE).pop(_COPIED_FROM)
                self.github.write_pinned_state(self.issue, pinned)
                moves(self)

                self.later()

                self.assertEqual(self.standing()[:3], _DROPPED)
                self.assertEqual(self.spent()[0], 1)

    def _edits_ahead_of_the_post(self) -> None:
        """A tick that finds the source edited ahead of the carry's post; the edit undone after it."""
        _EDITS_THE_SOURCE(self)
        self.later()
        _PUTS_BACK_THE_SOURCE(self)

    def _edits_behind_the_post(self) -> None:
        """A tick whose source is edited behind the carry's post, ahead of its settlement; undone after it."""
        edits = _world.AnotherRoadBehind(self, _POSTS_THE_ARTIFACT, bool, _EDITS_THE_SOURCE)
        with patch.object(self.github, _POSTS_THE_ARTIFACT, edits):
            self.later()
        _PUTS_BACK_THE_SOURCE(self)

    def _edits_before_the_retry(self) -> None:
        """A post whose response was lost, and the source edited before the retry; undone after it."""
        self._loses_the_post()
        _EDITS_THE_SOURCE(self)
        self.later()
        _PUTS_BACK_THE_SOURCE(self)

    def _deletes_before_the_retry(self) -> None:
        """A post whose response was lost, and the source deleted before the retry."""
        self._loses_the_post()
        _proof.deletes_the_artifact(self)
        self.later()

    def _loses_the_post(self) -> None:
        """A tick whose post of the carry lands and whose response is lost, held for the next."""
        self.github.report_failures.lost.add(_world.PR)
        self.later()
        self.github.report_failures.lost.discard(_world.PR)


class OwedCarryTest(_support.SquashedRoundWorld, unittest.TestCase):
    """A carry that could not settle for want of room holds the move, and settles once the room is back."""

    def test_a_full_comment_holds_the_move(self) -> None:
        # The carry is recorded, and another road fills the pinned comment to
        # its limit -- ahead of the tick that would post it, or behind that
        # post, ahead of its settlement. The carry cannot settle and stays
        # owed, so the move waits on it: the handoff stands, nothing parks,
        # and no agent runs. Once the room is back the next tick settles the
        # carry and moves the label, still one reviewer and the same report.
        for fills in (OwedCarryTest._fills_ahead_of_the_post, OwedCarryTest._fills_behind_the_post):
            with self.subTest(fills.__name__):
                self.setUp()
                self.approves()
                report = _read.current_report_revision(self)
                launched = fills(self)[_world.RUN_AGENT].call_count
                parked = self.pinned().get(_PARK_REASON)
                self.assertEqual(self.standing()[:3], _OWED)
                self.assertEqual((parked, launched), (None, 0))
                self.drops_the_record(_FILLER, popped=True)

                launched = self.later()[_world.RUN_AGENT].call_count

                self.assertEqual(self.standing()[:3], _HANDED_ON)
                self.assertEqual((launched, self.spent()[0]), (0, 1))
                self.assertEqual(_read.current_report_revision(self), report)

    def _fills_ahead_of_the_post(self) -> dict:
        """A tick whose comment another road filled ahead of the carry's post."""
        self._fills_the_comment()
        return self.later()

    def _fills_behind_the_post(self) -> dict:
        """A tick whose comment another road fills behind the carry's post, ahead of its settlement."""
        fills = _world.AnotherRoadBehind(self, _POSTS_THE_ARTIFACT, bool, OwedCarryTest._fills_the_comment)
        with patch.object(self.github, _POSTS_THE_ARTIFACT, fills):
            return self.later()

    def _fills_the_comment(self) -> None:
        """Another road filling the pinned comment to its limit with a field of its own."""
        filling = self.github.read_pinned_state(self.issue)
        filling.set(_FILLER, "")
        room = MAX_PINNED_BODY - len(pinned_state_body(filling.data))
        filling.set(_FILLER, "y" * room)
        self.github.write_pinned_state(self.issue, filling)


if __name__ == "__main__":
    unittest.main()
