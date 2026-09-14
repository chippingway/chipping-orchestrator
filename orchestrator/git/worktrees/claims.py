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
"""
from __future__ import annotations

import logging
from typing import Any

from orchestrator import config
from orchestrator.git.worktrees import naming as _naming
from orchestrator.git.worktrees.models import Retention, RetentionReason
from orchestrator.github import issues as github_issues
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.state import WorkflowLabel, label_for_name

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
    """The issue's authenticated pinned state, or the reason it is not one.

    Authenticated because the parse behind it is: the pinned comment is
    matched only when the bot itself wrote it and the body is the state
    marker alone, so a human pasting a state-shaped comment onto the thread
    cannot redirect a reclamation at a branch of their choosing.

    An issue with no pinned comment is a real answer -- the empty state, which
    a candidate the orchestrator never got as far as recording looks exactly
    like. A read that RAISED is not, and it is retained on: the recorded pull
    request and branch live in that comment, so a reclamation that treated an
    unreadable state as an empty one would go looking for neither.

    The payload is checked for being a state at all, because authentication
    does not make it one, and it is checked twice because it can fail to be
    one in two ways. A comment carrying valid JSON the bot wrote -- `[]`,
    `"x"` -- comes back as a `PinnedState` whose data has no `get`, and every
    reader below would raise on it. A comment carrying JSON that does not
    parse comes back EMPTY, which is the shape of an issue nothing was ever
    recorded for: the parser stands `{}` in so a write can overwrite the
    corruption in place, and `parsed` is how it says the payload is a
    substitute rather than a reading.

    Both are `STATE_MALFORMED` rather than `STATE_UNREADABLE`, because what
    an operator does with them differs from what they do with a failed
    request: an API failure clears itself on the next tick, while a corrupted
    pinned comment stays until a human edits it. Spending the substitute as a
    record instead would be the sharper mistake -- the recorded branch and
    pull request are exactly what it does not carry, so a candidate whose
    claims live there would read as a candidate with no claims at all.

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
    if not state.parsed:
        log.warning(
            "issue=#%d pinned state did not parse; refusing to classify its "
            "artifacts against the empty payload standing in for it",
            issue_number,
        )
        return Retention(RetentionReason.STATE_MALFORMED, subject)
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

    A set of members rather than of names, so the two spellings of one state
    -- the namespaced label the orchestrator writes and the bare one a
    repository carried before the migration -- count once. What is left over
    is genuine: two labels naming two different states, which is the case the
    caller refuses on.

    Labels that are not workflow states at all are absent, the operator's own
    `backlog` and `paused` controls included. They coexist with a state by
    design and say nothing about which one the issue is in.
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
    named `orchestrator/issue-<n>` and this scan found them, but nothing on
    the issue says this orchestrator ever drove it -- and a candidate nobody
    can attribute to a finished run is not one to act on.
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
    ended on a legacy ref, or on a branch a human has since renamed, still
    records its pull request number here, and that pull request is the thing
    reviewers are looking at.

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
    spec: config.RepoSpec,
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
    miss. The reported ones are what this host actually holds. Both names
    this orchestrator publishes an issue under are added whether or not the
    host still has them: an issue whose legacy branch was deleted locally
    still has its pull request open on the remote, and a scan reporting only
    the namespaced branch would have nothing to ask about. And the branch the
    pinned state resolves to is added on top, since a record can name a
    branch neither derivation produces.

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
    asked = set(branches) | set(
        _naming._issue_branch_names(spec, issue_number),
    ) | {_naming._resolve_branch_name(state, spec, issue_number)}
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
