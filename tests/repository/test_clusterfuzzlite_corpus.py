# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The corpus a ClusterFuzzLite batch or prune run starts from.

ClusterFuzzLite looks its corpus artifact up by name across every run in the
repository, a fork's pull request included, and unpacks it unfiltered, so the
workflows withhold its token and `.github/scripts/clusterfuzzlite_corpus.py`
restores first. What it may restore is the security boundary: only an
unexpired artifact a `schedule` or `workflow_dispatch` run of the batch or
prune workflow uploaded on this repository's default branch, the newest such,
and only files that land inside the corpus. The committed seeds are copied over
it either way, and finding no such artifact is a cold start from them alone.
Any other failure -- a read GitHub refuses, an archive that is not the one
ClusterFuzzLite writes -- ends the job, because a cold start's corpus would be
uploaded as the newest and displace the one that could not be read. The token
stays with GitHub when an archive download redirects to storage.
"""
from __future__ import annotations

import hashlib
import io
import os
import tarfile
import unittest
from http import HTTPStatus
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError

from tests.repository import clusterfuzzlite_corpus_test_support as support

_restore = support.load_restore_module()

_BEARER = f"Bearer {support.TOKEN}"
_TAR_MEMBER = f"{support.ARTIFACT_NAME}.tar"
_SEEDS = (("empty.txt", b""), ("split-chain.txt", b"committed seed"))
_KEPT = "kept"
_FORK_ID = 77
_STORAGE = "/storage/"
_OTHER_SHA256 = hashlib.sha256(b"another archive").hexdigest()
_WRONG_DIGEST = f"sha256:{_OTHER_SHA256}"
# The reads a restore of artifact 2 makes, in order.
_LISTING = f"/actions/artifacts?name={support.ARTIFACT_NAME}&per_page=100&page=1"
_RUN = "/actions/runs/20"
_DOWNLOAD = "/actions/artifacts/2/zip"
_OTHER_TARGET = "pinned_admission_fuzzer"
_OTHER_LISTING = f"/actions/artifacts?name=cifuzz-corpus-{_OTHER_TARGET}&per_page=100&page=1"


def _archive(inputs: dict[str, bytes]) -> bytes:
    return support.zipped(_TAR_MEMBER, support.corpus_tar(inputs))


def _corpus(workspace: Path, target: str = support.TARGET) -> dict[str, bytes]:
    files = filter(Path.is_file, (workspace / "cifuzz-corpus" / target).rglob("*"))
    return {path.name: path.read_bytes() for path in files}


def _unsafe_members(escape: Path) -> tuple[tarfile.TarInfo, ...]:
    """Members that would write outside the corpus, link out of it, or are no file at all."""
    # The corpus sits three levels under the directory `escape` is in.
    climbing = tarfile.TarInfo(f"../../../{escape.name}")
    link = tarfile.TarInfo("link")
    link.type = tarfile.SYMTYPE
    link.linkname = str(escape)
    device = tarfile.TarInfo("device")
    device.type = tarfile.CHRTYPE
    return climbing, link, device


class _RestoreCase(unittest.TestCase):
    """A local repository answering on a port, and a target with two committed seeds."""

    def setUp(self) -> None:
        # The local server is reached directly, whatever proxy the
        # environment running the suite names.
        self.enterContext(patch.dict(os.environ, {"no_proxy": "*"}))
        self.github = support.FakeGitHub()
        self.addCleanup(self.github.stop)
        self.scratch = Path(self.enterContext(TemporaryDirectory()))
        self.workspace = self.scratch / "workspace"
        self.seeds = self.scratch / "seeds" / support.TARGET
        self.seeds.mkdir(parents=True)
        for name, unit in _SEEDS:
            (self.seeds / name).write_bytes(unit)

    def restore_into(self, workspace: Path) -> str:
        reads = _restore.GitHubReads(self.github.url, support.REPOSITORY, support.TOKEN)
        restore = _restore.CorpusRestore(reads, support.REPOSITORY_ID, "main", workspace)
        return restore.target(self.seeds)

    def offer_only(self, record: dict, archive: bytes) -> None:
        """List `record` alone, a trusted run's artifact holding `archive`."""
        self.github.list_artifacts(self.github.offer(record, archive))

    def assert_corpus(self, **restored: bytes) -> None:
        """The workspace's corpus is `restored` with the committed seeds copied over it."""
        self.assertEqual(_corpus(self.workspace), restored | dict(_SEEDS))

    def assert_downloaded_only(self, *stored: str) -> None:
        """`stored` are the archives fetched, and the only reads made without the token."""
        paths = [path for path, _ in self.github.received()]
        fetched = [path for path in paths if path.startswith(_STORAGE)]
        self.assertEqual(fetched, list(stored))
        for path, authorization in self.github.received():
            with self.subTest(path=path):
                self.assertEqual(authorization, None if path in stored else _BEARER)


class TrustedSourceTest(_RestoreCase):
    def test_the_newest_trusted_corpus_wins(self) -> None:
        trusted = support.artifact_record(2)
        newest = _archive({_KEPT: b"newest trusted", "split-chain.txt": b"restored copy"})
        self.github.list_artifacts(
            self.github.offer(support.artifact_record(1), _archive({"older": b"old"})),
            self.github.offer(trusted, newest, path=support.PRUNE_WORKFLOW, event="workflow_dispatch"),
            *self.offer_refused(),
        )

        line = self.restore_into(self.workspace)

        # The committed seeds land over the restored copy of one of them.
        self.assert_corpus(kept=b"newest trusted")
        self.assertIn("2 inputs from artifact 2,", line)
        self.assertIn("plus 2 committed seeds", line)
        self.assert_downloaded_only("/storage/2")

    def test_the_listing_is_read_to_its_end(self) -> None:
        fork = support.artifact_record(4, head_repository_id=_FORK_ID)
        archive = _archive({_KEPT: b"page two"})
        digest = hashlib.sha256(archive).hexdigest()
        trusted = self.github.offer(support.artifact_record(2, digest=f"sha256:{digest}"), archive)
        untrusted = self.github.offer(fork, _archive({}))
        self.github.list_artifacts(untrusted, trusted, page_size=1)

        with patch.object(_restore, "_PAGE_SIZE", 1):
            self.restore_into(self.workspace)

        self.assert_corpus(kept=b"page two")

    def test_no_trusted_artifact_is_a_cold_start(self) -> None:
        fork = support.artifact_record(4, head_repository_id=_FORK_ID)
        self.offer_only(fork, _archive({_KEPT: b"fork"}))

        line = self.restore_into(self.workspace)

        self.assert_corpus()
        self.assertTrue(line.endswith("no trusted corpus artifact, so a cold start, plus 2 committed seeds"))
        self.assert_downloaded_only()

    def test_a_corpus_already_present_is_refused(self) -> None:
        (self.workspace / "cifuzz-corpus" / support.TARGET).mkdir(parents=True)

        with self.assertRaises(FileExistsError):
            self.restore_into(self.workspace)

    def offer_refused(self) -> list[dict]:
        """Artifacts newer than any trusted one, each refused for one reason of its own."""
        refused = _archive({"refused": b"untrusted"})
        offer = self.github.offer
        return [
            offer(support.artifact_record(3, expired=True), refused),
            offer(support.artifact_record(4, head_repository_id=_FORK_ID), refused),
            offer(support.artifact_record(5, head_branch="feature"), refused),
            offer(support.artifact_record(6), refused, path=".github/workflows/ci.yml"),
            offer(support.artifact_record(7), refused, event="push"),
            offer(support.artifact_record(8, name="cifuzz-corpus-manifest"), refused),
        ]


class RefusalTest(_RestoreCase):
    """A trusted artifact the restore cannot use as it stands ends it."""

    def test_an_unsafe_member_is_refused(self) -> None:
        escape = self.scratch / "escaped"
        for artifact_id, member in enumerate(_unsafe_members(escape), start=1):
            with self.subTest(member=member.name):
                archive = support.zipped(_TAR_MEMBER, support.crafted_tar(member))
                self.offer_only(support.artifact_record(artifact_id), archive)
                with self.assertRaises(tarfile.FilterError):
                    self.restore_into(self.scratch / str(artifact_id))
                self.assertFalse(escape.exists())

    def test_an_archive_unlike_the_upload_is_refused(self) -> None:
        tar = support.corpus_tar({_KEPT: b"input"})
        cases = (
            (support.artifact_record(1, digest=_WRONG_DIGEST), support.zipped(_TAR_MEMBER, tar)),
            (support.artifact_record(2), support.zipped(_TAR_MEMBER, tar, beside="extra.txt")),
            (support.artifact_record(3), support.zipped("corpus.tar", tar)),
        )
        for record, archive in cases:
            with self.subTest(artifact=record["id"]):
                self.offer_only(record, archive)
                with self.assertRaises(_restore.RestoreError):
                    self.restore_into(self.scratch / str(record["id"]))

    def test_a_refused_read_ends_the_restore(self) -> None:
        archive = _archive({_KEPT: b"input"})
        for index, refused in enumerate((_LISTING, _RUN, _DOWNLOAD)):
            with self.subTest(read=refused):
                self.offer_only(support.artifact_record(2), archive)
                self.github.answer(refused, {"message": "Gone"}, status=HTTPStatus.GONE)
                with self.assertRaises(HTTPError):
                    self.restore_into(self.scratch / str(index))


class MainTest(_RestoreCase):
    """The script names its targets by the seed directories and reports what each started from."""

    def setUp(self) -> None:
        super().setUp()
        other_seeds = self.seeds.parent / _OTHER_TARGET
        other_seeds.mkdir()
        (other_seeds / "empty.txt").write_bytes(b"")
        # The default branch is the one GitHub names, whatever it is called.
        self.github.answer("", {"id": support.REPOSITORY_ID, "default_branch": "trunk"})
        trunk = support.artifact_record(2, head_branch="trunk")
        self.offer_only(trunk, _archive({_KEPT: b"x"}))
        self.github.answer(_OTHER_LISTING, {"total_count": 0, "artifacts": []})
        self.summary = self.scratch / "summary.md"

    def test_each_seeded_target_is_reported(self) -> None:
        arguments = [str(self.workspace), str(self.seeds.parent)]

        with self.job_environment(), patch("sys.stdout", new=io.StringIO()) as logged:
            self.assertEqual(_restore.main(arguments), 0)
            log = logged.getvalue()

        self.assert_corpus(kept=b"x")
        self.assertEqual(_corpus(self.workspace, _OTHER_TARGET), {"empty.txt": b""})
        report = self.summary.read_text(encoding="utf-8")
        self.assertEqual(log, report)
        lines = report.splitlines()
        self.assertEqual(lines[:2], ["### Fuzzing corpora", ""])
        self.assertTrue(lines[2].startswith("- `manifest_fuzzer`: 1 inputs from artifact 2, uploaded"))
        self.assertTrue(lines[3].endswith("no trusted corpus artifact, so a cold start, plus 1 committed seeds"))

    def job_environment(self) -> patch.dict:
        """What a hosted job sets for the script, the API pointed at the local server."""
        return patch.dict(os.environ, {
            "GITHUB_API_URL": self.github.url,
            "GITHUB_REPOSITORY": support.REPOSITORY,
            "GITHUB_TOKEN": support.TOKEN,
            "GITHUB_STEP_SUMMARY": str(self.summary),
        })


if __name__ == "__main__":
    unittest.main()
