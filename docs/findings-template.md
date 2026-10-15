# Findings: <App name> <version> (`<package>`)

- Base APK SHA-256: `…`
- Signer: `…` (checked against: …)
- Analysed with: uncreep `<commit>`, <agent / model>, <date>
- Method: static analysis only, unless "Runtime testing" below says otherwise.

> Assessments here are opinions about what the user may not want, not legal conclusions.
> "Can" means the code is capable of it, and whether it runs may depend on server-side switches.

## Findings

| ID | Severity | Category | Finding | Server-gated? |
|---|---|---|---|---|
| F1 | Critical | A2 contact upload | … | no |
| F2 | High | … | … | yes, default on |

### F1: <one-line title>

- **What it does:** plain language, for the user.
- **Evidence:** `com/example/Foo->bar()V` (classes3), string `"contact_upload"`, manifest `READ_CONTACTS`.
- **Trigger → sink:** e.g. app start → `UploadWorker` every 24 h → `POST /contacts`.
- **Proposed removal:** remove `READ_CONTACTS`; stub `UploadWorker.doWork()` → success.
- **You would lose:** "find friends from contacts".
- **Risk:** low (runtime permission; app handles denial).

<!-- repeat per finding -->

## Chosen for removal

User's choice on <date>: F1, F2, …  (not chosen: F3 because …)

## Removed

<!-- What the build actually changed, one line per change, tagged with the finding ID.
     deliver.sh copies this section into the release notes. -->
- [F1] Removed permission `READ_CONTACTS`; contact upload worker never runs.

## Known risks

- …

## Runtime testing

- Not run on a device / emulator. Only statically verified (build, D8, signature, manifest diff, decompiled read-back).
