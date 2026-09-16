# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issue-state vocabulary, label writes and history, comments, and children.

The issue-state vocabulary lives here -- the attribute PyGithub carries it on
and the values it takes -- because it is the GitHub wire spelling, not a
workflow one: every reader that asks whether an issue is still open, and every
writer that closes one, has to spell it the way the API does -- the poller and
the two terminal owners included. The swept label sets sit beside it for the
reason the dispatcher reads them from here as well: which closed issues are
still owed a pass is a statement about issue state, not about how one walk
over a repository is taken.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from github.Issue import Issue
from github.IssueComment import IssueComment
from github.Label import Label

from orchestrator import config
from orchestrator.github import events, labels
from orchestrator.github.comments import carries_own_marker
from orchestrator.observability.analytics.recording import events as _recording_events
from orchestrator.workflow import (
    label_reading as _label_reading,
    state as _workflow_state,
    transition_guard as _transition_guard,
)

log = logging.getLogger("orchestrator.github")

_PARK_AWAITING_HUMAN = "park_awaiting_human"

_STATE_ATTR = "state"
_ISSUE_STATE_OPEN = "open"
_ISSUE_STATE_CLOSED = "closed"
# What the orphan lookup asks for: a child nobody has attributed yet is one a
# human may have closed, so an open-only search would miss it and duplicate.
_ISSUE_STATE_ALL = "all"
_RECORDED_EVENTS_CAP = 500

# The stages whose closed issues still have a terminal arc left to drain: an
# externally merged PR, a human closing the issue out from under a running
# agent, or -- on the two operator-applied conversation labels -- the close
# itself being the whole signal. The in-memory double sweeps this same set.
#
# What is absent is the decomposition family, because none of it has a
# terminal arc to drain: `ready` and `blocked` are a hard human stop with
# nothing to finalize, and `decomposing` and `umbrella` publish nothing on
# their own. All four are queried for CLEANUP only -- see
# `CLEANUP_ROUTE_LABELS` -- and none of them enters the arcs this set drives.
#
# A label leaves this set by being written off the issue, which every terminal
# arc does as it fires -- so in steady state the sweep costs one pass per
# closed issue. `discussion` is the one exception, and it is deliberate: a
# discussion whose plan PR is still open holds its terminal rather than taking
# one, KEEPING the label, so the sweep goes on yielding that issue every pass
# until the humans decide the pull request. Nothing else revisits a closed
# issue, and the branch and worktree the plan lives on have nothing else that
# would reap them.
CLOSED_SWEEP_LABELS: tuple[_workflow_state.WorkflowLabel, ...] = (
    _workflow_state.WorkflowLabel.IMPLEMENTING,
    _workflow_state.WorkflowLabel.DOCUMENTING,
    _workflow_state.WorkflowLabel.VALIDATING,
    _workflow_state.WorkflowLabel.IN_REVIEW,
    _workflow_state.WorkflowLabel.FIXING,
    _workflow_state.WorkflowLabel.RESOLVING_CONFLICT,
    _workflow_state.WorkflowLabel.QUESTION,
    _workflow_state.WorkflowLabel.DISCUSSION,
)

# The two states an issue that owns a preserved candidate can be closed on,
# and the only closed issues outside the set above that any pass revisits.
# They are queried apart because what they earn is different in kind: nothing
# here resumes a workflow, spawns an agent, or activates a child. The one
# reason to come back is that a split records obligations on the remote --
# the branch its superseded candidate sat on, and the immutable ref the
# children were cut from -- and an issue a human closed mid-cycle is one no
# other pass would ever bring a tick back to.
#
# `decomposing` is where a candidate is adjudicated and where the split
# transaction runs, and `umbrella` is what the parent is handed on to once it
# lands; between them they cover every state in which a generation ledger can
# START holding something the remote owes. They are the pair an OPEN issue is
# refetched on, too -- there a close decides which handler runs, and the wrong
# answer spawns the decomposer or activates children on an issue somebody has
# ended.
CLEANUP_SWEEP_LABELS: tuple[_workflow_state.WorkflowLabel, ...] = (
    _workflow_state.WorkflowLabel.DECOMPOSING,
    _workflow_state.WorkflowLabel.UMBRELLA,
)

# The two an interrupted ending can be LEFT on, which is a different question
# from where one runs. A decomposition outcome writes `ready` or `blocked`,
# and a run spawned before its owner was observed closed lands after that
# observation -- so a close latched, receipted on the thread, and never yet
# marked can end up on an issue that is closed under one of these. The latch
# that would route it is memory; a process that exits before any cleanup pass
# runs takes it away, and nothing else would ever bring a tick back to that
# owner: the ref its children were cut from would be held by a repository
# nobody asks about again.
#
# So their CLOSED issues are queried, and only theirs -- an open one is
# dispatched exactly as before, since an ending is not something an open issue
# on either label is in the middle of. What that costs is one pinned read per
# closed issue on them per sweep, on the `CLOSED_ISSUE_SWEEP_EVERY_N_TICKS`
# cadence that exists to bound precisely this, and what it buys is an ending
# no restart can lose.
CLEANUP_RECOVERY_LABELS: tuple[_workflow_state.WorkflowLabel, ...] = (
    _workflow_state.WorkflowLabel.READY,
    _workflow_state.WorkflowLabel.BLOCKED,
)

# Every label a CLOSED issue reaches the cleanup pass under. The dispatcher
# routes on this rather than on either half: what the pass does is read one
# record and settle whatever late cycle it finds, which is the same question
# wherever the label came from.
CLEANUP_ROUTE_LABELS: tuple[_workflow_state.WorkflowLabel, ...] = (
    CLEANUP_SWEEP_LABELS + CLEANUP_RECOVERY_LABELS
)


def issue_is_closed(issue: Any) -> bool:
    """Whether GitHub reports this issue as closed.

    The wire spelling is `state`, and on a PyGithub issue it is the only one:
    nothing there is called `closed`. A reader that asks for that attribute
    alone therefore answers "open" for every closed issue in production while
    passing every test, because the in-memory double DOES carry the flag --
    which is exactly the shape of bug this predicate exists to stop being
    written twice. It lives here because the state vocabulary does.

    Both shapes are honored, as the dispatcher's own check has always done:
    the flag is asked first and only when it is set, so an issue that merely
    lacks it falls through to `state` rather than reading as open. Anything
    that is not an issue at all -- the `None` a scan holds for a consumer it
    never fetched -- is not closed, leaving a caller that must fail closed on
    an absence to say so itself, where it knows what the absence means.
    """
    if bool(getattr(issue, "closed", False)):
        return True
    state = getattr(issue, _STATE_ATTR, _ISSUE_STATE_OPEN)
    return state == _ISSUE_STATE_CLOSED


def issue_query_options(
    *,
    issue_state: str,
    since: datetime | None,
    label: Label | None = None,
) -> dict[str, Any]:
    """Build common open/closed issue query options."""
    query_options: dict[str, Any] = {
        "state": issue_state,
        "sort": "updated",
        "direction": "desc",
    }
    if label is not None:
        query_options["labels"] = [label]
    if since is not None:
        query_options["since"] = since
    return query_options


def _cache_written_labels(issue: Issue, label_names: list[str]) -> None:
    """Leave the issue object a write went through reading what it wrote.

    PyGithub's `set_labels` sends the PUT and keeps nothing of the answer, so
    the object would go on serving the labels it was fetched with -- and the
    next write through it would have the transition guard judge its edge from
    the state before this one: `None -> ready` for a pickup whose
    decomposition ends in the same tick. What is stored is the set the write
    sent, in the shape a label listing carries, so no request is spent reading
    it back. Only this object moves; any other one for the same issue still
    carries what it was fetched with.
    """
    issue._useAttributes({"labels": [{"name": str(name)} for name in label_names]})


def set_workflow_label(
    client: Any,
    issue: Issue,
    new_label: str | None,
    *,
    guarded: bool = True,
) -> None:
    """Replace only the workflow label and emit its stage-enter event.

    A write that returns leaves `issue` reading the labels it wrote, so a
    second relabel through the same object in one tick is guarded against
    the state the first one left. A write GitHub refuses raises before either
    the cached labels or the stage-enter event move.

    `guarded=False` is for the one write that is not a transition: putting a
    label back where a human moved it from. The graph describes the moves this
    orchestrator makes, so under `enforce` it would refuse a repair of a move
    it never made -- `validating -> decomposing` is not a step the workflow
    takes, and the whole reason to write it is that the issue is not on the
    label it should be. Refusing there would strand the issue under the wrong
    one for as long as the operator kept the guard on, which is the opposite
    of what the guard is for.
    """
    new_workflow_label = (
        _label_reading.coerce_workflow_label(new_label) if new_label else None
    )
    if new_workflow_label is not None and guarded:
        _transition_guard.guard_transition(
            client.workflow_label(issue),
            new_workflow_label,
            config.WORKFLOW_TRANSITION_GUARD,
        )
    # Only the labels this write actually owns come off. A bare tag beside a
    # namespaced one belongs to the repository, not to the orchestrator, so it
    # survives -- see `replaced_label_names`.
    label_names = [issue_label.name for issue_label in issue.labels]
    replaced = _label_reading.replaced_label_names(label_names)
    kept_labels = [name for name in label_names if name not in replaced]
    if new_workflow_label is not None:
        kept_labels.append(new_workflow_label)
    issue.set_labels(*kept_labels)
    _cache_written_labels(issue, kept_labels)
    if new_workflow_label is not None:
        # The event and the analytics row name the state by its bare tag: the
        # namespace is a GitHub label spelling, and every reader downstream of
        # here keys on the tag under it.
        client._emit_stage_enter(issue, _workflow_state.stage_name(new_workflow_label))


# The event kind GitHub records when a label is put ON an issue. A removal is
# its own kind and is deliberately not counted: what the reading below is
# about is the last state this workflow PUT the issue in, and an operator
# taking a label off does not put it in another one.
_LABELED_EVENT = "labeled"


def _last_workflow_labeling(issue: Issue, bot_login: str) -> str | None:
    """The newest workflow label THIS orchestrator applied to the issue.

    The walk is oldest-first, which is the order the events endpoint serves,
    so the last match wins.

    Two filters, and both are what makes the answer mean "a state this
    orchestrator put the issue in". The ACTOR has to be its own account: every
    workflow label is one it writes itself, and a collaborator is free to
    apply and remove the same names by hand -- reading one of those back would
    let somebody outside the workflow forge the record of a write it never
    made. And the label has to be in the workflow vocabulary: a control label
    is an operator's modifier rather than a state, so a `paused` applied over
    a terminal must not displace it, and anything a repository names its own
    issues by is not this vocabulary at all.
    """
    latest = None
    for issue_event in issue.get_events():
        applied = _workflow_label_applied(issue_event, bot_login)
        if applied is not None:
            latest = applied
    return latest


def _workflow_label_applied(issue_event: Any, bot_login: str) -> str | None:
    """The workflow label one event says this orchestrator applied, or None."""
    if getattr(issue_event, "event", None) != _LABELED_EVENT:
        return None
    actor = getattr(getattr(issue_event, "actor", None), "login", None)
    if actor != bot_login:
        return None
    named = getattr(getattr(issue_event, "label", None), "name", None)
    return _label_reading.label_for_name(named) if named else None


class GitHubIssueMixin:
    """Issue-facing methods shared by the concrete GitHub client."""

    workflow_label = labels.WORKFLOW_LABEL_METHOD
    set_workflow_label = set_workflow_label

    def last_workflow_label_applied(self, issue: Issue) -> str | None:
        """The workflow label most recently APPLIED to this issue, or None.

        The one question about an issue's PAST this client answers, and it is
        here because nothing else can answer it: a label removed leaves the
        issue looking exactly like one that never carried it, and the pinned
        comment cannot record what a process that died never got to write.

        The newest application rather than "was it ever applied", because a
        caller asking this is asking about one attempt and an issue reaches
        the same state more than once. What separates the attempts is that
        every state this workflow moves an issue to is itself an application:
        a label applied after another one is proof the first is not the
        latest, whatever the two were.

        Only this orchestrator's OWN applications count, on the same
        authentication the pinned comment is read under: the answer is about a
        write it made, and a collaborator applying the same name by hand made
        no such write. An account this client could not establish therefore
        answers nothing at all rather than trusting every actor.

        `None` is the absence of evidence and covers every way of having
        none -- nothing this orchestrator applied, nothing this vocabulary
        recognizes, no account to attribute by, and a walk that failed. A
        caller here fails closed on all of them.

        Costs one paginated walk of the issue's own timeline, so it is for
        callers that have already narrowed themselves to a state the local
        record cannot decide. Nothing asks it in the steady state.
        """
        bot_login = getattr(self, "_bot_login", None)
        if bot_login is None:
            return None
        try:
            return _last_workflow_labeling(issue, bot_login)
        except Exception:
            log.exception(
                "issue=#%s label history could not be read; nothing is "
                "concluded from a request that failed",
                getattr(issue, "number", "?"),
            )
            return None

    def emit_event(
        self,
        event: str,
        *,
        issue_number: int,
        stage: str | None = None,
        **extras: Any,
    ) -> None:
        """Record an event in memory, in the audit sink, and fan out to analytics.

        Every event is recorded in memory (capped tail) and in the optional audit
        JSONL sink (`EVENT_LOG_PATH`). In addition, `park_awaiting_human` events
        are fanned out to the analytics recorder (`record_park_awaiting_human`).
        Other event families with dedicated analytics producers are excluded from
        fan-out. Analytics recording errors are logged and swallowed so failure
        cannot disrupt workflow progress or alter issue state.
        """
        event_record = events.build_event_record(
            repo=self._repo_slug,
            issue_number=issue_number,
            event=event,
            stage=stage,
            **extras,
        )
        self.recorded_events.append(event_record)
        if len(self.recorded_events) > _RECORDED_EVENTS_CAP:
            self.recorded_events = self.recorded_events[-_RECORDED_EVENTS_CAP:]
        events.write_event_record(event_record)
        if event == _PARK_AWAITING_HUMAN:
            try:
                _recording_events.record_park_awaiting_human(
                    repo=self._repo_slug,
                    issue=issue_number,
                    stage=stage,
                    **extras,
                )
            except Exception as error:  # noqa: BLE001 - analytics recording failure must never break event emission
                log.warning(
                    "issue=#%s park_awaiting_human analytics record failed: %s",
                    issue_number,
                    error,
                )

    def comment(self, issue: Issue, body: str) -> IssueComment:
        """Post one issue comment."""
        return issue.create_comment(body)

    def get_issue(self, number: int) -> Issue:
        """Return one issue by repository number."""
        return self.repo.get_issue(number)

    def create_child_issue(
        self,
        *,
        title: str,
        body: str,
        parent_number: int,
        labels: list[str],
    ) -> Issue:
        """Create a child with validated workflow labels and a parent link."""
        validated_labels = [
            _label_reading.coerce_workflow_label(label_name)
            for label_name in labels
        ]
        parent_body = (body or "").rstrip()
        full_body = f"{parent_body}\n\nParent: #{parent_number}"
        return self.repo.create_issue(
            title=title,
            body=full_body,
            labels=validated_labels,
        )

    def find_issue_carrying(self, marker: str) -> Issue | None:
        """Return the issue this orchestrator created carrying `marker`.

        The lookup a create that returned and a process that died a statement
        later needs. Creating an issue is not undoable and nothing outside
        GitHub knows the number, so the only way back to it is something the
        creator put IN it: a hidden marker naming the exact adjudication and
        the exact slice the issue was opened for.

        Searched in EVERY state and under no label, which is the expensive
        reading and the only correct one. The window this exists for is a
        child nobody has attributed yet, and in that window a human is free to
        close it as junk or move its label -- and a lookup scoped to open
        issues on the label it was born with would miss exactly those and open
        a second issue beside the one they had just acted on. What the caller
        does with a candidate it did not expect is the caller's; this answers
        whether one exists.

        Pull requests are dropped because the issue endpoint returns them too
        and a pull request is not a child.

        The body is what carries the marker, and the author is checked with
        it: the whole point is to recognize an issue THIS orchestrator opened,
        and an issue somebody else wrote the marker into is not one to adopt,
        reseed, and activate as a child.
        """
        for candidate in self.repo.get_issues(
            **issue_query_options(issue_state=_ISSUE_STATE_ALL, since=None),
        ):
            if candidate.pull_request is not None:
                continue
            if carries_own_marker(
                [candidate], marker, bot_login=getattr(self, "_bot_login", None),
            ):
                return candidate
        return None
