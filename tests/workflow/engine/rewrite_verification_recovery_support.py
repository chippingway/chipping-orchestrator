# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite whose tick died around its verification, and the next tick's base refresh recovering it.

The real-git finish case (`rewrite_finish_git_support`): issue #7 in review,
its anchor's evidence settled, the base moved, the branch rebased and pushed
over the anchor, and the rebased head's report settled and handed a reviewer,
so the evidence policy runs the configured command on that head. The
publication's finish is handed the landing, and the process dies at a step
(`ProcessDied`, which nothing on the finish's road catches): in the verify
runner before any command ran, behind a run that completed, or at the post of
the artifact behind the evidence write that captured the run -- or a recovery
dies at its own relabel, behind the write that abandoned that run.

What it left is recovered by the whole per-tick base refresh (`recovers`): the
anchor read, the branch fetched, the push observed where the remote stands,
and the one finish every landing gets. The push transport and the agent runner
are recorded around it, so a case reads back that nothing was pushed a second
time and no developer was launched. A case about the run the evidence write
captured (`CapturedRunCase`) lands it first (`captures`), answers a park with
the issue author's continue (`continues`), and reads the run back abandoned
(`assert_abandoned`), settled under the anchor (`assert_settled`), or offered
to the dispatcher's reconciliation (`reconciles`).
"""
from __future__ import annotations

import contextlib
from functools import partial
from typing import NoReturn
from unittest.mock import Mock, patch

from orchestrator.agents import runner as _agent_runner
from orchestrator.git import branch_transport
from orchestrator.git.verification import runner as _verify_runner
from orchestrator.workflow.engine import verification_settlement_state, verification_transaction
from tests.git.base_sync.real_git_test_support import _LocalBranchPusher
from tests.workflow.engine import (
    rewrite_finish_evidence_test_support as _finish_support,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    verification_evidence_test_support as _evidence_support,
)
from tests.workflow.git_owners import seam_patch

_BASE_REBASED = "base_rebased"

_MAIN = "main"

_QUIET = "--quiet"

# A commit another hand makes in the checkout, past whatever head it stands on.
STRAY_COMMIT = (
    "-c", "user.name=stray", "-c", "user.email=stray@example.invalid",
    "commit", _QUIET, "--allow-empty", "-m", "stray",
)

# The client's steps a finish or a recovery dies at: the relabel, and the post
# of the evidence artifact.
RELABEL = "set_workflow_label"

POST = "publish_verification_artifact"

# The command every case configures, put back once a case has moved it.
CONFIGURED = f"test -f feature.py && echo '{git_support.CHECKED}'"


class ProcessDied(Exception):
    """The orchestrator process dying at a step: nothing on the finish's road catches it, and nothing behind it runs."""


def dies(*_args, **_kwargs) -> NoReturn:
    """Die where this stands in for a step."""
    raise ProcessDied


# The real verify runner, read before any case patches its seam.
_VERIFY = _verify_runner._run_verify_commands


def runs_then(after, *args):
    """Run the configured commands through the real verify runner, then `after` -- a death or another road's move."""
    ran = _VERIFY(*args)
    after()
    return ran


class VerificationRecoveryCase(git_support.RealGitFinishCase):
    """Issue #7's rebased head handed a reviewer, a finish of it that dies, and the refresh that recovers it."""

    def setUp(self) -> None:
        git_support.RealGitFinishCase.setUp(self)
        self.pushes = Mock(side_effect=_LocalBranchPusher())
        self.developer = Mock()

    def lands_a_reviewed_rebase(self) -> str:
        """Move the base, rebase and push the branch over the anchor, and hand a reviewer the head; that head."""
        git_support.advances_the_base(self)
        head = self.rebases_by_hand()
        self.reviews(head)
        return head

    def dies_verifying(self, head: str, *, completed: bool) -> None:
        """Publish `head`'s finish and die in its verification: before any command ran, or behind a completed run."""
        died = partial(runs_then, dies) if completed else dies
        with seam_patch("_run_verify_commands", died), self.assertRaises(ProcessDied):
            self.finishes(head)

    def dies_at(self, step: str, finishing) -> None:
        """Run `finishing` -- a finish, or a whole recovery -- dying at the client's `step`, behind every earlier write.

        The step is put back behind the death, and nothing was relabelled. A
        death inside the base refresh is one more failed issue sync to it,
        logged and gone past, exactly as nothing behind it runs.
        """
        live = getattr(self.gh, step)
        setattr(self.gh, step, dies)
        with contextlib.suppress(ProcessDied):
            finishing()
        setattr(self.gh, step, live)
        self.assertEqual(readings.relabels(self), ())

    def recovers(self, during=None) -> None:
        """One whole per-tick base refresh, `during` done to this case behind any run of the commands it makes."""
        verify = _VERIFY if during is None else partial(runs_then, partial(during, self))
        with (
            patch.object(branch_transport, "_push_branch", self.pushes),
            patch.object(_agent_runner, "run_agent", self.developer),
            seam_patch("_run_verify_commands", verify),
        ):
            self._refresh()

    def assert_held(self, pending) -> None:
        """Nothing routed and the attempt still pinned on its anchor, `pending` the transaction the comment carries."""
        held = readings.pinned(self)
        standing = (readings.records(held)[0], held[readings.KEY_PENDING_PUSH])
        self.assertEqual(
            (*standing, readings.relabels(self)),
            (pending, self.anchor, ()),
        )

    def assert_recovered(self, head: str) -> None:
        """`head` routed once with its attempt retired and announced once, nothing pushed and no developer launched."""
        self.assertEqual(
            (readings.relabels(self), readings.attempt(readings.pinned(self))),
            (readings.ROUTED, readings.RETIRED),
        )
        said = (announced(self), len(readings.notices(self)))
        self.assertEqual(
            (*said, self.pushes.call_count, self.developer.call_count),
            ([head], 1, 0, 0),
        )


class CapturedRunCase(VerificationRecoveryCase):
    """Issue #7's rebased head handed a reviewer, its run captured by a finish that dies posting its artifact."""

    def captures(self) -> tuple:
        """Land a reviewed rebase whose finish records its run and dies posting its artifact; the head, and that run.

        The run's receipt went on the attempt in the write that recorded it.
        """
        head = self.lands_a_reviewed_rebase()
        self.dies_at(POST, partial(self.finishes, head))
        self.assertEqual(self.runs(), 1)
        captured = readings.pinned_records(self)[0]
        self.assertEqual(readings.pinned(self)[readings.KEY_EVIDENCE_RECEIPT], captured.receipt)
        return head, captured

    def continues(self) -> None:
        """Have the issue's author reply `/orchestrator continue` to the park a recovery left."""
        self.gh.comment(self.issue, "/orchestrator continue").user.login = self.issue.user.login

    def reconciles(self) -> None:
        """Run the dispatcher's reconciliation of the recorded evidence, over the comment as it stands."""
        verification_transaction._reconciles_pending_evidence(
            self.gh, self._spec, self.issue, git_support.REVIEWING, self.gh.read_pinned_state(self.issue),
        )

    def assert_settled(self, captured) -> None:
        """`captured` current exactly as recorded and its artifact posted once, beside the evidence it invalidated.

        Nothing pending, nothing retired but the evidence the rewrite moved
        past, and the command run once: the run the finish captured.
        """
        pending, current, retired = readings.pinned_records(self)
        settled = (current.receipt, current.revision, current.binding)
        self.assertEqual(
            (pending, settled, retired, self.runs()),
            (None, (captured.receipt, captured.revision, captured.binding), git_support.invalidated(self), 1),
        )
        self.assertEqual(self.posted(captured), [captured.commands])

    def posted(self, captured) -> list:
        """The transcript of every artifact the pull request carries under `captured`'s receipt, oldest first."""
        published = _evidence_support.posted_artifacts(self)
        return [artifact.commands for artifact in published if artifact.receipt == captured.receipt]

    def assert_abandoned(self, captured) -> None:
        """Nothing pending or current, the settled evidence invalidated and `captured` abandoned whole, run once.

        The abandoned entry keeps the revision and the whole binding the run
        was captured with: its tested commit and tree, configuration, source,
        and the review it answered for.
        """
        retired = (*git_support.invalidated(self), (captured.receipt, readings.ABANDONED))
        self.assertEqual(
            (readings.pinned_records(self), self.runs()),
            ((None, None, retired), 1),
        )
        abandoned = verification_settlement_state.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((abandoned.revision, abandoned.binding), (captured.revision, captured.binding))

    def assert_unannounced(self) -> None:
        """Nothing announced -- no notice, no `base_rebased` event -- relabelled, or reset: the round as spent."""
        unsaid = (announced(self), readings.notices(self), readings.relabels(self))
        self.assertEqual(
            (*unsaid, readings.pinned(self)[readings.KEY_REVIEW_ROUND]),
            ([], [], (), _finish_support.SPENT_ROUND),
        )


def announced(case: VerificationRecoveryCase) -> list[str]:
    """The head every `base_rebased` event filed for `case`'s issue names, oldest first."""
    return [
        event.get("sha") for event in case.gh.recorded_events
        if event.get("event") == _BASE_REBASED and event.get("issue") == git_support.ISSUE
    ]


def advances_the_base_again(case: VerificationRecoveryCase) -> None:
    """Move `case`'s base once more, by a file of its own, past whatever the branch was rebased onto."""
    work = case._work
    case._git("checkout", _QUIET, _MAIN, cwd=work)
    (work / "later.txt").write_text("later base\n")
    case._git("add", "later.txt", cwd=work)
    case._git("commit", _QUIET, "-m", "later base advance", cwd=work, env_extra=case._author_env)
    case._git("push", _QUIET, "origin", _MAIN, cwd=work)
