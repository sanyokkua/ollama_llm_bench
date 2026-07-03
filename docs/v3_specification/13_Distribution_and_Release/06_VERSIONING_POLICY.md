# Versioning Policy

**Status:** Draft
**Owner:** architect
**Audience:** user, human
**Last Updated:** 2026-06-06
**Cross-references:** 13_Distribution_and_Release/02_INSTALLATION.md, 13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md, 16_Engineering_Standards/08_CICD_AND_PACKAGING.md

This document defines how Ollama LLM Bench is versioned, what each part of a version number means, and the format of the changelog published with every release. The policy follows semantic versioning so that a version number alone tells a user what to expect from an upgrade.

---

## Table of Contents

1. [Version Number Format](#1-version-number-format)
2. [Major Versions](#2-major-versions)
3. [Minor Versions](#3-minor-versions)
4. [Patch Versions](#4-patch-versions)
5. [Pre-Release Versions](#5-pre-release-versions)
6. [Where the Version Is Shown](#6-where-the-version-is-shown)
7. [Version Tags and Releases](#7-version-tags-and-releases)
8. [The Changelog](#8-the-changelog)
9. [How Versioning Affects an Upgrade](#9-how-versioning-affects-an-upgrade)

---

## 1. Version Number Format

Every release has a version number of the form `MAJOR.MINOR.PATCH` — three numbers separated by dots, for example `2.4.1`. This is semantic versioning. Each part has a defined meaning:

| Part | Increments when | Signals to the user |
|---|---|---|
| `MAJOR` | A change is not backward-compatible and requires a fresh start. | The new version may not read the existing data; a fresh install may be needed. |
| `MINOR` | New, backward-compatible functionality is added. | New features; existing data and settings carry over unchanged. |
| `PATCH` | A backward-compatible bug fix is made, with no new functionality. | Fixes only; safe to apply; nothing changes for the user except the fix. |

When a part increments, every part to its right resets to zero. The first public release is `1.0.0`.

## 2. Major Versions

A major version increment — for example `2.x.x` to `3.0.0` — marks a release that is **not backward-compatible**. The most common reason is a change to the on-disk database schema.

The application performs **no data migrations and no data conversions — ever** (DD-53): no
`UPDATE`/backfill of existing rows, no value transformation, no row rewriting. Within one
major version, the schema may evolve through **purely structural additive steps** (Section
3); across major versions, nothing is carried forward. Each major version expects its own
schema lineage. If a major version is installed over a data directory created by a
different major version, the application detects the mismatch on launch and stops with an
explanatory dialog rather than altering the existing data (this behaviour is defined in
`08_Cross_Cutting/08-M_app_lifecycle.md`).

A major upgrade therefore requires a fresh start:

- Export any data to keep before upgrading.
- Move or remove the old data directory so the new major version creates a fresh one on its next launch (a first run, as described in `13_Distribution_and_Release/05_FIRST_RUN_EXPERIENCE.md`).

The changelog and release notes for a major version state explicitly that it is not backward-compatible and describe the fresh-start steps.

By design, the application provides **no automatic data-carry-over across a major upgrade**. This is a deliberate simplicity decision: the application stores no irreplaceable or sensitive data — benchmark results can be exported manually before upgrading (see `10_Domain_and_Data/05_EXPORT_FORMATS.md`) and any benchmark can simply be re-run on the new version. The schema-mismatch dialog therefore instructs the user to remove the old data directory and let the new version create a fresh one, and points to manual export as the way to retain prior results. A migration framework, an export-on-mismatch prompt, and an automatic import path are explicitly out of scope.

## 3. Minor Versions

A minor version increment — for example `2.3.x` to `2.4.0` — adds new functionality in a backward-compatible way. A minor upgrade is safe to apply over an existing installation:

- The existing data directory, runs, results, and settings are read by the new version unchanged.
- New settings introduced by the release take their default values (the `app_settings` key/value store grows by adding keys with built-in defaults; this is not a relational-schema change).
- No data is lost and no fresh start is needed.

**A minor version may evolve the schema through additive structural steps only (DD-53).**
Exactly three change kinds are legal within a minor version:

1. `ALTER TABLE … ADD COLUMN` — the new column nullable or carrying a `DEFAULT`; existing
   rows simply acquire `NULL`/the default — **their stored bytes are never touched**;
2. a new `CREATE TABLE` or `CREATE INDEX`;
3. new `app_settings` keys with defaults (as before).

Each step increments the integer `schema_version` by one and ships as one idempotent,
single-transaction structural statement; on startup an older database is brought forward by
applying the ordered steps (`10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md` §8). **No step is
ever a data migration or conversion** — no `UPDATE`, no backfill, no value transformation,
no row rewriting. Anything beyond additive — renaming, dropping, retyping a column or
table, or any change whose correctness would require touching existing rows — is a
**major** version with a fresh start. User run history therefore survives normal product
evolution.

Minor versions are the normal way backward-compatible new features reach users, within the limit above.

## 4. Patch Versions

A patch version increment — for example `2.4.0` to `2.4.1` — contains only backward-compatible bug fixes. A patch upgrade adds no features and changes no behaviour beyond correcting the fixed defects. It is always safe to apply over an existing installation and never requires a fresh start.

## 5. Pre-Release Versions

A release that is not yet considered stable may carry a pre-release suffix after the version number, separated by a hyphen — for example `2.5.0-rc.1` for a release candidate. A pre-release version sorts as older than the final release of the same `MAJOR.MINOR.PATCH` number. Pre-release versions are optional and are used only when a release needs a verification period before it is declared final.

## 6. Where the Version Is Shown

The installed version is shown in two places inside the application:

- The application's **About** surface displays the full version number.
- The main window **status bar** displays the version string.

The version is shown for user reference only. The application does not compare it against any remote value and has no in-app "Check for updates" affordance (DD-36); users check the project's GitHub Releases page out of band to learn whether a newer version exists.

## 7. Version Tags and Releases

Each release corresponds to a version tag in the project's source repository. Pushing a version tag triggers the release pipeline, which builds the per-operating-system artifacts and publishes a GitHub Release under the `sanyokkua` GitHub owner. The version in the tag, the version embedded in the built artifacts, and the version shown in the application's About surface are always the same value.

## 8. The Changelog

Every release is accompanied by a changelog entry. The project keeps a single `CHANGELOG.md` file in the source repository, with the newest release at the top. Each entry has a fixed structure:

```markdown
## [MAJOR.MINOR.PATCH] - YYYY-MM-DD

### Added
- New, backward-compatible functionality.

### Changed
- Changes to existing behaviour that remain backward-compatible.

### Fixed
- Bug fixes.

### Removed
- Functionality removed in this release.

### Breaking
- Backward-incompatible changes. Present only in a major release.
  States that a fresh start is required and how to perform it.
```

Rules for the changelog:

- Each entry is headed by the version number and the release date in `YYYY-MM-DD` form.
- A section heading (`Added`, `Changed`, `Fixed`, `Removed`, `Breaking`) is included only when it has content for that release.
- The **Breaking** section appears only in a major release and always describes the fresh-start steps.
- Entries are written for users: each line states the user-visible effect of the change, not the internal implementation.
- The same content is used as the release notes on the GitHub Release for that version.

## 9. How Versioning Affects an Upgrade

The version number alone tells a user what an upgrade involves:

| Upgrade | Example | Data and settings | Action needed |
|---|---|---|---|
| Patch | `2.4.0` → `2.4.1` | Carry over unchanged | None; apply directly |
| Minor | `2.3.1` → `2.4.0` | Carry over unchanged; new settings take defaults | None; apply directly |
| Major | `2.4.1` → `3.0.0` | May not be readable by the new version | Export data first, then start fresh with a new data directory |

For a patch or minor update, the user downloads the new artifact from the GitHub Releases page and replaces the existing installation files in place; no fresh start is needed (a minor that carries additive schema steps applies them automatically at first launch — structural only, never touching existing rows, DD-53). For a major update, the user reads the changelog's **Breaking** section before downloading and follows the fresh-start steps it describes.
