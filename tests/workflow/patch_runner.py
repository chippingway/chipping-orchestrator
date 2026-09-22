# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Stage-family adapters around the shared workflow patch context.

The fixing adapter seeds its own push double rather than the shared boolean,
because that stage BINDS a report to the commit it published and holds the
binding to the head the pull request is standing on: a static double leaves a
pull request frozen where the fixture seeded it, so a push that landed would
read back as a head somebody else moved. What lands moves the pull request
here, exactly as it does on the remote.
"""
from __future__ import annotations

from functools import partial

from orchestrator.workflow.stages.conflicts import handler as _conflicts
from orchestrator.workflow.stages.fixing import handler as _fixing
from orchestrator.workflow.stages.implementing import handler as _implementing
from orchestrator.workflow.stages.in_review import handler as _in_review
from orchestrator.workflow.stages.validating import handler as _validating
from tests.support.publication import LandingPush
from tests.workflow.patch_context import _patch_and_run
from tests.workflow.patch_models import _WorkflowRunContext
from tests.workflow.repo_values import _TEST_SPEC


class _ImplementationWorkflowMixin:
    def _run_implementing(
        self,
        github,
        issue,
        *,
        run_agent,
        **run_options,
    ):
        return self._run(
            partial(
                _implementing._handle_implementing,
                github,
                _TEST_SPEC,
                issue,
            ),
            run_agent=run_agent,
            **run_options,
        )

    def _run_fixing(
        self,
        github,
        issue,
        *,
        run_agent,
        **run_options,
    ):
        run_options["push_branch"] = _lands_on_the_pull_request(
            github, issue, run_options.get("push_branch", True),
        )
        return self._run(
            partial(
                _fixing._handle_fixing,
                github,
                _TEST_SPEC,
                issue,
            ),
            run_agent=run_agent,
            **run_options,
        )


def _lands_on_the_pull_request(github, issue, seed):
    """The push seam a fixing tick publishes through, moving what it lands on.

    A boolean seed says only whether the push succeeds, and every fixing road
    that publishes a report then asks where the pull request is STANDING --
    so a double that lands without moving it answers as a remote somebody
    force-pushed past this tick would. A seed that is already a double is its
    caller's own and is left alone, as is an issue with no pull request
    recorded for the push to move.
    """
    if not isinstance(seed, bool):
        return seed
    pr_number = github.pinned_data(issue.number).get("pr_number")
    if pr_number is None:
        return seed
    return LandingPush(github, int(pr_number), lands=seed)


class _ReviewWorkflowMixin:
    def _run_validating(
        self,
        github,
        issue,
        *,
        run_agent,
        **run_options,
    ):
        return self._run(
            partial(
                _validating._handle_validating,
                github,
                _TEST_SPEC,
                issue,
            ),
            run_agent=run_agent,
            **run_options,
        )

    def _run_in_review(
        self,
        github,
        issue,
        *,
        run_agent,
        **run_options,
    ):
        return self._run(
            partial(
                _in_review._handle_in_review,
                github,
                _TEST_SPEC,
                issue,
            ),
            run_agent=run_agent,
            **run_options,
        )


class _ConflictWorkflowMixin:
    def _run_resolving_conflict(
        self,
        github,
        issue,
        *,
        run_agent,
        **run_options,
    ):
        return self._run(
            partial(
                _conflicts._handle_resolving_conflict,
                github,
                _TEST_SPEC,
                issue,
            ),
            run_agent=run_agent,
            **run_options,
        )


class _StageWorkflowMixin(
    _ImplementationWorkflowMixin,
    _ReviewWorkflowMixin,
    _ConflictWorkflowMixin,
):
    """Combine stage-family entry points."""


class _PatchedWorkflowMixin(_StageWorkflowMixin):
    """Run a workflow handler inside the standard hermetic patch set."""

    def _run(self, callable_, *, run_agent, **run_options):
        context = _WorkflowRunContext(
            run_agent=run_agent,
            **run_options,
        )
        return _patch_and_run(callable_, context)
