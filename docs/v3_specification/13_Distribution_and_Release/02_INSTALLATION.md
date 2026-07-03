# Installation

**Status:** Draft
**Owner:** architect
**Audience:** user, human
**Last Updated:** 2026-05-22
**Cross-references:** 13_Distribution_and_Release/01_PLATFORM_SUPPORT.md, 13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md, 13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md, 13_Distribution_and_Release/08_UNINSTALL.md, 16_Engineering_Standards/08_CICD_AND_PACKAGING.md

This document gives the per-operating-system steps to install and launch Ollama LLM Bench. Before installing, confirm the machine meets the support matrix in `13_Distribution_and_Release/01_PLATFORM_SUPPORT.md`.

> **Numbering note (SPEC-084).** There is intentionally no `03_*` document in this folder; the series runs `01`, `02`, `04`, `05`, `06`, `07`, `08`. The `03` slot is a retired/never-used number and no document is missing — installation-medium content that an `03` might once have held is covered by `02_INSTALLATION.md` and `04_UNSIGNED_DISTRIBUTION.md`. No cross-reference points to a `13_Distribution_and_Release/03_*` file.

---

## Table of Contents

1. [Where to Download](#1-where-to-download)
2. [Verifying the Download](#2-verifying-the-download)
3. [Install on macOS](#3-install-on-macos)
4. [Install on Windows](#4-install-on-windows)
5. [Install on Linux](#5-install-on-linux)
6. [First Launch and the Security Prompt](#6-first-launch-and-the-security-prompt)
7. [Where Application Data Is Stored](#7-where-application-data-is-stored)
8. [Updating](#8-updating)

---

## 1. Where to Download

Every release is published on the project's GitHub Releases page, under the `sanyokkua` GitHub owner. Each release lists one artifact per operating system and a `SHA256SUMS` checksum file:

| Operating system | Artifact |
|---|---|
| macOS | `OllamaLLMBench-<version>-macos.dmg` |
| Windows | `OllamaLLMBench-<version>-windows-x86_64.zip` |
| Linux | `OllamaLLMBench-<version>-linux-x86_64.AppImage` |

Download only the artifact that matches the operating system and CPU architecture in `13_Distribution_and_Release/01_PLATFORM_SUPPORT.md`. Download the `SHA256SUMS` file from the same release.

## 2. Verifying the Download

Each release publishes a `SHA256SUMS` file listing the SHA256 checksum of every artifact. Verifying a download confirms it arrived intact and was not tampered with.

Compute the checksum of the downloaded file and compare it to the line for that file in `SHA256SUMS`:

| Operating system | Command |
|---|---|
| macOS | `shasum -a 256 OllamaLLMBench-<version>-macos.dmg` |
| Windows | `certutil -hashfile OllamaLLMBench-<version>-windows-x86_64.zip SHA256` |
| Linux | `sha256sum OllamaLLMBench-<version>-linux-x86_64.AppImage` |

The printed value must match the value in `SHA256SUMS` exactly. If it does not match, delete the file and download it again. Do not run an artifact whose checksum does not match.

## 3. Install on macOS

1. Download `OllamaLLMBench-<version>-macos.dmg`.
2. Optionally verify the download (Section 2).
3. Double-click the `.dmg` file. A window opens showing the `Ollama LLM Bench` application and a shortcut to the `Applications` folder.
4. Drag `Ollama LLM Bench` onto the `Applications` folder. This copies the application to `/Applications`.
5. Eject the mounted disk image: drag it to the Trash, or use the eject control in Finder.
6. Open the application from the `Applications` folder.

The application is unsigned and not notarized. The first launch shows a Gatekeeper security prompt; the steps to allow it are in Section 6 and in `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md`.

## 4. Install on Windows

The Windows build is a portable application. There is no installer.

1. Download `OllamaLLMBench-<version>-windows-x86_64.zip`.
2. Optionally verify the download (Section 2).
3. Move the `.zip` file to a writable folder where the application will live — for example, `C:\Users\<user>\Apps\`. Do not use a read-only or system-protected folder.
4. Right-click the `.zip` file and choose **Extract All**. Extract it into the chosen folder.
5. Open the extracted folder. It contains `OllamaLLMBench.exe` and its supporting files.
6. Double-click `OllamaLLMBench.exe` to launch the application.

The application runs in place from the extracted folder. Do not run it from inside the `.zip` archive itself; extract it first so that Windows can launch the executable normally.

To make the application easier to launch, right-click `OllamaLLMBench.exe` and choose **Pin to Start** or **Create shortcut**.

The application is unsigned. The first launch shows a SmartScreen security prompt; the steps to allow it are in Section 6 and in `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md`.

## 5. Install on Linux

The Linux build is an AppImage, a single self-contained file that runs without installation.

1. Download `OllamaLLMBench-<version>-linux-x86_64.AppImage`.
2. Optionally verify the download (Section 2).
3. Move the AppImage to a folder of your choosing — for example, `~/Applications/`.
4. Mark the file executable. From a file manager, open the file's properties and enable the "allow executing file as program" permission. From a terminal:
   `chmod +x ~/Applications/OllamaLLMBench-<version>-linux-x86_64.AppImage`
5. Launch the application by double-clicking the AppImage, or from a terminal by running the file's path directly.

The AppImage requires a FUSE runtime, which most desktop distributions provide by default. If the AppImage reports a FUSE error, install the distribution's FUSE package or run the AppImage with the `--appimage-extract-and-run` option (see `13_Distribution_and_Release/01_PLATFORM_SUPPORT.md`, issue KI-04).

The execute-permission step is the only setup needed on Linux; the steps are also covered in `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md`.

## 6. First Launch and the Security Prompt

The application binaries are unsigned. On the first launch the operating system shows a security prompt:

- **macOS** — Gatekeeper reports the application as from an unidentified developer.
- **Windows** — SmartScreen reports the application as unrecognised.
- **Linux** — there is no security prompt; only the execute permission of Section 5 is needed.

These prompts are expected. The exact steps to allow the application to run on each operating system are in `13_Distribution_and_Release/04_UNSIGNED_DISTRIBUTION.md`. After the application is allowed once, the operating system remembers the choice and does not prompt again.

On the first successful launch the application silently creates its data directory and a set of default settings. There is no setup wizard; the main window opens directly. This is described in `13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md`.

## 7. Where Application Data Is Stored

The application stores all of its data — runs, results, settings, logs, backups — under a single per-user data directory:

| Operating system | Application data directory |
|---|---|
| macOS | `~/Library/Application Support/OllamaLLMBench/` |
| Windows | `%LOCALAPPDATA%\OllamaLLMBench\` |
| Linux | `$XDG_DATA_HOME/OllamaLLMBench/`, falling back to `~/.local/share/OllamaLLMBench/` |

The data directory is separate from the application itself. Replacing the application does not affect it. Removing the application does not remove it; see `13_Distribution_and_Release/08_UNINSTALL.md` for how to remove the data directory deliberately.

## 8. Updating

The application has no built-in update mechanism (DD-36). To update, visit the project's GitHub Releases page, download the new artifact for your platform, replace the existing installation files with the new ones, and relaunch the application. The application's data directory (database, logs, settings) lives in the user home as listed in Section 7 and is not touched by replacing the installation files.
