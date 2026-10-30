# Qualcomm AI Hub MCP

> **Unofficial project.** This is an independent community project. It is not
> affiliated with, endorsed by, or supported by Qualcomm. Qualcomm and Qualcomm AI
> Hub are trademarks of Qualcomm Incorporated or its subsidiaries.

> **`confirm=true` is not human approval.** Sensitive tools need `confirm=true`, but
> a model can set that value itself. Require approval in your MCP client for
> `submit_*`, `upload_*`, `create_project`, `*_modify_sharing`, `*_disable_sharing`,
> and `job_set_name`, and do not auto-approve them.

**Status: beta.** See [what has been verified](ACCEPTANCE.md).

A standalone Python 3.11+ MCP stdio server for the Qualcomm AI Hub Core API.
It uses the official `qai-hub 0.57.0` and `mcp 2.3.0` SDKs. The official MCP SDK
calls its high-level server `MCPServer` (formerly `FastMCP`).

## Install

```sh
python -m pip install .
```

Install it in its own virtual environment. It pins exact `mcp` and `qai-hub`
versions, which can conflict with other packages in a shared environment.

Configure your MCP client to launch `qualcomm-ai-hub-mcp`, or use
`python -m qualcomm_ai_hub_mcp`. Both entry points accept:

- `--workspace PATH`: existing directory allowed for model/data files and outputs;
  defaults to the startup directory.
- `--profile NAME`: official Qualcomm SDK named configuration profile.
- `--version`: print the installed version.

Use an absolute executable path when a GUI client does not inherit your shell PATH.
Windows virtual environments put the executable in `Scripts`; Unix environments
put it in `bin`.

## Compatibility and limits

- Each release targets one `qai-hub` version. Newer SDK versions need a new release
  of this server.
- `submit_profile_job` and `submit_compile_and_profile_jobs` are deprecated by the
  SDK and will be removed after the SDK removes them. Use `submit_inference_job`.
- There is no delete tool. Remove uploaded models, jobs, datasets, and projects
  through Qualcomm's own tools.

## Your data and costs

Uploads and submissions send your models and data to Qualcomm, where they are stored
and processed under your account. Jobs run on Qualcomm-hosted devices. Review
Qualcomm's terms and pricing before use, because this server does not track usage or
cost.

This server adds no telemetry of its own. Its remote calls go through the official
Qualcomm SDK, which has its own behavior and terms.

## Authentication

Use one of these methods:

1. Run the official `qai-hub configure --api_token YOUR_TOKEN` command. The SDK
   uses `~/.qai_hub/client.ini` by default.
2. Set the official `QAIHUB_CLIENT_INI` variable to a configuration-file path.
3. Pass `--profile NAME` to select `~/.qai_hub/NAME.ini`.
4. Set connector-defined `QAI_HUB_API_TOKEN`; the connector passes it to the
   official SDK's `ClientConfig` using Qualcomm's default endpoints.

An explicit token and named profile cannot be combined. Keep credentials in the
client's environment or SDK configuration, never in tool arguments. Discovery
works without credentials; operations return an authentication error when local
configuration is absent. No credential-setting tool is exposed.

## Generic MCP client configuration

Clients use different configuration formats. For clients that accept
`mcpServers`, use:

```json
{
  "mcpServers": {
    "qualcomm": {
      "command": "qualcomm-ai-hub-mcp",
      "args": ["--workspace", "/absolute/models-and-data"]
    }
  }
}
```

This is a local stdio server, not an HTTP endpoint. Stdout carries MCP messages;
SDK progress and diagnostics go to stderr through the official transport.

## Tool inputs

Discover tools to obtain their full schemas and SDK documentation. Public SDK
parameter names, defaults, nullability, enum names and multi-device variants are
preserved. [API coverage](docs/API_COVERAGE.md) lists every exposed operation.

Python objects use these JSON equivalents:

| SDK value | MCP input |
|---|---|
| Uploaded model or dataset | `{"id":"existing-id"}` |
| Local model/dataset file | `{"path":"relative/or/absolute/path"}` |
| Device | `{"name":"device name","os":"","attributes":[]}` |
| Shape-only input spec | `{"image":[1,3,224,224]}` |
| Shape and dtype input spec | `{"image":[[1,3,224,224],"float32"]}` |
| Enum | Its SDK name, e.g. `"INT8"`, `"INFERENCE"`, `"DEVICE_LOG"` |
| Project | Project ID string |

`upload_model` accepts a local file or model directory. `upload_dataset` accepts
an HDF5 file or an inline dataset. Submission tools can resolve existing IDs.
Saved model files replace framework-specific Python objects; no PyTorch/ONNX/Core
ML runtime is required merely to upload them.

Inline datasets preserve feature order explicitly:

```json
{
  "features": [
    {"name":"x","samples":[{"dtype":"int8","shape":[2],"base64":"AQI="}]}
  ]
}
```

Each sample contains C-order bytes, a numeric NumPy dtype, and its shape. This
preserves non-finite floating-point values, byte order, and large integers.
Feature names must be unique and sample counts must match. Inline data is limited
to 16 MiB of decoded tensor bytes; use HDF5 files for larger datasets. Downloaded
inline tensors use the same encoding. Input/output model specifications return
ordered `graphs` records so unnamed graphs remain distinct from graphs named
`"null"`.

## Example workflow

Call these tools through your MCP client:

1. `get_devices` with `{}` to select a device.
2. `upload_model` with
   `{"model":{"path":"model.onnx"},"confirm":true}`.
3. `submit_compile_job` with the returned model ID:
   `{"model":{"id":"MODEL_ID"},"device":{"name":"DEVICE_NAME"},"confirm":true}`.
4. `job_get_status` with `{"job_id":"JOB_ID"}` to poll.
5. `compilejob_get_target_model` with `{"job_id":"JOB_ID"}` to retrieve the
   resulting model reference.
6. `model_download` with
   `{"model_id":"TARGET_MODEL_ID","filename":"outputs/model"}`.

Inference jobs profile by default. Omitting `inputs` runs profiling on generated
input data. Supplying `profile=false` requires real inputs. Legacy profile and
compile-and-profile tools remain available as SDK compatibility operations.

Individual submissions return remote job references. Compound SDK helpers and
result/model retrieval can wait for upstream jobs; they run in worker threads so
other MCP requests remain responsive. SDK `retry` and `timeout` parameters keep
their documented meanings. The connector adds no submission retries or task queue.
Cancelling a local call does not cancel a remote job, and an already-started SDK
call may finish in the background. After a transport failure, check existing jobs
before resubmitting. Prefer a `timeout` on long waits: clients that stop waiting
without sending an MCP cancellation keep a worker thread busy until the SDK call
returns, and 40 busy threads block further tool calls.

Successful calls return `{"result":...}` in structured content and JSON text.
Operational errors set MCP `isError=true` and return
`{"error":{"code":"AUTHENTICATION","message":"...","retryable":false}}`.
Schema validation errors use the MCP SDK's standard error response. Job failure
is represented in the returned job status; retrieving a failed status is itself a
successful API call.

## Authorization and files

Uploads, submissions, project creation, renaming, and sharing changes require the
literal boolean `confirm=true`. Missing/false confirmation is rejected before SDK
access. The MCP client must obtain human approval; a tool argument cannot prove
who approved it. No operation-wide permissions are silently enabled.

Choose a dedicated workspace containing only models and data the client may
access. Paths outside it, the workspace root as a model directory, protected
configuration/credential paths, model-directory symlinks, unsafe archive entries,
and HDF5 external/soft links or external storage are rejected. This is an
application file-access policy, not an OS sandbox.

Qualcomm IDs may contain only letters, digits, `-` and `_`. Anything else is
rejected before reaching the SDK.

Downloads use per-call temporary staging and exclusive output creation. Existing
files/directories are never overwritten, including SDK-appended extensions.
Server-provided filenames are checked before transfer. Archives remain zipped.
Result bundles use fixed `logs`, `model`, `dataset`, and `profile.json` locations.
When an optional target-model filename is omitted, the saved artifact goes under
`workspace/artifacts/<unique-id>/`; Python model objects are not deserialized.

## VS Code

Place this in `.vscode/mcp.json`; VS Code uses `servers`:

```json
{
  "servers": {
    "qualcomm": {
      "type": "stdio",
      "command": "qualcomm-ai-hub-mcp",
      "args": ["--workspace", "/absolute/models-and-data"]
    }
  }
}
```

Use **MCP: List Servers**, start `qualcomm`, and verify its tools appear. With
credentials configured, invoke `get_devices`. A sensitive call without confirmation
must return `AUTHORIZATION_REQUIRED`. See [acceptance results](ACCEPTANCE.md) for
what was actually verified. VS Code's setup and trust controls are described in
[its official MCP documentation](https://code.visualstudio.com/docs/agent-customization/mcp-servers).

## Tests

```sh
python -m pip install ".[test]"
python -m pytest -q
python tests/package_acceptance.py
```

Tests mock the official SDK. They cover each registered operation, schemas,
conversions, credentials, file security, downloads, real stdio subprocesses,
legacy protocol negotiation, errors, noisy SDK output, and concurrent polling.
The package check builds a wheel/sdist and tests both entry points in a clean venv.
CI is configured for Python 3.11, 3.12, and 3.13 on Linux, macOS, and Windows.

To opt into a read-only live Qualcomm check, configure credentials and set
`QAI_HUB_MCP_LIVE=1` before running `python -m pytest tests/test_live.py -q`.
It never uploads data or submits jobs. No live Qualcomm behavior is claimed by
the mocked tests; see the acceptance report for platform and live-test limits.

## License

Licensed under the [Apache License 2.0](LICENSE). This license covers this project
only; the Qualcomm AI Hub service and `qai-hub` SDK have their own terms.
