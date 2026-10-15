<p align="center">
  <img src="assets/logo.svg" alt="uncreep: Keep the app. Lose the creep." width="520">
</p>

<p align="center">
  <b>An AI-agent toolkit for finding and removing tracking and dark patterns from Android apps.</b><br>
  Point your coding agent at this repo, name an app, choose what goes, get an APK back.
</p>

<p align="center">
  <a href="AGENTS.md">Agent playbook</a> ·
  <a href="docs/creep-catalogue.md">Creep catalogue</a> ·
  <a href="docs/patching-guide.md">Patching guide</a> ·
  <a href="docs/delivery.md">Delivery</a> ·
  <a href="DISCLAIMER.md"><b>Disclaimer</b></a>
</p>

---

> [!CAUTION]
> **Read the [DISCLAIMER](DISCLAIMER.md) before use.** In short:
> - **Patched apps may contain new security vulnerabilities.** The creator of this repository can't be held
>   liable for them. AI is good at reverse engineering and writing code, but different models behave
>   differently, and uncreep has **not been tested against many apps**.
> - **Modifying an app may be against its terms and conditions or the law where you live.** Only use uncreep
>   where you are sure it is legally permitted.
> - **The creator of this repository waives all responsibility to the maximum extent permitted by law.** You
>   use uncreep and anything it produces entirely at your own risk.

## Why

Popular apps do a lot more than their features need. The
[algorithmresearch](https://github.com/iSaluki/algorithmresearch) project statically reverse-engineered
sixteen popular Android apps and [documented](https://github.com/iSaluki/algorithmresearch/blob/main/REPORT.md)
in-app browsers that monitor the third-party websites you visit, location collection bundled with Wi-Fi
and cell-tower data, detectors for which AI and automation apps you have installed, consent that is assumed
to be "yes", contact lists uploaded in the background, and engagement mechanics built to keep you scrolling.

Most of this lives in code you can read, and much of it can be switched off. uncreep packages that
workflow so an AI agent can repeat it on the app **you** care about, with **you** deciding what gets removed.

## How it works

```
 ┌───────────┐   ┌────────────┐   ┌────────────┐   ┌───────────┐   ┌───────────────┐   ┌───────────┐
 │ 1 Acquire │ → │ 2 Decompile│ → │ 3 Identify │ → │ 4 You     │ → │ 5 Patch &     │ → │ 6 Deliver │
 │ the APK   │   │            │   │ creepy bits│   │   choose  │   │   rebuild     │   │ the APK   │
 └───────────┘   └────────────┘   └────────────┘   └───────────┘   └───────────────┘   └───────────┘
  apkeep, or      JADX, apktool,   manifest audit,   the agent       remove permissions,  direct download,
  your own phone  REA (optional)   tracker scan,     lists findings  stub code paths,     adb, or a private
  + signer check                   pattern scan,     with trade-offs re-sign, merge       GitHub Release
                                   agent reads code  and asks you    splits, verify
```

The agent does the reading and the patching. The scripts do the mechanical parts reproducibly. You
make every decision about what is removed.

## Quick start (humans)

1. Open this repository in an AI coding agent that can run shell commands (for example
   [Claude Code](https://claude.ai/code), locally or on the web, or any agent that reads `AGENTS.md`).
2. Say something like:

   > **Uncreep `com.example.app` for me.**

3. The agent shows you the disclaimer, downloads and checks the app, analyses it, then **lists what it
   found and asks what to remove**, with what each removal costs you (for example "no more contact upload,
   but no friend suggestions from contacts").
4. You get a single installable `.apk`. Uninstall the store version first (this deletes the app's
   local data), then install the patched one.

Running in the cloud? The agent can publish the APK as a GitHub Release, but **only in a private
copy** of this repo (patched apps contain their publisher's code and must not be redistributed).
See [docs/delivery.md](docs/delivery.md).

## Quick start (agents)

**Read [AGENTS.md](AGENTS.md) and follow it phase by phase.** Phase 0 (disclaimer + user consent) and
Phase 4 (ask the user what to remove) are mandatory.

```bash
./uncreep setup                                  # tools: apkeep, apktool, JADX, build-tools, APKEditor, REA
./uncreep acquire com.example.app                # → workspace/com.example.app/input/
./uncreep analyse com.example.app                # → workspace/com.example.app/analysis/SUMMARY.md
#   … read code, write recipes/com.example.app/FINDINGS.md, ask the user …
./uncreep new-recipe com.example.app             # → recipes/com.example.app/recipe.py (pins filled in)
./uncreep build com.example.app                  # → workspace/com.example.app/out/<name>.apk
./uncreep verify com.example.app --method 'com/example/Tracker->start'
./uncreep deliver com.example.app                # or --github-release / --release-branch --confirm-private
```

## What a recipe looks like

```python
PACKAGE = "com.example.app"
VERSION = "1.2.3"
BASE_SHA256 = "…"            # recipes apply to one exact build

def patch_manifest(m):
    m.remove_permissions({"android.permission.READ_CONTACTS"}, why="[F1] contact upload")
    m.remove_query_packages({"com.other.app"}, why="[F2] installed-app profiling")

def patch_code(root, log):
    stub_method(root, "com/example/analytics/EventSink", "log(Ljava/lang/String;)V")     # [F3]
    stub_method(root, "com/example/flags/Flags", "isFeedAutoplayEnabled()Z", False)      # [F4]
```

Only the changed DEX files are rebuilt. Resources, assets and native libraries are copied byte-for-byte,
which keeps large apps buildable. Every patched DEX file is validated with D8. See the
[patching guide](docs/patching-guide.md).

## Requirements

Linux x86-64 (or WSL), Java 17+, Python 3.10+, `curl`, `unzip`, `ripgrep`, and about 8 GB RAM and
10 GB of disk for large apps. Node.js is optional (for REA). `./uncreep setup` downloads everything else,
version-pinned and checksum-verified, into `tools/`.

## Repository layout

| Path | Contents |
|---|---|
| `AGENTS.md`, `CLAUDE.md` | The agent playbook (and Claude Code specifics) |
| `uncreep` | CLI entry point |
| `scripts/` | acquire, identity check, manifest audit, tracker scan, decompile + pattern scan, summary, verify, deliver |
| `patchkit/` | The patcher: binary-manifest editor, smali helpers, build pipeline |
| `recipes/_template/` | Starting point for a per-app recipe |
| `docs/` | Creep catalogue, patching guide, delivery guide, findings template |
| `.claude/skills/` | `uncreep` workflow skill; [REA](https://github.com/morluto/rea) skill (MIT, © morluto) |
| `.mcp.json` | Registers the REA MCP server for Claude Code |
| `.github/workflows/release.yml` | Publishes a staged APK as a Release, **private repositories only** |
| `workspace/`, `keystore/`, `release/` | Git-ignored: apps, decompiled code, builds, your signing key |

## Limitations

- **Static first.** Agents read code rather than run it. Unless an emulator or device is available,
  builds are only statically verified (build, D8, signature, manifest diff, decompiled read-back).
- **One build per recipe.** Obfuscated names change every release, so updating the app means re-running
  the workflow.
- **Re-signed apps are detectable.** Some apps refuse to run or log in, or restrict accounts, when the
  signature isn't the publisher's. Play Integrity checks will fail.
- **Not everything is patchable.** React Native, Flutter and proprietary-packed code limit what can be
  changed, and server-side processing can't be changed at all.

## Contributing

Issues and pull requests that improve the tooling, docs and creep catalogue are welcome. Please don't
submit APKs, decompiled code or app-specific recipes to this repository.

## Credits

Built on [apkeep](https://github.com/EFForg/apkeep) (EFF), [Apktool](https://github.com/iBotPeaches/Apktool),
[JADX](https://github.com/skylot/jadx), [APKEditor](https://github.com/REAndroid/APKEditor), the Android SDK
build-tools, [Exodus Privacy](https://exodus-privacy.eu.org/) tracker signatures,
[androguard](https://github.com/androguard/androguard) and [REA](https://github.com/morluto/rea). Analysis
methods come from [algorithmresearch](https://github.com/iSaluki/algorithmresearch).

## License

[MIT](LICENSE) for uncreep's own code and docs. That grants no rights in any app you process with it. See
the [DISCLAIMER](DISCLAIMER.md).
