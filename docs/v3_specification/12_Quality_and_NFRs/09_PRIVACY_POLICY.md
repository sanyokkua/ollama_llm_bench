# Privacy Policy

**Status:** Draft
**Owner:** human-reviewer
**Audience:** user, human
**Last Updated:** 2026-06-06
**Cross-references:** 12_Quality_and_NFRs/02_SECURITY_MODEL.md, 12_Quality_and_NFRs/03_OBSERVABILITY.md, 10_Domain_and_Data/07_FILE_LAYOUT.md, 10_Domain_and_Data/08_REDACTION_PATTERNS.md, 16_Engineering_Standards/06_LOGGING_STANDARD.md, 00_Foundation/05_CONSTRAINTS.md

This is the privacy policy for Ollama LLM Bench, written to be read by the people who use it. It states plainly what data the application keeps, where it keeps it, what it never does, and what leaves your machine. The short version: Ollama LLM Bench is a local desktop tool. It collects no telemetry, sends no analytics, and phones home to no one. Your data stays on your computer. The only network traffic the application makes is to the LLM and embedding providers you yourself configure.

---

## Table of Contents

1. The short version
2. No telemetry, no analytics, no tracking
3. What stays on your machine
4. What leaves your machine
5. What you control
6. Secrets and how they are protected
7. Children and personal data
8. Changes to this policy

---

## 1. The short version

Ollama LLM Bench is a desktop application that benchmarks large language models. It runs entirely on your own computer.

- It collects **no telemetry** and **no usage analytics**.
- It has **no account system** and asks for **no sign-in**.
- It does **not** send your benchmark data, your task files, your settings, your results, or your logs anywhere.
- The **only** network connections it makes are to the LLM and embedding providers **you** configure — and those connections carry only the requests you asked the application to make.
- Everything else — your runs, your results, your logs, your settings — stays in a folder on your computer that only your user account can read.

If you never configure a remote provider and only benchmark a model running on your own machine, the application makes no outbound network connection at all beyond your own computer.

## 2. No telemetry, no analytics, no tracking

This is a binding product decision and it applies to every version and every download of the application.

- There is **no analytics service**. The application does not count launches, does not record which features you use, and does not measure how long you use it.
- There is **no crash-reporting service**. When the application crashes, nothing is sent anywhere. A crash is recorded only in a local log file on your machine (see Section 4 for how you can choose to share that yourself).
- There is **no "phone-home"** of any kind — no background connection to the developers, no licence check, no version beacon that reports your existence.
- There is **no advertising** and **no third-party tracking code**. The application embeds no analytics SDK and no tracking pixel.

The application cannot quietly start collecting data in a future update either: the absence of telemetry is part of the application's specification and its constraints (00_Foundation/05_CONSTRAINTS.md), and any future update that added data collection would be a deliberate, documented change you would be told about (Section 8).

## 3. What stays on your machine

All of the application's data lives in a single folder on your computer, the application data directory. Its location depends on your operating system:

| Operating system | Where the application data folder is |
|---|---|
| macOS | `~/Library/Application Support/OllamaLLMBench/` |
| Linux | `~/.local/share/OllamaLLMBench/` (or under `$XDG_DATA_HOME` if you have set it) |
| Windows | `%LOCALAPPDATA%\OllamaLLMBench\` |

That folder, and the files in it that could contain a secret, are created so that **only your user account can read them**. Nothing in it is uploaded anywhere. It contains:

- **Your benchmark database** — every run you have made, every result, every model and task snapshot, your provider configurations, and your settings. This is a single database file.
- **Your logs** — a general application log, and one detailed log file per benchmark run. These record what the application did so you can diagnose a problem.
- **Your settings backups** — automatic snapshots of your settings, kept so you can undo a settings change or import.
- **Exported files**, if you choose the option to save exports into this folder.

Your **task files** — the YAML files that define what to benchmark — are not kept in this folder at all. They are ordinary documents you keep wherever you like on your computer; the application only opens them when you point it at them.

## 4. What leaves your machine

Only one thing ever leaves your computer automatically, and it happens only because you chose it.

### 4.1 Requests to the providers you configured

To benchmark a model, the application has to send that model a prompt and receive its answer. So when you run a benchmark, the application connects to the LLM and embedding providers **you** set up in Settings, and sends them the prompts your benchmark uses.

- It connects **only** to the provider addresses you entered. The application has no hidden built-in endpoint.
- It sends **only** what is needed to run your benchmark: the prompts, and the credentials for that provider.
- If the model you are benchmarking runs on your own machine — a local provider — then even this traffic never leaves your computer.

This is not "data collection". It is the application doing the job you asked it to do: a benchmarking tool has to talk to the thing it benchmarks. You decide which providers exist and what they point at.

### 4.2 Reporting a bug

The application performs **no** automatic crash reporting and never packages or uploads diagnostic information. If you hit a problem and want help, you can file an issue on the project's GitHub repository (the link is in the **About** dialog) and, if you choose, manually attach your application log file (`app.log`). The About dialog shows the application-data folder (with **Open** and **Copy** actions); `app.log` lives in its `logs/app/` subfolder, so you can find it from there.

- Nothing is packaged or sent on your behalf. Sharing your log is entirely your decision.
- The application log is already passed through the application's redaction step, which removes secrets such as API keys (see Section 6), so a shared log is safe.

## 5. What you control

You are in control of all of your data, because all of it is files on your computer.

- **You decide which providers exist.** No provider is contacted that you did not configure.
- **You can delete any run** from inside the application. Deleting a run removes it and all its results and logs.
- **You can delete the whole application data folder** to remove every trace of the application's data. The application keeps nothing anywhere else.
- **Your API keys never go into the application's database.** Instead of a key, you enter the *name* of an environment variable that holds it; the application stores only that name and reads the actual key from your environment when it needs it (see Section 6).
- **You decide whether to share your logs** when reporting a bug; the application never sends them for you.
- **You can clear your logs.** The application offers a housekeeping action to remove old run logs, and old logs are pruned automatically over time.

## 6. Secrets and how they are protected

Some providers need an API key. The application treats every API key as a secret and protects it in three ways.

- **Owner-only files.** The database file and the log files are created so that only your user account can read them. On a shared computer, another account cannot read your keys.
- **The key never enters the database — you store its environment-variable name.** Instead of typing a key directly, you enter the *name* of an environment variable that holds it, like `OPENAI_API_KEY`. The application stores only that name — never the key itself — in its database, and reads the actual key from your environment only when it needs to make a request. The field accepts only a valid environment-variable name (or nothing, for a local provider that needs no key); if you paste an actual key, the application rejects it inline and asks for the variable name instead. The application resolves the configured environment variables into an in-memory secrets snapshot at startup and whenever the provider configuration is reloaded (so a key you add or change in Settings is picked up without a restart); a variable must already exist in the environment the app process can see — a variable you set in a single terminal is only visible if you launched the app from that same terminal, so for it to be picked up generally, set it system-wide or in your shell profile.
- **Redaction at the points where data could realistically leave the local-app context.** The application applies a redaction step that detects and removes anything that looks like an API key, a token, or an authorization header at two specific surfaces: the system/debug application log file (so a shared log is safe) and the messages of any error the application catches from a provider's SDK (so an error displayed or logged cannot echo back the credentials the SDK was using). On everything else — what you see on screen, what you copy to your clipboard, what you export as CSV or Markdown, what is recorded in the per-run benchmark log file — the application shows you your **own** prompts and the responses your **own** model produced, exactly as they are. This is your data on your computer; the application does not redact it from you.

The full technical detail of secret handling is in 12_Quality_and_NFRs/02_SECURITY_MODEL.md and 10_Domain_and_Data/08_REDACTION_PATTERNS.md.

## 7. Children and personal data

Ollama LLM Bench is a developer and researcher tool for benchmarking language models. It is not directed at children and is not designed to process personal data.

The application does not ask you for your name, your email, your location, or any identifying information, and it has no account system that would collect such data. The only data the application holds is the benchmarking data you create with it — the runs, results, tasks, settings, and logs described in Section 3 — all of which stay on your own computer.

If you choose to put personal data into a task file or a prompt, the application will benchmark it like any other text and store it in your local database; that is your content and your choice, and the application treats it no differently from any other text you supply.

## 8. Changes to this policy

This privacy policy is part of the application's specification. The behaviour it describes — no telemetry, local-only data, network traffic only to the providers you configure — is a binding part of how the application is built, not a promise made separately from the software.

If a future version of the application were to change any of this behaviour, that change would be a deliberate, documented change to the application's specification and would be stated in the application's release notes. The application will not quietly begin collecting data between versions; the absence of telemetry is enforced in the software itself.
