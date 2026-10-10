# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The publication a body edit's resume owes, recorded with the report it returned.

A resume the edit earns may rebase the branch itself, and a rebase moves the
branch off the head it replaced: the checkout comes back ahead of the pull
request AND behind it, which is the shape the divergence guard parks for fear
of dropping somebody else's commit. A tick that pushes it at once never meets
that guard, but one that dies between the report's record and the push comes
back to exactly that shape -- with the report durable and nothing else saying
whose commits the force-push would drop.

So the publication goes down beside the report: the head the push is leased
against, the commit it sends, and the pull request it goes onto. Staged rather
than written, because the report's own guarded commit is the first durable
write behind it and carries every field the tick changed -- so the two land
together, and a park taken instead of the record lands it too, for the reply
that finishes the same publication. A head nobody could name records nothing,
and neither does a candidate that IS the head it would replace -- until a
report of that head is saved. A run that committed nothing and reported is
still a report of one commit, the head the pull request carries, so that head
goes down as both ends of the record in the very write that saves the report
(`_saved_by_a_report_alone`), over any record an earlier resume left: it owes
no publication, and an earlier record left standing beside it would tie it to
a candidate it is not about. Recorded, it holds that report to its head as
the refusal below holds any other, so a checkout that gains a commit after a
crash cut the binding short neither publishes that commit under the report nor
binds the report to it.

The record speaks for the report it went down with only while that report is
unbound -- the refusal below asks it then and never after -- and nothing
retires it while any report is: not the tail that counts the round, nor the
settlement of some other, older transaction. A push landing is not the end of
it, since the relabel behind that push can fail, and a checkout that gains a
commit before the report is bound would otherwise go out as a recovered push
with the report bound to it. Where no report is unbound the tail drops it
(`_forgets_the_candidate`), and the base refresh that opens the next conflict
episode drops whatever is left, so a record never outlives its episode.

It is no rewrite evidence. The size gate is handed nothing from it: the commit
is the developer's own work, so it is measured as any other candidate is, and
an exemption an adjudication granted for some other commit is never offered
for it. What it licenses is the force-push alone, and only while the pull
request still stands on the head it names and the checkout on the commit it
names, so a record outliving its push licenses nothing more.

It is also what the report saved beside it is ABOUT, and that is the refusal it
carries. A report recorded and not yet bound binds to whatever head the
code-publication receipt names when it is bound, so while it stands this stage
neither publishes a recovered head other than the commit the record names nor
binds the report to a publication of any other: the checkout moved on, or put
back on the head the push would have replaced, the report would reach a
reviewer as the account of a commit it never described. Refused, the issue
parks for the report the work as it stands is owed, and the record stays.

A report whose run left a head nobody could read is refused before it is
recorded at all (`_refuses_an_unread_head`): with no commit to name, no record
could hold it to one, and whatever the checkout carries by the time a later
tick reads it -- a commit gained since included -- would become the head it is
published with or bound to.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads
from orchestrator.workflow.stages.conflicts import models as _models, state as _state

_ANOTHER_HEAD_PARK = (
    "{mentions} the developer report this issue saved for PR #{pr} describes "
    "commit `{candidate}`, and what would go out with it now is `{head}`. "
    "Nothing was pushed and the report was not bound: settled now, it would "
    "reach a reviewer as the account of a commit it never described. Reply and "
    "the orchestrator resumes the session; the report it writes then describes "
    "the branch as it stands and is published with it."
)

_UNREAD_HEAD_PARK = (
    "{mentions} nothing could read the commit the resumed session left on "
    "this issue's worktree, so the developer report it returned was not "
    "recorded and nothing was pushed: a report goes out only about a head "
    "this workflow read, and an unread one could be any commit the checkout "
    "carries by the time it is bound. Repair the checkout and reply, and the "
    "orchestrator resumes the session; the report it writes then describes "
    "the branch as it stands and is published with it."
)


def _stages_the_candidate(
    state: PinnedState, lease: str, candidate: str, pr_number,
) -> None:
    """Stage the publication a resume owes, for the first durable write behind it."""
    number = _payloads.as_identity(pr_number)
    if not (number and _commit(lease) and _commit(candidate)) or lease == candidate:
        return
    state.set(_state._RESUME_FROM_SHA, lease)
    state.set(_state._RESUME_TO_SHA, candidate)
    state.set(_state._RESUME_PR_NUMBER, number)


def _saved_by_a_report_alone(
    state: PinnedState, lease: str, candidate: str, pr_number,
) -> tuple[tuple[str, object], ...]:
    """The record a run that committed nothing writes, as `HandedRun.retires` pairs.

    The head the pull request carries, as both the head replaced and the
    commit sent, over whatever an earlier resume recorded. Written by the
    guarded commit that saves the run's report -- or by the park that holds a
    report owed in its place, which marks the work undescribed -- and by
    nothing else, so an `ACK:` or a question that saves no report leaves the
    record standing beside the earlier report it is about. A pull request
    that will not read retires an earlier record and names nothing, and only
    a record this comment carries, so a comment with none is left without
    empty fields.
    """
    if not _commit(lease) or lease != candidate:
        return ()
    number = _payloads.as_identity(pr_number)
    if number:
        return (
            (_state._RESUME_FROM_SHA, lease),
            (_state._RESUME_TO_SHA, lease),
            (_state._RESUME_PR_NUMBER, number),
        )
    carried = [key for key in _state._RESUME_KEYS if state.get(key) is not None]
    return tuple((key, None) for key in carried)


def _read_candidate(state: PinnedState) -> tuple[str, str, int] | None:
    """The head replaced, the commit sent, and the pull request, or None where any will not read."""
    number = _payloads.as_identity(state.get(_state._RESUME_PR_NUMBER))
    lease = state.get(_state._RESUME_FROM_SHA)
    candidate = state.get(_state._RESUME_TO_SHA)
    if not (number and _commit(lease) and _commit(candidate)):
        return None
    return lease, candidate, number


def _refuses_another_head(ctx: _models._ConflictContext, head: str) -> bool:
    """Park where a saved report would go out with a head other than its own; True where it parked.

    `head` is what is about to be published, or bound: the commit a recovered
    push would send, or the one the code-publication receipt names. Only while
    the report the record went down beside is still unbound -- once it is bound
    or settled, it is about the head it was bound to whatever this stage
    publishes next. The record is left exactly as it stands.
    """
    recorded = _read_candidate(ctx.state)
    if recorded is None or recorded[1] == head:
        return False
    if not _delivery_state.carries_delivered_report(ctx.state):
        return False
    _report_delivery.parks_an_undeliverable_report(
        ctx.gh, ctx.issue, ctx.state, _ANOTHER_HEAD_PARK.format(
            mentions=config.HITL_MENTIONS, pr=recorded[2],
            candidate=recorded[1], head=head or "an unreadable head",
        ),
    )
    return True


def _refuses_an_unread_head(ctx: _models._ConflictContext, head: str) -> bool:
    """Park a report whose run left a head nobody could read; True where it parked.

    `head` is what the run left, read once behind it. The report is about
    that commit and nothing can say which it was, so nothing is recorded and
    nothing pushed. The run's work is marked undescribed, which the recovered
    push refuses to carry out, and the reply to the park resumes the session
    for a report of the branch as it stands.
    """
    if _commit(head):
        return False
    ctx.state.set(_report_delivery.UNREPORTED_WORK, True)
    _report_delivery.parks_an_undeliverable_report(
        ctx.gh, ctx.issue, ctx.state, _UNREAD_HEAD_PARK.format(mentions=config.HITL_MENTIONS),
    )
    return True


def _forgets_the_candidate(state: PinnedState) -> None:
    """Drop the record, staged for the write that counts the round, where no unbound report is about it.

    A report still unbound keeps it, for the refusal above, whichever report
    that is: a record dropped from under a newer report would let the next
    recovered push carry that report onto whatever the checkout gained. A
    comment carrying none is left alone.
    """
    if _delivery_state.carries_delivered_report(state):
        return
    for key in _state._RESUME_KEYS:
        if state.get(key) is not None:
            state.set(key, None)


def _commit(recorded) -> bool:
    """Whether one recorded end is a whole object id and not an abbreviation."""
    return _formats.is_hex_of(recorded, _formats.COMMIT_LENGTHS)
