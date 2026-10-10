# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite whose tick died around its verification, and the next tick's base refresh recovering it.

The real-git finish case (`rewrite_finish_git_support`): issue #7 in review,
its anchor's evidence settled, the base moved, the branch rebased and pushed
over the anchor, and the rebased head's report settled and handed a reviewer,
so the evidence policy runs the configured command on that head. The
publication's finish is handed the landing, and the process dies at a step
(`ProcessDied`, which nothing on the finish's road catches): in the verify
runner before any command ran, behind a run that completed, or at the relabel
behind the evidence write that captured the run -- or a recovery dies at its
own relabel, behind the write that abandoned that run.

What it left is recovered by the whole per-tick base refresh (`recovers`): the
anchor read, the branch fetched, the push observed where the remote stands,
and the one finish every landing gets. The push transport and the agent runner
are recorded around it, so a case reads back that nothing was pushed a second
time and no developer was launched.
"""
from __future__ import annotations

import contextlib
from functools import partial
from typing import NoReturn
from unittest.mock import Mock, patch

from orchestrator.agents import runner as _agent_runner
from orchestrator.git import branch_transport
from orchestrator.git.verification import runner as _verify_runner
from tests.git.base_sync.real_git_test_support import _LocalBranchPusher
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
)
from tests.workflow.git_owners import seam_patch

_BASE_REBASED = "base_rebased"

_MAIN = "main"


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

    def dies_routing(self, finishing) -> None:
        """Run `finishing` -- a finish, or a whole recovery -- dying at its relabel, behind every write before it.

        A death inside the base refresh is one more failed issue sync to it,
        logged and gone past, exactly as nothing behind it runs.
        """
        relabel = self.gh.set_workflow_label
        self.gh.set_workflow_label = dies
        with contextlib.suppress(ProcessDied):
            finishing()
        self.gh.set_workflow_label = relabel
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


def announced(case: VerificationRecoveryCase) -> list[str]:
    """The head every `base_rebased` event filed for `case`'s issue names, oldest first."""
    return [
        event.get("sha") for event in case.gh.recorded_events
        if event.get("event") == _BASE_REBASED and event.get("issue") == git_support.ISSUE
    ]


def decided_moved(head: str) -> str:
    """What the evidence policy logs of a run something moved under while it verified `head`."""
    short_head = head[:8]
    return f"decided moved evidence for the base rewrite's head {short_head}"


def advances_the_base_again(case: VerificationRecoveryCase) -> None:
    """Move `case`'s base once more, by a file of its own, past whatever the branch was rebased onto."""
    work = case._work
    case._git("checkout", "--quiet", _MAIN, cwd=work)
    (work / "later.txt").write_text("later base\n")
    case._git("add", "later.txt", cwd=work)
    case._git("commit", "--quiet", "-m", "later base advance", cwd=work, env_extra=case._author_env)
    case._git("push", "--quiet", "origin", _MAIN, cwd=work)
