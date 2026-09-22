# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What this stage reads as unread feedback, and when that batch has settled.

The rescan reads the in_review watermarks, never the `pending_fix_*`
bookmarks: the bookmarks are the replay source a `/orchestrator continue`
needs, and consuming them here would spend them on the ordinary tick. It
reads them through the in_review owner rather than off pinned state directly,
because the issue thread and the PR conversation share an id space without
sharing a delivery record -- the thread answers to the issue-only cursor an
implementing or validating resume settled as well as to the PR-side one, and
the pull request answers to the PR-side cursor alone.

The quiet window sits between the scan and the advance because it is the same
batch it measures: a human mid-thought posts three comments in a minute, and
resuming on the first would spend the session on a fragment. Each rescan
re-reads the freshest timestamp, so a later comment extends the wait rather
than racing it -- and an accepted `/orchestrator continue` skips it outright,
because that is a deliberate operator signal rather than chatter.

The settlement is the narrower half of that pair, and it is the same reading
from the other end: each surface is recorded as consumed for the reader that
OWNS it, and for no other. The issue thread moves the issue-action boundary
`last_action_comment_id` beside the PR-side cursor, because a reply this stage
quoted has been in a developer prompt and the implementing and validating
resumes decide what to hand a parked session off exactly that field -- left
behind, a manual relabel out of `fixing` pays a second developer to read the
comment this one already answered. The PR conversation, the inline review
comments and the review summaries move only the in_review watermarks that are
theirs: nothing that advances the issue-action boundary has read the pull
request, so writing it over PR feedback would hide input no prompt carried.

While a report is owed the readers say less than they usually do, because they
are held back until its publication lands -- so the batch that report answers
reads as unread for as long as the push or the post keeps failing. What still
knows is the record, whose frozen pairs say exactly what its run consumed; a
rescan with nothing above them is the prompt the outstanding report is about,
and the tick holds rather than paying a second developer to answer it again.

Each reader advances only to the max id actually fed to the dev on the surface
it owns, ratcheted against what is already there, because a human comment that
landed after the scan was never quoted in the prompt. Swallowing it would drop
real feedback on the pushed path (the next in_review tick misses it) and on the
park path (the next fixing tick's stay-parked gate drops it), which is why the
settlement runs on every outcome that counts the prompt as delivered rather
than on success alone -- and on none that does not.

DIRECTLY, though, only where no report is owed for it. A round that finished on
a report outcome records these same pairs onto its report transaction instead,
and the write that completes that publication applies them; this owner still
derives them, so the two roads write the same fields the same way.

Orchestrator comments are stripped from the two IssueComment surfaces by
recorded id AND by the hidden body marker, because the id ledger is capped and
evicts on long-lived issues while the marker stays on the comment forever. The
two review surfaces are asked the delivery owner's own question instead, and
that one has no marker rule: this orchestrator posts no review and no inline
comment, so a body quoting the marker there is a reviewer quoting it -- and
the scan and the settlement have to answer it the same way or the item is
prompted and then recorded for nobody. A bare `/orchestrator add-agent-runs`
is stripped beside them, as in_review strips it: a control, not feedback. The
trusted-author filter sits above every surface, so an outsider on a public PR
can neither resume the dev nor extend the quiet window; an empty allowlist
trusts everyone.
"""
from __future__ import annotations

from datetime import UTC, datetime

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import filter_trusted
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    prompt_delivery as _delivery,
    report_consumed_values as _consumed,
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
    run_grant_request as _run_grant_request,
)
from orchestrator.workflow.stages.fixing import models as _models
from orchestrator.workflow.stages.in_review import (
    surfaces as _in_review_surfaces,
    watermarks as _in_review_watermarks,
)

# The excerpt bound this stage does not have. `_build_pr_comment_followup`
# quotes every item it is handed, so a record taken under a limit would name an
# omission the prompt never made -- and every reader would then stop below an
# item the developer read and hand it back as fresh feedback next tick.
_UNBOUNDED_EXCERPT = None

# What the delivery owner answers for an item nobody here wrote and nothing
# here refuses: admitted, under no reason of ours. Anything else is an item
# that owner would decline to advance a reader for, so it may not reach a
# prompt either.
_ADMITTED = (True, None)


def _unclaimed(comments, state) -> list:
    """The items of one IssueComment surface a developer may be handed.

    Orchestrator comments are filtered by id AND the hidden body marker -- the
    id cap evicts old ids on long-lived issues, after which an id-only filter
    would start re-feeding old bot comments to the dev. The pinned record is
    dropped by IDENTITY beside them, because neither of those two reaches it:
    it carries a marker of its own and nothing writes its id into the ledger,
    so an issue whose cursors sit below it would quote this stage's own
    bookkeeping to a developer -- and the settlement refuses it as the pinned
    comment, leaving it prompted and recorded for nobody. A bare
    `/orchestrator add-agent-runs` is dropped beside them, since it is a
    control the run-limit hold has already answered. Untrusted authors are
    dropped last (see `filter_trusted`) so an outsider's comment never resumes
    the dev or extends the debounce window; an empty allowlist trusts everyone.
    """
    orchestrator_ids = _comments._orchestrator_ids(state)
    unread = [
        comment
        for comment in comments
        if comment.id not in orchestrator_ids
        and comment.id != state.comment_id
        and _comments._ORCH_COMMENT_MARKER not in (comment.body or "")
        and not _run_grant_request._is_bare_command(comment)
    ]
    return filter_trusted(sorted(unread, key=lambda comment: comment.id))


def _reviewed(read) -> list:
    """One review surface's unread items a developer prompt may quote.

    Asked of the DELIVERY owner's own classifier rather than of the trust
    gate beside it, because what this returns is what that same owner is
    later asked to settle. Any reading this scan admits and that classifier
    refuses is fed to a developer and then recorded nowhere: a refused entry
    is neither delivered nor blocking, so the surface's watermark does not
    move and the next tick hands the identical comment to a second developer,
    every tick, forever. One predicate is the only way two owners cannot come
    to disagree about a batch they both read.

    `_ADMITTED` is the whole of the test: refused, and admitted under a
    reason of OURS, are both answers a settlement declines to advance for.
    No retained ids are handed over on either surface, because the
    orchestrator posts no review and no inline comment -- the same empty set
    the settlement derives for them.
    """
    return [
        found for found in sorted(read, key=lambda seen: seen.id)
        if _delivery.classify_review_trust(found) == _ADMITTED
    ]


def _rescan_fixing_feedback(
    gh: GitHubClient, issue: Issue, pr, state,
) -> _models._FixingFeedback:
    """Rescan the four PR-feedback surfaces for comments past the in_review
    watermarks (NOT the `pending_fix_*` bookmarks -- those stay in pinned
    state as the reconstruction source for `_reconstruct_pending_fix_batch`).

    Each surface is kept as its own list, because the settlement that follows
    owes a different reader for each of them. The prompt order the record
    derives is issue-space (issue thread + PR conversation, in id order), then
    inline review comments, then review summaries.

    The two review surfaces are read through the delivery owner's own
    classifier (`_reviewed`), which is the classifier the settlement applies:
    a reading the scan admitted and the settlement refused would be quoted to
    a developer and recorded for nobody, and its watermark would hand it back
    on the next tick.

    The two IssueComment surfaces are read through the in_review owner that
    holds their cursors, and the pair of cursors is not the same on both. The
    thread answers to `pr_last_comment_id` AND to `last_action_comment_id`,
    because an implementing or validating resume that quoted a reply recorded
    it on the second field alone -- read past the PR-side cursor only, that
    answered reply would be re-fed into the `_build_pr_comment_followup`
    prompt whenever a manual relabel or a handoff walk left the field below
    it. The PR conversation answers to `pr_last_comment_id` and to nothing
    else: nothing that advances the issue-action boundary has read the pull
    request, so applying that boundary here would hide every PR comment
    numbered below the last issue reply a developer answered.

    The issue thread is read ONCE and the whole read is kept on the batch. The
    round owes that surface two more answers than the cut -- the conversation
    a retired session is re-grounded on, and the requirements fingerprint a
    report is stamped with -- and every one of them taken from a second read
    is taken minutes later: the comment that landed in between then reaches an
    agent, or is recorded as requirements somebody answered, while the
    watermarks settled here stop below it and hand it to a second developer on
    the next poll.
    """
    thread = list(issue.get_comments())
    return _models._FixingFeedback(
        issue_thread=_unclaimed(
            _in_review_surfaces._unread_issue_thread(
                gh, issue, state, comments=thread,
            ),
            state,
        ),
        pr_conversation=_unclaimed(
            _in_review_surfaces._unread_pr_conversation(gh, pr, state), state,
        ),
        review_comments=_reviewed(gh.pr_inline_comments_after(
            pr, state.get("pr_last_review_comment_id"),
        )),
        review_summaries=_reviewed(gh.pr_reviews_after(
            pr, state.get("pr_last_review_summary_id"),
        )),
        read=tuple(thread),
        # What the re-grounding conversation cut from that read may keep
        # whatever the author allowlist says: the ids this orchestrator wrote
        # down as it posted them, which is the only evidence a body is its own.
        retained=frozenset(_comments._orchestrator_ids(state)),
    )


def _fixing_debounce_open(
    feedback: _models._FixingFeedback, replay_batch,
) -> bool:
    """True while the quiet window is still open: hold the resume until no
    comment has landed for `IN_REVIEW_DEBOUNCE_SECONDS`.

    A newer comment arriving on a later tick is naturally picked up by the
    rescan, which extends the wait because the freshest timestamp controls
    the gate. Comments without a usable timestamp (older fakes, PyGithub
    edge cases) do not block the resume; in production `created_at` /
    `submitted_at` are always set. An accepted `/orchestrator continue`
    (`replay_batch` set) skips the wait entirely -- it is a deliberate
    operator signal, not chatter to debounce.
    """
    if replay_batch is not None:
        return False
    now = datetime.now(UTC)
    latest_ts: datetime | None = None
    for feedback_item in feedback.all_items:
        ts = _in_review_watermarks._comment_created_at(feedback_item)
        if ts is None:
            continue
        if latest_ts is None or ts > latest_ts:
            latest_ts = ts
    return (
        latest_ts is not None
        and (now - latest_ts).total_seconds() < config.IN_REVIEW_DEBOUNCE_SECONDS
    )


def _consumed_delivery(
    state, feedback: _models._FixingFeedback,
) -> _delivery.PromptDeliverySnapshot:
    """The record of exactly what this batch put in front of a developer.

    Built on the shared delivery owner rather than on a per-field maximum of
    this stage's own, so the pairs it derives are the ones any durable
    settlement -- a report transaction's recorded watermarks among them --
    carries verbatim, and the surface provenance the rescan kept survives into
    what is written.

    `issue_watermark_field` is what tells that owner which cursor this stage's
    issue-space reading answers to. Without it a batch carrying issue-thread
    replies and no PR comment would leave `pr_last_comment_id` behind, and the
    next tick would read those replies back as unread PR feedback.

    The recorded ids are the IssueComment ledger's, and they reach the two
    review surfaces as the empty set that owner derives for them -- which is
    what the scan hands its own classifier, so both sides read every review
    item under the same rule.

    The requirements revision is deliberately not recorded here: the resume
    fingerprints the very read this batch was cut from and stamps the report
    with it, and a second writer would settle a baseline this batch never
    measured.

    A caller that has to FREEZE these pairs rather than write them reads them
    off the same snapshot (`consumed_pairs`): a round that finished on a
    report may not record its feedback as answered until that report reaches
    the pull request, so the pairs travel on the report's own record and are
    applied by the write that settles it.
    """
    return _delivery.create_prompt_delivery_snapshot(
        issue_comments=feedback.issue_thread,
        pr_conversation_comments=feedback.pr_conversation,
        inline_review_comments=feedback.review_comments,
        review_summaries=feedback.review_summaries,
        max_chars=_UNBOUNDED_EXCERPT,
        retained_ids=frozenset(_comments._orchestrator_ids(state)),
        state=state,
        state_comment_id=state.comment_id,
        issue_watermark_field=_delivery.PINNED_PR_LAST_COMMENT_ID,
    )


def _read_by_an_owed_report(state, feedback: _models._FixingFeedback) -> bool:
    """Whether an owed report has already put this whole batch in front of a dev.

    The readers this stage would answer with are deliberately held back while
    a publication is outstanding, so "unread" stops meaning "nobody has seen
    it" for exactly as long as that report is owed. The record is what still
    knows: it carries the pairs the run that wrote it consumed, frozen before
    anything was published. A batch with nothing above them is the prompt that
    report ANSWERS, and resuming a developer over it spawns a second one on
    the identical text -- every poll, for as long as the push or the post
    keeps failing.

    Asked of the record rather than of the readers, and of the record's own
    pairs rather than of a re-derivation, because those pairs are what the
    settlement will apply when the publication finally lands: the question
    "has this been delivered" and the question "will this be recorded as
    delivered" have to have one answer.

    False where no record carries pairs. A debt held as a park flag alone has
    no watermarks to compare, and the roads that take it applied their
    consumption into the park's own write, so their readers HAVE moved and
    this batch is genuinely fresh. An empty group says the same thing: a run
    that consumed nothing answers no prompt.

    A record this issue CLAIMS and nothing can read is the opposite answer,
    and it is the one place here that fails closed. Read as an absence it
    would say this batch is unread while the pairs that would have proved
    otherwise are exactly what nobody can decode -- so the scan behind it pays
    a second developer to answer feedback the first one already answered. The
    roads that park such a record run ahead of this, so what this covers is
    the reader reached before one of them could.
    """
    recorded = (
        _delivery_state.read_delivered_report(state)
        or _record_state.read_pending_report(state)
    )
    if recorded is None:
        return (
            _delivery_state.carries_delivered_report(state)
            or _record_state.carries_pending_report(state)
        )
    if not recorded.watermarks:
        return False
    answered = PinnedState(
        comment_id=state.comment_id, state_data=dict(state.data),
    )
    _consumed.advance_consumed(answered, recorded.watermarks)
    return not _consumed_delivery(answered, feedback).consumed_pairs(answered)


def _settle_consumed_feedback(
    state, feedback: _models._FixingFeedback,
) -> None:
    """Record this batch as consumed by every reader that owns a piece of it.

    Forward only and idempotently: each field moves to the max id delivered on
    the surface that field answers for, and a field already past that stays
    where it is. The issue thread settles `last_action_comment_id` as well as
    the PR-side cursor, so a route change out of `fixing` does not pay a second
    developer to deliver a reply this stage already quoted; the PR
    conversation, the inline review comments and the review summaries settle
    their own in_review watermarks and nothing else, so feedback no prompt
    carried is left for the scan that owns it.

    Called on every outcome that counts the prompt as delivered AND owes no
    report for it -- the pushed fix, the ACK, and the park or failure alike --
    and before the disposition that may publish or park, so the durable write
    that disposition makes carries this settlement instead of leaving it to a
    write a crash can lose. A round that finished on a report outcome does not
    come through here: `reporting` freezes these same pairs onto the report
    transaction, and the write that completes the publication applies them.
    Consumed ids and nothing else, because a comment the dev never saw in its
    prompt would otherwise be silently swallowed on the pushed path (the next
    in_review tick would miss it) and on the park/failure path (the next fixing
    tick's `awaiting_human and not new_feedback` gate would drop it).
    """
    _delivery.settle_delivery(state, _consumed_delivery(state, feedback))
