# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The admission a recovery reads again immediately before a captured report is handed on or withdrawn.

A recovery owner finishes an admitted capture through its stage's existing
disposition, and that disposition takes readings of its own before the report
is handed to the delivery or withdrawn beside a park: a pull request
fetched, a watermark carry over both comment surfaces, a remote fetch proving
the tip a publication replaces -- and then the write's own reads of the
comment: the transfer's or invalidation's, the guarded commit's, and last the
strict editor's walk to the comment it rewrites. Each is a request a human can
land a move behind -- a control applied, a relabel, a close, an edit, a push
-- and the capture may be handed on or retired only over readings that still
admit it. So the owner runs its disposition inside `rereads(admitted)`, which
hands the GitHub client the question its strict editor asks of every edit,
behind that walk and immediately before the edit goes out
(`github/edit_questions`): an edit moving the pending capture `admitted`
finishes -- its transfer, or its invalidation -- has every reading a
handoff's effect stands on taken again (`completion_effect.admitted_again`),
and anything but APPLICABLE holds the edit with nothing sent, refused to the
commit as MOVED_BEHIND, the caller's state withheld and the tick held for the
next dispatch to decide afresh. Every other edit goes through.

A recovery whose disposition writes more than the capture -- a late
revision's park, landing the guidance its run consumed before the capture is
withdrawn behind it, and the owner read behind its handoff or withdrawal --
asks for `every_edit`: then every strict edit made inside the block is held to
the same readings, not only the one moving the capture and not only while it
stands pending. A direct whole-state write is never
asked, and walks to the comment on its own, so that disposition lands such a
write through a guarded commit instead, whose strict edit asks behind its own
walk (`decomposition/late_revision_landing.lands_the_park`). A recovery whose
stage holds a reading the admission does not carry -- a late revision's close
latch, which a poll can set while the disposition reads, and any close its own
fetches read, which the admission's hold alone would forget -- hands it in `also`,
asked last behind that same walk, behind every request the question makes,
so a close latched at any point before the edit holds it alike.

Outside a recovery nothing is asked: a live tick honors the hold its run's
return read, whatever a later fetch sees.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from functools import partial

from orchestrator.github import edit_questions as _questions
from orchestrator.workflow.engine import (
    completion_admission as _admission,
    completion_effect as _effect,
    completion_records as _records,
    completion_recovery_models as _recovery_models,
    completion_spelling as _spelling,
)

log = logging.getLogger("orchestrator.workflow")

# What a move behind the question's own readings holds the edit as.
_MOVED_BEHIND = _recovery_models.Decision(_recovery_models.Standing.UNCERTAIN, _recovery_models.Reason.MOVED_BEHIND)


@contextmanager
def rereads(
    admitted: _recovery_models.AdmittedCompletion,
    *,
    every_edit: bool = False,
    also: Callable[[], bool] | None = None,
) -> Iterator[None]:
    """Have `admitted` read again immediately before its capture is handed on or withdrawn inside the block.

    `every_edit` holds every strict edit made while that capture is still
    pending to the same readings, not only the one moving it. `also` is the
    stage's own reading, asked last, whose False holds the edit as well.
    """
    with _questions.asked_before_the_edit(partial(_stands, admitted, (every_edit, also))):
        yield


def _stands(
    admitted: _recovery_models.AdmittedCompletion,
    asked: tuple[bool, Callable[[], bool] | None],
    read: _questions.Spelling,
    candidate: _questions.Spelling,
) -> bool:
    """Whether an edit leaving `candidate` over `read` may go out, read again where it moves `admitted`'s capture.

    True for an edit that leaves that pending capture as `read` carries it,
    or over a comment that no longer carries it pending -- unless `asked`'s
    `every_edit` asks of every edit inside the block, the ones behind its
    handoff or withdrawal included -- and where nothing holds it behind every
    request the question makes (`_held_behind`).
    """
    every_edit, also = asked
    captured = read.get(_records.DEVELOPER_COMPLETION)
    pending = _spelling.read_record(captured) == admitted.capture
    if not every_edit and (captured == candidate.get(_records.DEVELOPER_COMPLETION) or not pending):
        return True
    held = _held_behind(admitted, pending, read, also)
    if held is None:
        return True
    log.warning(
        "issue=#%d moved behind the readings its captured completion's recovery took (%s: %s); writing "
        "nothing more, for a later dispatch to decide",
        admitted.issue.number, held.standing, held.reason,
    )
    return False


def _held_behind(
    admitted: _recovery_models.AdmittedCompletion,
    pending: bool,
    read: _questions.Spelling,
    also: Callable[[], bool] | None,
) -> _recovery_models.Decision | None:
    """Why the edit is held, each reading taken behind the requests of the one before it; None where nothing holds it.

    Each reading the question takes is a request a move can land behind, so
    no reading's answer is the last word on what landed while a later one
    was out. The admission is read first (`_read_again`); then the comment
    once more (`_comment_stands`), so one another writer moved while the
    admission's requests were out holds the edit rather than being written
    over by a candidate derived from the reading before it; then the
    admission again, so a control applied, a relabel, or a close made while
    the comment was read holds it too; and last the stage's own reading,
    `also`, which makes no request at all -- a close a poll latched at any
    point up to here.
    """
    again = _read_again(admitted, pending)
    if again.standing is not _recovery_models.Standing.APPLICABLE:
        return again
    if not _comment_stands(admitted, read):
        return _MOVED_BEHIND
    again = _read_again(admitted, pending)
    if again.standing is not _recovery_models.Standing.APPLICABLE:
        return again
    if also is not None and not also():
        return _MOVED_BEHIND
    return None


def _read_again(admitted: _recovery_models.AdmittedCompletion, pending: bool) -> _recovery_models.Decision:
    """The admission read again for an edit: whole while the capture is pending, its issue's controls behind it.

    While the capture stands pending every reading its handoff's effect stands
    on is taken again (`completion_effect.admitted_again`). Once it is handed
    on or withdrawn there is no handoff left to read, and the records
    `admitted` was read off are the tick's own, moved by that very write; what
    still stands between the recovery and its next write is the issue held
    by a control or moved off its label, asked of a fresh fetch
    (`completion_admission.live_issue`).
    """
    if pending:
        return _effect.admitted_again(admitted)
    fresh = _admission.live_issue(admitted.gh, admitted.issue, admitted.label)
    if isinstance(fresh, _recovery_models.Decision):
        return fresh
    return _recovery_models.Decision(_recovery_models.Standing.APPLICABLE)


def _comment_stands(admitted: _recovery_models.AdmittedCompletion, read: _questions.Spelling) -> bool:
    """Whether the pinned comment, read once more, still reads as the editor's walk read it; False where unread."""
    try:
        fresh = admitted.gh.read_pinned_state(admitted.issue)
    except Exception:  # noqa: BLE001 - a comment nobody could read again holds the edit, never lets it through
        return False
    return fresh.reads_as(dict(read))
