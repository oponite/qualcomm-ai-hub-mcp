# Repository Guidelines

## Project Structure & Module Organization

This Python 3.11+ project provides an MCP stdio server for Qualcomm AI Hub.
Source files live in `src/qualcomm_ai_hub_mcp/`:

- `contracts.py` defines the operation registry and tool signatures.
- `server.py` registers tools and handles transport.
- `adapter.py` converts arguments and calls the SDK.
- `config.py`, `downloads.py`, `serialization.py`, and `errors.py` enforce boundaries and encode results.

`tests/` contains pytest tests, a subprocess fixture, and package acceptance checks.
`docs/` contains API coverage, input examples, and the security model.
`ACCEPTANCE.md` records verified behavior.

## Build, Test, and Development Commands

Run commands from the repository root:

```sh
uv sync --extra test
.venv/bin/python -m pytest -q
.venv/bin/python tests/package_acceptance.py
uvx ruff@0.17.3 check .
uvx ruff@0.17.3 format --check .
.venv/bin/qualcomm-ai-hub-mcp --workspace /absolute/path/to/workspace
```

These commands install dependencies, run tests, validate wheel/sdist installation, check lint and formatting, and start the stdio server.
After dependency changes, run `uv lock` and commit `uv.lock`.

## Coding Style & Naming Conventions

Use four-space indentation and Ruff formatting.
Use `snake_case` for functions, modules, and variables, and `PascalCase` for classes.
Keep changes compatible with Python 3.11 and the pinned SDK versions.
Keep diagnostic output on stderr because stdout carries MCP messages.

For tool changes, update `contracts.py` and `docs/API_COVERAGE.md`.
Add parameter mappings, serializer support, and `DOWNLOAD_METHODS` entries where applicable.

## Testing Guidelines

Name test files `test_*.py` and functions `test_*`.
Add regression tests for behavior changes.
Inject fake SDKs through `create_server(sdk=...)`.
Offline tests require no credentials.
CI runs Python 3.11–3.13 on Linux, macOS, and Windows, with coverage reporting but no minimum threshold.

For read-only live discovery, run:

```sh
QAI_HUB_MCP_LIVE=1 .venv/bin/python -m pytest tests/test_live.py -q
```

Require explicit opt-in for tests that upload data or submit jobs.

## Commit & Pull Request Guidelines

Use short imperative commit subjects, such as `Document real-model results and dynamic shapes`.
Keep pull requests focused.
Describe behavior changes and report only checks actually run.
Record user-facing changes in `CHANGELOG.md`.

## Security & Configuration

Use `RemoteId` for remote IDs and `config.path()` for local paths.
Preserve sensitive-operation confirmation and sanitized errors.
Keep tokens and private data out of commits, logs, and tool results.
Report vulnerabilities privately through `SECURITY.md`.
