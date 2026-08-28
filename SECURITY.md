# Security Policy

## Supported Versions

Archetype is pre-1.0 (Alpha). Security fixes are made against the latest
released version on PyPI. Older `0.x` releases do not receive backports.

| Version | Supported |
| --- | --- |
| Latest `0.x` release | Yes |
| Older `0.x` releases | No |

## Reporting a Vulnerability

Please do not open a public GitHub issue for security vulnerabilities.

Report suspected vulnerabilities privately by emailing
**mossabarektout2000@gmail.com** with:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, or a minimal proof of concept.
- The Archetype version and Python version affected.

You should receive an acknowledgement within 5 business days. We'll work
with you to confirm the issue, prepare a fix, and agree on a disclosure
timeline before any public details are published. Credit is given in the
release notes unless you ask to remain anonymous.

## Scope

In scope:

- The `archetype` Python package and its CLI.
- The GitHub Actions workflows and release process used to build and
  publish `archetype-py` to PyPI.

Out of scope:

- Vulnerabilities in third-party dependencies (`click`, `rich`,
  `networkx`) — please report those upstream. If a dependency
  vulnerability affects Archetype directly, we'll still take a fix.

## Security Model

Archetype loads and executes `architecture.py` as ordinary Python code —
it is not a declarative, sandboxed data format. Anything that file can do,
your rules can do, with the same privileges as the process running
`archetype check` (including CI secrets and repository write access, if
the workflow grants them).

This matters most in CI. If `archetype check` runs against a pull request
from an untrusted fork, and that PR can modify `architecture.py`, the
PR effectively gets arbitrary code execution in your CI environment the
moment the check runs — the same risk category as any other
"config-as-code" file (e.g. `conftest.py`, `setup.py`, a Makefile).

Recommendations:

- Use the default `pull_request` trigger (runs with a read-only token and
  no access to repository secrets) rather than `pull_request_target`
  unless you fully understand the checkout implications of the latter.
- Do not check out and run untrusted fork PR code in a workflow that has
  `secrets` or elevated `permissions:` — keep `archetype check` in a job
  scoped to `permissions: contents: read` and nothing else.
- Treat `architecture.py` changes in review the same way you'd treat
  changes to any other CI-executed file.

Archetype itself makes no network calls and sends no telemetry — it only
reads source files on disk and writes reports to stdout/files you specify.
