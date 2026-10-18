# Changelog

All notable changes to Gateway7 are recorded here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) with tags prefixed by `v`.

## [Unreleased]

### Added

- Project plan for SPRINT-03 to SPRINT-09, with the first release and weekly progress monitoring.
- Week 3 customer meeting report and decisions reconstructed from the privately supplied transcript, with unresolved story verdicts and Week 4 follow-ups.

### Changed

- Week 3 report links the published documentation, release, merged work and current checks, and identifies the remaining validation and scheduling gaps.
- Assignment 3 follow-up clarifies setup, release and submission steps, plugin timeout limits, and the remaining evidence needed to assess the success threshold.

## [0.1.0] - 2026-10-18

### Added

- Python text-chat gateway with server-held provider credentials, strict input validation and safe error responses.
- Trusted modules installed by restart, separate ordered request and response hooks, and fail-closed execution.
- Phone masking over conversation history and a one-file sample company plugin.
- Deterministic HTTP upstream and repeatable customer demonstration with locked setup instructions.
- Windows PowerShell commands for running the two services manually.
- Definition of Done and contribution guide with task/review standards and setup navigation.
- Locked documentation build with local Mermaid assets, pull-request validation and a main-only GitHub Pages workflow; first deployment pending.

### Fixed

- The one-command demonstration's plugin-installation check now passes on Windows, where it compared backslash paths with POSIX paths.
- The documented test command no longer errors on Windows, where one case's generated test ID exceeded the environment-variable size limit.

[Unreleased]: https://github.com/iteam7/gateway7/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/iteam7/gateway7/releases/tag/v0.1.0
