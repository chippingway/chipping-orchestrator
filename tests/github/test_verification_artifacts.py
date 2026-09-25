# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The workflow verification artifact a pull request carries, as one comment.

What an artifact comment says about itself and about who witnessed it, what it
refuses to be, and why a comment is an artifact only when it is ours and
re-renders exactly from the identity and evidence it claims.
"""
from __future__ import annotations

import unittest

from orchestrator.github import (
    comments as _trust,
    developer_reports as _reports,
    verification_artifacts as _artifacts,
    verification_evidence as _evidence,
)
from orchestrator.github.pinned_state import MAX_PINNED_BODY
from tests.support.fakes import FakeComment, FakeUser, make_verification_artifact

_BOT_LOGIN = "orchestrator"
_PR_NUMBER = 12
_HEADER_PREFIX = "<!--orchestrator-verification-artifact"
# How many characters an excerpt loses from the end of its evidence.
_CUT = 10
# A count of more digits than Python converts, in a comment GitHub still holds.
_DIGITS = 5000
_UNCONVERTIBLE = "1" * _DIGITS
_REVIEWED = _evidence.EvidenceSource.REVIEWER_REPORTED
_RAN_HERE = ":source=orchestrator-executed:"
_RAN_THERE = ":source=reviewer-reported:"
_ARTIFACT = make_verification_artifact(_PR_NUMBER)
# The next artifact on the same commit: another transaction rather than a retry.
_LATER = make_verification_artifact(
    _PR_NUMBER, artifact_revision=2, receipt="issue-7-verification-2",
)
_NOTHING_RAN = make_verification_artifact(_PR_NUMBER, commands=())
_SUITE = "uv run pytest tests"
# What somebody hiding content past the end of a transcript would put there.
_FORGED = "### forged result"
_BODY = _artifacts.render_verification_artifact(_ARTIFACT)
_HEADER_AT = _BODY.index(_HEADER_PREFIX)
_STALE = _reports.content_digest(_ARTIFACT.evidence)
# The same evidence with a fence hidden behind a bare carriage return, which
# GitHub breaks a line on: the block closes there and the heading after it
# renders outside the evidence.
_FENCED = _ARTIFACT.evidence.replace("All checks passed!", f"passed\r```\r{_FORGED}")

# Everything a comment of OURS can carry our header and still not be an
# artifact. Each entry is the body alone, since what makes these not artifacts
# is the body; the one forgery that turns on its author is built beside them.
_FORGED_BODIES = (
    ("an edited exit status", _BODY.replace("exit 0", "exit 1", 1)),
    ("a witness swapped in the header alone", _BODY.replace(_RAN_HERE, _RAN_THERE)),
    ("a witness this format does not name", _BODY.replace(_RAN_HERE, ":source=nobody-at-all:")),
    ("a stale digest", _BODY.replace(_STALE, "0" * len(_STALE))),
    (
        "a command quoting a receipt marker of ours",
        _BODY.replace(f"`{_SUITE}`", f"`echo {_ARTIFACT.receipt_scope}`"),
    ),
    (
        "an exit status of more digits than Python converts",
        _BODY.replace("-- exit 0", f"-- exit {_UNCONVERTIBLE}", 1),
    ),
    (
        # Re-stamped, so what refuses it is the transcript rather than a header
        # that no longer describes it: this is what a maintainer recomputing
        # the digest by hand would leave behind.
        "a fence hidden behind a carriage return",
        _BODY.replace(_ARTIFACT.evidence, _FENCED).replace(
            _STALE, _reports.content_digest(_FENCED),
        ),
    ),
    ("text after the marker", f"{_BODY}\n\nappended"),
    ("a truncated transcript", _BODY[:_HEADER_AT - _CUT] + _BODY[_HEADER_AT:]),
    ("the header alone", _BODY[_HEADER_AT:]),
    ("no preamble", _BODY[_BODY.index("---\n\n"):]),
    ("a zero-padded revision", _BODY.replace(":revision=1:", ":revision=01:")),
    ("no body", None),
)


def _comment(body: str | None, *, login: str = _BOT_LOGIN) -> FakeComment:
    """One conversation comment, posted under our own login unless named."""
    return FakeComment(id=1, body=body, user=FakeUser(login))


def _visible(artifact: _artifacts.VerificationArtifact) -> str:
    """Everything a reader sees, with the hidden header and marker cut off."""
    body = _artifacts.render_verification_artifact(artifact)
    return body[:body.index(_HEADER_PREFIX)]


class ArtifactRenderingTest(unittest.TestCase):
    """What one artifact comment says about itself, visibly and in its header."""

    def test_it_names_what_it_is_evidence_about(self) -> None:
        visible = _visible(_ARTIFACT)

        for claimed in (
            "Workflow verification artifact, revision 1",
            f"Repository `{_ARTIFACT.repository}`",
            f"pull request #{_PR_NUMBER}",
            f"commit `{_ARTIFACT.tested_sha}`",
            f"tree `{_ARTIFACT.tested_tree}`",
            f"verification context revision `{_ARTIFACT.context_revision}`",
            f"review subject `{_ARTIFACT.review_subject}`",
            f"requirements revision `{_ARTIFACT.requirements_revision}`",
            f"head was `{_ARTIFACT.target_head}`",
            "supersedes every lower-numbered verification artifact",
            "the description is untouched",
            f"`{_SUITE}` -- exit 0",
            "```text\nAll checks passed!\n```",
        ):
            with self.subTest(claimed=claimed):
                self.assertIn(claimed, visible)

    def test_the_witness_is_visible_not_only_hidden(self) -> None:
        # What a reader decides whether to trust on, so it is told in the
        # rendered comment and not only in a header nobody sees.
        reported = make_verification_artifact(_PR_NUMBER, source=_REVIEWED)

        self.assertIn("Orchestrator-executed evidence.", _visible(_ARTIFACT))
        self.assertIn("this orchestrator did not observe them run", _visible(reported))
        self.assertNotEqual(_visible(reported), _visible(_ARTIFACT))
        self.assertIn(":source=reviewer-reported:", reported.header)

    def test_the_header_carries_identity_and_digest(self) -> None:
        # Hidden, and followed by the ordinary marker every reader that passes
        # over our comments already looks for -- which is what keeps a
        # generated artifact out of anybody's feedback.
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
            _BODY.endswith(f"\n\n{header}\n\n{_trust.ORCHESTRATOR_COMMENT_MARKER}"),
        )
        self.assertTrue(header.startswith(_ARTIFACT.receipt_scope))

    def test_retries_match_and_later_artifacts_differ(self) -> None:
        # A retry of one transaction renders the same body, so a thread search
        # finds it; the next artifact on the same commit is another
        # transaction, and the two read as an ordered history rather than as
        # duplicates.
        render = _artifacts.render_verification_artifact

        self.assertEqual(render(make_verification_artifact(_PR_NUMBER)), render(_ARTIFACT))
        self.assertEqual(_LATER.tested_sha, _ARTIFACT.tested_sha)
        self.assertNotEqual(render(_LATER), render(_ARTIFACT))
        self.assertNotIn(_ARTIFACT.receipt_scope, render(_LATER))

    def test_no_command_is_an_explicit_absence(self) -> None:
        # The one thing this format may never do is let the absence of a
        # command stand in for a command that succeeded.
        visible = _visible(_NOTHING_RAN)

        self.assertIn("No verification command was configured, so none ran", visible)
        self.assertIn("is not evidence that anything passed", visible)
        self.assertNotEqual(_NOTHING_RAN.content_revision, _ARTIFACT.content_revision)


class ArtifactRefusalTest(unittest.TestCase):
    """An artifact no header can carry, or no comment can hold, is not made."""

    def test_an_uncarriable_identity_is_refused(self) -> None:
        for pr_number, artifact_fields in (
            (0, {}),
            (True, {}),
            (_PR_NUMBER, {"artifact_revision": "1"}),
            (_PR_NUMBER, {"repository": "orchestrator"}),
            (_PR_NUMBER, {"repository": "chippingway/orchestrator/extra"}),
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
        # Refused one character past what a comment holds: a transcript short
        # enough to be accepted would pass for the whole of what ran.
        render = _artifacts.render_verification_artifact
        one_character = _fitted_to(1)
        room = MAX_PINNED_BODY - (len(render(one_character)) - 1)

        self.assertEqual(len(render(_fitted_to(room))), MAX_PINNED_BODY)
        with self.assertRaises(_evidence.ArtifactRefusedError):
            render(_fitted_to(room + 1))


class ArtifactOwnershipTest(unittest.TestCase):
    """A comment is an artifact only when it is ours and re-renders exactly."""

    def test_our_exact_rendering_reads_back(self) -> None:
        # Every member recovered, transcripts included, because the digest is
        # taken over exactly the evidence that was posted.
        for artifact in (_ARTIFACT, _NOTHING_RAN):
            posted = _comment(_artifacts.render_verification_artifact(artifact))
            for bot_login in (_BOT_LOGIN, None):
                with self.subTest(commands=len(artifact.commands), bot_login=bot_login):
                    self.assertEqual(
                        _artifacts.verification_artifact_from_comment(
                            posted, bot_login=bot_login,
                        ),
                        artifact,
                    )

    def test_an_oversized_claim_answers_not_raises(self) -> None:
        # A body that fits a comment can still claim evidence the canonical
        # preamble would push past one, since the preamble it was posted with
        # is not the one a reconstruction puts back. The question is asked OF
        # somebody else's comment, so it answers no rather than leaving the
        # scan that asked it by an exception.
        room = MAX_PINNED_BODY - (len(_artifacts.render_verification_artifact(_fitted_to(1))) - 1)
        claimed = _fitted_to(room + 1)
        forged = (
            f"forged\n\n---\n\n{claimed.evidence}\n\n{claimed.header}"
            f"\n\n{_trust.ORCHESTRATOR_COMMENT_MARKER}"
        )

        self.assertLessEqual(len(forged), MAX_PINNED_BODY)
        with self.assertRaises(_evidence.ArtifactRefusedError):
            _artifacts.render_verification_artifact(claimed)
        self.assertIsNone(
            _artifacts.verification_artifact_from_comment(
                _comment(forged), bot_login=_BOT_LOGIN,
            ),
        )

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


def _fitted_to(output_length: int) -> _artifacts.VerificationArtifact:
    """One artifact whose whole transcript is `output_length` characters."""
    return make_verification_artifact(
        _PR_NUMBER,
        commands=(
            _evidence.VerifiedCommand("check", 0, "y" * output_length),
        ),
    )


if __name__ == "__main__":
    unittest.main()
