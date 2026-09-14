# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one bounded record a maintenance pass leaves for a candidate it decided.

Exactly one `terminal_artifact_cleanup` record per candidate the pass answered
for -- never one per phase, per artifact, or per deletion step. That
granularity is the whole of what a reader counts on: a pass takes a candidate
as one unit and answers for it once, so a count of these records is a count of
finished issues considered, and a count grouped by outcome is what the host did
about them. A record per branch would make an issue holding both published
layouts look like two, and a record per step would count a candidate whose
teardown ran further than another's as more work rather than the same one
issue.

A candidate the pass never reached has no record, exactly as it has no result:
an interrupted pass answers for the prefix it got to, and the discovery that
found the rest finds them again next interval. Nothing here is a retry list.

What may travel is closed and short: the repository and the issue the envelope
already spells, the outcome, the reason that fixes it, the layout the artifacts
were published under, and -- only where the reason is about one -- the branch.
Every one of them but the last is a member of a vocabulary this package
declares, so the record cannot say anything the code does not already name.
What a teardown actually touched stays off it: no command, no git output, no
exception text, no checkout path, nothing read out of a tree. Those belong to
the operator's `orchestrator.worktree_lifecycle` log, which is where the pass
reports each candidate in full; a sink is a metric surface, and a host's
filesystem layout is not a metric.

The branch is the one field naming an artifact, and what is published is the
name this owner derives rather than the one the result carried. Which kind of
artifact a reason is about is settled from the reason, not from the text of
the subject, because the two kinds are not distinguishable as text: under a
`WORKTREES_DIR` of `orchestrator` a checkout's path and its issue's branch are
the same characters. A checkout path therefore never becomes a branch, and
neither does anything else a result could name.

Nothing written here may change what the pass decided, and it cannot: the
records are built from results the pass has already produced and returned.
Each one rides its own boundary all the same, so a record that cannot be built
leaves every candidate behind it with its own -- a record lost is one line in a
log, while an exception let out of here would cost the answers for a whole pass
that had already run. The sink's own refusals never arrive here: it is silent
when it is turned off and it reports a filesystem that would not take the line
on its own channel.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

from orchestrator.git.worktrees import naming as _naming
from orchestrator.git.worktrees.models import (
    CandidateLayout,
    MaintenanceOutcome,
    MaintenanceReason,
    MaintenanceResult,
)
from orchestrator.observability.analytics import recording

# The channel the pass and its owner already report on, so an operator whose
# filter is pointed at what happened to a finished issue's artifacts is told
# about the record that did not get written as well.
log = logging.getLogger("orchestrator.worktree_lifecycle")

# The event kind one candidate's answer is recorded under. Spelled once, since
# a sink filter and a dashboard query both key off it.
CLEANUP_EVENT = "terminal_artifact_cleanup"

# What a record may carry beyond the envelope's own `ts` / `repo` / `issue` /
# `event`. Nothing outside this tuple is written, so widening the record is a
# deliberate edit here rather than a keyword somebody passed further down.
CLEANUP_PAYLOAD_FIELDS = ("outcome", "reason", "layout", "branch")

# What a refusal names in place of an issue number that did not prove to be
# one. A log line is the same surface a record is bounded for, so a value the
# sink was just protected from is not written into it instead.
_UNNAMED = "?"

# Which artifact a reason is about, read off where the pass spells each one. A
# subject is an artifact's own name and the vocabulary does not say which KIND
# of artifact that is, so the kind is settled here from the reason instead of
# guessed from the string: a checkout path and a branch name are both text, and
# under a `WORKTREES_DIR` of `orchestrator` they are the same text --
# `orchestrator/<slug>/issue-<n>` is what that configuration derives for both.
#
# These three are about a branch and can be about nothing else: the pass spells
# each at one site, on the branch it was taking. Their subject is a branch on
# every host, the one whose checkouts happen to be named like its branches
# included.
_BRANCH_REASONS = frozenset((
    MaintenanceReason.BRANCH_CHECKED_OUT,
    MaintenanceReason.REMOTE_DELETE_FAILED,
    MaintenanceReason.LOCAL_DELETE_FAILED,
))

# These three are about either: the two tip readings are taken over a checkout
# and over a branch, and a retention names whichever artifact kept the
# candidate. Only they are measured against the candidate's own checkouts,
# because only they can be about one -- and a name that is both is a name
# nothing here can attribute.
#
# Every reason in neither set names a checkout (the two quiet-period ones and
# the removal that was refused), the issue itself (the two claim ones), or
# nothing at all (the teardown that finished).
_EITHER_REASONS = frozenset((
    MaintenanceReason.UNPROVEN,
    MaintenanceReason.TIP_MOVED,
    MaintenanceReason.TIP_UNREADABLE,
))


def record_cleanup_results(answers: Iterable[MaintenanceResult]) -> None:
    """Record every candidate the pass decided about, one record each."""
    for answer in answers:
        _recorded(answer)


def _recorded(answer: MaintenanceResult) -> None:
    """Record one candidate's answer, or lose that record and nothing else.

    Total boundary, and it covers the payload as much as the write. A field
    that cannot prove itself a member of its own vocabulary produces no record
    rather than a record nobody should have written, and anything the write
    raises costs this one line -- in both cases the pass has already decided
    and acted, and the candidates behind this one still get theirs.

    What it does NOT see is the sink's own two answers, which are settled a
    layer down and never reach here: a sink turned off short-circuits before
    it opens anything, and a filesystem that refuses the append is caught
    where the line is written and reported on the analytics channel. So a host
    with no sink and a host with a full disk both leave this owner silent, and
    what a line here reports is a record that could not be BUILT or serialized
    at all.

    The failure is named by its type rather than rendered, because an exception
    raised below is free to carry whatever it was handed in its message, and
    the log is the surface this record is bounded for.
    """
    named = _identity(answer)
    try:
        recording.append_record(recording.build_record(
            repo=answer.candidate.artifacts.spec.slug,
            issue=named,
            event=CLEANUP_EVENT,
            **_cleanup_payload(answer),
        ))
    except Exception as refused:  # noqa: BLE001 - a lost record may not cost the pass that had already acted
        log.warning(
            "issue=#%s artifact cleanup record was not written (%s); "
            "the pass and the candidates behind it are unaffected",
            named, type(refused).__name__,
        )


def _identity(answer: MaintenanceResult) -> object:
    """The issue number a record and a refusal may name, or a sentinel.

    Read before the record is attempted rather than inside it, so a refusal
    can say which candidate lost its record however it was refused -- and
    proved to be a number on the way, since a log line is the same surface the
    record is bounded for and a value the sink was protected from may not be
    written into it instead.
    """
    try:
        return int(answer.candidate.artifacts.issue_number)
    except Exception:  # noqa: BLE001 - an unreadable identity is reported, never raised
        return _UNNAMED


def _cleanup_payload(answer: MaintenanceResult) -> dict[str, str | None]:
    """The bounded fields one candidate's record carries beside the envelope.

    Three closed vocabularies and one artifact name. The vocabularies are
    proved again here rather than trusted to the dataclass they arrive on: a
    type annotation bounds nothing at runtime, and the point of the contract
    is that a sink can only ever be told what this package names.
    """
    return {
        "outcome": _member(answer.outcome, MaintenanceOutcome),
        "reason": _member(answer.reason, MaintenanceReason),
        "layout": _member(answer.candidate.layout, CandidateLayout),
        "branch": _named_branch(answer),
    }


def _member(reported: object, vocabulary: type) -> str:
    """One field's own spelling, or a refusal that stops the whole record.

    A lookalike string is refused as squarely as prose: what makes the field
    safe to publish is that it came out of the closed set, not that it happens
    to read like a member of it.
    """
    if not isinstance(reported, vocabulary):
        raise TypeError(vocabulary.__name__)
    return str(reported)


def _named_branch(answer: MaintenanceResult) -> str | None:
    """The branch this answer is about, when it is one this issue's own.

    A result names the artifact its reason is about -- a branch by name, a
    checkout by path, an issue where the reason is about the candidate as a
    whole -- and only the first of those may be published. Which kind it is
    comes off the REASON rather than off the shape of the string, because the
    two are not distinguishable as text: with `WORKTREES_DIR` set to
    `orchestrator`, this issue's checkout path and its branch name are the
    same characters, and a removal that git refused would otherwise be
    published as a branch that was never touched.

    Then the name itself, and it is the derived one that is written rather
    than the subject that arrived: what reaches the sink is a value this owner
    produced from the repository and the issue number, matched against what
    the result named. A path, an issue reference, and a branch some other spec
    on a shared clone owns each fail that match and are dropped.

    Dropped rather than emptied, because the envelope leaves a `None` extra
    out entirely -- a record with no branch key is a reason that was never
    about one, which is a different fact from a branch nobody could name.
    """
    if not _names_a_branch(answer):
        return None
    artifacts = answer.candidate.artifacts
    published = _naming._issue_branch_names(
        artifacts.spec, artifacts.issue_number,
    )
    return next(
        (name for name in published if name == answer.subject), None,
    )


def _names_a_branch(answer: MaintenanceResult) -> bool:
    """Whether the artifact this answer is about is a branch.

    The reason settles it outright for the two families it can: one that is
    only ever spelled on a branch is about a branch on every host, and one
    that is never spelled on a branch is about a branch on none. Neither owes
    the checkouts a reading -- a delete the remote refused names the branch it
    refused, whatever this host happens to have called its checkouts.

    What the checkouts decide is the family in between, where the same reason
    is spelled over a tree in one place and over a ref in another. There the
    subject is all there is to go on, so a name that is also one of this
    candidate's own checkouts is not published: the two artifacts are one
    string, and a record has to say which one it means.
    """
    if answer.reason in _BRANCH_REASONS:
        return True
    if answer.reason not in _EITHER_REASONS:
        return False
    return answer.subject not in {
        str(worktree) for worktree in answer.candidate.artifacts.worktrees
    }
