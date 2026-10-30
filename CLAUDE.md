# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Python 3.11+ MCP stdio server wrapping the Qualcomm AI Hub Core API. `qai-hub==0.57.0` and `mcp==2.3.0` are pinned exactly; the `MCPServer` class in `mcp` 2.x is what was formerly `FastMCP`.

## Commands

`.venv` is a uv-managed editable install with the test extras, and has no `pip`. Run `uv lock` after changing dependencies. `ruff` is not a project dependency; run it through `uvx`. Its rules are set in `pyproject.toml`.

```sh
uv sync --extra test                              # (re)install from uv.lock
.venv/bin/python -m pytest -q                     # full suite; 253 pass, 1 skipped (live)
.venv/bin/python -m pytest tests/test_security.py -q
.venv/bin/python -m pytest "tests/test_contracts.py::test_each_operation_forwards_typed_parameters[get_devices]" -q
.venv/bin/python tests/package_acceptance.py      # builds wheel/sdist, installs in a clean venv, tests both entry points
uvx ruff@0.17.3 check . && uvx ruff@0.17.3 format --check .
```

Live check (read-only, needs credentials): `QAI_HUB_MCP_LIVE=1 .venv/bin/python -m pytest tests/test_live.py -q`. Everything else mocks the SDK.

CI (`.github/workflows/test.yml`) runs ruff, gitleaks, pytest with coverage, and `package_acceptance.py` on Python 3.11 to 3.13 across Linux, macOS and Windows. Actions are pinned to commit SHAs. `sdk-drift.yml` runs weekly against the latest `qai-hub` and `mcp`. See `ACCEPTANCE.md` for what has and has not been verified.

## Architecture

Tools are generated from the SDK, not hand-written. The flow for a call:

1. `contracts.py` holds the registry. `CLIENT_METHODS` and `OBJECT_METHODS` expand into `OPERATIONS`, one `Operation` per tool. `tool_signature()` builds each tool's signature by introspecting the SDK method, swapping in JSON types from `parameter_type()`. An SDK parameter with an unmapped annotation raises `TypeError` in `create_server`.
2. `server.py` registers each operation with `MCPServer`, using the SDK docstring as the tool description. It checks `confirm` before anything else, then runs `Adapter.invoke` in a worker thread so SDK blocking stays off the event loop.
3. `adapter.py` lazily builds the client, resolves the `{kind}_id` target for object methods, and converts arguments (references, paths, devices, enum names) to SDK values. Download methods go to `Downloads`; everything else calls the SDK directly.
4. `serialization.py` encodes results with an explicit allowlist of SDK types. Unknown types raise, so a client or its config can never be traversed into output.
5. `errors.py` maps exceptions to fixed `{"error":{code,message,retryable}}` records. Raw SDK messages are never forwarded, since they can carry credentials.

Tool names: client methods keep their name; object methods become `{prefix}_{method}` (`job_get_status`, `compilejob_get_target_model`), plus the property reads `model_get_{metadata,input_spec,output_spec}`.

## Invariants

- **Sensitive operations** are derived in `Operation.sensitive`: any `submit_*`, `upload_*`, `create_*`, plus `modify_sharing`, `disable_sharing`, `set_name`. They get a `confirm` parameter, and only the literal `True` passes. Rejection happens before any SDK access.
- **No retries or queues.** The connector adds no submission retries. For sensitive calls, `error_result` forces `retryable=False` on ambiguous failures (timeout, network, 5xx, internal) because the remote change may have completed.
- **Every ID input must use `RemoteId`.** IDs are checked against a strict character set before they reach the SDK. `test_every_id_input_has_the_id_pattern` enforces this for `*_id` and `project` inputs.
- **Worker calls use `abandon_on_cancel=True`** so cancelled waits free their slot and polling keeps working. Abandoned calls can still complete remotely.
- **Discovery must work without credentials.** Client creation is lazy; `config.client()` only loads local configuration. `QAI_HUB_API_TOKEN` and `--profile` are mutually exclusive.
- **All local paths go through `config.path()`.** It enforces the workspace root and refuses protected names (`.ssh`, `.qai_hub`, `.env*`, credential files). With `output=True` it refuses existing targets. Input model files also pass `validate_model_archive`, and HDF5 inputs pass `validate_hdf5`.
- **Downloads bypass the SDK's object-level `download*` methods** for models, artifacts and remote datasets. `Downloads` fetches the signed URL info, checks the server-provided filename with `safe_name`, transfers into a per-call temp stage using the SDK's low-level transfer helpers, then publishes with exclusive create (`"xb"`). Archives stay zipped, and model objects are never deserialized.
- **Stdout is the MCP wire.** SDK output must stay on stderr; `test_protocol.py` covers Python and native stdout noise.
- **Inline tensors** are capped at `MAX_INLINE_BYTES` (16 MiB) and carry dtype/shape/base64. Dataset features and graph specs are ordered lists, not maps.

## Changing the tool surface

`test_contracts.py` pins the registry to the SDK. `test_registry_matches_sdk_surface` requires `CLIENT_METHODS`/`OBJECT_METHODS` to equal the SDK's public surface exactly (`set_session_token` is the one exclusion), so an SDK version bump will fail here until the registry is updated.

Adding or renaming an operation also requires:

1. A row in `docs/API_COVERAGE.md`; `test_coverage_document_matches_registry` compares it to the registry.
2. A `parameter_type()` mapping for any non-scalar parameter.
3. A serializer branch in `encode()` for any new SDK result type.
4. An entry in `DOWNLOAD_METHODS` if it writes files, which also sets its `read_only_hint` to false.

The tool count (57) is also stated in `docs/API_COVERAGE.md` and `ACCEPTANCE.md`.

## Testing

`tests/stdio_fixture.py` is an offline fake SDK launched as a real subprocess for transport tests; it is not a shipped CLI option. `create_server(sdk=...)` is the injection point for mocks. `test_each_operation_forwards_typed_parameters` is parametrized over every operation, using tool names as test IDs.

## Project records

The version lives only in `pyproject.toml`; `__version__` reads it from installed package metadata. `ACCEPTANCE.md` is the verification report. It states tested counts and versions, so update it only with results that were actually run. `WORK_LOG.md` is a local, untracked implementation history. `MANIFEST.in` lists the docs, tests and policy files that ship in the sdist.
