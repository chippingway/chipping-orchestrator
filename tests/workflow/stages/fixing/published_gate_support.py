# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One whole tick whose dev run commits onto a pull request that is already open.

The fixture the post-publication size gate's contract is driven through. The
`fixing` in_review route, because it is the shortest road to the shared dev-fix
publication every gated push goes through: one unread comment past the debounce
window resumes the locked session, the run commits, and everything after that
is the gate and the push it either allows or holds.

It is a `fixing` scenario and lives with that route's own fixture, whatever it
is used to exercise: what it seeds and runs is this stage's handler, so keeping
it here is what stops the tests of another stage's owner reaching across a
package boundary for it.
"""

from __future__ import annotations

import importlib

# The frozen commit and the worktree status a case seeds the gate with.
# Every case names this module `support` and reads them off it, so the
# same-name alias is what declares the import a re-export rather than a
# dead one -- the same reason the mid-run effects below carry one.
from orchestrator.git.measurement.models import (
    FrozenCommit as FrozenCommit,
    MeasurementFailure as MeasurementFailure,
)
from orchestrator.git.verification.status import _WorktreeStatus as _WorktreeStatus
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.late_split import (
    phases as _late_phases,
    publication as _publication_context,
    state as _late_state,
)
from orchestrator.workflow.late_split.models import LateGeneration
from tests.workflow import fixtures

# The four things a case can have happen to the pull request while the dev
# run is out, reached off this module through the same door.
from tests.workflow.mid_run_effects import (
    _BreaksThePullRequest as _BreaksThePullRequest,
    _ClosesThePullRequest as _ClosesThePullRequest,
    _MovesThePullRequest as _MovesThePullRequest,
    _RelabelsTheIssue as _RelabelsTheIssue,
)
from tests.workflow.stages.fixing import fixing_test_support as support

MEASURED_BASE_SHA = fixtures.MEASURED_BASE_SHA
MEASURED_CANDIDATE_SHA = fixtures.MEASURED_CANDIDATE_SHA
LABEL_DECOMPOSING = fixtures.LABEL_DECOMPOSING

# A state with an edge to the adjudication and no pull request behind it,
# for the human relabel that lands while an agent is out.
LABEL_READY = fixtures.LABEL_READY

# The pinned keys a generation the size gate froze round-trips through, and
# the four the publication group is read back off.
KEY_CANDIDATE_SHA = "late_candidate_sha"
KEY_BASE_SHA = "late_base_sha"
KEY_THRESHOLD = "late_threshold"
KEY_ADDITIONS = "late_additions"
# What a reading the transport lost leaves on the pair it was owed for: the
# readings lost in a row, and -- once one of them has been announced -- the
# step the notice on the thread named.
KEY_MISS_COUNT = "late_measurement_miss_count"
KEY_MEASUREMENT_FAILURE = "late_measurement_failure"
KEY_PHASE = "late_phase"
KEY_APPROVED_SHA = "late_approved_sha"
KEY_APPROVED_LEASE = "late_approved_lease"
KEY_POST_PUBLICATION = "late_post_publication"
KEY_SOURCE_STAGE = "late_source_stage"
KEY_PUBLISHED_PR = "late_published_pr_number"
KEY_PUBLISHED_SHA = "late_published_sha"

# The receipt a landed gated push leaves, which is the implementing seam's
# own field rather than one of the group above: it names what this branch put
# on the remote, not what the reading was entered against.
KEY_RECEIPT_SHA = "implementing_published_sha"

# The head that receipt REPLACED, written with it and never on its own: what
# dates the receipt to one publication attempt, since the receipt itself is
# never cleared and goes on naming a commit pushed rounds ago.
KEY_RECEIPT_LEASE = "implementing_published_lease"

# The pull request that receipt went onto, written with it by the push that
# landed. Neither the commit nor the head it replaced says WHICH publication
# received the work, so a branch pushed from that head onto a pull request
# since closed and replaced answers for both.
KEY_RECEIPT_PR = "implementing_published_pr"


def receipt_group(sha: str, lease=None, pull_request=None) -> dict:
    """One whole publication receipt, ready to seed.

    The three fields a landed gated push writes, spelled together because the
    write is: every member goes down on every receipt, `null` included, so a
    fixture seeding one member alone would be a record no tick can produce --
    and a reader asked whether the group is sound is right to refuse it.
    """
    return {
        KEY_RECEIPT_SHA: sha,
        KEY_RECEIPT_LEASE: lease,
        KEY_RECEIPT_PR: pull_request,
    }

# The validating route's single replay anchor, cleared with its round.
KEY_REVIEWER_COMMENT_ID = "pending_fix_reviewer_comment_id"

PARK_MEASUREMENT_FAILED = "late_measurement_failed"
PARK_CANDIDATE_MOVED = "late_candidate_moved"
PHASE_MEASURING = "measuring"
EVENT_LATE_MEASUREMENT = "late_measurement"
EVENT_LATE_FAILURE = "late_failure"

COUNT_ADDED_LINES = "_count_added_lines"
FREEZE_BASE_COMMIT = "_freeze_base_commit"
BASE_OBJECT_PRESENT = "_base_object_present"
WORKTREE_PATH = "_worktree_path"

# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"

CEILING = 5
UNDER_THE_CEILING = 4
AT_THE_CEILING = 5
PAST_THE_CEILING = 6
MAX_ADDED_LINES = "MAX_ADDED_LINES"
DECOMPOSE = "DECOMPOSE"

# A head the pull request was not left standing on, for the tick that finds
# somebody else's push where the record froze one.
MOVED_HEAD = "ab" * (fixtures.SHA_LENGTH // 2)

# A commit the checkout went to while the push was out, for the races the
# publication boundary refuses on the far side of its own effect.
MOVED_AFTER_PUSH = "de" * (fixtures.SHA_LENGTH // 2)

# The commit an earlier tick of this issue froze and the checkout has since
# moved past, for the resumed developer whose fresh commit supersedes a
# record.
SUPERSEDED_CANDIDATE = "5c" * (fixtures.SHA_LENGTH // 2)

# A commit an EARLIER round of this issue put on the remote. The receipt names
# the last push this stage made and is never cleared, so it goes on naming
# this one for the rest of the issue's life -- which is what a case about a
# pull request rewound onto it needs.
STALE_RECEIPT = "7a" * (fixtures.SHA_LENGTH // 2)

# The head each successive round of a pull request grown one fix at a time
# leaves the checkout on. Spelled apart from every other commit here because a
# candidate the receipt already names is a republication rather than a fresh
# fix, and a round of growth is about the fix nobody has measured yet.
GROWN_CANDIDATES = tuple(
    marker * (fixtures.SHA_LENGTH // 2) for marker in ("a1", "b2", "c3")
)


def recorded_generation(*, stage: str = support.FIXING, **overrides) -> dict:
    """The pinned fields a post-publication generation is retried from.

    Written through the domain's own writer rather than spelled as a dict, so
    a test seeding a crash between the freeze and the count seeds exactly what
    the freeze would have left behind -- the publication it was entered on
    included, which is what the retry proves the pull request has not moved
    against.

    The stage is a parameter because it is a TERM of the reading rather than a
    detail of it: all five that publish onto a pull request the remote already
    carries can be left holding a pair, and the reading is re-entered only on
    the one the issue is still wearing.
    """
    recorded = PinnedState(data={})
    _late_state.write_late_generation(
        recorded,
        LateGeneration(**{
            "cycle_id": 1,
            "generation": 1,
            "root_issue": support.ISSUE,
            "current_issue": support.ISSUE,
            "lineage_depth": 0,
            "candidate_sha": MEASURED_CANDIDATE_SHA,
            "base_sha": MEASURED_BASE_SHA,
            "threshold": CEILING,
            "phase": _late_phases.LatePhase.MEASURING,
            **overrides,
            "publication": _publication_context.PublicationContext.enter(
                stage=stage,
                pr_number=support.PR_NUMBER,
                published_sha=support.PR_HEAD_SHA,
            ),
        }),
    )
    return recorded.data


class _RecordAtNotice:
    """What the pinned comment says at the moment a notice is posted.

    A park posts its mention and leaves the flags to the write behind it, so
    durable state read once the tick is over cannot tell a record written
    ahead of the notice from one written after it. This reads it as it stood
    then.
    """

    def __init__(self, github) -> None:
        self.pinned: dict = {}
        self._github = github
        self._wrapped = github.comment

    def __call__(self, *called, **options):
        self.pinned = dict(self._github.pinned_data(support.ISSUE))
        return self._wrapped(*called, **options)

    def held(self):
        """Patch the comment this records, for the duration of one tick."""
        return support.patch.object(self._github, "comment", self)


class _SizeGateAssertionsMixin:
    """What a tick that went through the gate looks like afterwards."""

    def _pinned(self, scenario) -> dict:
        """What the pinned comment says once this tick has finished."""
        return scenario.github.pinned_data(support.ISSUE)

    def _assert_unpushed(self, mocks) -> None:
        """Nothing reached the remote on this tick."""
        mocks[support.PUSH_BRANCH].assert_not_called()

    def _assert_pushed_once(self, mocks):
        """One push went out, reported so its keywords can be read off it."""
        pushed = mocks[support.PUSH_BRANCH]
        pushed.assert_called_once()
        return pushed.call_args

    def _assert_settled_publication(self, mocks) -> None:
        """The leased no-op a publication the remote already carries makes.

        Named and pinned at the same commit, which is what makes the request
        the atomic proof it exists to be: the pull request is standing on the
        commit, so git has nothing to send and rejects outright if somebody
        moved it between the freeze and here.
        """
        pushed = self._assert_pushed_once(mocks)
        self.assertEqual(pushed.kwargs[REVISION], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pushed.kwargs[LEASE], MEASURED_CANDIDATE_SHA)

    def _assert_unmeasured(self, mocks) -> None:
        """No reading was taken -- the candidate was decided about already."""
        mocks[COUNT_ADDED_LINES].assert_not_called()

    def _assert_held(self, scenario, mocks) -> None:
        """Nothing pushed, and the issue not handed on for another review."""
        self._assert_unpushed(mocks)
        self.assertNotIn(
            (support.ISSUE, support.VALIDATING), scenario.github.label_history,
        )

    def _assert_parked(self, scenario) -> None:
        pinned = self._pinned(scenario)
        self.assertTrue(pinned[support.AWAITING_HUMAN])
        self.assertEqual(pinned[support.PARK_REASON], PARK_MEASUREMENT_FAILED)
        self.assertEqual(scenario.github.label_history, [])


class _SizeGateFixtureMixin(support._FixingFixtureMixin, _SizeGateAssertionsMixin):
    """The seed and the run one fix round through the gate is driven by."""

    def _seed_fix_round(self, *, pr_head: str = support.PR_HEAD_SHA, **extra_state):
        """One fix round, with the head its pull request is standing on.

        `pr_head` is a parameter because a pull request already standing on
        the commit in hand is a state of its own rather than a variation: a
        push there would move nothing, so what a tick can still owe it is the
        bookkeeping behind a publication that has already happened.
        """
        long_ago = support.datetime.now(support.timezone.utc) - support.timedelta(
            hours=1,
        )
        feedback = support.FakeComment(
            id=support.TRIGGER_ID,
            body=support.FIX_FEEDBACK,
            user=support.FakeUser(support.ALICE),
            created_at=long_ago,
        )
        return support.IssueScenario(*self._seed(
            pr=self._open_pr(head=support.FakePRRef(sha=pr_head)),
            issue_comments=[feedback],
            extra_state=extra_state or None,
        ))

    def _run_fix_round(self, scenario, **run_options):
        run_options.setdefault(
            "run_agent",
            support._agent(
                session_id=support.DEV_SESSION,
                last_message=support.PUSHED_FIX_MESSAGE,
            ),
        )
        run_options.setdefault(
            "head_shas", (support.SHA_BEFORE, support.SHA_AFTER),
        )
        with support.patch.object(
            support.config, support.DEBOUNCE_CONFIG, support.DEBOUNCE_SECONDS,
        ):
            return self._run_fixing(
                scenario.github, scenario.issue, **run_options,
            )

    def _poll(self, scenario, **run_options):
        """One ordinary poll of this issue: whether the stage ran, and what read.

        The reading a frozen pair is owed is taken ahead of every stage
        handler rather than inside one, so a SECOND poll of the same issue
        only reaches it this way -- and reaching it is the point: what a
        record nobody has measured must never buy is the stage below running
        over it. So the handler is mocked out and the first half of the answer
        is whether it was reached at all.
        """
        run_options.setdefault("run_agent", support._agent())
        owner_name, named = _stage_targets._STAGE_HANDLER_TARGETS[support.FIXING]
        with support.patch.object(
            importlib.import_module(owner_name), named,
        ) as dispatched, support.patch.object(
            _worktree_paths, WORKTREE_PATH, return_value=support.TEMP_ROOT,
        ):
            mocks = self._run(
                lambda: _issue_processing._route_issue_to_handler(
                    scenario.github, fixtures._TEST_SPEC, scenario.issue,
                    scenario.github.workflow_label(scenario.issue),
                ),
                **run_options,
            )
            handled = dispatched.called
        return handled, mocks
