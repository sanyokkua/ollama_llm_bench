# Platform Support

**Status:** Draft
**Owner:** architect
**Audience:** user, human
**Last Updated:** 2026-06-06
**Cross-references:** 13_Distribution_and_Release/02_INSTALLATION.md, 13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md, 16_Engineering_Standards/08_CICD_AND_PACKAGING.md, 08_Cross_Cutting/08-K_platform_specifics.md

This document states which operating systems Ollama LLM Bench supports, the minimum and tested versions of each, the supported CPU architectures, and the known platform-specific issues. Use it to confirm that a given machine can run the application before downloading an artifact.

---

## Table of Contents

1. [Supported Operating Systems](#1-supported-operating-systems)
2. [Platform Support Matrix](#2-platform-support-matrix)
3. [CPU Architectures](#3-cpu-architectures)
4. [Known Issues by Platform](#4-known-issues-by-platform)
5. [What "Tested" Means](#5-what-tested-means)
6. [Unsupported Platforms](#6-unsupported-platforms)

---

## 1. Supported Operating Systems

Ollama LLM Bench is a desktop application supported on three operating systems:

- **macOS** — distributed as a `.dmg` disk image.
- **Windows** — distributed as a portable `.zip` archive; there is no Windows installer.
- **Linux** — distributed as a single self-contained AppImage.

Each release publishes one artifact per operating system. The artifact format and the per-OS install steps are described in `13_Distribution_and_Release/02_INSTALLATION.md`.

## 2. Platform Support Matrix

The minimum version is the oldest release of the operating system on which the application is expected to run. The tested versions are the releases against which each build is verified.

| Operating system | Minimum version | Tested versions | CPU architectures | Artifact |
|---|---|---|---|---|
| macOS | macOS 11 (Big Sur) | macOS 13 (Ventura), macOS 14 (Sonoma), macOS 15 (Sequoia) | Apple silicon (**arm64 only**, DD-69) | `.dmg` (arm64) |
| Windows | Windows 10, build 1809 | Windows 10 (22H2), Windows 11 (23H2, 24H2) | x86-64 | portable `.zip` |
| Linux | A distribution with glibc 2.35 or newer | Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, Fedora 40 | x86-64 | AppImage |

Notes:

- **macOS.** The macOS bundle ships **arm64 only** (DD-69; Apple-silicon Macs). Its minimum system version is the **higher of macOS 11 and the bundled PySide6/Qt's own macOS minimum** (SPEC-096): a Qt upgrade that raises Qt's macOS floor automatically raises the app's, and the declared minimum in this matrix is updated to match the shipped Qt — the bundle never declares a minimum below what the bundled Qt supports. Intel Macs are not supported (Apple has dropped Intel from current macOS), so no Intel artifact is produced. It is verified on the tested versions listed above.
- **Windows.** Windows 10 build 1809 is the floor. The application runs on later Windows 10 builds and on Windows 11. There is no support for Windows versions earlier than build 1809.
- **Linux.** The Linux artifact is built on a runner with a glibc 2.35 baseline so it runs on that and any newer distribution. A distribution older than the glibc 2.35 baseline (for example, Ubuntu 20.04 LTS) is not supported. A FUSE runtime is required to run an AppImage; most desktop distributions provide it by default.

## 3. CPU Architectures

| Operating system | Supported architectures | Not supported |
|---|---|---|
| macOS | Apple silicon (arm64) | Intel (x86-64) — dropped (DD-69) |
| Windows | x86-64 | 32-bit x86; ARM Windows |
| Linux | x86-64 | 32-bit x86; ARM Linux |

The macOS release publishes a **single arm64 (Apple-silicon) `.dmg`** (DD-69). Intel (x86-64) macOS is **not supported**: Apple has ended Intel support in current macOS, so the project does not build or ship an Intel artifact and CI builds arm64 only. Windows and Linux are 64-bit x86 only.

## 4. Known Issues by Platform

| ID | Platform | Issue | Status |
|---|---|---|---|
| KI-01 | macOS | The application is unsigned and not notarized. On first launch, Gatekeeper reports it as from an unidentified developer. | Expected behaviour. Workaround in `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md`. |
| KI-02 | Windows | The application is unsigned. On first launch, SmartScreen reports it as an unrecognised application. | Expected behaviour. Workaround in `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md`. |
| KI-03 | Linux | The AppImage may not have the execute permission set after download. The application then does not launch on a double-click. | Expected behaviour. Workaround in `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md`. |
| KI-04 | Linux | A distribution without a FUSE runtime cannot mount an AppImage. The AppImage reports a FUSE error on launch. | Install the distribution's FUSE package, or run the AppImage with its `--appimage-extract-and-run` option. |

There are no known issues that prevent normal benchmarking on any supported platform.

## 5. What "Tested" Means

A tested version is one on which a release build is verified before publication: the application launches, creates its data directory, and runs a benchmark on that operating-system version. A version that is supported but not in the tested list — for example, macOS 12 — is expected to work because it sits between the minimum version and a tested version, but is not part of the per-release verification.

## 6. Unsupported Platforms
7. Provider Backend Expectations

The application does not run on, and is not built for:

- Mobile operating systems (iOS, iPadOS, Android).
- Web browsers; there is no hosted or web version.
- 32-bit operating systems.
- ARM-based Windows and ARM-based Linux.
- Linux distributions whose glibc is older than 2.35.
- Windows versions earlier than Windows 10 build 1809.
- macOS versions earlier than macOS 11.

A machine outside the support matrix in Section 2 cannot run Ollama LLM Bench.

---

## 7. Provider Backend Expectations

The application talks to every provider — local or cloud — through the OpenAI-compatible API dialect (plus the native Anthropic and Gemini SDK dialects for those two types). For embedding-based grading, the selected provider must serve the OpenAI-compatible `/v1/embeddings` route; the application deliberately speaks **no native backend routes** (such as Ollama's `/api/embed`).

| Backend | Expectation | If not met |
|---|---|---|
| Ollama | A 2024-08 or later release (v0.3.x+), which serves `/v1/embeddings` for embedding models (`nomic-embed-text`, `mxbai-embed-large`, `bge-m3`, …) and returns streamed token usage when the request sets `stream_options.include_usage` (SPEC-047). | Older Ollama exposes embeddings only natively and may not report usage — update Ollama; throughput then falls back to a flagged char/4 estimate. |
| llama.cpp server | Started with `--embedding` and serving an embedding-capable model. | A chat-only server answers `/v1/chat/completions` but 404s on `/v1/embeddings` — restart with `--embedding`. |
| LM Studio | A release exposing the OpenAI-compatible embeddings endpoint for a loaded embedding model. | Load an embedding model / update LM Studio. |
| OpenAI / Azure / Gemini | Embeddings served by the platform; no minimum beyond a valid key. | — |
| Anthropic | No first-party embedding endpoint — never selectable as the embedding provider. | Pick a different provider for embeddings. |

**Version numbers are guidance only.** The authoritative gate is the embedding **capability probe** (`11_Services_and_Algorithms/06_EMBEDDING_SERVICE.md` §6.6a): one user-initiated `embed("probe")` call that empirically verifies the route works for the selected `(provider, model)`. A selection that fails the probe is rejected with remediation guidance regardless of the backend's version, and a backend regression is caught the same way.
