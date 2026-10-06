# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A change request's reviewer-feedback post: its words, the post a later tick finds, and the post as a replay shows it.

A change request's handoff (`review_handoffs`) posts the reviewer's feedback on
the pull request (`requested_changes._post_reviewer_feedback`) in the words
written here (`posted`): a line naming the review and its round, then the
feedback, then the receipt naming the verdict it was posted for
(`receipted`), the hidden marker every post of this orchestrator closes on
appended below. The id that post lands as is the anchor a failed run's
`/orchestrator continue` replays (`fixing/continue_command`), quoting the post
to a fresh developer.

A post GitHub took whose response was lost names no id, and neither does one
a later refusal left unanchored, so a later tick's handoff looks for the post
before it makes one (`finds`): a comment this orchestrator posted on the pull
request in the words the verdict it hands over posts, receipt and marker
included, is that post, and is anchored rather than posted twice. Of the line
naming the review only the round is held to the verdict's: which reviewer it
names, and how many rounds it counts to, are configuration a restart between
the post and its recovery may change, and a post passed over for either would
be posted twice. The receipt is a digest of the verdict's round, subject, and
evidence claim, so the same findings returned again over another subject -- a
later report, a push, an edited issue, fresh evidence, the round reset --
never take the earlier verdict's receipted post. The thread is read whole
for it, since findings may quote the pinned state's marker. The author is part
of it: the anchor is replayed to a developer as this orchestrator's own words,
outside the author allowlist, so a comment anybody else wrote in them is never
taken.

A tick before receipts posted a verdict with none: its findings concise, or,
for a verdict persisted before findings were formatted, raw. Such a post is
found in those words too -- and a raw post receipted -- but a post with no
receipt names no verdict, so only its place in the thread ties it to the one
handed over: it has to be newer than the developer report that verdict's
subject records and the evidence artifact its claim names, and none of the
comments the ledger of this orchestrator's own already accounts for, which a
landed handoff of another verdict put there. The same findings posted for an
earlier subject stand above a later report or fresh evidence, or were
anchored by that verdict's handoff, and are never taken. One left unanchored
over the very report and evidence the later verdict was reviewed over --
only the issue edited since, say -- cannot be told apart by its place.

A post made before findings were formatted quotes the reviewer's verification
declaration raw, and it stays on the pull request as it was posted. So the
replay quotes it as shown (`ShownPost`): the same comment -- its id, author,
and every other attribute its own, so the batch it rides sorts, deduplicates,
and settles exactly as over the comment itself -- whose body has the findings
formatted (`review_findings`), each check not shown passing kept as its
diagnostic, between the line naming the review and the receipt and marker,
all kept as posted. Findings formatting leaves nothing of read as the
sentence saying so, as a live round's would. A post made since quotes its
findings concise already, and formatting them again changes nothing; a body
of any other shape is read as findings whole.
"""
from __future__ import annotations

import hashlib
import json
import re

from orchestrator import config
from orchestrator.github import comments as _github_comments
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    report_record_values as _record_values,
    report_settlement_state as _report_state,
    review_findings as _findings,
    review_subjects as _review_subjects,
    verification_settlement_state as _evidence_state,
)
from orchestrator.workflow.stages.validating import review_verdicts as _verdicts

# The receipt a post closes on above the orchestrator's marker: the digest of
# the verdict it was posted for -- its round, recorded subject, and evidence
# claim, as canonical JSON.
_RECEIPT = "<!--orchestrator-review-feedback:sha256={digest}-->"

# Where in the thread a receipted post may stand: anywhere -- newer than no
# comment, and none of them excluded.
_ANYWHERE = (0, frozenset())

# The line a post opens on, as `posted` writes it: the review and its round,
# naming whichever reviewer and round cap were configured when it was posted.
_HEAD_RE = re.compile(r"\A:eyes: [^\n]* review \(round (?P<round>\d+)/\d+\) requested changes:\n\n")

# A post as `posted` writes it and the post appends its marker: the line naming
# the review, the findings, the receipt, and the marker -- all but the
# findings optional, so any body reads as findings at least.
_POST_RE = re.compile(
    "(?P<head>:eyes: [^\n]* requested changes:\n\n)?(?P<findings>.*?)"
    "(?P<receipt>\n\n<!--orchestrator-review-feedback:sha256=[0-9a-f]{64}-->)?"
    f"(?P<marker>\n\n{re.escape(_comments._ORCH_COMMENT_MARKER)})?",
    re.DOTALL,
)


def posted(round_n: int, feedback: str) -> str:
    """The words the reviewer's `feedback` is posted in, for the review round `round_n` counted from 0."""
    round_display = round_n + 1
    return (
        f":eyes: {config.REVIEW_AGENT} review "
        f"(round {round_display}/{config.MAX_REVIEW_ROUNDS}) requested changes:\n\n"
        f"{feedback}"
    )


def receipted(words: str, held: _verdicts.ReturnedVerdict) -> str:
    """`words` with the receipt below them naming `held`, the persisted verdict they are posted for."""
    claim = None if held.evidence is None else held.evidence.recorded()
    identity = json.dumps(
        {"round": held.round_n, "subject": held.subject, "evidence": claim},
        sort_keys=True, separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return f"{words}\n\n{_RECEIPT.format(digest=digest)}"


def finds(
    gh: GitHubClient, pr_number: int, words: str, held: _verdicts.ReturnedVerdict, state: PinnedState,
) -> int | None:
    """The newest comment this orchestrator posted on the pull request for `held` in `words`; None for none.

    `words` are the post as `posted` spells `held`'s findings as shown, and
    `state` the pinned comment the handoff stands on. Only a body this
    orchestrator posts for `held` -- the line naming its round's review, the
    findings, and the marker it closes on -- and only where it stands in the
    thread as a post for `held` does (`_recognised`), is that post -- and
    only a comment of this orchestrator's own, by the whole id it is addressed
    by. That line is read for the round alone (`_stands`), whatever reviewer
    and round cap it names. The thread is read whole
    (`pr_conversation_thread`): a reviewer's findings may quote the pinned
    state's marker, which the feedback readers leave out, and a post passed
    over for it would be posted twice. A thread that will not read raises,
    and proves nothing either way.
    """
    accepted = _recognised(words, held, state)
    own = getattr(gh, "_bot_login", None)
    thread = gh.pr_conversation_thread(gh.get_pr(pr_number))
    found = (
        _stands(said, held.round_n, accepted) for said in thread
        if _github_comments.authored_by_us(said, bot_login=own)
    )
    return max((identified for identified in found if identified is not None), default=None)


class ShownPost:
    """A reviewer-feedback comment as a replay quotes it: its findings formatted, everything else the comment's own."""

    def __init__(self, comment: object) -> None:
        self._comment = comment
        # The findings formatted, every other part of the body -- in
        # `_POST_RE`'s order -- as posted.
        body = getattr(comment, "body", None) or ""
        parts = _POST_RE.fullmatch(body).groupdict(default="")
        parts["findings"] = _findings._concise_findings(parts["findings"])
        self.body = "".join(parts.values())

    def __getattr__(self, name: str) -> object:
        return getattr(self._comment, name)


def _recognised(words: str, held: _verdicts.ReturnedVerdict, state: PinnedState) -> dict[str, tuple]:
    """Each body a post made for `held` may carry below its opening line, and where in the thread it has to stand.

    Each body runs from the findings to the marker, and maps to `(past,
    accounted)`: the id the post has to be newer than, and the ids it may not
    be. A receipted body names `held` itself, in the findings `words` post or
    -- a verdict persisted before findings were formatted -- in its raw
    findings, and stands anywhere. A body with no receipt is how a tick
    before receipts posted it, in either, and names no request: it stands
    only where a post for `held` does (`_unreceipted`).
    """
    shown = {_HEAD_RE.sub("", words, count=1), held.feedback}
    accepted = dict.fromkeys((receipted(said, held) for said in shown), _ANYWHERE)
    unreceipted = _unreceipted(state, held)
    if unreceipted is not None:
        accepted.update(dict.fromkeys(shown, unreceipted))
    return {_comments._with_orch_marker(body): stands for body, stands in accepted.items()}


def _unreceipted(state: PinnedState, held: _verdicts.ReturnedVerdict) -> tuple | None:
    """Where in the thread a post for `held` with no receipt has to stand, as `(past, accounted)`; None for nowhere.

    Only its place ties it to `held`. It is newer than every comment `held`
    was reviewed over -- the developer report its subject records, where the
    report records name it (none for one in the pull request's description),
    and the artifact of the evidence it claims -- since the same findings
    posted for an earlier subject stand above the report or the evidence the
    later one was reviewed over. And it is none of the comments the ledger of
    the orchestrator's own accounts for, which only a landed write of another
    request's handoff put there: an unhanded request's own post is in no
    landed write. None where the report recorded now is not the one the
    subject names, or the evidence settled now is not the one the claim names.
    """
    report = _report_state.read_current_report(state)
    if report is None:
        return None
    recorded = (report.location.pr_number, report.report_revision, report.content_revision)
    if _review_subjects.ReviewSubject.identity_recorded_in(held.subject) != recorded:
        return None
    reviewed_over = [report.location.comment_id or 0]
    if held.evidence is not None:
        evidence = _evidence_state.read_current_evidence(state)
        settled = None if evidence is None else (evidence.receipt, evidence.revision)
        if settled != (held.evidence.receipt, held.evidence.revision):
            return None
        reviewed_over.append(evidence.comment_id)
    return max(reviewed_over), frozenset(_comments._orchestrator_ids(state))


def _stands(said: object, round_n: int, accepted: dict[str, tuple]) -> int | None:
    """The id of `said` where it is a post for round `round_n` that `accepted` maps and stands as mapped; or None.

    Its body opens on the line naming the review of that round, counted from
    0, whichever reviewer and round cap that line names, and `accepted` maps
    the rest of it.
    """
    identified = _record_values.as_recorded_number(getattr(said, "id", None))
    head = _HEAD_RE.match(getattr(said, "body", None) or "")
    stands = None
    if head is not None and head["round"] == str(round_n + 1):
        stands = accepted.get(head.string[head.end():])
    if identified is None or stands is None:
        return None
    past, accounted = stands
    return identified if identified > past and identified not in accounted else None
