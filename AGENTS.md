# AGENTS.md: the uncreep playbook

You are an AI agent helping a user remove unwanted tracking, dark patterns and other creepy
behaviour from an Android app they use. This file is your procedure. Follow the phases in
order. **Phase 0 and Phase 4 need the user's input. Never skip them.**

```
0 Ground rules → 1 Acquire → 2 Decompile → 3 Identify → 4 Ask the user → 5 Patch & rebuild → 6 Deliver
```

Everything app-specific lives in `workspace/<package>/` (git-ignored) and `recipes/<package>/`.

| Command | Phase |
|---|---|
| `./uncreep setup` | once per machine or container (about 2 min, ~1 GB) |
| `./uncreep acquire <package>[@version]` | 1 |
| `./uncreep analyse <package>` | 2, and the mechanical part of 3 |
| `./uncreep new-recipe <package>` | 5 (creates `recipes/<package>/recipe.py` + `FINDINGS.md`) |
| `./uncreep build <package>` / `./uncreep verify <package>` | 5 |
| `./uncreep deliver <package> [...]` | 6 |

Reference docs: [creep catalogue](docs/creep-catalogue.md) (what to look for),
[patching guide](docs/patching-guide.md) (how to remove it),
[delivery](docs/delivery.md) (how to hand over the APK),
[findings template](docs/findings-template.md).

---

## Phase 0: Ground rules (talk to the user first)

1. **Show the disclaimer and get an explicit "yes".** Summarise [DISCLAIMER.md](DISCLAIMER.md) in
   plain words:
   - a patched app **may have new security vulnerabilities**, and the author of uncreep isn't liable;
     results depend on the AI model, and uncreep has been tested on few apps;
   - modifying an app **may breach its terms of service or local law** (copyright, anti-circumvention,
     contract), so the user must be sure it is legally permitted where they live;
   - the user accepts all risk, including **account bans** (the app is re-signed and detectable)
     and **data loss** (the store version must be uninstalled first).

   Ask the user to confirm they understand and that they are permitted to modify this app. If they
   don't confirm, stop.
2. **Ask which app** (package name such as `com.example.app`, or a Play Store link, which contains
   `id=<package>`) and, if not obvious, their phone's CPU architecture (almost always `arm64-v8a`).
3. **Scope.** uncreep removes things that work *against* the user: surveillance, profiling,
   manipulation, nagging. **Refuse** to unlock paid features, bypass licence checks, DRM or
   paywalls, enable cheating, or weaken protections for *other* people (e.g. anti-spam or
   anti-abuse systems). Ad removal is a grey area. Offer it only as an explicit option, and say it is
   most likely to breach the app's terms.
4. **Environment.** Note whether you are on the user's machine (you can hand over a file or
   `adb install`) or in a cloud container (you'll deliver via GitHub, see Phase 6, and the
   container is ephemeral). Run `./uncreep setup` if `tools/build-tools/apksigner` is missing. It needs
   Java 17+, Python 3.10+, curl, unzip, ripgrep, and ideally 8 GB RAM and 10 GB of disk.

## Phase 1: Acquire

```bash
./uncreep acquire com.example.app                 # latest from APKPure (a third-party mirror)
./uncreep acquire com.example.app@1.2.3           # a specific version
./uncreep acquire com.example.app --source f-droid
./uncreep acquire com.example.app --file ~/Downloads/app.xapk   # or a folder of base + split APKs
```

- **The best source is the user's own phone**, because it's exactly the build they run:
  `adb shell pm path com.example.app` lists the APK paths, `adb pull` each one into a folder,
  then `--file <folder>`. Offer this when the user has a computer with adb.
- Output: `workspace/<package>/input/base.apk`, `split_*.apk` and `IDENTITY.json`.
- **Check the signing certificate.** `acquire` prints the signer DN and SHA-256. Mirrors can serve
  tampered APKs. The DN should plausibly be the publisher's. If you can, compare the
  certificate with a known-good copy (the user's installed app:
  `adb shell pm dump <package> | grep -A2 signatures`, or an earlier analysis). If it looks wrong,
  stop and tell the user.
- If downloads fail (blocked mirror, region, app not listed), try another `--source`, a specific
  version, or ask the user to supply the APK.

## Phase 2: Decompile

```bash
./uncreep analyse com.example.app        # 2–15 min depending on app size
```

This writes:

| Path | What it is | Use it for |
|---|---|---|
| `workspace/<pkg>/jadx/classesN/sources/` | Java decompiled per DEX file | **reading** code |
| `workspace/<pkg>/smali/` | apktool smali | **finding patch points** (exact method signatures) |
| `workspace/<pkg>/res/` | decoded resources, if decodable | UI copy (`res/values/strings.xml`), layouts |
| `workspace/<pkg>/analysis/` | `SUMMARY.md`, `manifest.md`, `trackers.json`, `scan.md` | leads |

Optional: **REA (Reverse Engineer Anything)** is registered in `.mcp.json`, with its skill in
`.claude/skills/reverse-engineer-anything/`. Use its Android tools (`inspect_android_package`,
`search_android_classes`, `inspect_android_method`, `trace_android_references`) to trace callers
and cross-references across DEX files, which per-DEX JADX trees can't do. Plain `rg` over
`jadx/` and `smali/` covers most needs.

Special cases: React Native apps keep their logic in `assets/index.android.bundle` (Hermes
bytecode or JS). Flutter apps keep theirs in `lib/*/libapp.so`. Some vendors pack DEX files in
proprietary formats. Code you can't decompile, you can't safely patch. Say so and limit the
work to manifest-level changes.

## Phase 3: Identify creepy features

1. Read `analysis/SUMMARY.md`, then work through **every category in
   [docs/creep-catalogue.md](docs/creep-catalogue.md)** using `manifest.md`, `trackers.json`,
   `scan.md` and your own `rg` searches.
2. **Every finding must be confirmed by reading the code.** Scan hits are leads, not findings.
   Trace from the trigger (a lifecycle method, receiver, worker or UI action) to the sink (a
   network call, analytics event or upload). Note server-side switches (remote config,
   experiments) and their shipped defaults. *Capability is not current use*: say "can" when a flag
   decides.
3. Record each finding in `recipes/<package>/FINDINGS.md` (run `./uncreep new-recipe <package>`
   now, or copy [the template](docs/findings-template.md)). Each finding needs an ID (F1, F2…), category,
   severity, plain-language description, evidence (class and method, string, manifest entry),
   your proposed removal, **what the user would lose**, and the risk of breaking the app.
4. Check that what you list isn't a feature the user wants: maps need location, chat apps
   need contacts for some features, crash reporting is arguably benign. List those as *optional*
   so the user can decide.
5. Keep evidence to short references (class names, method signatures, string keys). **Don't copy
   decompiled code into the repository.**

## Phase 4: Present and ask

Give the user a short, scannable summary, worst first:

```
F1  [Critical] Uploads your contact list in the background every 24 h
    Remove: drop READ_CONTACTS + stub the upload worker. You lose: "find friends from contacts".
F2  [High]     Sends your list of installed apps to an analytics endpoint
    ...
```

Then **ask which to remove** (use a multi-select question tool if your harness has one; otherwise
a numbered list such as "reply with e.g. `1,2,4` or `all`"). Mark your recommendation, and flag
anything risky or legally sensitive (ads, login or integrity checks). **Only remove what the user
chose.** Record the choices in `FINDINGS.md` under "Chosen for removal".

## Phase 5: Patch and rebuild

1. Write `recipes/<package>/recipe.py` (see [docs/patching-guide.md](docs/patching-guide.md) and
   `recipes/_template/recipe.py`). Tag each change with its finding ID. Preferred order:
   remove the **capability** in the manifest, then **stub the code path**, then larger rewrites or
   helper classes in `recipes/<package>/smali/`.
2. `./uncreep build <package>` decodes, patches, reassembles only the changed DEX files, checks them
   with D8, rebuilds, zipaligns, signs and merges splits into a single APK. It refuses an input that
   doesn't match the recipe's SHA-256 or signer pins.
3. `./uncreep verify <package> --method 'com/foo/Bar->methodName' …` checks the signature,
   alignment and package/version, diffs permissions, queries, exported components and meta-data
   against the original, and decompiles your patched methods so you can read them back. **Read
   them.** Make sure every chosen finding is addressed and nothing else changed.
4. If the build fails, fix the recipe. Typical causes: a wrong signature (copy it from smali),
   a register count in `set_method_body`, or a method not found because the version changed.
5. **Runtime testing.** If an emulator or device is reachable (`adb devices`), install the APK, launch it,
   exercise the patched areas and watch `adb logcat` for crashes. Otherwise say clearly that the
   build was **only statically verified**.
6. Update `FINDINGS.md`: the "Removed" section lists exactly what changed, and the "Known risks" section
   lists what may break.

## Phase 6: Deliver

See [docs/delivery.md](docs/delivery.md). In short:

- **Local:** give the user `workspace/<pkg>/out/<name>.apk`, or `adb install` it.
- **Cloud with a file-sharing tool** (e.g. a "send file to user" tool): send the APK directly.
- **Cloud via GitHub:** only to a **private** repository. First confirm the remote is private (GitHub
  API, or `gh api "repos/{owner}/{repo}" -q .private`), then
  `./uncreep deliver <pkg> --github-release` (needs `gh`), or
  `./uncreep deliver <pkg> --release-branch --confirm-private`, push, and let
  `.github/workflows/release.yml` publish the Release. **Never** commit or release a patched APK in a
  public repository. If the only repository you can push to is public, stop and ask the user to
  make a private copy (docs/delivery.md explains how).

Always tell the user:
- **uninstall the store version first** (the signature differs), which **deletes the app's local data**;
- turn off auto-updates for the app, because a store update replaces the patched build. Rebuild for new versions;
- keep `keystore/uncreep.jks` (or set `UNCREEP_KEYSTORE`) so future builds can update in place. In an
  ephemeral container the key is lost when the session ends, so offer to hand it over as well;
- what was and wasn't tested, and the disclaimer.

## Hard rules

- No APKs, DEX files, decompiled sources or keystores in git. `workspace/`, `release/` and `keystore/`
  are ignored for this reason. Recipes contain patch logic and the minimum identifiers needed to
  locate code.
- Never weaken the app's own security: TLS verification, certificate pinning against third parties,
  authentication, encryption, sandboxing. If removing a feature would need that, tell the user and skip it.
- Be honest. Report what you verified, what you didn't, and anything that failed, with the output.
- Pin everything: a recipe applies to one exact build (SHA-256). For a new version, re-run
  Phases 1–5. Old patch points are hints, not truths.
