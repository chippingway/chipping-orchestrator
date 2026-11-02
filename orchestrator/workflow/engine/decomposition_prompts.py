# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Decomposition prompts, and what a decision hands the implementation after it.

The child limit comes from the manifest validator. Prompt markers and manifest
fields agree with their readers -- the `depends_on` list every child is told to
state is the one a fresh split reply is refused without -- and file lists
remain bounded in the notice. The prompt's last instruction is a check of the
block against that schema, because a reply that is valid JSON can still leave
out a list the validator refuses it without. That whole reply contract is
spelled once (`_MANIFEST_CONTRACT`): the decompose prompt closes on it, and the
correction prompt a rejected answer earns hands it back beside the exact error
the parser refused that answer with, so both ask for the same manifest.

The prompt sizes an issue by its complete deliverable -- implementation, tests,
the documentation it makes stale, and the final documentation pass -- judged by
the behaviors it delivers, their coupling, and the effort to verify them, never
by a file or commit count, and asks for the coarsest split whose children each
stay manageable. That is the policy the repository's `decompose` skill holds,
so the two change together.

An unsplit decision hands its groundwork on through a comment the implementer
reads in the thread. A split hands its rationale on through the parent's own
record instead: on a parent that is no umbrella it names the residual scope
the split kept for the parent's own pass, which the developer prompts quote
in a section of their own. That section is read off the record rather than
left to the thread, because the thread excerpt a prompt carries is bounded and
the split summary quoting the rationale is long past by the time every child
is done; and it is read off the record of the issue being implemented, so a
child, which records no split of its own, is handed none of its parent's.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    prompt_context as _prompt_context,
    prompt_notes as _prompt_notes,
)
from orchestrator.workflow.engine.prompt_context import _SECTION_SEP
from orchestrator.workflow.stages.decomposition import state as _decomposition_state
from orchestrator.workflow.stages.decomposition.validation import _MAX_CHILDREN

# The section a parent's developer prompt quotes its split's rationale under.
# Attributed to the decomposer and to the record it was read from, so the
# agent can tell the residual scope from the issue body and the thread around
# it, and quoted line by line, so none of the decomposer's words reads as this
# prompt's own instructions.
_SPLIT_RATIONALE_SECTION = (
    "Decomposer split rationale (the decomposer's own account, recorded on "
    "this issue when it split the issue into child issues, and quoted "
    "verbatim from that record rather than from the conversation; it explains "
    "the split and names the residual scope kept for this issue's own "
    "implementation, while the child issues carry the rest):\n\n{quoted}\n\n"
)


# The reply contract every initial decomposer answer is held to, the manifest
# parser's own rules spelled for the agent: the ordinary prompt closes on it,
# and a correction prompt hands it back whole beside the error its answer was
# refused with, so the two never ask for different manifests.
_MANIFEST_CONTRACT = (
    "If you genuinely need a clarification, end your message with a "
    "question for the human and DO NOT emit a manifest. Otherwise, end "
    "your final message with EXACTLY ONE fenced JSON block in this "
    "format (and nothing else after it):\n\n"
    "```orchestrator-manifest\n"
    "{\n"
    "  \"decision\": \"split\",\n"
    "  \"rationale\": \"<<= 2 sentences why>\",\n"
    "  \"umbrella\": false,\n"
    "  \"children\": [\n"
    "    {\"title\": \"...\", \"body\": \"...\", \"depends_on\": []},\n"
    "    {\"title\": \"...\", \"body\": \"... needs child 0 ...\", \"depends_on\": [0]}\n"
    "  ]\n"
    "}\n"
    "```\n\n"
    "The block must be valid JSON parseable by `json.loads`. The "
    "`decision` value must be exactly the string `\"single\"` or "
    "`\"split\"` (no other values, no union syntax). On `\"single\"`, "
    "omit the `children` field and instead hand off the context you "
    "already gathered so the implementer does not re-derive it: add "
    "`\"affected_files\"` (a list of repo-relative paths you found "
    "relevant) and `\"notes\"` (<= 3 sentences of concrete "
    "implementation guidance). Both are optional but strongly "
    "encouraged on `\"single\"`.\n\n"
    "Rules for the children list (omit entirely on 'single'):\n"
    f"- At most {_MAX_CHILDREN} children.\n"
    "- Every child MUST carry `depends_on`: a list of 0-based indexes "
    "into THIS children array (not GitHub issue numbers; the orchestrator "
    "allocates those). Use `[]` for a child with no prerequisites; a "
    "missing or null `depends_on` rejects the whole manifest.\n"
    "- `depends_on` must name exactly the prerequisites the child's body "
    "describes: a child whose body says it needs another child's work "
    "lists that child's index, and does not start until that child is "
    "done.\n"
    "- Self-dependencies and cycles are rejected.\n"
    "- Each child must be small enough to implement in one context "
    "(do not propose a child that itself needs decomposition).\n\n"
    "The optional `umbrella` boolean (default false) signals that the "
    "parent issue itself has NO implementation work of its own and exists "
    "only to aggregate the children. Set it to true when every line of "
    "the parent's intent is covered by the children you are creating; "
    "leave it false when the parent still needs its own coding pass after "
    "the children land. An umbrella parent auto-resolves to `done` once "
    "every child resolves; a non-umbrella parent re-enters "
    "implementation, so name its residual work in `rationale`.\n\n"
    "Before you emit the block, check it against this schema field by "
    "field. Valid JSON alone is not enough: a block that parses but "
    "leaves out a field it requires -- one child's `depends_on` is "
    "enough -- is refused, and the issue waits for a human. "
    "Confirm the `decision` value; on a split, that EVERY child carries "
    "an explicit `depends_on` array (`[]` for none, never omitted or "
    "null) naming exactly the prerequisites its body and your "
    "`rationale` describe; that the arrays form no self-dependency or "
    f"cycle and there are at most {_MAX_CHILDREN} children; and that "
    "nothing follows the closing fence."
)


def _build_decompose_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    comments_text: str,
    specs: list[_config_models.RepoSpec],
) -> str:
    body = issue.body or _prompt_notes._NO_BODY
    convo = comments_text or _prompt_notes._NO_PRIOR_COMMENTS
    tracked = _prompt_context._build_tracked_repos_context(spec, specs)
    tracked_block = f"{tracked}\n\n" if tracked else ""
    return (
        f"You are the decomposer for GitHub issue #{issue.number}: {issue.title!r}.\n\n"
        f"Issue body:\n{body}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"{tracked_block}"
        "Decide whether this issue's COMPLETE deliverable can be implemented "
        "in ONE coding-agent context. If yes, return decision='single'. If "
        "no, propose a list of smaller child issues, each manageable in one "
        "context on its own.\n\n"
        "Size the complete deliverable, not its code alone: the "
        "implementation, the tests that prove it, the documentation, "
        "inventories, and docstrings it makes stale, the format and "
        "integration work repository policy requires, and the final "
        "documentation pass every implementation receives. Judge it by the "
        "number and complexity of the distinct behaviors it delivers, how "
        "tightly they are coupled, the context an implementer has to read "
        "and hold, and the effort needed to verify the result. File and "
        "commit counts can guide your inspection, but neither decides single "
        "versus split on its own: a coherent, manageable change stays "
        "single however many files its completion touches, and a few files "
        "can still hold several substantial, independently deliverable "
        "behaviors. Use `git ls-files`, `wc -l`, or other read-only commands "
        "to inspect the codebase. You MUST NOT commit, push, or modify any "
        "file -- you are read-only.\n\n"
        "When the complete work is too large, split it at meaningful "
        "deliverable boundaries: each child delivers a behavior of its own, "
        "carries its own acceptance criteria and verification, and is "
        "manageable in one context. Before committing to a split, compare it "
        "with the plausible coarser groupings and prefer fewer complete "
        "children while their combined scope stays manageable -- every extra "
        "child repeats investigation, adds integration work, and adds a "
        "dependency handoff. A different file, owner, layer, or display is "
        "not on its own a reason for another child. The child limit below is "
        "a ceiling, not a target, and the residual work a non-umbrella "
        "parent keeps for its own pass must itself fit one context. Each "
        "child carries its own tests and documentation, so never propose one "
        "that only runs checks or cleans up documentation another child "
        "owes. Assign every parent requirement exactly once, to one child or "
        "to that residual parent work. Once all of a child's direct and "
        "transitive prerequisites have landed completely, it must still keep "
        "a unique acceptance criterion and a non-empty diff, and no two "
        "children may promise the same behavior. If no split meets these "
        "rules, answer single. Explain the decision in `rationale` by its "
        "concrete scope and dependencies, not by a file count.\n\n"
        f"{_MANIFEST_CONTRACT}"
    )


def _build_correction_prompt(diagnostic: str) -> str:
    """The one correction a rejected manifest earns, asked of the session that wrote it.

    Handed to the resumed conversation, which already holds the issue and the
    reasoning behind its answer, so it carries only the exact error the
    manifest parser refused that answer with and the whole contract the
    ordinary prompt closes on: one complete manifest, never a patch of the
    rejected block, held to the very rules that refused it.
    """
    return (
        "The orchestrator's manifest validator rejected the decomposition "
        "manifest you just returned, with this error:\n\n"
        f"> {diagnostic}\n\n"
        "Return ONE complete corrected answer for the same issue: the whole "
        "manifest again, every field and every child in full, never a patch "
        "or a diff of the rejected block. Fix what the error names and "
        "re-check every other child against the same rules -- one omission "
        "repeated elsewhere is refused the same way. Keep the decision and "
        "the children you intended unless the error itself requires "
        "changing them. You are still read-only: you MUST NOT commit, push, "
        "or modify any file.\n\n"
        f"{_MANIFEST_CONTRACT}"
    )


def _single_manifest_text(
    manifest: dict, field_name: str, fallback: str = "",
) -> str:
    """Return one stripped optional text field with a safe fallback."""
    raw_value = manifest.get(field_name)
    text = raw_value.strip() if isinstance(raw_value, str) else ""
    return text or fallback


def _single_manifest_files(manifest: dict) -> list[str]:
    """Return non-empty string paths from optional single-decision context."""
    raw_files = manifest.get("affected_files")
    if not isinstance(raw_files, list):
        return []
    return [
        file_path.strip()
        for file_path in raw_files
        if isinstance(file_path, str) and file_path.strip()
    ]


def _build_single_decision_comment(manifest: dict) -> str:
    """Compose the `single`-decision comment posted on the parent issue.

    Beyond the decomposer's rationale, this surfaces the context the
    decomposer already gathered while sizing the issue -- the affected
    files and any implementation notes -- so the develop agent that picks
    the issue up in `implementing` starts from that groundwork instead of
    re-deriving it. The implementer reads the issue thread via
    `_recent_comments_text` at spawn, so anything included here reaches it.
    A comment (not a body edit) is deliberate: rewriting the issue body
    would shift the user-content hash and trip `_detect_user_content_change`
    into re-decomposing the issue on the next tick.

    Every field beyond `decision` is best-effort. `_parse_manifest` only
    validates the decision string for the single branch, so `rationale` /
    `affected_files` / `notes` may be any JSON value or missing; coerce
    non-strings / non-lists to empty rather than parking a valid single
    decision after the agent already ran.
    """
    rationale = _single_manifest_text(
        manifest, "rationale", "(no rationale provided)",
    )
    lines = [f":mag: decomposer says this fits one context: {rationale}"]

    files = _single_manifest_files(manifest)
    if files:
        rendered = "\n".join(f"- `{file_path}`" for file_path in files)
        lines.append(f"**Affected files:**\n{rendered}")

    notes = _single_manifest_text(manifest, "notes")
    if notes:
        lines.append(f"**Implementation notes:**\n{notes}")

    return _SECTION_SEP.join(lines)


def _handed_split_rationale(state: PinnedState) -> str | None:
    """The rationale this issue's own developer prompts are handed, or None where they are handed none.

    The issue's latest split's, as `_recorded_split_rationale` reads it back,
    so a record an older binary or a hand edit left without usable text hands
    nothing, and whatever superseded the split has already cleared it. It does
    not ask whether the split still holds `split_attempt`: the parent's
    hand-back drops that once every child is done, which is exactly when the
    implementation this is for begins. An umbrella's rationale is withheld,
    since an umbrella keeps no work of its own for the account to scope.
    """
    if state.get(_decomposition_state._UMBRELLA):
        return None
    return _decomposition_state._recorded_split_rationale(state)


def _split_rationale_block(rationale: str | None) -> str:
    """The attributed section quoting `rationale` whole, or nothing where there is none.

    Every line is quoted whatever ends it -- a bare carriage return included,
    after which the words would otherwise start a line of the prompt's own.
    """
    if rationale is None:
        return ""
    quoted = "".join(f"> {line}" for line in rationale.splitlines(keepends=True))
    return _SPLIT_RATIONALE_SECTION.format(quoted=quoted)
