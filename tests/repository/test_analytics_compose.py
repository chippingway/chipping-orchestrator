# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Compose declares checkout binds with automatic directory creation disabled.

Render a copied configuration through Compose itself so short volume syntax
cannot silently enable host-directory creation. This needs the Compose CLI,
but never connects to Docker or accesses the operator's data directory.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

_COMPOSE_FILE = Path(__file__).resolve().parents[2] / "analytics-db" / "compose.yml"
_DOCKER = shutil.which("docker")
_SKIP_REASON = "Docker Compose CLI is required to render analytics mounts"
_TIMEOUT = 10


@unittest.skipUnless(_DOCKER, _SKIP_REASON)
class AnalyticsComposeMountsTest(unittest.TestCase):
    def test_binds_require_checkout_sources(self) -> None:
        if subprocess.run(
            [_DOCKER, "compose", "version"],
            capture_output=True, check=False, timeout=_TIMEOUT,
        ).returncode:
            self.skipTest(_SKIP_REASON)

        with tempfile.TemporaryDirectory() as checkout:
            compose_file = Path(checkout) / "compose.yml"
            shutil.copyfile(_COMPOSE_FILE, compose_file)
            rendered = subprocess.run(
                [
                    _DOCKER, "compose", "--env-file", "/dev/null", "-f", str(compose_file),
                    "config", "--format", "json", "--no-interpolate",
                ],
                capture_output=True, text=True, check=True, timeout=_TIMEOUT,
            )
            mounts = json.loads(rendered.stdout)["services"]["analytics-db"]["volumes"]
            self.assertEqual(len(mounts), 2)
            for mount in mounts:
                with self.subTest(target=mount["target"]):
                    self.assertEqual(mount["type"], "bind")
                    self.assertEqual(
                        Path(mount["source"]).parent.resolve(), Path(checkout).resolve(),
                    )
                    self.assertIs(mount["bind"]["create_host_path"], False)


if __name__ == "__main__":
    unittest.main()
