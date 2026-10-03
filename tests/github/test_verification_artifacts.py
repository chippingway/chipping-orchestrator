# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The workflow verification artifact a pull request carries, as one comment.

What a compact artifact comment says about itself in its visible summary and
its hidden header, and what it keeps only in its hidden payload; what it
refuses to be; why a comment is an artifact only when it is ours and
re-renders exactly, in its own format, from the identity and evidence it
claims; and that a comment published in the legacy format reads back as the
artifact it was, exactly as it was posted.
"""
from __future__ import annotations

import unittest

from orchestrator.github import (
    comments as _trust,
    developer_reports as _reports,
    verification_artifacts as _artifacts,
    verification_evidence as _evidence,
    verification_payloads as _payloads,
)
from orchestrator.github.pinned_state import MAX_PINNED_BODY
from tests.support.fakes import FakeComment, FakeUser, make_verification_artifact
from tests.support.github import legacy_artifacts as _legacy

_BOT_LOGIN = "orchestrator"
_PR_NUMBER = 12
_HEADER_PREFIX = "<!--orchestrator-verification-artifact"
_PAYLOAD_PREFIX = "<!--orchestrator-verification-evidence "
_CLOSE = "-->"
# How many characters an excerpt loses from the end of what it cuts.
_CUT = 10
# A count of more digits than Python converts, in a comment GitHub still holds.
_DIGITS = 5000
_UNCONVERTIBLE = "1" * _DIGITS
_REVIEWED = _evidence.EvidenceSource.REVIEWER_REPORTED
_RAN_HERE = ":source=orchestrator-executed:"
_RAN_THERE = ":source=reviewer-reported:"
_PASSING_STATUS = '"exit_status":0'
_SUITE = "uv run pytest tests"
_LINT = "uv run ruff check orchestrator tests"
_TRANSCRIPT = "All checks passed!"
# One character a transcript carries as itself and the payload as a six-character escape.
_ACCENTED = "\u00e9"
_ESCAPE_WIDTH = len(r"\u00e9")
_ARTIFACT = make_verification_artifact(_PR_NUMBER)
# The next artifact on the same commit: another transaction rather than a retry.
_LATER = make_verification_artifact(
    _PR_NUMBER, artifact_revision=2, receipt="issue-7-verification-2",
)
_NOTHING_RAN = make_verification_artifact(_PR_NUMBER, commands=())
# The suite failing beside the linter passing.
_FAILING = make_verification_artifact(
    _PR_NUMBER,
    commands=(_evidence.VerifiedCommand(_SUITE, 1, "1 failed"), _ARTIFACT.commands[1]),
)
# The same evidence on the very head it ran on, and witnessed by a reviewer.
_RAN_THERE_ARTIFACT = make_verification_artifact(_PR_NUMBER, target_head=_ARTIFACT.tested_sha)
_REPORTED = make_verification_artifact(_PR_NUMBER, source=_REVIEWED)
_BODY = _artifacts.render_verification_artifact(_ARTIFACT)
_HEADER_AT = _BODY.index(_HEADER_PREFIX)
_PAYLOAD = _payloads.encode_evidence(_ARTIFACT.commands)
_FAILING_PAYLOAD = _payloads.encode_evidence(_FAILING.commands)
_STALE = _reports.content_digest(_ARTIFACT.evidence)
_ZEROED = "0" * len(_STALE)
_FAILING_DIGEST = _FAILING.content_revision
_PASSED_LINE = ":heavy_check_mark: **Passed:** 2 of 2 recorded checks exited 0."
_FAILED_LINE = ":x: **Failed:** 1 of 2 recorded checks did not exit 0."
_ABSENT_LINE = (
    ":warning: **Not verified:** no check ran, so this artifact records that "
    "absence and is not evidence that anything passed."
)
_EXECUTED_LINE = (
    "- **Source:** :robot: orchestrator-executed. This orchestrator ran the "
    "checks itself and observed the status each exited with."
)
_REPORTED_LINE = (
    "- **Source:** :eyes: reviewer-reported. A reviewer run reported the checks; "
    "this orchestrator did not observe them run."
)
_CARRIED_LINE = (
    f"- **Target head:** `{_ARTIFACT.target_head}`, an equivalent-tree carry: a "
    "different commit proved to carry the same tree. The checks ran on the "
    "tested commit, not on this head."
)
_RAN_THERE_LINE = f"- **Target head:** `{_ARTIFACT.tested_sha}`, the tested commit itself."
# What somebody hiding content past the end of a transcript would put there.
_FORGED = "### forged result"

# Everything a comment of OURS can carry our header in the compact format and
# still not be an artifact. Each entry is the body alone, since what makes
# these not artifacts is the body; the one forgery that turns on its author is
# built beside them.
_FORGED_BODIES = (
    ("a status edited in the payload", _BODY.replace(_PASSING_STATUS, '"exit_status":1', 1)),
    ("a transcript edited in the payload", _BODY.replace(_TRANSCRIPT, "All checks failed!")),
    ("another run's payload under this header", _BODY.replace(_PAYLOAD, _FAILING_PAYLOAD)),
    (
        # Payload and header agree with each other; the summary still names
        # the evidence they replaced, and says it passed.
        "a header re-stamped for another run's payload",
        _BODY.replace(_PAYLOAD, _FAILING_PAYLOAD).replace(f"content={_STALE}", f"content={_FAILING_DIGEST}"),
    ),
    (
        "a failing run whose summary says it passed",
        _artifacts.render_verification_artifact(_FAILING).replace(_FAILED_LINE, _PASSED_LINE),
    ),
    ("a payload of another version", _BODY.replace('{"version":1,', '{"version":2,')),
    ("a payload closed early", _BODY.replace(_TRANSCRIPT, f"All checks {_CLOSE} passed")),
    ("a payload cut short", _BODY.replace(_PAYLOAD, _PAYLOAD[:-_CUT])),
    ("no payload", _BODY.replace(f"{_PAYLOAD_PREFIX}{_PAYLOAD}{_CLOSE}\n\n", "")),
    (
        "an exit status of more digits than Python converts",
        _BODY.replace(_PASSING_STATUS, f'"exit_status":{_UNCONVERTIBLE}', 1),
    ),
    ("a witness swapped in the header alone", _BODY.replace(_RAN_HERE, _RAN_THERE)),
    ("a witness swapped in the summary alone", _BODY.replace(_EXECUTED_LINE, _REPORTED_LINE)),
    ("a witness this format does not name", _BODY.replace(_RAN_HERE, ":source=nobody-at-all:")),
    ("a carry named a run on its head", _BODY.replace(_CARRIED_LINE, _RAN_THERE_LINE)),
    (
        "a header naming the head as the tested commit",
        _BODY.replace(f":head={_ARTIFACT.target_head}:", f":head={_ARTIFACT.tested_sha}:"),
    ),
    ("a stale digest", _BODY.replace(_STALE, _ZEROED)),
    ("text after the marker", f"{_BODY}\n\nappended"),
    ("the header alone", _BODY[_HEADER_AT:]),
    ("a zero-padded revision", _BODY.replace(":revision=1:", ":revision=01:")),
    ("no body", None),
)

# The same evidence with a fence hidden behind a bare carriage return, which
# GitHub breaks a line on: the block closes there and the heading after it
# renders outside the evidence.
_FENCED = _ARTIFACT.evidence.replace(_TRANSCRIPT, f"passed\r```\r{_FORGED}")
_LEGACY_HEADER_AT = _legacy.CARRIED.index(_HEADER_PREFIX)

# What the legacy format refuses of a comment of ours, over a comment it
# published: the same exact re-rendering, held to that format's own body.
_LEGACY_FORGERIES = (
    ("an edited exit status", _legacy.CARRIED.replace("exit 0", "exit 1", 1)),
    ("a witness swapped in the header alone", _legacy.CARRIED.replace(_RAN_HERE, _RAN_THERE)),
    ("a stale digest", _legacy.CARRIED.replace(_STALE, _ZEROED)),
    (
        "a command quoting a receipt marker of ours",
        _legacy.CARRIED.replace(f"`{_SUITE}`", f"`echo {_ARTIFACT.receipt_scope}`"),
    ),
    (
        "an exit status of more digits than Python converts",
        _legacy.CARRIED.replace("-- exit 0", f"-- exit {_UNCONVERTIBLE}", 1),
    ),
    (
        # Re-stamped, so what refuses it is the transcript rather than a header
        # that no longer describes it: this is what a maintainer recomputing
        # the digest by hand would leave behind.
        "a fence hidden behind a carriage return",
        _legacy.CARRIED.replace(_ARTIFACT.evidence, _FENCED).replace(
            _STALE, _reports.content_digest(_FENCED),
        ),
    ),
    # A lone surrogate, which reads back out of a body but has no digest.
    ("text UTF-8 cannot carry", _legacy.CARRIED.replace(_TRANSCRIPT, "All checks \ud800")),
    (
        "a hidden payload beside the visible evidence",
        _legacy.CARRIED.replace(
            "\n\n<!--orchestrator-verification-artifact",
            f"\n\n{_PAYLOAD_PREFIX}{_PAYLOAD}{_CLOSE}\n\n<!--orchestrator-verification-artifact",
        ),
    ),
    ("text after the marker", f"{_legacy.CARRIED}\n\nappended"),
    (
        "a truncated transcript",
        _legacy.CARRIED[:_LEGACY_HEADER_AT - _CUT] + _legacy.CARRIED[_LEGACY_HEADER_AT:],
    ),
    ("no preamble", _legacy.CARRIED[_legacy.CARRIED.index("---\n\n"):]),
)


def _comment(body: str | None, *, login: str = _BOT_LOGIN) -> FakeComment:
    """One conversation comment, posted under our own login unless named."""
    return FakeComment(id=1, body=body, user=FakeUser(login))


def _read(body: str | None, *, bot_login: str | None = _BOT_LOGIN) -> _artifacts.VerificationArtifact | None:
    """What a comment of ours carrying `body` reads back as."""
    return _artifacts.verification_artifact_from_comment(_comment(body), bot_login=bot_login)


class CompactRenderingTest(unittest.TestCase):
    """What one compact artifact says visibly, and what it keeps hidden."""

    def test_it_summarizes_rather_than_lists(self) -> None:
        # The outcome, both revisions, the witness, the tested commit, and the
        # head, and not one command or transcript: those are the payload's,
        # every one of them exactly, under the revision the summary names.
        visible = _BODY[:_BODY.index(_PAYLOAD_PREFIX)]

        for claimed in (
            "### :microscope: Workflow verification artifact, revision 1\n\n",
            f"\n\n{_PASSED_LINE}\n\n",
            _EXECUTED_LINE,
            f"- **Evidence revision:** `sha256:{_ARTIFACT.content_revision}`",
            f"- **Tested commit:** `{_ARTIFACT.tested_sha}` (tree `{_ARTIFACT.tested_tree}`)",
            _CARRIED_LINE,
            "kept in this comment's hidden evidence payload",
            "supersedes every lower-numbered verification artifact",
        ):
            with self.subTest(claimed=claimed):
                self.assertIn(claimed, visible)
        for listed in (_SUITE, _LINT, _TRANSCRIPT, "-- exit", "```"):
            with self.subTest(listed=listed):
                self.assertNotIn(listed, visible)
        self.assertIn(f"\n\n{_PAYLOAD_PREFIX}{_PAYLOAD}{_CLOSE}\n\n", _BODY)
        self.assertEqual(_payloads.decode_evidence(_PAYLOAD), _ARTIFACT.commands)
        self.assertEqual(_ARTIFACT.summary, visible.removesuffix("\n\n"))

    def test_outcomes_and_witnesses_are_told_apart(self) -> None:
        # Passing, failing, and absent evidence each say what they are and
        # nothing another says, and so do the two witnesses; a carried head
        # says it was carried, and a head the checks ran on says that.
        for artifact, said, unsaid in (
            (_ARTIFACT, (_PASSED_LINE, _EXECUTED_LINE, _CARRIED_LINE), (_FAILED_LINE, _ABSENT_LINE)),
            (_FAILING, (_FAILED_LINE,), (_PASSED_LINE, _ABSENT_LINE)),
            (_NOTHING_RAN, (_ABSENT_LINE,), (_PASSED_LINE, _FAILED_LINE)),
            (_REPORTED, (_REPORTED_LINE,), (_EXECUTED_LINE,)),
            (_RAN_THERE_ARTIFACT, (_RAN_THERE_LINE,), (_CARRIED_LINE, "equivalent-tree")),
        ):
            visible = artifact.summary
            with self.subTest(said=said[0]):
                self.assertEqual([line for line in said if line not in visible], [])
                self.assertEqual([line for line in unsaid if line in visible], [])
        self.assertIn(_RAN_THERE, _REPORTED.header)

    def test_the_header_carries_identity_and_digest(self) -> None:
        # Hidden, after the payload, and followed by the ordinary marker every
        # reader that passes over our comments already looks for -- which is
        # what keeps a generated artifact out of anybody's feedback. The digest
        # is the one the rendered evidence has always been settled under.
        header = (
            f"{_HEADER_PREFIX}:receipt={_ARTIFACT.receipt}:pr={_PR_NUMBER}"
            f":revision=1:source=orchestrator-executed"
            f":repository={_ARTIFACT.repository}:tested={_ARTIFACT.tested_sha}"
            f":tree={_ARTIFACT.tested_tree}:head={_ARTIFACT.target_head}"
            f":subject={_ARTIFACT.review_subject}"
            f":requirements={_ARTIFACT.requirements_revision}"
            f":context={_ARTIFACT.context_revision}"
            f":content={_reports.content_digest(_ARTIFACT.evidence)}-->"
        )
        self.assertEqual(_ARTIFACT.header, header)
        self.assertTrue(
            _BODY.endswith(f"{_CLOSE}\n\n{header}\n\n{_trust.ORCHESTRATOR_COMMENT_MARKER}"),
        )
        self.assertTrue(header.startswith(_ARTIFACT.receipt_scope))

    def test_retries_match_and_later_artifacts_differ(self) -> None:
        # A retry of one transaction renders the same body, so a thread search
        # finds it; the next artifact on the same commit is another
        # transaction, and the two read as an ordered history rather than as
        # duplicates.
        render = _artifacts.render_verification_artifact

        self.assertEqual(render(make_verification_artifact(_PR_NUMBER)), _BODY)
        self.assertEqual(_LATER.tested_sha, _ARTIFACT.tested_sha)
        self.assertIn("Workflow verification artifact, revision 2", render(_LATER))
        self.assertNotIn(_ARTIFACT.receipt_scope, render(_LATER))


class ArtifactRefusalTest(unittest.TestCase):
    """An artifact no header can carry, or no comment can hold, is not made."""

    def test_an_uncarriable_identity_is_refused(self) -> None:
        for pr_number, artifact_fields in (
            (0, {}),
            (True, {}),
            (_PR_NUMBER, {"artifact_revision": "1"}),
            (_PR_NUMBER, {"repository": "orchestrator"}),
            (_PR_NUMBER, {"repository": "chippingway/chipping-orchestrator/extra"}),
            (_PR_NUMBER, {"tested_sha": "3f78685"}),
            (_PR_NUMBER, {"tested_tree": _ARTIFACT.tested_tree.upper()}),
            (_PR_NUMBER, {"target_head": ""}),
            (_PR_NUMBER, {"review_subject": "the latest round"}),
            (_PR_NUMBER, {"requirements_revision": "two words"}),
            (_PR_NUMBER, {"context_revision": "run-->"}),
            (_PR_NUMBER, {"receipt": "run:1"}),
            (_PR_NUMBER, {"source": "orchestrator-executed"}),
            (_PR_NUMBER, {"commands": [_ARTIFACT.commands[0]]}),
            (_PR_NUMBER, {"commands": ("uv run pytest tests",)}),
        ):
            with (
                self.subTest(pr_number=pr_number, **artifact_fields),
                self.assertRaises(_evidence.ArtifactRefusedError),
            ):
                make_verification_artifact(pr_number, **artifact_fields)

    def test_an_unreportable_command_is_refused(self) -> None:
        # Each would render back as something other than the command it names,
        # or -- the receipt marker -- as a step nobody took, since a thread is
        # searched for receipts by substring. A bare carriage return is a line
        # ending to GitHub, so a fence behind one closes the block where it
        # renders and whatever follows lands outside the evidence.
        for command, exit_status, output in (
            ("", 0, ""),
            (" \n\t", 0, ""),
            ("echo `date`", 0, ""),
            ("echo one\necho two", 0, ""),
            (f"echo {_ARTIFACT.receipt_scope}", 0, ""),
            (_SUITE, True, ""),
            (_SUITE, "0", ""),
            (_SUITE, 0, None),
            (_SUITE, 0, _trust.ORCHESTRATOR_COMMENT_MARKER),
            (_SUITE, 0, "passed\n```\nnot output"),
            (_SUITE, 0, "passed\n  ``` still closes it on GitHub"),
            (_SUITE, 0, f"passed\r```\r{_FORGED}"),
            (_SUITE, 0, "passed\r\n```"),
            ("echo one\recho two", 0, ""),
        ):
            with (
                self.subTest(command=command, exit_status=exit_status, output=output),
                self.assertRaises(_evidence.ArtifactRefusedError),
            ):
                _evidence.VerifiedCommand(command, exit_status, output)

    def test_an_oversized_artifact_is_refused_not_cut(self) -> None:
        # Refused one character past what a comment holds, measured on the
        # body posted -- escapes included, so a transcript whose rendering
        # would fit is still refused once its payload does not. A payload
        # short enough to be accepted would pass for the whole of what ran.
        room = MAX_PINNED_BODY - (len(_artifacts.render_verification_artifact(_fitted_to(1))) - 1)
        past = _fitted_to(room + 1)
        escaped = _fitted_to(room // _ESCAPE_WIDTH + 1, character=_ACCENTED)

        self.assertEqual(len(_artifacts.render_verification_artifact(_fitted_to(room))), MAX_PINNED_BODY)
        self.assertLess(len(escaped.evidence), room)
        for label, artifact in (("one character past", past), ("escaped past", escaped)):
            with self.subTest(label), self.assertRaises(_evidence.ArtifactRefusedError):
                _artifacts.render_verification_artifact(artifact)


class CompactReadBackTest(unittest.TestCase):
    """A comment is a compact artifact only when it is ours and re-renders exactly."""

    def test_our_exact_rendering_reads_back(self) -> None:
        # Every member recovered, transcripts included, out of the payload
        # alone, with or without a login to hold the author to: whatever the
        # outcome, the witness, or the head it answers for.
        for label, artifact in (
            ("passing and carried", _ARTIFACT),
            ("absent", _NOTHING_RAN),
            ("failing", _FAILING),
            ("reviewer-reported", _REPORTED),
            ("run on its head", _RAN_THERE_ARTIFACT),
        ):
            body = _artifacts.render_verification_artifact(artifact)
            for bot_login in (_BOT_LOGIN, None):
                with self.subTest(label, bot_login=bot_login):
                    self.assertEqual(_read(body, bot_login=bot_login), artifact)

    def test_an_oversized_claim_answers_not_raises(self) -> None:
        # A body that fits a comment can still claim evidence the canonical
        # presentation would push past one, since the presentation it was
        # posted with is not the one a reconstruction puts back -- in either
        # format. The question is asked OF somebody else's comment, so it
        # answers no rather than leaving the scan that asked it by an
        # exception.
        room = MAX_PINNED_BODY - (len(_artifacts.render_verification_artifact(_fitted_to(1))) - 1)
        claimed = _fitted_to(room + 1)
        hidden = f"{_PAYLOAD_PREFIX}{_payloads.encode_evidence(claimed.commands)}{_CLOSE}"
        closing = f"\n\n{claimed.header}\n\n{_trust.ORCHESTRATOR_COMMENT_MARKER}"

        with self.assertRaises(_evidence.ArtifactRefusedError):
            _artifacts.render_verification_artifact(claimed)
        for forged in (f"forged\n\n{hidden}{closing}", f"forged\n\n---\n\n{claimed.evidence}{closing}"):
            with self.subTest(payload=_PAYLOAD_PREFIX in forged):
                self.assertLessEqual(len(forged), MAX_PINNED_BODY)
                self.assertIsNone(_read(forged))

    def test_anything_else_is_not_an_artifact(self) -> None:
        # A copy anybody else pasted is ours by neither half; every other case
        # is ours and differs in the body, so none of them passes by not
        # having been changed at all.
        forgeries = [("another author's paste", _comment(_BODY, login="mallory"))]
        forgeries.extend(
            (label, _comment(forged)) for label, forged in _FORGED_BODIES
        )
        for label, comment in forgeries:
            with self.subTest(label):
                self.assertNotEqual(
                    (comment.body, comment.user.login), (_BODY, _BOT_LOGIN),
                )
                self.assertIsNone(
                    _artifacts.verification_artifact_from_comment(
                        comment, bot_login=_BOT_LOGIN,
                    ),
                )


class LegacyReadBackTest(unittest.TestCase):
    """A comment the legacy format published reads back as the artifact it was, as it stands."""

    def test_historical_comments_read_back(self) -> None:
        # Fixed text that format wrote, never this writer's: each is the
        # artifact it was posted as, under the evidence revision its header
        # was settled by, though the writer would spell it otherwise now.
        for published, artifact in (
            (_legacy.CARRIED, _ARTIFACT),
            (_legacy.FAILED, make_verification_artifact(
                _PR_NUMBER,
                source=_REVIEWED,
                target_head=_ARTIFACT.tested_sha,
                artifact_revision=2,
                receipt="issue-7-verification-2",
                commands=(_evidence.VerifiedCommand(
                    _SUITE, 1, "collected 12 items\n\n1 failed, 11 passed in 0.4s",
                ),),
            )),
            (_legacy.NOTHING_RAN, make_verification_artifact(
                _PR_NUMBER, commands=(), artifact_revision=3, receipt="issue-7-verification-3",
            )),
        ):
            for bot_login in (_BOT_LOGIN, None):
                with self.subTest(revision=artifact.artifact_revision, bot_login=bot_login):
                    self.assertEqual(_read(published, bot_login=bot_login), artifact)
                    self.assertIn(f":content={artifact.content_revision}-->", published)
                    self.assertNotEqual(_artifacts.render_verification_artifact(artifact), published)

    def test_one_past_the_compact_bound_reads_back(self) -> None:
        # A comment that format posted within one comment's room, whose
        # transcript the compact payload would escape past it: never refused
        # for what the writer would make of it now.
        room = MAX_PINNED_BODY - len(_legacy.transcribing(""))
        published = _legacy.transcribing(_ACCENTED * room)
        artifact = _read(published)

        self.assertEqual(len(published), MAX_PINNED_BODY)
        self.assertIsNotNone(artifact)
        self.assertEqual(_reports.content_digest(artifact.evidence), artifact.content_revision)
        self.assertIn(f":content={artifact.content_revision}-->", published)
        with self.assertRaises(_evidence.ArtifactRefusedError):
            _artifacts.render_verification_artifact(artifact)

    def test_a_tampered_comment_is_not_an_artifact(self) -> None:
        # Held to that format's own body, exactly: an edit no re-rendering
        # wrote is no artifact, and neither is one that would raise on the
        # way to saying so.
        for label, forged in _LEGACY_FORGERIES:
            with self.subTest(label):
                self.assertNotEqual(forged, _legacy.CARRIED)
                self.assertIsNone(_read(forged))


def _fitted_to(output_length: int, *, character: str = "y") -> _artifacts.VerificationArtifact:
    """One artifact whose whole transcript is `output_length` repeats of `character`."""
    return make_verification_artifact(
        _PR_NUMBER,
        commands=(
            _evidence.VerifiedCommand("check", 0, character * output_length),
        ),
    )


if __name__ == "__main__":
    unittest.main()
