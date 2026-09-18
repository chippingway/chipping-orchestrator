# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pull request an implementation is published under, and whose work it says
it carries.

The title is chosen from the branch's own first commit subject, falling back to
a prefix inferred from recent base history, so the PR reads like the repository
it lands in rather than like the orchestrator. The body pairs the `Resolves #N`
that closes the issue on merge with the dev session that wrote the branch, and
with the agent's closing message where the run produced one -- capped, and cut
on a boundary that leaves the Markdown around it intact.

That closing message is written only where this issue neither owes a developer
report nor has one settled.
A report of its own is published as a comment with an identity, a revision and a
digest, and it says in as many words that it supersedes any agent message in the
description -- so a capped excerpt of the same run written here as well would be
a second, unmarked, unversioned copy of the report in a place nothing records or
rereads. Where the report is the authority, the description carries what only it
can: the closing reference and the attribution.

Nothing already on a description is ever removed on that account. A body written
before this record existed carries its agent message under an unmarked
`_Last agent message:_` heading, and nothing can tell where that message ends
and a human's own words begin -- so the tail stays where it is, historical, and
the report comment is what a reader is pointed at.

Nor is anything removed on the reuse's account. A pull request somebody else
described -- an operator, the `discussion` stage's plan, a human editing one this
stage already pushed onto -- gets the closing reference and the attribution put
ABOVE what it says, and what it says stays beneath them word for word, read
afresh by number so an edit landing after the lookup is the text judged and
kept. The one description never touched is one a report lives in: a developer
that verified one there recorded the digest of what it read, so even an edit
that keeps every word moves the location off it. Such a body is left exactly as
it stands until a report somewhere else frees it. And none is cut to make room:
a description the two lines would take past what GitHub accepts is held for a
human rather than shortened.

The attribution line is what holds the two halves of this owner together. The
body states it, and the verdict below reads it back off a pull request of unknown
provenance: `find_open_pr` promises only that something is open on the branch,
so what it hands over may be this stage's own crashed attempt, an operator's,
or the `discussion` stage's plan PR sitting on the very ref the dev commits went
to. Its presence beside this issue's closing reference is the one thing that
separates the first from the others, which is why the same sentence is
generated for both readings rather than written twice.

Reuse rather than a second open is also what makes the publication re-runnable:
a tick that died between `open_pr` and the relabel comes back to a pull request
already carrying the commit and adopts it, instead of 422-ing on a duplicate.
"""
from __future__ import annotations

import logging
from pathlib import Path

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.publication import titles as _titles
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    comments as _comments,
    report_delivery as _report_delivery,
    report_locations as _report_locations,
    report_settlement_state as _report_settlement,
)
from orchestrator.workflow.stages.implementing import (
    late_overflow as _overflow,
    models as _models,
    session_read as _session_read,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

# GitHub holds a pull request's description to the same 65,536 characters it
# holds a comment to, so a description near that ceiling cannot take the two
# lines this implementation needs above it without something being cut.
_TOO_LONG_PARK = (
    "{mentions} PR #{pr}'s description is too long to have this issue's "
    "closing reference and the developer session's attribution put above it: "
    "with them it would be {length} characters, past the {limit} GitHub "
    "accepts, and this orchestrator will not cut what anybody wrote there. The "
    "branch and the pull request stand as they are; the work is held rather "
    "than handed to review, because merging it would close nothing. Shorten "
    "the description, then reply and the orchestrator resumes the session -- "
    "the report it writes then goes out with the description named."
)


def _format_pr_agent_message(
    message: str, *, cap: int = _state._PR_BODY_AGENT_MESSAGE_CAP
) -> str:
    """Return the agent's final message ready to embed in a PR body.

    A message within `cap` is returned verbatim. A longer one is trimmed on the
    nearest paragraph -> line -> word boundary before `cap` and an explicit
    `_…(message truncated)_` marker is appended, so the PR body reads as
    intentionally clipped rather than severed mid-sentence. A dangling code
    fence in the trimmed region is closed first so the marker (and any following
    body) renders outside the half-open block instead of being swallowed by it.
    """
    if len(message) <= cap:
        return message
    head = message[:cap]
    # Prefer a paragraph break, then a line break, then a word boundary, so the
    # cut lands somewhere readable instead of mid-token.
    for sep in ("\n\n", "\n", " "):
        idx = head.rfind(sep)
        if idx > 0:
            head = head[:idx]
            break
    head = head.rstrip()
    # An odd count of ``` fences means the cut landed inside a fenced block;
    # close it so GitHub doesn't swallow the marker into the open code block.
    if head.count("```") % 2:
        head = f"{head}\n```"
    return f"{head}\n\n{_state._PR_BODY_TRUNCATION_MARKER}"


def _derive_pr_title(spec: _config_models.RepoSpec, issue: Issue, wt: Path) -> str:
    """PR title for a freshly opened dev PR.

    Prefers the first commit's conventional subject; when that carries no
    recognizable `<type>:` prefix, one is inferred from recent base-branch
    history (`_infer_subject_prefix`) and applied to the issue title.
    """
    first_subject = _titles._first_commit_subject(spec, wt)
    fallback_prefix = _titles._infer_subject_prefix(spec, wt, issue)
    return _titles._pr_title_from_commit_or_issue(
        issue, first_subject, fallback_prefix,
    )


def _dev_pr_attribution(state: _pinned_state.PinnedState) -> str:
    """Which dev session the branch on this PR was written by.

    Its own line because two owners need it: the body that states it, and the
    reuse below, which reads a PR of unknown provenance for it before adopting
    that PR as this implementation's.
    """
    _, dev_backend, _, dev_sid = _session_read._read_dev_session(state)
    session_id = dev_sid or "?"
    return f"Generated by orchestrator ({dev_backend} session `{session_id}`)."


def _build_pr_body(
    state: _pinned_state.PinnedState,
    issue: Issue,
    agent_result: AgentResult,
    preserved: str = "",
) -> str:
    """PR body: the `Resolves #N` line, the generating session's identity, and
    the (capped) final agent message when the run produced one and this issue
    owes no report of its own -- then, on a pull request somebody else
    described first, that description exactly as it stood.

    The two lines above the message are what the description alone can say: the
    reference that closes the issue on merge, and the session the reuse below
    reads back before it adopts a pull request somebody else opened.

    The message is the half a report replaces. An issue that owes one is going
    to have it published as a comment carrying its own identity, revision and
    digest, and saying that it supersedes any agent message here -- so writing a
    capped excerpt of the same run into the description too would leave two
    copies of one report, one of them unmarked and unversioned, in a place
    nothing rereads. An issue whose report has already SETTLED is the same
    case one step later, and it is the one a description named after the
    report went out is built in.
    """
    body_parts = [
        f"Resolves #{issue.number}",
        "",
        _dev_pr_attribution(state),
    ]
    if agent_result.last_message.strip() and not (
        _report_delivery.owes_a_report(state)
        or _report_settlement.carries_settled_record(state)
    ):
        body_parts += [
            "", "---", "_Last agent message:_", "",
            _format_pr_agent_message(agent_result.last_message),
        ]
    if preserved.strip():
        body_parts += ["", "---", _state._PR_BODY_EARLIER_HEADING, "", preserved]
    return "\n".join(body_parts)


def _reuse_or_open_pr(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    work: _models._PRWork,
):
    """Return the PR for `branch`, reusing an open one or opening a new one.

    Recovers gracefully if a previous tick crashed between `open_pr` and the
    relabel: an existing open PR is reused instead of 422-ing on a duplicate.
    Opening a new PR posts the ":sparkles: PR opened" comment and emits the
    `pr_opened` event; reuse only logs.

    `work.delivered_pr` is the other road, and on it nothing may be opened at
    all: the gate let this candidate past BECAUSE that pull request is already
    standing on it, so the push moved nothing and all that is left is the
    bookkeeping behind a publication that has happened. Looked up by branch
    like any other, a pull request somebody closed between the gate's proof
    and here answers None and a second one is opened over the same work.
    Pinned, the same window answers None to the CALLER, which holds the tick
    and leaves the record exactly as it stands.

    What the pull request found on either road SAYS is not decided here.
    Whether its description closes this issue and names this session is
    `_names_the_implementation`'s, asked by the caller of a description read
    afresh -- once before the report is bound, and once more after it settles,
    since settling a report elsewhere is what frees a description a report of
    this issue's was verified on.
    """
    if work.delivered_pr:
        return _delivered_pull_request(gh, issue, work)
    pr = gh.find_open_pr(branch=work.branch, base=spec.base_branch)
    if pr is not None:
        log.info(
            "issue=#%s reusing existing PR #%d for %s",
            issue.number, pr.number, work.branch,
        )
        return pr
    pr = gh.open_pr(
        branch=work.branch, base=spec.base_branch,
        title=_derive_pr_title(spec, issue, work.worktree),
        body=_build_pr_body(state, issue, work.agent_result),
    )
    _comments._post_issue_comment(gh, issue, state, f":sparkles: PR opened: #{pr.number}")
    gh.emit_event(
        "pr_opened",
        issue_number=issue.number,
        stage=_state._IMPLEMENTING_STAGE,
        pr_number=pr.number,
        branch=work.branch,
        sha=getattr(pr.head, "sha", None) or None,
        retry_count=state.get(_state._RETRY_COUNT),
    )
    return pr


def _delivered_pull_request(
    gh: _client.GitHubClient,
    issue: Issue,
    work: _models._PRWork,
):
    """The pull request this publication is finishing up, or None if it moved.

    Read by NUMBER, which is the one thing a lookup by branch cannot promise:
    the proof that admitted the candidate was about a particular pull request
    standing on a particular commit, and a branch lookup a moment later is a
    different question with a different answer.

    Re-read rather than trusted, and re-read WHOLE: the proof and this
    bookkeeping are two moments, and between them lie the barrier, the push
    and whatever else the tick spent. What is written past this line is a
    receipt naming this commit and a relabel handing a reviewer this pull
    request, so every term the proof established has to still hold together --
    open, in this repository, on the branch the push named, and standing on
    the commit it sent. A pull request somebody closed has nothing left for a
    relabel to hand on; one somebody MOVED leaves the receipt naming work the
    branch no longer carries and sends a reviewer to a head this issue never
    published.

    A pull request this host could not read answers None on the same footing,
    since what the caller does with None is hold -- the commit stays where it
    is, the record stays as it stands, and the next poll asks again. Asked
    through the size gate's own publication reader, which is where the
    fail-closed shape of that read lives: a fetched pull request is LAZY, so
    the lookup itself asks GitHub nothing and the request that can fail is the
    attribute access that reader already wraps.

    ONE reading, and the object it came back with is the object handed on. A
    check followed by a fetch of the same number is two moments: a pull
    request proved open by the first can be closed by the time the second
    answers, and what the relabel would then hand a reviewer is a publication
    nothing here checked.

    Opening one is never the answer here, whatever the disagreement: the gate
    let this candidate past BECAUSE that pull request already carries it, so a
    second one would be opened over work the first may still have.
    """
    delivered = _overflow._PublicationReading.standing_exactly_on(
        gh, work.delivered_pr, work.branch, work.delivered_sha,
    )
    if delivered is None:
        log.warning(
            "issue=#%s cannot read pull request #%d as open on %s and "
            "standing on %s for the bookkeeping its own push already "
            "delivered; holding rather than recording a publication nothing "
            "re-read",
            issue.number, work.delivered_pr, work.branch, work.delivered_sha,
        )
        return None
    log.info(
        "issue=#%s finishing the bookkeeping for PR #%d, which already "
        "carries %s",
        issue.number, work.delivered_pr, work.branch,
    )
    return delivered


def _names_the_implementation(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    pr,
) -> bool | None:
    """Whether the pull request's description closes this issue and names it.

    What `find_open_pr` returns is only known to be open on this branch. The
    sharpest case is the `discussion` stage's plan PR: an issue relabeled here
    arrives with it open on the very branch the dev commits go to, so a silent
    reuse leaves a body saying the branch is one Markdown file and changes
    nothing else -- a claim the push just made false -- under the decomposer's
    session rather than the developer's, and with no `Resolves #N` to close
    the issue when it merges. An operator's own PR on the branch is the same
    problem with different words, and so is one of this stage's own that a
    human has since re-described.

    What decides is the description as it stands NOW, read again by number.
    The body on the object in hand is as old as whatever fetched it: a human
    editing in between could have taken the closing reference or the
    attribution out of a body that had both, and a verdict read off that
    snapshot would hand review a pull request that closes nothing. GitHub
    offers no conditional write, so the one request between that read and the
    edit is the window left.

    True is a description that already closes this issue and names this
    session -- left alone, with everything a human added -- or one that did
    not and has just had the closing reference and the attribution put ABOVE
    it, every word it said kept beneath them. False is the one description
    never edited whatever it says: the one this issue's own report claims as
    its location, since even an edit that keeps every word moves it off the
    digest it was verified at. None holds the tick: a description nobody could
    read, and one too long to carry the two lines without cutting what
    somebody wrote, which is a repair the issue parks for.
    """
    try:
        current = gh.get_pr(pr.number)
    except Exception:
        log.exception(
            "issue=#%s could not re-read PR #%d's description; holding rather "
            "than deciding on one nobody read", issue.number, pr.number,
        )
        return None
    if _report_locations.describes_the_issue(
        current, issue.number, _dev_pr_attribution(state),
    ):
        return True
    if _report_locations.claims_the_description(state, pr.number):
        log.warning(
            "issue=#%s is not editing PR #%d's body: a developer report of this "
            "issue's is published there, and any edit would move it",
            issue.number, pr.number,
        )
        return False
    described = getattr(current, "body", None)
    named = _build_pr_body(
        state, issue, agent_result,
        described if isinstance(described, str) else "",
    )
    if len(named) > _pinned_state.MAX_PINNED_BODY:
        _report_delivery.parks_an_undeliverable_report(
            gh, issue, state, _TOO_LONG_PARK.format(
                mentions=config.HITL_MENTIONS, pr=pr.number,
                length=len(named), limit=_pinned_state.MAX_PINNED_BODY,
            ),
        )
        return None
    log.info(
        "issue=#%s naming this implementation above PR #%d's description",
        issue.number, pr.number,
    )
    gh.edit_pr_body(pr, named)
    return True
