# Uninstall

**Status:** Draft
**Owner:** architect
**Audience:** user, human
**Last Updated:** 2026-06-06
**Cross-references:** 13_Distribution_and_Release/02_INSTALLATION.md, 13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md, 13_Distribution_and_Release/07_CRASH_REPORTING.md, 10_Domain_and_Data/07_FILE_LAYOUT.md

This document describes how to remove Ollama LLM Bench cleanly from macOS, Windows, and Linux. A complete uninstall has two parts: removing the application itself and, optionally, removing the application data directory that holds all runs, results, settings, logs, and backups.

---

## Table of Contents

1. [What a Complete Uninstall Removes](#1-what-a-complete-uninstall-removes)
2. [Back Up Before You Uninstall](#2-back-up-before-you-uninstall)
3. [Uninstall on macOS](#3-uninstall-on-macos)
4. [Uninstall on Windows](#4-uninstall-on-windows)
5. [Uninstall on Linux](#5-uninstall-on-linux)
6. [The Application Data Directory](#6-the-application-data-directory)
7. [What Is Left Behind](#7-what-is-left-behind)

---

## 1. What a Complete Uninstall Removes

Ollama LLM Bench writes to exactly two places on disk:

1. **The application itself** — the `.app` bundle, the portable folder, or the AppImage file, wherever the user placed it.
2. **The application data directory** — `OllamaLLMBench`, which holds the database (runs and results), settings, logs, and automatic settings backups.

A complete uninstall removes both. Removing the application but keeping the data directory is also valid: the data directory is then reused if the application is installed again. Task files the user created are separate user-owned documents and are never removed by an uninstall.

## 2. Back Up Before You Uninstall

Removing the application data directory permanently deletes every benchmark run, result, and the application settings. Before deleting it:

- To keep run data, copy the data directory (Section 6) to another location first.
- To keep the settings, export them from the Settings dialog before uninstalling, or copy a `settings_<timestamp>.yaml` file from the `backups/` folder inside the data directory.

There is no undo once the data directory is deleted.

## 3. Uninstall on macOS

1. Quit Ollama LLM Bench.
2. Open the `Applications` folder.
3. Move `Ollama LLM Bench` to the Trash.
4. To remove the application data as well, delete the data directory:
   `~/Library/Application Support/OllamaLLMBench/`
   In Finder, use **Go → Go to Folder** and enter `~/Library/Application Support/`, then move the `OllamaLLMBench` folder to the Trash.
5. Empty the Trash.

No installer database or system-level entries need to be cleaned up; the macOS build does not write outside the two locations above.

## 4. Uninstall on Windows

The Windows build is a portable application. There is no installer and therefore no "Add or remove programs" entry.

1. Quit Ollama LLM Bench.
2. Delete the folder the portable `.zip` was extracted into — the folder that contains `OllamaLLMBench.exe`.
3. Delete any shortcuts that were created manually (Start menu pin, desktop shortcut).
4. To remove the application data as well, delete the data directory:
   `%LOCALAPPDATA%\OllamaLLMBench\`
   In File Explorer, enter `%LOCALAPPDATA%` in the address bar, then delete the `OllamaLLMBench` folder.

Because the application is portable, no registry cleanup is required.

## 5. Uninstall on Linux

1. Quit Ollama LLM Bench.
2. Delete the AppImage file from wherever it was placed (for example, `~/Applications/`).
3. Delete any desktop launcher entry created manually for the AppImage.
4. To remove the application data as well, delete the data directory:
   - `$XDG_DATA_HOME/OllamaLLMBench/` if `XDG_DATA_HOME` is set, or
   - `~/.local/share/OllamaLLMBench/` otherwise.

   From a terminal: `rm -rf ~/.local/share/OllamaLLMBench/` (adjust the path if `XDG_DATA_HOME` is set).

## 6. The Application Data Directory

The data directory is the same name, `OllamaLLMBench`, on every operating system; only its parent location differs:

| Operating system | Application data directory |
|---|---|
| macOS | `~/Library/Application Support/OllamaLLMBench/` |
| Windows | `%LOCALAPPDATA%\OllamaLLMBench\`, typically `C:\Users\<user>\AppData\Local\OllamaLLMBench\` |
| Linux | `$XDG_DATA_HOME/OllamaLLMBench/`, falling back to `~/.local/share/OllamaLLMBench/` |

This directory contains the SQLite database and its write-ahead-log companion files, the `logs/` folder, the `exports/` folder, the `backups/` folder, and the `temp/` folder. Its full layout is specified in `10_Domain_and_Data/07_FILE_LAYOUT.md`. Deleting this directory removes all application data.

If the data directory is left in place after the application is removed, a later reinstall reuses it: the existing runs, results, and settings reappear. If it is deleted, a later reinstall is treated as a fresh first run and the directory is recreated with defaults (see `13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md`).

## 7. What Is Left Behind

After removing the application and the data directory, nothing the application created remains, except items the user controls directly **and OS-level launch-approval state outside the application's control** (SPEC-102) — for example the macOS Gatekeeper allow-decision and the Windows SmartScreen reputation recorded for the binary. These are managed by the operating system, are not created or removable by this application, and are harmless; they are noted here only for completeness:

- **Task files** the user created or edited. These are user-owned documents stored wherever the user saved them, never inside the data directory, and are never removed by an uninstall.
- **Exported files** the user saved to a location of their own choosing outside the data directory.
- **Copies** of the data directory or settings files the user deliberately moved elsewhere before uninstalling (Section 2).

The application creates no system services, no scheduled tasks, no registry entries, and no files outside the two locations described in this document.
