# Tool inputs and results

Each tool publishes its full schema and SDK documentation through MCP discovery. Public
SDK parameter names, defaults, nullability, enum names, and multi-device variants are
preserved. [API coverage](API_COVERAGE.md) lists every tool.

## JSON equivalents

| SDK value | MCP input |
|---|---|
| Uploaded model or dataset | `{"id":"existing-id"}` |
| Local model or dataset file | `{"path":"relative/or/absolute/path"}` |
| Device | `{"name":"device name","os":"","attributes":[]}` |
| Shape-only input spec | `{"image":[1,3,224,224]}` |
| Shape and dtype input spec | `{"image":[[1,3,224,224],"float32"]}` |
| Enum | Its SDK name, such as `"INT8"`, `"INFERENCE"`, or `"DEVICE_LOG"` |
| Project | Project ID string |

Qualcomm IDs may contain only letters, digits, `-`, and `_`.

`upload_model` accepts a local file or model directory. `upload_dataset` accepts an
HDF5 file or an inline dataset. Submission tools can use existing IDs. Saved model files
replace framework-specific Python objects, so uploading needs no PyTorch, ONNX, or Core
ML runtime.

## Dynamic input shapes

Compile jobs fail with a job status message when a model has dynamic input shapes. Set
fixed shapes with `input_specs`, such as `{"input":[1,3,224,224]}`.

## Inline datasets

Inline datasets keep feature order explicit:

```json
{
  "features": [
    {"name":"x","samples":[{"dtype":"int8","shape":[2],"base64":"AQI="}]}
  ]
}
```

Each sample contains C-order bytes, a numeric NumPy dtype, and its shape. This preserves
non-finite floating-point values, byte order, and large integers. Feature names must be
unique, and every feature must have the same number of samples.

Inline data is limited to 16 MiB of decoded tensor bytes. Use HDF5 files for larger
datasets. Downloaded inline tensors use the same encoding.

Model input and output specifications return ordered `graphs` records, so unnamed graphs
stay distinct from graphs named `"null"`.

## Example workflow

1. `get_devices` with `{}` to choose a device.
2. `upload_model` with `{"model":{"path":"model.onnx"},"confirm":true}`.
3. `submit_compile_job` with the returned model ID:
   `{"model":{"id":"MODEL_ID"},"device":{"name":"DEVICE_NAME"},"confirm":true}`.
4. `job_get_status` with `{"job_id":"JOB_ID"}` to poll.
5. `compilejob_get_target_model` with `{"job_id":"JOB_ID"}` to get the compiled model.
6. `model_download` with `{"model_id":"TARGET_MODEL_ID","filename":"outputs/model"}`.

## Jobs

Inference jobs profile by default. Omitting `inputs` profiles on generated input data.
Setting `profile=false` requires real inputs. Legacy profile and compile-and-profile
tools remain available as SDK compatibility operations.

Individual submissions return remote job references. Compound SDK helpers and result or
model retrieval can wait for upstream jobs. They run in worker threads, so other requests
stay responsive. SDK `retry` and `timeout` parameters keep their documented meanings. The
server adds no submission retries or task queue.

Cancelling a call does not cancel a remote job, and a started SDK call may finish in the
background. After a connection failure, check existing jobs before resubmitting.

Set a `timeout` on long waits. A client that stops waiting without sending an MCP
cancellation keeps a worker thread busy until the SDK call returns, and 40 busy threads
block further tool calls.

## Results and errors

Successful calls return `{"result":...}` in structured content and JSON text.

Operational errors set MCP `isError=true` and return a sanitized record:

```json
{"error":{"code":"AUTHENTICATION","message":"...","retryable":false}}
```

Schema validation errors use the MCP SDK's standard error response.

A failed job is reported in its returned status. Retrieving that status is a successful
API call.
