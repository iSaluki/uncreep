---
name: uncreep
description: Remove tracking, dark patterns and other unwanted behaviour from an Android app. Use when the user asks to "uncreep", de-track, de-bloat or privacy-patch an Android app or APK, or to rebuild an app without certain features.
---

# uncreep

Follow `AGENTS.md` at the repository root, phase by phase:

0. Show the disclaimer (DISCLAIMER.md) and get the user's explicit confirmation that they understand the risks and are legally permitted to modify the app. Establish the package name and whether you run locally or in the cloud. Run `./uncreep setup` if tools are missing.
1. `./uncreep acquire <package>` and check the signer.
2. `./uncreep analyse <package>`.
3. Confirm findings in code using docs/creep-catalogue.md and write `recipes/<package>/FINDINGS.md`.
4. Present the findings, worst first, with what each removal costs, and **ask the user which to remove**. Remove nothing they didn't choose.
5. Write `recipes/<package>/recipe.py`, then `./uncreep build <package>` and `./uncreep verify <package> --method ...`. Read the patched code back.
6. `./uncreep deliver <package>`: hand the APK over directly, or via a GitHub Release in a **private** repository only.

Never commit APKs, decompiled code or keystores. Never weaken the app's own security. Report honestly what was and wasn't tested.
