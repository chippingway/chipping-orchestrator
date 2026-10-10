# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pull request a body edit resumes the developer over mid-rebase, and the ticks behind it.

The requirements-drift world (`tests/workflow/drift_reports.py`) on
`workflow:resolving_conflict`, in the shape #2077 reached it: the pull request
carries the report an approval covered, the final docs pass ran on the head it
stands on -- which is what makes that head one this orchestrator produced --
and a human then changes the requirements while the branch is being rebased.

A tick past the resume reaches the rest of the stage -- the recovered push, the
settled round, the rebase -- and each of those asks git directly how far the
checkout is behind its base and runs the rebase itself. Those seams answer here
the way a branch already standing on its base answers them, so a recovery tick
reads the world a crash left rather than a git nobody seeded. Every tick runs
under the fix loop's author policy, since a human's reply is only a reply to an
author the deployment trusts.

The checkout a later tick finds comes in two shapes: one commit ahead of the
pull request, and rebased past it -- ahead of it and behind it at once, which
is what a rebase the developer ran leaves. A world with no final-docs pass
behind it is the one where nothing but the resume's own record can say whose
commits a force-push over the second shape would drop.
"""
from __future__ import annotations

import contextlib
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git.measurement.models import FrozenCommit, MeasurementFailure
from orchestrator.observability.usage.agy_events import ToolLifecycle
from orchestrator.workflow.engine import (
    base_refresh as _base_refresh,
    base_rewrite as _base_rewrite,
    report_binding as _report_binding,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import (
    drift_reports as _drift_world,
    fix_reports as _fix_world,
    published_reports as _published_reports,
)
from tests.workflow.fixtures import _TEST_SPEC, LABEL_RESOLVING_CONFLICT, _agent
from tests.workflow.git_owners import seam_patch

ISSUE = 2_077

PR = 20_870

# The requirements the human rewrites the issue to while the rebase is out.
CHANGED_REQUIREMENTS = "The acceptance criteria changed while the branch was being rebased."

# A checkout whose resume rebased the branch: standing on the commit it left,
# two ahead of the pull request's head and one behind it, which is still where
# the remote branch stands.
REBASED_PAST = MappingProxyType({
    _drift_world.HEAD_SHAS: (_drift_world.FIXED_HEAD,),
    _drift_world.AHEAD_BEHIND: (2, 1),
    _drift_world.FETCHED_TIP: _drift_world.PUBLISHED_HEAD,
})

# Both shapes a commit nothing has published yet can leave the checkout in.
UNPUBLISHED = (
    ("one commit ahead", _drift_world.STRANDED),
    ("rebased past the head", REBASED_PAST),
)

# A commit the checkout gains once a resume's push of its own landed: the head
# it then stands on, one ahead of a remote standing on the pushed commit.
GAINED_HEAD = "b0b0b0b0" * 5

PAST_THE_PUSH = MappingProxyType({
    _drift_world.HEAD_SHAS: (GAINED_HEAD,),
    _drift_world.AHEAD_BEHIND: (1, 0),
    _drift_world.FETCHED_TIP: _drift_world.FIXED_HEAD,
    "candidate_commit": FrozenCommit(sha=GAINED_HEAD),
})

# A tick whose checkout's head nothing could prove.
UNPROVED_HEAD = MappingProxyType({
    "candidate_commit": FrozenCommit(failure=MeasurementFailure.CANDIDATE_UNREADABLE),
})

# A run whose checkout nobody could read once it was back: the head it began
# on, and every reading behind it empty.
UNREAD_HEAD = MappingProxyType({
    _drift_world.HEAD_SHAS: (_drift_world.PUBLISHED_HEAD, "", ""),
})

# What `git rev-list --count HEAD..<remote>/<base>` answers for a checkout
# already standing on its base, and for one the base has moved one commit past.
_ON_BASE = MagicMock(returncode=0, stdout="0\n", stderr="")

_BEHIND_BASE = MagicMock(returncode=0, stdout="1\n", stderr="")

# What a rebase onto a base that moved answers: replayed cleanly, or stopped on
# a file both sides changed.
REBASED_CLEANLY = (True, [])

REBASED_INTO_CONFLICT = (False, ["a.py"])

# A resume the agent timeout killed.
TIMED_OUT = _agent(session_id=_drift_world.DEV_SESSION, timed_out=True)

# A resume that wrote a report with a command it started still running: a run
# that never finished, whatever its last message says.
UNFINISHED_REPORT = _agent(
    session_id=_drift_world.DEV_SESSION,
    last_message=_drift_world.reported(),
    unfinished_steps=(ToolLifecycle(step_index=1, tool_name="run_command", state="ACTIVE"),),
)


@contextlib.contextmanager
def on_its_base():
    """Answer the stage's own git as a branch standing on its base does.

    Nothing behind the base, and a rebase onto it that replays nothing.
    """
    with _answered(_ON_BASE, REBASED_CLEANLY):
        yield


@contextlib.contextmanager
def behind_its_base(rebase: MagicMock):
    """Answer the stage's own git as a branch the base has moved past does, the rebase itself answered by `rebase`."""
    with _answered(_BEHIND_BASE, rebase):
        yield


@contextlib.contextmanager
def _answered(counted, rebase):
    """The stage's git seams: `counted` for the behind-base count, `rebase` (a result or the seam) for the rebase."""
    if not isinstance(rebase, MagicMock):
        rebase = MagicMock(return_value=rebase)
    with (
        seam_patch("_git", MagicMock(return_value=counted)),
        seam_patch("_git_hardened", MagicMock(return_value=counted)),
        seam_patch("_rebase_base_into_worktree", rebase),
    ):
        yield


class PushedAfterTheRecord:
    """A push that lands, remembering the report the pinned comment held as it went out."""

    def __init__(self, case) -> None:
        self._case = case
        self._lands = _drift_world._LandingPush(case.pull_request)
        self.delivered = None

    def __call__(self, *args, **kwargs):
        self.delivered = self._case.records()["delivered"]
        return self._lands(*args, **kwargs)


class _DiesOnTheWrite:
    """The pinned writes a tick makes, ending on the first one `ends` picks out, which never lands."""

    def __init__(self, case, ends) -> None:
        self._ends = ends
        self._writes = case.github.write_pinned_state

    def __call__(self, issue, state):
        if self._ends(issue, state):
            raise RuntimeError("the process died on a pinned write")
        return self._writes(issue, state)


@contextlib.contextmanager
def dying_behind_the_relabel(case):
    """A process that ends on the write behind the relabel to `validating`, the relabel itself landed."""
    ends = _DiesOnTheWrite(
        case, lambda issue, _state: case.github.workflow_label(issue) == WorkflowLabel.VALIDATING,
    )
    with patch.object(case.github, "write_pinned_state", ends), contextlib.suppress(RuntimeError):
        yield


class _ConflictDriftReportMixin(_drift_world._DriftReportMixin):
    """Ticks over an approved, documented pull request whose requirements moved mid-rebase."""

    def seeded_on_conflict(self, *, documented: bool = True, **pinned) -> None:
        """The approved pull request, its report, and the edit that lands mid-rebase.

        The report is settled against the requirements as they stood, and the
        edit is made afterwards, so the baseline the pinned comment carries is
        the one that report answered and the issue has since moved off it.
        Not `documented`, no final-docs pass has run on the head the pull
        request stands on, so nothing records it as a head this orchestrator
        produced. `pinned` overrides what the comment is seeded with -- the
        rounds spent, or a park already standing.
        """
        self.seeded(ISSUE, PR, LABEL_RESOLVING_CONFLICT, **{
            "conflict_round": 0,
            "review_round": 2,
            "docs_checked_sha": _drift_world.PUBLISHED_HEAD if documented else None,
            **pinned,
        })
        state = self.github.read_pinned_state(self.issue)
        state.set("user_content_hash", _drift_world.handed_revision(self.issue))
        self.github.write_pinned_state(self.issue, state)
        _published_reports.approves_the_report(self.github, self.issue)
        self.opening_report = None
        self.opening_report = self.records()["current"]
        _drift_world.edits(self, CHANGED_REQUIREMENTS)

    def drift(self, run_agent, **run_options):
        """One tick of the issue's stage, its git answering as a branch on its base unless `base` says otherwise."""
        with run_options.pop("base", None) or on_its_base(), _fix_world.author_policy():
            return super().drift(run_agent, **run_options)

    def reconcile(self):
        """The dispatch reconciliation ahead of the next handler, under the same policy."""
        with _fix_world.author_policy():
            return super().reconcile()

    def handed(self) -> str:
        """The revision a resume launched on the edited issue is handed."""
        return _drift_world.handed_revision(self.issue)

    def refreshes(self) -> MagicMock:
        """The per-tick base refresh over this issue's checkout, the base one commit ahead of it.

        What it hands the rewrite route is answered by the double handed back,
        so a case reads whether the refresh would have rebased and pushed.
        """
        rewrite = MagicMock()
        with (
            seam_patch("_git", MagicMock(return_value=_BEHIND_BASE)),
            patch.object(_base_rewrite, "_sync_pr_worktree_to_base", rewrite),
        ):
            _base_refresh._sync_claimed_worktree(
                self.github, _TEST_SPEC, _drift_world._EXISTING_WORKTREE, ISSUE,
            )
        return rewrite

    @contextlib.contextmanager
    def dying_at_the_count(self):
        """A process that ends on the write that would make the first round's count durable, before it lands."""
        ends = _DiesOnTheWrite(self, lambda _issue, state: state.get("conflict_round") == 1)
        with patch.object(self.github, "write_pinned_state", ends), contextlib.suppress(RuntimeError):
            yield

    @contextlib.contextmanager
    def dying_at_the_binding(self):
        """A process that ends as the report is bound, the round counted and handed on before it."""
        with (
            patch.object(_report_binding, "binds_the_delivery", side_effect=RuntimeError),
            contextlib.suppress(RuntimeError),
        ):
            yield
