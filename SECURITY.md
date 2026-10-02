# Security policy

## Reporting a vulnerability

Report a suspected vulnerability **privately**, through GitHub Private Vulnerability Reporting on this repository:
open the [Security tab](https://github.com/chippingway/chipping-orchestrator/security) and choose **"Report a
vulnerability"**. That opens an advisory draft only the maintainer and the people invited to it can read.

Please do **not** open a public issue, pull request, or discussion for one. Issues on this repository drive an
automated agent workflow, so a public report is not merely visible early — it is picked up and worked on in the open
before a fix exists.

Include what you would need yourself to reproduce it: the version or commit, the configuration involved (env vars and
labels, with secrets redacted), the steps, and the impact you believe it has.

## Supported versions

| Version           | Supported |
| ----------------- | --------- |
| latest release    | yes       |
| `main`            | yes       |
| earlier releases  | no        |

Fixes land on `main` and ship in the next release; earlier releases are not patched.

## What to expect

This is a solo-maintained project, so these are best-effort targets rather than a contractual SLA:

- **Acknowledgement within 7 days** that the report arrived and is being looked at.
- **An assessment within 30 days** — a fix, a fix in progress with a target, or the reason the report is not treated
  as a vulnerability.
- Credit in the published advisory, unless you would rather not be named.

Please give the maintainer a chance to publish a fix before disclosing publicly.

## Hardening posture

This page is the reporting channel. How the repository's own controls map to the project security checklist — what
the files in the repo enforce, and what an operator has to switch on in GitHub — is in
[`docs/security.md`](docs/security.md).

One deployment note belongs here, because it decides how a report is triaged: the orchestrator spawns `codex` /
`claude` CLI subprocesses with sandbox-bypass flags, so the **host** it runs on is the trust boundary, not the agent
process. Run it on its own host, VM, or container rather than beside other workloads' secrets.
