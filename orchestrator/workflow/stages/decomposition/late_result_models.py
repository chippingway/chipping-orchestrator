# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Late-run identities, adjudication answers, and their guarded settlement values.

Recorded answers retain their exact source commit, cycle, and generation.
A split carries its children, a question needs its category and text, and a
legacy single answer retains the explanation fallback used by park notices.
A single or a split also keeps the agent's rationale, cut to a fixed bound
with a visible marker where it was cut.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from orchestrator.workflow.late_split.events import LateVerdictCategory
from orchestrator.workflow.late_split.models import LateGeneration, LateVerdict

# The role a late adjudication is recorded under. It is the decomposer's --
# the question being answered is a decomposition question -- and it is stored
# beside the run rather than assumed, because the same coordinator owns the
# developer revision a trusted answer earns, which records its own role.
_DECOMPOSER_ROLE = "decomposer"

# What a `single` with no explanation beside it answers with. A fresh reply
# that omits one is refused where it is read, so the absence a reader meets is
# always a RECORD's: live issues carry results written before this domain kept
# an explanation, and those still decide this candidate. So it has a sentence
# of its own rather than an empty string a reader would render as nothing.
# Re-running the adjudicator to recover the prose is the one thing it must not
# cost: a second run is not free and is free to decide differently.
UNRECORDED_SPLIT_BLOCKER = (
    "no explanation of what stopped a split was recorded with this verdict"
)

# The verdicts a record keeps a rationale for. A `question` asks rather than
# argues, and a split refused at the lineage bound is recorded as the question
# it became -- so the argument for a split nobody may act on is not kept.
_RATIONALE_VERDICTS = frozenset((LateVerdict.SINGLE, LateVerdict.SPLIT))

# How much of a rationale a record keeps, in characters of the value. It is
# prose a human reads and nothing acts on, so a longer one is cut to this
# rather than refused: a refusal would take the verdict it argued for into a
# park the next attempt supersedes, and buy another agent run to recover an
# argument. The fields a verdict IS acted on through are never cut.
#
# Fixed rather than derived from the room a comment has left, so one reply
# records the same text whatever else the comment holds. What JSON escaping
# makes of those characters is not bounded here; the whole-comment preflight
# measures the rendered write, and a record it cannot hold is refused whole.
MAX_RATIONALE = 2048

# What ends a rationale that was cut. It sits INSIDE the bound, so no recorded
# rationale is longer than `MAX_RATIONALE`, and it says so in words, so a
# reader shown the value can tell a shortened argument from a whole one.
RATIONALE_TRUNCATION_MARKER = " [... rationale truncated by the orchestrator]"


class _LateDisposition(Enum):
    """What one late-adjudication call did with the tick it was given."""

    NOT_LATE = "not_late"
    PARKED = "parked"
    DEFERRED = "deferred"
    DECIDED = "decided"
    REVISED = "revised"
    SETTLED = "settled"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class _LateAdjudication:
    """What one late reply decided, once its fenced block was believed.

    A verdict is always present -- a reply that could not produce one is a
    parse error and never becomes one of these -- and the rest is what that
    verdict is allowed to carry. `children` is the manifest a `split`
    proposes, held in memory for the tick that acts on it, each slice of it
    carrying the addition budget it was proposed at: the issue created from
    that slice states the size, so the number travels with the manifest.

    `split_blocker` is the `single` verdict's own: what the agent said made
    splitting unsafe or unavailable, verbatim. It is what a reader shows
    somebody deciding what to do about an oversized candidate, and it is kept
    apart from `rationale` -- the prose arguing for the verdict -- because
    they answer different questions and are held to different rules. The
    explanation is required of a fresh `single` and recorded whole or not at
    all; the rationale is optional, is recorded only beside a `single` or a
    `split`, and is cut to `MAX_RATIONALE` on its way into the record.

    A fresh answer carries the rationale as the agent wrote it, and one
    rebuilt from the record carries the bounded text the record kept -- so a
    caller that has to show the same words on both roads reads them off the
    record.
    """

    verdict: LateVerdict
    category: LateVerdictCategory | None = None
    rationale: str = ""
    question: str = ""
    split_blocker: str = ""
    children: tuple[dict, ...] = ()

    @property
    def split_blocker_explanation(self) -> str:
        """What this verdict says stopped a split, or that nothing says.

        Asked instead of the field, so every reader of a `single` gets a
        sentence: an outcome recorded before this domain kept one answers
        with the stand-in rather than with nothing, which is the only way the
        field is ever empty on this verdict, since a reply that declared it
        without an explanation never became one of these. Empty on the other
        two verdicts, which are not answers about a split that did not
        happen.
        """
        if self.verdict != LateVerdict.SINGLE:
            return ""
        return self.split_blocker or UNRECORDED_SPLIT_BLOCKER

    @property
    def child_count(self) -> int | None:
        """How many children a split proposed, and nothing for the others.

        The verdict event's contract, answered where the manifest is: a child
        count belongs to a `split` and to no other verdict, in both
        directions.
        """
        if self.verdict != LateVerdict.SPLIT:
            return None
        return len(self.children)


@dataclass(frozen=True)
class _LateRun:
    """The late run one issue is locked to, as pinned state records it.

    The spec is the whole configured command rather than the backend alone,
    for the reason every other role's pin is: a resume has to land on the CLI
    that issued the session id, and configured args are part of what a later
    run must reproduce.

    The result is the whole of what the verdict decided, not a marker for it.
    A `single` carries the explanation of what stopped a split, because that
    is the one thing a human deciding about an oversized candidate cannot get
    from anywhere else once the run is over; a `question` carries the category
    it was asked under and the sentence it asked, because announcing it is the
    outcome's own external effect and a crash between recording and posting
    has to be able to finish it; a `split` carries the child manifest and the
    budget each slice of it was proposed at, because that manifest IS what the
    split decided and the issues it becomes state those sizes -- a record
    without them would refuse the re-run while the answer it stands for was
    gone.

    A `single` or a `split` also carries the rationale it argued with, as the
    record bounded it. That decides nothing: a record written before this
    domain kept one, or holding a value no reader can use, is still this
    candidate's answer, so the field reads empty rather than the verdict
    reading incomplete. It is written and dropped with the result, which is
    what binds it to the same cycle, generation, and commit.
    """

    role: str = _DECOMPOSER_ROLE
    spec: str = ""
    backend: str = ""
    extra_args: tuple[str, ...] = ()
    session_id: str | None = None
    cycle_id: int = 0
    source_sha: str = ""
    generation: int = 0
    verdict: LateVerdict | None = None
    category: LateVerdictCategory | None = None
    question: str = ""
    split_blocker: str = ""
    children: tuple[dict, ...] = ()
    rationale: str = ""

    @property
    def is_actionable(self) -> bool:
        """Whether the recorded outcome is one a caller could act on.

        Asked per verdict, because what "complete" means differs by verdict
        and a half-written one is worse than none: a `question` with no
        sentence and no category suppresses the next spawn and then announces
        nothing, and a `split` with no children suppresses it and then names
        no children to create. Either would leave the issue decided, silent,
        and going nowhere -- so an incomplete record is not an answer, and the
        adjudicator runs again.

        A `single` is complete on its verdict alone, and the explanation
        beside it does not change that: it is what a reader shows rather than
        what a caller acts on, so a result recorded before this domain kept
        one is still this candidate's answer. Reading it as incomplete would
        buy a second agent run to recover prose.
        """
        if self.verdict == LateVerdict.SINGLE:
            return True
        if self.verdict == LateVerdict.QUESTION:
            return bool(self.question) and self.category is not None
        if self.verdict == LateVerdict.SPLIT:
            return bool(self.children)
        return False

    def ran_against(self, generation: LateGeneration) -> bool:
        """Whether this record's run was the one spawned for THIS candidate.

        All three parts of the identity are required, because any of them
        alone would let a stale record through. The generation counter is not
        unique on its own: a restart mints a fresh CYCLE and puts the counter
        back to where it started, so generation 1 of cycle 4 is a different
        attempt from generation 1 of cycle 3 -- and these run fields survive a
        late-generation clear, which is exactly the window a repeated counter
        would be read in. The commit is required beside them because a
        candidate replaced within one generation is a different question.

        Asked of two things, which is why it is separate from the verdict. A
        recorded ANSWER is this candidate's only when the run that produced it
        was; and a pinned SESSION may be resumed only when the conversation it
        holds is about this candidate, since resuming one opened against a
        commit that has since been replaced would hand the agent a transcript
        describing work nobody is adjudicating.
        """
        if not self.source_sha:
            return False
        return (
            self.cycle_id == generation.cycle_id
            and self.generation == generation.generation
            and self.source_sha == generation.candidate_sha
        )

    def answers(self, generation: LateGeneration) -> bool:
        """Whether a recorded result already decides THIS candidate.

        A record that is not actionable is unanswered whatever identity it
        carries: re-adjudicating costs one more agent run, while acting on a
        verdict whose substance nothing kept would cost whatever that verdict
        was about.
        """
        return self.is_actionable and self.ran_against(generation)


@dataclass(frozen=True)
class _GuardedSplit:
    """A split outcome that has passed the post-agent owner guard.

    The handoff to the transaction that creates the children, and the only
    shape that transaction accepts one in: a split reaches it having been
    decided AND having been re-checked against an owner read taken after the
    agent finished, so nothing can create children under an issue somebody
    closed while the adjudication ran.

    Both fields are carried rather than re-read. The generation is the record
    as the guard left it -- the phase it reached included -- and the children
    are the manifest the verdict decided on, so the transaction acts on the
    exact answer that was guarded rather than on whatever the pinned comment
    says by the time it looks.
    """

    generation: LateGeneration
    children: tuple[dict, ...]


@dataclass(frozen=True)
class _LateAdjudicationRun:
    """What one call to the late coordinator did, and what it decided.

    `run` is the record pinned state holds once this call is over, read back
    rather than assembled, so a caller reading a session id off it is reading
    the one a later resume would land on rather than the one the tick opened
    with.

    `adjudication` is present on every `DECIDED` answer, whether this tick's
    own agent produced it or a crashed one already had: a recovered outcome is
    rebuilt from the record, which carries the whole of what each verdict
    decided and the bounded rationale beside a `single` or a `split`.

    `guarded_split` is set on exactly one path: a `split` verdict that a fresh
    owner read found open. It is absent everywhere else, so a caller cannot
    reach the child-creating transaction from an outcome the guard never
    cleared.
    """

    disposition: _LateDisposition
    generation: LateGeneration
    run: _LateRun
    adjudication: _LateAdjudication | None = None
    guarded_split: _GuardedSplit | None = None
