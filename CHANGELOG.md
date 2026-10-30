# Changelog

This project follows [Semantic Versioning](https://semver.org/). Breaking changes can
occur in `0.x` minor releases.

## 0.1.0 - 2026-10-30

### Added

- Initial beta: 57 MCP tools covering the `qai-hub` 0.57.0 Core API over stdio.
- Explicit `confirm=true` for uploads, submissions, project creation, renames, and
  sharing changes.
- Workspace-restricted file access, with guarded downloads that never overwrite.
- Sanitized, structured errors.
