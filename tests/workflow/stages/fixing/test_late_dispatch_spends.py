# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a crash between the freeze and the count owes, and where it survives.

A hold closes the bookkeeping its caller's tick was in the middle of -- the
reviewer round a fix spends, the bookmarks a consumed batch clears -- and the
caller says up front what that is, because the hold relabels and nothing
behind it would go back for the count. The freeze is durable and the count is
not, so a tick that dies in between leaves the reconciliation ahead of the
next handler to take the reading instead. That tick has no run behind it, so
there is nothing for it to re-derive any of this from: it is restored off the
pinned comment or it is lost.

Lost, an oversized retry routes to the adjudication having closed none of it,
and the pinned comment goes on naming a fix batch that was already answered.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.measurement.models import (
    MeasurementFailure,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.fixing.bookmarks import (
    _cleared_pending_fix_bookmarks,
)
from orchestrator.workflow.stages.implementing import late_push as _late_push
from tests.workflow.stages.fixing import (
    fixing_test_support as fixing,
    published_gate_support as support,
)
from tests.workflow.stages.fixing.test_late_dispatch import (
    _FrozenPairMixin,
)

ISSUE = fixing.ISSUE
CEILING = support.CEILING
PAST_THE_CEILING = support.PAST_THE_CEILING
LABEL_DECOMPOSING = support.LABEL_DECOMPOSING

KEY_SPENDS = "late_spends"
KEY_RECEIPT_SHA = support.KEY_RECEIPT_SHA
PUBLICATION_PAID = "_publication_paid"
MEASURED_CANDIDATE_SHA = support.MEASURED_CANDIDATE_SHA
PUSH_BRANCH = fixing.PUSH_BRANCH
# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"
KEY_APPROVED_SHA = support.KEY_APPROVED_SHA
PUSH_BRANCH = fixing.PUSH_BRANCH
MEASURED_CANDIDATE_SHA = support.MEASURED_CANDIDATE_SHA
KEY_REVIEW_ROUND = "review_round"
KEY_PENDING_FIX_AT = "pending_fix_at"
KEY_PENDING_COMMENT = "pending_fix_reviewer_comment_id"

# The round the interrupted tick had reached, and the one its hold owes. The
# in_review route reset: the round before this fix was APPROVED, so the fix
# starts a fresh count rather than advancing the one it answered.
ROUND_BEFORE = 1
ROUND_SPENT = 0

# The comment the fixing route recorded as the batch it was answering.
PENDING_COMMENT_ID = 4242

# What the crashed tick recorded beside the pair: the round it would have
# counted, and the fix batch it would have marked consumed. Built from the
# route's own list rather than spelled again, so a bookmark added there is one
# this pins down rather than one it silently stops covering.
FROZEN_SPENDS = tuple(
    [key, cleared] for key, cleared in (
        *_cleared_pending_fix_bookmarks(),
        (KEY_REVIEW_ROUND, ROUND_SPENT),
    )
)

# The batch the fixing route recorded when it started the run that crashed.
CONSUMED_BATCH = MappingProxyType({
    KEY_REVIEW_ROUND: ROUND_BEFORE,
    KEY_PENDING_FIX_AT: "2026-01-01T00:00:00+00:00",
    KEY_PENDING_COMMENT: PENDING_COMMENT_ID,
})

# A count that never happened, which leaves the pair on the comment with no
# number beside it -- the same shape a crash between the two leaves.
UNCOUNTED = MeasurementFailure.DIFF_UNREADABLE


# One whole member of a recorded group, one cleared bookmark, and one whose
# value the pinned comment could never carry. Spelled as the tuples a record
# is compared against; the reader is handed the lists JSON decodes to.
_ROUND = (KEY_REVIEW_ROUND, 2)
_CLEARED = (KEY_PENDING_FIX_AT, None)
_UNCARRIABLE = ("docs_settled_sha", "{}")
_SETTLED = ("docs_settled_sha", MEASURED_CANDIDATE_SHA)


def _recorded(*members) -> list:
    """One `late_spends` value as a pinned comment decodes it."""
    return [list(member) for member in members]


class _DiesPastTheReceipt:
    """A tick that stops the moment the receipt write returns.

    The write itself is the real one, so what the pinned comment carries
    afterwards is exactly what a process killed in that window would leave
    behind -- and what the tick would have done next never runs.
    """

    def __init__(self) -> None:
        self._paid = _late_push._publication_paid

    def __call__(self, gate, published, unproven) -> None:
        self._paid(gate, published, unproven)
        raise RuntimeError("the tick died past the receipt")


def _pinned(github) -> dict:
    """The pinned comment this issue carries, read back after a tick."""
    return github.pinned_data(ISSUE)


class FrozenSpendsPersistenceTest(unittest.TestCase, _FrozenPairMixin):
    """The freeze records what its caller's hold owes, in the same write."""

    def test_a_freeze_records_what_the_hold_owes(self) -> None:
        # Written with the pair rather than after the count, because the
        # window this pays for opens the moment the pair is durable: a tick
        # that dies before the count is exactly the tick that cannot say what
        # it owed.
        scenario = self._seeded_fix_round()

        with patch.object(fixing.config, support.MAX_ADDED_LINES, CEILING):
            self._run_fix_round(scenario, added_lines=PAST_THE_CEILING)

        # The routed hold spent it and the write that carried the count
        # dropped it: nothing is left for a later cycle to be handed. The
        # round is this one's to hand over because it wrote no report -- one
        # that did freezes the same pair onto that record instead, for the
        # write that finally publishes it.
        pinned = _pinned(scenario.github)
        self.assertNotIn(KEY_SPENDS, pinned)
        self.assertEqual(pinned[KEY_REVIEW_ROUND], ROUND_SPENT)
        self.assertIsNone(pinned[KEY_PENDING_FIX_AT])

    def test_a_freeze_that_never_counted_keeps_it(self) -> None:
        # The same write, seen from the crash it exists for: the pair is on
        # the pinned comment, no number is beside it, and what the hold owes
        # is there for the tick that takes the reading.
        scenario = self._seeded_fix_round()

        with patch.object(fixing.config, support.MAX_ADDED_LINES, CEILING):
            self._run_fix_round(
                scenario, added_lines=UNCOUNTED,
            )

        pinned = _pinned(scenario.github)
        self.assertEqual(tuple(pinned[KEY_SPENDS]), FROZEN_SPENDS)
        self.assertEqual(pinned[KEY_REVIEW_ROUND], ROUND_BEFORE)

    def _seeded_fix_round(self):
        """A fix round whose hold owes a reviewer round and a cleared batch."""
        return self._seed_fix_round(**CONSUMED_BATCH)

    _seed_fix_round = support._SizeGateFixtureMixin._seed_fix_round
    # This class's rounds go down the road that still hands the gate the
    # route's own pair: a reply with no report of its own, republishing a
    # commit an earlier round stranded.
    _run_fix_round = support._SizeGateFixtureMixin._run_stranded_round
    _seed = support._SizeGateFixtureMixin._seed
    _open_pr = support._SizeGateFixtureMixin._open_pr


class FrozenSpendsRestoredTest(unittest.TestCase, _FrozenPairMixin):
    """What the tick that takes the interrupted reading closes with it."""

    def test_an_oversized_retry_closes_the_round(self) -> None:
        # The hold this retry takes is the hold the crashed tick would have
        # taken, so it owes exactly what that one did. Routed without it, the
        # issue reaches the adjudication with a round uncounted and a fix
        # batch the pinned comment still calls pending -- and no later tick
        # goes back for either, since a settled verdict publishes the accepted
        # commit and the resumed stage finds nothing left to push.
        github = self._frozen_with_spends()

        with patch.object(fixing.config, support.MAX_ADDED_LINES, CEILING):
            dispatched, _mocks = self._routed(
                github, added_lines=PAST_THE_CEILING,
            )

        dispatched.assert_not_called()
        self.assertEqual(github.label_history, [(ISSUE, LABEL_DECOMPOSING)])
        pinned = _pinned(github)
        self.assertEqual(pinned[KEY_REVIEW_ROUND], ROUND_SPENT)
        self.assertIsNone(pinned[KEY_PENDING_FIX_AT])
        self.assertIsNone(pinned[KEY_PENDING_COMMENT])

    def test_an_allowed_retry_closes_its_round(self) -> None:
        # The retirement an allowed candidate earns drops the record those
        # fields were written beside, so nothing behind this reads them: the
        # stage runs, finds the commit already on its pull request, and counts
        # nothing. The push this recovery landed IS the event they were owed
        # for, so they go down once it has.
        github = self._frozen_with_spends()

        dispatched, _mocks = self._routed(github)

        dispatched.assert_called_once()
        pinned = _pinned(github)
        self.assertEqual(pinned[KEY_REVIEW_ROUND], ROUND_SPENT)
        self.assertIsNone(pinned[KEY_PENDING_COMMENT])
        # Retired with the pair it was owed for, so no later cycle inherits it.
        self.assertNotIn(KEY_SPENDS, pinned)

    def _frozen_with_spends(self):
        """The pinned comment a crash between the freeze and the count left."""
        github = self._frozen()[0]
        pinned = _pinned(github)
        pinned.update(CONSUMED_BATCH)
        pinned[KEY_SPENDS] = list(FROZEN_SPENDS)
        github.seed_state(ISSUE, **pinned)
        return github

    def _routed(self, github, **run_options):
        """Route the tick the dispatcher takes over the issue this seeded."""
        return self._route(
            github, github.get_issue(ISSUE), **run_options,
        )


class RecordedSpendsReadingTest(unittest.TestCase):
    """What a recorded spend has to be before a write may apply it."""

    def test_a_group_comes_back_whole_or_not_at_all(self) -> None:
        # What a hold owed is ONE claim, and the caller restoring it cannot
        # tell which half it got. Members dropped individually leave the round
        # advanced, the bookmark it was spent for still pending, and the
        # record discarded as paid -- so the next in_review re-entry reruns a
        # developer over feedback that was already answered. The key is
        # bounded too: what comes back is applied to the pinned comment, so an
        # arbitrary one is a write into any field the workflow has.
        for recorded, restored in (
            (None, ()),
            ("not-a-list", ()),
            ([], ()),
            (_recorded(_ROUND), (_ROUND,)),
            (_recorded(_CLEARED), (_CLEARED,)),
            (_recorded(_SETTLED), (_SETTLED,)),
            (_recorded(_ROUND, ("not_a_field", 1)), ()),
            (_recorded(_ROUND, (7, "keyless")), ()),
            ([list(_ROUND), ["short"]], ()),
            ([list(_ROUND), [_UNCARRIABLE[0], {}]], ()),
            (_recorded((7, "keyless")), ()),
            (_recorded(("", 1)), ()),
            ([["short"]], ()),
            ([[_UNCARRIABLE[0], {}]], ()),
            # The shape each field may take, which the key is what says: a
            # counter that came back as text is applied to the comment and
            # then read by the cap that counts rounds, a bookmark is only ever
            # CLEARED, and a settled head is compared against a commit.
            (_recorded((KEY_REVIEW_ROUND, "later")), ()),
            (_recorded((KEY_REVIEW_ROUND, True)), ()),
            (_recorded((KEY_REVIEW_ROUND, -1)), ()),
            (_recorded((KEY_PENDING_FIX_AT, "2026-01-01T00:00:00+00:00")), ()),
            (_recorded((_SETTLED[0], "not-a-commit")), ()),
            (_recorded(("conflict_settled_outcome", "")), ()),
            (_recorded(("conflict_settled_outcome", 7)), ()),
        ):
            with self.subTest(recorded=recorded):
                state = PinnedState(data={KEY_SPENDS: recorded})

                self.assertEqual(
                    _late_state.read_late_spends(state), restored,
                )

    def test_nothing_owed_writes_no_key(self) -> None:
        # A generation frozen by a seam with no bookkeeping behind it -- the
        # whole implementing side -- leaves the key absent rather than empty,
        # so a reader cannot tell an empty list from a damaged one.
        state = PinnedState(data={KEY_SPENDS: list(FROZEN_SPENDS)})

        _late_state.write_late_spends(state, ())

        self.assertNotIn(KEY_SPENDS, state.data)


class RecoveredRoundEndToEndTest(unittest.TestCase, _FrozenPairMixin):
    """The world a recovery hands the real stage handler behind it.

    The mocked handler says the recovery published; only the real one says
    whether what it published left the issue where the crashed tick would
    have. The round is the part nothing behind the recovery can supply: the
    stage finds the commit already on its pull request, so the bounce that
    would have counted it finds nothing ahead and counts nothing.
    """

    def test_a_recovered_fix_lands_its_recorded_round(self) -> None:
        # `review_round` is what `MAX_REVIEW_ROUNDS` counts, and this fix came
        # through the in_review route -- which RESETS it, because the round
        # before the fix was approved. Left to the handler, the counter ends
        # on the value the crashed tick was moving it off.
        github = self._frozen_with_spends()

        self._run_the_stage(github)

        pinned = _pinned(github)
        self.assertEqual(pinned[KEY_REVIEW_ROUND], ROUND_SPENT)

    def test_a_recovered_fix_consumes_its_batch(self) -> None:
        # The bookmarks the fix route recorded when it started the run that
        # crashed. Left pending, the in_review re-entry behind this correlates
        # the same triggering comments again and reruns the developer over
        # feedback that was already answered.
        github = self._frozen_with_spends()

        self._run_the_stage(github)

        pinned = _pinned(github)
        self.assertIsNone(pinned[KEY_PENDING_FIX_AT])
        self.assertIsNone(pinned[KEY_PENDING_COMMENT])

    def test_a_recovered_fix_publishes_first(self) -> None:
        # The push the crashed tick owed is this recovery's, and the handler
        # runs behind it: what reaches the pull request is the commit that was
        # measured, not whatever the stage would have made of the checkout.
        github = self._frozen_with_spends()

        mocks = self._run_the_stage(github)

        pushed = mocks[PUSH_BRANCH].call_args
        self.assertEqual(pushed.kwargs[REVISION], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pushed.kwargs[LEASE], fixing.PR_HEAD_SHA)

    def test_a_crash_past_the_receipt_keeps_the_round(self) -> None:
        # The window a second write opens. There is no tick behind this push
        # to close what it owed, and the retirement that granted the approval
        # already dropped the record those fields were written beside -- so
        # applied after the receipt instead of with it, a process dying in
        # between comes back to a published commit, a paid debt, and an
        # uncounted round with nothing left saying one was owed.
        github = self._frozen_with_spends()

        with patch.object(
            _late_push, PUBLICATION_PAID, _DiesPastTheReceipt(),
        ), self.assertRaises(RuntimeError):
            self._run_the_stage(github)

        pinned = _pinned(github)
        self.assertEqual(pinned[KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[KEY_REVIEW_ROUND], ROUND_SPENT)
        self.assertIsNone(pinned[KEY_PENDING_COMMENT])

    def _run_the_stage(self, github):
        """One dispatched tick, with the real fixing handler behind it."""
        return self._route_to_the_stage(github, github.get_issue(ISSUE))

    _frozen_with_spends = FrozenSpendsRestoredTest._frozen_with_spends
