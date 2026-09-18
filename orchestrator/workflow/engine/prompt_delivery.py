# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Exact delivered developer inputs, bounded-excerpt omissions, and settlement.

Records which issue-thread, PR-conversation, inline-review, and review-summary
inputs actually entered a developer prompt. Surfaces retain their distinct
namespaces and provenance, preserving pinned watermark fields
(`last_action_comment_id`, `pr_last_comment_id`, `pr_last_review_comment_id`,
`pr_last_review_summary_id`) and requirements revision (`user_content_hash`).

Forward updates are conservative: they never copy a live thread tip,
combine unrelated namespaces, or take an unrestricted maximum across surfaces.
Untrusted comments and forged orchestrator markers cannot authorize
advancement. The pinned state comment is excluded by its id where a caller
names it, so a human reply quoting its marker is still a reply. Independent
watermarks are derived across surfaces without collapsing mixed snapshots.
Unseen PR comments bound the PR conversation cursor without holding back the
issue action watermark. Starting watermarks are incorporated so historical
omitted context does not block forward progress.

Consumed field pairs are exposed for durable report/checkpoint settlement and
can be settled directly and idempotently into pinned state.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType

from orchestrator.github import comments as _trust
from orchestrator.github.comments import is_trusted_author
from orchestrator.github.pinned_state import PinnedState

log = logging.getLogger("orchestrator.workflow")

# The four distinct surfaces whose inputs may enter an agent prompt.
SURFACE_ISSUE_THREAD = "issue_thread"
SURFACE_PR_CONVERSATION = "pr_conversation"
SURFACE_INLINE_REVIEW = "inline_review"
SURFACE_REVIEW_SUMMARY = "review_summary"

SURFACES = frozenset((
    SURFACE_ISSUE_THREAD,
    SURFACE_PR_CONVERSATION,
    SURFACE_INLINE_REVIEW,
    SURFACE_REVIEW_SUMMARY,
))

# Status of each input evaluated for delivery.
STATUS_DELIVERED = "delivered"
STATUS_PARTIALLY_OMITTED = "partially_omitted"
STATUS_OMITTED = "omitted"
STATUS_FILTERED = "filtered"

STATUSES = frozenset((
    STATUS_DELIVERED,
    STATUS_PARTIALLY_OMITTED,
    STATUS_OMITTED,
    STATUS_FILTERED,
))

# Specific filtering reasons retained in the snapshot.
REASON_UNTRUSTED_AUTHOR = "untrusted_author"
REASON_FORGED_MARKER = "forged_marker"
REASON_UNRECORDED_PAT = "unrecorded_pat"
REASON_STATE_COMMENT = "state_comment"
REASON_ORCHESTRATOR_COMMENT = "orchestrator_comment"

# Pinned field names preserved verbatim.
PINNED_LAST_ACTION_COMMENT_ID = "last_action_comment_id"
PINNED_PR_LAST_COMMENT_ID = "pr_last_comment_id"
PINNED_PR_LAST_REVIEW_COMMENT_ID = "pr_last_review_comment_id"
PINNED_PR_LAST_REVIEW_SUMMARY_ID = "pr_last_review_summary_id"
PINNED_USER_CONTENT_HASH = "user_content_hash"

WATERMARK_FIELDS = (
    PINNED_LAST_ACTION_COMMENT_ID,
    PINNED_PR_LAST_COMMENT_ID,
    PINNED_PR_LAST_REVIEW_COMMENT_ID,
    PINNED_PR_LAST_REVIEW_SUMMARY_ID,
)

_SURFACE_CURSORS = MappingProxyType({
    SURFACE_ISSUE_THREAD: PINNED_LAST_ACTION_COMMENT_ID,
    SURFACE_PR_CONVERSATION: PINNED_PR_LAST_COMMENT_ID,
    SURFACE_INLINE_REVIEW: PINNED_PR_LAST_REVIEW_COMMENT_ID,
    SURFACE_REVIEW_SUMMARY: PINNED_PR_LAST_REVIEW_SUMMARY_ID,
})

_BATCH_KEYS = (
    (SURFACE_ISSUE_THREAD, "issue_comments"),
    (SURFACE_PR_CONVERSATION, "pr_conversation_comments"),
    (SURFACE_INLINE_REVIEW, "inline_review_comments"),
    (SURFACE_REVIEW_SUMMARY, "review_summaries"),
)

_SECTION_SEP = "\n\n"
_EMPTY_IDS: frozenset[int] = frozenset()
_DEFAULT_AUTHOR = "user"
_DEFAULT_MAX_CHARS = 4000
_ATTR_BODY = "body"
_ATTR_ID = "id"
_ATTR_USER = "user"
_ATTR_LOGIN = "login"

# What `classify_comment` answers for a comment somebody outside this process
# wrote and nothing here refuses: admitted, with no filtering reason recorded
# against it. Our own posts come back admitted too, under the reason that
# names them, which is why the reason is half of the test.
_A_HUMAN_WROTE_IT = (True, None)

SurfaceBatch = tuple[str, Iterable]
Batches = dict[str, Iterable] | Iterable[SurfaceBatch]


@dataclass(frozen=True)
class DeliveredInput:
    """A single input evaluated for inclusion in a developer prompt."""

    surface: str
    id: int
    author: str
    body: str = ""
    created_at: datetime | None = None
    status: str = STATUS_DELIVERED
    filter_reason: str | None = None
    rendered_line: str = ""

    @property
    def is_delivered(self) -> bool:
        """Whether this input was fully delivered into the prompt."""
        return self.status == STATUS_DELIVERED

    @property
    def is_omitted(self) -> bool:
        """Whether this input was omitted by excerpt bounds or selection."""
        return self.status == STATUS_OMITTED

    @property
    def is_partially_omitted(self) -> bool:
        """Whether this input was partially truncated by character bounds."""
        return self.status == STATUS_PARTIALLY_OMITTED

    @property
    def is_filtered(self) -> bool:
        """Whether this input was rejected by trust or marker checks."""
        return self.status == STATUS_FILTERED

    def with_status(self, new_status: str) -> DeliveredInput:
        """Return a copy of this input with an updated status."""
        return DeliveredInput(
            surface=self.surface,
            id=self.id,
            author=self.author,
            body=self.body,
            created_at=self.created_at,
            status=new_status,
            filter_reason=self.filter_reason,
            rendered_line=self.rendered_line,
        )

    def bound_status(self, start_off: int, end_off: int, cutoff: int) -> str:
        """Determine delivery status from character span relative to cutoff."""
        if start_off >= cutoff:
            return STATUS_DELIVERED
        if end_off <= cutoff:
            return STATUS_OMITTED
        return STATUS_PARTIALLY_OMITTED

    @classmethod
    def render_line(cls, surface: str, raw_entry: object, author: str) -> str:
        """Render one comment or review summary into its prompt line."""
        body_text = getattr(raw_entry, _ATTR_BODY, "") or ""
        if surface == SURFACE_PR_CONVERSATION:
            return f"@{author} (PR comment): {body_text}"
        if surface == SURFACE_INLINE_REVIEW:
            return f"@{author} (review comment): {body_text}"
        if surface == SURFACE_REVIEW_SUMMARY:
            state_tag = getattr(raw_entry, "state", "")
            suffix = f" (review {state_tag})" if state_tag else " (review)"
            return f"@{author}{suffix}: {body_text}"
        return f"@{author}: {body_text}"


@dataclass(frozen=True)
class PromptDeliverySnapshot:
    """Process-local record of exact inputs delivered to a developer prompt."""

    entries: tuple[DeliveredInput, ...]
    requirements_revision: str | None = None
    rendered_text: str = ""
    tracked_repos_text: str = ""
    issue_watermark_field: str | None = None
    initial_cursors: dict[str, int] = field(default_factory=dict)

    def surface_provenance(self, surface: str) -> tuple[DeliveredInput, ...]:
        """Return all evaluated inputs that originated on `surface`."""
        return tuple(
            entry for entry in self.entries if entry.surface == surface
        )

    def per_surface_projections(self) -> dict[str, tuple[DeliveredInput, ...]]:
        """Project evaluated inputs grouped by their originating surface."""
        surfaces = {entry.surface for entry in self.entries}
        return {
            surface: self.surface_provenance(surface)
            for surface in surfaces
        }

    def delivered_inputs(
        self, surface: str | None = None,
    ) -> tuple[DeliveredInput, ...]:
        """Return inputs that were fully delivered, optionally by surface."""
        return tuple(
            entry for entry in self.entries
            if entry.is_delivered and (
                surface is None or entry.surface == surface
            )
        )

    def bounded_excerpt_omissions(
        self, surface: str | None = None,
    ) -> tuple[DeliveredInput, ...]:
        """Return inputs omitted or partially omitted by excerpt limits."""
        return tuple(
            entry for entry in self.entries
            if (entry.is_omitted or entry.is_partially_omitted)
            and (surface is None or entry.surface == surface)
        )

    def filtering_decisions(
        self, surface: str | None = None,
    ) -> tuple[DeliveredInput, ...]:
        """Return inputs excluded by trust, marker, or ownership filtering."""
        return tuple(
            entry for entry in self.entries
            if entry.is_filtered and (
                surface is None or entry.surface == surface
            )
        )

    def consumed_pairs(
        self, state: PinnedState | None = None,
    ) -> tuple[tuple[str, int | str], ...]:
        """Derive forward updates for consumed pinned state fields."""
        return _DeliverySettlement.consumed_pairs(self, state)

    def settle(self, state: PinnedState) -> tuple[tuple[str, int | str], ...]:
        """Directly and idempotently apply forward updates into `state`."""
        return _DeliverySettlement.settle(state, self)


class _DeliverySettlement:
    """Helper deriving forward watermarks and applying direct settlement."""

    @classmethod
    def watermark(
        cls,
        delivered_entries: Iterable[DeliveredInput],
        omitted_entries: Iterable[DeliveredInput],
        initial_cursor: int | None = None,
        cursors: dict[str, int] | None = None,
    ) -> int | None:
        delivered_ids = [
            entry.id for entry in delivered_entries
            if entry.is_delivered
            and entry.filter_reason != REASON_ORCHESTRATOR_COMMENT
        ]
        if not delivered_ids:
            return None
        blocking_ids = [
            entry.id for entry in omitted_entries
            if cls._is_blocking(entry, cursors, initial_cursor)
        ]
        limit = min(blocking_ids) if blocking_ids else None
        eligible = [
            cid for cid in delivered_ids
            if (limit is None or cid < limit)
            and (initial_cursor is None or cid > initial_cursor)
        ]
        return max(eligible) if eligible else None

    @classmethod
    def consumed_pairs(
        cls,
        snapshot: PromptDeliverySnapshot,
        state: PinnedState | None = None,
    ) -> tuple[tuple[str, int | str], ...]:
        cursors = dict(snapshot.initial_cursors)
        if state is not None:
            for fname in WATERMARK_FIELDS:
                raw_cursor = state.get(fname)
                if fname not in cursors and isinstance(raw_cursor, int):
                    cursors[fname] = raw_cursor

        pairs: list[tuple[str, int | str]] = []
        cls._add_review_pairs(snapshot, cursors, pairs)
        cls._add_action_pair(snapshot, cursors, pairs)
        cls._add_pr_pair(snapshot, cursors, pairs)
        if snapshot.requirements_revision:
            pairs.append(
                (PINNED_USER_CONTENT_HASH, snapshot.requirements_revision),
            )
        return tuple(pairs)

    @classmethod
    def settle(
        cls,
        state: PinnedState,
        snapshot: PromptDeliverySnapshot,
    ) -> tuple[tuple[str, int | str], ...]:
        pairs = cls.consumed_pairs(snapshot, state)
        for pair in pairs:
            prior = state.get(pair[0])
            if (
                isinstance(pair[1], int)
                and isinstance(prior, int)
                and prior >= pair[1]
            ):
                continue
            state.set(pair[0], pair[1])
        return pairs

    @classmethod
    def _is_blocking(
        cls,
        entry: DeliveredInput,
        cursors: dict[str, int] | None = None,
        fallback_cursor: int | None = None,
    ) -> bool:
        if not (entry.is_omitted or entry.is_partially_omitted):
            return False
        if cursors is None:
            cursor = fallback_cursor
        else:
            cursor_field = _SURFACE_CURSORS.get(entry.surface)
            cursor = cursors.get(cursor_field) if cursor_field else None
        return cursor is None or entry.id > cursor

    @classmethod
    def _add_review_pairs(
        cls,
        snapshot: PromptDeliverySnapshot,
        cursors: dict[str, int],
        pairs: list[tuple[str, int | str]],
    ) -> None:
        inline_entries = snapshot.surface_provenance(SURFACE_INLINE_REVIEW)
        if inline_entries:
            wm_inline = cls.watermark(
                inline_entries, inline_entries,
                cursors.get(PINNED_PR_LAST_REVIEW_COMMENT_ID),
                cursors,
            )
            if wm_inline is not None:
                pairs.append((PINNED_PR_LAST_REVIEW_COMMENT_ID, wm_inline))

        summary_entries = snapshot.surface_provenance(SURFACE_REVIEW_SUMMARY)
        if summary_entries:
            wm_summary = cls.watermark(
                summary_entries, summary_entries,
                cursors.get(PINNED_PR_LAST_REVIEW_SUMMARY_ID),
                cursors,
            )
            if wm_summary is not None:
                pairs.append((PINNED_PR_LAST_REVIEW_SUMMARY_ID, wm_summary))

    @classmethod
    def _add_action_pair(
        cls,
        snapshot: PromptDeliverySnapshot,
        cursors: dict[str, int],
        pairs: list[tuple[str, int | str]],
    ) -> None:
        thread_entries = snapshot.surface_provenance(SURFACE_ISSUE_THREAD)
        if thread_entries:
            wm_action = cls.watermark(
                thread_entries, thread_entries,
                cursors.get(PINNED_LAST_ACTION_COMMENT_ID),
                cursors,
            )
            if wm_action is not None:
                pairs.append((PINNED_LAST_ACTION_COMMENT_ID, wm_action))

    @classmethod
    def _add_pr_pair(
        cls,
        snapshot: PromptDeliverySnapshot,
        cursors: dict[str, int],
        pairs: list[tuple[str, int | str]],
    ) -> None:
        pr_entries = snapshot.surface_provenance(SURFACE_PR_CONVERSATION)
        target = snapshot.issue_watermark_field
        if pr_entries or target == PINNED_PR_LAST_COMMENT_ID:
            issue_space = tuple(
                entry for entry in snapshot.entries
                if entry.surface in (
                    SURFACE_ISSUE_THREAD, SURFACE_PR_CONVERSATION,
                )
            )
            wm_pr = cls.watermark(
                issue_space, issue_space,
                cursors.get(PINNED_PR_LAST_COMMENT_ID),
                cursors,
            )
            if wm_pr is not None:
                pairs.append((PINNED_PR_LAST_COMMENT_ID, wm_pr))


class _CandidateClassifier:
    """Classifies input entries against trust, marker, and ownership rules."""

    @classmethod
    def classify_comment(
        cls,
        comment: object,
        retained_ids: frozenset,
        pat_login: str | None = None,
        state_comment_id: int | None = None,
    ) -> tuple[bool, str | None]:
        """Whether one comment may enter a prompt, and why not where it may not.

        The pinned state comment is answered by IDENTITY where the caller can
        name it, and by its marker only where it cannot -- the same split the
        thread reader makes. The marker is text a human can quote, and read as
        the pinned comment it hides that human's reply from every prompt while
        the reading beside it still counts the reply as there.
        """
        body_text = getattr(comment, _ATTR_BODY, None) or ""
        if state_comment_id is None:
            pinned = "<!--orchestrator-state" in body_text
        else:
            pinned = getattr(comment, _ATTR_ID, None) == state_comment_id
        if pinned:
            return False, REASON_STATE_COMMENT

        posted_here = getattr(comment, _ATTR_ID, None) in retained_ids
        if _trust.ORCHESTRATOR_COMMENT_MARKER in body_text and not posted_here:
            return False, REASON_FORGED_MARKER

        if posted_here:
            return True, REASON_ORCHESTRATOR_COMMENT

        user_obj = getattr(comment, _ATTR_USER, None)
        trusted = is_trusted_author(user_obj)
        return trusted, None if trusted else REASON_UNTRUSTED_AUTHOR

    @classmethod
    def human_replies(
        cls,
        read: Iterable,
        retained_ids: frozenset = _EMPTY_IDS,
        state_comment_id: int | None = None,
    ) -> list:
        """The replies one read of a thread leaves for a prompt to be built of.

        The same classification `evaluate` records per entry, asked as a list
        question, for the roads that decide who OWNS a batch before anything
        builds a prompt from it. One answer rather than two: a command
        classifier reading the raw thread and a delivery record reading the
        filtered one disagree the moment a comment is in exactly one of them
        -- a park notice of ours above the reply a human wrote while the agent
        was out makes the batch look mixed to the classifier, which passes it
        through to a resume that then delivers the bare command as prose, the
        explicit retry gone and the watermark moved past the words that asked
        for it.

        Four kinds come out: an untrusted author, the pinned state comment,
        our own posts by recorded id, and a body carrying our marker that the
        ledger cannot vouch for. The last two are the same evidence read in
        both directions -- an id admits a comment as ours and a marker without
        one admits nothing -- because the marker is an HTML comment anybody may
        paste and the login may be a token shared with a human.

        `state_comment_id` names the pinned comment for a read that was taken
        by it, so a reply quoting the state marker is a reply like any other.
        """
        return [
            reply for reply in read
            if cls.classify_comment(
                reply, retained_ids, state_comment_id=state_comment_id,
            ) == _A_HUMAN_WROTE_IT
        ]

    @classmethod
    def classify_review(
        cls,
        review: object,
        retained_ids: frozenset = _EMPTY_IDS,
        pat_login: str | None = None,
    ) -> tuple[bool, str | None]:
        body_text = getattr(review, _ATTR_BODY, None) or ""
        posted_here = getattr(review, _ATTR_ID, None) in retained_ids
        if _trust.ORCHESTRATOR_COMMENT_MARKER in body_text and not posted_here:
            return False, REASON_FORGED_MARKER
        if posted_here:
            return True, REASON_ORCHESTRATOR_COMMENT
        user_obj = getattr(review, _ATTR_USER, None)
        trusted = is_trusted_author(user_obj)
        return trusted, None if trusted else REASON_UNTRUSTED_AUTHOR

    @classmethod
    def evaluate(
        cls,
        surface: str,
        raw_entry: object,
        retained_ids: frozenset,
        pat_login: str | None,
        state_comment_id: int | None = None,
    ) -> tuple[DeliveredInput, bool]:
        if surface in (SURFACE_REVIEW_SUMMARY, SURFACE_INLINE_REVIEW):
            is_ok, reason = cls.classify_review(
                raw_entry, retained_ids, pat_login,
            )
        else:
            is_ok, reason = cls.classify_comment(
                raw_entry, retained_ids, pat_login, state_comment_id,
            )

        user_obj = getattr(raw_entry, _ATTR_USER, None)
        author = (
            getattr(user_obj, _ATTR_LOGIN, _DEFAULT_AUTHOR)
            if user_obj
            else _DEFAULT_AUTHOR
        )
        return (
            DeliveredInput(
                surface=surface,
                id=getattr(raw_entry, _ATTR_ID, 0),
                author=author,
                body=getattr(raw_entry, _ATTR_BODY, "") or "",
                created_at=(
                    getattr(raw_entry, "created_at", None)
                    or getattr(raw_entry, "submitted_at", None)
                ),
                status=STATUS_DELIVERED if is_ok else STATUS_FILTERED,
                filter_reason=reason,
                rendered_line=DeliveredInput.render_line(
                    surface, raw_entry, author,
                ),
            ),
            is_ok,
        )

    @classmethod
    def surface_retained(cls, options: dict, surface: str) -> frozenset[int]:
        retained = options.get("retained_ids", _EMPTY_IDS)
        if isinstance(retained, dict):
            return frozenset(retained.get(surface, _EMPTY_IDS))
        if surface in (SURFACE_ISSUE_THREAD, SURFACE_PR_CONVERSATION):
            return frozenset(retained)
        key = (
            "retained_review_ids" if surface == SURFACE_INLINE_REVIEW
            else "retained_summary_ids"
        )
        return frozenset(options.get(key, _EMPTY_IDS))

    @classmethod
    def scan_batches(
        cls,
        batches: list[tuple[str, Iterable]],
        options: dict,
    ) -> list[DeliveredInput]:
        evaluated: list[DeliveredInput] = []
        for sname, batch in batches:
            retained = cls.surface_retained(options, sname)
            # The pinned comment lives on the issue thread, so the identity
            # that names it answers for that surface and no other.
            pinned = (
                options.get("state_comment_id")
                if sname == SURFACE_ISSUE_THREAD else None
            )
            evaluated.extend(
                cls.evaluate(
                    sname, raw_input, retained, options.get("pat_login"), pinned,
                )[0]
                for raw_input in batch
            )
        return evaluated

    @classmethod
    def append_unseen(
        cls,
        evaluated: list[DeliveredInput],
        options: dict,
    ) -> None:
        retained = cls.surface_retained(options, SURFACE_PR_CONVERSATION)
        for raw_comment in options.get("unseen_comments", ()):
            surface = getattr(raw_comment, "surface", SURFACE_PR_CONVERSATION)
            entry, is_ok = cls.evaluate(
                surface, raw_comment, retained, options.get("pat_login"),
            )
            evaluated.append(
                entry.with_status(STATUS_OMITTED) if is_ok else entry,
            )


class _SnapshotAssembler:
    """Normalizes batches, applies character bounds, and builds snapshots."""

    @classmethod
    def build(
        cls,
        surface_batches: Batches | None,
        options: dict,
    ) -> PromptDeliverySnapshot:
        cursors = cls.freeze_cursors(options)
        provided = options.get("entries")
        if provided is not None:
            return PromptDeliverySnapshot(
                entries=tuple(provided),
                requirements_revision=options.get("requirements_revision"),
                tracked_repos_text=options.get("tracked_repos_text", ""),
                issue_watermark_field=options.get("issue_watermark_field"),
                initial_cursors=cursors,
            )
        batches = cls.normalize_batches(surface_batches, options)
        return cls._assemble_from_batches(batches, options, cursors)

    @classmethod
    def freeze_cursors(cls, options: dict) -> dict[str, int]:
        cursors: dict[str, int] = {}
        state_arg = options.get("state") or options.get("initial_state")
        if state_arg is not None:
            for field_name in WATERMARK_FIELDS:
                cursor_val = state_arg.get(field_name)
                if isinstance(cursor_val, int):
                    cursors[field_name] = cursor_val
        passed = options.get("initial_cursors")
        if passed:
            cursors.update(passed)
        return cursors

    @classmethod
    def normalize_batches(
        cls,
        surface_batches: Batches | None,
        options: dict,
    ) -> list[tuple[str, Iterable]]:
        if surface_batches is not None:
            if isinstance(surface_batches, dict):
                return list(surface_batches.items())
            return list(surface_batches)

        ordered: list[tuple[str, Iterable]] = []
        for surface, key in _BATCH_KEYS:
            batch = options.get(key, ())
            if batch:
                ordered.append((surface, batch))
        return ordered

    @classmethod
    def apply_bounds(
        cls,
        authorized: list[DeliveredInput],
        max_chars: int | None,
    ) -> tuple[list[DeliveredInput], str]:
        if max_chars is not None and max_chars < 0:
            raise ValueError("max_chars must be non-negative")
        if not authorized:
            return [], ""
        if max_chars == 0:
            return [
                entry.with_status(STATUS_OMITTED) for entry in authorized
            ], ""
        full_text = _SECTION_SEP.join(
            entry.rendered_line for entry in authorized
        )
        if max_chars is None or len(full_text) <= max_chars:
            return authorized, full_text
        cutoff = len(full_text) - max_chars
        sliced = cls._slice_authorized(authorized, cutoff)
        return sliced, full_text[-max_chars:]

    @classmethod
    def _slice_authorized(
        cls,
        authorized: Iterable[DeliveredInput],
        cutoff: int,
    ) -> list[DeliveredInput]:
        sliced: list[DeliveredInput] = []
        curr = 0
        for entry in authorized:
            line_len = len(entry.rendered_line)
            status = entry.bound_status(curr, curr + line_len, cutoff)
            sliced.append(entry.with_status(status))
            curr += line_len + len(_SECTION_SEP)
        return sliced

    @classmethod
    def _collect_and_bound(
        cls,
        batches: list[tuple[str, Iterable]],
        options: dict,
    ) -> tuple[list[DeliveredInput], str]:
        evaluated = _CandidateClassifier.scan_batches(batches, options)
        authorized = [entry for entry in evaluated if not entry.is_filtered]
        bounded, text = cls.apply_bounds(
            authorized, options.get("max_chars", _DEFAULT_MAX_CHARS),
        )
        bounded_iter = iter(bounded)
        return [
            entry if entry.is_filtered else next(bounded_iter)
            for entry in evaluated
        ], text

    @classmethod
    def _assemble_from_batches(
        cls,
        batches: list[tuple[str, Iterable]],
        options: dict,
        cursors: dict[str, int],
    ) -> PromptDeliverySnapshot:
        evaluated, text = cls._collect_and_bound(batches, options)
        _CandidateClassifier.append_unseen(evaluated, options)
        return PromptDeliverySnapshot(
            entries=tuple(evaluated),
            requirements_revision=options.get("requirements_revision"),
            rendered_text=text,
            tracked_repos_text=options.get("tracked_repos_text", ""),
            issue_watermark_field=options.get("issue_watermark_field"),
            initial_cursors=cursors,
        )


def settle_delivery(
    state: PinnedState,
    snapshot: PromptDeliverySnapshot,
) -> tuple[tuple[str, int | str], ...]:
    """Rachet consumed fields forward into pinned state without regression."""
    return _DeliverySettlement.settle(state, snapshot)


def create_prompt_delivery_snapshot(
    surface_batches: Batches | None = None,
    **options,
) -> PromptDeliverySnapshot:
    """Build process-local record of exact inputs delivered to a prompt."""
    return _SnapshotAssembler.build(surface_batches, options)


classify_comment_trust = _CandidateClassifier.classify_comment
classify_review_trust = _CandidateClassifier.classify_review
human_replies = _CandidateClassifier.human_replies
