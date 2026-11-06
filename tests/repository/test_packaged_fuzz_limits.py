# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The libFuzzer limits every run of a packaged fuzz target is held to.

ClusterFuzzLite passes the `[libfuzzer]` settings of a target's `.options`
file when it fuzzes or reproduces, but its corpus pruning starts the merge
with no flags at all, so an input would be merged with no size cap, memory
limit, or per-input timeout. `build.sh` therefore runs
`.clusterfuzzlite/hold_limits.sh` on each packaged target, which writes those
limits into the wrapper `compile_python_fuzzer` leaves beside the packaged
binary. Here the helper is run on that wrapper as the pinned base image writes
it, the wrapper is then run the way a prune's merge runs it, and the binary
behind it reports what it was handed: the limits first, the runner's own flags
after them, so a flag a run passes still wins. A wrapper of any other shape
fails the build rather than shipping a target without its limits.
"""
from __future__ import annotations

import configparser
import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_ROOT = Path(__file__).resolve().parents[2]
_HELPER = _ROOT / ".clusterfuzzlite" / "hold_limits.sh"
_BUILD = _ROOT / ".clusterfuzzlite" / "build.sh"
_FUZZ = _ROOT / "fuzz"
_ENCODING = "utf-8"
_LIMITS = "libfuzzer"
# The wrapper `compile_python_fuzzer` in the pinned base image writes as
# `$OUT/<target>`, `{package}` naming the packaged binary beside it; the shell
# joins its run line's continuations into the one line here.
_RUN_LINE_PARTS = (
    "LD_PRELOAD=$this_dir/sanitizer_with_fuzzer.so",
    "ASAN_OPTIONS=$ASAN_OPTIONS:symbolize=1:external_symbolizer_path=$this_dir/llvm-symbolizer:detect_leaks=0",
    "$this_dir/{package} $@",
)
_WRAPPER_LINES = (
    "#!/bin/sh",
    "# LLVMFuzzerTestOneInput for fuzzer detection.",
    'this_dir=$(dirname "$0")',
    "chmod +x $this_dir/{package}",
    " ".join(_RUN_LINE_PARTS),
    "",
)
# A packaged binary that writes down the arguments it was run with.
_RECORDING_LINES = ("#!/bin/sh", r'printf "%s\n" "$@" > "$(dirname "$0")/arguments"', "")
_EXECUTABLE = 0o755
# How ClusterFuzzLite's prune mode runs a target: the merge and its paths, no limits.
_MERGE = ("-merge=1", "-artifact_prefix=/out/artifacts/", "/work/pruned", "/work/corpus")


def _limits(target: str) -> list[str]:
    """The flags `target`'s options file sets, in the order it sets them."""
    options = configparser.ConfigParser()
    options.read(_FUZZ / f"{target}.options", encoding=_ENCODING)
    return [f"-{name}={setting}" for name, setting in options[_LIMITS].items()]


class PackagedLimitsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.out = Path(self.enterContext(TemporaryDirectory()))

    def test_a_merge_is_held_to_the_target_limits(self) -> None:
        for target in ("manifest_fuzzer", "pinned_admission_fuzzer"):
            with self.subTest(target=target):
                wrapper = self.package(target)
                self.assertEqual(self.hold(target, wrapper).returncode, 0)
                subprocess.run(
                    [wrapper, *_MERGE],
                    env={"PATH": os.environ["PATH"]},
                    capture_output=True,
                    check=True,
                )
                handed = (self.out / "arguments").read_text(encoding=_ENCODING).splitlines()
                self.assertEqual(handed, [*_limits(target), *_MERGE])
                self.assertGreater(len(_limits(target)), 2)

    def test_another_wrapper_shape_fails_the_build(self) -> None:
        wrapper = self.out / "manifest_fuzzer"
        wrapper.write_text("#!/bin/sh\nexec ./manifest_fuzzer.pkg\n", encoding=_ENCODING)

        held = self.hold("manifest_fuzzer", wrapper)

        self.assertNotEqual(held.returncode, 0)
        self.assertIn("does not end in", held.stderr)
        self.assertEqual(wrapper.read_text(encoding=_ENCODING), "#!/bin/sh\nexec ./manifest_fuzzer.pkg\n")

    def test_the_build_holds_each_target_it_packages(self) -> None:
        build = _BUILD.read_text(encoding=_ENCODING)
        compiled = '  compile_python_fuzzer "fuzz/$target.py" --paths "$project"\n'
        held = '  bash "$project/.clusterfuzzlite/hold_limits.sh" "fuzz/$target.options" "$OUT/$target"\n'
        self.assertIn(f"{compiled}{held}", build)
        self.assertRegex(build, r"(?m)^for target in \"\$\{targets\[@\]\}\"; do$")

    def package(self, target: str) -> Path:
        """`target` as the build leaves it before its limits are written in, its binary recording its arguments."""
        package = f"{target}.pkg"
        (self.out / package).write_text("\n".join(_RECORDING_LINES), encoding=_ENCODING)
        wrapper = self.out / target
        wrapper.write_text("\n".join(_WRAPPER_LINES).format(package=package), encoding=_ENCODING)
        wrapper.chmod(_EXECUTABLE)
        return wrapper

    def hold(self, target: str, wrapper: Path) -> subprocess.CompletedProcess[str]:
        options = _FUZZ / f"{target}.options"
        return subprocess.run(
            ["bash", str(_HELPER), str(options), str(wrapper)],
            capture_output=True,
            text=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
