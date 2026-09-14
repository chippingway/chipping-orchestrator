# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One snapshot decides both halves of the recorded pull request's question.

This stage asks two things about the pull request its record names, and they
are different facts about the same object. The HEAD says what it IS -- the
`discussion` stage's plan while it still stands on the commit that publication
put there, this stage's own work once anything here has pushed over it. The
STATE says what to DO about it -- `done` for a merge, `rejected` for a close
nobody merged.

A human can move either at any moment, so reading them apart is reading two
moments. Classified on one snapshot and finalized on another, a plan the
humans merged is closed `done` as delivered work, with no developer having
run and a design document standing in for the build.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import terminal_reading as _terminal_reading
from tests.support.fakes import FakePRRef
from tests.workflow.fixtures import (
    LABEL_DONE,
    LABEL_VALIDATING,
    _issue_branch,
)
from tests.workflow.interleaving import _RacesPastTheStep
from tests.workflow.stages.implementing import (
    plan_handoff_test_support as support,
)
from tests.workflow.stages.implementing.read_only_relabel_test_support import (
    HEAD_AFTER_COMMIT,
    HEAD_BEFORE_ROUND,
)

# The step this whole module is about: the one guarded reading of the recorded
# pull request. A case hangs its transition on the far side of it, which is
# where a second fetch would have been.
_PULL_REQUEST_FACTS = "_pull_request_facts"

_RACE_ISSUE_NUMBER = 8410


class PlanTransitionRaceTest(support._HandoffTickMixin, unittest.TestCase):
    """What a pull request that moves mid-tick may not buy.

    Driven through the whole handler rather than at the reading, because what
    the two answers reach are different effects -- one lets the tick carry on
    to a developer, the other closes the issue -- and only a run says which
    one a moved snapshot actually got.
    """

    def test_a_moved_head_finalizes_nothing(self) -> None:
        # The tick opens on a pull request this stage has already pushed over:
        # its head is not the recorded plan commit, so it is an implementation
        # and the terminals may decide on it. The instant that reading is
        # taken, a human rewinds it onto the plan commit and merges it.
        #
        # Read once, the tick answers on the snapshot it actually read: an
        # open implementation, so nothing is finalized and the committed work
        # is handed to review as it would have been. Read twice -- classify on
        # the head, finalize on the state -- the second read is a merged pull
        # request standing on the plan, and the issue is closed `done` over a
        # design document with no developer having run.
        github, issue = support._seed_accepted_handoff(
            _RACE_ISSUE_NUMBER,
            head_sha=HEAD_AFTER_COMMIT,
            merged=False,
        )

        self._raced(github, issue)

        self.assertNotIn(
            (_RACE_ISSUE_NUMBER, LABEL_DONE), github.label_history,
        )
        self.assertIn(
            (_RACE_ISSUE_NUMBER, LABEL_VALIDATING), github.label_history,
        )

    def _raced(self, github, issue):
        """Run one tick, rewinding and merging the plan PR as it is read."""
        with patch.object(
            _terminal_reading,
            _PULL_REQUEST_FACTS,
            _RacesPastTheStep(
                _terminal_reading._pull_request_facts,
                lambda: _settled_onto_the_plan(github),
            ),
        ):
            return self._run_handoff_tick(
                github,
                issue,
                unpushed_branch=_issue_branch(_RACE_ISSUE_NUMBER),
                has_new_commits=True,
                branch_tip_sha=HEAD_BEFORE_ROUND,
                head_shas=(
                    HEAD_BEFORE_ROUND,
                    HEAD_BEFORE_ROUND,
                    HEAD_AFTER_COMMIT,
                ),
            )


def _settled_onto_the_plan(github) -> None:
    """What a human does in the window: rewind onto the plan, then merge it.

    Both halves, because either alone leaves one of the two readings agreeing
    with the other: a merge without the rewind is an implementation the
    terminal is right to finalize, and a rewind without the merge is a plan
    nothing would finalize anyway.
    """
    pull_request = github.get_pr(support.HANDOFF_PR_NUMBER)
    pull_request.head = FakePRRef(sha=support.PLAN_COMMIT)
    pull_request.merged = True
    pull_request.state = support.STATE_CLOSED


if __name__ == "__main__":
    unittest.main()
