# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a conflict-stage replay carries an adjudicated change with it.

The exemption a `single` verdict leaves names one commit, and this stage is the
one place a branch standing on that commit is still replayed onto a base that
has moved: the per-tick base refresh skips such a checkout and never drives
`workflow:resolving_conflict`. Measured afresh, the very change a human ruled
on crosses the same ceiling again on the last push before the merge button.

So the clean rebase -- the one publication here that replays HISTORY it ran
itself -- hands the gate the pair it replaced, and the exemption moves onto the
commit it produced. Nothing else here presents evidence. A resolution an agent
authored over conflicted files, unpushed fix commits a reroute sent over, and
whatever an earlier tick left for the ahead-only recovery to find are all
commits somebody ELSE made, and no reading off the branch tells them from a
replay -- being on base least of all, since that is one of the two shapes the
`fixing` reroute fires on. Each is measured, and an oversized one earns the
fresh adjudication it is owed.

What carries a transfer through a crash is the PERMISSION the rebase made
durable before its push, which names the exact commit its replay produced. The
recovery presents nothing and is answered from that record, so a commit no
such record names gets nothing however alike it fingerprints.

Beside all of it sits the case the seam turns on: a replay that changed a byte.
It presents evidence like any other, and the fingerprints refuse it -- which is
what keeps a transfer a claim about the CONTRIBUTION rather than about the
rebase having run.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    rewrites as _rewrites,
)
from tests.support.fakes import FakePR, FakePRRef
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.conflicts import replay_test_support as _support
from tests.workflow.stages.conflicts.conflicts_test_support import (
    MOVED_PR_HEAD_SHA,
    _ResolvingConflictMixin,
)

CONFLICT_FILE = "a.py"
DIRTY_PATH = "orchestrator/x.py"

PUSH_BRANCH = "_push_branch"
COUNT_ADDED_LINES = "_count_added_lines"

LABEL_VALIDATING = "workflow:validating"
LABEL_DECOMPOSING = "workflow:decomposing"

REVISION = "revision"
LEASE = "force_with_lease"
AWAITING_HUMAN = "awaiting_human"
MAX_ADDED_LINES = "MAX_ADDED_LINES"
KEY_PR_NUMBER = "pr_number"

# What a replay really leaves the checkout at against the head it replaced:
# ahead by the base commits it landed on plus its own, and behind by the one
# it superseded. Measured off the real fixture rather than chosen.
REPLAYED_DIVERGENCE = (2, 1)

# A second open pull request on this branch, standing on the same head the
# replay was leased against -- which is what a repointed `pr_number` hands a
# recovery that reads the publication live instead of off the record.
OTHER_PR = _support.CONFLICT_PR + 1

# A ceiling the seeded diff is over, so a candidate no transfer carries is
# held and routed to a second adjudication of work a human already ruled on.
CEILING = 5
PAST_THE_CEILING = 6

# The two shapes a recovery no permission names arrives in. Both carry a
# commit an earlier tick made and never published, and the behind-base reading
# tells them apart for the ROUND they owe and for nothing else -- the `fixing`
# drift reroute sends unpushed fix commits over on either side of it.
_UNRECORDED_RECOVERIES = MappingProxyType({
    "one an agent's resolution left on base": _support.ON_BASE,
    "one the fixing reroute left behind base": _support.BEHIND_BASE,
})

# What a commit made ON TOP of the publication leaves: ahead of it and behind
# it by nothing, since the remote's head is still an ancestor. That is the
# shape a resolution and a rerouted fix commit arrive in, and it is what tells
# them from a replay before anything is read off the comment.
COMMITTED_ON_TOP = (1, 0)


@dataclass(frozen=True)
class _Replay:
    """One finished conflict tick, and the seams it was decided at."""

    github: object
    mocks: dict

    @property
    def pinned(self) -> dict:
        """What this issue's pinned comment says once the tick has ended."""
        return self.github.pinned_data(_support.CONFLICT_ISSUE)

    @property
    def pushes(self):
        """The force-push every one of these cases is decided at."""
        return self.mocks[PUSH_BRANCH]


class _ConflictReplayCase(ObservedCloseCase, _ResolvingConflictMixin):
    """One adjudicated branch, replayed and published under a low ceiling."""

    def setUp(self) -> None:
        super().setUp()
        # The transfer re-reads the issue before it grants anything, and a
        # close another case latched process-wide is a refusal this one never
        # asked for.
        self._fresh_process()

    def _replayed(self, **run_options) -> _Replay:
        """One clean rebase of an adjudicated commit, run to its push."""
        return self._published(
            merge_succeeded=True,
            head_shas=[_support.ADJUDICATED_HEAD, _support.REPLAYED_HEAD],
            **run_options,
        )

    def _recovered(self, **run_options) -> _Replay:
        """One commit an earlier tick left unpushed, published by this one.

        DIVERGED from the pull request by default, because that is what a
        replay really leaves: the rebase moves the branch off the head it
        replayed, so that head stops being an ancestor and the checkout comes
        back ahead of the publication AND behind it. A case about the fix
        commits a reroute leaves says `(1, 0)` instead, which is the shape of
        a commit made ON TOP of what the remote already has.

        On base unless a case says otherwise, since a replayed branch carries
        the base it was replayed onto.
        """
        run_options.setdefault("behind_base", _support.ON_BASE)
        run_options.setdefault("branch_ahead_behind", REPLAYED_DIVERGENCE)
        return self._published(
            merge_succeeded=True,
            head_shas=[_support.REPLAYED_HEAD, _support.REPLAYED_HEAD],
            candidate_commit=FrozenCommit(sha=_support.REPLAYED_HEAD),
            **run_options,
        )

    def _published(
        self,
        *,
        seeded: dict | None = None,
        pr_head: str = "",
        other_pr: int = 0,
        **run_options,
    ) -> _Replay:
        """Seed one adjudicated conflict issue and run a tick over it.

        The pull request rides with the seed because the head it stands on is
        part of what a case is about: this stage leases its force-push against
        the head it read out of the checkout, and a remote standing anywhere
        else is somebody else's push landing mid-tick.

        `other_pr` opens a SECOND one on the same branch, standing on that
        same head. That is what a repointed `pr_number` hands a recovery: a
        publication every reading but the record itself would accept.
        """
        github, issue = self._seed(
            extra_state=_support.adjudicated_state() if seeded is None else seeded,
        )[:2]
        if pr_head:
            github.get_pr(_support.CONFLICT_PR).head.sha = pr_head
        if other_pr:
            github.add_pr(FakePR(
                number=other_pr,
                head_branch=self.issue_branch,
                head=FakePRRef(sha=_support.ADJUDICATED_HEAD),
            ))
        run_options.setdefault("fork_points", _support.REPLAY_FORK_POINTS)
        run_options.setdefault("added_lines", PAST_THE_CEILING)
        run_options.setdefault("push_branch", True)
        with patch.object(config, MAX_ADDED_LINES, CEILING):
            mocks = self._run_with_merge(github, issue, **run_options)[0]
        return _Replay(github, mocks)

    def _assert_carried(self, replay: _Replay) -> None:
        """The exemption is on the replayed commit, and the push carried it."""
        replay.mocks[COUNT_ADDED_LINES].assert_not_called()
        pinned = replay.pinned
        self.assertEqual(pinned[_exemption.LATE_EXEMPT_SHA], _support.REPLAYED_HEAD)
        self.assertEqual(
            pinned[_rewrites.LATE_REWRITE_PHASE],
            _rewrites.LateRewritePhase.PUBLISHED,
        )
        self.assertEqual(
            pinned[_rewrites.LATE_REWRITE_KIND],
            _rewrites.LateRewriteKind.CONFLICT_REBASE,
        )
        pushed = replay.pushes.call_args.kwargs
        self.assertEqual(pushed[REVISION], _support.REPLAYED_HEAD)
        self.assertEqual(pushed[LEASE], _support.ADJUDICATED_HEAD)
        self.assertIn(
            (_support.CONFLICT_ISSUE, LABEL_VALIDATING), replay.github.label_history,
        )

    def _assert_adjudicated_afresh(self, replay: _Replay) -> None:
        """Nothing was carried, and the ordinary ceiling took the issue."""
        replay.mocks[COUNT_ADDED_LINES].assert_called_once()
        pinned = replay.pinned
        self.assertEqual(pinned[_exemption.LATE_EXEMPT_SHA], _support.ADJUDICATED_HEAD)
        self.assertNotIn(_rewrites.LATE_REWRITE_KIND, pinned)
        replay.pushes.assert_not_called()
        self.assertIn(
            (_support.CONFLICT_ISSUE, LABEL_DECOMPOSING), replay.github.label_history,
        )

    def _assert_left_alone(self, replay: _Replay) -> None:
        """Nothing reached the remote, and the exemption never moved."""
        replay.pushes.assert_not_called()
        pinned = replay.pinned
        self.assertEqual(pinned[_exemption.LATE_EXEMPT_SHA], _support.ADJUDICATED_HEAD)
        self.assertTrue(pinned[AWAITING_HUMAN])


class ConflictRebaseTransferTest(_ConflictReplayCase, unittest.TestCase):
    """A replay that left the adjudicated contribution exactly as it was."""

    def test_a_history_only_rebase_carries_it(self) -> None:
        # The whole point of the seam: the branch is replayed onto a base that
        # moved, the accepted object stops existing on it, and the change a
        # human ruled on is recognized in the commit that replaced it rather
        # than measured past the same ceiling and adjudicated again.
        self._assert_carried(self._replayed())

    def test_a_crash_before_the_grant_still_carries(self) -> None:
        # The earlier of the two crash windows: the replay ran and the tick
        # died before the size gate could persist a permission for it. Nothing
        # about the branch says a rebase put that commit there -- what does is
        # the account the replay wrote about itself, before it ran and again
        # once there was a commit to name.
        self._assert_carried(self._recovered(seeded=_support.replayed_state()))

    def test_a_crashed_grant_settles_on_the_recovery(self) -> None:
        # The later window, past the grant. The record the replay left is
        # spent by then, so what answers this tick is the permission itself,
        # re-asked in full over the terms it was granted on rather than
        # believed.
        self._assert_carried(self._recovered(seeded=_support.granted_state()))

    def test_the_pair_it_replaced_is_recorded(self) -> None:
        # The evidence is what a later reader re-derives the equality from,
        # so both ends of both contributions go down rather than the digest
        # alone -- over the two fork points, which is what says the bases
        # really moved.
        pinned = self._replayed().pinned

        self.assertEqual(
            pinned[_rewrites.LATE_REWRITE_FROM_SHA], _support.ADJUDICATED_HEAD,
        )
        self.assertEqual(
            pinned[_rewrites.LATE_REWRITE_FROM_BASE_SHA],
            _support.REPLAY_FORK_POINTS[_support.ADJUDICATED_HEAD],
        )
        self.assertEqual(
            pinned[_rewrites.LATE_REWRITE_TO_BASE_SHA],
            _support.REPLAY_FORK_POINTS[_support.REPLAYED_HEAD],
        )
        self.assertEqual(
            pinned[_rewrites.LATE_REWRITE_LEASE], _support.ADJUDICATED_HEAD,
        )


class ConflictRebaseRefusalTest(_ConflictReplayCase, unittest.TestCase):
    """Every record the permit refuses, and the reading it falls back to.

    None of them parks: a refusal leaves the exemption exactly where the
    adjudication put it and hands the commit to the ordinary cumulative gate,
    which past the ceiling is the second adjudication the transfer exists to
    spare a change that really did survive.
    """

    def test_a_changed_byte_is_adjudicated_afresh(self) -> None:
        # The permit is a claim about the CONTRIBUTION rather than about the
        # rebase having run. A replay that picked anything up fingerprints to
        # something else and falls through to the ordinary cumulative gate --
        # which past the ceiling is a second adjudication.
        self._assert_adjudicated_afresh(self._replayed(
            contribution_digest={_support.REPLAYED_HEAD: _support.OTHER_DIGEST},
        ))

    def test_a_fork_point_nothing_read_refuses(self) -> None:
        # A reading that did not happen is not a base. Taken as one, both
        # contributions would be fingerprinted over a range that means
        # nothing and the two digests would agree by construction.
        self._assert_adjudicated_afresh(self._replayed(fork_points=""))

    def test_an_exemption_naming_no_change_stays(self) -> None:
        # The exact-SHA exemption goes on exempting exactly the commit it
        # names, whatever is missing beside it -- and a commit that is not on
        # this branch any more exempts nothing this push is about.
        for case, damaged in _support.UNTRANSFERABLE_EXEMPTIONS.items():
            with self.subTest(case=case):
                self._assert_adjudicated_afresh(self._replayed(
                    seeded=_support.adjudicated_state(
                        identity=bool(damaged), damaged=damaged,
                    ),
                ))


class ConflictUnclaimedPushTest(_ConflictReplayCase, unittest.TestCase):
    """The pushes here that hand the gate no rewrite at all.

    Each carries a commit its caller did not make, so none of them can say
    whether what it is publishing replays anything -- and a caller that cannot
    say presents nothing rather than a claim the fingerprints would have to
    settle.
    """

    def test_an_agent_resolution_presents_no_evidence(self) -> None:
        # Content somebody wrote is not a replay of content somebody ruled
        # on, so the resolution is measured like any other candidate.
        self._assert_adjudicated_afresh(self._published(
            merge_succeeded=False,
            conflicted_files=[CONFLICT_FILE],
            head_shas=[_support.ADJUDICATED_HEAD, _support.REPLAYED_HEAD],
        ))

    def test_an_unrecorded_recovery_is_measured(self) -> None:
        # A commit made ON TOP of the publication, which is what an agent's
        # resolution and the `fixing` reroute's fix commits leave: the remote's
        # head is still an ancestor, so nothing here is a replay of it. Their
        # contribution fingerprints to the accepted one, which is exactly the
        # case a probe of the branch would wave through -- and what refuses it
        # is that no record names the commit in hand.
        for case, behind in _UNRECORDED_RECOVERIES.items():
            with self.subTest(case=case):
                self._assert_adjudicated_afresh(self._recovered(
                    behind_base=behind, branch_ahead_behind=COMMITTED_ON_TOP,
                ))


class ConflictUnprovableDivergenceTest(
    _ConflictReplayCase, unittest.TestCase,
):
    """A diverged branch this stage cannot account for is never published.

    A replay leaves the checkout ahead of its publication AND behind it, which
    is the same reading a stale branch carrying somebody else's commit gives.
    The record is the only thing that tells them apart, so where it cannot be
    read -- or is about some other publication -- the conservative park stands
    and nothing is force-pushed over the pull request.
    """

    def test_a_repointed_pull_request_stays_parked(self) -> None:
        # A rewrite is evidence about the ONE publication it was made against,
        # and `pr_number` is a field a later tick can find pointing somewhere
        # else. Read live rather than off the record, this replay would be
        # offered as a rewrite of whatever pull request the issue records now
        # -- and another open one standing on the same head would satisfy
        # every check the permit makes and take the exemption with it.
        self._assert_left_alone(self._recovered(
            seeded={**_support.replayed_state(), KEY_PR_NUMBER: OTHER_PR},
            other_pr=OTHER_PR,
        ))

    def test_a_damaged_replay_record_stays_parked(self) -> None:
        # Read whole or not at all, like every other record in this domain: a
        # group short of a member, or carrying a value no writer here would
        # have written, describes a replay nothing can check -- and a
        # divergence nothing accounts for may not be overwritten.
        for case, damage in _support.UNUSABLE_REPLAYS.items():
            with self.subTest(case=case):
                self._assert_left_alone(
                    self._recovered(seeded=_support.replayed_state(**damage)),
                )


class ConflictUnpublishedReplayTest(_ConflictReplayCase, unittest.TestCase):
    """The two readings that stop a replay before anything reaches the remote."""

    def test_a_publication_that_moved_carries_nothing(self) -> None:
        # Somebody else's push landing mid-tick. The two readings of the head
        # this replay is leased against disagree, so nothing is measured and
        # nothing is published.
        self._assert_left_alone(self._replayed(pr_head=MOVED_PR_HEAD_SHA))

    def test_a_dirty_checkout_publishes_nothing(self) -> None:
        # The tree a push would publish from is not the tree anything here
        # read, so this stage refuses before the gate is reached at all.
        self._assert_left_alone(self._replayed(dirty_files=(DIRTY_PATH,)))


if __name__ == "__main__":
    unittest.main()
