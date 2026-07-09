# ADR-0003 — Use the uv build backend and distribute unsigned, checksum-verified binaries

**Status:** accepted
**Date:** 2026-07-09
**Deciders:** project owner, architect
**Supersedes:** —
**Relates to:** ADR-P-003, decisions D-028, D-029

## Context and problem statement

The application is a solo-maintained, cross-platform desktop tool distributed through public
releases. Two distribution-shaping choices were delegated: which Python build backend to use,
and how to distribute on Windows. The project already standardizes on the uv package manager
and an exact pinned interpreter, and the application is distributed unsigned — macOS builds are
ad-hoc signed only, with no paid certificates. Which build backend and Windows distribution form
fit a zero-paid-tooling, reproducible-build, single-maintainer workflow, and how should release
integrity be established without paid signing?

## Decision drivers

- Zero recurring paid-tooling cost for a solo maintainer.
- A build toolchain unified with the already-adopted `uv` package manager.
- No administrative-rights requirement for end users on any platform.
- Some form of download-integrity verification without paid code-signing.

## Considered options

- Option A — A conventional general-purpose build backend (e.g. `hatchling`/`setuptools`) plus a
  Windows installer and paid code-signing certificates.
- Option B — `uv_build` as the build backend; Windows as a portable `.zip`; unsigned binaries
  with a published `SHA256SUMS` checksum file.
- Option C — `uv_build` as the build backend; a self-contained single-file Windows executable.

## Decision outcome

Chosen option: **Option B**, because it keeps the toolchain unified inside `uv`, requires no
paid tooling, needs no administrative rights to run, and gives users an integrity check without
any signing infrastructure. Use `uv_build`, uv's native build backend, as the Python build
backend for the project. Distribute the Windows build as a portable `.zip` archive only — no
installer is provided. Continue to distribute all binaries unsigned: macOS builds are ad-hoc
signed only, with no Developer ID and no notarization, and Windows binaries carry no
Authenticode certificate. Release integrity is established by publishing an unsigned
`SHA256SUMS` checksum file alongside the artifacts on each GitHub Release rather than by OS
code-signing or any cryptographic signing. The checksums provide integrity (corruption
detection), not authenticity; the trust anchor is the HTTPS GitHub Releases page itself
(D-R-11b). There is no GPG, Ed25519, or Sigstore signing of checksums or artifacts. A user who
wants stronger assurance can build from source. The application has no auto-update mechanism
(DD-36); updates are manual user actions performed against the GitHub Releases page.

### Consequences

- Positive — `uv_build` keeps the build backend within the same tool that already manages
  packaging and the locked dependency set, simplifying the toolchain for a solo maintainer. A
  portable Windows `.zip` requires no installer authoring or maintenance and lets users run the
  application without administrative rights. Avoiding paid code-signing certificates keeps
  distribution cost at zero. The published `SHA256SUMS` file lets a user verify a download is
  intact (corruption detection) without OS code-signing, at zero tooling and key-management
  cost.
- Negative — Unsigned binaries trigger first-run operating-system warnings and possible
  antivirus false positives; this is tracked as a distribution risk and mitigated with clear
  unblock documentation. The unsigned checksums are not an authenticity guarantee: an actor who
  controlled the GitHub Releases page could replace artifacts and checksums together. This
  residual risk is accepted (D-R-11b); cryptographic signing is an explicitly deferred option,
  re-evaluated only at a sustained user-base milestone. A portable `.zip` offers no start-menu
  integration, no uninstaller, and no file-association registration on Windows.
- Neutral — `uv_build` is a comparatively young build backend; the project accepts tracking its
  maturity and treating backend upgrades as deliberate changes.

## Pros and cons of the options

### Option A — Conventional build backend, Windows installer, paid signing

- Good — Familiar toolchain; signed binaries avoid first-run OS warnings; an installer gives
  start-menu integration and clean uninstall.
- Bad — Adds a second packaging tool alongside uv; recurring paid-certificate cost disproportionate
  to the current user base; installer authoring and maintenance burden for little benefit on a
  portable single-folder application.

### Option B — `uv_build`, portable `.zip`, unsigned + SHA256SUMS

- Good — Unified toolchain inside `uv`; zero tooling cost; no admin rights needed; integrity
  check via checksums.
- Bad — First-run OS security warnings; checksums give no authenticity guarantee; no Windows
  start-menu integration or uninstaller.

### Option C — `uv_build`, self-contained single-file Windows executable

- Good — A single file is simple to distribute and explain to users.
- Bad — Single-file packaging incurs slow startup and temporary-extraction behaviour on every
  launch; a portable folder distribution is preferred.

## Links

- Related ADRs: —
- Spec clauses: `16_Engineering_Standards/02_TOOLCHAIN.md`,
  `16_Engineering_Standards/08_CICD_AND_PACKAGING.md`, `13_Distribution_and_Release/`,
  `15_Risks_and_Open_Questions/03_PROPOSED_ADRS.md#adr-p-003--uv-build-backend-and-portable-unsigned-distribution`
- Stories: —
