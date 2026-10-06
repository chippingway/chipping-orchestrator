# Remaining work before the first PyPI release

Working notes for unfinished release preparation. The recurring tag, build, validation, upload, retry, and
constraints-asset procedure lives in the [maintainer release guide](../CONTRIBUTING.md#notes-for-maintainers).

## Remaining validation and policy

- Cover configuration reuse and diagnostics across a manual package upgrade and rollback. Reuse the existing
  installed-layout and startup-refusal coverage rather than repeating its scenarios.
- Validate the installation and upgrade instructions in isolated pipx and venv environments, including constrained
  installs and saved settings from a previous version. Exercise configured startup outside a source checkout;
  the release guide's `--help` checks alone do not exercise configuration loading.
- Document local publishing credentials and protected release tags in [security](../docs/security.md), preserving
  the existing GitHub Pages deployment policy.

## First publication

- Complete the release machine and PyPI account setup in the maintainer guide, including Poetry **2.5.1**, the
  separately installed export plugin and Twine, and real Python 3.12, 3.13, and 3.14 interpreters.
- Choose the first release version, or a real prerelease if claiming the name before the stable release. Follow the
  maintainer guide from the signed tag through artifact checks, local upload, SHA-256 comparison, installation checks,
  and attaching `constraints.txt` to the GitHub release. Record the publication in the
  [release timeline](../docs/release-timeline.md).
- After the first upload, confirm `geserdugarov` owns the project, replace the temporary account-scoped API token with
  a project-scoped token, and revoke the temporary token. Keep credentials outside the repository.

A PyPI organization and transfer into it remain optional follow-up work. This plan does not select a version,
perform an upload, or authorize live changes to an operator's deployment.
