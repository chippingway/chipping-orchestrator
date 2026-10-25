# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a split leaves behind when it dies while creating its children.

The middle of the transaction, and the part with a window nothing durable can
close on its own: `create_child_issue` returns and the process dies before the
write that records the number, so the only way back to that issue is the marker
it was created with. These cases also drive the DISPATCHER, because poll order
is the repository's rather than this transaction's -- an orphan can reach the
stage machine on its own, before anything has attributed it.

What a crash leaves owed includes a child's drift baseline. The create's
answer dies with the process that took it and nothing retained proves what
the child was created saying, so a resumed walk seeds the child with none --
and keeps one a landed seed already recorded.
"""
from __future__ import annotations

import unittest

from orchestrator.git.snapshots.refs import SnapshotOutcome
from orchestrator.workflow.engine import issue_processing as _issue_processing
from orchestrator.workflow.stages.decomposition import (
    late_child_records as _late_child_records,
)
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.support.writer_claims import claimed_on_creation
from tests.workflow.fixtures import _TEST_SPEC, LABEL_BLOCKED
from tests.workflow.stages.decomposition import (
    child_baseline_support as _baseline_support,
    late_baseline_support as _late_baselines,
    late_test_support as _late_support,
)
from tests.workflow.stages.decomposition.late_crash_support import (
    killed_after,
    killed_before,
)
from tests.workflow.stages.decomposition.late_seam_support import (
    RecordedDelete,
)
from tests.workflow.stages.decomposition.late_transaction_support import (
    CHILDREN,
    KEY_CHILDREN,
    KEY_CONSUMERS,
    KEY_EXPECTED_CHILDREN,
    KEY_UMBRELLA,
    PARK_CHILDREN_FAILED,
    LateSplitCase,
    first_child,
)

LATE_ISSUE_NUMBER = _late_support.LATE_ISSUE_NUMBER

KEY_AWAITING_HUMAN = "awaiting_human"

KEY_PARK_REASON = "park_reason"

KEY_PARENT_NUMBER = "parent_number"

CREATE_CHILD = "create_child_issue"

# How the split's park names a child whose pinned record admission refuses.
_UNADMITTED = "whose pinned record this orchestrator does not admit"

# A park a child took for itself, after it had been attributed.
_ITS_OWN_PARK = "implementing_timeout"

# How a pass a child's seed held left the split -- parked, announcing nothing,
# and the child still blocked -- and how a pass that settled it did: announced
# once, with one child per slice.
_HELD = (_LateDisposition.PARKED, PARK_CHILDREN_FAILED, 0, LABEL_BLOCKED)
_SETTLED = (_LateDisposition.SETTLED, 1, len(CHILDREN))

# The two windows a crash leaves a child's seed owed in: between its create
# and the write recording it, where the resume adopts the child by its
# receipt, and between that write and the seed, where the resume seeds the
# child its register names.
_OWED_SEED_WINDOWS = (
    ("its create and its record", lambda case: killed_after(case.github, CREATE_CHILD)),
    ("its record and its seed", lambda case: killed_after(_late_child_records, "_recorded")),
)

# The remote a resumed walk's configuration names once an operator renamed it.
_RENAMED_REMOTE = "upstream"


class ChildReachedFirstTest(LateSplitCase, unittest.TestCase):
    """A child another poller on this host reaches first is not this split's to seed.

    Poll order is the repository's, so the child the split has just created can
    be dispatched by a second poller before the seed lands, and while that
    poller holds the child's writer claim its record is that poller's to write.
    The split records the child, writes nothing to it, and parks as a seed that
    could not be made -- the park the next attempt supersedes.
    """

    def test_a_held_child_waits_for_the_next_attempt(self) -> None:
        with claimed_on_creation(self.github), self.assertLogs(level="INFO"):
            outcome = self._transact()

        held = self.github.created_child_issues[0].number
        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertEqual(self._pinned()[KEY_PARK_REASON], PARK_CHILDREN_FAILED)
        self.assertEqual(self._pinned()[KEY_CHILDREN], [held])
        self.assertEqual(len(self.github.created_child_issues), 1, "no child is opened past it")
        self.assertEqual(self._child_state(held), {}, "nothing is written to it")

        resumed = self._resume()

        self.assertEqual(resumed.disposition, _LateDisposition.SETTLED)
        self.assertEqual(self._child_state(held)[KEY_PARENT_NUMBER], LATE_ISSUE_NUMBER)

    def test_a_baseline_it_recorded_is_kept(self) -> None:
        # That poller wrote its own record on the child and let go before the
        # seed's claim, a baseline in it. The seed attributes the child and
        # lifts the park it took, and keeps the baseline as it stands rather
        # than the one the create answered.
        self.github.create_child_issue = _baseline_support.ReadAtCreation(
            self.github, _late_baselines.REACHED_FIRST,
        )

        settled = self._transact()

        seeded = self._child_state(first_child(self.github).number)
        self.assertEqual(
            (settled.disposition, seeded[KEY_PARENT_NUMBER], seeded[KEY_AWAITING_HUMAN]),
            (_LateDisposition.SETTLED, LATE_ISSUE_NUMBER, False),
        )
        self.assertEqual(seeded[_late_baselines.KEY_BASELINE], _late_baselines.RECORDED_BASELINE)


class RefusedChildTest(LateSplitCase, unittest.TestCase):
    """A child whose own pinned record admission refuses is not this split's to seed.

    Read under the child's claim, such a record is one nothing can vouch for:
    seeded, it would be stamped as current with its park lifted. The split
    records the child, writes nothing to it and says nothing on it, and parks
    as a seed that could not be made -- the park the next attempt supersedes,
    and the one that seeds it once a record admission takes is back on it.
    """

    def test_a_refused_orphan_is_adopted_unwritten(self) -> None:
        with self.assertRaises(KeyboardInterrupt):
            self._transact(killed=killed_after(self.github, CREATE_CHILD))
        orphan = self.github.created_child_issues[0].number
        self.github.seed_state(orphan, raw=True, awaiting_human=True)
        refused = self._child_state(orphan)

        with self.assertLogs(level="WARNING"):
            parked = self._resume()

        self.assertEqual(
            (parked.disposition, self._pinned()[KEY_PARK_REASON], self._pinned()[KEY_CHILDREN]),
            (_LateDisposition.PARKED, PARK_CHILDREN_FAILED, [orphan]),
        )
        self.assertEqual(self._child_state(orphan), refused, "nothing is written to it")
        self.assertNotIn(orphan, [number for number, _ in self.github.posted_comments], "nothing is said on it")
        self.assertIn(
            f"#{orphan} ('A'), {_UNADMITTED}", self.github.posted_comments[-1][1], "the park on this issue names it",
        )
        self.assertEqual(len(self.github.created_child_issues), 1, "no child is opened past it")

        self.github.seed_state(orphan)
        settled = self._resume()

        self.assertEqual(
            (settled.disposition, self._child_state(orphan)[KEY_PARENT_NUMBER]),
            (_LateDisposition.SETTLED, LATE_ISSUE_NUMBER),
        )


class OwedSeedBaselineTest(LateSplitCase, unittest.TestCase):
    """A child whose seed a crash left owed is seeded with no drift baseline, whatever it reads by then.

    The create's answer dies with the process that took it, and nothing the
    split retains replaces it: the manifest renders a body that also names the
    configured base branch, remote, and mirror, which no record keeps, so a
    child reading exactly as its manifest renders it now may be one edited to
    match a configuration changed since. The resume links and seeds the child
    with its baseline missing, opens no slice twice, and settles the split; a
    baseline a landed seed recorded is kept.
    """

    def test_an_owed_seed_records_none(self) -> None:
        # Whatever lands on the child before the resume -- nothing included --
        # it is seeded with no baseline rather than one hashed off what it
        # says by then.
        for window, killed in _OWED_SEED_WINDOWS:
            for landed, landing in _late_baselines.LANDINGS_OR_NONE.items():
                with self.subTest(window=window, landed=landed):
                    self.setUp()
                    child = self._crashed_owing_the_seed(killed)
                    landing.on(self.github, child)

                    self.assertEqual(self._settled(self._resume()), _SETTLED)
                    self.assertEqual(self._child_state(child.number)[KEY_PARENT_NUMBER], LATE_ISSUE_NUMBER)
                    self.assertEqual(_late_baselines.seeded(self.github, child.number), (None, None))

    def test_a_configuration_change_proves_nothing(self) -> None:
        # The process dies between the record and the seed; an operator then
        # renames the remote and edits the child's fetch instruction to match,
        # so it reads exactly as its manifest renders it under the
        # configuration the resume runs with. That edit is still no proof of
        # what the child was created saying: it is seeded with no baseline.
        child = self._crashed_owing_the_seed(_OWED_SEED_WINDOWS[1][1])
        fetch = f"git fetch {_TEST_SPEC.remote_name} "
        self.assertIn(fetch, child.body)
        child.body = child.body.replace(fetch, f"git fetch {_RENAMED_REMOTE} ")

        with _late_baselines.renamed_remote(_RENAMED_REMOTE):
            self.assertEqual(self._settled(self._resume()), _SETTLED)

        self.assertEqual(_late_baselines.seeded(self.github, child.number), (None, None))

    def test_a_lost_seed_answer_keeps_its_baseline(self) -> None:
        # The seed lands and its answer is lost: the split parks naming the
        # child, and announces and activates nothing. An edit lands while
        # the park stands; the resume reads the seed that landed and keeps
        # the baseline it carries -- what the child was created saying -- so
        # the edit stays drift, and the split settles announcing once, with
        # one child per slice.
        with _late_baselines.lost_seed(self.github, lands=True), self.assertLogs(level="ERROR"):
            parked = self._transact()
        child = first_child(self.github)
        created = _baseline_support.reading(child)
        held = (
            self._held(parked, child.number),
            _late_baselines.seeded(self.github, child.number),
        )
        _late_baselines.BODY_EDIT(self.github, child)

        settled = self._resume()

        self.assertEqual(held, (_HELD, (created, False)))
        self.assertEqual(_late_baselines.seeded(self.github, child.number), (created, True))
        self.assertEqual(self._settled(settled), _SETTLED)

    def test_an_unreadable_record_holds_the_seed(self) -> None:
        # The process dies between the record and the seed, and the resume
        # cannot read the child's record under its claim, which proves nothing
        # about what landed there: it writes nothing to the child and parks,
        # announcing and activating nothing. Once the record reads again, the
        # child is seeded -- with no baseline -- and the split settles
        # announcing once.
        child = self._crashed_owing_the_seed(_OWED_SEED_WINDOWS[1][1]).number
        with _late_baselines.unreadable(self.github, child), self.assertLogs(level="ERROR"):
            parked = self._resume()
        held = (self._held(parked, child), self._child_state(child))

        settled = self._resume()

        self.assertEqual(held, (_HELD, {}))
        self.assertEqual(self._child_state(child)[KEY_PARENT_NUMBER], LATE_ISSUE_NUMBER)
        self.assertEqual(_late_baselines.seeded(self.github, child), (None, None))
        self.assertEqual(self._settled(settled), _SETTLED)

    def _crashed_owing_the_seed(self, killed):
        """Run the split into the crash `killed` builds for this case, leaving a child's seed owed; that child."""
        with self.assertRaises(KeyboardInterrupt):
            self._transact(killed=killed(self))
        return first_child(self.github)

    def _held(self, parked, child: int) -> tuple:
        """How a parked pass left the split: its disposition and park, its announcements, and the child's label."""
        return (
            parked.disposition,
            self._pinned()[KEY_PARK_REASON],
            _late_baselines.announcements(self.github),
            self.github.workflow_label(self.github.get_issue(child)),
        )

    def _settled(self, resumed) -> tuple:
        """How a resumed pass left the split: its disposition, its announcements, and how many children exist."""
        return resumed.disposition, _late_baselines.announcements(self.github), len(self.github.created_child_issues)


class ChildBoundaryTest(LateSplitCase, unittest.TestCase):
    """A child is recorded before anything else is done with it."""

    def test_a_death_pre_child_leaves_the_count(self) -> None:
        # What tells a partial split from a finished one, and what says the
        # parent has no implementation of its own to return to.
        with self.assertRaises(KeyboardInterrupt):
            self._transact(
                killed=killed_before(self.github, CREATE_CHILD),
            )

        pinned = self._pinned()
        self.assertEqual(pinned[KEY_EXPECTED_CHILDREN], len(CHILDREN))
        self.assertTrue(pinned[KEY_UMBRELLA])
        self.assertIsNone(pinned.get(KEY_CHILDREN))

    def test_a_death_mid_create_is_visible(self) -> None:
        # The one window the ordering accepts rather than closes: the create
        # returned and the parent never learned of it. The operator sees a
        # count the recorded children do not reach; nothing here silently
        # adopts an issue the parent cannot name.
        with self.assertRaises(KeyboardInterrupt):
            self._transact(
                killed=killed_after(self.github, CREATE_CHILD),
            )

        self.assertEqual(len(self.github.created_child_issues), 1)
        self.assertIsNone(self._pinned().get(KEY_CHILDREN))
        self.assertEqual(
            self._pinned()[KEY_EXPECTED_CHILDREN], len(CHILDREN),
        )

    def test_a_death_between_children_resumes(self) -> None:
        # The first slice is created, recorded, and seeded; the second has not
        # been touched. The resume adopts the first and opens only the second.
        with self.assertRaises(KeyboardInterrupt):
            self._transact(killed=killed_after(_late_child_records, "_seeded"))
        first = list(self._pinned()[KEY_CHILDREN])
        self.assertEqual(len(first), 1)

        resumed = self._resume()

        self.assertEqual(resumed.disposition, _LateDisposition.SETTLED)
        self.assertEqual(len(self.github.created_child_issues), len(CHILDREN))
        self.assertEqual(self._pinned()[KEY_CHILDREN][:1], first)

    def test_an_orphan_polled_first_is_unparked(self) -> None:
        # Poll order is the repository's, not this transaction's: GitHub sorts
        # by most recently updated, so the child a crash left unrecorded can be
        # dispatched before the write that attributes it -- and a `blocked`
        # issue nobody claims is parked for a human. Adopting it has to take
        # that park back, or the child is activated and then waits for a reply
        # nobody owes it.
        with self.assertRaises(KeyboardInterrupt):
            self._transact(
                killed=killed_after(self.github, CREATE_CHILD),
            )
        orphan = self.github.created_child_issues[0]
        self._dispatch(orphan)
        self.assertTrue(self._child_state(orphan.number)[KEY_AWAITING_HUMAN])

        self._resume()

        seeded = self._child_state(orphan.number)
        self.assertFalse(seeded[KEY_AWAITING_HUMAN])
        self.assertIsNone(seeded[KEY_PARK_REASON])
        self.assertEqual(seeded[KEY_PARENT_NUMBER], LATE_ISSUE_NUMBER)

    def test_a_park_of_its_own_survives_a_reseed(self) -> None:
        # A child that already records a parent has been attributed, so a park
        # on it is something it hit while running -- not this transaction's to
        # take back.
        self._transact()
        adopted = self.github.created_child_issues[0].number
        self.github.seed_state(adopted, **{
            **self._child_state(adopted),
            KEY_AWAITING_HUMAN: True,
            KEY_PARK_REASON: _ITS_OWN_PARK,
        })

        self._resume()

        self.assertTrue(self._child_state(adopted)[KEY_AWAITING_HUMAN])
        self.assertEqual(
            self._child_state(adopted)[KEY_PARK_REASON], _ITS_OWN_PARK,
        )

    def test_a_death_after_the_record_adopts(self) -> None:
        # Recorded first, so the retry reuses the child rather than opening a
        # second issue for the same slice -- and re-seeds it, since the seed
        # is the step that can have been lost.
        with self.assertRaises(KeyboardInterrupt):
            self._transact(killed=killed_after(_late_child_records, "_recorded"))

        recorded = list(self._pinned()[KEY_CHILDREN])
        self.assertEqual(self._pinned()[KEY_CONSUMERS], recorded)

        resumed = self._resume()

        self.assertEqual(resumed.disposition, _LateDisposition.SETTLED)
        self.assertEqual(
            [child.number for child in self.github.created_child_issues],
            self._pinned()[KEY_CHILDREN],
        )
        self.assertEqual(len(self._pinned()[KEY_CHILDREN]), len(CHILDREN))

    def _dispatch(self, child) -> None:
        """Route one child through the real tick, as a poll would.

        The whole dispatcher rather than the handler it lands on, because what
        is under test is the ORDER a repository polls in: the child reaches the
        stage machine on its own, before anything has attributed it.

        The remote answers for the split's own ref while it does, because the
        reuse guard may ask about it: an orphan carries a marker naming the
        split, and where the parent's ledger vouches for that claim the ref it
        names is asked about -- a split still in flight has left it exactly
        where it created it.
        """
        with RecordedDelete(SnapshotOutcome.DELETED).answering():
            _issue_processing._process_issue(self.github, _TEST_SPEC, child)


if __name__ == "__main__":
    unittest.main()
