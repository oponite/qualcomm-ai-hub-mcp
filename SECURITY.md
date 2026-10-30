# Security policy

## Supported versions

This project is in beta. Only the latest release receives security fixes.

## Reporting a vulnerability

Report privately through GitHub: open the repository's **Security** tab and choose
**Report a vulnerability**. Do not open a public issue. Do not include real API
tokens, private models, or private data in a report.

This is a volunteer project, so responses are best effort. Please allow time for a
fix before disclosing publicly.

Report flaws in Qualcomm AI Hub or the `qai-hub` SDK to Qualcomm. If such a flaw also
affects this server, report it here too.

## Scope

In scope:

- API token exposure through tool output, errors, logs, or outbound requests.
- Reading or writing files outside the configured workspace, or reaching protected
  credential paths.
- A sensitive operation running without `confirm=true`.
- Unsafe handling of server-provided filenames, archives, or HDF5 files.

Out of scope:

- A client or model setting `confirm=true` without human approval. The server cannot
  tell who approved a call, so approval must be enforced by the client.
- Actions by software already running as the same OS user. The workspace check is an
  application policy, not an OS sandbox.

## Safe use

Use a dedicated workspace that holds only the models and data the client may access.
Do not auto-approve sensitive tools. Keep tokens in the SDK configuration or the
client's environment, never in tool arguments.
