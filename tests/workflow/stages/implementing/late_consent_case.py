# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A parked implementation, its live state, and the gate or tick a reply resumes.

The assertions beside the fixture are the ones every case about a park asks of
a whole tick -- what it spent, what it published, and where it left the issue
-- so the modules that drive this park through the handler read the same
answers off the same client rather than each spelling its own.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import (
    PinnedState,
)
from orchestrator.workflow.engine import content_hash as _content_hash
from orchestrator.workflow.stages.implementing import (
    late_command as _command,
    late_gate_models as _late_gate_models,
    state as _state,
)
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_IMPLEMENTING,
    LABEL_VALIDATING,
    MEASURED_CANDIDATE_SHA,
    _agent,
    _PatchedWorkflowMixin,
    _reported,
    _stand_opened_prs_on_the_push,
)
from tests.workflow.report_values import _recovered_report
from tests.workflow.stages.implementing import (
    late_consent_comments as _consent_comments,
    late_consent_payloads as _consent_payloads,
)

_USER_CONTENT_HASH = "user_content_hash"


class _ParkedTickAssertions:
    """What one whole tick over a parked issue spent, published and left.

    Beside the fixture rather than in the module that drives it, because the
    answers are the same wherever the park is driven from: a road is what it
    pushed, what it said, where it put the label and what the pinned comment
    holds afterwards.
    """

    def _assert_still_parked(self) -> None:
        """The park exactly as it was: somebody waiting, behind this question."""
        pinned = self._pinned()
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertEqual(
            pinned[_state._PARK_REASON], _command.PARK_UNAUTHORIZED_EXEMPTION,
        )

    def _assert_no_agent(self, mocks) -> None:
        """No developer was paid for on this tick, whatever else it decided."""
        mocks[_consent_payloads.RUN_AGENT].assert_not_called()

    def _assert_held(self, mocks) -> None:
        """The tick spent nothing and moved the issue nowhere."""
        self._assert_no_agent(mocks)
        mocks[_consent_payloads.PUSH_BRANCH].assert_not_called()
        self.assertEqual(self.github.label_history, [])

    def _assert_published(
        self, mocks, revision: str = MEASURED_CANDIDATE_SHA,
    ) -> None:
        """The branch went out named against `revision`, and nobody was resumed.

        The commit is half of the assertion because the push is where a
        checkout that moved would show: named against nothing it would carry
        whatever the worktree had become, under a record naming the commit the
        park was about.

        The label is the other half of "published" rather than a detail of it.
        A push moves a branch; what ends this stage's hold on the issue is the
        handoff behind it, and a road that pushed and never relabelled leaves
        committed work on a remote nobody downstream will look at.

        Which is asserted as the WHOLE transition history and as the label the
        issue is wearing, rather than as a membership test. One write of
        `workflow:validating` and no other: a road that moved the label and
        then wrote over it, or one that moved it twice, satisfies a
        membership test while leaving the issue under whatever the last write
        said -- and the dispatcher routes by the label the issue wears.
        """
        self._assert_no_agent(mocks)
        pushed = mocks[_consent_payloads.PUSH_BRANCH]
        pushed.assert_called_once()
        self.assertEqual(
            pushed.call_args.kwargs[_consent_payloads.REVISION], revision,
        )
        self.assertEqual(
            self.github.label_history,
            [(_consent_payloads.ISSUE_NUMBER, LABEL_VALIDATING)],
        )
        self.assertEqual(
            self.github.workflow_label(self.issue), LABEL_VALIDATING,
        )
        self._assert_delivery_receipt(revision, pushed.call_args.kwargs)

    def _assert_delivery_receipt(self, revision: str, pushed: dict) -> None:
        """The pull request this stage opened, and the whole receipt naming it.

        All three members, because the receipt is read as a GROUP. The commit
        alone reads the same on a branch a revert rewound onto work this issue
        published rounds ago; the head that push replaced dates it to this
        attempt; and the number says which pull request now carries the work,
        without which a reader falls back to a lookup by branch and answers
        with whatever is open on that ref. `pr_number` beside them is the
        relabel's own write, and the announcement is what a human is left
        able to find the pull request by.

        The lease is held to what the push was actually leased against rather
        than to a value of its own, which on every road this park reaches is
        NOTHING: the pull request is opened by that push, so no head was
        frozen for the receipt to be scoped to. What it catches here is a
        build recording one anyway -- a receipt claiming a superseded head
        that never existed, dating it to an attempt nobody made. The roads
        that do record a head are the ones a branch was already published on,
        and they are `test_late_receipt`'s.

        The remote is asserted too. The poll after a publication reads the
        pull request's head to tell one this issue made from a branch somebody
        else moved, so a fixture leaving it anywhere but on the pushed commit
        would make every later reading disagree with this tick.
        """
        self.assertEqual(len(self.github.opened_prs), 1)
        opened = self.github.opened_prs[0]
        self.assertEqual(opened.head.sha, revision)
        announced = _consent_payloads.PR_OPENED.format(number=opened.number)
        self.assertTrue(any(
            announced in body for _, body in self.github.posted_comments
        ))
        published = self._pinned()
        self.assertEqual(
            published[_consent_payloads.KEY_PUBLISHED_SHA], revision,
        )
        self.assertEqual(
            published[_consent_payloads.KEY_PUBLISHED_PR], opened.number,
        )
        self.assertEqual(
            published[_consent_payloads.KEY_PUBLISHED_LEASE],
            pushed[_consent_payloads.FORCE_WITH_LEASE],
        )
        self.assertEqual(
            published[_consent_payloads.KEY_PR_NUMBER], opened.number,
        )

    def _assert_wrote_nothing(self) -> None:
        """Nothing was said and nothing was persisted, over one whole tick.

        The write count as well as the record, because the two answer
        different questions: the record says the tick changed nothing, and the
        count says it never reached a write at all -- which is what a hold
        taken before the seam promises and a rollback after one cannot.
        """
        self.assertEqual(self.github.posted_comments, [])
        self.assertEqual(self.github.write_state_calls, 0)


class _ParkedCase(
    _consent_comments._ConsentComments,
    _ParkedTickAssertions,
    _PatchedWorkflowMixin,
):
    """An issue holding one adjudicated candidate nobody has authorized."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(_consent_payloads.ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        self.github.seed_state(_consent_payloads.ISSUE_NUMBER)
        self._seed()

    def _seed(self, *, parked: bool = True, **state) -> None:
        """Replace the pinned comment with the one a case is about.

        `parked=False` is the same issue with nothing standing on it, which is
        what the cases about ENTERING this park are seeded with.
        """
        standing = {
            _state._AWAITING_HUMAN: True,
            _state._PARK_REASON: _command.PARK_UNAUTHORIZED_EXEMPTION,
        } if parked else {}
        self.github.seed_state(_consent_payloads.ISSUE_NUMBER, **{
            _state._LAST_ACTION_COMMENT_ID: _consent_payloads.PRIOR_ACTION_COMMENT_ID,
            # The requirements baseline a real park carries: the thread as it
            # had been read, so a reply moves the hash as in production.
            _USER_CONTENT_HASH: _content_hash._compute_user_content_hash(
                self.issue, set(), comments=[
                    seen for seen in self.issue.comments
                    if seen.id <= _consent_payloads.PRIOR_ACTION_COMMENT_ID
                ],
            ),
            _consent_payloads.KEY_EXEMPT_SHA: MEASURED_CANDIDATE_SHA,
            # The report of the run that committed this candidate, which every
            # tick over already-committed work carries: without one the stage
            # holds the work rather than measuring it.
            **_recovered_report(self.issue),
            **standing,
            **state,
        })

    def _pinned(self) -> dict:
        return self.github.pinned_data(_consent_payloads.ISSUE_NUMBER)

    def _run_tick(self, worktree: Path = _consent_payloads.TEMP_WORKTREE_ROOT, **run_options):
        """Run one whole implementing tick over this parked issue.

        The seams the recovery hands its answer to are the real ones, which is
        the only way a case can see what the publication below does to a park
        it was entered under.

        A pull request this tick opened is left standing on the commit the
        push carried, because the remote is where the poll after a publication
        reads one from: left at the double's default head it would say this
        issue's own branch had been moved by somebody else, and the next tick
        would refuse the very publication this one made.
        """
        run_options.setdefault("has_new_commits", True)
        # Past the ceiling by default, because that is the reading this park
        # exists for: a candidate the gate measures small needs nobody's
        # authorization and publishes on its own count.
        run_options.setdefault("added_lines", _consent_payloads.OVERSIZED_ADDITIONS)
        run_options.setdefault(
            "run_agent", _agent(last_message=_reported()),
        )
        # Re-stamped here rather than at the seed, because a case that posts a
        # command or a reply moves the requirements the issue reads at, and a
        # record naming an older revision is a human editing mid-run -- which
        # holds the report rather than publishing it.
        self.github.seed_state(_consent_payloads.ISSUE_NUMBER, **{
            **self._pinned(), **_recovered_report(self.issue),
        })
        opened_before = len(self.github.opened_prs)
        with patch.object(
            _worktree_paths, _consent_payloads.WORKTREE_PATH, return_value=worktree,
        ):
            mocks = self._run_implementing(
                self.github, self.issue, **run_options,
            )
        _stand_opened_prs_on_the_push(self.github, mocks, opened_before)
        return mocks

    def _gate(self, state: PinnedState | None = None, **entered):
        """The gate call this park was taken on, or is being answered from."""
        return _late_gate_models._Gate(
            gh=self.github,
            spec=_TEST_SPEC,
            issue=self.issue,
            state=self._state() if state is None else state,
            worktree=_consent_payloads.WORKTREE,
            **entered,
        )
