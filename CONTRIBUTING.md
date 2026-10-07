# Contributing to chipping-orchestrator

Bug reports, ideas, documentation fixes, tests, and pull requests are welcome. A short issue is enough to get started.

## Report a problem or suggest a change

Check existing issues and pull requests to see whether someone has already raised the same topic, then use the
[issue forms](https://github.com/chippingway/chipping-orchestrator/issues/new/choose).

For a bug, tell us what happened and what you expected. For a change, describe the problem and the improvement you want.
Steps to reproduce, examples, your version, or redacted logs are helpful if you have them. Share what you know;
maintainers can ask for more details and help clarify scope and success criteria.

Report suspected vulnerabilities privately through [SECURITY.md](SECURITY.md). Redact secrets and private details
from anything you share publicly.

Issues can start automated agent work. Maintainers manage workflow labels; for a question or design discussion,
say so clearly so they can choose the appropriate route. Leave the orchestrator's pinned state comment intact.
See the [README](README.md#how-it-works) for how issues become pull requests.

## Set up a development checkout

Use Linux, Git, Python 3.12 or newer, and Poetry 2.5.1. Fork the repository, then:

```sh
pipx install "poetry==2.5.1"
git clone https://github.com/YOUR-LOGIN/chipping-orchestrator.git
cd chipping-orchestrator
git switch -c my-change
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync
```

Local lint and test checks work without GitHub credentials or coding-agent setup. For dashboard work, use
`env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync --with dashboard`.

Run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync` in each new worktree before checks; `poetry run` does not
install dependencies. Add `--with docs` for documentation work or `--with docs,dashboard` for both groups. Follow the
[environment selection policy](docs/configuration/operations.md#dependency-tooling) for every Poetry command. To select
another Python interpreter, use `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry env use /path/to/python`.

Live orchestrator runs perform real GitHub operations. Use a dedicated test repository and follow the
[configuration](docs/configuration.md) and [security](docs/security.md) guides.
The [developer guide](docs/development.md) covers checkout configuration, direct launches, the restart wrapper,
and optional analytics tools. User installations follow the [pipx quick start](README.md#quick-start).
Do not access or change `analytics-db/data/`; it holds operator-owned runtime data.

## Make a focused change

Small fixes can go straight to a PR. Discuss larger features or new dependencies in an issue first, and coordinate
with anyone already working on the same issue.

Add or update tests for behavioral changes and update the affected documentation. Tests follow the package layout.
Preserve existing workflow labels, pinned-state fields, comment markers, watermarks, and event payloads. For workflow
or agent changes, consult the [state machine](docs/state-machine.md) and [workflow guide](docs/workflow.md).

The [development guide](.agents/skills/develop/SKILL.md) covers detailed conventions, license headers, and the full
pre-push checklist. The [documentation index](docs/README.md) helps you find the relevant reference pages.

## Check your changes

Before submitting a PR, run:

```sh
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run ruff check orchestrator tests .github/scripts/docs_site.py
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run flake8 orchestrator tests .github/scripts/docs_site.py --select=WPS
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run python -m pytest tests
git diff --check
```

Fix failing checks. Report a baseline failure only after reproducing it on the unchanged base commit, and note
any relevant optional tests you skipped.

## Open a pull request

Target `main`. Briefly explain what changed and why, link any related issue, and say which checks you ran.
Use a single Conventional Commit subject, such as `fix: preserve paused issue state` or `docs: clarify retry controls`,
with no body or trailers. Keep issue references in the PR description.

Agent-assisted contributions follow the same checks; review and understand the code you submit. A human makes the
final merge decision. Contributions use the repository's [Apache-2.0 license](LICENSE).

## Notes for maintainers

GitHub releases and PyPI releases are separate manual actions. CI validates Python packages; the maintainer builds
and uploads the chosen version locally with Poetry 2.5.1, matching CI, and the poetry-core backend. Sign every new
release tag explicitly with SSH. Signing records the maintainer's deliberate release decision.

### Releasing a new version

1. Choose the version and prepare release notes covering changes since the previous tag, including configuration
   changes and upgrade instructions. Stable versions use `X.Y.Z`; prereleases include a suffix such as `X.Y.Za1`.
2. Update `version` in [pyproject.toml](pyproject.toml) and `__version__` in
   [orchestrator/__init__.py](orchestrator/__init__.py) together, then run
   `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry check --lock`. A version-only bump needs no lock change.
   Update affected documentation and submit the release preparation as a PR to `main`.
3. Run the [full pre-push checklist](.agents/skills/develop/SKILL.md#pre-push-checklist), merge the PR, and wait for
   CI on the exact release commit to pass on Python 3.12, 3.13, and 3.14. The
   [CI reference](docs/configuration.md#continuous-integration) explains the lint, test, build, and installed-CLI
   checks.
4. Use a separate, clean release checkout. Confirm that the selected commit is on `main` and both version fields
   match the chosen version. Confirm the tag ruleset protects `v*` against unauthorized creation, updates, and
   deletion under the
   [release policy](docs/security.md#no-ci-publishing--deploys-outside-protected-refs).

Review that commit and message before signing. Use the passphrase-protected release key whose public key is
`~/.ssh/git_release_signing_ed25519.pub`; make the corresponding private key available through `ssh-agent`, unlocking
it with `ssh-add ~/.ssh/git_release_signing_ed25519` when needed.

Create a signed annotated tag for the exact commit checked in step 3, with settings scoped to this invocation.
Replace `<release-sha>` with that commit's full SHA. `tag -s` explicitly requests the signature:

```bash
git -c gpg.format=ssh \
  -c user.signingKey="$HOME/.ssh/git_release_signing_ed25519.pub" \
  tag -s vX.Y.Z '<release-sha>' -m 'vX.Y.Z: <short release summary>'
git push origin vX.Y.Z
```

On the repository's **Releases** page select that existing signed tag and save the corresponding release with
extended release notes as a draft. For prerelease versions, select **This is a pre-release**. Publish the draft only
after the PyPI upload, digest comparison, and installation checks below succeed.
[GitHub release instructions][github-releases]

### Publishing to PyPI

Build from a clean checkout of the signed release tag whose commit is on `main` and has passing CI. Confirm that
the tag and both version fields match. Before the first PyPI upload, verify the package's README, project URLs,
license metadata, and installed configuration behavior, including `.env` discovery and path defaults. Verify that
self-update detection stays inert when the installed package is not inside a git checkout. Test configuration from an
unrelated launch directory separately from the CLI's `--help` smoke test, which must work without repository
configuration.

The release machine needs Poetry 2.5.1 and real Python 3.12, 3.13, and 3.14 interpreters, installed through the
distribution or built with pyenv. Make them available as `python3.12`, `python3.13`, and `python3.14` on `PATH`.
Install the export plugin into Poetry's pipx environment using the same pin as the
[vulnerability-scan workflow](.github/workflows/vulnerability-scan.yml), and install Twine separately:

```sh
pipx install --force "poetry==2.5.1"
pipx inject poetry "poetry-plugin-export==1.10.1"
pipx install --force "twine==7.0.0"
env -u VIRTUAL_ENV -u CONDA_PREFIX poetry --version
```

The export plugin and Twine are maintainer tools, outside the project's dependency groups.
[Export plugin installation][poetry-export], [Twine checks][twine-check]

Sign in to PyPI as `geserdugarov`, verify the account's email, and enable two-factor authentication. Create an API
token under **Account settings → API tokens**. The first upload needs **Entire account** scope; after the project
exists, create a token scoped to `chipping-orchestrator` and revoke the account-scoped token. Keep tokens in your
credential store outside the repository and load them only for local publishing through `POETRY_PYPI_TOKEN_PYPI`.
Keep them out of `.env`, repository files, and GitHub Actions secrets. Do not save the token with Poetry's
configuration command; it would remain available to later publishing commands.
[PyPI token instructions](https://pypi.org/help/#apitoken)

The first successful upload establishes ownership of the name. A pending Trusted Publisher does not reserve it.
An early upload can be a real alpha release of the application, following the same release checks and matching
prerelease tag above. Empty reservation packages count as name squatting.
[PyPI project creation](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
[name-retention policy](https://peps.python.org/pep-0541/#invalid-projects)

Build one wheel and source distribution into a fresh version-specific directory. Replace `X.Y.Z` below with the
release tag's version without the `v` prefix, including any prerelease suffix. Run these blocks in the same Bash
session; the paths are absolute so the install checks can run outside the checkout. A failed block must stop the
release; correct the failure before proceeding to the next block. The build block requires a clean checkout,
refreshes `origin/main`, and checks that the tag's commit is on that branch. It verifies the tag against the release
public key with an invocation-scoped [allowed signers file][git-ssh-signatures] and checks that `HEAD` is the tagged
commit:

```bash
RELEASE_VERSION='X.Y.Z'
RELEASE_TAG="v${RELEASE_VERSION}"
RELEASE_DIST="$PWD/dist/pypi-${RELEASE_VERSION}"
RELEASE_WHEEL="$RELEASE_DIST/chipping_orchestrator-${RELEASE_VERSION}-py3-none-any.whl"
RELEASE_SDIST="$RELEASE_DIST/chipping_orchestrator-${RELEASE_VERSION}.tar.gz"
(
  set -e
  test ! -e "$RELEASE_DIST"
  test -z "$(git status --porcelain --untracked-files=all)"
  git fetch origin main
  git merge-base --is-ancestor "$RELEASE_TAG" origin/main
  RELEASE_ALLOWED_SIGNERS="$(mktemp)"
  trap 'rm -f "$RELEASE_ALLOWED_SIGNERS"' EXIT
  {
    printf 'release '
    cat "$HOME/.ssh/git_release_signing_ed25519.pub"
  } > "$RELEASE_ALLOWED_SIGNERS"
  git -c gpg.format=ssh \
    -c gpg.ssh.allowedSignersFile="$RELEASE_ALLOWED_SIGNERS" \
    verify-tag "$RELEASE_TAG"
  test "$(git rev-parse HEAD)" = "$(git rev-parse "$RELEASE_TAG^{commit}")"
  env -u VIRTUAL_ENV -u CONDA_PREFIX poetry check --lock
  env -u VIRTUAL_ENV -u CONDA_PREFIX poetry build --output "$RELEASE_DIST"
  python3.12 -m zipfile -l "$RELEASE_WHEEL"
  tar -tzf "$RELEASE_SDIST"
  twine check --strict "$RELEASE_WHEEL" "$RELEASE_SDIST"
  env -u VIRTUAL_ENV -u CONDA_PREFIX poetry export --only main --without-hashes \
    -f constraints.txt --output "$RELEASE_DIST/constraints.txt"
)
```

Inspect the archive lists and the wheel's `METADATA` and sdist's `PKG-INFO`: check the name, version, Python
requirement, runtime dependency bounds, README, URLs, and license. The wheel carries `orchestrator/` and its
distribution metadata; the sdist also carries `pyproject.toml`, `README.md`, and `LICENSE`. Neither archive should
contain `tests/`, `plans/`, agent configuration, or `.env` files. The constraints export contains only the tested
runtime dependencies, without hashes so pip can also resolve the root package when the file is used as a constraint.
Retain the wheel, sdist, and constraints file unchanged for publishing and retries.

For each interpreter, install the wheel and sdist into separate virtual environments outside the source tree and
run the installed CLI. A missing interpreter or failed check must stop the release:

```bash
(
  set -e
  RELEASE_SMOKE_ROOT="$(mktemp -d)"
  cd "$RELEASE_SMOKE_ROOT"
  for RELEASE_PYTHON in python3.12 python3.13 python3.14; do
    for RELEASE_ARTIFACT in "$RELEASE_WHEEL" "$RELEASE_SDIST"; do
      RELEASE_ENV="$RELEASE_SMOKE_ROOT/${RELEASE_PYTHON}-$(basename "$RELEASE_ARTIFACT")"
      "$RELEASE_PYTHON" -m venv "$RELEASE_ENV"
      "$RELEASE_ENV/bin/python" -m pip install --no-cache-dir "$RELEASE_ARTIFACT"
      "$RELEASE_ENV/bin/chipping-orchestrator" --help
    done
  done
)
```

After all checks pass, enter the API token at the hidden Bash prompt. Run the publish block from the same tagged
checkout, using the retained directory without rebuilding. Poetry uses the checkout's project name to select wheel
and sdist filenames, then uploads only the latest version present in that directory. The fresh version-specific
directory limits the upload to the two checked distributions; `constraints.txt` is not a distribution and is ignored.
See [Poetry's publishing options][poetry-publish]. The subshell discards the token when the upload finishes:

```bash
(
  read -rsp 'PyPI API token: ' POETRY_PYPI_TOKEN_PYPI || exit
  export POETRY_PYPI_TOKEN_PYPI
  env -u VIRTUAL_ENV -u CONDA_PREFIX poetry publish --dist-dir "$RELEASE_DIST"
)
```

PyPI's JSON API and package index can lag just after an upload; if the version or files are missing, wait a minute
and retry the digest and installation checks.

Verify the version, files, and ownership on the PyPI project page. Compare PyPI's SHA-256 digests with the retained
files using the [release JSON API][pypi-json]:

```bash
python3.12 - "$RELEASE_VERSION" "$RELEASE_WHEEL" "$RELEASE_SDIST" <<'PY'
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

version, *paths = sys.argv[1:]
url = f"https://pypi.org/pypi/chipping-orchestrator/{version}/json"
with urllib.request.urlopen(url, timeout=30) as response:
    uploaded = {entry["filename"]: entry["digests"]["sha256"] for entry in json.load(response)["urls"]}
for name in paths:
    artifact = Path(name)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if uploaded.get(artifact.name) != digest:
        raise SystemExit(f"PyPI SHA-256 mismatch: {artifact.name}")
    print(f"{artifact.name}: SHA-256 matches")
PY
```

Check installation of that exact version from PyPI in fresh environments, with and without the constraints file:

```bash
(
  set -e
  RELEASE_PYPI_ROOT="$(mktemp -d)"
  cd "$RELEASE_PYPI_ROOT"
  for RELEASE_MODE in default constrained; do
    RELEASE_ENV="$RELEASE_PYPI_ROOT/$RELEASE_MODE"
    python3.12 -m venv "$RELEASE_ENV"
    RELEASE_PIP_ARGS=()
    if [ "$RELEASE_MODE" = constrained ]; then
      RELEASE_PIP_ARGS=(--constraint "$RELEASE_DIST/constraints.txt")
    fi
    "$RELEASE_ENV/bin/python" -m pip install --no-cache-dir --index-url https://pypi.org/simple \
      "${RELEASE_PIP_ARGS[@]}" "chipping-orchestrator==${RELEASE_VERSION}"
    "$RELEASE_ENV/bin/chipping-orchestrator" --help
  done
)
```

After the digest and installation checks pass, attach `constraints.txt` from the retained directory to the draft
GitHub release for the same tag and publish it. Record its publication date and functionality in the
[release timeline](docs/release-timeline.md). Operators can optionally apply the constraints file through pipx;
see [package installation, upgrades, and rollback](docs/configuration.md#package-installation-upgrades-and-rollback).

If an upload is interrupted, reload the token and rerun the same publish command with the retained files, without
`--build` or `--skip-existing`. PyPI accepts identical re-uploads and rejects conflicting contents; skipping that
rejection could hide a conflict. Repeat the digest and installation checks after a retry. Corrected package contents
require a new version. [Poetry publishing options][poetry-publish], [PyPI upload handler][pypi-upload]

Keep the PyPI project after the initial upload: deleting it releases the name.
[PyPI deletion rules](https://pypi.org/help/#project-deletion)

[github-releases]:
  https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository
[git-ssh-signatures]: https://git-scm.com/docs/git-config#Documentation/git-config.txt-gpgsshallowedSignersFile
[poetry-export]: https://github.com/python-poetry/poetry-plugin-export#installation
[twine-check]: https://twine.readthedocs.io/en/stable/#twine-check
[poetry-publish]: https://python-poetry.org/docs/cli/#publish
[pypi-json]: https://docs.pypi.org/api/json/#get-a-release
[pypi-upload]: https://github.com/pypi/warehouse/blob/main/warehouse/forklift/legacy.py
