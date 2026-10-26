# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A finished docs pass completed straight into `in_review`, its final head verified and recorded apart.

Documenting is the last automated delivery stage, so every pass that finishes
ends here -- one that published a docs commit (`_completes_published`) and one
that changed nothing (`_completes_unchanged`) alike -- and none of it is a
review: the approved review subject, the settled developer report and the
commit it was written about, the approval's evidence claim, and `review_round`
stay exactly as the approval left them. No report debt is recorded, no
evidence is retired, and no reviewer or report refresh is asked for.

What the pass completed on is verified by this stage instead, and recorded
beside the approval as its final-documentation completion
(`final_verification`, `docs_final_provenance`): the head the pass was
entered on -- the lease the size gate recorded beside the docs receipt
(`docs_settled_lease`), which is the approved commit or the head its squash
published -- and the head it completed on. A published docs commit is
verified by a run of exactly that commit under the configured
`VERIFY_COMMANDS`, minted as an orchestrator-executed transaction the
dispatcher's reconciliation publishes and settles, or under an empty
configuration by nothing, recorded as no evidence that anything passed. An
unchanged head is verified by the evidence the approval rests on, which
`retention` has just proved still answers for it, named as it stands.

The completion lands in the one write every pass lands through
(`handoff._completes`), owning the completion record and a run's transaction
beside the stamp and decided as well on every record that evidence is bound
through, and the relabel to `in_review` goes behind that write alone. The
ready ping there proves the completion whole before it announces the head
(`stages/in_review/completion.py`).

A completion that cannot be recorded never pretends otherwise:

- A run of the configured commands that did not pass on the docs commit
  parks with the failing command and its output, the receipt and its lease
  left standing, so nothing is offered for merge and the base refresh holds
  the branch still; so does a run that passed and still binds nothing -- an
  output no verification artifact can carry -- since a completion recorded
  without it would leave the ping nothing to prove, and the receipt it
  consumes nothing to verify from again. A bare `/orchestrator continue`
  answers either (`_reruns_the_pass`): the docs pass resumes over that commit
  with the failure on the thread it is handed, and what it leaves is verified
  again -- a fix it commits over the head the pass was first entered on, and
  a `DOCS: NO_CHANGE` as the commit already published.
- A run of another head or configuration, and a completion the comment has no
  room for, hold: what the tick staged lands alone, the receipt stays, and
  the next tick verifies again.
- A docs receipt with no readable lease names no head the pass was entered
  on, so nothing is written, announced, or relabelled over it.
- A `paused` or `backlog` label applied while the verification ran is
  honored before anything acts on its result: nothing is written, announced,
  or relabelled, and the receipt stands for the tick after the label comes
  off, which verifies the commit again and completes it.
- A pass with nothing a completion could follow or rest on -- no approval
  recorded in the current format, no settled report to bind a run to, so no
  run is made -- is handed on with its stamp alone, so the ping there rests on
  the ordinary readiness proof, which never passes over evidence of another
  head.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    final_docs_records as _final_docs,
    guards as _guards,
    report_commits as _commits,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads
from orchestrator.workflow.stages.documenting import (
    final_verification as _final_verification,
    handoff as _handoff,
    models as _models,
    parks as _parks,
    retention as _retention,
    state as _state,
)
from orchestrator.workflow.stages.validating import state as _validating_state, verify as _verify
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_ROUTE = _final_verification.FinalRoute

# The verdict a pass that published a docs commit is stamped with.
_UPDATED = "updated"

# The completion of a pass that published a docs commit, recording how its
# head is verified: the completion every pass lands, owning the completion
# record and a run's transaction with the history and revision floor it moves,
# and decided as well on every record that evidence is bound through.
_PUBLISHED = _handoff._COMPLETION.owning(*_final_verification.OWNED).deciding_on(
    *_final_verification.VERIFIED.decided_on,
)

# The completion of a pass that changed nothing over evidence proved to still
# answer for its head, recording that evidence as the one it rests on.
_UNCHANGED = _retention.UNCHANGED.owning(*_final_verification.OWNED)

# What a published pass held short of its completion lands: nothing of its
# own, only what the tick staged, decided on what the completion would be.
_HELD = _commits.ReportWrite(owned=frozenset(), decided_on=_PUBLISHED.decided_on)

# The reason a park over a docs commit whose run passed and binds nothing is
# filed under, and every reason a park over a docs commit's own run is: those
# the approval gate files a failed run under, which name the failure the same
# way, and that one.
_UNRECORDED_RUN = "verify_unrecorded"

_FAILED_RUN_PARKS = frozenset((*_validating_state._VERIFY_STATUS_TO_REASON.values(), _UNRECORDED_RUN))

_UNRECORDED_RUN_FAILURE = (
    "the configured verification commands passed on it, but their run could not be recorded as this "
    "orchestrator's evidence of it -- its output does not fit a verification artifact -- so the pull request "
    "is not handed off to in_review."
)

# What the pull request is told of a published docs commit's verification.
_VERIFIED_NOTICE = (
    "{notice}\n\nThe docs commit `{commit}` {verified}. The approved review and its developer report stand as "
    "they were written, and the pull request goes on to `in_review`."
)

_FAILED_RUN_NOTICE = (
    "{mentions} the docs commit `{commit}` is on this pull request, and {failure}\n\n"
    "Reply with exactly `/orchestrator continue` to resume the docs pass over this commit; whatever it leaves is "
    "verified again before anything is offered for merge."
)

_VERIFIED = MappingProxyType({
    _final_docs.FinalVerification.EXECUTED: (
        "passed the configured verification commands, run on it by this orchestrator"
    ),
    _final_docs.FinalVerification.UNCONFIGURED: (
        "ran no verification, since no `VERIFY_COMMANDS` are configured"
    ),
})


def _completes_published(ctx: _models._DocumentingContext, checked_sha: str, notice: str) -> None:
    """Verify the docs commit `checked_sha` a pass published, record its completion, and move the issue to `in_review`.

    `notice` is what the pull request is told about the publication; the
    verification is said beneath it. The head the pass was entered on is the
    docs receipt's lease (`_entry_head`); a receipt with none readable
    refuses the whole completion, the record left for a human to repair.
    Writes pinned state otherwise; the caller returns unconditionally.
    """
    entry_head = _entry_head(ctx, checked_sha)
    if not entry_head:
        return
    outcome = _final_verification.verifies_final_head(ctx, entry_head, checked_sha)
    if _guards._paused_during_agent_run(ctx.gh, ctx.issue):
        # The run is long enough for an operator to apply `paused` or
        # `backlog`, which nothing past it may work past: what it staged is
        # dropped unwritten, and the receipt the gate already landed is what
        # the first tick after the label comes off completes the pass from.
        ctx.state.withheld = True
        return
    unrecorded_run = outcome.route is _ROUTE.UNBOUND and outcome.run is not None
    if outcome.route is _ROUTE.FAILED or unrecorded_run:
        _parks_the_run(ctx, checked_sha, outcome)
        return
    if outcome.route not in {_ROUTE.RECORDED, _ROUTE.UNBOUND}:
        _holds(ctx, checked_sha, outcome.route)
        return
    write = _PUBLISHED
    if outcome.final is None:
        write = _handoff._COMPLETION
        log.warning(
            "issue=#%d nothing a final-documentation completion could follow or rest on is recorded for the docs "
            "commit %s; handing it to `%s` on its stamp alone", ctx.issue.number, checked_sha, WorkflowLabel.IN_REVIEW,
        )
    else:
        notice = _VERIFIED_NOTICE.format(
            notice=notice, commit=checked_sha, verified=_VERIFIED[outcome.final.verification],
        )
    _handoff._stamp_docs_verdict(ctx.state, checked_sha, _UPDATED)
    _handoff._completes(ctx, write, notice, WorkflowLabel.IN_REVIEW)


def _completes_unchanged(ctx: _models._DocumentingContext, checked_sha: str, notice: str) -> None:
    """Record the completion of a pass that changed nothing at `checked_sha`, and hand it to `in_review`.

    Asked only behind the proof that the evidence the approval rests on still
    answers for `checked_sha` (`retention._retains`), so that evidence is
    what the completion names, retained as it stands. One the comment has no
    room for holds through the proof's own checkpoint; one with nothing to
    follow or rest on hands off on the stamp alone. Writes pinned state.
    """
    outcome = _final_verification.verifies_final_head(ctx, checked_sha, checked_sha)
    if outcome.route is _ROUTE.UNRECORDED:
        _retention._holds(ctx, checked_sha, "the pinned comment has no room for the final-documentation completion")
        return
    write = _retention.UNCHANGED if outcome.final is None else _UNCHANGED
    _handoff._hand_off_to_in_review(ctx, checked_sha, notice, write)


def _entry_head(ctx: _models._DocumentingContext, checked_sha: str) -> str | None:
    """The head the pass that published `checked_sha` was entered on, or None with the tick withheld.

    The size gate writes the docs receipt and its lease in one write, and the
    stamp drops them together, so a receipt naming `checked_sha` with no
    whole commit id beside it -- missing, `null`, or no commit -- is a record
    something edited, and so is a receipt naming another commit: neither says
    which head the pass was entered on, and nothing is read off anything else
    in its place.
    """
    state = ctx.state
    lease = _payloads.as_hex(state.get(_state._SETTLED_DOCS_LEASE), _formats.COMMIT_LENGTHS)
    if state.get(_state._SETTLED_DOCS_SHA) == checked_sha and lease:
        return lease
    state.withheld = True
    log.error(
        "issue=#%d the docs receipt for %s carries no readable `%s`, so the head the pass was entered on is "
        "unknown; holding its completion with the record left as it stands for a human to repair",
        ctx.issue.number, checked_sha, _state._SETTLED_DOCS_LEASE,
    )
    return None


def _parks_the_run(
    ctx: _models._DocumentingContext, checked_sha: str, outcome: _final_verification.FinalOutcome,
) -> None:
    """Park a docs commit whose run of the configured commands did not pass, or passed and binds nothing.

    A failed run is worded as the approval's own verify gate words one
    (`validating/verify._verify_failure_park`), naming the command and its
    output, under the reason it would carry; a run that passed and binds
    nothing is said as that (`verify_unrecorded`). The receipt and its lease
    stay, so the commit is still the pass's to complete: nothing reaches
    `in_review`, the base refresh keeps the branch still, and the bare
    continue the notice asks for resumes the docs pass over this commit
    (`_reruns_the_pass`), whatever it leaves verified again. Writes pinned
    state.
    """
    reason, message = _UNRECORDED_RUN, _UNRECORDED_RUN_FAILURE
    if outcome.route is _ROUTE.FAILED:
        reason, message = _verify._verify_failure_park(outcome.run)
    _parks._park_documenting(ctx, _FAILED_RUN_NOTICE.format(
        mentions=config.HITL_MENTIONS, commit=checked_sha, failure=message,
    ), reason)


def _reruns_the_pass(state: PinnedState) -> bool:
    """Whether the issue is parked over a docs commit its own run did not pass or record, for a continue to rerun it.

    Asked of the reply that answers the park: the settled-commit road leaves
    the commit to the docs pass it resumes, and the bare continue is retried
    rather than refused, since that pass is what the park waits on.
    """
    parked = bool(state.get(_state._AWAITING_HUMAN))
    return parked and state.get(_state._PARK_REASON) in _FAILED_RUN_PARKS


def _holds(ctx: _models._DocumentingContext, checked_sha: str, route: _final_verification.FinalRoute) -> None:
    """Hold the completion of `checked_sha` for `route`: what the tick staged lands alone, the receipt standing."""
    log.info(
        "issue=#%d holds the completion of its docs commit %s: verifying it came to %s; announcing and "
        "relabelling nothing, and leaving the receipt for the next tick", ctx.issue.number, checked_sha, route.value,
    )
    commit = _commits.ReportCommit(ctx.gh, ctx.issue, ctx.state)
    _handoff._stops(ctx, commit.lands(ctx.state, _HELD), "relabelling")
