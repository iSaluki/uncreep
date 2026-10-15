# Delivery

`./uncreep deliver <package>` stages `workspace/<package>/release/`: the APK(s), `SHA256SUMS`, a
`TAG` and `NOTES.md` (built from the "Removed" section of `recipes/<package>/FINDINGS.md`). Then
pick a route.

> **A patched app contains its publisher's code. Never publish it from a public repository.**
> uncreep refuses to: `deliver --github-release` checks visibility, `--release-branch` requires
> `--confirm-private`, and the release workflow fails in public repositories. Pushing a commit to a
> public repository publishes it, even before any workflow runs. Check first.

## 1. Directly (local sessions, or a harness that can send files)

- Same machine as the phone: `adb install workspace/<pkg>/out/<name>.apk`
- Otherwise give the user the single APK `workspace/<pkg>/out/<name>.apk`. If the harness has a
  "send file to user" tool, use it. They open it on the phone, allowing "install unknown apps"
  for their browser or file manager when Android asks.
- Split set instead of the merged APK: `adb install-multiple workspace/<pkg>/out/<name>-base.apk workspace/<pkg>/out/<name>-config.*.apk`

## 2. GitHub Release with `gh` (cloud sessions)

```bash
gh api "repos/{owner}/{repo}" -q .private   # must print true
./uncreep deliver <pkg> --github-release
```

## 3. GitHub Release via a pushed commit (cloud sessions without `gh`)

For agents that can `git push` but can't upload release assets:

1. Confirm the remote is **private** (GitHub API, or ask the user).
2. `./uncreep deliver <pkg> --release-branch --confirm-private` splits the APKs into 45 MB parts
   under `release/` (GitHub rejects files over 100 MB) and commits them.
3. Push the branch. `.github/workflows/release.yml` triggers on `release/TAG`, reassembles and
   checks the APKs, and creates a Release named after the tag.
4. Give the user the Release link. Afterwards, `git rm -r release/` in a follow-up commit (the
   parts stay in the private history).

If the session can only push to a specific branch, push the release commit there. The workflow
runs on any branch.

### Making a private copy of uncreep

GitHub doesn't allow private forks of public repositories. Instead:

1. Create a new **private** repository on GitHub (e.g. `you/uncreep-private`), empty.
2. `git clone https://github.com/iSaluki/uncreep && cd uncreep && git remote set-url origin https://github.com/you/uncreep-private && git push -u origin main`
3. Enable Actions for it if prompted, and run the agent against the private copy.

## Installing on the phone

- **Uninstall the store version first.** The signing key differs, so Android won't update over it.
  Uninstalling **deletes the app's local data**, so back up anything you need.
- **Turn off auto-update** for the app (or the store will replace it). For a new version, re-run
  uncreep (Phases 1–5). Recipes are version-specific.
- **Keep the signing key** (`keystore/uncreep.jks`, password `uncreep` unless
  `UNCREEP_KEYSTORE_PASSWORD` was set). Builds signed with the same key install as updates without data
  loss. In an ephemeral cloud container the key disappears with the session. Hand it to the user,
  or point `UNCREEP_KEYSTORE` at a persistent location. Treat it as a secret, and **never commit it**.
- On the phone with Termux: `termux-setup-storage`, copy the APK to `~/storage/downloads`, then
  `termux-open ~/storage/downloads/<name>.apk`.
