# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""GitHub's artifact, run, and job-log reads served locally, and corpus artifacts in ClusterFuzzLite's shape.

The restore under `.github/scripts/` and the workflows' log copies run on a
hosted runner against the REST API; here they read a local server answering
the same paths, which records every request and the token it carried.
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tarfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "clusterfuzzlite_corpus.py"
REPOSITORY = "chippingway/chipping-orchestrator"
REPOSITORY_ID = 1220700175
TOKEN = "ghs_job_token"
TARGET = "manifest_fuzzer"
ARTIFACT_NAME = f"cifuzz-corpus-{TARGET}"
BATCH_WORKFLOW = ".github/workflows/clusterfuzzlite-batch.yml"
PRUNE_WORKFLOW = ".github/workflows/clusterfuzzlite-prune.yml"
_LOCALHOST = "127.0.0.1"
_OK = 200
_FOUND = 302
_NOT_FOUND = (404, (), b'{"message": "Not Found"}')
_JSON_TYPE = (("Content-Type", "application/json"),)
_TEXT_TYPE = (("Content-Type", "text/plain"),)
_ID = "id"
# How often the server checks for its shutdown, kept short so a test's cleanup is quick.
_POLL_SECONDS = 0.05
# A run's id is its artifact's times this, so the two never coincide.
_RUN_ID_FACTOR = 10


def load_restore_module():
    """The restore script as a module, registered under its own name as a script run would be."""
    spec = spec_from_file_location(SCRIPT.stem, SCRIPT)
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def zipped(member: str, payload: bytes, *, beside: str = "") -> bytes:
    """The zip GitHub serves an artifact as, holding `member`, and a second file if `beside` names one."""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as writer:
        writer.writestr(member, payload)
        if beside:
            writer.writestr(beside, b"")
    return archive.getvalue()


def corpus_tar(inputs: dict[str, bytes]) -> bytes:
    """A corpus directory archived the way ClusterFuzzLite's GitHub filestore archives one."""
    with TemporaryDirectory() as scratch:
        corpus = Path(scratch) / "corpus"
        corpus.mkdir()
        for name, unit in inputs.items():
            (corpus / name).write_bytes(unit)
        base = str(Path(scratch) / "archive")
        return Path(shutil.make_archive(base, "tar", root_dir=corpus, base_dir="./")).read_bytes()


def crafted_tar(member: tarfile.TarInfo) -> bytes:
    """A tar holding the one hand-built `member`, a regular one carrying a byte."""
    archive = io.BytesIO()
    unit = b"x" if member.isfile() else b""
    member.size = len(unit)
    with tarfile.open(fileobj=archive, mode="w") as writer:
        writer.addfile(member, io.BytesIO(unit))
    return archive.getvalue()


def artifact_record(artifact_id: int, **overrides: object) -> dict:
    """The listing entry for corpus artifact `artifact_id`, which a run of this repository uploaded on `main`.

    It was uploaded on day `artifact_id` of November 2026, so a higher id is a
    newer artifact. An override naming one of the `workflow_run` fields replaces
    that field, and any other one a field of the entry itself.
    """
    day = str(artifact_id).zfill(2)
    run = {
        _ID: artifact_id * _RUN_ID_FACTOR,
        "repository_id": REPOSITORY_ID,
        "head_repository_id": REPOSITORY_ID,
        "head_branch": "main",
        "head_sha": format(artifact_id, "040x"),
    }
    record = {
        _ID: artifact_id,
        "name": ARTIFACT_NAME,
        "expired": False,
        "created_at": f"2026-11-{day}T02:30:00Z",
        "digest": None,
        "workflow_run": run,
    }
    for field, override in overrides.items():
        (run if field in run else record)[field] = override
    return record


class FakeGitHub:
    """The repository's REST answers on a local port, each request kept with its `Authorization`."""

    def __init__(self) -> None:
        self.server = ThreadingHTTPServer((_LOCALHOST, 0), _RecordingHandler)
        self.server.routes = {}
        self.server.received = []
        port = self.server.server_address[1]
        self.url = f"http://{_LOCALHOST}:{port}"
        serving = threading.Thread(target=self.server.serve_forever, args=(_POLL_SECONDS,), daemon=True)
        serving.start()

    def answer(self, path: str, payload: object, status: int = _OK) -> None:
        """Answer `/repos/<repository><path>` with `payload`: bytes as the plain text a job's log is, else JSON."""
        if isinstance(payload, bytes):
            route = (status, _TEXT_TYPE, payload)
        else:
            route = (status, _JSON_TYPE, json.dumps(payload).encode())
        self.server.routes[f"/repos/{REPOSITORY}{path}"] = route

    def offer(self, record: dict, archive: bytes, **run: object) -> dict:
        """Serve `record`'s archive and the run it names.

        The archive is served as GitHub serves one, the API redirecting to the
        storage holding it. The run is a scheduled batch run on the branch the
        record names, `run` overriding any of its fields.
        """
        artifact_id = record[_ID]
        stored = f"/storage/{artifact_id}"
        download = f"/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip"
        redirect = (("Location", f"{self.url}{stored}"),)
        self.server.routes[download] = (_FOUND, redirect, b"")
        self.server.routes[stored] = (_OK, (), archive)
        self._answer_run(record["workflow_run"], run)
        return record | {"archive_download_url": f"{self.url}{download}"}

    def list_artifacts(self, *records: dict, page_size: int = 100) -> None:
        """Answer the listing of `ARTIFACT_NAME` with `records`, `page_size` to a page."""
        for start in range(0, max(len(records), 1), page_size):
            on_page = records[start:start + page_size]
            listing = {"total_count": len(records), "artifacts": on_page}
            page = start // page_size + 1
            self.answer(f"/actions/artifacts?name={ARTIFACT_NAME}&per_page={page_size}&page={page}", listing)

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def received(self) -> list[tuple[str, str | None]]:
        """Each path asked for, in order, with the `Authorization` header it carried."""
        return [(path, headers.get("Authorization")) for path, headers in self.server.received]

    def _answer_run(self, listed_run: dict, overrides: dict[str, object]) -> None:
        """A scheduled batch run on the branch and repository its artifact lists, `overrides` aside."""
        answered = {
            "path": BATCH_WORKFLOW,
            "event": "schedule",
            "head_branch": listed_run["head_branch"],
            "head_repository": {_ID: listed_run["head_repository_id"]},
        }
        run_id = listed_run[_ID]
        self.answer(f"/actions/runs/{run_id}", answered | overrides)


class _RecordingHandler(BaseHTTPRequestHandler):
    """Answers from the server's routes, recording the path and headers of each request."""

    def do_GET(self) -> None:
        self.server.received.append((self.path, self.headers))
        status, headers, body = self.server.routes.get(self.path, _NOT_FOUND)
        self.send_response(status)
        for name, header_value in (*headers, ("Content-Length", str(len(body)))):
            self.send_header(name, header_value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_logged: object) -> None:
        """Keep the server's access log out of the test output."""
