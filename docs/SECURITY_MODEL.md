# Security model

This describes what the server enforces and what it leaves to you. To report a problem,
see [SECURITY.md](../SECURITY.md).

## Confirmation

Uploads, submissions, project creation, renames, and sharing changes require the literal
boolean `confirm=true`. A missing or false value is rejected before any SDK access.

The server cannot tell who set that value, so a model can set it. Your MCP client must
obtain human approval. No operation-wide permissions are silently enabled.

## Credentials

Keep tokens in the SDK configuration or the client's environment, never in tool
arguments. No tool sets credentials. Tool discovery works without credentials, and
operations return an authentication error when none are configured.

Errors are sanitized. Raw SDK messages are not forwarded, because they can contain
credentials.

Remote IDs are limited to letters, digits, `-`, and `_` before they reach the SDK.

## Workspace

Use a dedicated workspace that holds only the models and data the client may access. The
server rejects:

- Paths outside the workspace.
- The workspace root as a model directory.
- Protected configuration and credential paths, such as `.ssh`, `.aws`, and `.env`.
- Symlinks inside model directories.
- Unsafe archive entries.
- HDF5 external links, soft links, virtual datasets, and external storage.

This is an application file-access policy, not an OS sandbox. It does not defend against
other software running as the same user. Any other file in the workspace can still be
uploaded, so do not keep unrelated private files there.

## Downloads

Downloads go through per-call temporary staging and exclusive output creation:

- Existing files and folders are never overwritten, including when the SDK adds an
  extension.
- Server-provided filenames are checked before transfer.
- Archives stay zipped, and Python model objects are not deserialized.
- Result bundles use fixed `logs`, `model`, `dataset`, and `profile.json` locations.
- When an optional target-model filename is omitted, the file is saved under
  `workspace/artifacts/<unique-id>/`.

Downloaded files use your default file permissions.
