# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read authorization command text, comment identities, and attributed stage replies.

Only the whole-comment command supplies a candidate. The recorded comment
ledger distinguishes stage prose while the watermark tracks all seen ids.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    messages as _messages,
)
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
)

# The attribute a comment's own address is read off, spelled once because
# every reading here asks for it: which reply was acted on, how far the thread
# was looked at, and which comments this process posted itself.
_COMMENT_ID = "id"


def _furthest_read(examined: list, at_least: int) -> int:
    """How far this reading of the thread actually got.

    Every comment the fetch returned counts, not just the ones that survived
    the trust and authorship filters: what a watermark records is what has
    been LOOKED at, and a filtered-out comment has been. Left out, an
    outsider's reply or a sentence of ours would be handed to the next poll as
    something nobody has read yet.

    Never short of the reply being acted on, which is the floor a fetch that
    answered with ids nothing could read still has to clear.
    """
    read = [at_least]
    for seen in examined:
        identified = _payloads.as_identity(getattr(seen, _COMMENT_ID, 0))
        if identified is not None:
            read.append(identified)
    return max(read)


def _ours(reply, state: PinnedState) -> bool:
    """Whether the orchestrator itself POSTED this reply, by its recorded id.

    Dropped before anything here reads a thread, because nothing this process
    posts is ever somebody's decision -- and a park notice spells the command
    out ready to copy, so our own sentences are exactly the comments a reader
    matching on that syntax would otherwise mistake for one.

    Which makes the standard of proof the whole question, because dropping a
    comment here is not a neutral act. The reading behind this takes the LAST
    fresh reply, so a comment dropped is a comment whose author never spoke:
    an operator who authorizes a candidate and then retracts it would have the
    retraction removed and the authorization selected, and the candidate would
    publish on consent that had been withdrawn. Over-filtering is how this
    park publishes something nobody agreed to.

    So the ledger of ids `_post_issue_comment` records is the whole of the
    evidence. It is a fact about what this process DID, and nothing a
    commenter writes can put itself into it.

    Neither of the other two signals may stand in for it, and both are
    refused rather than accepted as a weaker second best. The marker is plain
    text in a public thread that anybody may paste, or quote off a comment of
    ours that carries one. And the author login is the shared-PAT hazard this
    repository already names where that ledger is defined: the token belongs
    to a human, so a reviewer posting from the same account matches it
    exactly, and a retraction they wrote under a quoted marker would be read
    as the orchestrator talking to itself. The two together are no better,
    since the human who shares the login is the one whose consent this park
    exists to collect.

    Anything the ledger cannot vouch for is somebody's word and stays in the
    reading -- including a comment of ours whose id has been evicted past the
    ledger's bound. What that costs at worst is one of our own sentences
    standing as the last reply, which is not the command, so the park goes on
    standing and waits. That is the safe direction for a question only a human
    can answer, and it is the one this owner fails in.

    A sentence this stage said and lost the id write for is put INTO that
    ledger before this reading runs, by `late_authorship`, so nothing here has
    to read a body to recognize one. That repair is the only road that adds to
    the ledger without having posted the comment itself, and what it rests on
    is spelled where it lives.
    """
    identified = _payloads.as_identity(getattr(reply, _COMMENT_ID, 0))
    if identified is None:
        return False
    return identified in _comments._orchestrator_ids(state)


def _is_the_command(reply) -> bool:
    """Whether this reply is the whole command, whatever it went on to say.

    Asked apart from what the command NAMES, because the two decide different
    things. A comment that is not the command is guidance and is left for the
    road that feeds it to a developer. One that IS the command is a gesture
    this park owes an answer to -- and that holds just as much when nobody
    could act on it, since a human who typed an abbreviation is owed the
    sentence saying so rather than a park that goes on standing in silence.

    A reply with no id is neither: a record made from it would name a comment
    nothing can locate, which is the one thing an authorization may not be.
    """
    return _messages._authorized_oversized_candidate(reply) is not None


def _names(reply) -> str:
    """The whole object id one reply authorizes, or "" if it authorizes none.

    A comment that is not the whole command answers "", and so does one whose
    argument is not a whole git object id: nothing here abbreviates, so an
    abbreviation is the mismatch it is rather than a prefix to compare -- and
    the mismatch is what earns the sentence, since "" is never a candidate.
    """
    written = _messages._authorized_oversized_candidate(reply)
    if written is None:
        return ""
    return _payloads.as_hex(written, _formats.COMMIT_LENGTHS) or ""
