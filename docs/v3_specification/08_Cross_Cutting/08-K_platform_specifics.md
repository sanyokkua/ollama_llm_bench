# Platform Specifics

**Status:** Draft
**Owner:** architect
**Audience:** architect, coder, tester
**Last Updated:** 2026-05-22
**Cross-references:** 08_Cross_Cutting/08-M_app_lifecycle.md, 08_Cross_Cutting/08-A_architecture_principles.md, 10_Domain_and_Data/07_FILE_LAYOUT.md, 11_Services_and_Algorithms/01_SERVICE_INVENTORY.md

This document fixes the per-operating-system behaviour of the application. It runs on macOS, Windows, and Linux. At launch the platform detector establishes the current operating system and produces a platform profile that every later service consults for OS-specific paths, file-manager integration, theme detection, fonts, and window behaviour. The application presents a deliberately consistent surface on every platform: the menu bar is rendered inside the window everywhere, all feedback stays inside the window, and the only behaviours that differ are the ones a user genuinely expects to differ — paths and file-manager labels.

---

## Table of Contents

1. Supported platforms
2. The platform detector and the platform profile
3. Application data paths per operating system
4. Menu bar placement
5. File-manager integration
6. File picker conventions
7. Theme detection
8. Fonts
9. High-DPI and scaling
10. Window close behaviour
11. Notifications and system tray
12. Path display conventions
13. Platform-specific edge cases

---

## 1. Supported platforms

The application supports macOS, Windows, and Linux. The platform abstraction is reached through an **OS adapter** port (see `08-A_architecture_principles.md` section 4); the backend never branches on the operating system directly. Every OS-specific decision is resolved once at launch and cached in the platform profile.

## 2. The platform detector and the platform profile

The **platform detector** runs once during launch, at the step fixed in `08-M_app_lifecycle.md`. It classifies the operating system and produces an immutable **platform profile** cached in the composition root for the process lifetime.

The detector classifies the operating system into one of four kinds:

| Kind | Meaning |
|---|---|
| `MACOS` | An Apple macOS host. |
| `WINDOWS` | A Microsoft Windows host. |
| `LINUX` | A Linux host. |
| `UNKNOWN` | A host the detector cannot classify; the application falls back to Linux conventions and surfaces a warning. |

The platform profile carries, at minimum:

| Field | Meaning |
|---|---|
| `kind` | One of the four platform kinds above. |
| `os_version` | Human-readable OS version, for diagnostics and the About surface. |
| `app_data_root` | The resolved application data directory (section 3). |
| `home_path` | The current user's home directory. |
| `desktop_path` | The current user's Desktop directory. |
| `path_separator` | The native path separator. |
| `line_ending` | The native text line ending. |
| `case_sensitive_fs` | Whether the filesystem is case-sensitive. |
| `supports_native_dark_mode` | Whether the host exposes a dark-mode signal (section 7). |
| `file_manager_label` | The platform-correct "reveal in file manager" label (section 5). |

The platform profile is read-only after construction. Any later code that needs an OS-specific value reads it from the profile, never re-detects.

## 3. Application data paths per operating system

All application state lives under a single per-user application data directory, written `<app-data>` throughout the specification. The platform detector resolves it once and caches it in the profile. The directory name is `OllamaLLMBench` on every platform; only the parent location differs.

| Operating system | `<app-data>` path |
|---|---|
| macOS | `~/Library/Application Support/OllamaLLMBench/` |
| Linux | `$XDG_DATA_HOME/OllamaLLMBench/`, falling back to `~/.local/share/OllamaLLMBench/` when `XDG_DATA_HOME` is unset or empty. |
| Windows | `%LOCALAPPDATA%\OllamaLLMBench\`, typically `C:\Users\<user>\AppData\Local\OllamaLLMBench\`. |

The internal subtree below `<app-data>` — the SQLite database, the exports folder, the run and application log folders, the backups folder — is identical on every platform. Only the path separator differs. The full directory tree, rotation policy, and permissions are fixed in `10_Domain_and_Data/07_FILE_LAYOUT.md`.

The application creates `<app-data>` and its subtree on first launch (see `08-M_app_lifecycle.md`). Task files are user-owned documents kept anywhere on the filesystem; they are never stored under `<app-data>`.

## 4. Menu bar placement

The application uses a minimal in-window menu bar on every platform. There is no `File` / `Edit` / `View` / `Help` menu structure. The menu surface contains only the workspace switcher, a Settings entry, and an About entry.

| Platform | Default toolkit behaviour | Application contract |
|---|---|---|
| macOS | A global menu bar at the top of the screen | **Override** — render the menu bar inside the application window. |
| Windows | An in-window menu bar | In-window, matching the default. |
| Linux | An in-window menu bar; some desktop environments offer a global menu | In-window; the global-menu integration is not used. |

The menu bar is rendered inside the window on every platform so the application looks and behaves identically everywhere. Documentation screenshots and tutorials are then valid on every operating system.

## 5. File-manager integration

The OS adapter exposes a single "reveal in file manager" action. The behaviour and label are platform-specific:

| Platform | Action | Label |
|---|---|---|
| macOS | Open in Finder | "Reveal in Finder" |
| Windows | Open in File Explorer | "Show in Explorer" |
| Linux | Open in the default file manager | "Open in file manager" |

When the target path is a file, the file manager opens with that file selected, where the platform supports selection. When the target path is a folder, the folder is opened.

## 6. File picker conventions

The application uses the host's native file and folder pickers on every platform. Linux falls back to the toolkit picker where no native picker is available.

| Aspect | macOS | Windows | Linux |
|---|---|---|---|
| Save and Open pickers | Native | Native | Native, with toolkit fallback |
| Default folder for an export | Desktop | Desktop | Desktop |
| Default folder for opening a task file | The last folder used in the task editor, otherwise the user's documents folder | Same | Same |

## 7. Theme detection

The application supports a light theme, a dark theme, and a `system` setting that follows the host. Theme tokens are Python design-token objects (see `08-A_architecture_principles.md` section 13), applied programmatically.

| Platform | Host signal consulted |
|---|---|
| macOS | The system appearance (light / dark Aqua). |
| Windows | The personalisation app-mode setting (light / dark). |
| Linux | The desktop-environment colour-scheme preference. |

When the theme setting is `system`, the application subscribes to the host's colour-scheme change signal and re-applies the theme tokens at runtime, without a restart. When the host exposes no usable dark-mode signal, the application defaults to the light theme and the `system` choice resolves to light.

## 8. Fonts

Font selection is **platform-aware**. At startup the theme module reads the current platform from the Platform Detector (section 2) — a `PlatformKind` value — and applies the sans + mono chain prescribed for that platform from the table below. The theme module **never probes `QFontDatabase`** for per-family availability; platform-based branching on `PlatformKind` (or, equivalently, `sys.platform` / `QSysInfo`) is the only branching used, and Qt's font system then resolves the declared chain to the first available family. The full cross-platform chain is retained only as a defensive fallback when the Platform Detector cannot classify the host (`UNKNOWN`).

| Platform (`PlatformKind`) | Sans-serif body and UI text | Monospace text (logs, YAML, code) |
|---|---|---|
| `MACOS` | `"Helvetica Neue", "Arial", sans-serif` | `"Menlo", "Monaco", "Courier New", monospace` |
| `WINDOWS` | `"Segoe UI", "Arial", sans-serif` | `"Consolas", "Cascadia Mono", "Courier New", monospace` |
| `LINUX` | `"Cantarell", "Ubuntu", "Noto Sans", "DejaVu Sans", sans-serif` | `"DejaVu Sans Mono", "Ubuntu Mono", "Noto Sans Mono", "Liberation Mono", monospace` |
| `UNKNOWN` (defensive fallback) | `"Segoe UI", "Helvetica Neue", "Cantarell", "Ubuntu", "Noto Sans", "DejaVu Sans", "Arial", sans-serif` | `"Consolas", "Menlo", "Cascadia Mono", "DejaVu Sans Mono", "Ubuntu Mono", "Monaco", "Courier New", monospace` |

The full per-platform rationale (Segoe UI on Windows; Helvetica Neue on macOS; Cantarell/Ubuntu/Noto Sans/DejaVu Sans on Linux; Cascadia Mono not guaranteed on Windows 11; DejaVu Sans Mono first on Linux for ubiquity) and the list of avoided families are owned by `08-D_color_palette_and_typography.md` §7; this section restates the chains for platform-context lookup only.

The chosen font must satisfy the WCAG AA contrast requirement against the active theme tokens.

## 9. High-DPI and scaling

- The main window scales with the host's DPI and scaling factor on every platform.
- Every pixel dimension in the specification is a logical-pixel value at a 1.0× scale factor; the toolkit scales it for the host.
- The application re-layouts without a restart when the user moves the window to a monitor with a different scaling factor.
- Chart export image dimensions are physical-pixel values and are not scaled by the host DPI.

## 10. Window close behaviour

The application is single-window. Closing the main window quits the application on every platform.

| Platform | Native behaviour | Application contract |
|---|---|---|
| macOS | The system close control quits the application; the native dock-quit menu entry is also honoured | **Override** — clicking the window's close control quits the application. |
| Windows / Linux | The close button quits | The close button quits. |

Closing the window via the close button always runs the quit sequence fixed in `08-M_app_lifecycle.md`, including its confirmation prompts. The confirmations apply on every platform.

## 11. Notifications and system tray

- All feedback stays inside the application window. Transient feedback is an in-window status-bar toast; a blocking message is an in-window modal dialog. This is identical on every platform.
- The application uses **no** operating-system notification surface — no macOS Notification Center, no Windows notification, no Linux desktop notification.
- The application uses **no** system tray or menu-bar status item on any platform.

## 12. Path display conventions

When a path is shown to the user:

- The home directory is rendered as `~/...` on macOS and Linux, and as `%USERPROFILE%\...` on Windows.
- Path separators are rendered native — `/` on macOS and Linux, `\` on Windows.
- A path longer than 60 characters is truncated in the middle with an ellipsis, always preserving the final path segment.
- Paths are normalised to the platform's native form before being written to the data store; display formatting is applied only at render time.

## 13. Platform-specific edge cases

| ID | Concern | Handling |
|---|---|---|
| EC-K1 | The application data folder does not exist on first launch. | The folder and its subtree are created during launch (see `08-M_app_lifecycle.md`). Creation is recursive and idempotent. A permission failure aborts launch with an explanatory modal dialog naming the path. |
| EC-K2 | macOS: the application bundle was downloaded and is quarantined. | The application still resolves `<app-data>` and runs normally; quarantine does not affect the per-user data directory. |
| EC-K3 | Windows: a path under `<app-data>` exceeds the legacy 260-character limit. | The application uses the extended-length path form internally so long paths resolve. |
| EC-K4 | Linux: `XDG_DATA_HOME` is unset or empty. | `<app-data>` falls back to `~/.local/share/OllamaLLMBench/` (section 3). |
| EC-K5 | The host theme changes while the application is running and the theme setting is `system`. | The application re-applies the theme tokens live, without a restart (section 7). |
| EC-K6 | The user moves the window to a monitor with a different DPI or scaling factor. | The application re-layouts live, without a restart (section 9). |
| EC-K7 | The platform detector cannot classify the host. | The platform kind is `UNKNOWN`; the application falls back to Linux conventions, defaults to the light theme, and surfaces a status-bar warning. |
