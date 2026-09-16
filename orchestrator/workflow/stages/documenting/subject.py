# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pull-request reference a docs commit's subject is amended to end in.

A rebase merge copies the docs commit onto the base as it was published, so
under `PR_REF_IN_SUBJECT` its subject is amended to end in ` (#N)` before
`publication` enters the size gate. The amendment is a NEW commit, which is
why it comes first: the gate measures the candidate it is handed, leaves that
id as a hold's receipt, and pushes it by id, and the stamp records it as
documented -- amended after any of those, each would name a commit the branch
no longer carries.

The amendment is bound to the commit this pass read, never to HEAD. Its
message is read off that commit by id, its replacement is built from that
commit, and HEAD is moved onto the replacement only if HEAD is still that
commit -- so a checkout something committed on after the pass read its head
refuses, rather than having the newer commit rewritten and handed to a gate
that would accept it for being the commit it was named. HEAD is then read back
before anything else runs, and the replacement is handed on only where HEAD is
standing on it: the id is still the one git created, and the read proves the
checkout the gate goes on to prove is that commit rather than whatever landed
on top of it after the move.

It is an edit of the subject's own text and nothing else. The author, the
tree, and every other byte of the message -- the subject line's ending
included -- stay the commit's own, only the subject and the committer change,
and no commit lands beside it. A subject already carrying the reference is
published as the commit it already is, which keeps a recovered commit and a
retried push from moving again or carrying the number twice. A read, a
replacement, a move, or a HEAD that does not read back as the replacement
parks rather than publishing the subject without it.
"""
from __future__ import annotations

import logging

from orchestrator import config
from orchestrator.git.publication import (
    commits as _publication_commits,
    pr_references as _pr_references,
)
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.workflow.stages.documenting import (
    models as _models,
    parks as _parks,
)

log = logging.getLogger("orchestrator.workflow")


# What a docs commit whose subject could not be given its pull request's
# reference parks as. Nothing has been published by then, so the retry that
# republishes it amends it first like any other.
_SUBJECT_AMEND_FAILED = "subject_amend_failed"

# The byte an editor writing CR LF line endings leaves at the end of a line.
_CARRIAGE_RETURN = "\r"


def _referenced_docs_commit(
    ctx: _models._DocumentingContext, wt, after_sha: str,
) -> str | None:
    """The docs commit to publish, its subject ending in its PR's reference.

    `after_sha` comes back untouched with the switch off -- no message read --
    and wherever its subject already ends in the reference: a commit an earlier
    tick amended and never pushed, or the retry of a push that failed,
    publishes the commit it already is rather than moving it again. Handed on
    as it is, it is still what the gate proves the checkout against, so a
    checkout that moved refuses there.

    `SQUASH_ON_APPROVAL` is not asked. It keeps the developer's history intact,
    and this is the commit the orchestrator publishes whichever way it is set.

    Returns None where the issue was parked instead. None of those readings may
    fall through to publishing the commit as it stands, which would put a
    subject without the reference on the pull request.
    """
    if not config.PR_REF_IN_SUBJECT:
        return after_sha
    message = _publication_commits._commit_message(wt, after_sha)
    if message is None:
        _park_unreferenced(ctx, "its message could not be read")
        return None
    referenced = _message_with_reference(message, int(ctx.pr_number))
    if referenced == message:
        return after_sha
    return _amended_docs_commit(ctx, wt, after_sha, referenced)


def _message_with_reference(message: str, pr_number: int) -> str:
    """`message` with its subject ending in the reference, all else as written.

    Only the subject's own text is handed to the formatter. The ending its line
    was written with -- a bare line feed, or the carriage return and line feed
    an editor writing CR LF leaves -- and every character after it go back
    exactly as they were, so a message already carrying the reference comes
    back equal to itself and a CR LF body is never normalized on its way into
    the replacement.
    """
    line, separator, rest = message.partition("\n")
    subject = line.removesuffix(_CARRIAGE_RETURN)
    ending = line[len(subject):]
    return "".join((
        _pr_references._subject_with_pr_reference(subject, pr_number),
        ending,
        separator,
        rest,
    ))


def _amended_docs_commit(
    ctx: _models._DocumentingContext, wt, after_sha: str, message: str,
) -> str | None:
    """Replace `after_sha` with a commit carrying `message`, or park.

    The replacement's own id is what comes back, because the move onto it is
    what proved HEAD was still `after_sha`. HEAD read back is asked only whether
    it is standing on that id: a checkout something committed on after the
    move is not the replacement, and handing the gate the id HEAD reads instead
    would carry the race the move closed straight to it.
    """
    amended = _publication_commits._amend_commit_message(
        wt, after_sha, message,
    )
    if not amended.sha:
        log.error(
            "issue=#%s could not give docs commit %s its reference: %s",
            ctx.issue.number, after_sha, amended.error,
        )
        _park_unreferenced(ctx, (
            f"the checkout moved off `{after_sha}` before its replacement "
            "landed, so nothing was amended"
            if amended.moved else "git could not create its replacement"
        ))
        return None
    standing = _verification_probes._head_sha(wt)
    if standing != amended.sha:
        log.error(
            "issue=#%s checkout stands on %s rather than %s, the replacement "
            "of docs commit %s",
            ctx.issue.number, standing or "an unreadable head", amended.sha,
            after_sha,
        )
        _park_unreferenced(
            ctx, f"HEAD did not read back as its replacement `{amended.sha}`",
        )
        return None
    return amended.sha


def _park_unreferenced(
    ctx: _models._DocumentingContext, failure: str,
) -> None:
    """Park a docs commit whose subject could not be given its reference.

    Nothing has been measured or pushed, so the resumed pass republishes the
    commit through the amendment and the gate once a human has replied.
    """
    _parks._park_documenting(
        ctx,
        f"{config.HITL_MENTIONS} the docs commit's subject could not be given "
        f"this pull request's reference (#{ctx.pr_number}): {failure}. Nothing "
        "was pushed; see orchestrator logs.",
        _SUBJECT_AMEND_FAILED,
    )
