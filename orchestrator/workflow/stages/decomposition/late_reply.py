# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One fenced block at the end of a LATE reply, or a reason it is not one.

An additive mode beside the initial parser, on its own fence and with its own
decision vocabulary, so that what a missing or malformed initial manifest
means is exactly what it always meant. The two fences cannot be mistaken for
each other -- `orchestrator-manifest` is not a substring of
`orchestrator-late-manifest` and the patterns are anchored on the whole name
-- so an initial reply cannot be read as a late one or the other way round.

The envelope is the same and is asked once, on the owner beside this one: one
block, and nothing after it. What differs is what a reply with NO block means.
The initial contract treats it as the decomposer asking a question, because
there its question has nowhere else to go; the late contract gives a question
its own structured decision, complete with the category telemetry counts, so a
reply with no block is a protocol failure and is parked for a human rather
than read as an answer.

`split` is validated by the initial mode's own split validator rather than by
a second copy of it. The child cap, the shape of a child, and the acyclicity
of the graph they declare are properties of a manifest that is about to become
GitHub issues, and that is the same manifest either mode produces -- so a rule
tightened there tightens here, and the number the late prompt states is still
the number the reply is judged against.

`single` carries one field the other two do not: the explanation of what
stopped a split. The verdict says the committed work is one change AND that no
safe split of it is available, and it decides nothing on its own -- it hands an
oversized candidate to a human -- so that reason is the whole of what the human
is given to decide on. It is read off the reply as text rather than left in the
prose around the block, which nothing keeps, and a fresh reply that declares
the outcome without it is refused rather than recorded: what would be kept
otherwise is a verdict missing the one thing it exists to carry, and the park a
refusal takes names the field that was owed.

What that refusal is NOT is a rule about records. A result recorded before this
domain kept an explanation is on live issues, and it reads back as this
candidate's answer with a stand-in beside it -- re-adjudicating to recover
prose would buy a second run free to decide something else entirely. The
obligation is the fresh reply's alone, exactly as the per-child budget below
is.

Every child of a `split` owes one field the initial mode never asks for: the
lines that child is estimated to ADD across all of its paths. It is required
and it is bounded -- a real count of at least one line, strictly below the
ceiling this candidate was measured against -- because a split whose children
are each still oversized is not a split, and the cheapest place to catch one
that says so is while it is still a reply rather than after it has become
issues. What is judged here is whether the proposal is ACTIONABLE, and never
whether a later measurement may disagree with it: what decides that a child is
oversized is the cumulative measurement of that child's own diff. The number
itself travels past this owner -- the record keeps it and the child issue
states it -- so the slice a developer is handed says what it was sized at.

The ceiling comes from the generation the reply is about rather than from
configuration, so an answer is judged against the number its own prompt
stated even where an operator retuned the knob while the agent was running. A
generation that cannot say what its ceiling was refuses nothing on size, and
still refuses a child that declared no estimate at all: a missing budget is a
protocol failure whatever the bound is, while a bound nobody can name is not
one a reply can be measured against.

That rule sits on THIS owner rather than on the shared split validator, for
the reason the explanation above is asked only of a reply: it is a rule about
what an agent just said. The same validator reads recorded manifests back off
the pinned comment, and a live issue's recorded split was written before any
budget was asked for -- so a requirement placed there would read every one of
them as no manifest at all and send a candidate that has already been
adjudicated round again.

What this owner does NOT decide is whether a `split` is allowed at all. The
lineage bound is the record's invariant and is enforced where the generation
is: a structurally perfect split proposed at the bound parses cleanly here and
is refused one layer up, which is what keeps "the agent got the format wrong"
apart from "the agent proposed something the lineage forbids".
"""
from __future__ import annotations

import re
from typing import Any

from orchestrator.workflow.late_split import events as _events
from orchestrator.workflow.late_split.events import LateVerdictCategory
from orchestrator.workflow.late_split.models import LateVerdict
from orchestrator.workflow.stages.decomposition import (
    late_budget as _budget,
    manifest as _manifest,
    validation as _validation,
)
from orchestrator.workflow.stages.decomposition.late_result_models import _LateAdjudication

_LATE_BLOCK = "orchestrator-late-manifest"

_LATE_MANIFEST_RE = re.compile(
    r"```orchestrator-late-manifest\s*\n(.*?)\n```",
    re.DOTALL,
)

_DECISION = "decision"
_CATEGORY = "category"
_QUESTION = "question"
_SPLIT_BLOCKER = "split_blocker"

_SINGLE_DECISION = "single"
_SPLIT_DECISION = "split"

_DECISIONS = (_SINGLE_DECISION, _SPLIT_DECISION, _QUESTION)

_NO_BLOCK = (
    f"expected one {_LATE_BLOCK} block; the late contract has no outcome "
    "that is prose"
)

_BAD_DECISION = "decision must be 'single', 'split', or 'question'"

_NO_QUESTION = "question decision requires a non-empty question"

_NO_SPLIT_BLOCKER = (
    f"single decision requires a non-empty {_SPLIT_BLOCKER} saying why no "
    "safe split of this work is available"
)


def _parse_late_reply(
    last_message: str, threshold: int | None,
) -> tuple[_LateAdjudication | None, str | None]:
    """Parse a fenced `orchestrator-late-manifest` block.

    Returns `(adjudication, None)` for a reply that decided something, and
    `(None, error)` -- a short human-readable reason, used in the park
    message -- for every reply that did not. There is deliberately no third
    answer: unlike the initial mode, a late reply with no block has not asked
    a question, it has failed to answer one.

    The threshold is the ceiling THIS candidate was measured against, and it
    is passed rather than read, so what a proposed child is judged against is
    the number its own prompt stated.
    """
    payload, envelope_error = _manifest._fenced_payload(
        last_message, _LATE_MANIFEST_RE, _LATE_BLOCK,
    )
    if payload is None:
        return None, envelope_error or _NO_BLOCK
    late_manifest, decode_error = _manifest._decode_manifest(payload)
    if late_manifest is None:
        return None, decode_error
    return _adjudication(late_manifest, threshold)


def _adjudication(
    late_manifest: dict, threshold: int | None,
) -> tuple[_LateAdjudication | None, str | None]:
    """Route one decoded late manifest onto the verdict it declares."""
    decision = late_manifest.get(_DECISION)
    if decision not in _DECISIONS:
        return None, _BAD_DECISION
    if decision == _SPLIT_DECISION:
        return _split_adjudication(late_manifest, threshold)
    if decision == _QUESTION:
        return _question_adjudication(late_manifest)
    return _single_adjudication(late_manifest)


def _single_adjudication(
    late_manifest: dict,
) -> tuple[_LateAdjudication | None, str | None]:
    """Require a `single` to say why no safe split of the work is available.

    Asked of the reply for the same reason the question's own sentence is:
    this verdict publishes nothing and hands the candidate to a human, so an
    answer that names no obstacle has decided the one thing it is not allowed
    to decide alone and given the human nothing to decide it on. A reply
    refused here parks naming the field, which is a cheaper thing to read than
    a recorded verdict nobody can act on.
    """
    blocked = _text(late_manifest, _SPLIT_BLOCKER)
    if not blocked:
        return None, _NO_SPLIT_BLOCKER
    return _LateAdjudication(
        verdict=LateVerdict.SINGLE,
        category=_category(late_manifest, required=False),
        rationale=_text(late_manifest, "rationale"),
        split_blocker=blocked,
    ), None


def _split_adjudication(
    late_manifest: dict, threshold: int | None,
) -> tuple[_LateAdjudication | None, str | None]:
    """Validate a late split against the split rules and the budget.

    The shared rules first, because they are what says these are children at
    all: a budget read off something that is not a child object would be
    reporting the wrong fault about the wrong thing.
    """
    split_error = _validation._split_manifest_error(late_manifest)
    if split_error is not None:
        return None, split_error
    children = tuple(late_manifest.get("children") or ())
    budget_error = _budget._estimates_error(children, threshold)
    if budget_error is not None:
        return None, budget_error
    return _LateAdjudication(
        verdict=LateVerdict.SPLIT,
        category=_category(late_manifest, required=False),
        rationale=_text(late_manifest, "rationale"),
        children=children,
    ), None


def _question_adjudication(
    late_manifest: dict,
) -> tuple[_LateAdjudication | None, str | None]:
    """Require a question to say what it is asking before it may park one."""
    asked = _text(late_manifest, _QUESTION)
    if not asked:
        return None, _NO_QUESTION
    return _LateAdjudication(
        verdict=LateVerdict.QUESTION,
        category=_category(late_manifest, required=True),
        question=asked,
    ), None


def _category(
    late_manifest: dict, *, required: bool,
) -> LateVerdictCategory | None:
    """Map a declared category onto the closed vocabulary, or leave it out.

    Mapped rather than trusted, so an agent's own spelling records as
    `unknown` and never widens the field. Absent is a real answer on the two
    verdicts that do not require one, which is what keeps `unknown` meaning
    "a category this binary does not know" rather than "no category given".
    """
    asked = late_manifest.get(_CATEGORY)
    if asked is None and not required:
        return None
    return _events.verdict_category(asked)


def _text(late_manifest: dict, field_name: str) -> str:
    """Return one stripped optional text field, or an empty string."""
    written: Any = late_manifest.get(field_name)
    return written.strip() if isinstance(written, str) else ""
