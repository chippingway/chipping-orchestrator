# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pull request a post-publication verdict was taken over, read once.

Both roads out of an adjudication entered on the published side have to ask
the same question before they act, and neither can look it up: the entry the
gate froze names the pull request the work is already on and the head it was
standing on, so what a settlement or a split owes is a PROOF that those two
are still what they were rather than a search. The BRANCH that head is the tip
of is read with them, because the number and the branch are separate fields on
one pinned comment and a settlement pushes the branch it resolves for itself:
proved on the SHA alone, a pull request standing at the frozen head on some
other ref would be accepted, and the push would grow a branch that pull request
never carried while the handoff named it. The REPOSITORY that ref lives in is
read beside it and asked first, because forks carry this repository's ref names
over its commits -- so one agrees on both of the others while naming a branch
no push of this issue's has ever touched. A settlement publishes onto
that pull request; a `split` closes it over a supersession and hands the work
to
children. Both are irreversible on the remote, and both are wrong if somebody
moved or settled the publication while the adjudication was open.

So the reading lives here rather than on either of them. It is one owner
because it is one fact -- the state and the head of one pull request -- and
because a fetched pull request is LAZY: `get_pr` asks GitHub nothing, and the
requests that can fail are the attribute reads behind it. A caller guarding
only the lookup leaves those two to raise out of a road whose every other
refusal parks, and an exception on the way to a park is a park nobody takes.

The pull request those facts were read off travels back with them, so a caller
that has to ACT may act on the object it proved rather than on a second
lookup. A human can merge, push to, or reopen one between two round-trips, and
a proof spent on the first says nothing about what the second returns -- so
the window a caller cannot close is the write itself, never the fetch in front
of it.

The question a SETTLED split then keeps asking lives here too, and for the
same reason the reading does: it is one fact about one pull request, and three
owners need it. The transaction asks it in front of every step its own
supersession licenses; the activation walk asks it before every child it
releases; the reclamation asks it immediately before deleting the branch that
pull request points at. None of them may share an answer with the step in
front of it, so what is published is the ASK rather than a fact -- taken from
the record each time, which is why the split's retirement keeps the
publication group rather than dropping it with the measurement.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.github import comments as _github_comments
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration

log = logging.getLogger("orchestrator.workflow")

# What a pull request has to be for either road to act on it. A merged or
# closed one is a change a human settled while the adjudication was open, and
# neither publishing onto it nor closing it over a supersession is something
# this workflow may do behind that.
OPEN = "open"

# What a pull request this workflow closed itself reads as. Told apart from
# `merged` because the two mean opposite things to a caller holding a receipt:
# a close is what a supersession makes, and a merge is a human landing the
# very work the supersession says is being replaced.
CLOSED = "closed"


# Why a pull request this split superseded is no longer one anything may act
# behind. Spelled here rather than beside a caller because all three owners
# that ask -- the transaction, the umbrella, the reclamation -- put the same
# sentence in front of a human.
_REOPENED_PUBLICATION = (
    "PR #{number} is open again behind the supersession this split made"
)

_UNSUPERSEDED_PUBLICATION = (
    "PR #{number} is {state} rather than closed over that supersession"
)

_UNREADABLE_PUBLICATION = "PR #{number} could not be read"

_MOVED_PUBLICATION = (
    "PR #{number} was standing at `{frozen}` and stands at `{moved}` now"
)


@dataclass(frozen=True)
class _PublicationReading:
    """One pull request as this tick found it, or the refusal it got.

    Both facts together because both are requests, and a reading where either
    did not come back is one refusal rather than a state with a head missing
    from it.
    """

    state: str = ""
    head: str | None = None
    # The branch that head is the tip OF. The other half of naming a
    # publication: a pull request standing on the commit a verdict was reached
    # over says nothing about where a push would land unless it is open on the
    # branch that push names, and the two are separate fields on one pinned
    # comment. Read here because it comes off the same lazy object as the head
    # and a caller that fetched again for it would have a second request to
    # guard.
    head_branch: str | None = None
    # The repository that branch lives in, which is what makes the two above
    # identify anything at all: a fork carries this repository's ref names
    # over its commits, so one satisfies every other term here while pointing
    # at a branch no push of this issue's has ever touched.
    head_repo: str | None = None
    refused: bool = False
    # Whether the caller's own receipt is already on this pull request's
    # thread. Asked inside the same guarded read as the other two, because it
    # is the same lazy object and a caller that fetched again to look would
    # have a second request to guard -- and taken only where a caller names a
    # receipt to look for, since nothing else pays a comment listing for it.
    superseded: bool = False
    # The pull request these facts were read off, for a caller that has to ACT
    # on what it just proved. It travels with them because the alternative is
    # a second lookup, and a second lookup is a second pull request as far as
    # the proof goes: whatever the reading established was established about
    # THIS object, and closing a freshly fetched one instead spends the proof
    # on a change nobody looked at. None on a refusal, where there is nothing
    # to act on.
    pull_request: object | None = None


def _publication_undone(
    gh: GitHubClient, issue: Issue, generation: LateGeneration,
) -> str:
    """Why the close a split made is not on its pull request now, or "".

    Read off the record every time it is asked rather than from a value a
    caller captured, because the answer is exactly as old as the request
    behind it: a step licensed by an answer the step in front of it took is a
    step run on evidence a human had time to overtake. The record can carry it
    because the retirement keeps the publication group.

    "" for everything that never had one -- an umbrella the initial decomposer
    made, a split entered before publication, a damaged group -- and no
    request is spent on any of them.

    Three readings, and each is a different thing for a human to reconcile. An
    OPEN one was reopened behind the close, and releasing children or deleting
    the branch beside it is the outcome this whole road exists to prevent. A
    MERGED one is a human deciding the opposite of what the supersession
    claims. And a head that moved is the same refusal the close itself is
    proved against: what the snapshot holds is the frozen commit rather than
    whatever was pushed onto the branch since.

    A reading nothing could take is a refusal like any other and reads as one
    here: what the callers do with it is decline the step in front of them,
    which is the same answer they give a publication that really did move.

    No receipt is asked for, so no comment listing is paid for. What these
    callers need is the STATE -- closed, and closed over the head the verdict
    was taken on -- and the close being there has already answered the rest.
    """
    if not generation.publication.is_complete:
        return ""
    number = generation.publication.published_pr_number
    return _reading_undone(
        number,
        _read_publication(gh, issue, number),
        generation.publication.published_sha,
    )


def _reading_undone(
    number: int, reading: _PublicationReading, frozen: str,
) -> str:
    """Why one reading of that pull request is not the supersession, or "".

    A reading nothing could take is a refusal like any other and reads as one
    here: what the callers do with it is decline the step in front of them,
    which is the same answer they give a publication that really did move.
    """
    if reading.refused:
        return _UNREADABLE_PUBLICATION.format(number=number)
    if reading.state == OPEN:
        return _REOPENED_PUBLICATION.format(number=number)
    if reading.state != CLOSED:
        return _UNSUPERSEDED_PUBLICATION.format(
            number=number, state=reading.state,
        )
    head = _payloads.as_hex(reading.head, _formats.COMMIT_LENGTHS)
    if head == frozen:
        return ""
    return _MOVED_PUBLICATION.format(
        number=number, frozen=frozen, moved=head or "an unreadable head",
    )


def _release_undone(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> str:
    """The same question, for a caller holding the pinned comment.

    Which is what the activation walk holds: it is shared with parents that
    never entered the gate, so it asks the record rather than being told, and
    a parent with no publication on it answers without a request.
    """
    return _publication_undone(
        gh, issue, _late_state.read_late_generation(state),
    )


def _read_publication(
    gh: GitHubClient, issue: Issue, number: int, receipt: str = "",
) -> _PublicationReading:
    """The state and head of the publication a verdict was taken over.

    Both inside one refusal, for the reason the module says: the lookup asks
    GitHub nothing and the two attribute reads behind it are what talk. What
    comes back is a reading a caller may act on, or a refusal it must park on.

    `receipt` is a marker a caller has already stamped on this pull request if
    it acted on it before, and the answer rides the same refusal for the same
    reason. A caller that CLOSED the pull request itself and died before the
    work behind that close was finished cannot tell its own close from a
    human's by the state alone -- both read `closed` -- and the thread is
    where the difference is written.
    """
    try:
        return _publication_facts(gh, number, receipt)
    except Exception:
        log.exception(
            "issue=#%d could not read published PR #%d before acting on the "
            "verdict taken over it", issue.number, number,
        )
    return _PublicationReading(refused=True)


def _publication_facts(
    gh: GitHubClient, number: int, receipt: str,
) -> _PublicationReading:
    """The lookup and the lazy reads behind it, as one reading."""
    pull_request = gh.get_pr(number)
    head = getattr(pull_request, "head", None)
    return _PublicationReading(
        state=gh.pr_state(pull_request),
        head=getattr(head, "sha", None),
        head_branch=getattr(head, "ref", None),
        head_repo=getattr(getattr(head, "repo", None), "full_name", None),
        superseded=bool(receipt) and _carries_receipt(
            gh, pull_request, receipt,
        ),
        pull_request=pull_request,
    )


def _carries_receipt(gh: GitHubClient, pull_request, receipt: str) -> bool:
    """Whether a comment of OURS on this thread already carries `receipt`.

    Ours, because an HTML comment is invisible in the rendered thread and
    anybody could otherwise post the marker that tells this workflow it has
    already acted. Walked whole rather than from a watermark: nothing this
    mode keeps was moved past the notice, so a bounded scan could start above
    the very comment it is looking for.
    """
    return _github_comments.carries_own_marker(
        gh.pr_conversation_comments_after(pull_request, None),
        receipt,
        bot_login=getattr(gh, "_bot_login", None),
    )
