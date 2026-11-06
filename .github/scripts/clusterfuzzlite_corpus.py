# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Restore the corpus a ClusterFuzzLite batch or prune run fuzzes from.

ClusterFuzzLite keeps each target's corpus as the Actions artifact
`cifuzz-corpus-<target>`: GitHub's zip around the one
`cifuzz-corpus-<target>.tar` its run step uploads. Handed a token, that step
downloads the newest unexpired artifact of the name from any run in the
repository, a fork's pull request included, and unpacks the tar unfiltered. The
workflows hand it none. This script restores first, into the directory the step
fuzzes from, and takes an artifact only from a `schedule` or
`workflow_dispatch` run of the batch or prune workflow on this repository's
default branch.

The committed seeds are copied over whatever was restored, so every run fuzzes
them, a seed edited since the artifact was made included. Finding no trusted
artifact -- the first run, or one after every candidate expired -- is a cold
start from the seeds alone. Any other failure ends the job before it fuzzes:
the corpus a cold start uploads would become the newest and displace the one
this run could not read.

Run from a job whose `actions: read` token is in `GITHUB_TOKEN`:
`python3 clusterfuzzlite_corpus.py <workspace> <seed directory>`, one target
per subdirectory of the seed directory.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tarfile
import zipfile
from dataclasses import dataclass, field
from http.client import HTTPResponse
from pathlib import Path
from urllib.request import Request, urlopen

# The workflows whose runs on the default branch upload a corpus a later run
# may start from, and the events that start them there.
TRUSTED_WORKFLOWS = frozenset((
    ".github/workflows/clusterfuzzlite-batch.yml",
    ".github/workflows/clusterfuzzlite-prune.yml",
))
TRUSTED_EVENTS = frozenset(("schedule", "workflow_dispatch"))
# Where ClusterFuzzLite's run step reads a target's corpus, under the workspace.
CORPUS_DIRECTORY = "cifuzz-corpus"
ARTIFACT_PREFIX = "cifuzz-corpus-"

_PAGE_SIZE = 100
_TIMEOUT_SECONDS = 60
_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"


class RestoreError(Exception):
    """A trusted corpus artifact this run cannot use as it stands."""


@dataclass
class GitHubReads:
    """The REST reads a restore makes, under the job's token."""

    api_url: str
    repository: str
    token: str
    runs: dict[int, dict] = field(default_factory=dict)

    @classmethod
    def from_environment(cls) -> GitHubReads:
        """The reads the job's own environment names."""
        environ = os.environ
        return cls(
            environ.get("GITHUB_API_URL", "https://api.github.com"),
            environ["GITHUB_REPOSITORY"],
            environ["GITHUB_TOKEN"],
        )

    def read(self, path: str) -> dict:
        """The JSON a repository endpoint answers; `""` is the repository itself."""
        with self._open(f"{self.api_url}/repos/{self.repository}{path}") as response:
            return json.load(response)

    def download(self, url: str) -> bytes:
        with self._open(url) as response:
            return response.read()

    def run(self, run_id: int) -> dict:
        """The workflow run `run_id`, read once however many artifacts name it."""
        if run_id not in self.runs:
            self.runs[run_id] = self.read(f"/actions/runs/{run_id}")
        return self.runs[run_id]

    def identity(self) -> tuple[int, str]:
        """The repository's id and the name of its default branch."""
        repository = self.read("")
        return repository["id"], repository["default_branch"]

    def _open(self, url: str) -> HTTPResponse:
        request = Request(url, headers={"Accept": _ACCEPT, "X-GitHub-Api-Version": _API_VERSION})
        # Unredirected, so the token stays with GitHub when an archive download
        # is redirected to the storage serving it.
        request.add_unredirected_header("Authorization", f"Bearer {self.token}")
        return urlopen(request, timeout=_TIMEOUT_SECONDS)


@dataclass(frozen=True)
class CorpusRestore:
    """One job's restore, against the repository and default branch GitHub names."""

    github: GitHubReads
    repository_id: int
    default_branch: str
    workspace: Path

    def target(self, seeds: Path) -> str:
        """Restore the corpus of the target `seeds` is named for, then copy its seeds over it.

        Returns the line the job summary records for it.
        """
        corpus = self.workspace / CORPUS_DIRECTORY / seeds.name
        corpus.mkdir(parents=True)
        artifact = self.newest_trusted(seeds.name)
        origin = "no trusted corpus artifact, so a cold start"
        if artifact is not None:
            origin = self._unpack(artifact, corpus)
        return f"- `{seeds.name}`: {origin}, plus {_copy_seeds(seeds, corpus)} committed seeds"

    def newest_trusted(self, target: str) -> dict | None:
        """The newest unexpired corpus a trusted run uploaded for `target`, if one is left."""
        listed = self._listed(f"{ARTIFACT_PREFIX}{target}")
        listed.sort(key=lambda artifact: artifact["created_at"], reverse=True)
        return next((artifact for artifact in listed if self._trusted(artifact)), None)

    def _listed(self, name: str) -> list[dict]:
        found: list[dict] = []
        page = 1
        while True:
            listing = self.github.read(f"/actions/artifacts?name={name}&per_page={_PAGE_SIZE}&page={page}")
            found.extend(listing["artifacts"])
            if not listing["artifacts"] or len(found) >= listing["total_count"]:
                return [artifact for artifact in found if self._on_default_branch(artifact, name)]
            page += 1

    def _on_default_branch(self, artifact: dict, name: str) -> bool:
        # A fork's run belongs to this repository too: only its head repository
        # tells the two apart.
        run = artifact["workflow_run"]
        return (
            artifact["name"] == name
            and not artifact["expired"]
            and run["head_repository_id"] == self.repository_id
            and run["head_branch"] == self.default_branch
        )

    def _trusted(self, artifact: dict) -> bool:
        run = self.github.run(artifact["workflow_run"]["id"])
        return (
            run["path"] in TRUSTED_WORKFLOWS
            and run["event"] in TRUSTED_EVENTS
            and run["head_branch"] == self.default_branch
            and run["head_repository"]["id"] == self.repository_id
        )

    def _verified(self, artifact: dict) -> bytes:
        archive = self.github.download(artifact["archive_download_url"])
        digest = artifact.get("digest")
        downloaded = hashlib.sha256(archive).hexdigest()
        if digest is not None and digest != f"sha256:{downloaded}":
            raise RestoreError(f"artifact {artifact['id']} does not match its digest {digest}")
        return archive

    def _unpack(self, artifact: dict, corpus: Path) -> str:
        member = f"{artifact['name']}.tar"
        with zipfile.ZipFile(io.BytesIO(self._verified(artifact))) as archive:
            if archive.namelist() != [member]:
                raise RestoreError(f"artifact {artifact['id']} holds {archive.namelist()}, not one {member}")
            # The `data` filter refuses a member that would land outside the
            # corpus or link out of it, and anything but files and directories.
            with tarfile.open(fileobj=io.BytesIO(archive.read(member))) as tar:
                tar.extractall(corpus, filter="data")
        restored = sum(1 for path in corpus.rglob("*") if path.is_file())
        run = artifact["workflow_run"]
        return (
            f"{restored} inputs from artifact {artifact['id']}, uploaded {artifact['created_at']} "
            f"by run {run['id']} at {run['head_sha']}"
        )


def _copy_seeds(seeds: Path, corpus: Path) -> int:
    copied = 0
    for seed in sorted(seeds.iterdir()):
        if seed.is_file():
            (corpus / seed.name).write_bytes(seed.read_bytes())
            copied += 1
    return copied


def _record(lines: list[str]) -> None:
    """Write the restore's report to the log and to the job summary GitHub shows on the run."""
    report = "\n".join(["### Fuzzing corpora", "", *lines, ""])
    sys.stdout.write(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as summary_file:
            summary_file.write(report)


def main(argv: list[str]) -> int:
    """Restore every target the seed directory has a subdirectory for."""
    workspace, seed_root = map(Path, argv)
    github = GitHubReads.from_environment()
    restore = CorpusRestore(github, *github.identity(), workspace)
    targets = filter(Path.is_dir, sorted(seed_root.iterdir()))
    _record([restore.target(seeds) for seeds in targets])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
