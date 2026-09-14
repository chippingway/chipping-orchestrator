# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Frozen content fingerprints, trusted authorization replies, and reconciliation results.

Title/body and conversation drift remain separate readings. Their shared
watermark identifies which replies a settlement can consume, while the
optional authorization names the exact candidate and comment that supplied it.
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.workflow.stages.decomposition import late_result_models as _late_result_models


@dataclass(frozen=True)
class _LateFingerprint:
    """What the requirements behind a frozen candidate currently hash to.

    Two digests and the watermark one of them covers from, because the two
    questions a late generation asks about content are different questions. A
    title or body edit changes what the candidate is supposed to BE. Trusted
    conversation arriving after the baseline is a human answering, and which
    comments are new is a thing only an identifier can say -- so the watermark
    travels with the digest rather than being re-derived from it.

    The watermark is a ratchet the reader maintains rather than a maximum
    recomputed from the thread: a comment a human deleted must not put it back
    down and let already-consumed conversation read as fresh guidance.
    """

    title_body_hash: str
    comment_hash: str
    comment_watermark_id: int | None = None


@dataclass(frozen=True)
class _LateAuthorization:
    """One operator command authorizing an oversized candidate to publish.

    The commit as the human WROTE it rather than one this domain has vouched
    for: what a malformed argument earns is an answer on the thread, and a
    reader handed nothing at all could not tell that request from a line
    nobody typed.

    The comment is carried beside it because it is half of what the durable
    record is: a bypass of the size gate is licensed by one gesture at one
    address anybody can go and read, so what is recorded is which comment was
    acted on rather than a copy of a judgement about its author.
    """

    candidate_sha: str
    comment_id: int


@dataclass(frozen=True)
class _LateContentSignal:
    """What the human's content says about a candidate under adjudication.

    `guidance` is the trusted comments past the watermark that carry something
    to act on, in thread order, so the developer resume quotes what a human
    actually wrote. A bare `/orchestrator continue` is deliberately not one of
    them -- it is an operator control with no answer in it -- which is why it
    is reported separately rather than as one more comment.

    Untrusted authors, bots, and the orchestrator's own comments are not here
    at all: they are filtered out where the thread is read, so nothing an
    outsider posts becomes guidance, moves the watermark, or shifts a digest.

    `authorization` is the operator command that publishes an oversized
    candidate as it stands, reported apart from the guidance for the same
    reason the bare continue is: it is a control rather than a requirement,
    and handing it to a developer would answer a question about scope with a
    commit id. The last one a batch carries is the one reported -- a human who
    wrote it twice meant the second -- and only the whole comment is ever one.

    `baselined` is what keeps "nothing to compare against" apart from "the
    requirements moved". A generation whose baseline has still to be taken
    reports both drift flags -- an absent digest equals nothing -- and reading
    that as a scope edit would park the very first tick of every late
    adjudication.
    """

    fingerprint: _LateFingerprint
    baselined: bool = False
    title_body_drifted: bool = False
    conversation_drifted: bool = False
    guidance: tuple = ()
    bare_continue: bool = False
    authorization: _LateAuthorization | None = None

    @property
    def drifted(self) -> bool:
        """Whether the requirements themselves moved under the candidate.

        Either fingerprint answers it. A title or body edit is the obvious
        one; a counted comment edited or deleted after the fact is the same
        event with no new comment to read it out of, so it is answered the
        same way rather than being lost.
        """
        return self.title_body_drifted or self.conversation_drifted


@dataclass(frozen=True)
class _LateContentSettlement:
    """What reconciling the human's content did with this tick.

    A `disposition` of None is the only answer that lets adjudication carry
    on; every other one is the whole of what the tick did and the coordinator
    returns it. `persisted` says whether this owner already wrote what it
    staged, so a caller holding a staged retirement of its own knows whether
    it still owes a write.
    """

    disposition: _late_result_models._LateDisposition | None = None
    persisted: bool = False
