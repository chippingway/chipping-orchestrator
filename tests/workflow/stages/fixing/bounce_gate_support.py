# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The no-feedback bounce, driven with the post-publication size gate on.

The bounce is the one tick left that can publish a commit an earlier fixing
round stranded on the branch, and no agent runs on it: the reviewer feedback
that opened the round is orchestrator-authored, so every rescan filters it out.
That makes it a seam a candidate reaches a published pull request through with
nothing behind it having measured what the pull request would come to -- which
is what the fixture here seeds the gate in front of.

It shares the stranded fixture the route's other tests use and adds only what
a gated tick needs: the ceiling, the pinned fields a hold is handed to the
adjudication under, and the one window a closed pull request can arrive in.
"""

from __future__ import annotations

from tests.workflow import fixtures
from tests.workflow.stages.fixing import (
    fixing_test_support as support,
    published_gate_support as _published_gate,
)

MEASURED_BASE_SHA = fixtures.MEASURED_BASE_SHA
LABEL_DECOMPOSING = fixtures.LABEL_DECOMPOSING

# What each seeded probe answer is called where a case reads it back.
AHEAD_BEHIND = "branch_ahead_behind"
ADDED_LINES = "added_lines"
CANDIDATE_COMMIT = "candidate_commit"
FETCHED_TIP = "fetched_branch_tip"
HEAD_SHAS = "head_shas"

# The commit the gate proves a checkout to, for a case that has the branch
# probe and that proof read one worktree a moment apart.
FrozenCommit = _published_gate.FrozenCommit

# The head the stranded proof is taken against, which is the head the pull
# request is standing on: the fetch is what makes the local ref agree with the
# remote, so the two are one fact.
PUBLICATION_HEAD = support.PR_HEAD_SHA

# The commit the stranded round left in the checkout, which is the head the
# gate proves that checkout to.
STRANDED_CANDIDATE = support.SHA_AFTER

# A head somebody else pushed between the stranded proof and this tick.
MOVED_HEAD = "ab" * (fixtures.SHA_LENGTH // 2)

# How far ahead of its publication the branch is: one stranded commit, and a
# round that was killed several commits in.
ONE_COMMIT = (1, 0)
SEVERAL_COMMITS = (3, 0)

# The branch a landed push leaves behind -- level with its publication, which
# is what stops a second bounce republishing and counting again.
NOTHING_AHEAD = (0, 0)

# The pinned fields a held candidate is handed to the adjudication under.
KEY_ADDITIONS = "late_additions"
KEY_BASE_SHA = "late_base_sha"
KEY_CANDIDATE_SHA = "late_candidate_sha"
KEY_PUBLISHED_SHA = "late_published_sha"
KEY_SOURCE_STAGE = "late_source_stage"

# The receipt a landed gated push leaves: the commit that reached the remote,
# the head it replaced, and the pull request it went onto. All three go down
# on every receipt, so `published_gate_support.receipt_group` beside this is
# what a fixture seeds one with.
KEY_RECEIPT_SHA = "implementing_published_sha"
KEY_RECEIPT_LEASE = "implementing_published_lease"
KEY_RECEIPT_PR = "implementing_published_pr"
receipt_group = _published_gate.receipt_group

# What a measured candidate whose push missed leaves instead: the commit still
# owed a publication, the head that push is pinned to, and the bookkeeping the
# tick that finally lands it has to close on this route's behalf.
KEY_APPROVED_SHA = "late_approved_sha"
KEY_APPROVED_LEASE = "late_approved_lease"
KEY_SPENDS = "late_spends"

PARK_MEASUREMENT_FAILED = "late_measurement_failed"

COUNT_ADDED_LINES = "_count_added_lines"
GET_PR = "get_pr"

# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"

CEILING = 5
UNDER_THE_CEILING = 4
PAST_THE_CEILING = 6
MAX_ADDED_LINES = "MAX_ADDED_LINES"
DECOMPOSE = "DECOMPOSE"

# The round the stranded fixture seeds, and the one a published fix spends.
SEEDED_ROUND = 2
SPENT_ROUND = 3


class _ClosedUnderTheProbe:
    """A pull request somebody closes while this tick is probing the branch.

    The only window the closed-pull-request refusal is reachable in on this
    seam. The preflight reads the pull request first and drains a closed one
    to a terminal before the bounce is reached, so the state the gate refuses
    on can only arrive between that read and the gate's own -- and the fetch
    and the ahead/behind proof are what fill it.
    """

    def __init__(self, github, number: int) -> None:
        self._read_pull_request = github.get_pr
        self._number = number
        self._reads = 0

    def __call__(self, number: int):
        pull_request = self._read_pull_request(number)
        self._reads += 1
        if self._reads > 1 and number == self._number:
            pull_request.state = fixtures.STATE_CLOSED
        return pull_request


class _GatedBounceMixin(support._StrandedFixingFixtureMixin):
    """One no-feedback bounce over a stranded commit, gate on."""

    def _bounce(self, scenario, **run_options):
        """The whole fixing tick that reaches the no-feedback exit.

        The branch is one commit ahead of its publication unless a case says
        otherwise, because that is the shape the exit exists for: a fix an
        earlier round committed and never pushed.
        """
        run_options.setdefault(AHEAD_BEHIND, ONE_COMMIT)
        with support.patch.object(support.config, DECOMPOSE, True):
            return self._run_stranded_bounce(
                scenario.github, scenario.issue, support.TEMP_ROOT,
                **run_options,
            )

    def _seed_gated_bounce(self, **extra_state):
        """The stranded `fixing` issue every case here starts from."""
        github, issue = self._seed_stranded_bounce()
        if extra_state:
            github.seed_state(
                support.ISSUE, **{**github.pinned_data(support.ISSUE), **extra_state},
            )
        return support.IssueScenario(github, issue)

    def _pinned(self, scenario) -> dict:
        """What the pinned comment says once this tick has finished."""
        return scenario.github.pinned_data(support.ISSUE)

    def _assert_pushed_once(self, mocks):
        """One push went out, reported so its keywords can be read off it."""
        pushed = mocks[support.PUSH_BRANCH]
        pushed.assert_called_once()
        return pushed.call_args

    def _assert_bounced(self, scenario, *, round_n: int) -> None:
        """The bounce landed: bookmarks dropped, back to `validating`."""
        pinned = self._pinned(scenario)
        self.assertEqual(pinned[support.REVIEW_ROUND], round_n)
        self.assertIsNone(pinned[support.PENDING_FIX_REVIEWER_COMMENT_ID])
        self.assertIn(
            (support.ISSUE, support.VALIDATING), scenario.github.label_history,
        )

    def _assert_held(self, scenario, mocks) -> None:
        """Nothing pushed, and the issue not handed on for another review."""
        mocks[support.PUSH_BRANCH].assert_not_called()
        self.assertNotIn(
            (support.ISSUE, support.VALIDATING), scenario.github.label_history,
        )
