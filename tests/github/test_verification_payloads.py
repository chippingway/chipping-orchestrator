# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The hidden payload a verification artifact's evidence is carried in.

That it carries back exactly every command the evidence model accepts, in
order and under the revision the rendered evidence is settled by; that no
transcript can end the comment it sits in or open a receipt marker of ours;
and that anything but the one spelling it writes reads as no evidence at all.
"""
from __future__ import annotations

import json
import unittest

from orchestrator.github import (
    comments as _trust,
    developer_reports as _reports,
    verification_evidence as _evidence,
    verification_payloads as _payloads,
)
from tests.support.fakes import make_verification_artifact

_PR_NUMBER = 12
_SUITE = "uv run pytest tests"
_LINT = "uv run ruff check orchestrator tests"
_PASSING = "All checks passed!"
_PASSED = _evidence.VerifiedCommand(_SUITE, 0, _PASSING)
_FAILED = _evidence.VerifiedCommand(_LINT, 1, "E501 Line too long")
# Statuses at both ends of what the model accepts: a signal, and a number far
# wider than any process exits with but still one Python spells.
_KILLED = -9
_WIDE = 10 ** 100
# A count of more digits than Python converts.
_DIGITS = 5000
_UNCONVERTIBLE = 10 ** _DIGITS
_UNCONVERTIBLE_DIGITS = "1" * _DIGITS
_UNCONVERTIBLE_STATUS = f'"exit_status":{_UNCONVERTIBLE_DIGITS}'
# Deeper than the JSON decoder recurses.
_NESTING = 100_000
_CLOSE = "-->"
_COMMANDS = "commands"
_REVISION_KEY = "content"

# Transcripts a hidden comment has to carry back exactly: every way out of the
# comment, every line ending Python or GitHub reads, what no visible fence
# could hold, and what JSON itself has to escape.
_TRANSCRIPTS = (
    "closes --> the comment",
    "closes --!> it the other way",
    "opens <!-- another one",
    "<script>alert(1)</script> &amp; <details>",
    "crlf\r\nbare cr\rnel\x85line separator\u2028paragraph\u2029end",
    "nul\x00 del\x7f escape\x1b[31m red",
    r'quotes " and \ backslashes, an escape spelled \u003e',
    "astral \U0001F600 and combining e\u0301",
    "trailing whitespace and blank lines  \n\n",
    "`inline backticks` and ~~~ tildes",
    "\n",
    "",
)

# Commands at the edge of what the model accepts, each with one transcript.
_ACCEPTED = (
    _evidence.VerifiedCommand("echo a > out.txt && cat < in.txt", 0, _TRANSCRIPTS[0]),
    _evidence.VerifiedCommand(f"echo {_CLOSE}", _KILLED, _TRANSCRIPTS[1]),
    _evidence.VerifiedCommand("echo \u2713 \U0001F600", _WIDE, _TRANSCRIPTS[2]),
    *(
        _evidence.VerifiedCommand(f"echo {index}", index, transcript)
        for index, transcript in enumerate(_TRANSCRIPTS[3:])
    ),
)

# Sequences whose order and repeats are themselves evidence.
_SEQUENCES = (
    (),
    (_PASSED,),
    (_PASSED, _FAILED),
    (_FAILED, _PASSED),
    (_PASSED, _PASSED, _FAILED, _PASSED),
    _ACCEPTED,
)

_PAYLOAD = _payloads.encode_evidence((_PASSED, _FAILED))
_REVISION = _evidence.content_revision((_PASSED, _FAILED))
_LISTED = tuple(json.loads(_PAYLOAD)[_COMMANDS])


def _spelled(document: object) -> str:
    """`document` serialized the way the codec writes one, whatever it holds."""
    serialized = json.dumps(document, separators=(",", ":"))
    return serialized.replace("<", r"\u003c").replace(">", r"\u003e")


def _altered(**members: object) -> str:
    """`_PAYLOAD` with top-level members replaced, or removed where given None."""
    document = json.loads(_PAYLOAD) | members
    kept = {name: member for name, member in document.items() if member is not None}
    return _spelled(kept)


def _with_command(**members: object) -> str:
    """`_PAYLOAD` with its first command's members replaced, the revision kept."""
    document = json.loads(_PAYLOAD)
    document[_COMMANDS][0] |= members
    return _spelled(document)


def _forged(command: str, output: str) -> str:
    """One passing command spelled as the codec would, under the revision its rendering hashes to.

    Rendered by hand rather than through the model, so it can carry what the
    model refuses and leave nothing else for a reader to refuse it by.
    """
    rendered = f"`{command}` -- exit 0"
    if output:
        rendered = f"{rendered}\n\n```text\n{output}\n```"
    return _spelled({
        "version": 1,
        _REVISION_KEY: _reports.content_digest(rendered),
        _COMMANDS: [{"command": command, "exit_status": 0, "output": output}],
    })


class PayloadEncodingTest(unittest.TestCase):
    """Every sequence the evidence model accepts is carried back exactly, inside its comment."""

    def test_every_sequence_reads_back_in_order(self) -> None:
        # Deterministic both ways, so a retry writes the payload it wrote
        # before and a reread compares it character for character.
        for sequence, commands in enumerate(_SEQUENCES):
            payload = _payloads.encode_evidence(commands)
            with self.subTest(sequence=sequence):
                self.assertEqual(_payloads.decode_evidence(payload), commands)
                self.assertEqual(_payloads.encode_evidence(commands), payload)
                self.assertEqual(
                    [tuple(ran.values()) for ran in json.loads(payload)[_COMMANDS]],
                    [(ran.command, ran.exit_status, ran.output) for ran in commands],
                )
        self.assertNotEqual(
            _payloads.encode_evidence((_PASSED, _FAILED)),
            _payloads.encode_evidence((_FAILED, _PASSED)),
        )

    def test_it_names_the_rendered_revision(self) -> None:
        # Taken over the rendered section rather than over the payload, so the
        # revision an artifact settled under is the one its payload names, and
        # empty evidence names the explicit absence it renders as.
        for sequence, commands in enumerate(_SEQUENCES):
            artifact = make_verification_artifact(_PR_NUMBER, commands=commands)
            with self.subTest(sequence=sequence):
                self.assertEqual(
                    json.loads(_payloads.encode_evidence(commands))[_REVISION_KEY],
                    artifact.content_revision,
                )
                self.assertEqual(
                    artifact.content_revision,
                    _reports.content_digest(_evidence.render_commands(commands)),
                )
        nothing_ran = _reports.content_digest(_evidence.NOTHING_RAN)
        self.assertEqual(
            _payloads.encode_evidence(()),
            f'{{"version":1,"content":"{nothing_ran}","commands":[]}}',
        )
        self.assertEqual(_forged(_SUITE, _PASSING), _payloads.encode_evidence((_PASSED,)))

    def test_no_transcript_leaves_the_comment(self) -> None:
        payload = _payloads.encode_evidence(_ACCEPTED)
        hidden = f"<!--{payload}{_CLOSE}"

        self.assertTrue(payload.isascii() and payload.isprintable())
        self.assertEqual(payload.splitlines(), [payload])
        for delimiter in ("<", ">", _trust.RECEIPT_MARKER_PREFIX):
            with self.subTest(delimiter=delimiter):
                self.assertNotIn(delimiter, payload)
        self.assertEqual(hidden[hidden.index(_CLOSE):], _CLOSE)
        self.assertEqual(_payloads.decode_evidence(payload), _ACCEPTED)

    def test_evidence_with_no_revision_is_refused(self) -> None:
        for label, commands in (
            ("a list", [_PASSED]),
            ("a command line alone", (_SUITE,)),
            ("a lone surrogate", (_evidence.VerifiedCommand(_SUITE, 0, "\ud800"),)),
            ("a status past what Python converts", (_evidence.VerifiedCommand(_SUITE, _UNCONVERTIBLE),)),
        ):
            with self.subTest(label), self.assertRaises(_evidence.ArtifactRefusedError):
                _payloads.encode_evidence(commands)


class PayloadDecodingRefusalTest(unittest.TestCase):
    """Anything but the one spelling written for the evidence reads as nothing."""

    def test_an_unreadable_or_other_version(self) -> None:
        # Asked of text anybody can post, so each answers rather than raises.
        for label, payload in (
            ("no payload", None),
            ("bytes", _PAYLOAD.encode()),
            ("the decoded object", json.loads(_PAYLOAD)),
            ("empty", ""),
            ("not JSON", "evidence"),
            ("a JSON null", "null"),
            ("a JSON array", "[]"),
            ("cut short", _PAYLOAD[:-1]),
            ("nested past the decoder", "[" * _NESTING),
            ("a status past what Python converts", _PAYLOAD.replace('"exit_status":0', _UNCONVERTIBLE_STATUS, 1)),
            ("text UTF-8 cannot carry", _with_command(output="\ud800")),
            ("a later version", _altered(version=2)),
            ("no version", _altered(version=None)),
            ("no revision", _altered(content=None)),
            ("no commands", _altered(commands=None)),
            ("an unknown member", _altered(witness="reviewer-reported")),
        ):
            with self.subTest(label):
                self.assertIsNone(_payloads.decode_evidence(payload))

    def test_a_member_of_the_wrong_type_or_shape(self) -> None:
        for label, payload in (
            ("a version as text", _altered(version="1")),
            ("a version as a flag", _altered(version=True)),
            ("a version as a fraction", _altered(version=1.0)),
            ("commands as an object", _altered(commands=dict(enumerate(_LISTED)))),
            ("commands as text", _altered(commands=_SUITE)),
            ("a command as the pinned triple", _altered(commands=[[_SUITE, 0, _PASSING]])),
            ("a command line as a number", _with_command(command=1)),
            ("a status as text", _with_command(exit_status="0")),
            ("a status as a flag", _with_command(exit_status=False)),
            ("a status as a fraction", _with_command(exit_status=float(0))),
            ("a transcript as a list", _with_command(output=[_PASSING])),
            ("a missing transcript", _altered(commands=[{"command": _SUITE, "exit_status": 0}])),
            ("an unknown command member", _with_command(witness="reviewer")),
        ):
            with self.subTest(label):
                self.assertIsNone(_payloads.decode_evidence(payload))

    def test_a_command_the_evidence_model_refuses(self) -> None:
        # Under the revision each one's rendering hashes to, and escaped where
        # the payload spells it, so the model is all that refuses it.
        marked = _forged(_SUITE, _trust.ORCHESTRATOR_COMMENT_MARKER)

        self.assertNotIn(_trust.RECEIPT_MARKER_PREFIX, marked)
        for label, payload in (
            ("a blank command line", _forged(" ", "")),
            ("a backtick in the command line", _forged("echo `date`", "")),
            ("a line ending in the command line", _forged("echo\recho", "")),
            ("a closing fence", _forged(_SUITE, "passed\n```\nforged")),
            ("a receipt marker", marked),
        ):
            with self.subTest(label):
                self.assertIsNone(_payloads.decode_evidence(payload))

    def test_a_revision_its_commands_do_not_hash_to(self) -> None:
        # Each is otherwise exactly what the codec writes, so what refuses it
        # is the revision alone.
        repeated = json.loads(_payloads.encode_evidence((_PASSED, _PASSED, _FAILED)))
        for label, payload in (
            ("an edited transcript", _with_command(output="All checks passed?")),
            ("an edited status", _with_command(exit_status=1)),
            ("reordered commands", _altered(commands=list(reversed(_LISTED)))),
            ("a repeat dropped", _spelled(repeated | {_COMMANDS: _LISTED})),
            ("another evidence's revision", _altered(content=_evidence.content_revision(()))),
            ("an unrelated digest", _altered(content="0" * len(_REVISION))),
            ("the revision in capitals", _altered(content=_REVISION.upper())),
        ):
            with self.subTest(label):
                self.assertIsNone(_payloads.decode_evidence(payload))

    def test_another_spelling_of_the_same_evidence(self) -> None:
        # The object any JSON reader decodes the written payload to, spelled
        # some other way.
        document = json.loads(_PAYLOAD)
        bracketed = _payloads.encode_evidence((_evidence.VerifiedCommand("echo a > b", 0),))
        for label, written, payload in (
            ("optional whitespace", _PAYLOAD, json.dumps(document)),
            ("members reordered", _PAYLOAD, _spelled(dict(reversed(document.items())))),
            ("a letter escaped", _PAYLOAD, _PAYLOAD.replace("A", r"\u0041", 1)),
            ("a bracket left raw", bracketed, bracketed.replace(r"\u003e", ">")),
            ("padded", _PAYLOAD, f" {_PAYLOAD}\n"),
        ):
            with self.subTest(label):
                self.assertEqual(json.loads(payload), json.loads(written))
                self.assertIsNone(_payloads.decode_evidence(payload))


if __name__ == "__main__":
    unittest.main()
