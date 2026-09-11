# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The owner reads a finished late run is guarded by, described once.

Shared by every module about what one guarded completion becomes: the guard
itself, the park an adjudicator's `single` earns, and the settlement a
decision to publish that candidate unsplit would license. They share the three
answers a fresh read can give -- the issue is open, a human closed it while the
agent ran, and GitHub could not be asked -- because each is a race rather than
a state a fixture can simply seed: the read happens INSIDE the call under test,
after the spawn it is guarding has already returned, so what changes the answer
has to change it from inside the run.

`settle_single` is the settlement's own entry point, for the cases about the
road rather than about the reply that reaches it. It stands beside the runs
because it needs the same worktree seams they do.

The three finished runs are module constants because `AgentResult` is frozen
and every one of these tests wants the same one: what differs between them is
what the world does while the run is in flight, not what the run said.

The plan-PR case sits here for the same reason it does in the hold's own
tests: an issue that reached its implementation through a design discussion is
the only one with a description to put back, and several of these modules ask
about it.
"""
from __future__ import annotations

import contextlib
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git.measurement.models import FingerprintFailure
from orchestrator.workflow.late_split import models as _late_models, state as _late_state
from orchestrator.workflow.stages.decomposition import (
    late_hold as _late_hold,
    late_owner as _late_owner,
    late_session as _late_session,
    late_settlement as _late_settlement,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateAdjudication,
    _LateAdjudicationRun,
    _LateContext,
    _LateDisposition,
)
from tests.support.fakes import FakeGitHubClient
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.stages.decomposition import late_test_support as _support
from tests.workflow.stages.decomposition.late_run_support import (
    LateCase,
    WorktreeSeed,
    agent_reply,
    late_run_context,
)

WORKFLOW_LOG = "orchestrator.workflow"

ERROR = "ERROR"

EVENT_LATE_CANCELLATION = "late_cancellation"
EVENT_LATE_SNAPSHOT = "late_snapshot"

PARK_OWNER_UNREADABLE = "late_owner_unreadable"
PARK_HOLD_FAILED = "late_plan_pr_hold_failed"
PARK_QUESTION = "late_question"
PARK_PR_UNRECONCILED = "late_pr_unreconciled"
PARK_SINGLE_DECISION = "late_single_decision"

# What a park's own sentence reaches the thread as: one comment, never
# two. Shared because every module about a park that stands asks it.
SAID_ONCE = 1

KEY_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

RECOVERY_FOLLOWUP_MARKER = "<!--orchestrator-late-owner-recovery-->"

RECOVERED_PREFIX = "Recovered automatically:"

NO_ACTION_LINE = "No action needed."

SPLIT_CHILDREN = 2

SINGLE_RUN = agent_reply(_support.SINGLE_REPLY)
SPLIT_RUN = agent_reply(_support.SPLIT_REPLY)
QUESTION_RUN = agent_reply(_support.QUESTION_REPLY)

# The runs that finish without deciding anything. Each parks the issue, and
# each is a completion the guard has to stand in front of all the same: the
# issue paid for the run, and a closure during one of them strands the same
# generation as a closure during a verdict would.
TIMEOUT_RUN = agent_reply("", timed_out=True)
UNPARSED_RUN = agent_reply(_support.NO_BLOCK_REPLY)
_TOO_LONG_TO_RECORD = "q" * _late_session.MAX_RECORDED_BODY
UNRECORDABLE_RUN = agent_reply(_support.late_block(
    '{"decision": "question", "category": "unsafe_split", '
    '"question": "' + _TOO_LONG_TO_RECORD + '"}'
))

# A worktree the read-only adjudicator moved. The run finished and its verdict
# is refused, which is one more completion that only parks.
MOVED_CANDIDATE = WorktreeSeed(head=_support.OTHER_SHA)

# A store that holds both commits and cannot hand back the content between
# them. The verdict settles exactly as it would have -- the exact commit is
# exempt -- and there is no identity of the accepted change to carry.
UNFINGERPRINTED = WorktreeSeed(
    fingerprint=FingerprintFailure.CONTENT_ABSENT,
)

PARK_TIMEOUT = "late_adjudicator_timeout"
PARK_UNPARSED = "late_manifest_invalid"
PARK_UNRECORDABLE = "late_result_unrecordable"
PARK_WORKTREE_MUTATED = "late_worktree_mutated"

# What one entry of the table below is read by.
NAME = "name"
RUN = "run"
TREE = "worktree"
REASON = "reason"

# Every non-verdict completion, with the reason it parks under and the
# worktree it needs. One table, because what the guard owes each of them is
# identical and a case added here is a case both races cover. Spelled as
# mappings rather than tuples so a test reads one case rather than unpacking
# four names it then has to keep straight.
PARKING_COMPLETIONS = (
    {NAME: "a timeout", RUN: TIMEOUT_RUN, TREE: None, REASON: PARK_TIMEOUT},
    {
        NAME: "an unusable reply",
        RUN: UNPARSED_RUN,
        TREE: None,
        REASON: PARK_UNPARSED,
    },
    {
        NAME: "an unrecordable outcome",
        RUN: UNRECORDABLE_RUN,
        TREE: None,
        REASON: PARK_UNRECORDABLE,
    },
    {
        NAME: "a moved candidate",
        RUN: SPLIT_RUN,
        TREE: MOVED_CANDIDATE,
        REASON: PARK_WORKTREE_MUTATED,
    },
)

# The mention id a park's own notice took, and therefore the watermark a
# recovery follow-up for that episode is looked for above.
PARK_NOTICE_ID = 100

# A split this issue already recorded against exactly this candidate: what a
# tick reuses instead of paying for a second adjudication.
RECORDED_SPLIT = MappingProxyType({
    _support.KEYS.verdict: "split",
    _support.KEYS.children: [
        {"title": "A", "body": "a", "depends_on": []},
        {"title": "B", "body": "b", "depends_on": [0]},
    ],
    _support.KEYS.run_cycle_id: _support.late_generation().cycle_id,
    _support.KEYS.run_generation: _support.late_generation().generation,
    _support.KEYS.source_sha: _support.CANDIDATE_SHA,
})

# What a human replacing a held pull request's description leaves behind: text
# the preserved copy is no longer a description of.
HUMAN_REWRITE = "I rewrote this while it was held."

# The two seams a killed tick can die at, named so a test says which.
OWNER_READ = "_owner_state"
OWNER_GUARD = "_guarded_owner"

# A shape GitHub could answer with that names no state at all. Reading it as
# open would publish on the strength of a read that established nothing.
STATELESS_OWNER = MagicMock(closed=False, state="")


class _ClosedDuringRun:
    """A human closing the issue while the agent is still running."""

    def __init__(self, issue, agent_result) -> None:
        self._issue = issue
        self._agent_result = agent_result

    def __call__(self, *_args, **_kwargs):
        self._issue.closed = True
        return self._agent_result


# What a human editing the notice rather than replacing it leaves behind: the
# hidden marker is still in the body, and so are words nothing here wrote.
HUMAN_ADDITION = "and a note of my own."


@contextlib.contextmanager
def unreadable_owner(github: FakeGitHubClient):
    """GitHub refusing the re-read the guard takes after the run."""
    with patch.object(github, "get_issue", side_effect=RuntimeError):
        yield


@contextlib.contextmanager
def killed_at(seam: str):
    """The process dying at one of the guard's seams, rather than failing.

    A `BaseException` the guard's own `except Exception` cannot catch, which
    is the whole point: a read that FAILS is handled, and a tick that does not
    live long enough to see it fail is what the obligation has to be written
    ahead of. Aimed at the guard rather than at the client, since the mid-run
    pause probe re-fetches the same issue and killing that one would be a
    different tick entirely.

    `OWNER_READ` is the kill inside the read, past the claim. `OWNER_GUARD` is
    one step earlier and nothing of the guard runs at all -- the boundary that
    decides whether the obligation is part of the write that recorded the
    result or something the step after it adds.
    """
    with patch.object(_late_owner, seam, side_effect=KeyboardInterrupt):
        yield


@contextlib.contextmanager
def stateless_owner(github: FakeGitHubClient):
    """A re-read that comes back naming no state this binary knows."""
    with patch.object(github, "get_issue", return_value=STATELESS_OWNER):
        yield


# The park a previous tick's failed read left standing. Seeded beside the
# generation's own marker because the two halves are what the reconciliation
# reads together: the marker says a read is owed, and the park says this mode
# told somebody so and therefore owes them a follow-up when it heals.
_OWED_READ_PARK = MappingProxyType({
    _support.KEYS.awaiting: True,
    _support.KEYS.park_reason: PARK_OWNER_UNREADABLE,
    KEY_LAST_ACTION_COMMENT_ID: PARK_NOTICE_ID,
})


# The branch a candidate publishes on, pinned so the exact-commit lookup is
# asked about a branch the fake's pull requests can actually be on.
CANDIDATE_BRANCH = "orchestrator/issue-41-candidate"

KEY_BRANCH = "branch"

KEY_PR_NUMBER = "pr_number"

# A pull request that is neither the plan nor this candidate's. What makes it
# worth its own fixture is that it is MERGED: carried into the implementing
# stage it ends the issue as done, on a change the accepted candidate is not
# in.
SETTLED_PR_NUMBER = 91

CARRYING_PR_NUMBER = 92


def settle_single(github, issue, **run_fields):
    """Run the settlement road a decided `single` licenses, at its own owner.

    Entered here rather than through the coordinator, because the coordinator's
    answer to an adjudicator's own `single` is the park beside this owner: what
    these cases are about is the settlement itself -- the two reconciliations,
    the exemption and the identity beside it, the push, and the handback -- so
    it is entered where a decision enters it, past the owner read and with the
    verdict already durable.

    The worktree seams are held the way a run holds them, since the identity
    reading, the push, and the checkout proof all reach the checkout the
    candidate was committed in.
    """
    state = github.read_pinned_state(issue)
    generation = _late_state.read_late_generation(state)
    context = _LateContext(
        gh=github,
        spec=_TEST_SPEC,
        issue=issue,
        state=state,
        generation=generation,
    )
    decided = _LateAdjudicationRun(
        disposition=_LateDisposition.DECIDED,
        generation=generation,
        run=_late_session._read_late_run(state),
        adjudication=_LateAdjudication(
            verdict=_late_models.LateVerdict.SINGLE,
        ),
    )
    with late_run_context(MagicMock(), **run_fields):
        return _late_settlement._reconcile_single(context, decided)


class GuardedLateCase(LateCase):
    """One late issue, adjudicated once, reported by what it decided."""

    def _decide(self, agent_result=SPLIT_RUN, **run_fields):
        """Adjudicate once and report only the outcome."""
        outcome, _spawn = self._adjudicate(agent_result, **run_fields)
        return outcome

    def _settle(self, **run_fields):
        """Take the settlement road this issue's candidate publishes on."""
        return settle_single(self.github, self.issue, **run_fields)

    def _decide_unread(self, agent_result=SPLIT_RUN):
        """Adjudicate once with the owner unreadable, log line included."""
        with unreadable_owner(self.github), self.assertLogs(WORKFLOW_LOG, level=ERROR):
            return self._decide(agent_result)

    def _seed_owing(self, recorded=None, **generation_fields) -> None:
        """Re-seed this issue as one owing an owner read from a prior tick.

        `recorded` is the run record a tick that got as far as an answer left
        beside it, for the tests about what happens once the read heals.
        """
        self.github.seed_state(
            self.issue.number,
            **_support.generation_state(
                _support.late_generation(
                    owner_check_pending=True, **generation_fields,
                ),
            ),
            **_OWED_READ_PARK,
            **(recorded or {}),
        )


class HeldPlanPrCase(GuardedLateCase):
    """A late issue whose plan PR already wears this generation's hold.

    Seeded held rather than held by a first tick, because what these tests
    are about is the RELEASE: an adjudication that has to take the hold first
    would have to record a verdict to get there, and a recorded verdict is
    exactly what stops the next tick spawning the run whose verdict is under
    test.
    """

    def setUp(self) -> None:
        super().setUp()
        self.github = FakeGitHubClient()
        self.generation = _support.late_generation(
            plan_pr_number=_support.PLAN_PR_NUMBER, plan_pr_body=_support.PLAN_PR_BODY,
        )
        self.issue = _support.seed_late_issue(
            self.github,
            self.generation,
            pr_number=_support.PLAN_PR_NUMBER,
            **{_support.KEY_PLAN_PATH: _support.PLAN_PATH},
        )
        self.plan_pr = _support.seed_plan_pr(
            self.github, body=_late_hold._hold_body(self.generation),
        )
