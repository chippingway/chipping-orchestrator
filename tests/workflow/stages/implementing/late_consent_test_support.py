# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One adjudicated candidate parked for the person nobody can show.

The fixture the authorization park's own contract is driven through, at both
altitudes it has to be asked at. Most of what the park promises is a thread
and a pinned comment -- which reply a reading acts on, what the record it
writes says, and how far it consumes -- and driving that through a whole stage
handler would put a publication seam between the case and the answer it is
asserting on. What the ROUTING promises is the opposite: that a parked tick
reaches the gate at all, and that the park survives whatever the real seam
does with it, neither of which a double in that seam's place can answer. So
`_run_tick` runs the whole handler over the same seeded issue.

The generation carries the PAIR and no count, which is exactly what the park
leaves: a record answering "oversized" is what this workflow means by an
adjudication in flight, and the dispatcher puts `workflow:decomposing` back
over one before any stage runs. So the reading is re-taken by the tick that
acts, and the count a case hands in is that tick's own.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.measurement import (
    additions as _additions,
    fingerprint as _fingerprint,
)
from orchestrator.git.measurement.models import (
    AdditionMeasurement,
    ContributionFingerprint,
    FingerprintFailure,
    MeasurementFailure,
)
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import (
    MAX_PINNED_BODY,
    PINNED_STATE_MARKER,
    PinnedState,
    pinned_state_body,
)
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration, LatePhase
from orchestrator.workflow.stages.implementing import (
    late_command as _command,
    late_consent as _consent,
    late_freeze as _freeze,
    late_gate as _gate,
    late_reading as _reading,
    late_records as _records,
    state as _state,
)
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_IMPLEMENTING,
    MEASURED_BASE_SHA,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
    _agent,
    _PatchedWorkflowMixin,
)
from tests.workflow.repo_values import CONTRIBUTION_DIGEST

FINGERPRINT_CONTRIBUTION = "_fingerprint_contribution"
FROZEN_PAIR = "_frozen_pair"
COUNT_ADDED_LINES = "_count_added_lines"
SETTLED = "_settled"
# The two the verdict owner reaches past that one: the publication a count at
# or below the ceiling earns, and the hold an oversized candidate nobody has
# ruled on is routed by.
ACCEPTED = "_accepted"
ROUTED = "_routed"
RECONCILED_MEASUREMENT = "_reconciled_measurement"
FRESHLY_MEASURED = "_freshly_measured"
PARK_AWAITING_HUMAN = "_park_awaiting_human"
WRITE_PINNED_STATE = "write_pinned_state"
POST_ISSUE_COMMENT = "_post_issue_comment"
ORCHESTRATOR_IDS = "orchestrator_comment_ids"

ISSUE_NUMBER = 612
THRESHOLD = 4000
OVERSIZED_ADDITIONS = 9123

# A reading the ceiling lets through, which is a candidate no operator has to
# authorize: measured afresh, it is not the change anybody was asked about.
SMALL_ADDITIONS = 12
PR_NUMBER = 41
WORKTREE = Path("/tmp/orchestrator-test-late-consent")

# A directory the recovery's existence probe finds, standing in for the
# checkout the committed candidate lives in.
TEMP_WORKTREE_ROOT = Path("/tmp")

# The two seams a case asks whether a whole tick spent: a developer run, and
# the push that would have published the candidate.
RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"
WORKTREE_PATH = "_worktree_path"

# A commit that types as one and that no record on this issue names: the id an
# operator copies out of a notice about work a resumed developer moved past.
STRANGER_SHA = "d" * SHA_LENGTH

# How much of a whole object id a `git log` line shows, which is what somebody
# types when they abbreviate. Nothing in this domain writes one, so it is the
# mismatch it is rather than a prefix to compare.
ABBREVIATED = 7

TRUSTED_AUTHOR = "alice"
OUTSIDER = "mallory"
ALLOWLIST_CONFIG = "ALLOWED_ISSUE_AUTHORS"

# Where the thread had been read to when the park went up, so every reply a
# case seeds is one the reading is entitled to find.
PRIOR_ACTION_COMMENT_ID = 900

_COMMAND = "/orchestrator authorize-oversized {commit}"

AUTHORIZE = _COMMAND.format(commit=MEASURED_CANDIDATE_SHA)
AUTHORIZE_ANOTHER = _COMMAND.format(commit=STRANGER_SHA)
AUTHORIZE_ABBREVIATED = _COMMAND.format(
    commit=MEASURED_CANDIDATE_SHA[:ABBREVIATED],
)
GUIDANCE = "make it smaller, please"

# The one reply the measurement park is ended by: take the reading you could
# not take again. It carries no words for a developer, which is what makes it
# the retry rather than guidance -- and what has every road but that park's
# own read it as a command carrying no answer.
CONTINUE = "/orchestrator continue"

# The receipt the park's own notice is stamped with, which is what a tick that
# died before saying it leaves on the record and what the sentence itself
# carries once it lands.
PARK_RECEIPT = _consent._RECEIPTS["parked"].format(
    issue=ISSUE_NUMBER, scope=MEASURED_CANDIDATE_SHA,
)

# A record too big for its own escaping, which is the rendering that puts
# every receipt it holds into the pinned comment's body VERBATIM: the escape
# that hides a comment terminator is dropped wherever keeping it would push
# the write past GitHub's ceiling, and losing the write is the worse trade.
# Sized through a park's own message, which is free text a stage really does
# put there.
AT_THE_LIMIT = MappingProxyType({
    "late_park_notice": {
        "reason": "late_question", "message": "x" * MAX_PINNED_BODY,
    },
})


def refusal_receipt(comment_id: int) -> str:
    """The receipt the answer to one reply is stamped with."""
    return _consent._RECEIPTS["refused"].format(
        issue=ISSUE_NUMBER, scope=comment_id,
    )

# A reply that merely QUOTES the pinned comment's marker -- an operator
# pasting a payload back to ask about it, or writing under one they copied.
# The record is named by its id, so this is somebody's word like any other.
QUOTES_THE_RECORD = f"hold off -- this issue says {PINNED_STATE_MARKER} ... -->"

KEY_OVERRIDE_CANDIDATE_SHA = "late_override_candidate_sha"
KEY_OVERRIDE_BASE_SHA = "late_override_base_sha"
KEY_OVERRIDE_ADDITIONS = "late_override_additions"
KEY_OVERRIDE_THRESHOLD = "late_override_threshold"
KEY_OVERRIDE_COMMENT_ID = "late_override_comment_id"

KEY_EXEMPT_SHA = "late_exempt_sha"


def measured() -> LateGeneration:
    """The reading the tick that acts took, which the terms are written from."""
    return LateGeneration(
        cycle_id=1,
        generation=1,
        root_issue=ISSUE_NUMBER,
        current_issue=ISSUE_NUMBER,
        lineage_depth=0,
        candidate_sha=MEASURED_CANDIDATE_SHA,
        base_sha=MEASURED_BASE_SHA,
        threshold=THRESHOLD,
        additions=OVERSIZED_ADDITIONS,
        phase=LatePhase.MEASURING,
    )


# A gate call entered PAST a publication: the stage it takes the issue out
# of, the pull request the work already has, and the head that pull request
# stands on. What it changes here is the notice, since guidance reaches a
# developer only where the ordinary resume is still in front of the issue.
PUBLISHED_ENTRY = _records._PublicationEntry(
    stage=LABEL_IMPLEMENTING,
    pr_number=PR_NUMBER,
    published_sha=MEASURED_BASE_SHA,
)


def measured_pair(**overrides) -> dict:
    """The pair the freeze wrote, which is all a standing park carries.

    Deliberately without the count, which is what the freeze itself persists:
    a generation answering "oversized" is what this workflow means by an
    adjudication in flight, so a park that recorded one would be relabelled
    out from under itself before anything could answer it -- and a recorded
    number is what the gate acts on instead of taking the reading again. What
    the announce-once guard compares is the COMMIT.
    """
    recorded = PinnedState(data={})
    _late_state.write_late_generation(
        recorded, replace(measured(), additions=None, **overrides),
    )
    return recorded.data


class FreezesThePair:
    """Stand in for the freeze, persisting the pair it froze as it does.

    The WRITE is why this is a double rather than a stubbed return value.
    What the entry ordering turns on is that the freeze puts the pair in hand
    onto the pinned comment before anything reads which commit the park is
    standing over -- so a stub that answered without writing would hide the
    question these cases ask.

    `None` is a base this host could not name, which is a reading that did not
    happen and leaves the record exactly as found.
    """

    def __init__(self, pair: LateGeneration | None) -> None:
        self._pair = pair

    def __call__(self, gate, recorded, candidate_sha):
        if self._pair is None:
            return None
        frozen = replace(
            self._pair, candidate_sha=candidate_sha, additions=None,
        )
        _late_state.write_late_generation(gate.state, frozen)
        gate.gh.write_pinned_state(gate.issue, gate.state)
        return frozen


@dataclass(frozen=True)
class GateDecision:
    """What one gate call answered, and whether it needed a reading to.

    Both facts, because the roads past the gate reach the same two verdicts:
    a commit two records vouch for publishes without a count, and one an
    exemption alone names publishes only once the count says the ceiling lets
    it through, so a case asking only what came back could not tell them
    apart.
    """

    verdict: object
    measured: bool


class SettlesWithItsOwnWrite:
    """The settlement's durable write, without its cycle bookkeeping.

    What a case here asserts is that the park comes off IN that write, so the
    double has to make one -- and it keeps the record it was handed, so a case
    can ask what the settlement was given as well as what landed.
    """

    def __init__(self) -> None:
        self.given: list[dict] = []

    def __call__(self, gate, generation) -> bool:
        self.given.append(dict(gate.state.data))
        gate.gh.write_pinned_state(gate.issue, gate.state)
        return False


class CrashedTick(RuntimeError):
    """The process dying between two writes one road makes."""


class DiesPastTheFirstWrite:
    """A client that makes its first durable write and then dies.

    For a road whose first write is not the one at risk: the sentence has been
    said AND recorded by then, and what the crash costs is whatever the write
    after that carried.
    """

    def __init__(self, github) -> None:
        self._wrapped = github.write_pinned_state
        self._writes = 0

    def __call__(self, *called, **options):
        self._writes += 1
        if self._writes > 1:
            raise CrashedTick
        return self._wrapped(*called, **options)


class DiesPastTheRelabel:
    """A client that dies on the first write once the label has moved.

    The window a successful publication opens: the handoff writes durably and
    then hands the issue to `validating`, and everything this stage still had
    in flight is past saving from that point on -- nothing under the new label
    spends it and this stage never sees the issue again. What it kills is the
    write AFTER the relabel, which is the last chance a road here would have
    had to tidy up in memory.
    """

    def __init__(self, github) -> None:
        self._github = github
        self._wrapped = github.write_pinned_state

    def __call__(self, *called, **options):
        if self._github.label_history:
            raise CrashedTick
        return self._wrapped(*called, **options)


class DiesRestoringTheHeldPark:
    """A client that dies on the write that would put a held park back.

    The window the durable rollback exists for, named by what makes it that
    window rather than by a count of writes: a handoff has recorded what the
    park was, the seam has written over it, and the write that would restore
    it is the one killed. Everything the seam itself persisted lands, which is
    the whole point -- a rollback kept in memory is gone by the next poll and
    the record still says whatever the seam left.
    """

    def __init__(self, github) -> None:
        self._wrapped = github.write_pinned_state
        self._recorded = False

    def __call__(self, issue, state, *called, **options):
        held = state.get(_state._HELD_PARK)
        if self._recorded and held is None:
            raise CrashedTick
        self._recorded = self._recorded or held is not None
        return self._wrapped(issue, state, *called, **options)


class DiesPastTheNotice:
    """A client whose write dies once the thread carries what a case is about.

    The window itself rather than a count of writes, so a case reproduces it
    whichever order the road makes its operations in: what it kills is always
    the write that would have recorded the sentences just posted.

    `said` is how many of them have to be on the thread first, for a road that
    says more than one thing before anything records any of it -- a pull
    request opened, then a refusal over a checkout that moved under the push.

    `spared` is how many writes past that go through anyway, for a road whose
    own next act is a write: the client this park hands the seam records each
    id the instant the post returns, so a case about the window PAST that one
    has to let it land.
    """

    def __init__(self, github, said: int = 1, spared: int = 0) -> None:
        self._github = github
        self._said = said
        self._spared = spared
        self._wrapped = github.write_pinned_state

    def __call__(self, *called, **options):
        if len(self._github.posted_comments) >= self._said:
            if not self._spared:
                raise CrashedTick
            self._spared -= 1
        return self._wrapped(*called, **options)


# What the hermetic world's reading of the frozen pair answers with, and the
# refusal a host that never held the content between them gives instead.
CONTRIBUTED = ContributionFingerprint(
    base_sha=MEASURED_BASE_SHA,
    candidate_sha=MEASURED_CANDIDATE_SHA,
    digest=CONTRIBUTION_DIGEST,
)
UNREADABLE = ContributionFingerprint(failure=FingerprintFailure.CONTENT_ABSENT)

# What a fresh count answers with on each side of the ceiling, and what a host
# that could not read the diff between the frozen pair answers instead.
OVERSIZED = AdditionMeasurement(additions=OVERSIZED_ADDITIONS)
FITS = AdditionMeasurement(additions=SMALL_ADDITIONS)
UNCOUNTABLE = AdditionMeasurement(failure=MeasurementFailure.DIFF_FAILED)


class _ParkedCase(_PatchedWorkflowMixin):
    """An issue holding one adjudicated candidate nobody has authorized."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        self.github.seed_state(ISSUE_NUMBER)
        self._seed()

    def _seed(self, *, parked: bool = True, **state) -> None:
        """Replace the pinned comment with the one a case is about.

        `parked=False` is the same issue with nothing standing on it, which is
        what the cases about ENTERING this park are seeded with.
        """
        standing = {
            _state._AWAITING_HUMAN: True,
            _state._PARK_REASON: _command.PARK_UNAUTHORIZED_EXEMPTION,
        } if parked else {}
        self.github.seed_state(ISSUE_NUMBER, **{
            _state._LAST_ACTION_COMMENT_ID: PRIOR_ACTION_COMMENT_ID,
            KEY_EXEMPT_SHA: MEASURED_CANDIDATE_SHA,
            **standing,
            **state,
        })

    def _reply(self, body: str, author: str = TRUSTED_AUTHOR) -> int:
        """Add one comment past the consumed watermark, and say which it is."""
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(FakeComment(
            identified, body, user=FakeUser(author),
        ))
        return identified

    def _pinned(self) -> dict:
        return self.github.pinned_data(ISSUE_NUMBER)

    def _pin_the_record(self) -> int:
        """Put the pinned comment itself on the thread, rendered as it is written.

        The double keeps the record in a dict and puts no comment on the
        thread for it, so nothing that READS a thread can see the one comment
        every issue really carries. What a case here turns on is that body's
        contents, so it is produced by the production renderer rather than
        spelled out: a record whose escaped form would not fit is written as
        its own payload, and every receipt in it lands on the thread as the
        literal string it is.
        """
        state = self._state()
        self.issue.comments.append(FakeComment(
            state.comment_id,
            pinned_state_body(state.data),
            user=FakeUser(self.github._bot_login),
        ))
        return state.comment_id

    def _said(self) -> int:
        """How many sentences of ours this thread carries."""
        return len(self.github.posted_comments)

    def _assert_still_parked(self) -> None:
        """The park exactly as it was: somebody waiting, behind this question."""
        pinned = self._pinned()
        self.assertTrue(pinned[_state._AWAITING_HUMAN])
        self.assertEqual(
            pinned[_state._PARK_REASON], _command.PARK_UNAUTHORIZED_EXEMPTION,
        )

    def _run_tick(self, worktree: Path = TEMP_WORKTREE_ROOT, **run_options):
        """Run one whole implementing tick over this parked issue.

        The seams the recovery hands its answer to are the real ones, which is
        the only way a case can see what the publication below does to a park
        it was entered under.
        """
        run_options.setdefault("has_new_commits", True)
        # Past the ceiling by default, because that is the reading this park
        # exists for: a candidate the gate measures small needs nobody's
        # authorization and publishes on its own count.
        run_options.setdefault("added_lines", OVERSIZED_ADDITIONS)
        run_options.setdefault(
            "run_agent", _agent(last_message="implemented"),
        )
        with patch.object(
            _worktree_paths, WORKTREE_PATH, return_value=worktree,
        ):
            return self._run_implementing(
                self.github, self.issue, **run_options,
            )

    def _state(self) -> PinnedState:
        return self.github.read_pinned_state(self.issue)

    def _gate(self, state: PinnedState | None = None, **entered):
        """The gate call this park was taken on, or is being answered from."""
        return _records._Gate(
            gh=self.github,
            spec=_TEST_SPEC,
            issue=self.issue,
            state=self._state() if state is None else state,
            worktree=WORKTREE,
            **entered,
        )


class _ConsentCase(_ParkedCase):
    """One gate call asking whether this candidate may publish as it stands."""

    def _authorizes(self, contribution=CONTRIBUTED, **entered) -> bool:
        """The reply half alone, over the reading the gate has already taken."""
        with patch.object(
            _fingerprint, FINGERPRINT_CONTRIBUTION, return_value=contribution,
        ):
            return _consent._authorizes_the_park(
                self._gate(**entered), measured(),
            )

    def _holds(self, counted=OVERSIZED, pair=..., **entered) -> bool:
        """The whole ordinary reading this park is reached from.

        The gate's own freeze-and-count rather than a road of this owner's,
        because that is what a tick actually walks: the park is what an
        oversized answer to it earns, and every way the reading can fail is
        the measurement's own. The record this tick writes and the record the
        last one left are two different things, which is what every case about
        a lost write and a moved candidate turns on.
        """
        frozen = measured() if pair is ... else pair
        with (
            patch.object(_freeze, FROZEN_PAIR, FreezesThePair(frozen)),
            patch.object(_additions, COUNT_ADDED_LINES, return_value=counted),
            patch.object(
                _fingerprint, FINGERPRINT_CONTRIBUTION,
                return_value=CONTRIBUTED,
            ),
        ):
            return _reading._freshly_measured(
                self._gate(**entered), measured(), MEASURED_CANDIDATE_SHA,
            )

    def _decides(self, counted=OVERSIZED, **entered) -> GateDecision:
        """One whole gate decision over this candidate, reading and all.

        The measurement is RUN rather than stubbed, because the road this park
        is reached down is the ordinary one: a case that cut the reading out
        would answer a question no tick asks. What says which road was taken
        is whether a count was needed at all.
        """
        with (
            patch.object(_freeze, FROZEN_PAIR, FreezesThePair(measured())),
            patch.object(
                _additions, COUNT_ADDED_LINES, return_value=counted,
            ) as counting,
            patch.object(
                _fingerprint, FINGERPRINT_CONTRIBUTION,
                return_value=CONTRIBUTED,
            ),
        ):
            gate = self._gate(**entered)
            verdict = _gate._decided(
                gate,
                _late_state.read_late_generation(gate.state),
                MEASURED_CANDIDATE_SHA,
            )
            ordinary = counting.called
        return GateDecision(verdict=verdict, measured=ordinary)

    def _crashes_past_our_sentence(self, *, parked: bool = True) -> None:
        """Run one whole call, and lose the write past whatever it posted.

        The window itself rather than a count of writes, so the same helper
        reproduces it for the park's notice and for the refusal alike: what it
        kills is always the write that would have recorded the sentence this
        call just said.

        `parked=False` is the call that TAKES the park, which is the only one
        that says its notice: a park already standing over the pair the freeze
        just wrote has said that sentence on an earlier tick, so a case
        seeding one would reproduce the quiet road instead of the window.
        """
        self._seed(parked=parked)
        with (
            patch.object(
                self.github, WRITE_PINNED_STATE,
                side_effect=DiesPastTheNotice(self.github),
            ),
            self.assertRaises(CrashedTick),
        ):
            self._holds()
