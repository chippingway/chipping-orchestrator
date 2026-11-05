# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The parser fuzz targets under `fuzz/`, replayed over their committed seeds.

Each target holds its reader's answers to the contract the reader implements
and raises on any answer that contract does not allow, so every seed replaying
clean is that contract holding over the corpus. A corpus earns its place by
reaching the readers' decisions rather than their first refusal: together the
seeds reach every admission status and every version refusal, the writer's
rendering past the comment ceiling, and every manifest outcome from a valid
split to each child, dependency, and cycle refusal. A pruned corpus that would
only fuzz the decoders fails here.

How a target starts and runs (`fuzz/isolation.py`) is asked of a fresh
interpreter, where nothing has imported the settings package or installed an
audit hook: starting both targets and replaying every seed opens no `.env`,
token, or repository file and starts no process, and a sealed target that
reaches for a file or a process fails the input and is unsealed behind it,
while one reading Python source, as a coverage tracer does, goes on.

With Atheris installed (`poetry sync --with fuzz`), each entry point is run
once over its seeds as well, which shows the readers instrumented rather than
only importable; without it that check is skipped.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from importlib import util as _import_util
from pathlib import Path
from tempfile import TemporaryDirectory

from fuzz import manifest_reply, pinned_admission, split_contract
from orchestrator.github import pinned_state as _pinned_state
from orchestrator.workflow.stages.decomposition import manifest as _manifest

_ROOT = Path(__file__).resolve().parents[2]
_CORPUS = _ROOT / "fuzz" / "corpus"
_ADMISSION = "pinned_admission_fuzzer"
_MANIFEST = "manifest_fuzzer"
_TIMEOUT_SECONDS = 300
# How often the derived-graph check names one prerequisite.
_REPEATS = 50
# How much of a failed run's output a failure quotes.
_TAIL_CHARACTERS = 4000

# The refusals the admission seeds reach between them: each kind of version
# the contract refuses, and each payload that is no object at all.
_ADMISSION_REFUSALS = (
    "missing schema_version",
    "schema_version is boolean",
    "schema_version is float",
    "schema_version is str",
    "unsupported schema_version",
    "malformed JSON",
    "rather than an object",
)

# The refusals the manifest seeds reach between them, from the envelope to the
# dependency graph. Nesting the decoder will not build is left out: how deep
# it builds is the interpreter's and the stack's, and no reply inside the
# targets' input limit is too deep for every supported one.
_MANIFEST_REFUSALS = (
    "expected exactly one orchestrator-manifest block",
    "must be the final block",
    "invalid JSON: Expecting",
    "invalid JSON: an integer literal is too long to decode",
    "manifest is not a JSON object",
    "decision must be",
    "split decision requires non-empty children list",
    "too many children",
    "umbrella must be a boolean",
    "is not an object",
    "missing title or body",
    "missing depends_on",
    "depends_on is null",
    "must be a list",
    "has invalid dependency",
    "dependency graph has a cycle",
)

# Starts both targets the way their entry points do and replays every seed
# through them sealed, then reports what the process reached meanwhile beyond
# reading code: a process or a connection, a file outside the interpreter's
# installation and the checkout's two packages, and whether the settings
# package resolved anything.
_STARTUP_PROBE = """
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
seeds = {
    name: [seed.read_bytes() for seed in sorted((root / "fuzz" / "corpus" / name).iterdir())]
    for name in ("pinned_admission_fuzzer", "manifest_fuzzer")
}
reached = []
watched = ("open", "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "socket.connect")
sys.addaudithook(lambda event, args: reached.append((event, str(args[0]))) if event in watched else None)
sys.path.insert(0, str(root))
from fuzz import isolation
isolation.isolate()
from fuzz import manifest_reply, pinned_admission
for target, name in ((pinned_admission, "pinned_admission_fuzzer"), (manifest_reply, "manifest_fuzzer")):
    sealed = isolation.Sealed(target.test_one_input)
    for seed in seeds[name]:
        sealed(seed)
code = (sys.prefix, sys.base_prefix, str(root / "orchestrator"), str(root / "fuzz"))
print(json.dumps({
    "processes": [event for event, _ in reached if event != "open"],
    "foreign": [
        path for event, path in reached
        if event == "open" and path != "/dev/urandom"
        and not (path.startswith(code) and path.endswith((".py", ".pyc", ".so")))
    ],
    "resolved": hasattr(sys.modules["orchestrator.config"], "REPO"),
}))
"""

# Seals a target that opens a file, one that starts a process, and one that
# reads Python source, then opens a file once none is running.
_SEAL_PROBE = """
import os, sys
sys.path.insert(0, sys.argv[1])
from fuzz import isolation
reaches = (
    lambda _: open(os.devnull).close(),
    lambda _: os.system("true"),
    lambda _: open(isolation.__file__, "rb").close(),
)
for reach in reaches:
    try:
        isolation.Sealed(reach)(b"")
    except isolation.SideEffectError as error:
        print("refused", error.args[0])
    else:
        print("let through")
open(os.devnull).close()
print("unsealed")
"""

# The owners each entry point has to report instrumenting.
_INSTRUMENTED = (
    (_ADMISSION, ("orchestrator.github.pinned_state",)),
    (_MANIFEST, tuple(
        f"orchestrator.workflow.stages.decomposition.{owner}"
        for owner in ("manifest", "validation", "child_validation")
    )),
)


def _seeds(target: str) -> list[Path]:
    return sorted((_CORPUS / target).iterdir())


def _probe(script: str, **overrides: str) -> subprocess.CompletedProcess[str]:
    """Run `script` in an isolated interpreter that writes no bytecode, settings left to load `.env`."""
    environment = {
        key: setting for key, setting in os.environ.items()
        if key != "ORCHESTRATOR_SKIP_DOTENV"
    }
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", script, str(_ROOT)],
        env={**environment, **overrides},
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
    )


def _replay(entry: str, scratch: str) -> subprocess.CompletedProcess[str]:
    """Run one entry point once over its seeds, writing whatever it writes into `scratch`."""
    return subprocess.run(
        [
            sys.executable, "-m", f"fuzz.{entry}", scratch, str(_CORPUS / entry),
            "-runs=0", f"-artifact_prefix={scratch}/",
        ],
        cwd=_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
    )


class SeedCorpusTest(unittest.TestCase):
    def test_every_seed_holds_to_its_target(self) -> None:
        for target, name in ((pinned_admission, _ADMISSION), (manifest_reply, _MANIFEST)):
            for seed in _seeds(name):
                with self.subTest(target=name, seed=seed.name):
                    target.test_one_input(seed.read_bytes())

    def test_admission_seeds_reach_every_decision(self) -> None:
        readings = [pinned_admission.admit(text) for text in self._texts(_ADMISSION)]
        self.assertEqual({reading.status for reading in readings}, set(_pinned_state.AdmissionStatus))
        reasons = "\n".join(reading.refusal_reason or "" for reading in readings)
        for refusal in _ADMISSION_REFUSALS:
            with self.subTest(refusal=refusal):
                self.assertIn(refusal, reasons)
        rendered = [
            _pinned_state.pinned_state_body(pinned_admission.quoting_record(text), escaped_in_full=True)
            for text in self._texts(_ADMISSION)
        ]
        self.assertGreater(max(map(len, rendered)), _pinned_state.MAX_PINNED_BODY)

    def test_manifest_seeds_reach_every_outcome(self) -> None:
        answers = [_manifest._parse_manifest(text) for text in self._texts(_MANIFEST)]
        accepted = {parsed["decision"] for parsed, _ in answers if parsed is not None}
        self.assertEqual(accepted, {"single", "split"})
        self.assertIn((None, None), answers)
        reasons = "\n".join(refusal for _, refusal in answers if refusal is not None)
        for refusal in _MANIFEST_REFUSALS:
            with self.subTest(refusal=refusal):
                self.assertIn(refusal, reasons)


    def _texts(self, target: str) -> list[str]:
        return [seed.read_bytes().decode("utf-8", "surrogateescape") for seed in _seeds(target)]


class DerivedGraphTest(unittest.TestCase):
    def test_a_repeated_edge_derives_no_more_graphs(self) -> None:
        # A list may name one prerequisite again and again and still be valid,
        # and it draws one edge however often it does: the graphs the manifest
        # target derives follow the edges, never the length of a list, and
        # leave the children as the parser read them.
        repeated = self._children(_REPEATS)
        derived = list(split_contract.broken_children(repeated))
        stated_once = list(split_contract.broken_children(self._children(1)))
        self.assertEqual(len(derived), len(stated_once))
        self.assertEqual(repeated, self._children(_REPEATS))
        record = json.dumps({"decision": "split", "children": repeated})
        manifest_reply.test_one_input(f"```orchestrator-manifest\n{record}\n```".encode())

    def _children(self, repeats: int) -> list[dict]:
        """A valid split's children, the second naming the first `repeats` times."""
        return [
            {"title": "first", "body": "first", split_contract.DEPENDS_ON: []},
            {"title": "second", "body": "second", split_contract.DEPENDS_ON: [0 for _ in range(repeats)]},
        ]


class TargetIsolationTest(unittest.TestCase):
    def test_startup_and_replay_reach_only_their_code(self) -> None:
        with TemporaryDirectory() as scratch:
            token_file = Path(scratch, "token")
            token_file.write_text("ghp_never_read\n", encoding="utf-8")
            completed = _probe(_STARTUP_PROBE, ORCHESTRATOR_TOKEN_FILE=str(token_file))
        self.assertEqual(completed.returncode, 0, completed.stderr[-_TAIL_CHARACTERS:])
        report = json.loads(completed.stdout)
        self.assertEqual(report, {"processes": [], "foreign": [], "resolved": False})

    def test_a_sealed_target_cannot_reach_out(self) -> None:
        completed = _probe(_SEAL_PROBE)
        self.assertEqual(completed.returncode, 0, completed.stderr[-_TAIL_CHARACTERS:])
        self.assertEqual(
            completed.stdout.splitlines(), ["refused open", "refused os.system", "let through", "unsealed"],
        )


@unittest.skipUnless(_import_util.find_spec("atheris"), "Atheris is required: poetry sync --with fuzz")
class EntryPointTest(unittest.TestCase):
    def test_entry_points_replay_seeds_instrumented(self) -> None:
        for entry, owners in _INSTRUMENTED:
            with self.subTest(entry=entry), TemporaryDirectory() as scratch:
                completed = _replay(entry, scratch)
            self.assertEqual(completed.returncode, 0, completed.stdout[-_TAIL_CHARACTERS:])
            self.assertIn("INITED cov:", completed.stdout)
            for owner in owners:
                self.assertIn(f"INFO: Instrumenting {owner}\n", completed.stdout)


if __name__ == "__main__":
    unittest.main()
