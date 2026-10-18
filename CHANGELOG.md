# Changelog

All notable changes to Gateway7 are recorded here.
Versions will follow Semantic Versioning when a release is published.

## [Unreleased]

### Added

- Python text-chat gateway with server-held provider credentials, strict input validation and safe error responses.
- Trusted modules installed by restart, separate ordered request and response hooks, and fail-closed execution.
- Phone masking over conversation history and a one-file sample company plugin.
- Deterministic HTTP upstream and repeatable customer demonstration with locked setup instructions.
- Definition of Done and contribution guide with task/review standards and setup navigation.
- Locked documentation build with local Mermaid assets, pull-request validation and a main-only GitHub Pages workflow; first deployment pending.

### Changed

- Python checks also run on Windows.

### Fixed

- The one-command demonstration's plugin-installation check now passes on Windows, where it compared backslash paths with POSIX paths.

No version has been released by this contribution.
