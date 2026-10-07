# Remaining PyPI release work

Working notes for unfinished release validation and publication follow-up. The recurring tag, build, upload, retry, and
constraints-asset procedure lives in the [maintainer release guide](../CONTRIBUTING.md#notes-for-maintainers).

## Remaining validation and policy

- Cover configuration reuse and diagnostics across a manual package upgrade and rollback. Reuse the existing
  installed-layout and startup-refusal coverage rather than repeating its scenarios.
- Validate the installation and upgrade instructions in isolated pipx and venv environments, including constrained
  installs and saved settings from a previous version. Exercise configured startup outside a source checkout;
  the release guide's `--help` checks alone do not exercise configuration loading.
- Document local publishing credentials in [security](../docs/security.md), preserving the existing GitHub Pages
  deployment policy.

## Publication follow-up

- Complete the maintainer guide's post-upload installation checks for `0.13.0`, with and without runtime constraints.
- Export runtime constraints from the signed `v0.13.0` tag and attach `constraints.txt` to that GitHub release.

These notes do not authorize uploads or live changes to an operator's deployment.
