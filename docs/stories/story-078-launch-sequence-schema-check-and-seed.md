---
id: STORY-078
title: Run the launch glue — app-data directory, schema check, seeding, and the abort modals
status: ready
spec_clauses:
  - 08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations
  - 08_Cross_Cutting/08-M_app_lifecycle.md#3-the-schema-check-and-the-no-migration-rule
  - 08_Cross_Cutting/08-M_app_lifecycle.md#4-default-seeding
  - 08_Cross_Cutting/08-K_platform_specifics.md#3-application-data-paths-per-operating-system
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#8-schema-versioning--additive-structural-steps-no-data-migration-dd-53
  - 10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#10-seed-data
  - 08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-1
  - 08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-2
  - 08_Cross_Cutting/08-M_app_lifecycle.md#EC-M-3
modules:
  - backend/infra/
  - backend/persistence/app_settings/
  - backend/persistence/providers/
acceptance_criteria:
  - STORY-078-AC-1
  - STORY-078-AC-2
  - STORY-078-AC-3
  - STORY-078-AC-4
  - STORY-078-AC-5
edge_cases:
  - EC-M-1
  - EC-M-2
  - EC-M-3
depends_on:
  - STORY-077
  - STORY-079
adrs:
  - ADR-0010
owner: coder
estimate: M
---

# STORY-078 — Run the launch glue — app-data directory, schema check, seeding, and the abort modals

## Goal

Bring the application from a fresh or existing profile to a usable, internally consistent state at
startup. `build_app` ensures the application-data directory exists, checks the persisted schema
version against the version the running build expects, seeds the default providers when the catalog
is empty, and aborts with a clear modal — never touching the database — when the directory cannot be
created, the schema does not match, or the file is unreadable. There is no data migration, ever: an
incompatible database is a hard startup error.

## In scope

- The launch-glue prelude of `build_app` (ADR-0010), in this order, before the object graph is
  wired: ensure `<app-data>` and its subtree exist (recursive, idempotent, with the
  permission-failure abort below), then run the schema-version check against the already-open write
  connection, then seed defaults.
- The hardened app-data-directory creation, which supersedes the plain parent-directory `mkdir`
  STORY-077 performs purely to let the database open succeed. This story covers the whole subtree
  and adds the permission-failure abort modal.
- The three abort-with-modal paths: an app-data permission failure, a schema-version mismatch, and a
  present-but-unreadable/corrupt database each show an explanatory modal and exit without altering
  the database.
- The corrupt/unreadable-database abort path specifically **wraps STORY-077's
  `open_write_connection` call**, catching the `PersistenceError` that helper already raises for a
  file that is not a valid SQLite database, and turning it into the AC-3 modal. STORY-077 owns the
  open; this story owns the failure surface around it.
- Idempotent default seeding: seed the bundled default providers only when the provider catalog is
  empty; leave a non-empty catalog untouched; leave `app_settings` empty so every setting resolves to
  its built-in default.

## Out of scope

- Constructing the `QApplication`, installing the exception hooks — owned by STORY-076.
- The object-graph wiring, `AppHandle`, and the export bridge — owned by STORY-077.
- **Opening the single database write connection and applying its `03_PERSISTENCE_SCHEMA.md` §2
  pragmas — owned by STORY-077.** That pair is one indivisible step (§2 requires the pragmas
  "immediately after opening, before any statement runs"), and the existing `open_write_connection`
  helper already performs both atomically. This story runs its schema check *on the connection
  STORY-077 opened*; it never opens a connection and never calls `apply_pragmas` itself.
- Acquiring the single-instance advisory lock (which runs between the app-data step and the DB open) —
  the lock helper is owned by STORY-079; this story calls it.
- The crash-recovery result sweep and the quit sequence — owned by STORY-080.
- The schema DDL, the version-check primitive, and the seed rows themselves — already
  delivered by STORY-008 and STORY-012; this story orchestrates and surfaces them at launch.
- Any change to `ui/common_dialogs/`. The three abort modals reuse its existing `make_error_dialog`
  factory unchanged, so it is not a `modules:` entry — see Design constraints.

## Spec inputs

- `08_Cross_Cutting/08-M_app_lifecycle.md#2-launch--order-of-operations` — the ordered steps: ensure
  app-data dir (4), open DB + pragmas + schema check (5), seed defaults (6); a failure in these steps
  aborts launch with an explanatory modal.
- `08_Cross_Cutting/08-M_app_lifecycle.md#3-the-schema-check-and-the-no-migration-rule` — a schema
  match continues to seeding; a mismatch aborts immediately with the hard schema-mismatch modal naming
  the database path, the database is never altered, and the process exits.
- `08_Cross_Cutting/08-M_app_lifecycle.md#4-default-seeding` — seeding is idempotent and runs only
  against an empty target (empty settings table → fully seeded; empty provider catalog → default
  providers written), and performs no network call.
- `08_Cross_Cutting/08-K_platform_specifics.md#3-application-data-paths-per-operating-system` — the
  per-OS `<app-data>` location; the directory and its subtree are created on first launch, recursively
  and idempotently, and a permission failure aborts with a modal naming the path.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#8-schema-versioning--additive-structural-steps-no-data-migration-dd-53` —
  the expected-version comparison and the no-migration rule; a higher or cross-major stored version is
  a hard startup error.
- `10_Domain_and_Data/03_PERSISTENCE_SCHEMA.md#10-seed-data` — the three built-in provider rows written
  on first start and the empty `app_settings` table.

## Design constraints

- `backend/infra/` is Qt-free (it resolves the app-data path and creates the directory); the abort
  modals are rendered by `compose.py` on the live `QApplication`, not by any backend module (ADR-0010).
- Exactly one write connection exists (DD-41) and STORY-077 opened it with the §2 pragmas already
  applied. This story's schema check is the *first statement* to run on that connection, which is
  what makes AC-5 an observable property of the launch path rather than a claim about work this
  story performs.
- No data migration ever occurs: the database is never `UPDATE`d, backfilled, downgraded, or
  overwritten automatically; an incompatible or unreadable database aborts launch untouched.
- Seeding performs no network call and writes only when its target table is empty.
- **Render the three abort modals through the existing `make_error_dialog` factory on
  `ui/common_dialogs/`'s public surface, not as inline hand-built `QMessageBox` code in
  `compose.py`.** Its `ErrorDialogPattern.FATAL` pattern already requires a `quit_callback` and
  already renders a title, a plain-language message, and an optional detail block — exactly the
  shape of "explain the failure, then exit". This is the budget-cheapest option and it stays legal
  under the "only `compose.py` imports concrete implementations" contract precisely because
  `make_error_dialog` is an existing public `api.py` factory rather than a concrete internal class,
  so no new module and no new public symbol is needed. Because nothing in `ui/common_dialogs/`
  changes, it is not a `modules:` entry and this story stays inside its three-module `M` bound.
- **Ordering caveat for the abort modals.** `make_error_dialog` needs a `Clipboard` and an
  `EventBus`, but the abort paths fire before the object graph is wired (step 8). Construct those
  two dependency-free leaves early — before the app-data step — so any abort can actually render its
  modal. This is the practical consequence of ADR-0010's decision to create the `QApplication` early
  so that every launch-abort path has something to render on.
- **The `compose.py` 50–200-line budget is shared.** STORY-077-AC-5 asserts it as a standing
  invariant on the *final* `compose.py`, so this story's prelude and its three abort paths spend from
  the same budget as STORY-076, STORY-080, and STORY-083. Reusing `make_error_dialog` instead of
  three inline dialogs is the main lever for staying inside it here.

## Acceptance criteria

### STORY-078-AC-1

Given the application-data directory does not exist and cannot be created because of a permission
failure,
when launch reaches the app-data step,
then launch aborts with a modal naming the path and the required permission, and the process exits
(EC-M-1).

### STORY-078-AC-2

Given an existing database whose persisted schema version does not match the version this build
expects,
when launch runs the schema check,
then launch aborts with the hard schema-mismatch modal naming the database file, the database is left
untouched, and the process exits (EC-M-2).

### STORY-078-AC-3

Given a database file that is present but unreadable or corrupt,
when launch attempts to open the write connection to it,
then launch aborts with an explanatory modal naming the database file, and the file is never
overwritten automatically (EC-M-3).

### STORY-078-AC-4

Default seeding is idempotent per target table:

| Target state at launch     | Seeding action                                             |
| -------------------------- | ---------------------------------------------------------- |
| Provider catalog empty     | The three bundled default providers are written            |
| Provider catalog non-empty | No provider is written; the catalog is left untouched      |
| Settings table empty       | Left empty; every setting resolves to its built-in default |

### STORY-078-AC-5

Given the application has launched as far as the schema check — the first statement run on the write
connection,
when that statement executes,
then every `03_PERSISTENCE_SCHEMA.md` §2 write-connection pragma is already in effect on that
connection.

## Test plan

- STORY-078-AC-1 — integration, `tests/integration/test_launch_app_data_dir.py`,
  `test_app_data_permission_failure_aborts_with_modal_and_exits`. Covers EC-M-1.
- STORY-078-AC-2 — integration, `tests/integration/test_launch_schema_check.py`,
  `test_schema_version_mismatch_aborts_and_leaves_db_untouched`. Covers EC-M-2.
- STORY-078-AC-3 — integration, same file, `test_unreadable_database_aborts_without_overwrite`.
  Covers EC-M-3.
- STORY-078-AC-4 — integration (table-driven, one `@pytest.mark.parametrize` row per target state),
  `tests/integration/test_launch_seeding.py`, `test_seeding_is_idempotent_per_target_table`.
- STORY-078-AC-5 — integration, `tests/integration/test_launch_schema_check.py`,
  `test_write_connection_applies_pragmas_before_first_statement`.

## Definition of done

- [ ] Every acceptance criterion has a passing test that names STORY-078.
- [ ] EC-M-1, EC-M-2, and EC-M-3 each have a passing test.
- [ ] `mypy --strict`, `ruff`, and `import-linter` pass for the touched modules.
- [ ] The traceability record validates with no orphan clause and no orphan test.
- [ ] The module inventory is unchanged.
