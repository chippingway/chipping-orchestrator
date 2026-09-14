# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A record that claims a post-publication reading it cannot produce.

Every field in this domain is read fail-closed, and ahead of the HANDLER that
is only half an answer: a publication group missing one member parses as no
group and an approval missing its lease parses as no approval, so both of the
questions the reconciliation asks answer "nothing owed" and the stage runs
over a claim nothing can check.

What these pin down is that it does not. A reviewer spawned over a pull
request nobody can say received the work, a bounce relabelling on a candidate
nobody measured, a docs pass committing on top of either -- none of them may
follow a claim the record cannot make whole.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow import state as _workflow_state
from orchestrator.workflow.stages.implementing import late_claims as _claims
from tests.workflow.stages.fixing import (
    fixing_test_support as fixing,
    published_gate_support as support,
)
from tests.workflow.stages.fixing.test_late_dispatch import (
    _FrozenPairMixin,
)

ISSUE = fixing.ISSUE
AWAITING_HUMAN = fixing.AWAITING_HUMAN
PARK_REASON = fixing.PARK_REASON
PARK_MEASUREMENT_FAILED = support.PARK_MEASUREMENT_FAILED
MEASURED_CANDIDATE_SHA = support.MEASURED_CANDIDATE_SHA
PUSH_BRANCH = fixing.PUSH_BRANCH
COUNT_ADDED_LINES = support.COUNT_ADDED_LINES
UNDER_THE_CEILING = support.UNDER_THE_CEILING

KEY_POST_PUBLICATION = "late_post_publication"
KEY_SOURCE_STAGE = "late_source_stage"
KEY_PUBLISHED_PR = "late_published_pr_number"
KEY_PUBLISHED_SHA = "late_published_sha"
KEY_APPROVED_SHA = "late_approved_sha"
KEY_APPROVED_LEASE = "late_approved_lease"
KEY_CANDIDATE_SHA = "late_candidate_sha"
KEY_BASE_SHA = "late_base_sha"
KEY_ADDITIONS = "late_additions"
KEY_THRESHOLD = "late_threshold"
KEY_PHASE = "late_phase"
KEY_SPENDS = "late_spends"
KEY_CYCLE_ID = "late_cycle_id"
KEY_GENERATION = "late_generation"
KEY_ROOT_ISSUE = "late_root_issue"
KEY_CURRENT_ISSUE = "late_current_issue"

# The note a settled transfer keeps until the record it owes the sinks is out.
KEY_REWRITE_PROOF = "late_rewrite_proof"

# The one stage with an edge to the adjudication that this owner may NOT read
# an approval on: its push opens the pull request, so the approval it writes
# carries no head to be pinned against.
IMPLEMENTING = _workflow_state.WorkflowLabel.IMPLEMENTING

# Three labels with an edge to the adjudication and no pull request to publish
# onto, which is what tells the general graph from the exact predicate.
READY = _workflow_state.WorkflowLabel.READY
BLOCKED = _workflow_state.WorkflowLabel.BLOCKED
UMBRELLA = _workflow_state.WorkflowLabel.UMBRELLA

# Values that are ON the comment and are nothing this domain will type, which
# is the damage a hand edit or an older binary leaves behind rather than an
# absence.
NOT_A_COMMIT = "nope"
NOT_A_COUNT = -1
NOT_A_FLAG = "yes"
NOT_A_PHASE = "halfway"

# The half of the pair a case is not about, left as a whole debt carries it.
_WHOLE = object()

# The prefix every field one generation owns is spelled with. Dropping them
# all is what the write that approves a small candidate does -- it retires the
# record in the same breath -- so an approval left standing is the ONLY late
# field a crash past that write leaves behind.
_LATE_PREFIX = "late_"


class DamagedPublicationDispatchTest(unittest.TestCase, _FrozenPairMixin):
    """A marked publication group that cannot name all three members."""

    def test_a_partial_group_stops_the_stage(self) -> None:
        # None of the three can be worked out from anywhere else: the label it
        # names has been replaced, the pull request is not the plan one beside
        # it, and the head is a commit the branch has moved off. Parsed, the
        # group vanishes and the issue reads as one with nothing owed.
        for missing in (KEY_SOURCE_STAGE, KEY_PUBLISHED_PR, KEY_PUBLISHED_SHA):
            with self.subTest(missing=missing):
                github = self._damaged(**{missing: None})

                dispatched, mocks = self._routed(github)

                self._assert_refused(github, dispatched, mocks)

    def test_a_group_without_its_marker_stops(self) -> None:
        # The marker is a MEMBER of the group rather than the question asked
        # of it, and the group goes down in one write. Read only where the
        # marker is there, a comment still naming the stage, the pull request,
        # and the head reads back as an entry taken BEFORE publication --
        # nothing frozen, nothing owed -- and the bounce below relabels to
        # `validating` over a candidate nobody measured and nobody pushed. So
        # the group is asked from either end.
        github = self._damaged(**{KEY_POST_PUBLICATION: None})

        unmarked, unmarked_mocks = self._routed(github)

        self._assert_refused(github, unmarked, unmarked_mocks)

    def test_a_malformed_member_stops_the_stage(self) -> None:
        # Present and unusable is the same claim as absent, and the commonest
        # way to reach it: a hand-edited comment leaves a value the parse
        # rejects rather than a key it never finds.
        github = self._damaged(**{KEY_PUBLISHED_SHA: NOT_A_COMMIT})

        dispatched, mocks = self._routed(github)

        self._assert_refused(github, dispatched, mocks)

    def test_a_repeated_refusal_says_so_once(self) -> None:
        # Nothing this process can repair is behind it, so a fresh notice
        # every poll would be a mention nobody can answer any faster.
        github = self._damaged(**{KEY_SOURCE_STAGE: None})
        self._routed(github)
        posted = len(github.get_issue(ISSUE).comments)

        self._routed(github)

        self.assertEqual(len(github.get_issue(ISSUE).comments), posted)

    def _damaged(self, **overrides):
        """The pinned comment a hand edit or an older binary left behind."""
        github = self._frozen()[0]
        pinned = github.pinned_data(ISSUE)
        pinned.update(overrides)
        github.seed_state(ISSUE, **pinned)
        return github

    def _routed(self, github):
        """Route the tick the dispatcher takes over this issue."""
        return self._route(github, github.get_issue(ISSUE))

    def _assert_refused(self, github, dispatched, mocks) -> None:
        """Nothing run, nothing pushed, and a human asked for."""
        dispatched.assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        pinned = github.pinned_data(ISSUE)
        self.assertTrue(pinned[AWAITING_HUMAN])
        self.assertEqual(pinned[PARK_REASON], PARK_MEASUREMENT_FAILED)
        self.assertEqual(github.label_history, [])


class DamagedEvidenceDispatchTest(unittest.TestCase, _FrozenPairMixin):
    """Frozen evidence the pinned comment carries and cannot produce.

    Every reader in this domain answers "absent" for a value it will not type,
    and absent is what an issue that froze nothing answers too. So a damaged
    member does not merely lose itself: the reconciliation finds nothing owed
    and the stage runs, the freeze re-derives the half it cannot see from a
    remote that has moved, and the count is taken again over that new pair.
    """

    def test_a_damaged_member_stops_the_stage(self) -> None:
        # Each of these is a different fail-open behind the same edit. The
        # candidate is what says a reading is owed at all; the base is the
        # other end of the pair a verdict is defended by; the count is the
        # answer itself; and the marker is what the moved-publication
        # comparison is scoped by.
        for damaged in (
            {KEY_CANDIDATE_SHA: NOT_A_COMMIT},
            {KEY_BASE_SHA: NOT_A_COMMIT},
            {KEY_ADDITIONS: NOT_A_COUNT},
            {KEY_POST_PUBLICATION: NOT_A_FLAG},
            {KEY_THRESHOLD: NOT_A_COUNT},
            {KEY_PHASE: NOT_A_PHASE},
        ):
            with self.subTest(damaged=damaged):
                github = self._damaged(**damaged)

                damaged, damaged_mocks = self._routed(github)

                self._assert_refused(github, damaged, damaged_mocks)

    def test_evidence_with_no_candidate_stops(self) -> None:
        # A group carrying anything at all and naming no commit is a record
        # about nothing: the freeze writes the pair and the identity in one
        # write, and the one identity minted without them is deliberately
        # never persisted.
        github = self._damaged(**{KEY_CANDIDATE_SHA: None})

        damaged, damaged_mocks = self._routed(github)

        self._assert_refused(github, damaged, damaged_mocks)

    def test_a_missing_member_stops_the_stage(self) -> None:
        # The same damage with nothing left to notice it by. The write that
        # mints a generation puts every one of these down in one go, so a
        # record missing one is a record something edited -- and each reader
        # answers for the hole the way it answers for an issue that froze
        # nothing: no ceiling is a candidate that is never oversized, no phase
        # a generation at no boundary, and no identity a reading no audit line
        # or lineage can be joined to.
        for gone in (
            KEY_THRESHOLD,
            KEY_PHASE,
            KEY_CYCLE_ID,
            KEY_GENERATION,
            KEY_ROOT_ISSUE,
            KEY_CURRENT_ISSUE,
        ):
            with self.subTest(gone=gone):
                github = self._damaged(**{gone: None})

                missing, missing_mocks = self._routed(github)

                self._assert_refused(github, missing, missing_mocks)

    def test_a_counted_pair_with_no_base_stops(self) -> None:
        # The one field asked conditionally: a reading that could not freeze a
        # base is a state this domain persists, so its absence alone is not
        # damage. A COUNT beside it is what makes it damage -- a number is
        # taken over a pair, and a record that cannot show the base it was
        # measured from cannot defend the answer it carries.
        github = self._damaged(
            **{KEY_BASE_SHA: None, KEY_ADDITIONS: UNDER_THE_CEILING},
        )

        missing, missing_mocks = self._routed(github)

        self._assert_refused(github, missing, missing_mocks)

    def test_an_uncounted_pair_with_no_base_runs(self) -> None:
        # And the state that absence really is: the freeze recorded the
        # failure beside the identity so the retry has one exact object to ask
        # for, and parking it would stop the reading it was written for.
        github = self._damaged(**{KEY_BASE_SHA: None})

        unfrozen, unfrozen_mocks = self._routed(github)

        unfrozen_mocks[COUNT_ADDED_LINES].assert_called_once()
        unfrozen.assert_called_once()
        self.assertNotIn(AWAITING_HUMAN, github.pinned_data(ISSUE))

    def test_a_damaged_spend_stops_the_stage(self) -> None:
        # What a hold owed is one claim, and half of it is worse than none:
        # the round advances, the bookmark it was spent for stays pending, and
        # the record is discarded as paid.
        for damaged in ([["not_a_field", 1]], [["review_round", 2], ["x"]]):
            with self.subTest(damaged=damaged):
                github = self._damaged(**{KEY_SPENDS: damaged})

                damaged, damaged_mocks = self._routed(github)

                self._assert_refused(github, damaged, damaged_mocks)

    def test_a_whole_reading_is_answered(self) -> None:
        # What says the refusals above are about the damage rather than about
        # the reconciliation refusing every record it finds.
        github = self._damaged(**{KEY_SPENDS: [["review_round", 2]]})

        damaged, damaged_mocks = self._routed(github)

        damaged.assert_called_once()
        damaged_mocks[PUSH_BRANCH].assert_called_once()

    _damaged = DamagedPublicationDispatchTest._damaged
    _routed = DamagedPublicationDispatchTest._routed
    _assert_refused = DamagedPublicationDispatchTest._assert_refused


class DamagedApprovalDispatchTest(unittest.TestCase, _FrozenPairMixin):
    """A recorded debt that cannot produce the pair it is spent as."""

    def test_an_approval_without_its_lease_stops(self) -> None:
        # The commit and the head it is pinned against are written together
        # and mean nothing apart: an approval whose lease is gone is one the
        # retry would force-push under whatever the pull request has become.
        github = self._owing(lease=None)

        dispatched, mocks = self._routed(github)

        self._assert_refused(github, dispatched, mocks)

    def test_a_lease_without_its_approval_stops(self) -> None:
        # The same claim from its other end, and the same repair: a lease
        # naming a head nobody owes a push for says the write that paired
        # them did not finish.
        github = self._owing(approved=NOT_A_COMMIT)

        dispatched, mocks = self._routed(github)

        self._assert_refused(github, dispatched, mocks)

    def test_a_malformed_lease_stops(self) -> None:
        # Read fail-closed, a hand-edited lease is no lease -- which is
        # exactly the reading that would otherwise let the stage run.
        github = self._owing(lease=NOT_A_COMMIT)

        dispatched, mocks = self._routed(github)

        self._assert_refused(github, dispatched, mocks)

    def test_a_whole_debt_is_paid_rather_than_parked(self) -> None:
        # What says the refusals above are about the damage rather than about
        # the reconciliation refusing every approval it finds.
        github = self._owing()

        dispatched, mocks = self._routed(github)

        dispatched.assert_called_once()
        self.assertEqual(
            mocks[PUSH_BRANCH].call_args.kwargs["revision"],
            MEASURED_CANDIDATE_SHA,
        )

    def test_an_initial_approval_is_left_to_its_stage(self) -> None:
        # `workflow:implementing` has an edge to the adjudication too, and its
        # approval carries no pull-request head BY DESIGN: the push it
        # licenses is the one that opens the pull request, so it reads the
        # remote for itself. A crash between the two leaves exactly the shape
        # this owner would otherwise call damaged -- and parking it stops the
        # publication the stage below is there to finish.
        github = self._owing(lease=None, label=IMPLEMENTING)

        dispatched, _mocks = self._route(
            github, github.get_issue(ISSUE), handled=IMPLEMENTING,
        )

        dispatched.assert_called_once()
        pinned = github.pinned_data(ISSUE)
        self.assertNotIn(AWAITING_HUMAN, pinned)
        self.assertEqual(pinned[KEY_APPROVED_SHA], MEASURED_CANDIDATE_SHA)

    def _owing(self, *, approved=_WHOLE, lease=_WHOLE, label=fixing.FIXING):
        """An approval left standing after the write that granted it.

        Both halves default to the pair a whole debt carries; a case names the
        one it is about, and `None` is the key nothing wrote rather than a
        value nothing could read.
        """
        github = self._frozen(label=label)[0]
        pinned = {
            key: recorded
            for key, recorded in github.pinned_data(ISSUE).items()
            if not key.startswith(_LATE_PREFIX)
        }
        pinned[KEY_APPROVED_SHA] = (
            MEASURED_CANDIDATE_SHA if approved is _WHOLE else approved
        )
        pinned[KEY_APPROVED_LEASE] = (
            fixing.PR_HEAD_SHA if lease is _WHOLE else lease
        )
        github.seed_state(ISSUE, **pinned)
        return github

    _routed = DamagedPublicationDispatchTest._routed
    _assert_refused = DamagedPublicationDispatchTest._assert_refused


class DamagedTransferNoteDispatchTest(unittest.TestCase, _FrozenPairMixin):
    """A settlement note that cannot produce the record it says is owed.

    The note is written by the statement that settles a transfer and dropped by
    the write behind its record, so one standing over no permission, or naming
    no reading, is a comment saying two things at once. The report reads it as
    nothing owed, which is exactly the reading that would let the stage run
    behind a verdict nothing can account for.
    """

    def test_an_unreportable_note_stops_the_stage(self) -> None:
        for described, note in (
            ("a note beside no permission", "pushed"),
            ("a note naming no reading", NOT_A_PHASE),
        ):
            with self.subTest(described):
                github = self._damaged(**{KEY_REWRITE_PROOF: note})

                self._assert_refused(github, *self._routed(github))

    def test_a_repeated_refusal_says_so_once(self) -> None:
        # Nothing discards the note, so every later poll finds it again; the
        # park it earned has already said so, and the stage stays held.
        github = self._damaged(**{KEY_REWRITE_PROOF: NOT_A_PHASE})
        self._routed(github)
        posted = len(github.get_issue(ISSUE).comments)

        self._assert_refused(github, *self._routed(github))
        self.assertEqual(len(github.get_issue(ISSUE).comments), posted)

    def test_the_adjudication_is_asked_it_too(self) -> None:
        # A note the adjudication did not write is one it cannot repair.
        noted = PinnedState(data={KEY_REWRITE_PROOF: NOT_A_PHASE})

        self.assertEqual(
            _claims._unreadable_record(_workflow_state.WorkflowLabel.DECOMPOSING, noted),
            _claims._DAMAGED_TRANSFER,
        )

    _damaged = DamagedPublicationDispatchTest._damaged
    _routed = DamagedPublicationDispatchTest._routed
    _assert_refused = DamagedPublicationDispatchTest._assert_refused


class MovedStageDebtDispatchTest(unittest.TestCase, _FrozenPairMixin):
    """A debt whose stage the label has left before it was paid.

    The stages a debt may be published from are the five that push onto a pull
    request the remote already carries. Every other label with an edge to the
    adjudication -- `ready`, `blocked`, `umbrella` -- has one for reasons of
    its own, and none of them is a pull request.
    """

    def test_a_debt_on_a_moved_stage_stops(self) -> None:
        # The stages a debt may be paid from are the five that publish onto a
        # pull request the remote already carries -- not every label with an
        # edge to the adjudication, which `ready`, `blocked`, and `umbrella`
        # all have for reasons of their own. Paid from one of those the push
        # would go onto a branch that stage knows nothing about; ignored, the
        # handler runs over a publication the approved commit never reached.
        for moved in (READY, BLOCKED, UMBRELLA):
            with self.subTest(moved=moved):
                self._assert_refused(*self._routed_from(moved))

    def test_a_moved_stage_says_so_once(self) -> None:
        # Nothing this process can repair is behind it -- a human moved the
        # label and only a human can put it back -- so a fresh mention every
        # poll would be one nobody can answer any faster.
        stranded = self._owing(label=READY)
        self._routed_from(READY, github=stranded)
        announced = len(stranded.get_issue(ISSUE).comments)

        self._routed_from(READY, github=stranded)

        self.assertEqual(len(stranded.get_issue(ISSUE).comments), announced)

    def _routed_from(self, label, github=None):
        """One dispatched tick over a debt standing on `label`."""
        stranded = self._owing(label=label) if github is None else github
        issue = stranded.get_issue(ISSUE)
        dispatched, mocks = self._route(stranded, issue, handled=label)
        return stranded, dispatched, mocks

    _owing = DamagedApprovalDispatchTest._owing
    _frozen = DamagedApprovalDispatchTest._frozen
    _assert_refused = DamagedPublicationDispatchTest._assert_refused


class UnpublishedSourceStageDispatchTest(unittest.TestCase, _FrozenPairMixin):
    """A frozen record naming a stage no publication is entered from.

    The five that push onto a pull request the remote already carries are the
    whole of what a group may name. `ready`, `blocked`, and `umbrella` each
    have an edge to the adjudication for reasons of their own and no pull
    request behind any of them, and `implementing`'s own push is the one that
    OPENS the pull request -- so a persisted record naming one of them
    describes a publication this workflow never entered, and reconciling it
    would measure and push a candidate no post-publication stage committed.
    """

    def test_a_record_of_such_a_stage_is_never_pushed(self) -> None:
        # Read on the very stage it names, which is the shape that would
        # otherwise pass every check: the record agrees with the label, so
        # nothing reads it as stranded and the reconciliation settles and
        # pushes a commit the stage below never published.
        for named in (READY, BLOCKED, UMBRELLA, IMPLEMENTING):
            with self.subTest(named=named):
                github = self._entered_from(named)

                stage, seams = self._route(
                    github, github.get_issue(ISSUE), handled=named,
                )

                seams[COUNT_ADDED_LINES].assert_not_called()
                seams[PUSH_BRANCH].assert_not_called()
                self.assertEqual(github.label_history, [])
                self.assertNotIn(AWAITING_HUMAN, github.pinned_data(ISSUE))
                stage.assert_called_once()

    def _entered_from(self, named):
        """A whole group whose stage is one no publication is entered from.

        The issue sits on the very state the record names, so nothing reads
        this as a pair stranded by a relabel. Hand-edited onto the comment
        rather than written through the record, which refuses to enter a group
        on such a stage at all -- an older binary and an operator's edit are
        what leave this shape behind.
        """
        github = self._frozen(label=named)[0]
        pinned = github.pinned_data(ISSUE)
        pinned[KEY_SOURCE_STAGE] = str(named)
        github.seed_state(ISSUE, **pinned)
        return github
