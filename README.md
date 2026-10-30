# Qualcomm AI Hub MCP

Compile, profile, and run AI models on real phones and other devices hosted by
Qualcomm AI Hub, directly from your MCP client.

**Unofficial and in beta.** This independent project is not affiliated with, endorsed
by, or supported by Qualcomm.

## What you can do

Ask your assistant something like this:

> Upload `model.onnx`, compile it for the Samsung Galaxy S24, run it on the device,
> and tell me how long inference took.

The server covers the Qualcomm AI Hub Core API with 57 tools. You can:

- Browse available devices, chipsets, and frameworks.
- Upload models and datasets from a local workspace.
- Compile, quantize, and link models.
- Run inference on hosted devices and read performance profiles.
- Download compiled models, outputs, and logs.

Here is a real run through this server, using a tiny one-layer test model:

```text
Device     Samsung Galaxy S24 (Family), Android 14
Compile    ONNX to TFLite: SUCCESS
Inference  SUCCESS, output shape [1, 1, 32, 32]
Profile    Downloaded with the output data and device log
```

## Quick start

You need [uv](https://docs.astral.sh/uv/) and a
[Qualcomm AI Hub account](https://workbench.aihub.qualcomm.com).

1. Copy your API token from your Qualcomm AI Hub account settings, then save it:

   ```sh
   uvx --from qai-hub==0.57.0 qai-hub configure --api_token YOUR_TOKEN
   ```

   This stores the token in `~/.qai_hub/client.ini`. On macOS and Linux, restrict
   that file with `chmod 600 ~/.qai_hub/client.ini`.

2. Create a folder that holds only the models and data your assistant may use.

3. Add the server to your client. For Claude Code:

   ```sh
   claude mcp add qualcomm -- uvx --from git+https://github.com/oponite/qualcomm-ai-hub-mcp qualcomm-ai-hub-mcp --workspace /absolute/path/to/folder
   ```

   See [Other clients](#other-clients) for VS Code and others.

4. Ask your assistant to list the available Qualcomm devices.

Always set `--workspace`. Without it, the server uses the folder it started in.

## Before you use it

**Keep human approval on.** Tools that change your account or start jobs require
`confirm=true`, but a model can set that value itself. Require approval in your client
for these tools, and do not auto-approve them:

- `submit_*` and `upload_*`
- `create_project` and `job_set_name`
- `*_modify_sharing` and `*_disable_sharing`

**Your models and data leave your machine.** Uploads and submissions send them to
Qualcomm, where they are stored and processed under your account. Review Qualcomm's
terms and pricing first. This server does not track usage or cost.

**Your credentials stay out of tool calls.** There is no tool for setting a token. The
server adds no telemetry of its own, and its remote calls go through the official
Qualcomm SDK, which has its own behavior and terms.

## Other clients

The server runs locally over stdio. It is not an HTTP endpoint. If your client cannot
find `uvx`, use its absolute path. This project is not on PyPI yet, so these commands
install it from GitHub.

**VS Code:** add this to `.vscode/mcp.json`:

```json
{
  "servers": {
    "qualcomm": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/oponite/qualcomm-ai-hub-mcp",
        "qualcomm-ai-hub-mcp", "--workspace", "/absolute/path/to/folder"
      ]
    }
  }
}
```

**Clients that use `mcpServers`:**

```json
{
  "mcpServers": {
    "qualcomm": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/oponite/qualcomm-ai-hub-mcp",
        "qualcomm-ai-hub-mcp", "--workspace", "/absolute/path/to/folder"
      ]
    }
  }
}
```

### Server options

| Option | Meaning |
|---|---|
| `--workspace PATH` | Existing folder for model files, data, and downloads. |
| `--profile NAME` | Use `~/.qai_hub/NAME.ini`. |
| `--version` | Print the installed version. |

### Other ways to authenticate

- Set `QAIHUB_CLIENT_INI` to the path of a configuration file.
- Set `QAI_HUB_API_TOKEN` in the client's environment. This cannot be combined with
  `--profile`.

## Limits

- Each release targets one `qai-hub` version, currently 0.57.0.
- There is no delete tool. Remove uploads, jobs, and projects with Qualcomm's own tools.
- Cancelling a call does not cancel the remote job. After a connection failure, check
  existing jobs before resubmitting.
- Set a `timeout` on long waits.
- Inline data is limited to 16 MiB. Use HDF5 files for larger datasets.
- `submit_profile_job` and `submit_compile_and_profile_jobs` are deprecated by the SDK.
  Use `submit_inference_job`.

## Documentation

- [Tool inputs and results](https://github.com/oponite/qualcomm-ai-hub-mcp/blob/main/docs/TOOL_INPUTS.md)
- [Security model](https://github.com/oponite/qualcomm-ai-hub-mcp/blob/main/docs/SECURITY_MODEL.md)
- [Full tool list](https://github.com/oponite/qualcomm-ai-hub-mcp/blob/main/docs/API_COVERAGE.md)
- [What has been verified](https://github.com/oponite/qualcomm-ai-hub-mcp/blob/main/ACCEPTANCE.md)
- [Changelog](https://github.com/oponite/qualcomm-ai-hub-mcp/blob/main/CHANGELOG.md)
- [Contributing](https://github.com/oponite/qualcomm-ai-hub-mcp/blob/main/CONTRIBUTING.md)
- [Report a security issue](https://github.com/oponite/qualcomm-ai-hub-mcp/blob/main/SECURITY.md)

## License

Licensed under the
[Apache License 2.0](https://github.com/oponite/qualcomm-ai-hub-mcp/blob/main/LICENSE).
This covers this project only. The Qualcomm AI Hub service and `qai-hub` SDK have their
own terms. Qualcomm and Qualcomm AI Hub are trademarks of Qualcomm Incorporated or its
subsidiaries.
