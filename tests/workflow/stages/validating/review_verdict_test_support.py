# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One validating issue whose reviewer returned, and the preparation its verdict is handed to.

The world is the one a reviewer round normally meets, shared with the stages
past this one (`tests/workflow/review_world.py`): an open pull request on the
default head, the report its delivery published settled on the pinned comment,
a checkout this host holds, and a fake repository reading every commit as one
tree, under a configuration that requires the suite. In it the proof that
settles a reviewer's declared commands passes, so a case that refuses one is
visibly about the one thing it moved.

A case hands the preparation a returned run directly, built the way the live
round (`reviewer`) hands its own over, so one request of the preparation can be
raced or refused without a whole tick around it: the subject resolved and
recorded as the launch and the return record it, the launch charged, the
reviewer's usage folded once by the service itself, and the parsed verdict
handed to `review_disposition.prepares_the_verdict`, whose answer the case
keeps (`prepared`). Whole ticks through the stage handler, the reviewer round
included, are `evidence_round_test_support`'s. A later tick here is the dispatcher's evidence reconciliation
and then `review_disposition.waiting_verdict_ready` over the pinned comment
alone -- the returned run is forgotten first, as a later process never had it
-- whose answer the case keeps too (`ready`). Both are read back through
`review_verdict_readings`. A case that has the verdict disposed of, and a
later tick finish it, is `disposed_verdict_test_support`'s, and one whose
later tick is a stage handler's own, finishing the verdict through its
recovery (`review_resume`), is `resumed_verdict_test_support`'s.

What another road does between two of a tick's requests is spelled here too
(`AnotherRoadBehind`): a push, or a thread that stops answering, behind the
one request a case is about.
"""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

from orchestrator.observability.usage.metrics import UsageMetrics
from orchestrator.workflow.engine import (
    completion_verdicts as _completion_verdicts,
    prompt_context as _prompt_context,
    review_findings as _findings,
    verification_transaction as _transaction,
)
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_disposition as _disposition,
    review_evidence as _review_evidence,
    review_records as _review_records,
    review_report as _review_report,
    review_verdicts as _verdicts,
)
from tests.workflow import review_world as _review_world
from tests.workflow.fixtures import _agent
from tests.workflow.git_owners import GIT_SEAM_OWNERS
from tests.workflow.repo_values import _FAKE_WT, _TEST_SPEC

# The issue, its pull request and head, and the sessions and run seam of the
# review world this one builds on (`review_world`).
ISSUE = _review_world.ISSUE

PR = _review_world.PR

HEAD = _review_world.HEAD

OTHER_HEAD = _review_world.OTHER_HEAD

DEV_SESSION = _review_world.DEV_SESSION

REVIEWER_SESSION = _review_world.REVIEWER_SESSION

RUN_AGENT = _review_world.RUN_AGENT

# The pinned records a case reads back, spelled as the comment spells them.
RETURNED_VERDICT = "review_returned_verdict"

PENDING_EVIDENCE = "verification_evidence_pending"

AGENT_RUNS_USED = "agent_runs_used"

# The reviewer's folded tokens, the suite the configuration requires, what the
# reviewer's run printed, and the change it requests.
REVIEWER_TOKENS = _review_world.REVIEWER_TOKENS

SUITE = _review_world.SUITE

SUITE_OUTPUT = _review_world.SUITE_OUTPUT

REQUESTED = _review_world.REQUESTED

# What a failing run of the suite printed, and the findings a human is shown of
# a change request declaring it: the reviewer's words, then that check as the
# diagnostic a developer acts on -- led by the test that failed, named by its
# exact ID, and its error, then the command and how it ended, over its output
# quoted whole.
FAILED_TEST = "tests/test_config.py::test_empty"

FAILURE_ERROR = "KeyError: 'VERIFY_COMMANDS'"

FAILURE_OUTPUT = f"FAILED {FAILED_TEST} - {FAILURE_ERROR}\n1 failed, 11 passed"

CONCISE_FAILURE = (
    f"{REQUESTED}\n\nFailure: `{FAILED_TEST}`\nError: `{FAILURE_ERROR}`\n"
    f"`{SUITE}` exited with status 1:\n\n```\n{FAILURE_OUTPUT}\n```"
)

# The findings a tick before each failing check was led by what failed showed
# of that change request -- the check's sentence over its output alone --
# spelled out as such a tick posted them, so a post it made stays found
# whatever the formatting shows now.
PREVIOUS_CONCISE_FAILURE = f"{REQUESTED}\n\n`{SUITE}` exited with status 1:\n\n```\n{FAILURE_OUTPUT}\n```"

# A stdin command a reviewer ran two probes of its own through, each probe's
# scenario name and the error its run printed, and the change request entering
# each failure in the findings by that name, error, and snippet above the
# declaration of both runs -- declared in the other order than the entries
# stand in. The findings a human is shown of it are those entries as written,
# then each run led by the scenario whose error it printed, never the two
# merged for the command they share.
PROBE = ".venv/bin/python -"

PROBES = (
    ("A lost announcement revives settled evidence", "AssertionError: a lost announcement revived settled evidence"),
    ("A failed relabel revives settled evidence", "AssertionError: a failed relabel revived settled evidence"),
)

PROBE_RUNS = tuple(reversed(PROBES))

PROBE_ENTRIES = "\n\n".join(
    f"Failure: {scenario}\nError: {error}\nReproduce: `{PROBE}` reading:\n\n"
    f"```python\nfrom tests.workflow import probes\nprobes.check({scenario!r})\n```"
    for scenario, error in PROBES
)

PROBED_REQUEST = (
    f"{REQUESTED}\n\n{PROBE_ENTRIES}\n\nVERIFICATION: RUN {HEAD}\n"
    + "".join(f"COMMAND: {PROBE}\nEXIT: 1\n{error}\n" for _scenario, error in PROBE_RUNS)
    + "VERIFICATION: END\n\nVERDICT: CHANGES_REQUESTED"
)

CONCISE_PROBES = "\n\n".join((
    REQUESTED,
    PROBE_ENTRIES,
    *(f"Failure: {scenario}\n`{PROBE}` exited with status 1:\n\n```\n{error}\n```" for scenario, error in PROBE_RUNS),
))

# The same probes printing their errors in the shape pytest refuses a run in,
# `ERROR:` and a message, as their entries give them: each run is still led by
# its own scenario, never as a run pytest refused -- and so is each where a
# tick before leads showed the request, each run's sentence over its output.
REFUSAL_RUNS = tuple(
    (scenario, error.replace("AssertionError:", "ERROR:")) for scenario, error in PROBE_RUNS
)

REFUSAL_PROBED_REQUEST, CONCISE_REFUSAL_PROBES = (
    shown.replace("AssertionError: a ", "ERROR: a ") for shown in (PROBED_REQUEST, CONCISE_PROBES)
)

PREVIOUS_REFUSAL_PROBES = "\n\n".join((
    REQUESTED,
    PROBE_ENTRIES.replace("AssertionError: a ", "ERROR: a "),
    *(f"`{PROBE}` exited with status 1:\n\n```\n{error}\n```" for _scenario, error in REFUSAL_RUNS),
))

# What findings that are a declaration and nothing else read as.
NO_FINDINGS = _findings._NO_FINDINGS

# The full tree every commit in the fake checkout reads as.
TREE = _review_world.TREE

# A reviewer's final message declaring one run of a command on the head.
declared_run = _review_world.declared_run


# A change request whose run of the suite failed, printing `FAILURE_OUTPUT`.
FAILED_REQUEST = declared_run(exit_status=1, verdict="CHANGES_REQUESTED", output=FAILURE_OUTPUT)

# A change request beside a passing run of the suite, whose findings are the
# reviewer's words alone once the declaration is set aside.
PASSED_REQUEST = declared_run(verdict="CHANGES_REQUESTED")

# A change request declaring a passing run of the suite and saying nothing else.
DECLARED_ALONE = PASSED_REQUEST.removeprefix(f"{REQUESTED}\n\n")

# A change request reusing the evidence revision `digest` names.
REQUEST_REUSING = f"{REQUESTED}\n\nVERIFICATION: REUSED sha256:{{digest}}\n\nVERDICT: CHANGES_REQUESTED"


# Another road's push past the reviewed head, and the pull request's thread
# going unanswered.
pushes = _review_world.pushes

stops_answering = _review_world.stops_answering


def returned_run(case, state, message: str) -> _models._ReviewerRun:
    """The run of a reviewer handed the subject standing now that returned `message`, launched on `state`."""
    delivered = _prompt_context._delivered_thread(case.github, case.issue, state)
    handover = case.handed(state, delivered)
    return _models._ReviewerRun(
        wt=_FAKE_WT,
        round_n=state.get("review_round"),
        pr_number=PR,
        agent_result=replace(
            _agent(session_id=REVIEWER_SESSION, last_message=message),
            usage=UsageMetrics(backend="codex", input_tokens=REVIEWER_TOKENS),
        ),
        delivery=delivered,
        subject=handover.subject,
        resolved_over=handover.resolved_over,
        evidence=_review_evidence.handed_evidence(case.github, _TEST_SPEC, case.issue, state, handover.subject),
    )


def reconciles(case) -> bool:
    """The dispatcher's evidence reconciliation on `case`'s issue; whether it held the tick."""
    return _transaction._reconciles_pending_evidence(
        case.github, _TEST_SPEC, case.issue,
        case.github.workflow_label(case.issue), case.github.read_pinned_state(case.issue),
    )


class AnotherRoadBehind:
    """A request behind which, the `times`-th time `when` says, `road` does another road's work.

    The request is the client's where the client carries one of that name, and
    otherwise the git seam of that name on the owner defining it -- the tree
    read evidence is minted over, say. `when` is asked about the request's last
    positional argument: the state a write carries, the body a post carries,
    the location a reread asks about, the commit a tree read names.
    """

    def __init__(self, case, request: str, when, road, times: int = 1) -> None:
        self._case = case
        self._name = request
        self._owner = case.github if hasattr(case.github, request) else GIT_SEAM_OWNERS[request]
        self._request = getattr(self._owner, request)
        self._when = when
        self._road = road
        self._left = times

    def __call__(self, *asked, **named):
        answered = self._request(*asked, **named)
        if self._left and self._when(asked[-1]):
            self._left -= 1
            if not self._left:
                self._road(self._case)
        return answered

    def returning(self, message: str, **run_options) -> dict:
        """The tick in which a reviewer returned `message`, over a client carrying this request."""
        with self.patched():
            return self._case.returns(message, **run_options)

    def patched(self):
        """A patch of the request, with this road behind it."""
        return patch.object(self._owner, self._name, self)


class ReviewVerdictWorld(_review_world.ReviewWorld):
    """An issue on `workflow:validating` whose reviewer is about to return."""

    def setUp(self) -> None:
        super().setUp()
        # The decision the last returned run was handed over as, what its
        # preparation answered, and what the last later tick answered of the
        # verdict it found waiting -- None where none waited.
        self.decision: _models._ReviewerDecision | None = None
        self.prepared: _disposition.Prepared | None = None
        self.ready: _verdicts.ReturnedVerdict | None = None

    def returns(self, message: str, **run_options) -> dict:
        """One tick in which a reviewer returned `message` and its verdict was handed over (`_prepares`).

        The tree read is the one `setUp` stood in, which a case may wrap.
        """
        run_options.setdefault(RUN_AGENT, [])
        run_options.setdefault("checkout_tree", None)
        return self._run(lambda: self._prepares(message), **run_options)

    def finishes(self, *, meanwhile=None) -> dict:
        """One later tick: the evidence reconciliation, then the waiting verdict asked whether it is ready.

        `meanwhile` is another road's work once the tick has read the comment
        it asks over.
        """
        # A later tick holds nothing the returned run left in memory.
        self.decision = None
        self.ready = None
        return self._run(lambda: self._finishes(meanwhile), run_agent=[])

    def handed(self, state, delivered=None):
        """The subject a reviewer round is handed now, recorded on `state` as its launch records it."""
        if delivered is None:
            delivered = _prompt_context._delivered_thread(self.github, self.issue, state)
        handover = _review_report._resolves_the_subject(self.github, self.issue, state, PR, delivered)
        _review_records._records_the_launch(state, handover.subject)
        return handover

    def _prepares(self, message: str) -> None:
        """The returned round, as the live one records it, handed to the preparation."""
        state = self.github.read_pinned_state(self.issue)
        run = returned_run(self, state, message)
        # The launch's lifetime charge, which the live round's run circuit takes.
        state.set(AGENT_RUNS_USED, (state.get(AGENT_RUNS_USED) or 0) + 1)
        verdict, body = _completion_verdicts._parse_review_verdict(message)
        self.decision = _models._ReviewerDecision(run, verdict, body)
        self.prepared = _disposition.prepares_the_verdict(self.github, _TEST_SPEC, self.issue, state, self.decision)

    def _finishes(self, meanwhile) -> None:
        """The verdict the comment carries, asked over the comment alone once the reconciliation lets the tick on."""
        if reconciles(self):
            return
        state = self.github.read_pinned_state(self.issue)
        if meanwhile is not None:
            meanwhile(self)
        self.ready = _disposition.waiting_verdict_ready(self.github, self.issue, state)
