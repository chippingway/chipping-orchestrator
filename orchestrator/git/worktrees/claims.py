# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What GitHub still says about an issue whose artifacts a host is holding.

The remote half of a reclamation decision. A checkout and a branch on this
host say nothing about whether the work they carry is finished -- only the
issue does, and only its pull requests say whether anybody is still standing
on the branch. Two questions are put here: whether the issue has actually
ended, and whether an open pull request still claims one of these branches.
Either settles a candidate before any artifact is read; what a terminal pull
request published is a question about one commit rather than about the issue,
and ``commit_claims`` owns it.

Every read is behind its own boundary, and every boundary produces a
retention rather than a raise or a default. A pull-request lookup that failed
is not "no pull request", and an issue that could not be fetched is not an
issue that ended: read either way round, the reclamation runs on the strength
of a question nobody put. The reads are lazy on the wire too -- a PyGithub
object raises from the first attribute touched as readily as from the call
that produced it -- which is why the boundaries are around the use and not
only around the request.

Ending is read strictly. The issue must be closed, and the workflow labels on
it must come to exactly one state, and that state must be `done` or
`rejected`. An issue carrying two of them is one no reading here can settle:
the label vocabulary is what the whole state machine routes on, so an issue
in two states at once is a repository somebody is in the middle of editing,
not a candidate.

The pinned record is held to admission, whatever the labels say. One that
admission refuses -- a missing or unsupported version, or a payload that is
no state -- keeps the candidate even on an issue closed on a terminal label:
it reads back empty, which is what an issue nothing was recorded for reads
as, and taken that way the pull request and branch it names would go
unasked. It is said in one local line naming the repository, the issue, and
the version found against the one supported, and nothing is written for it.
An issue with no pinned comment at all is no refusal and is classified as
ever.
"""
from __future__ import annotations

import logging
from typing import Any

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import naming as _naming
from orchestrator.git.worktrees.models import Retention, RetentionReason
from orchestrator.github import issues as github_issues
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.label_reading import label_for_name
from orchestrator.workflow.state import WorkflowLabel

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so a question that could not be put
# reports where their filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")

# The two states an issue whose artifacts may be reclaimed can have ended in.
# Both are terminal in the transition table and neither has an arc out of it,
# so nothing that runs later needs the checkout or the branch.
TERMINAL_LABELS = frozenset((WorkflowLabel.DONE, WorkflowLabel.REJECTED))

_OPEN_PULL_REQUEST = "open"

# What the pass does with a pinned record admission refuses.
_RECORD_KEPT = "keeping every checkout and branch of the issue for whoever disposes of the record"


def _fetched_issue(gh: GitHubClient, issue_number: int) -> Any | None:
    """The issue one candidate names, or None when GitHub would not say.

    An artifact scan reads a number off a directory or a branch, which is a
    name rather than a fact: the issue may have been transferred, deleted, or
    simply be unreachable this tick. None is what the caller retains on,
    because every question after this one is asked of the issue -- and an
    absent issue read as an ended one reclaims the artifacts of an issue that
    is, as far as anybody here knows, still running.
    """
    try:
        return gh.get_issue(issue_number)
    except Exception:
        log.warning(
            "issue=#%d could not be fetched while classifying its artifacts",
            issue_number, exc_info=True,
        )
        return None


def _read_state(
    gh: GitHubClient, issue: Any, issue_number: int,
) -> PinnedState | Retention:
    """The issue's admitted pinned state, or the reason it is not one.

    Authenticated because the parse behind it is: the pinned comment is
    matched only when the bot itself wrote it and the body is the state
    marker alone, so a human pasting a state-shaped comment onto the thread
    cannot redirect a reclamation at a branch of their choosing.

    An issue with no pinned comment is a real answer -- the empty state, which
    a candidate the orchestrator never got as far as recording looks exactly
    like. A read that RAISED is not, and it is retained on: the recorded pull
    request and branch live in that comment, so a reclamation that treated an
    unreadable state as an empty one would go looking for neither.

    Nor is a comment admission refuses, though it reads back just as EMPTY:
    the parser stands `{}` in for a payload that will not parse, that is no
    object, or that is an object under a missing or unsupported version, and
    `supported` is how it says the payload is a substitute rather than a
    reading. Spending the substitute as a record would be the sharper mistake
    -- the recorded branch and pull request are exactly what it does not
    carry, so a candidate whose claims live there would read as a candidate
    with no claims at all, and an issue closed on a terminal label would have
    its artifacts reclaimed on the strength of a record nobody read. The
    refusal is said in the one local line naming the repository, the issue,
    the comment, its admission status, and the version found against the one
    supported, and the record is left for whoever disposes of it.

    A payload that is no state at all is `STATE_MALFORMED` and an object
    under a version this build does not admit is `STATE_UNSUPPORTED`, and
    neither is `STATE_UNREADABLE`, because what an operator does with them
    differs from what they do with a failed request: an API failure clears
    itself on the next tick, while a refused pinned comment stays until a
    human disposes of it. A state built in memory rather than parsed can
    still carry a payload with no `get` on it, and every reader below would
    raise on it, so it is checked for being an object as well.

    The reason is returned rather than raised, and the issue number comes from
    the candidate rather than off the issue, so that neither the answer nor
    the subject naming it depends on an attribute that can fail on the wire.
    """
    subject = f"#{issue_number}"
    try:
        state = gh.read_pinned_state(issue)
    except Exception:
        log.warning(
            "issue=#%d pinned state could not be read while classifying its "
            "artifacts", issue_number, exc_info=True,
        )
        return Retention(RetentionReason.STATE_UNREADABLE, subject)
    if not state.supported:
        log.warning(
            "repo=%s issue=#%d pinned comment #%s is %s (found schema_version %r, supported %s: %s); %s",
            state.repo_slug, issue_number, state.comment_id, state.admission_status.value,
            state.found_version, state.supported_version, state.refusal_reason, _RECORD_KEPT,
        )
        refused = RetentionReason.STATE_UNSUPPORTED if state.parsed else RetentionReason.STATE_MALFORMED
        return Retention(refused, subject)
    if not isinstance(state.data, dict):
        log.warning(
            "issue=#%d pinned state is a %s rather than an object; refusing "
            "to classify its artifacts against it",
            issue_number, type(state.data).__name__,
        )
        return Retention(RetentionReason.STATE_MALFORMED, subject)
    return state


def _workflow_members(issue: Any) -> frozenset[WorkflowLabel]:
    """Every workflow state this issue's labels put it in.

    Only canonical labels count, so more than one member is genuine: two
    labels naming two different states, which is the case the caller refuses
    on.

    Labels that are not workflow states at all are absent, the operator's own
    `backlog` and `paused` controls included. They coexist with a state by
    design and say nothing about which one the issue is in. So is a bare name
    such as `implementing`: it is repository metadata, and an issue carrying
    nothing else has no workflow label to own artifacts by.
    """
    named = (
        label_for_name(getattr(label, "name", "") or "")
        for label in (issue.labels or [])
    )
    return frozenset(member for member in named if member is not None)


def _terminal_retentions(
    issue: Any, issue_number: int,
) -> tuple[Retention, ...]:
    """Why this issue is not one whose artifacts may be reclaimed, if it is not.

    The boundary around the reading rather than the reading itself. Every
    field it consults is lazy on the wire -- a PyGithub issue fetches on the
    first attribute touched, and its labels are their own request -- so a
    failure here is a question that could not be put, and it answers as one.
    Left to propagate it would take the whole classification out on a
    transient error, which is the one way an unreadable issue could end up
    costing more than the artifact it is about.

    The issue number comes from the candidate rather than off the issue,
    since reading it is exactly what may fail.
    """
    try:
        return _ended_retentions(issue, issue_number)
    except Exception:
        log.warning(
            "issue=#%d could not be read while classifying its artifacts",
            issue_number, exc_info=True,
        )
        return (Retention(
            RetentionReason.ISSUE_UNREADABLE, f"#{issue_number}",
        ),)


def _ended_retentions(
    issue: Any, issue_number: int,
) -> tuple[Retention, ...]:
    """The ending itself, inside the boundary that owns its failures.

    Closed AND terminally labelled, because neither half implies the other. A
    human closes an issue mid-implementation and the workflow label stays
    where it was, which is a running issue somebody ended by hand rather than
    one that finished; a `done` label on an open issue is a state the closing
    write has not reached yet, and the tick that reaches it may reopen work.

    An issue with no workflow label at all is refused too. Its artifacts are
    named for it and this scan found them, but nothing on the issue says this
    orchestrator ever drove it -- and a candidate nobody can attribute to a
    finished run is not one to act on.
    """
    subject = f"#{issue_number}"
    if not github_issues.issue_is_closed(issue):
        return (Retention(RetentionReason.ISSUE_OPEN, subject),)
    members = _workflow_members(issue)
    if not members:
        return (Retention(RetentionReason.NO_WORKFLOW_LABEL, subject),)
    if len(members) > 1:
        return (Retention(
            RetentionReason.AMBIGUOUS_WORKFLOW_LABEL,
            ", ".join(sorted(members)),
        ),)
    state_label = next(iter(members))
    if state_label not in TERMINAL_LABELS:
        return (Retention(
            RetentionReason.NON_TERMINAL_LABEL, str(state_label),
        ),)
    return ()


def _recorded_pull_request(
    gh: GitHubClient, state: PinnedState,
) -> tuple[Retention, ...]:
    """Whether the pull request the pinned state names is still open.

    The authoritative claim, and the one a branch lookup can miss: an issue
    that ended on a branch the current layout does not derive, or on one a
    human has since renamed, still records its pull request number here, and
    that pull request is the thing reviewers are looking at.

    A number that is not one -- a state field somebody edited, a value from a
    schema this code does not know -- is read as a lookup that failed rather
    than as no pull request at all, which is what the conversion sitting
    inside the boundary is for.
    """
    recorded = state.get("pr_number")
    if recorded is None:
        return ()
    try:
        recorded_state = gh.pr_state(gh.get_pr(int(recorded)))
    except Exception:
        log.warning(
            "the recorded pull request %r could not be read while "
            "classifying artifacts", recorded, exc_info=True,
        )
        return (Retention(
            RetentionReason.PULL_REQUEST_UNREADABLE, f"#{recorded}",
        ),)
    if recorded_state == _OPEN_PULL_REQUEST:
        return (Retention(
            RetentionReason.OPEN_PULL_REQUEST, f"#{recorded}",
        ),)
    return ()


def _open_pull_request_retentions(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    branches: tuple[str, ...],
    state: PinnedState,
) -> tuple[Retention, ...]:
    """Every open pull request still standing on this issue's artifacts.

    Both ways of asking, because they find different things. The recorded
    number finds the pull request this issue's own run opened, whatever
    branch it went out on. The per-branch lookup finds one opened on a branch
    this host holds -- by a human, by a superseded run -- which nothing in
    the pinned state would ever name.

    Three sources of branch names, because each finds something the others
    miss. The reported ones are what this host actually holds. The issue's
    current-layout name is added whether or not the host still has it: a
    candidate found by its checkout alone still has a branch a pull request
    can stand on. And the branch the pinned state names is added on top, as
    the record spells it, since a record can name a branch that derivation
    does not produce and the live resolver refuses. That name owns nothing
    here -- the teardown spends only the current one -- and asking about it
    can only keep a candidate, never clear one.

    No base is named, so what comes back is a pull request open from this
    branch to ANY base. The question is whether anybody is still standing on
    the branch, and a reviewer looking at it retargeted onto a release line,
    onto another issue's branch, or onto a base this repository was
    reconfigured away from is standing on it just as squarely -- while a
    lookup filtered by the configured base would report nobody there.

    Every failed lookup is its own retention rather than a skipped branch: an
    unanswered question about one branch says nothing about the others, and
    the operator has to be told which branch nobody could answer for.
    """
    asked = set(branches) | {_naming._branch_name(spec, issue_number)}
    pinned = state.get(_naming._PINNED_BRANCH)
    if isinstance(pinned, str) and pinned:
        asked.add(pinned)
    retentions = _recorded_pull_request(gh, state)
    for branch in sorted(asked):
        try:
            open_pull_request = gh.find_open_pr(branch=branch)
        except Exception:
            log.warning(
                "the open pull requests on %r could not be listed while "
                "classifying artifacts", branch, exc_info=True,
            )
            retentions += (Retention(
                RetentionReason.PULL_REQUEST_UNREADABLE, branch,
            ),)
            continue
        if open_pull_request is not None:
            retentions += (Retention(
                RetentionReason.OPEN_PULL_REQUEST, branch,
            ),)
    return retentions
