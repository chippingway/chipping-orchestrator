# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The prompt one late adjudication is spawned with, and only that one.

Built beside its single caller rather than with the shared builders, the way
the drift-resume prompt is: nothing else asks this question. It opens on the
same header every conversation-carrying prompt does -- the issue body, the
trust-filtered thread, the tracked-repository block -- so an untrusted author's
comment is as absent here as it is from the implement and decompose prompts.

What it adds is everything the late question needs and the initial one never
had: that committed work ALREADY exists and is not to be rewritten, the
declared scope this generation owns, the two frozen commits the diff is to be
read between, the measurement that brought the candidate here, and where the
issue sits in its lineage.

The diff it names is the three-dot one, because that is the range the
measurement was taken over. Two dots would show everything that happened on
the base since the candidate branched as well, so on a diverged history the
agent would be adjudicating changes nobody measured -- and deciding a split
over work this candidate does not add.

Three numbers in it are read back off the owners that enforce them rather than
typed in, for the reason the child cap already is: a bound an agent is told and
a bound it is judged against must be one number. The child cap comes from the
split validator, the lineage bound from the record whose invariant it is, and
the category vocabulary from the closed set a verdict is recorded under -- so a
category widened in review reaches the prompt with it, and one an agent
invents still records as `unknown`.

The per-child addition budget is the fourth, and it is this generation's own
ceiling rather than the configured one: the reply is judged against the number
this candidate was measured against, so an operator retuning the knob while an
agent is running cannot leave that agent sizing children under a bound nothing
checks. A generation that cannot say what its ceiling was still asks for the
number, worded on the measurement above rather than on a figure nobody has.

The two field NAMES in it are read the same way and for the same reason: each
comes from the owner that reads it back. The explanation a `single` is asked
for is the reply parser's, since nothing else ever reads one; the budget every
proposed child owes is the shared budget owner's, since the reply, the record,
and the child issue created from a slice all read the same field. A prompt
asking for one key while the reply is read for another would leave every
conforming answer with nothing recorded about why a split was not proposed, and
every conforming split refused over a field nobody asked for.

What a `single` EARNS is named too, because the prompt must not tell an agent
it is deciding something it is not. That verdict publishes nothing: the ceiling
exists so unreviewed bulk does not reach a pull request, so an oversized change
is published unsplit only on a human's decision, and the verdict is what hands
the issue to them. An agent told the orchestrator would publish on its word is
one weighing a consequence the workflow does not give it. Which is also why the
explanation is asked for as an obligation rather than as a nicety: what the
human is handed is a decision, and a `single` with nothing in it about why a
safe split was unavailable hands them the decision without the one thing it
turns on. The parser refuses such a reply, so the obligation this prompt states
is the one the answer is judged by rather than advice beside it.

The way out of that decision is named beside it, because it is the one an
agent otherwise talks itself out of. Work that will not cut across features
almost always cuts along its dependencies: a prerequisite lands first and may
land DORMANT -- built, tested directly, reached by nothing in production -- with
its activation waiting for the last consumer that needs it, recovery paths
included. Unsaid, "none of this works until all of it exists" reads as proof
that no safe split exists, and the `single` that follows is one a human then
has to answer for. Each child is told to own its own tests and documentation
for the same reason: a slice whose proof or description belongs to a sibling
is not a slice, and a child carrying somebody else's tests is a change nobody
can review on its own.

The budget beside them is what keeps a split proposal actionable rather than
merely plausible. A child estimated at or above the ceiling this candidate was
measured against would arrive back here as another oversized candidate, so the
number is required, bounded, and refused where it does not clear -- and the
prompt asks for headroom under the bound rather than a number that only just
fits, because the review fixes that follow land on the same pull request. The
figure the JSON template shows is scaled to that same bound, for the reason
every other bound here is read off its owner: a template is copied verbatim, so
a standing figure would be a child this binary refuses on every repository
whose ceiling is configured below it -- the prompt would be handing out the one
shape that parks the candidate it is about. What it is not is a promise
anything later honours: the cumulative measurement of a
child's own diff is what decides whether that child is oversized, and the
prompt says so rather than leaving an agent to think a declared number buys it
anything.

The false positives are named out loud because the gate is a size gate and
size is not the question. A diff dominated by legitimate generated or data
artifacts is a small change with a large diff and gets a fast `single`; the
same artifacts looking like something nobody should have committed are a
question for a human, not a verdict for an agent. Saying both in the prompt is
what keeps the first from being split and the second from being waved through.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.workflow.engine import prompt_context as _prompt_context
from orchestrator.workflow.engine.prompt_context import _SECTION_SEP
from orchestrator.workflow.late_split.events import LateVerdictCategory
from orchestrator.workflow.late_split.models import MAX_LINEAGE_DEPTH, LateGeneration
from orchestrator.workflow.stages.decomposition import late_budget as _budget
from orchestrator.workflow.stages.decomposition.late_reply import _SPLIT_BLOCKER
from orchestrator.workflow.stages.decomposition.validation import _MAX_CHILDREN

_NO_BODY = "(no body)"

_NO_PRIOR_COMMENTS = "(no prior comments)"

_WHOLE_ISSUE = "(the whole issue)"

# The categories an adjudication may name, read off the closed vocabulary a
# verdict is recorded under. `UNKNOWN` is not offered: it is what this binary
# answers for a spelling it does not know, not one an agent may choose.
_CATEGORIES = ", ".join(
    f"`{member}`"
    for member in LateVerdictCategory
    if member != LateVerdictCategory.UNKNOWN
)

_MAY_SPLIT = (
    "- a child of this issue would be born at depth {depth}, which is still "
    "inside the bound, so `split` is available to you."
)

_NO_SPLIT = (
    "- this issue may NOT split further, so `split` is not available to you: "
    "an oversized change here resolves as `single` or asks a human with "
    '`"category": "lineage_bound"`. Do not propose children.'
)

_UNKNOWN_DEPTH = "unknown"

# How the per-child budget is worded on a generation whose ceiling cannot be
# read. The bound is the measurement's own, so an unreadable one is named by
# the block that carries it rather than by a figure this prompt invents.
_UNKNOWN_CEILING = "the ceiling this candidate was measured against"

# The budget the JSON template shows, where the ceiling leaves room for it.
# A template is copied verbatim, so the figure in it has to be one the reply
# contract would accept -- and modest enough that a wide ceiling does not
# anchor a child at a size nobody sized it at.
_EXAMPLE_ESTIMATE = 250

# What the shown figure keeps under a ceiling narrow enough to refuse the
# standing one: half of it, which is the headroom the paragraph below asks
# for said in a number. The floor is one line, since that is the smallest a
# child may claim -- a ceiling of exactly one leaves no claimable budget at
# all, and no template can invent one.
_EXAMPLE_SHARE = 2

_CHOOSE_ONE = "Decide EXACTLY ONE of three outcomes."

_QUESTION_RULE = (
    "`question` -- neither of the above is safe, and a human has to decide. "
    "If the diff is dominated by generated or data artifacts that look like "
    "they should NOT have been committed at all, this is the outcome: say "
    "what you found rather than deciding it yourself."
)


def _build_late_decompose_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    comments_text: str,
    generation: LateGeneration,
    specs: list[_config_models.RepoSpec],
) -> str:
    """Compose the late adjudication prompt for one frozen candidate."""
    body = issue.body or _NO_BODY
    convo = comments_text or _NO_PRIOR_COMMENTS
    tracked = _prompt_context._build_tracked_repos_context(spec, specs)
    tracked_block = f"{tracked}\n\n" if tracked else ""
    header = (
        f"You are the late decomposer for GitHub issue #{issue.number}: "
        f"{issue.title!r}.\n\n"
        f"Issue body:\n{body}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"{tracked_block}"
    )
    return _SECTION_SEP.join((
        header + _candidate_block(generation),
        _lineage_block(generation),
        _outcome_rules(generation.threshold),
    ))


def _candidate_block(generation: LateGeneration) -> str:
    """What already exists, what it measured, and how to read it."""
    scope = generation.scope or _WHOLE_ISSUE
    return (
        "A developer has ALREADY implemented this issue in the current "
        "working directory and COMMITTED the work. Nothing has been pushed "
        "and no pull request carries it. The orchestrator measured the "
        "prospective pull-request diff and it is larger than this repository "
        "lets one change be, so you are deciding what happens to work that "
        "already exists. You are NOT implementing anything and NOT reviewing "
        "it.\n\n"
        "Declared scope of this attempt:\n"
        f"{scope}\n\n"
        "The frozen candidate:\n"
        f"- candidate commit: {generation.candidate_sha}\n"
        f"- base commit: {generation.base_sha}\n"
        f"- measured additions: {generation.additions} lines, against a "
        f"ceiling of {generation.threshold}\n\n"
        "Read the exact diff with "
        f"`git diff {generation.base_sha}...{generation.candidate_sha}` in "
        "the current working directory -- `--stat` and `--numstat` for its "
        "shape, a path argument for one part of it. THREE dots, not two: "
        "that is the prospective pull-request range, the one the measurement "
        "above was taken over, and it shows what this candidate ADDS rather "
        "than everything that has happened on the base since. Those two "
        "commits are frozen: they are what every later step acts on, so "
        "decide from them and never from `HEAD`, the branch, or the working "
        "tree. You MUST NOT commit, push, fetch, or modify any file -- you "
        "are read-only."
    )


def _lineage_block(generation: LateGeneration) -> str:
    """Where this issue sits in its lineage, and what that permits."""
    depth = generation.lineage_depth
    shown = _UNKNOWN_DEPTH if depth is None else depth
    if generation.may_split:
        rule = _MAY_SPLIT.format(depth=depth + 1)
    else:
        rule = _NO_SPLIT
    return (
        "Lineage:\n"
        f"- root issue: #{generation.root_issue}\n"
        f"- this issue: #{generation.current_issue}\n"
        f"- lineage depth: {shown} of at most {MAX_LINEAGE_DEPTH}\n"
        f"{rule}"
    )


def _outcome_rules(threshold: int | None) -> str:
    """The three outcomes and the one fenced block that reports them."""
    return "\n\n".join((
        _CHOOSE_ONE,
        _single_rule(),
        _split_rule(),
        _QUESTION_RULE,
        _block_rules(threshold),
    ))


def _single_rule() -> str:
    """What a `single` claims, what it earns, and what it owes a human."""
    return (
        "`single` -- the committed work is one coherent change despite its "
        "size, and NO safe split of it is available. This does NOT publish "
        "it, and it is not the cheap way out of a hard diff: a `single` "
        "REQUIRES A HUMAN DECISION. The issue is handed to a human, who "
        "decides whether an oversized change may be published unsplit -- so "
        "this verdict MUST say what they are being handed. "
        f'`"{_SPLIT_BLOCKER}"` is where you explain why a SAFE SPLIT IS '
        "UNAVAILABLE: the prerequisite that cannot be landed dormant, the "
        "artifact that cannot land apart from what generates it, the "
        "invariant a half-landed slice would break. \"It is one coherent "
        "change\" restates the verdict rather than giving a reason for it. "
        "Size alone is not a reason to split. A diff dominated by legitimate "
        "generated or data artifacts -- a lockfile, a regenerated schema or "
        "client, a golden fixture, a vendored tree, a data or message "
        "catalog, a migration -- is a small change with a large diff, and "
        'the fast answer is `single` with `"category": '
        '"generated_artifacts"`.'
    )


def _split_rule() -> str:
    """What a `split` partitions, how it may be sliced, and what each owns."""
    return (
        "`split` -- the committed work covers several separable changes. "
        "Propose the child issues that partition the DECLARED SCOPE "
        "COMPLETELY: every part of that scope belongs to exactly one child, "
        "no child depends on work no child owns, and no child is itself big "
        "enough to need decomposing again. The children reuse this committed "
        "work rather than starting over, so describe each one by the slice "
        "of it that child owns.\n\n"
        "Before you answer `single`, you MUST consider DEPENDENCY-ORDERED "
        "IMPLEMENTATION SLICES. Work that will not cut across features can "
        "almost always be cut along its dependencies: a prerequisite child "
        "lands first, and the children that consume it land after it and "
        "name it in `depends_on`. A prerequisite MAY LAND DORMANT -- built, "
        "tested directly, and reached by nothing in production yet -- with "
        "its ACTIVATION waiting for the last consumer that needs it, the "
        "recovery and failure paths included, so no half-wired state is ever "
        "what a user or a later tick meets. A slice that only makes sense "
        "once everything around it exists is a dormant prerequisite, not "
        "proof that no safe split exists.\n\n"
        "EVERY CHILD BODY must own its slice end to end: the implementation "
        "of that slice, the tests that prove it (its dormant paths "
        "included), and the documentation that describes it. A child that "
        "leaves its own tests or documentation to a sibling is not a slice, "
        "and neither is one whose whole content is tests or documentation "
        "for another child's code."
    )


def _block_rules(threshold: int | None) -> str:
    """The one fenced block, its fields, and the budget each child owes.

    The example budget is scaled to the ceiling rather than fixed, because an
    agent copies the template it is shown: a standing figure would be a child
    this binary refuses on every repository configured under it, and the
    prompt would be handing out the one shape it then parks.
    """
    ceiling = _UNKNOWN_CEILING if threshold is None else threshold
    example = _EXAMPLE_ESTIMATE
    if threshold is not None:
        example = max(1, min(example, threshold // _EXAMPLE_SHARE))
    return (
        "End your final message with EXACTLY ONE fenced JSON block in this "
        "format (and nothing else after it):\n\n"
        "```orchestrator-late-manifest\n"
        "{\n"
        '  "decision": "split",\n'
        '  "rationale": "<<= 2 sentences why>",\n'
        '  "children": [\n'
        '    {"title": "...", "body": "...", "depends_on": [], '
        f'"{_budget.ESTIMATE}": {example}}}\n'
        "  ]\n"
        "}\n"
        "```\n\n"
        "The block must be valid JSON parseable by `json.loads`, and "
        "`decision` must be exactly the string `\"single\"`, `\"split\"`, or "
        "`\"question\"` (no other values, no union syntax). Unlike the "
        "initial decomposer, prose alone is not an outcome here: a reply with "
        "no block, or with more than one, is parked for a human rather than "
        "guessed at, so ask through `\"question\"` instead.\n\n"
        f'- On `"single"`: omit `"children"`. Give `"{_SPLIT_BLOCKER}"` -- '
        "one or two sentences on what makes splitting this work unsafe or "
        "unavailable. That is the part of a `single` answer the orchestrator "
        "keeps, and the only account anybody looking at this oversized "
        'candidate later has of why it was not split; `"rationale"` (<= 2 '
        'sentences) says why the work is one change and is not kept. '
        '`"category"` is optional and worth setting when the verdict has a '
        "reason worth counting.\n"
        f'- On `"split"`: `"children"` is a non-empty list of at most '
        f'{_MAX_CHILDREN} entries, each with a non-empty `"title"`, a '
        f'non-empty `"body"`, and an `"{_budget.ESTIMATE}"`. `"depends_on"` is a '
        "list of 0-based indexes into THIS children array (not GitHub issue "
        "numbers; the orchestrator allocates those). Self-dependencies and "
        "cycles are rejected.\n"
        '- On `"question"`: omit `"children"`, and give `"question"` (the one '
        'specific thing you are asking) and `"category"`.\n\n'
        f'`"{_budget.ESTIMATE}"` is REQUIRED on every child: your estimate of the '
        "lines that child will ADD, counted over ALL of its paths -- "
        "implementation, tests, documentation, fixtures, generated files, "
        "everything that child commits -- as one whole number of at least 1. "
        "NO PATH MAY BE EXCLUDED from it. It must be strictly below "
        f"{ceiling}, and a child estimated at or above that is refused: a "
        "split whose children are each still oversized is not a split, it is "
        "this same adjudication again with issue numbers in front of it. "
        "Leave real headroom under that ceiling for the REVIEW FIXES that "
        "land on the same pull request afterwards -- a child sized to only "
        "just fit comes back here the moment a reviewer asks for anything. "
        "The number binds nothing and excuses nothing: what decides whether "
        "a child is oversized is the ACTUAL CUMULATIVE MEASUREMENT of its "
        "own diff, taken the way this candidate's was.\n\n"
        f"`\"category\"` must be one of {_CATEGORIES}. Anything else is "
        "recorded as `unknown` rather than as what you wrote."
    )
