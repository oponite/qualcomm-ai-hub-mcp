# Contributing

Report security problems through [SECURITY.md](SECURITY.md), not public issues.

## Setup

Use Python 3.11 or newer and [uv](https://docs.astral.sh/uv/). `uv.lock` pins the
development and CI environment:

```sh
uv sync --extra test
```

After changing dependencies, run `uv lock` and commit the result.

## Checks

All of these should pass before you open a pull request:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python tests/package_acceptance.py
uvx ruff@0.17.3 check .
uvx ruff@0.17.3 format --check .
```

The test suite mocks the Qualcomm SDK and needs no account or token.

## Live checks

`QAI_HUB_MCP_LIVE=1 python -m pytest tests/test_live.py -q` makes a read-only call
with your configured credentials. Never add live tests that upload data or submit
jobs without an explicit opt-in. These can change an account and may be billable.

## Changing the tool surface

Tools are generated from the registry in `contracts.py`, which tests compare to the
pinned SDK. When you add or rename an operation, also update:

1. `docs/API_COVERAGE.md`.
2. `parameter_type()`, for any parameter that is not a plain scalar.
3. `encode()`, for any new SDK result type.
4. `DOWNLOAD_METHODS`, if the operation writes files.

The weekly `SDK drift` workflow runs these tests against the latest `qai-hub` and
`mcp`. If it fails, update the registry and the pins together.

Any new ID input must use `RemoteId`, and any new local path must go through
`config.path()`.

## Pull requests

Keep each change focused and add a test for any behavior change. Add user-facing
changes to `CHANGELOG.md`. Report only test results you actually ran.
