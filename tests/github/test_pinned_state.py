# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import sys
import unittest
from types import MappingProxyType

from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import ORCHESTRATOR_COMMENT_MARKER
from orchestrator.github.pinned_state import (
    MAX_PINNED_BODY,
    PINNED_STATE_MARKER,
    PINNED_STATE_TEMPLATE,
    SUPPORTED_SCHEMA_VERSION,
    AdmissionStatus,
    PinnedState,
    admit_pinned_comment,
    pinned_state_body,
)
from orchestrator.workflow.engine import comments as _engine_comments
from tests.github.pinned_state_test_support import (
    BOT,
    ORDINARY_PROSE,
    RAW_ORDINARY_QUOTE,
    RAW_TERMINATORS,
    bot_comment,
    cut_short,
    marker,
    state_client,
)
from tests.support.fakes import FakeComment, FakeUser, make_issue

REAL_BRANCH = "orchestrator/chippingway__chipping-orchestrator/issue-5"
_ATTACKER_BRANCH = "orchestrator/evil"
_ATTACKER_LOGIN = "mallory"
_BRANCH_KEY = "branch"
_DEV_AGENT_KEY = "dev_agent"
_PINNED_COMMENT_ID = 200
_SCHEMA_VERSION = "schema_version"
_REPO = "chippingway/chipping-orchestrator"

# An integer longer than the interpreter's default digit limit of 4300, and
# arrays nested inside a record: one level short of the recursion limit, so the
# record reaches it, then one level more, which every supported interpreter
# still decodes and only the reader's own bound refuses, and far past it, which
# some decoders refuse themselves while others build what their encoder then
# overflows on.
_PAST_THE_DIGIT_LIMIT = 5000
_AT_THE_LIMIT = sys.getrecursionlimit() - 1
_TOO_DEEP = 100_000
_HUGE_INTEGER = "9" * _PAST_THE_DIGIT_LIMIT
_LIMIT_ARRAY = "".join(("[" * _AT_THE_LIMIT, "]" * _AT_THE_LIMIT))
_PAST_LIMIT_ARRAY = f"[{_LIMIT_ARRAY}]"
_DEEP_ARRAY = "".join(("[" * _TOO_DEEP, "]" * _TOO_DEEP))

# A record written raw around its terminators and then cut short of its
# closing brace: nothing but the marker it opens with identifies it, whatever
# its values quote.
_CUT_SHORT = cut_short({_SCHEMA_VERSION: 1, "note": RAW_TERMINATORS})
_CUT_SHORT_QUOTING = cut_short({_SCHEMA_VERSION: 1, "note": RAW_ORDINARY_QUOTE})

# Payloads no reading decodes, each a different refusal: a syntax error, an
# integer past the digit limit (a ValueError that is no JSONDecodeError), the
# constants Python's decoder takes and JSON has no spelling for, nesting past
# the recursion limit (a RecursionError, whether the decoder or the reader's
# own bound raises it), a record cut short around raw terminators,
# which nothing but its marker identifies as one, and a string cut open in the
# middle of an escape, whose backslash stands right before the terminator.
_UNDECODABLE = MappingProxyType({
    "syntax": "{bad json}",
    "an integer past the digit limit": f'{{"schema_version": {_HUGE_INTEGER}}}',
    "NaN": '{"schema_version": 1, "usage_total": NaN}',
    "Infinity": '{"schema_version": 1, "usage_total": Infinity}',
    "-Infinity": '{"schema_version": 1, "usage_total": [-Infinity]}',
    "a number past the float range": '{"pr_number": 1e309, "schema_version": 1}',
    "nesting just past the recursion limit": f'{{"schema_version": 1, "x": {_PAST_LIMIT_ARRAY}}}',
    "nesting far past the recursion limit": f'{{"schema_version": 1, "x": {_DEEP_ARRAY}}}',
    "an object cut short around raw terminators": _CUT_SHORT,
    "an object cut short around a raw quote of the ordinary marker": _CUT_SHORT_QUOTING,
    "an object cut open on a dangling escape": '{"schema_version": 1, "note": "unfinished\\',
    "a string cut open on a dangling escape": '"unfinished\\',
})

# A comment that QUOTES the state marker rather than being the state comment:
# what a park notice explaining this orchestrator's own pinned comment looks
# like on the thread, and what the marker test cannot tell from the real one.
_QUOTING_BODY = f"the schema in {PINNED_STATE_MARKER} blocks it"

# Payloads that are no state and carry the comment terminator inside a value:
# what a truncated write or a hand edit could leave, each still the marker alone.
_TERMINATED_NON_OBJECTS = ('["-->"]', '"a --> b"', '[{"note": "-->"}]')

# Payloads no state is read out of that quote, inside a JSON string, the marker
# every other comment this orchestrator posts carries: still the marker alone,
# so each is a corrupted state comment, refused and kept, as one carrying the
# comment terminator is.
_QUOTING_NON_OBJECTS = (json.dumps([ORCHESTRATOR_COMMENT_MARKER]), json.dumps(ORCHESTRATOR_COMMENT_MARKER))

# Every non-object payload the bot's own state-only comment is refused for.
_NON_OBJECTS = ("[]", '"str"', "7", "null", "true", "false", *_TERMINATED_NON_OBJECTS, *_QUOTING_NON_OBJECTS)

# Payloads that carry that marker outside any JSON string, where only an
# ordinary comment's prose puts it: text an agent wrote, never a state comment.
_PROSE_NON_OBJECTS = (
    f"7 {ORCHESTRATOR_COMMENT_MARKER}",
    f'["x"]--> {ORCHESTRATOR_COMMENT_MARKER} ["y"]',
)

# An ordinary comment's prose shaped as an object, cut short and closed: it
# carries that marker outside any JSON string, where no record does.
_PROSE_OBJECTS = (ORDINARY_PROSE, f"{ORDINARY_PROSE}}}")

# What ends the comment the payload is wrapped in, and a value that carries
# it: an agent's explanation, a preserved pull-request body, a human's own
# words all reach the record as somebody wrote them.
_COMMENT_CLOSE = "-->"

_BLOCKER_KEY = "late_result_split_blocker"

_TERMINATING_VALUE = f"the marker {_COMMENT_CLOSE} ends it"

# How many terminators one value carries where escaping every one would cost
# more than the comment GitHub takes while the payload as it was stored is
# well inside it. What a record an older binary accepted at the ceiling looks
# like: a preserved pull-request body is where they come by the thousand.
_TERMINATORS = 16384

_TERMINATOR_RUN = _COMMENT_CLOSE * _TERMINATORS


class ReadPinnedStateTrustsAuthorTest(unittest.TestCase):
    """`read_pinned_state` must authenticate durable state to the account
    backing the token. A third party who can comment on the issue must not be
    able to preempt the real pinned state with a forged marker comment
    (CWE-345)."""

    def test_foreign_marker_before_state_is_ignored(self) -> None:
        # An attacker posts (or edits an older comment to carry) the hidden
        # state marker before the orchestrator's real pinned comment. GitHub
        # keeps the original author on an edit, so "edited older comment" is
        # the same case: the foreign author is skipped regardless of order.
        attacker = FakeComment(
            id=1,
            body=marker({_BRANCH_KEY: _ATTACKER_BRANCH, _DEV_AGENT_KEY: "pwn"}),
            user=FakeUser(_ATTACKER_LOGIN),
        )
        legit = FakeComment(
            id=_PINNED_COMMENT_ID,
            body=marker({_BRANCH_KEY: REAL_BRANCH, _DEV_AGENT_KEY: "claude"}),
            user=FakeUser(login=BOT),
        )
        issue = make_issue(5, comments=[attacker, legit])

        state = state_client().read_pinned_state(issue)

        # The orchestrator's own comment wins, not the earlier forged one.
        self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
        self.assertEqual(state.get(_BRANCH_KEY), REAL_BRANCH)
        self.assertEqual(state.get(_DEV_AGENT_KEY), "claude")

    def test_bad_foreign_marker_cannot_shadow_state(self) -> None:
        # A foreign marker with unparseable JSON would, under the old
        # first-marker-wins parser, early-return empty state and shadow the
        # real one. The author gate skips it before its body is parsed.
        attacker = FakeComment(
            id=1,
            body="<!--orchestrator-state {bad json}-->",
            user=FakeUser(_ATTACKER_LOGIN),
        )
        legit = bot_comment(
            _PINNED_COMMENT_ID,
            marker({_BRANCH_KEY: REAL_BRANCH}),
        )
        issue = make_issue(5, comments=[attacker, legit])

        state = state_client().read_pinned_state(issue)

        self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
        self.assertEqual(state.get(_BRANCH_KEY), REAL_BRANCH)

    def test_only_foreign_marker_yields_empty_state(self) -> None:
        # With no orchestrator-authored marker present, nothing is trusted:
        # the parser reports no pinned state (comment_id None) so the caller
        # creates a fresh state comment rather than adopting the forgery.
        attacker = FakeComment(
            id=1,
            body=marker({_BRANCH_KEY: _ATTACKER_BRANCH, "pr_number": 999}),
            user=FakeUser(_ATTACKER_LOGIN),
        )
        issue = make_issue(5, comments=[attacker])

        state = state_client().read_pinned_state(issue)

        self.assertIsNone(state.comment_id)
        self.assertEqual(state.state_data, {})

    def test_bot_authored_state_is_trusted(self) -> None:
        # The account backing the token authored it, so its current record is
        # the state.
        bot_user = FakeUser(BOT)
        legit = FakeComment(
            id=_PINNED_COMMENT_ID,
            body=marker({_BRANCH_KEY: REAL_BRANCH, "review_round": 2}),
            user=bot_user,
        )
        issue = make_issue(5, comments=[legit])

        state = state_client().read_pinned_state(issue)

        self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
        self.assertEqual(state.get("review_round"), 2)
        self.assertTrue(state.parsed)

    def test_bad_trusted_marker_keeps_comment_id(self) -> None:
        # A corrupted orchestrator-authored comment still resolves to its id
        # (with empty data), so it is reported and both writers leave it as it
        # stands -- read as no record at all, a write would post a second
        # pinned comment beside it.
        #
        # The empty payload is a stand-in, not a reading, and it says so: an
        # issue nothing was ever recorded for resolves to the same `{}`, and
        # a caller deciding on the absence of a recorded branch or pull
        # request would otherwise be deciding on a record it never read.
        legit = bot_comment(
            _PINNED_COMMENT_ID,
            "<!--orchestrator-state {bad json}-->",
        )
        issue = make_issue(5, comments=[legit])

        state = state_client().read_pinned_state(issue)

        self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
        self.assertEqual(state.state_data, {})
        self.assertEqual((state.parsed, state.supported), (False, False))

    def test_a_missing_login_authenticates_nothing(self) -> None:
        # A client that does not know whose token it holds cannot tell the
        # orchestrator's record from anybody's, so it takes none: not an
        # outsider's, and not the one the bot did write.
        client = GitHubClient.__new__(GitHubClient)
        forged = marker({_BRANCH_KEY: _ATTACKER_BRANCH})
        legit = marker({_BRANCH_KEY: REAL_BRANCH})
        issue = make_issue(5, comments=[
            FakeComment(id=1, body=forged, user=FakeUser(_ATTACKER_LOGIN)),
            bot_comment(_PINNED_COMMENT_ID, legit),
        ])

        state = client.read_pinned_state(issue)

        self.assertEqual((state.comment_id, state.state_data), (None, {}))
        self.assertEqual(
            [admit_pinned_comment(comment, trusted_login=None).status for comment in issue.comments],
            [AdmissionStatus.NO_COMMENT, AdmissionStatus.NO_COMMENT],
        )


class ReadPinnedStateRequiresStateOnlyBodyTest(unittest.TestCase):
    """Author match is necessary but not sufficient. An ordinary bot-authored
    comment -- `_post_issue_comment` posts decomposer/agent text that is
    attacker-influenced, and does so BEFORE the real state comment exists on a
    manually-labeled issue -- that embeds a `<!--orchestrator-state ...-->`
    substring must not be mistaken for state. Only a comment whose ENTIRE body
    is the marker (what `write_pinned_state` emits) is trusted.

    What that comment CARRIES is the second half of the same question. A body
    that is the marker alone is the state comment whatever payload sits in it,
    and a payload no state can be read out of is reported as one rather than
    passed over -- passed over, it would read as an issue that recorded
    nothing at all. A payload carrying the wrapper's own terminator is the
    sharp case of that, since it would leave the body no longer being the
    marker alone -- and everything after it visible on the issue."""

    def test_a_terminating_value_closes_nothing(self) -> None:
        # An agent's explanation, a preserved pull-request body, a human's own
        # words: none is this owner's to sanitize, so what is escaped is the
        # serialized form. Left raw, the comment ends inside the payload and
        # the rest of the record is issue text a human reads.
        body = pinned_state_body({_BLOCKER_KEY: _TERMINATING_VALUE})

        closes_at = len(body) - len(_COMMENT_CLOSE)
        self.assertEqual(body.index(_COMMENT_CLOSE), closes_at)

    def test_a_terminating_value_reads_back_whole(self) -> None:
        # Escaped in the serialized form and nowhere else: what a reader
        # decodes is the value somebody actually wrote.
        written = pinned_state_body({"schema_version": 1, _BLOCKER_KEY: _TERMINATING_VALUE})
        issue = make_issue(5, comments=[
            bot_comment(_PINNED_COMMENT_ID, written),
        ])
        client = state_client()

        state = client.read_pinned_state(issue)

        self.assertEqual(state.get(_BLOCKER_KEY), _TERMINATING_VALUE)

    def test_an_unescapable_payload_is_stored_raw(self) -> None:
        # The escape is five characters an occurrence, and a record already on
        # an issue never paid them. Refusing the write it puts past the limit
        # would lose the record the next tick reads; writing the payload as it
        # was stored renders the comment the way the binary that accepted it
        # rendered it, and the object form spans the terminator on the way
        # back.
        written = pinned_state_body({"schema_version": 1, _BLOCKER_KEY: _TERMINATOR_RUN})
        issue = make_issue(5, comments=[
            bot_comment(_PINNED_COMMENT_ID, written),
        ])
        client = state_client()

        state = client.read_pinned_state(issue)

        self.assertLessEqual(len(written), MAX_PINNED_BODY)
        self.assertIn(_COMMENT_CLOSE * 2, written)
        self.assertEqual(state.get(_BLOCKER_KEY), _TERMINATOR_RUN)

    def test_embedded_bot_marker_is_not_state(self) -> None:
        # Adversarial shape: forged marker at position 0 of a comment the
        # orchestrator posts, which carries the orchestrator-comment marker --
        # appended at its end, or wherever its text already put it. Either way
        # the body is not state-only, whatever shape of payload the forged
        # marker carries, whether or not it is terminated, and whatever string
        # its text leaves open for the appended marker to land in: only a
        # JSON string carries that marker inside a record.
        forgeries = (
            marker({_BRANCH_KEY: _ATTACKER_BRANCH, _DEV_AGENT_KEY: "pwn"}),
            *(PINNED_STATE_TEMPLATE.format(payload=payload) for payload in _TERMINATED_NON_OBJECTS),
            *(PINNED_STATE_TEMPLATE.format(payload=payload) for payload in _PROSE_NON_OBJECTS),
            *(PINNED_STATE_TEMPLATE.format(payload=payload) for payload in _PROSE_OBJECTS),
            f"{PINNED_STATE_MARKER} 7",
            f'{PINNED_STATE_MARKER} {{"{_BRANCH_KEY}": "{_ATTACKER_BRANCH}',
            f"{PINNED_STATE_MARKER} {_CUT_SHORT}-->",
            f"{PINNED_STATE_MARKER} {_CUT_SHORT_QUOTING}",
        )
        for forged in forgeries:
            with self.subTest(forged=forged):
                ordinary = bot_comment(1, _engine_comments._with_orch_marker(forged))

                state = state_client().read_pinned_state(make_issue(5, comments=[ordinary]))

                # No real state comment exists yet, so nothing is adopted.
                self.assertEqual((state.comment_id, state.state_data), (None, {}))

    def test_marker_embedded_in_prose_is_not_state(self) -> None:
        forged = marker({"pr_number": 999})
        ordinary = bot_comment(
            1,
            f"decomposer says this fits one context {forged}",
        )
        issue = make_issue(5, comments=[ordinary])

        client = state_client()
        state = client.read_pinned_state(issue)

        self.assertIsNone(state.comment_id)
        self.assertEqual(state.state_data, {})

    def test_a_non_object_payload_is_not_a_reading(self) -> None:
        # Valid JSON the bot could have written that no state can be read out
        # of -- a truncated write, a hand-edited comment -- and JSON the decoder
        # will not build at all. The comment is still identified -- the id is
        # what keeps both writers off it, and a replacement from being posted
        # beside it -- but the empty payload standing in for it is not offered
        # as a reading, since an issue that recorded nothing resolves to
        # exactly the same `{}`.
        client = state_client()
        corrupted = (
            "[]", '"x"', "7", "null", *_TERMINATED_NON_OBJECTS, *_QUOTING_NON_OBJECTS, *_UNDECODABLE.values(),
        )
        for payload in corrupted:
            with self.subTest(payload=payload):
                corrupt = bot_comment(
                    _PINNED_COMMENT_ID,
                    PINNED_STATE_TEMPLATE.format(payload=payload),
                )

                state = client.read_pinned_state(
                    make_issue(5, comments=[corrupt]),
                )

                self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
                self.assertEqual(state.state_data, {})
                self.assertFalse(state.parsed)

    def test_embedded_marker_cannot_shadow_state(self) -> None:
        # An ordinary comment ahead of the record, its text opening on a forged
        # marker -- an object's, or prose shaped as one: it authenticates as no
        # record, so the record behind it is the one every reader takes.
        forgeries = (
            marker({_BRANCH_KEY: _ATTACKER_BRANCH}),
            *(PINNED_STATE_TEMPLATE.format(payload=payload) for payload in _PROSE_OBJECTS),
        )
        for forged in forgeries:
            with self.subTest(forged=forged):
                ordinary = bot_comment(1, _engine_comments._with_orch_marker(forged))
                thread = [ordinary, bot_comment(_PINNED_COMMENT_ID, marker({_BRANCH_KEY: REAL_BRANCH}))]

                state = state_client().read_pinned_state(make_issue(5, comments=thread))

                self.assertIs(admit_pinned_comment(ordinary, trusted_login=BOT).status, AdmissionStatus.NO_COMMENT)
                self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
                self.assertEqual(state.get(_BRANCH_KEY), REAL_BRANCH)


class CommentsAfterExcludesStateTest(unittest.TestCase):
    """Which comment the thread read leaves out, and how it decides.

    Two questions wear the same answer most of the time and are not the same
    question. A reader after CONVERSATION wants the pinned comment gone and
    has no id to name it by, so the marker in a body stands in. A reader after
    a receipt it posted itself can name that comment -- and must, because the
    marker test also hides every comment merely QUOTING the marker, which is
    exactly what a notice explaining this orchestrator's own state comment
    does.
    """

    def test_the_marker_stands_in_for_no_id(self) -> None:
        issue = make_issue(5, comments=[
            bot_comment(1, marker({_BRANCH_KEY: REAL_BRANCH})),
            bot_comment(2, _QUOTING_BODY),
        ])

        read = state_client().comments_after(issue, None)

        self.assertEqual([issue_comment.id for issue_comment in read], [])

    def test_a_named_state_leaves_a_quote_visible(self) -> None:
        # The receipt case: the pinned comment goes by id, and the sentence
        # quoting its marker is the one comment the caller is looking for.
        issue = make_issue(5, comments=[
            bot_comment(1, marker({_BRANCH_KEY: REAL_BRANCH})),
            bot_comment(2, _QUOTING_BODY),
        ])

        read = state_client().comments_after(issue, None, state_comment_id=1)

        self.assertEqual([issue_comment.id for issue_comment in read], [2])

    def test_a_named_state_is_cut_by_id_alone(self) -> None:
        # The id is the whole answer where the caller names one: the pinned
        # comment edited into prose is still not conversation.
        issue = make_issue(5, comments=[
            bot_comment(1, "the state was here"),
            bot_comment(2, "said afterwards"),
        ])

        read = state_client().comments_after(issue, None, state_comment_id=1)

        self.assertEqual([issue_comment.id for issue_comment in read], [2])

    def test_the_watermark_still_bounds_it(self) -> None:
        issue = make_issue(5, comments=[
            bot_comment(1, marker({_BRANCH_KEY: REAL_BRANCH})),
            bot_comment(2, _QUOTING_BODY),
            bot_comment(3, "said afterwards"),
        ])

        read = state_client().comments_after(issue, 2, state_comment_id=1)

        self.assertEqual([issue_comment.id for issue_comment in read], [3])


class PinnedStatePayloadTest(unittest.TestCase):
    """`state_data` is the one name the payload goes by, as keyword and as attribute.

    A state is built from keywords alone, and nothing answers to another
    spelling of the payload: a `data` keyword or attribute fails where it is
    used rather than reaching the record under a second name.
    """

    def test_state_data_is_the_payload(self) -> None:
        state_data = {_BRANCH_KEY: REAL_BRANCH}

        state = PinnedState(state_data=state_data)

        self.assertIs(state.state_data, state_data)
        self.assertEqual(state.get(_BRANCH_KEY), REAL_BRANCH)

    def test_no_other_spelling_reaches_it(self) -> None:
        with self.assertRaises(TypeError):
            PinnedState(data={})
        with self.assertRaises(TypeError):
            PinnedState(_PINNED_COMMENT_ID, {})
        self.assertFalse(hasattr(PinnedState(), "data"))


class PinnedAdmissionMatrixTest(unittest.TestCase):
    """The admission contract for pinned comments: authentication first, then schema admission."""

    def setUp(self) -> None:
        self.client = state_client()

    def test_admit_no_comment(self) -> None:
        no_marker = bot_comment(_PINNED_COMMENT_ID, "just an ordinary comment")
        self.assertEqual(
            admit_pinned_comment(no_marker, trusted_login=BOT).status,
            AdmissionStatus.NO_COMMENT,
        )

        foreign_author = FakeComment(
            id=1,
            body=marker({_SCHEMA_VERSION: 1}),
            user=FakeUser(_ATTACKER_LOGIN),
        )
        self.assertEqual(
            admit_pinned_comment(foreign_author, trusted_login=BOT).status,
            AdmissionStatus.NO_COMMENT,
        )

        embedded = bot_comment(
            _PINNED_COMMENT_ID,
            f"prose text {marker({_SCHEMA_VERSION: 1})}",
        )
        self.assertEqual(
            admit_pinned_comment(embedded, trusted_login=BOT).status,
            AdmissionStatus.NO_COMMENT,
        )

    def test_admit_malformed(self) -> None:
        # A payload the decoder will not build is refused with the identity a
        # caller reports it by, never raised out of admission, however far
        # inside the comment's capacity it is.
        for case, payload in _UNDECODABLE.items():
            with self.subTest(case=case):
                comment = bot_comment(_PINNED_COMMENT_ID, PINNED_STATE_TEMPLATE.format(payload=payload))
                admission = admit_pinned_comment(comment, trusted_login=BOT, issue_number=5, repo_slug=_REPO)
                self.assertEqual(
                    (admission.status, admission.comment_id, admission.issue_number, admission.repo_slug),
                    (AdmissionStatus.MALFORMED, _PINNED_COMMENT_ID, 5, _REPO),
                )
                self.assertTrue(admission.refusal_reason.startswith("malformed JSON ("))

        for non_object in _NON_OBJECTS:
            with self.subTest(non_object=non_object):
                comment = bot_comment(_PINNED_COMMENT_ID, PINNED_STATE_TEMPLATE.format(payload=non_object))
                admission = admit_pinned_comment(comment, trusted_login=BOT)
                self.assertEqual(admission.status, AdmissionStatus.MALFORMED)
                self.assertTrue(admission.is_refused)
                self.assertFalse(admission.is_supported)

    def test_admit_unsupported(self) -> None:
        unsupported_versions = (
            (None, "missing schema_version"),
            (True, "boolean rather than integer"),
            (False, "boolean rather than integer"),
            ("1", "str rather than integer"),
            (1.0, "float rather than integer"),
            (1.5, "float rather than integer"),
            (0, "unsupported schema_version 0 (supported: 1)"),
            (2, "unsupported schema_version 2 (supported: 1)"),
            (-1, "unsupported schema_version -1 (supported: 1)"),
            (99, "unsupported schema_version 99 (supported: 1)"),
        )
        for version, expected_reason in unsupported_versions:
            with self.subTest(version=version):
                payload = {} if version is None else {_SCHEMA_VERSION: version}
                admission = admit_pinned_comment(
                    bot_comment(_PINNED_COMMENT_ID, marker(payload, raw=True)),
                    trusted_login=BOT,
                )
                self.assertEqual(
                    (admission.status, admission.is_refused, admission.is_supported, admission.found_version),
                    (AdmissionStatus.UNSUPPORTED, True, False, version),
                )
                self.assertIn(expected_reason, admission.refusal_reason)

    def test_admit_supported(self) -> None:
        legit = bot_comment(_PINNED_COMMENT_ID, marker({_SCHEMA_VERSION: 1, "branch": REAL_BRANCH}))
        supported_admission = admit_pinned_comment(legit, trusted_login=BOT)
        self.assertEqual(supported_admission.status, AdmissionStatus.SUPPORTED)
        self.assertTrue(supported_admission.is_supported)
        self.assertFalse(supported_admission.is_refused)
        self.assertEqual(supported_admission.found_version, 1)
        self.assertEqual(supported_admission.supported_version, 1)
        self.assertIsNotNone(supported_admission.state)
        self.assertEqual(supported_admission.state.get("branch"), REAL_BRANCH)

        # The reader's nesting bound is the recursion limit itself: a record
        # that nests exactly that deep is still the state.
        at_the_limit = bot_comment(
            _PINNED_COMMENT_ID,
            PINNED_STATE_TEMPLATE.format(payload=f'{{"schema_version": 1, "x": {_LIMIT_ARRAY}}}'),
        )
        self.assertEqual(admit_pinned_comment(at_the_limit, trusted_login=BOT).status, AdmissionStatus.SUPPORTED)

    def test_author_gate_before_admission(self) -> None:
        foreign_v2 = FakeComment(
            id=1,
            body=marker({_SCHEMA_VERSION: 2, _BRANCH_KEY: _ATTACKER_BRANCH}),
            user=FakeUser(_ATTACKER_LOGIN),
        )
        legit = bot_comment(
            _PINNED_COMMENT_ID,
            marker({_SCHEMA_VERSION: 1, _BRANCH_KEY: REAL_BRANCH}),
        )
        issue = make_issue(5, comments=[foreign_v2, legit])

        state = self.client.read_pinned_state(issue)
        self.assertEqual(state.comment_id, _PINNED_COMMENT_ID)
        self.assertTrue(state.supported)
        self.assertEqual(state.get(_BRANCH_KEY), REAL_BRANCH)

    def test_admission_identity_and_refusal(self) -> None:
        issue = make_issue(
            5,
            comments=[bot_comment(_PINNED_COMMENT_ID, marker({_SCHEMA_VERSION: 2, "field": "value"}))],
        )
        admission = admit_pinned_comment(issue.comments[0], trusted_login=BOT, issue_number=5)
        self.assertEqual(
            (
                admission.status,
                admission.comment_id,
                admission.found_version,
                admission.supported_version,
                admission.issue_number,
            ),
            (AdmissionStatus.UNSUPPORTED, _PINNED_COMMENT_ID, 2, SUPPORTED_SCHEMA_VERSION, 5),
        )
        self.assertIn("unsupported schema_version 2", admission.refusal_reason)

        state = self.client.read_pinned_state(issue)
        self.assertEqual(
            (
                state.comment_id,
                state.supported,
                state.parsed,
                state.state_data,
                state.found_version,
                state.supported_version,
                state.issue_number,
            ),
            (_PINNED_COMMENT_ID, False, True, {}, 2, SUPPORTED_SCHEMA_VERSION, 5),
        )
        self.assertIn("unsupported schema_version 2", state.refusal_reason)
        candidates = ({_SCHEMA_VERSION: 1}, {_SCHEMA_VERSION: 2, "field": "value"}, {})
        self.assertFalse(any(state.reads_as(candidate) for candidate in candidates))


if __name__ == "__main__":
    unittest.main()
