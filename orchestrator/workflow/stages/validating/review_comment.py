# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned comment a review is bound to, and read against when it returns.

A validating tick that resolves its reviewer's subject does so from the state
it read when it began, and a report settling since -- a later revision on the
very head, by another road -- is recorded on the pinned comment and nowhere in
hand, while the report the tick resolved still reads, exactly as it settled,
where it was. Nothing at that report's own location tells the two apart; only
the records on the comment do.

So `review_report` binds a resolved subject only to a comment read afresh that
carries the report records the state in hand carries (`_resolved_over`), and
every later road that acts on an approval after requests long enough for that
to happen asks the same (`_records_in_hand`): the squash handoff once the
rewrite is published, and the in_review ready ping and the unmergeable park
beside it once mergeability is read. Where the comment moved them, or will not
read or parse, the answer is the one that hands nothing over and writes
nothing: every write from there would be laid over records the tick never
read, putting back the report they replaced. So is a fresh reading of another
comment than the one the state in hand was read from -- the pinned comment
replaced, or gone -- since the tick's write goes to the comment it read and
would pin a second one. The reading that agreed goes on with the subject.

`_records_stand` reads the comment against that reading again, as the reviewer
returns and once more after an approval is verified, before anything the run
leaves is written -- a park for a timeout or a missing verdict as much as the
record of a verdict. Records are compared as the comment's JSON spells them, so
one written `null` where there was none, or a revision spelled `true` where it
was `1`, is a move. Records that stand leave the state alone. Records that
moved refuse the verdict, and everything the comment changed since the subject
was resolved is carried onto the state in hand, so every write the run makes
lays itself over the newer settlement. A comment that will not read or parse,
or is no longer the one the state was read from, carries nothing, and the
answer is the one that writes nothing: the run is charged, and the next tick
spawns a reviewer over whatever the comment carries then.

Nothing here parks or posts.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_records as _records,
    review_subjects as _review_subjects,
)

log = logging.getLogger("orchestrator.workflow")

# Every record a developer report's transaction moves on the pinned comment:
# one in flight, the delivery it binds, and the settled pair a settlement
# replaces.
_REPORT_RECORDS = (
    _records.PENDING_REPORT,
    _records.DELIVERED_REPORT,
    _records.CURRENT_REPORT,
    _records.REPORT_HANDOFF,
)

# What a field the comment does not carry reads as, apart from one it carries
# as `null`.
_ABSENT = object()


@dataclass(frozen=True)
class _ResolvedSubject:
    """A subject a reviewer may be handed, and the comment it was resolved over."""

    subject: _review_subjects.ReviewSubject
    # The pinned comment as it was read once the subject was resolved, which
    # carries the very report records the subject was resolved from: what
    # the verdict's return measures the comment against.
    resolved_over: dict


def _resolved_over(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> dict | None:
    """The comment a subject resolved from `state` is bound to, or None.

    None where the comment will not read or parse, is not the one `state` was
    read from, or carries other report records than `state` does; the caller
    ends the tick without writing.
    """
    durable = _in_hand(gh, issue, state, "bind the report its reviewer is handed")
    return None if durable is None else dict(durable.data)


def _records_in_hand(
    gh: GitHubClient, issue: Issue, state: PinnedState, purpose: str,
) -> bool:
    """Whether the comment still carries the report records `state` carries.

    Asked by a road about to act on an approval of the report `state` records
    as current, and to write `state` beside it, after requests long enough for
    another road to settle a later report. False where it moved them, will
    not read or parse, or is no longer the comment `state` was read from; the
    caller then acts on nothing and writes nothing, so the next tick reads
    what the issue carries then and answers it. `purpose` is what the road was
    about to do, for the log.
    """
    return _in_hand(gh, issue, state, purpose) is not None


def _records_stand(
    gh: GitHubClient, issue: Issue, state: PinnedState, resolved_over: dict,
) -> bool | None:
    """Whether the comment still carries the report records the subject had.

    True where they stand. False where they moved: everything the comment
    changed since `resolved_over` is carried onto `state`, and the verdict is
    not acted on. None where the comment will not read or parse, or is not the
    one `state` was read from, which carries nothing -- a record read back
    empty is no settlement to keep -- and the caller ends the tick without
    writing.
    """
    durable = _read(
        gh, issue, state, "see whether a report settled while the reviewer ran",
    )
    if durable is None:
        return None
    if not _moved(durable.data, resolved_over, _REPORT_RECORDS):
        return True
    # Every field the comment changed since `resolved_over`, as `_moved`
    # spells a change: a field Python calls equal -- `true` over `1` -- is
    # still carried rather than written back over by the run's own write.
    for field in _moved(durable.data, resolved_over, {*resolved_over, *durable.data}):
        written = durable.data.get(field, _ABSENT)
        if written is _ABSENT:
            state.data.pop(field, None)
        else:
            state.set(field, written)
    log.warning(
        "issue=#%d its developer report records moved on the pinned comment "
        "while the reviewer ran; keeping them and not acting on the verdict",
        issue.number,
    )
    return False


def _in_hand(
    gh: GitHubClient, issue: Issue, state: PinnedState, purpose: str,
) -> PinnedState | None:
    """The comment read afresh where it carries the report records `state` does."""
    durable = _read(gh, issue, state, purpose)
    if durable is None or not _moved(durable.data, state.data, _REPORT_RECORDS):
        return durable
    log.warning(
        "issue=#%d its pinned comment does not carry the developer report "
        "records this tick holds, so it will not %s; writing nothing this "
        "tick", issue.number, purpose,
    )
    return None


def _read(
    gh: GitHubClient, issue: Issue, state: PinnedState, purpose: str,
) -> PinnedState | None:
    """The comment `state` was read from, read afresh and parsed, or None logged.

    None as well where the fresh reading is another comment -- the pinned
    comment replaced, or gone -- since every write the tick makes goes to the
    comment `state` names: made over one that is no longer pinned, it would
    pin a second comment beside the one every later reader takes.
    """
    try:
        durable = gh.read_pinned_state(issue)
    except Exception:
        log.exception(
            "issue=#%d could not read its pinned comment to %s; ending the "
            "tick with nothing written", issue.number, purpose,
        )
        return None
    if not durable.parsed:
        log.error(
            "issue=#%d its pinned comment will not parse where it is read to "
            "%s; ending the tick with nothing written", issue.number, purpose,
        )
        return None
    if durable.comment_id != state.comment_id:
        log.warning(
            "issue=#%d its pinned comment is %s where this tick read %s, so it "
            "will not %s; ending the tick with nothing written",
            issue.number, durable.comment_id, state.comment_id, purpose,
        )
        return None
    return durable


def _moved(durable: dict, in_hand: dict, fields: Iterable[str]) -> list[str]:
    """The fields two readings of the comment spell differently.

    Compared as the comment's JSON spells them rather than as Python values,
    which call a field written `null` equal to one missing and a revision `1`
    equal to `true`: each of those is a different record to its reader, so a
    concurrent write of either is a move, not agreement.
    """
    return [
        field for field in fields
        if (field in durable, json.dumps(durable.get(field), sort_keys=True))
        != (field in in_hand, json.dumps(in_hand.get(field), sort_keys=True))
    ]
