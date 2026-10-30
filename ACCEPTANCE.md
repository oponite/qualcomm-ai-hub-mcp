# Acceptance results

Verified locally on 2026-10-30: macOS arm64, Python 3.11.16,
`qai-hub 0.57.0`, `mcp 2.3.0`, VS Code 1.144.0.

| Boundary | Result |
|---|---|
| SDK surface and parameter mapping | All 57 registered operations have mocked invocation coverage; registry parity and schema/default checks pass. |
| Full source suite | 253 passed; one optional live test skipped. |
| Tensor and SDK result serialization | Numeric bytes/dtype/shape/order, large integers, non-finite values, real SDK records, metadata and graph specs checked. |
| Authentication and authorization | Official config, environment token and named profile paths tested without live requests; every sensitive operation rejects missing/invalid confirmation before SDK access. |
| File handling and downloads | Traversal, symlinks, protected configuration, unsafe archives/HDF5 links, duplicate artifact names, SDK-added extensions, overwrite refusal and failure cleanup checked. |
| Job/result handling | All four SDK job result bundles, target-model downloads, dataset/profile output and concurrent polling checked with mocks. |
| Actual stdio transport | Official client subprocess calls pass; SDK Python/native stdout noise stays off the wire. |
| Legacy MCP | Raw initialize/tools/list/tools/call exchange passes for protocol 2025-11-25. |
| Current MCP | Official client negotiates 2026-07-28 and successfully invokes tools. |
| Packaging | Wheel and sdist built; wheel installed into a fresh venv; pip check and both installed entry points pass MCP discovery and confirmation rejection. |
| VS Code host | Actual VS Code extension-host API starts servers from workspace mcp.json, discovers 57 tools per instance, invokes a successful offline tool and receives authentication/authorization failures. |
| Claude Code host | Claude Code 2.1.314 started the server from an MCP config and returned live `get_devices` data. Confirmed on macOS with a read-only call. |

VS Code acceptance used temporary, isolated user-data/extensions directories and a
fresh test workspace. One server used the offline SDK fixture; the other used the
real entry point with a deliberately empty token. No Qualcomm upload, submission,
sharing change, or live service request occurred. The user's normal VS Code profile
was not modified. The extension-host test exited after completion.

[Recorded VS Code results](docs/vscode-acceptance.json) contain the returned tool
responses. This verifies the VS Code MCP host boundary, not a model-driven Copilot
conversation or successful live Qualcomm execution.

## Continuous integration

GitHub Actions passed on Ubuntu, macOS and Windows with Python 3.11, 3.12 and 3.13.
Each of the 9 jobs ran 253 passing tests with one optional live test skipped, plus the
package check. Lint and the secret scan also passed. These jobs use the mocked SDK.

## Live Qualcomm API

Verified on 2026-10-30 from macOS through the MCP tools, using a real Qualcomm
account, `Samsung Galaxy S24 (Family)`, and a tiny generated test model. 53 of the
57 tools were called live.

| Area | Result |
|---|---|
| Compile | ONNX upload, TFLite and QNN DLC compile jobs, polling, target-model download. |
| Inference | Real device run with an inline input. Output matched a local calculation to within 0.00045. Profile data and result bundle downloaded. |
| Quantize and link | HDF5 calibration upload, quantize job, QNN context binary link, default artifact location. |
| Legacy and compound jobs | `submit_profile_job`, `submit_compile_and_profile_jobs` and `submit_compile_and_link_jobs` succeeded. The SDK reports the first two as deprecated. |
| Sharing | Add, read back and remove on a model; `model_disable_sharing` with nothing shared. |
| Project and job changes | `create_project` and `job_set_name`. |
| Refusals | Overwrite and wrong job type were rejected with structured errors. |

Live testing found one bug that the mocked suite missed: the `get_sharing` tools
failed because the SDK returns a protobuf container, not a list. It is fixed and has
a regression test using a real protobuf object.

After the final security changes, the read-only live check, sharing reads and ID
lookups were repeated and passed, including with protobuf 5.29.6. The job flows above
ran with protobuf 6.31.1 and were not repeated.

## Not run

- Live `dataset_modify_sharing`, `dataset_disable_sharing`, `job_modify_sharing` and
  `job_disable_sharing`. They share an implementation path with the model tools.
- Loading the quantized ONNX, QNN DLC or QNN context binary outputs. Only the compiled
  TFLite model was executed on a device.
- Multi-graph links, multi-device submissions, and models larger than the test model.
- Live Qualcomm calls from Linux or Windows. Live testing ran only on macOS.

The connector pins its SDK versions. Python-only model objects are represented by
saved files/IDs; optional target-model downloads return a saved file path. Archives
stay zipped. Deprecated credential setters are replaced by startup configuration.
See [coverage and equivalents](docs/API_COVERAGE.md) for the exact API boundary.
