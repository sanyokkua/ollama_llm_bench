## Bug Reporting and Diagnostics (no crash reporting)

**Status:** Draft
**Owner:** architect
**Audience:** user, human
**Last Updated:** 2026-06-04
**Cross-references:** 13_Distribution_and_Release/08_UNINSTALL.md, 10_Domain_and_Data/07_FILE_LAYOUT.md, 12_Quality_and_NFRs/09_PRIVACY_POLICY.md, 16_Engineering_Standards/06_LOGGING_STANDARD.md, 08_Cross_Cutting/08-M_app_lifecycle.md, 07_Common_Dialogs/about_dialog.md

This document describes how a user reports a defect in Ollama LLM Bench. The application performs **no** automatic crash reporting, sends **no** telemetry, and generates **no** support bundle. Nothing about a crash or a defect leaves the machine unless the user deliberately shares it.

---

## 1. No Automatic Crash Reporting and No Telemetry

Ollama LLM Bench performs no automatic crash reporting and sends no telemetry. There is no crash-reporting service and no analytics service, and the application never packages or uploads diagnostic information. This policy is consistent with `12_Quality_and_NFRs/09_PRIVACY_POLICY.md`.

The application log and the per-run logs are the only crash evidence, and they stay on the user's machine under their control (see `08_Cross_Cutting/08-M_app_lifecycle.md` §8).

## 2. What Happens When the Application Crashes

When an unrecoverable error occurs, the application catches it, records it in the application log at `<app-data>/logs/app/app.log`, closes its database cleanly, and exits. A failure inside a background benchmark run is caught and recorded in the application log, the affected run is marked as failed, and the application keeps running and stays usable. The crash policy is specified in `08_Cross_Cutting/08-M_app_lifecycle.md` §8.

In every case the failure is written to the application log; that log file is the diagnostic record.

## 3. Reporting a Bug

To report a bug, the user can open the project's GitHub repository (the repository link is shown in the **About** dialog, `07_Common_Dialogs/about_dialog.md`) and file an issue describing the problem. If the user chooses to, they can manually attach their `app.log` file to the issue — the application does not package or upload anything on their behalf. The **About** dialog shows the application-data folder with **Open** and **Copy** actions; `app.log` lives in its `logs/app/` subfolder, so the user can locate the file when they want it.

There is no automated packaging, no generated archive, and no "attach the bundle" step. The application log (and, where relevant, the per-run logs) are the diagnostic evidence the user may share at their own discretion.
