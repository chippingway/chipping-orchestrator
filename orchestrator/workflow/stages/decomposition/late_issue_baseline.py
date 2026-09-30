# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a generation's first late baseline meets the issue-wide one.

The first reading a generation takes is its baseline: what the frozen
candidate is compared against from then on. Taken over the whole thread, it
would fold in whatever the thread carried at that moment -- including a
comment written while the developer's last run was out, or an edit made after
the issue-wide `user_content_hash` was last settled. Nothing has read those.
Folded into the late fingerprints they would never come back as guidance, and
the first consumption after them would record `user_content_hash` over them
too, so the next stage's drift check would not see them either.

So the first baseline is taken over the part of the reading the issue-wide
baseline already covers, and no further: the longest prefix of the comment
batch that, beside the title and body as they read now, reproduces the
recorded hash. Comments are append-only and their ids ascend, so the part a
settled baseline covered is a prefix of every later read; what lies past it is
exactly what no stage has consumed, and it stays uncounted -- a fresh reply
above the shared watermark, or withheld guidance below a park's notice -- so
the late path hands it to the developer rather than absorbing it.

When no prefix reproduces the recorded hash, the change is one a prefix cannot
explain: the title or the body moved, or a comment already covered was edited
or deleted. That is the requirements moving under the candidate, and the
caller parks on it as drift. What it baselines on then is `_unreconciled`:
no comment counted, since which of them the recorded hash covered can no
longer be told, and the title and body held to that recorded hash itself --
the only record there is of what the developer worked against, and one no
fingerprint of the title and body as they now read can equal. So the reading
goes on reading as drift until a human answers the park or the edit is taken
back, and every trusted comment is uncounted meanwhile: whatever answers it
hands them to the developer whole, a comment written under the drift park's
own notice included, rather than folding them into a baseline. A baseline
written by the legacy algorithm, which counted a bare continue, is recognized
the way the drift check recognizes one.

The revert is the one answer that fingerprint cannot see for itself. Where
the recorded hash covered a comment, no title and body alone reproduce it, so
the drift that reading reports is asked again here (`_reconciled`): a thread
that once more has a prefix reproducing the recorded hash is one whose edit
was taken back, and the generation is baselined on that prefix exactly as a
first reading without the edit would have been. The park's own answer then
reads it as the revert it is.

An issue with no recorded hash has recorded nothing as read, so its first
late baseline counts no comment at all: the title and body as they read now,
and an empty conversation. Every trusted comment the thread carries is then
uncounted -- a fresh reply, or withheld guidance below a park's notice -- and
reaches an agent whole before anything records it read. Taking the whole
reading instead would fold in whatever the thread said, a comment written
under a park's notice and the words beside the continue that lifted it
included, and the first consumption would record the hash over them.

Nothing here records the issue-wide baseline itself: only a reading a late
path consumed may move it, and a first baseline consumes nothing. What an
issue with none needs instead is `_observed`, below.

A generation baselined before its first reading was held to the issue-wide
baseline was baselined over the whole thread, and it may count comments no
stage has consumed -- ones the recorded hash leaves out, or any comment at
all where no hash is recorded. It does not carry `baseline_bounded`, which
every baseline taken here and every consumption since sets, and `_retaken`
gives up what it counts before anything is compared against it, drifted or
not -- a drifted reading being exactly the one where what the recorded hash
covered can no longer be told. Those comments are then handed to an agent
whole, by the reading itself or by whatever answers the drift park it takes.
Left counted, they would never come back as guidance: a split's umbrella
would meet them as an edit on its first poll and orphan the children it was
just handed, a certificate answering a drift park would record them read,
or, with nothing recorded, the umbrella would take them as its own baseline
and hand them to nobody.

`_observed` is what keeps that umbrella's poll honest where no hash is
recorded and no reply was consumed. The reading an adjudication carries on
over is recorded as `observed_user_content_hash` -- a snapshot beside the
issue-wide baseline rather than a move of it -- and the drift check compares
against it while no baseline is recorded, so a comment written while the
adjudicator ran, or an edit made then, is the drift it is rather than the
baseline that poll takes.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments, content_hash as _content_hash, drift as _engine_drift
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import late_content as _late_content
from orchestrator.workflow.stages.decomposition.late_content_models import _LateContentSignal

_USER_CONTENT_HASH = "user_content_hash"


def _covered(
    state: PinnedState, generation: LateGeneration, signal: _LateContentSignal,
) -> LateGeneration | None:
    """This generation baselined on what the issue-wide baseline covers, or None.

    Searched from the whole reading down, so the prefix taken is the longest
    one that reproduces the recorded hash: comments the global filter drops
    change no hash, and a baseline that stopped short of them would leave the
    orchestrator's own notices uncounted for no reason.
    """
    recorded = state.get(_USER_CONTENT_HASH)
    ours = _comments._orchestrator_ids(state)
    if not isinstance(recorded, str):
        return _baselined_on(state, generation, signal, ())
    for end in range(len(signal.read), -1, -1):
        prefix = signal.read[:end]
        if recorded in _prefix_hashes(signal.text, prefix, ours):
            return _baselined_on(state, generation, signal, prefix)
    return None


def _unreconciled(
    state: PinnedState, generation: LateGeneration, signal: _LateContentSignal,
) -> LateGeneration:
    """This generation baselined where no prefix reproduces the issue-wide baseline.

    No comment is counted, and the title and body are held to the recorded
    hash itself, which is what keeps every later reading drifted until a
    human's answer rebaselines it or `_reconciled` finds the edit taken back.
    Where that hash covered no comment at all it IS the fingerprint of the
    title and body it was taken over, so a revert needs no second look.
    """
    return replace(
        _baselined_on(state, generation, signal, ()),
        title_body_hash=state.get(_USER_CONTENT_HASH),
    )


def _reconciled(
    state: PinnedState, generation: LateGeneration, signal: _LateContentSignal,
) -> LateGeneration | None:
    """This drifted generation baselined afresh, where the edit it parked on was taken back.

    Asked only of a generation `_unreconciled` took -- one that counts no
    comment and holds its title and body to the recorded hash itself -- since
    only its drift can hide a revert. Every other generation's fingerprint is
    its own, and the reading it calls drifted is None here and parks as it
    would have. So is a reading of this one that still carries the edit: no
    prefix of it reproduces the recorded hash.
    """
    if (
        generation.comment_watermark_id is not None
        or generation.title_body_hash != state.get(_USER_CONTENT_HASH)
    ):
        return None
    return _covered(state, generation, signal)


def _retaken(
    state: PinnedState, generation: LateGeneration, signal: _LateContentSignal,
) -> LateGeneration | None:
    """What a baseline taken before it was bounded is taken again as, or None.

    None for a generation with no baseline yet, which is taking its first,
    and for one whose baseline is bounded (`baseline_bounded`), which counts
    no more than the issue-wide baseline covers by construction.

    Any other was baselined over the whole thread, and whether it counts a
    comment no stage consumed cannot be told once the title or body moved:
    the recorded hash was taken over a title and body that are gone. So what
    it counts is given up, drifted or not. With a hash recorded, the whole
    fingerprint goes and the baseline is taken again the way a first one is
    -- over the covered prefix, or as a drift park that counts no comment.
    With none, its title and body are all there is to hold the candidate's
    requirements to, so they are kept and only the comments go: an edit is
    still the drift it is, and every trusted comment is handed on whole by
    whatever answers it.
    """
    if not signal.baselined or generation.baseline_bounded:
        return None
    if isinstance(state.get(_USER_CONTENT_HASH), str):
        return replace(
            generation, title_body_hash=None, comment_hash=None, comment_watermark_id=None,
        )
    return replace(
        generation,
        comment_hash=_late_content._thread_digest([]),
        comment_watermark_id=None,
        baseline_bounded=True,
    )


def _observed(state: PinnedState, signal: _LateContentSignal) -> None:
    """Record the reading an adjudication carries on over, where no baseline is.

    The requirements hash frozen on the reading, under the global filter the
    drift check applies -- written beside `user_content_hash` rather than into
    it, since carrying on consumes nothing. In memory only: the write that
    starts or settles the run keeps it. An issue with a recorded baseline has
    no use for it, because its drift check compares against that.
    """
    if not isinstance(state.get(_USER_CONTENT_HASH), str):
        state.set(_engine_drift._OBSERVED_USER_CONTENT_HASH, signal.requirements_hash)


def _baselined_on(
    state: PinnedState,
    generation: LateGeneration,
    signal: _LateContentSignal,
    prefix: tuple,
) -> LateGeneration:
    """This generation baselined on the reading's title and body and this prefix."""
    return _late_content._rebaselined(
        generation,
        _late_content._signal_of(
            signal.text, list(prefix), state, generation,
        ).fingerprint,
    )


def _prefix_hashes(
    text: tuple[str, str], prefix: tuple, ours: set[int],
) -> set[str]:
    """What the issue-wide baseline would read for this prefix, in either algorithm."""
    title, body = text
    return {
        _content_hash._hash_requirements(
            title, body, prefix, ours, include_bare_continue=legacy,
        )
        for legacy in (False, True)
    }
