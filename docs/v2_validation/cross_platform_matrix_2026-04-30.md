# Cross-Platform Validation Matrix — 2026-04-30

## Scope

Manual validation pass required by Section 9.6 of the V2 implementation plan.
Captures visual fidelity across platforms and themes against the Section 8 design guide.

## Platform Coverage

| Platform | Status | Notes |
|----------|--------|-------|
| macOS | In progress | Primary development machine |
| Windows | Skipped — not available | Requires separate CI runner or contributor validation |
| Linux | Skipped — not available | Requires VM or CI runner with display |

## How to complete a cell

Run `uv run ollama_llm_bench`, navigate to the surface, compare against the V2 design guide
(`docs/v2/v2-ui-design-guide.html`), then mark:
- ✅ matches the design guide
- ⚠ minor deviation (add a note row below the table)
- ❌ blocking issue (file a follow-up against the relevant Section 1–8)

Screenshots go in `docs/v2_validation/screenshots/<os>_<theme>/` (e.g., `macos_dark/`).

---

## Validation Matrix

| Surface | macOS Light | macOS Dark | Windows Light | Windows Dark | Linux Light | Linux Dark |
|---------|------------|------------|---------------|--------------|-------------|------------|
| Main Window | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| Settings → Providers tab | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| Settings → General tab | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| Pre-start dialog | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| Resume dialog | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| Detached table window | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| Detached chart window | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| `QToolTip` | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| `QSpinBox` arrows | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| `QComboBox` dropdown | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| `QCheckBox` indicator | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| `QRadioButton` indicator | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| `QScrollBar` | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| `QSplitter` handles | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| `QHeaderView` | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| Status bar messages | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| `QMessageBox` | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| Drag-and-drop visual feedback | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| Theme switching (System mode toggle) | ☐ | n/a | ☐ | n/a | ☐ | n/a |
| Font rendering — sans serif | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |
| Font rendering — monospace | ☐ | ☐ | ☐ | ☐ | ☐ | ☐ |

---

## Dark Theme Parity Checklist (Section 9.7)

Verify these dark-mode-specific concerns before marking the dark column complete:

- [ ] All sub-controls (`QSpinBox::up-button`, `QComboBox::drop-down`, etc.) use dark token values
- [ ] `text_disabled` on `bg_secondary` (`#4B5563` on `#1F2937`) reaches WCAG AA contrast (≥ 4.5:1)
- [ ] `failure` text (`#F87171`) on `failure_bg` (`#7F1D1D`) is legible
- [ ] Health dots: `down` state (`#F87171`) is distinguishable from `unknown` state (`#FBBF24`) without colour-only signalling

---

## Known Platform Deviations

*(Fill in during validation — one row per deviation)*

| Date | Platform | Theme | Surface | Severity | Description | Follow-up |
|------|----------|-------|---------|----------|-------------|-----------|
| — | — | — | — | — | None recorded yet | — |

---

## Notes

- Windows and Linux columns must be completed before Section 9 can be marked "done".
- Any ❌ cell generates a follow-up issue against the relevant Section 1–8.
- Screenshots should be committed alongside an updated version of this file.
